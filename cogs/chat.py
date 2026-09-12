"""Core chat: /chat command, auto-reply, auto-train ingestion, reaction feedback."""

from __future__ import annotations

import logging
import re

import discord
from discord import app_commands
from discord.ext import commands

from core.prompt import build_system_prompt, select_examples
from core.database import ARCHIVE_COLLECTION
from utils.checks import RateLimiter
from utils.embeds import (CHAT, ERROR, make_embed, error_embed, success_embed)
from utils.helpers import strip_mentions, truncate

log = logging.getLogger("manubot.chat")

_THUMB_LIKE = {"👍": 1.0, "👀": 0.7, "💯": 1.0, "❤️": 1.0}
_UNLIKE = {"👎": 0.0, "🤮": 0.0}
_ARCHIVE_EMOJI = "📌"
_REGENERATE = "🔄"


class ChatCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._limiter = RateLimiter()

    # ------------------------------------------------------------------ utils
    def _relevant_lore(self, content: str) -> dict:
        """Pick incidents whose keywords overlap the user's message."""
        lore = self.bot.lore.data()
        if not lore:
            return {}
        tokens = set(re.findall(r"[a-z0-9]+", content.lower())) - {"the", "a", "an", "is", "are", "and", "of", "to", "for", "in", "on", "with"}
        if not tokens:
            return {}
        scored = []
        for name, info in lore.items():
            words = set(re.findall(r"[a-z0-9]+", f"{name} {info.get('description', '')}".lower()))
            overlap = len(words & tokens)
            if overlap:
                scored.append((overlap, name, info))
        scored.sort(key=lambda t: t[0], reverse=True)
        return {name: info for _, name, info in scored[:3]}

    async def _generate_once(self, guild_id: int, channel_id: int, content: str) -> tuple:
        """Run the full mimic pipeline. Returns (reply, doc_id)."""
        person = self.bot.personalities.get_active(guild_id)
        similar = self.bot.db.query(person.collection, content, n_results=12)
        examples = select_examples(similar, max_examples=8)
        lore = self._relevant_lore(content)
        history = self.bot.memory.get(guild_id, channel_id)
        system = build_system_prompt(person.name, examples, lore)

        messages = history + [{"role": "user", "content": content}]
        max_tokens = self.bot.config.get(guild_id, "max_tokens", 900)
        temperature = self.bot.config.get(guild_id, "temperature", 0.9)
        model = self.bot.config.get(guild_id, "model")

        reply = await self.bot.llm.agenerate(
            system=system,
            messages=messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
        )

        history_len = self.bot.config.get(guild_id, "history_length", 12)
        self.bot.memory.push(guild_id, channel_id, "user", content, history_len)
        self.bot.memory.push(guild_id, channel_id, "assistant", reply, history_len)

        doc_id = None
        min_len = self.bot.config.get(guild_id, "min_response_length", 3)
        if reply and len(reply.strip()) > min_len:
            doc_id = self.bot.db.add(
                person.collection,
                reply,
                {"source": "generated", "quality": 0.5, "author": self.bot.user.name if self.bot.user else "ManuBot"},
            )
        return reply, doc_id

    # --------------------------------------------------------------- commands
    @app_commands.command(name="chat", description="Talk to the bot - it replies as the active personality")
    @app_commands.describe(message="What you want to say")
    async def chat(self, interaction: discord.Interaction, message: str):
        if not interaction.guild:
            await interaction.response.send_message(embed=error_embed("Works in servers only"), ephemeral=True)
            return
        cooldown = self.bot.config.get(interaction.guild_id, "cooldown_seconds", 5)
        key = f"chat:{interaction.guild_id}:{interaction.user.id}"
        if not self._limiter.check(key, cooldown):
            await interaction.response.send_message(embed=error_embed(f"Slow down - one message every {cooldown}s"), ephemeral=True)
            return

        await interaction.response.defer()
        content = strip_mentions(message)
        if not content:
            await interaction.followup.send(embed=error_embed("Say something non-empty!"))
            return

        self.bot.stats["slash_chats"] = self.bot.stats.get("slash_chats", 0) + 1

        try:
            async with interaction.channel.typing():
                reply, doc_id = await self._generate_once(interaction.guild_id, interaction.channel.id, content)
        except Exception as exc:  # noqa: BLE001
            log.exception("chat failed")
            await interaction.followup.send(embed=error_embed(f"Couldn't respond: {exc}"))
            return

        person = self.bot.personalities.get_active(interaction.guild_id)
        embed = make_embed(
            title=f"As {person.name}",
            description=truncate(reply, 1950),
            color=CHAT,
            footer="React \U0001f44d / \U0001f44e / \U0001f440 to give feedback",
        )
        sent = await interaction.followup.send(embed=embed)
        if doc_id:
            self.bot.track_message(sent.id, doc_id, person.collection, interaction.guild_id, interaction.channel.id, content)

    @app_commands.command(name="forget", description="Clear the bot's memory of this channel's conversation")
    async def forget(self, interaction: discord.Interaction):
        self.bot.memory.clear(interaction.guild_id, interaction.channel.id)
        await interaction.response.send_message(embed=success_embed("Conversation history cleared for this channel"), ephemeral=True)

    # --------------------------------------------------------------- listeners
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        guild_id = message.guild.id
        channel_id = message.channel.id
        cfg = self.bot.config

        watched = cfg.get(guild_id, "monitored_channels", [])
        is_watched = channel_id in watched
        is_mention = self.bot.user in message.mentions
        respond_on_mention = cfg.get(guild_id, "respond_on_mention", True)
        auto_reply = cfg.get(guild_id, "auto_reply", True)

        # -- auto-train: swallow qualifying messages into the personality DB
        if is_watched and cfg.get(guild_id, "auto_train", False):
            user_filter = cfg.get(guild_id, "train_user_filter", 0)
            if not user_filter or message.author.id == user_filter:
                person = self.bot.personalities.get_active(guild_id)
                self.bot.db.add(
                    person.collection,
                    message.content,
                    {"source": "original", "quality": 1.0, "author": str(message.author), "timestamp": message.created_at.isoformat()},
                )

        do_reply = (is_watched and auto_reply) or (is_mention and respond_on_mention)
        if not do_reply:
            return

        clean = strip_mentions(message.content)
        if len(clean) < 1 and not is_mention:
            return

        cooldown = cfg.get(guild_id, "cooldown_seconds", 5)
        key = f"msg:{guild_id}:{message.author.id}"
        if not self._limiter.check(key, cooldown):
            return

        try:
            async with message.channel.typing():
                reply, doc_id = await self._generate_once(guild_id, channel_id, clean)
        except Exception as exc:  # noqa: BLE001
            log.warning("auto-reply failed: %s", exc)
            return

        reply = truncate(reply, 1950)
        try:
            sent = await message.channel.send(reply, reference=message, mention_author=False)
        except discord.HTTPException as exc:
            log.warning("send failed: %s", exc)
            sent = None

        self.bot.stats["auto_replies"] = self.bot.stats.get("auto_replies", 0) + 1

        if sent and doc_id:
            self.bot.track_message(sent.id, doc_id, self.bot.personalities.get_active(guild_id).collection, guild_id, channel_id, clean)

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        if payload.user_id == self.bot.user.id:
            return

        tracked = self.bot.message_doc_map.get(str(payload.message_id))
        if not tracked:
            return

        emoji = str(payload.emoji)
        doc_id = tracked.get("doc_id")
        collection = tracked.get("collection")

        if emoji in _THUMB_LIKE:
            self.bot.db.update_metadata(collection, doc_id, {
                "source": tracked.get("source", "generated"),
                "quality": _THUMB_LIKE[emoji],
            })
            log.info("feedback %s on %s", emoji, doc_id)

        elif emoji in _UNLIKE:
            self.bot.db.delete(collection, doc_id)
            self.bot.message_doc_map.remove(str(payload.message_id))
            log.info("deleted %s via %s", doc_id, emoji)

        elif emoji == _ARCHIVE_EMOJI:
            channel = self.bot.get_channel(payload.channel_id)
            if channel:
                msg = await channel.fetch_message(payload.message_id)
                self.bot.db.add(
                    ARCHIVE_COLLECTION,
                    msg.content or msg.embeds[0].description if msg.embeds else "(non-text message)",
                    {"author": str(msg.author), "channel": channel.name, "timestamp": msg.created_at.isoformat()},
                )

        elif emoji == _REGENERATE:
            query = tracked.get("query")
            guild_id = tracked.get("guild_id")
            channel_id = tracked.get("channel_id")
            if query and guild_id and channel_id:
                try:
                    reply, new_doc_id = await self._generate_once(guild_id, channel_id, query)
                except Exception as exc:  # noqa: BLE001
                    log.warning("regen failed: %s", exc)
                    return
                channel = self.bot.get_channel(channel_id)
                if channel:
                    sent = await channel.send(truncate(reply, 1950))
                    self.bot.message_doc_map.remove(str(payload.message_id))
                    if new_doc_id:
                        self.bot.track_message(sent.id, new_doc_id, self.bot.personalities.get_active(guild_id).collection, guild_id, channel_id, query)


async def setup(bot):
    await bot.add_cog(ChatCog(bot))