"""Help command: overview of all slash command groups."""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from utils.embeds import INFO, make_embed

SECTIONS = [
    ("Chat", [
        ("/chat <message>", "Talk to the bot; it replies as the active personality"),
        ("/forget", "Clear this channel's conversation memory"),
    ]),
    ("Personality", [
        ("/personality list", "List all personalities & message counts"),
        ("/personality add <name>", "Create a new empty personality"),
        ("/personality clone <name> <@member>", "New personality that mimics a member"),
        ("/personality switch <name>", "Set the active personality (admin)"),
        ("/personality info <name>", "Show personality details"),
        ("/personality remove <name>", "Delete a personality (admin)"),
    ]),
    ("Training", [
        ("/train import <@member>", "Pull a member's history into a collection"),
        ("/train watch #channel [@user]", "Continuously learn from a channel"),
        ("/train unwatch #channel", "Stop learning from a channel"),
        ("/train status", "Show watched channels & sizes"),
        ("/train prune", "Delete generated low-quality replies"),
    ]),
    ("Archive & lore", [
        ("/archive remember <text>", "Store something permanently"),
        ("/archive recall <query>", "Semantic search of the archive"),
        ("/archive recent", "Recently archived entries"),
        ("/incidents list", "List all lore/inside jokes"),
        ("/incidents add <name> <desc>", "Record a piece of lore"),
        ("/incidents search <text>", "Find relevant lore"),
    ]),
    ("Settings", [
        ("/config", "Show server config"),
        ("/config <key> <value>", "Change a setting (admin)"),
        ("/models", "List available Groq models"),
        ("/stats", "Bot usage statistics"),
    ]),
    ("Feedback", [
        ("\U0001f44d / \U0001f44e / \U0001f440", "Rate a generated reply (good / bad / meh)"),
        ("\U0001f4cc", "Archive a reply"),
        ("\U0001f504", "Regenerate the reply"),
    ]),
]


class HelpCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="help", description="Show all commands and how to use the bot")
    async def help(self, interaction: discord.Interaction):
        lines = []
        for section, cmds in SECTIONS:
            lines.append(f"**{section}**")
            for cmd, desc in cmds:
                lines.append(f"`{cmd}` - {desc}")
            lines.append("")
        embed = make_embed(
            title="ManuBot - commands",
            description="\n".join(lines),
            color=INFO,
            footer="Admin commands: personality switch/add/remove, train import/watch, config set",
        )
        await interaction.response.send_message(embed=embed)


async def setup(bot):
    await bot.add_cog(HelpCog(bot))