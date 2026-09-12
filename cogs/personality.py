"""Personality management: list, add, switch, remove personalities."""

from __future__ import annotations

import logging

import discord
from discord import app_commands

from utils.checks import admin_only
from utils.embeds import (Paginator, SUCCESS, TRAIN, error_embed, info_embed, make_embed, success_embed)

log = logging.getLogger("manubot.personality")


@app_commands.guild_only()
class PersonalityGroup(app_commands.Group):
    def __init__(self, bot, **kwargs):
        super().__init__(name="personality", description="Manage the personalities the bot imitates", **kwargs)
        self.bot = bot

    @app_commands.command(name="list", description="List all personalities and their message counts")
    async def list_personalities(self, interaction: discord.Interaction):
        persons = self.bot.personalities.list()
        if not persons:
            await interaction.response.send_message(embed=info_embed("No personalities yet."), ephemeral=True)
            return

        active = self.bot.personalities.get_active(interaction.guild_id)

        async def load_all():
            active_collection = active.collection
            yield "**Personalities:**"
            for p in persons:
                marker = " (active)" if p.name == active.name else ""
                count = self.bot.db.count(p.collection)
                target = f"<@{p.target_user_id}>" if p.target_user_id else "anyone"
                desc = f" - {p.description[:60]}" if p.description else ""
                yield f"- `{p.name}`{marker}: {count:,} messages, target {target}{desc}"
            yield f"\nActive collection: `{active_collection}`"

        items = []
        async for line in load_all():
            items.append(line)

        view = Paginator("Personalities", items, color=TRAIN, author="ManuBot")
        await interaction.response.send_message(embed=view._embed(), view=view)

    @app_commands.command(name="info", description="Show details about a personality")
    @app_commands.describe(name="Personality name")
    async def info(self, interaction: discord.Interaction, name: str):
        person = self.bot.personalities.get(name)
        if not person:
            await interaction.response.send_message(embed=error_embed(f"Unknown personality `{name}`"), ephemeral=True)
            return
        count = self.bot.db.count(person.collection)
        embed = make_embed(
            title=f"Personality: {person.name}",
            color=TRAIN,
            fields=[
                ("Collection", f"`{person.collection}`", True),
                ("Messages stored", f"{count:,}", True),
                ("Target user", f"<@{person.target_user_id}>" if person.target_user_id else "anyone", True),
                ("Created", person.created_at[:19] or "unknown", True),
                ("Description", person.description or "_none_", False),
            ],
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="add", description="Create a new personality (empty, then train it)")
    @app_commands.describe(
        name="Unique name for the personality",
        description="Short description of who this person is",
    )
    @admin_only()
    async def add(self, interaction: discord.Interaction, name: str, description: str = ""):
        name = name.strip().lower().replace(" ", "_")
        if not name or len(name) > 32:
            await interaction.response.send_message(embed=error_embed("Name must be 1-32 chars"), ephemeral=True)
            return
        if self.bot.personalities.get(name):
            await interaction.response.send_message(embed=error_embed(f"`{name}` already exists"), ephemeral=True)
            return

        collection = f"pers_{name}"
        person = self.bot.personalities.add(
            name=name,
            collection=collection,
            description=description,
            guild_id=interaction.guild_id,
        )
        existing = self.bot.db.count(collection)
        embed = success_embed(
            f"Created personality `{name}` with collection `{collection}`.\n"
            f"Now use `/train import` or `/train watch` to feed it messages.",
            title="Personality created",
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="switch", description="Set the active personality for this server")
    @app_commands.describe(name="Personality name to activate")
    @admin_only()
    async def switch(self, interaction: discord.Interaction, name: str):
        if not self.bot.personalities.set_active(interaction.guild_id, name):
            await interaction.response.send_message(embed=error_embed(f"Unknown personality `{name}`"), ephemeral=True)
            return
        embed = success_embed(f"Active personality is now `{name}`", title="Switched")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="remove", description="Delete a personality and its message collection (default can't be removed)")
    @app_commands.describe(name="Personality name to remove")
    @admin_only()
    async def remove(self, interaction: discord.Interaction, name: str):
        person = self.bot.personalities.get(name)
        if not person:
            await interaction.response.send_message(embed=error_embed(f"Unknown personality `{name}`"), ephemeral=True)
            return
        if self.bot.personalities.remove(name):
            self.bot.db.drop_collection(person.collection)
            await interaction.response.send_message(embed=success_embed(f"Removed `{name}` and its collection `{person.collection}`", title="Removed"))
        else:
            await interaction.response.send_message(embed=error_embed("The default personality can't be removed"), ephemeral=True)

    @app_commands.command(name="clone", description="Create a personality that mimics a specific member")
    @app_commands.describe(
        name="Name for the new personality",
        member="The member to mimic",
    )
    @admin_only()
    async def clone(self, interaction: discord.Interaction, name: str, member: discord.Member):
        name = name.strip().lower().replace(" ", "_")
        if not name or len(name) > 32:
            await interaction.response.send_message(embed=error_embed("Name must be 1-32 chars"), ephemeral=True)
            return
        if self.bot.personalities.get(name):
            await interaction.response.send_message(embed=error_embed(f"`{name}` already exists"), ephemeral=True)
            return

        collection = f"pers_{name}"
        self.bot.personalities.add(
            name=name,
            collection=collection,
            description=f"Mimics {member.display_name}",
            target_user_id=member.id,
            guild_id=interaction.guild_id,
        )
        embed = success_embed(
            f"Created personality `{name}` targeting <@{member.id}>.\n"
            f"Run `/train import` targeting this personality to pull their message history.",
            title="Personality created",
        )
        await interaction.response.send_message(embed=embed)


async def setup(bot):
    bot.tree.add_command(PersonalityGroup(bot))