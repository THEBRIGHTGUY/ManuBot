"""ManuBot - an advanced Discord bot that imitates a real person's texting style.

Features: slash commands, multi-personality, auto-training, archive/lore,
configurable models & stats. See README.md for deployment.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import List, Optional

from dotenv import load_dotenv

# Load credentials from either .env or the legacy `env` file
load_dotenv(".env")
load_dotenv("env")

PREFIX = "!"
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = int(os.getenv("GUILD_ID", "0") or 0)
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

# All persistent files (chroma_db/, json stores) live under DATA_DIR.
# On Render/Railway/Fly mount a persistent volume at /data and set DATA_DIR=/data.
DATA_ENV = os.getenv("DATA_DIR", "").strip()
DATA_DIR = os.path.abspath(DATA_ENV) if DATA_ENV else os.getcwd()
os.makedirs(DATA_DIR, exist_ok=True)

# ChromaDB resolves its onnx-model cache path (<HOME>/.cache/chroma/onnx_models)
# AT IMPORT TIME via Path.home(). It must therefore be set BEFORE any chromadb
# import happens below, otherwise the model re-downloads to the ephemeral
# container home on every deploy.
if DATA_ENV:
    os.environ["HOME"] = DATA_DIR
    os.makedirs(os.path.join(DATA_DIR, ".cache", "chroma", "onnx_models"), exist_ok=True)

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("manubot")
log.info("Data directory: %s", DATA_DIR)

# NOTE: keep any import that pulls in chromadb BELOW the HOME override above.
import discord  # noqa: E402
from discord.ext import commands  # noqa: E402

from core.config import BotConfig, JsonStore  # noqa: E402
from core.database import Database  # noqa: E402
from core.groq_client import GroqClient  # noqa: E402
from core.memory import ConversationMemory  # noqa: E402
from core.personality import PersonalityManager  # noqa: E402

OWNER_IDS = {int(x) for x in os.getenv("OWNER_IDS", "0").split(",") if x.strip().lstrip("-").isdigit()}
if OWNER_IDS:
    os.environ["OWNER_IDS"] = ",".join(str(x) for x in OWNER_IDS)


class ManuBot(commands.Bot):
    """Bot subclass carrying shared services and runtime state."""

    def __init__(self, *args, **kwargs):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.guilds = True
        intents.members = True
        intents.reactions = True

        super().__init__(command_prefix=PREFIX, intents=intents, help_command=None, *args, **kwargs)
        self.owner_ids = OWNER_IDS or None

        def join(*names: str) -> str:
            return os.path.join(DATA_DIR, *names)

        # services
        self.db = Database(persist_path=join("chroma_db"))
        self.config = BotConfig(join("server_configs.json"))
        self.memory = ConversationMemory(join("conversation_history.json"))
        self.llm = GroqClient()
        self.personalities = PersonalityManager(self.config)
        self.lore = JsonStore(join("incidents.json"))
        self.message_doc_map = JsonStore(join("message_doc_map.json"))

        # runtime state
        self.uptime = time.time()
        self.stats = {"auto_replies": 0, "slash_chats": 0}

    # -- wiring ---------------------------------------------------------------
    def track_message(self, message_id: int, doc_id: str, collection: str, guild_id: int, channel_id: int, query: str):
        """Remember that a bot message maps to a stored training doc (for reactions)."""
        self.message_doc_map.set(str(message_id), {
            "doc_id": doc_id,
            "collection": collection,
            "guild_id": guild_id,
            "channel_id": channel_id,
            "query": query,
            "source": "generated",
            "sent_at": time.time(),
        })

    async def setup_hook(self) -> None:
        @self.tree.error
        async def _tree_error(interaction: discord.Interaction, error: discord.app_commands.AppCommandError):
            app_commands = discord.app_commands
            if isinstance(error, app_commands.CommandOnCooldown):
                await interaction.response.send_message("Slow down!", ephemeral=True)
            elif isinstance(error, app_commands.MissingPermissions):
                await interaction.response.send_message("You don't have permission to use that.", ephemeral=True)
            elif isinstance(error, app_commands.CheckFailure):
                await interaction.response.send_message("That command isn't available to you.", ephemeral=True)
            else:
                log.exception("unhandled command error: %s", error)
                try:
                    await interaction.response.send_message(f"Command errored: {error}", ephemeral=True)
                except discord.HTTPException:
                    pass

        for cog in (
            "cogs.chat",
            "cogs.personality",
            "cogs.training",
            "cogs.archive",
            "cogs.config",
            "cogs.stats",
            "cogs.admin",
            "cogs.help",
        ):
            try:
                await self.load_extension(cog)
                log.info("loaded %s", cog)
            except Exception as exc:  # noqa: BLE001
                log.exception("failed to load %s: %s", cog, exc)

    async def on_ready(self):
        log.info("Logged in as %s (ID %s)", self.user, self.user.id)
        log.info("Guilds: %s", ", ".join(g.name for g in self.guilds))
        for guild in self.guilds:
            self.config.set_default_guild_config(guild.id)

        await asyncio.to_thread(self.db.warm_up)
        log.info("Embedder warm-up complete")

        # Sync commands to EVERY guild the bot is in so they always work.
        # NOTE: commands are declared as *global*, and discord.py's guild sync
        # only posts commands explicitly bound to that guild — a bare guild sync
        # would POST an empty array (wiping commands). copy_global_to() clones
        # the globals into the guild's scope first, making them appear instantly.
        for guild in self.guilds:
            try:
                self.tree.copy_global_to(guild=guild)
                registered = await self.tree.sync(guild=discord.Object(id=guild.id))
                names = [c.name for c in registered] if registered else []
                log.info("Synced %d commands to guild %s: %s", len(names), guild.id, ", ".join(names) or "(none)")
            except Exception as exc:  # noqa: BLE001
                log.warning("guild sync failed for %s: %s", guild.id, exc)

        # Optionally also publish globally (takes up to 1h to propagate).
        if os.getenv("SYNC_GLOBAL", "0") == "1":
            await self.tree.sync()
            log.info("Synced global commands")

    async def on_guild_join(self, guild: discord.Guild):
        self.config.set_default_guild_config(guild.id)
        log.info("Joined guild %s", guild.name)

    def run_bot(self):
        if not DISCORD_TOKEN:
            raise SystemExit("Missing DISCORD_TOKEN in env/.env")
        self.run(DISCORD_TOKEN)


if __name__ == "__main__":
    bot = ManuBot()
    bot.run_bot()