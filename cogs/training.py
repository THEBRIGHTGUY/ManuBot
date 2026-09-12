"""Training: one-shot import of a member's history, and continuous channel watching."""

from __future__ import annotations

import logging
from typing import List, Optional

import discord
from discord import app_commands

from training.embedder import embed_messages
from training.scraper import iterate_user_messages
from utils.checks import admin_only
from utils.embeds import (Paginator, TRAIN, error_embed, info_embed, make_embed, success_embed)
from utils.helpers import uniq

log = logging.getLogger("manubot.training")


@app_commands.guild_only()
class TrainGroup(app_commands.Group):
    def __init__(self, bot, **kwargs):
        super().__init__(name="train", description="Train the bot on real Discord messages", **kwargs)
        self.bot = bot

    def _pick_collection(self, guild_id: int, personality: Optional[str]) -> str:
        if personality:
            person = self.bot.personalities.get(personality)
            if person:
                return person.collection
            raise ValueError(f"Unknown personality `{personality}`")
        return self.bot.personalities.get_active(guild_id).collection

    # ------------------------------------------------------------- commands
    @app_commands.command(name="import", description="One-shot: pull a member's message history into a personality")
    @app_commands.describe(
        member="The member whose messages should be imported",
        channels="Optional channels (IDs, comma separated). Defaults to all readable text channels",
        personality="Optional personality to import into (defaults to active)",
    )
    @admin_only()
    async def import_history(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        channels: str = "",
        personality: Optional[str] = None,
    ):
        if member.bot:
            await interaction.response.send_message(embed=error_embed("Can't copy a bot's messages"), ephemeral=True)
            return

        try:
            collection = self._pick_collection(interaction.guild_id, personality)
        except ValueError as exc:
            await interaction.response.send_message(embed=error_embed(str(exc)), ephemeral=True)
            return

        await interaction.response.defer()

        channel_objs: Optional[List[discord.TextChannel]] = None
        if channels:
            ids = [int(x) for x in channels.replace(",", " ").split() if x.strip().isdigit()]
            channel_objs = [c for c in interaction.guild.text_channels if c.id in ids]

        progress = []
        stage = await interaction.followup.send(embed=info_embed("Starting import..."))

        async def render():
            await stage.edit(embed=make_embed(
                title="Importing messages",
                description="\n".join(progress[-8:]) or "_working..._",
                color=TRAIN,
                footer=f"Target: {member.display_name} -> collection `{collection}`",
            ))

        def progress_cb(text: str):
            progress.append(text)

        messages = []
        async for msg in iterate_user_messages(
            self.bot, interaction.guild_id, member.id, channel_objs, progress_cb=progress_cb
        ):
            messages.append(msg)
            if len(messages) % 100 == 0:
                progress_cb(f"Scraping... {len(messages)} found so far")
                self.bot.loop.create_task(render())

        progress_cb(f"Found {len(messages)} messages total. Embedding...")
        await render()

        added = await self.bot.loop.run_in_executor(
            None, embed_messages, self.bot.db, collection, messages, "original", 1.0, 500, progress_cb
        )
        await render()

        active = self.bot.personalities.get_active(interaction.guild_id)
        if collection == active.collection and added:
            data = self.bot.config.personalities()
            for pname, pdata in data.items():
                if pdata.get("collection") == collection:
                    old = int(pdata.get("message_count") or 0)
                    pdata["message_count"] = old + added
                    self.bot.config.add_personality(pname, pdata)

        total = self.bot.db.count(collection)
        embed = success_embed(
            f"Imported {added:,} messages from <@{member.id}> into `{collection}`.\n"
            f"Collection now has **{total:,}** messages.",
            title="Import complete",
        )
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="watch", description="Continuously learn from a channel into the active personality")
    @app_commands.describe(
        channel="Channel to watch for training",
        user="Optional: only learn from this user's messages (default: everyone)",
    )
    @admin_only()
    async def watch(self, interaction: discord.Interaction, channel: discord.TextChannel, user: Optional[discord.User] = None):
        cfg = self.bot.config
        watched = cfg.get(interaction.guild_id, "monitored_channels", [])
        if channel.id not in watched:
            watched = uniq(watched + [channel.id])
            cfg.set(interaction.guild_id, "monitored_channels", watched)
            cfg.set(interaction.guild_id, "auto_train", True)
        if user:
            cfg.set(interaction.guild_id, "train_user_filter", user.id)
        embed = success_embed(
            f"Watching {channel.mention} for training{(' (user: ' + user.mention + ')') if user else ''}.\n"
            "Messages here will be embedded into the active personality. "
            "Disable with `/train unwatch`.",
            title="Channel watched",
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="unwatch", description="Stop learning from a channel")
    @app_commands.describe(channel="Channel to stop watching")
    @admin_only()
    async def unwatch(self, interaction: discord.Interaction, channel: discord.TextChannel):
        cfg = self.bot.config
        watched = [c for c in cfg.get(interaction.guild_id, "monitored_channels", []) if c != channel.id]
        cfg.set(interaction.guild_id, "monitored_channels", watched)
        if not watched:
            cfg.set(interaction.guild_id, "auto_train", False)
        await interaction.response.send_message(embed=success_embed(f"Stopped watching {channel.mention}", title="Unwatched"))

    @app_commands.command(name="status", description="Show what the bot is watching and its data sizes")
    async def status(self, interaction: discord.Interaction):
        cfg = self.bot.config
        watched = cfg.get(interaction.guild_id, "monitored_channels", [])
        auto_train = cfg.get(interaction.guild_id, "auto_train", False)
        auto_reply = cfg.get(interaction.guild_id, "auto_reply", True)
        ufilter = cfg.get(interaction.guild_id, "train_user_filter", 0)

        lines = [f"Auto-train: **{'on' if auto_train else 'off'}**", f"Auto-reply: **{'on' if auto_reply else 'off'}**"]
        if ufilter:
            lines.append(f"Only learning from: <@{ufilter}>")
        if watched:
            names = []
            for cid in watched:
                ch = self.bot.get_channel(cid)
                names.append(f"- {ch.mention if ch else '#' + str(cid)}")
            lines.append("**Watched channels:**\n" + "\n".join(names))
        else:
            lines.append("No watched channels.")

        lines.append("")
        for p in self.bot.personalities.list()[:6]:
            lines.append(f"- `{p.name}`: {self.bot.db.count(p.collection):,} messages")

        embed = make_embed(title="Training status", description="\n".join(lines), color=TRAIN)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="prune", description="Delete the bot's own low-quality generated replies from the active personality")
    @admin_only()
    async def prune(self, interaction: discord.Interaction):
        collection = self.bot.personalities.get_active(interaction.guild_id).collection
        await interaction.response.defer()
        result = self.bot.db.get_where(collection, {"source": "generated"}, limit=10000)
        ids = result.get("ids", [])
        if not ids:
            await interaction.followup.send(embed=info_embed("Nothing generated to prune."))
            return
        deleted = self.bot.db.delete_where(collection, {"source": "generated"})
        embed = success_embed(f"Deleted **{deleted:,}** generated messages from `{collection}`.", title="Pruned")
        await interaction.followup.send(embed=embed)


async def setup(bot):
    bot.tree.add_command(TrainGroup(bot))