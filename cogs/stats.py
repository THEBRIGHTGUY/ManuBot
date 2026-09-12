"""Statistics: `/stats` dashboard with usage info."""

from __future__ import annotations

import time

import discord
from discord import app_commands
from discord.ext import commands

from core.prompt import format_lore
from utils.embeds import INFO, make_embed
from utils.helpers import format_duration


class StatsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="stats", description="Show bot usage statistics")
    async def stats(self, interaction: discord.Interaction):
        guild_id = interaction.guild_id
        db = self.bot.db
        cfg = self.bot.config

        lines = []

        # knowledge
        total = 0
        person_lines = []
        for p in self.bot.personalities.list():
            c = db.count(p.collection)
            total += c
            person_lines.append(f"  - `{p.name}`: {c:,}")
        lines.append(f"**Knowledge base** ({total:,} total messages)\n" + "\n".join(person_lines))

        # archive + lore
        archive = db.count("server_archive")
        lore = len(self.bot.lore.data())
        lines.append(f"**Memory**\n  - Archive entries: {archive:,}\n  - Incidents/lore: {lore}")

        # usage
        uptime = time.time() - self.bot.uptime
        auto = self.bot.stats.get("auto_replies", 0)
        chats = self.bot.stats.get("slash_chats", 0)
        tracks = len(self.bot.message_doc_map.data())
        lines.append(
            f"**Activity**\n"
            f"  - Uptime: {format_duration(uptime)}\n"
            f"  - Auto-replies sent: {auto:,}\n"
            f"  - /chat calls: {chats:,}\n"
            f"  - Tracked feedback messages: {tracks:,}"
        )

        # conversation memory
        mem = self.bot.memory.total_entries()
        lines.append(f"  - Conversation episodes in memory: {mem:,}")

        # model
        lines.append(
            f"**Model**\n"
            f"  - Model: `{cfg.get(guild_id, 'model')}`\n"
            f"  - Temperature: `{cfg.get(guild_id, 'temperature')}`\n"
            f"  - Active personality: `{self.bot.personalities.get_active(guild_id).name}`"
        )

        embed = make_embed(
            title="ManuBot statistics",
            description="\n\n".join(lines),
            color=INFO,
            footer=f"Requested by {interaction.user.display_name}",
        )
        await interaction.response.send_message(embed=embed)


async def setup(bot):
    await bot.add_cog(StatsCog(bot))