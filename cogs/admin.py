"""Owner-only administration commands (`/admin`)."""

from __future__ import annotations

import logging

import discord
from discord import app_commands

from utils.checks import owner_only
from utils.embeds import (SUCCESS, error_embed, info_embed, make_embed, success_embed)

log = logging.getLogger("manubot.admin")


@app_commands.guild_only()
class AdminGroup(app_commands.Group):
    def __init__(self, bot, **kwargs):
        super().__init__(name="admin", description="Owner-only maintenance commands", **kwargs)
        self.bot = bot

    @app_commands.command(name="cleanup", description="Remove generated low-quality replies from a collection")
    @app_commands.describe(personality="Optional personality name (defaults to active)")
    @owner_only()
    async def cleanup(self, interaction: discord.Interaction, personality: str = ""):
        if personality:
            person = self.bot.personalities.get(personality)
            if not person:
                await interaction.response.send_message(embed=error_embed(f"Unknown personality `{personality}`"), ephemeral=True)
                return
            collection = person.collection
        else:
            collection = self.bot.personalities.get_active(interaction.guild_id).collection

        await interaction.response.defer()
        bad = self.bot.db.get_where(collection, {"source": "generated"}, limit=10000)
        ids = bad.get("ids", [])
        if not ids:
            await interaction.followup.send(embed=info_embed(f"`{collection}` has nothing generated"))
            return
        deleted = self.bot.db.delete_where(collection, {"source": "generated"})
        await interaction.followup.send(embed=success_embed(
            f"Deleted **{deleted:,}** generated messages from `{collection}`.", title="Cleanup done"
        ))

    @app_commands.command(name="drop-collection", description="Delete a ChromaDB collection entirely")
    @app_commands.describe(collection="Collection name (must not be in use by a personality)")
    @owner_only()
    async def drop_collection(self, interaction: discord.Interaction, collection: str):
        if self.bot.db.has_collection(collection):
            used = {p.collection for p in self.bot.personalities.list()}
            if collection in used:
                await interaction.response.send_message(embed=error_embed("That collection is used by a personality - delete the personality instead"), ephemeral=True)
                return
            self.bot.db.drop_collection(collection)
            await interaction.response.send_message(embed=success_embed(f"Dropped collection `{collection}`"))
        else:
            await interaction.response.send_message(embed=info_embed(f"No collection named `{collection}`"))

    @app_commands.command(name="collections", description="List all ChromaDB collections")
    @owner_only()
    async def collections(self, interaction: discord.Interaction):
        rows = []
        for name in self.bot.db.list_collections():
            rows.append(f"- `{name}`: {self.bot.db.count(name):,} docs")
        await interaction.response.send_message(embed=make_embed(
            title="Collections", description="\n".join(rows) or "_empty_", color=SUCCESS
        ))

    @app_commands.command(name="reload", description="Reload config and personality registry from disk")
    @owner_only()
    async def reload(self, interaction: discord.Interaction):
        self.bot.config = type(self.bot.config)("server_configs.json")
        self.bot.personalities = type(self.bot.personalities)(self.bot.config)
        self.bot.lore = type(self.bot.lore)("incidents.json")
        self.bot.message_doc_map = type(self.bot.message_doc_map)("message_doc_map.json")
        await interaction.response.send_message(embed=success_embed("Config, personalities & lore reloaded"))

    @app_commands.command(name="purge-archive", description="Purge generated archive entries or all of them")
    @app_commands.describe(all="Pass True to wipe the entire archive (default: generated only)")
    @owner_only()
    async def purge_archive(self, interaction: discord.Interaction, all: bool = False):
        await interaction.response.defer()
        if all:
            deleted = self.bot.db.delete_where("server_archive", {"source": "generated"})
            remaining = self.bot.db.count("server_archive")
            await interaction.followup.send(embed=info_embed(
                f"Removed {deleted:,} generated archive entries. {remaining:,} remain."
            ))
        else:
            deleted = self.bot.db.delete_where("server_archive", {"source": "generated"})
            await interaction.followup.send(embed=success_embed(f"Deleted {deleted:,} generated archive entries"))


async def setup(bot):
    bot.tree.add_command(AdminGroup(bot))