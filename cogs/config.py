"""Per-server configuration commands (`/config`)."""

from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from core.config import DEFAULT_CONFIG
from utils.checks import admin_only
from utils.embeds import (SUCCESS, error_embed, info_embed, make_embed, success_embed)

log = logging.getLogger("manubot.config")

# key -> (label, value parser, friendly min/max hint, choices)
CONFIG_KEYS = {
    "model": {
        "label": "LLM model",
        "kind": "str",
        "hint": "A Groq model id (see /config models). E.g. qwen/qwen3.8-27b",
    },
    "temperature": {
        "label": "Temperature",
        "kind": "float",
        "hint": "0.0 (precise) - 2.0 (chaotic)",
        "min": 0.0,
        "max": 2.0,
    },
    "max_tokens": {
        "label": "Max response tokens",
        "kind": "int",
        "hint": "50 - 2000",
        "min": 50,
        "max": 2000,
    },
    "auto_reply": {
        "label": "Auto-reply in watched channels",
        "kind": "bool",
    },
    "auto_train": {
        "label": "Learn from watched channels",
        "kind": "bool",
    },
    "respond_on_mention": {
        "label": "Reply when mentioned",
        "kind": "bool",
    },
    "cooldown_seconds": {
        "label": "Per-user reply cooldown (s)",
        "kind": "int",
        "hint": "0 - 3600",
        "min": 0,
        "max": 3600,
    },
    "history_length": {
        "label": "Conversation memory length",
        "kind": "int",
        "hint": "2 - 40",
        "min": 2,
        "max": 40,
    },
    "min_response_length": {
        "label": "Min reply length kept for training",
        "kind": "int",
        "hint": "1 - 100",
        "min": 1,
        "max": 100,
    },
}


class ConfigCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def _parse(self, key: str, raw: str):
        spec = CONFIG_KEYS.get(key)
        if not spec:
            raise ValueError("unknown key")
        if spec["kind"] == "bool":
            v = raw.strip().lower()
            if v in ("1", "true", "on", "yes", "y"):
                return True
            if v in ("0", "false", "off", "no", "n"):
                return False
            raise ValueError("expected true/false")
        if spec["kind"] == "int":
            v = int(raw)
            if "min" in spec and v < spec["min"]:
                raise ValueError(f"must be >= {spec['min']}")
            if "max" in spec and v > spec["max"]:
                raise ValueError(f"must be <= {spec['max']}")
            return v
        if spec["kind"] == "float":
            v = float(raw)
            if "min" in spec and v < spec["min"]:
                raise ValueError(f"must be >= {spec['min']}")
            if "max" in spec and v > spec["max"]:
                raise ValueError(f"must be <= {spec['max']}")
            return v
        return raw.strip()

    @app_commands.command(name="config", description="Show or change this server's bot settings")
    @app_commands.describe(
        key="Setting to change (e.g. temperature, model, auto_reply, max_tokens)",
        value="New value",
    )
    async def config(self, interaction: discord.Interaction, key: str = "", value: str = ""):
        if not key:
            await self._show(interaction)
            return

        # changing settings requires admin rights
        if not interaction.user.guild_permissions.administrator and not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message(embed=error_embed("You need Manage Server perms to change settings"), ephemeral=True)
            return

        key = key.strip().lower()
        if key not in CONFIG_KEYS:
            await interaction.response.send_message(embed=error_embed(
                f"Unknown setting `{key}`.\nValid: {', '.join(CONFIG_KEYS)}"
            ), ephemeral=True)
            return

        if not value:
            current = self.bot.config.get(interaction.guild_id, key)
            spec = CONFIG_KEYS[key]
            await interaction.response.send_message(embed=info_embed(
                f"**{spec['label']}** = `{current}`\n{spec.get('hint', '')}"
            ), ephemeral=True)
            return

        try:
            parsed = self._parse(key, value)
        except ValueError as exc:
            await interaction.response.send_message(embed=error_embed(f"Invalid value: {exc}"), ephemeral=True)
            return

        self.bot.config.set(interaction.guild_id, key, parsed)
        await interaction.response.send_message(embed=success_embed(
            f"**{CONFIG_KEYS[key]['label']}** set to `{parsed}`", title="Config updated"
        ))

    async def _show(self, interaction: discord.Interaction):
        rows = []
        for key, spec in CONFIG_KEYS.items():
            current = self.bot.config.get(interaction.guild_id, key)
            rows.append(f"- **{spec['label']}** (`{key}`): `{current}`")
        active = self.bot.personalities.get_active(interaction.guild_id)
        rows.append(f"- **Active personality**: `{active.name}`")
        embed = make_embed(
            title="Server configuration",
            description="\n".join(rows),
            color=SUCCESS,
            footer="Change with /config <key> <value> (admin only)",
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="models", description="List models available on Groq")
    async def models(self, interaction: discord.Interaction):
        ids = self.bot.llm.list_models()
        lines = "\n".join(f"- `{m}`" for m in ids)
        embed = make_embed(title="Available Groq models", description=lines or "_can't fetch_", color=SUCCESS)
        if len(embed.description) > 4000:
            embed = make_embed(title="Available Groq models", description=lines[:3800] + "\n...", color=SUCCESS)
        await interaction.response.send_message(embed=embed)


async def setup(bot):
    await bot.add_cog(ConfigCog(bot))