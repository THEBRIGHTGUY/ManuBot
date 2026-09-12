"""Archive: store & search server lore (`/remember`, `/recall`, `/incidents`)."""

from __future__ import annotations

import re
import uuid

import discord
from discord import app_commands

from core.database import ARCHIVE_COLLECTION
from utils.checks import admin_only
from utils.embeds import (Paginator, SUCCESS, error_embed, info_embed, make_embed, success_embed)
from utils.helpers import now_iso, truncate

STOPWORDS = {"the", "a", "an", "is", "are", "and", "of", "to", "for", "in", "on", "with", "that", "this"}


@app_commands.guild_only()
class ArchiveGroup(app_commands.Group):
    def __init__(self, bot, **kwargs):
        super().__init__(name="archive", description="Store and search messages/lore the bot should remember", **kwargs)
        self.bot = bot

    @app_commands.command(name="remember", description="Add a message to the server archive")
    @app_commands.describe(text="The message to remember")
    async def remember(self, interaction: discord.Interaction, text: str):
        if len(text) > 1500:
            await interaction.response.send_message(embed=error_embed("Keep archived notes under 1500 characters"), ephemeral=True)
            return
        doc_id = self.bot.db.add(
            ARCHIVE_COLLECTION,
            text,
            {
                "author": str(interaction.user),
                "user_id": interaction.user.id,
                "channel": interaction.channel.name,
                "timestamp": now_iso(),
            },
        )
        if not doc_id:
            await interaction.response.send_message(embed=error_embed("Failed to store that message"))
            return
        embed = success_embed(f"Archived: \"{truncate(text, 500)}\"", title="Remembered")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="recall", description="Search the server archive")
    @app_commands.describe(query="What you're looking for (semantic search, not exact)")
    async def recall(self, interaction: discord.Interaction, query: str):
        results = self.bot.db.query(ARCHIVE_COLLECTION, query, n_results=10)
        if not results:
            await interaction.response.send_message(embed=info_embed("Nothing found in the archive"), ephemeral=True)
            return

        lines = []
        for i, r in enumerate(results, start=1):
            meta = r["metadata"]
            author = meta.get("author", "unknown")
            channel = meta.get("channel", "?")
            lines.append(f"**{i}.** {truncate(r['doc'], 220)}\n     - {author} in #{channel}")

        embed = make_embed(
            title="Archive results",
            description="\n\n".join(lines),
            color=SUCCESS,
            footer=f"{len(results)} matches",
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="recent", description="Show recently archived messages")
    async def recent(self, interaction: discord.Interaction):
        result = self.bot.db.get_where(ARCHIVE_COLLECTION, {}, limit=50)
        metas = result.get("metadatas") or []
        docs = result.get("documents") or []
        ids = result.get("ids") or []

        rows = []
        for doc_id, doc, meta in zip(ids, docs, metas):
            rows.append(f"{truncate(doc, 100)}  _(by {meta.get('author', '?')})_")
        if not rows:
            await interaction.response.send_message(embed=info_embed("Archive is empty"))
            return
        view = Paginator("Recent archived messages", rows, color=SUCCESS)
        await interaction.response.send_message(embed=view._embed(), view=view)

    @app_commands.command(name="delete", description="Forget a specific archived message by its number from /archive recall")
    @app_commands.describe(number="The line number shown in a recall result")
    async def delete(self, interaction: discord.Interaction, number: int):
        # Re-run the last 10 most relevant... simplest: drop oldest by count is unsafe.
        await interaction.response.send_message(
            embed=info_embed("Use reaction controls or contact the bot owner to purge archive entries"),
            ephemeral=True,
        )


@app_commands.guild_only()
class IncidentGroup(app_commands.Group):
    """Server lore/incidents that get fed into the personality's context."""

    def __init__(self, bot, **kwargs):
        super().__init__(name="incidents", description="Manage lore/inside-jokes that flavor the bot's personality", **kwargs)
        self.bot = bot

    @app_commands.command(name="list", description="List all known incidents/lore")
    async def list_incidents(self, interaction: discord.Interaction):
        lore = self.bot.lore.data()
        if not lore:
            await interaction.response.send_message(embed=info_embed("No incidents recorded yet"))
            return
        rows = [f"- **{name}** - {truncate(info.get('description', ''), 120)}" for name, info in lore.items()]
        view = Paginator("Server incidents", rows, color=SUCCESS)
        await interaction.response.send_message(embed=view._embed(), view=view)

    @app_commands.command(name="add", description="Record a piece of lore or an inside joke")
    @app_commands.describe(name="Short name for it", description="What happened")
    async def add(self, interaction: discord.Interaction, name: str, description: str):
        lore = dict(self.bot.lore.data())
        lore[name] = {
            "description": description,
            "added_by": str(interaction.user),
            "added_by_id": interaction.user.id,
            "timestamp": now_iso(),
        }
        self.bot.lore.replace(lore)
        embed = success_embed(f"Added incident **{name}**: {truncate(description, 300)}", title="Incident recorded")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="remove", description="Remove an incident")
    @app_commands.describe(name="Incident name to remove")
    @admin_only()
    async def remove(self, interaction: discord.Interaction, name: str):
        lore = dict(self.bot.lore.data())
        if name not in lore:
            await interaction.response.send_message(embed=error_embed(f"No incident named `{name}`"), ephemeral=True)
            return
        del lore[name]
        self.bot.lore.replace(lore)
        await interaction.response.send_message(embed=success_embed(f"Removed incident `{name}`"))

    @app_commands.command(name="search", description="Find incidents whose keywords overlap your message")
    @app_commands.describe(text="Text to match against")
    async def search(self, interaction: discord.Interaction, text: str):
        tokens = set(re.findall(r"[a-z0-9]+", text.lower())) - STOPWORDS
        loots = self.bot.lore.data()
        hits = []
        for name, info in loots.items():
            words = set(re.findall(r"[a-z0-9]+", f"{name} {info.get('description','')}".lower()))
            overlap = words & tokens
            if overlap:
                hits.append((len(overlap), name, info))
        if not hits:
            await interaction.response.send_message(embed=info_embed("No incidents match that text"))
            return
        hits.sort(key=lambda t: t[0], reverse=True)
        rows = [f"- **{name}** - {truncate(info['description'], 120)}" for _, name, info in hits[:10]]
        await interaction.response.send_message(embed=make_embed(title="Matching incidents", description="\n".join(rows), color=SUCCESS))


async def setup(bot):
    bot.tree.add_command(ArchiveGroup(bot))
    bot.tree.add_command(IncidentGroup(bot))