"""Async Discord message scraper for building a mimic dataset."""

from __future__ import annotations

import logging
from typing import AsyncIterator, Callable, Dict, List, Optional

import discord

log = logging.getLogger("manubot.scraper")


async def iterate_user_messages(
    client: discord.Client,
    guild_id: int,
    target_user_id: int,
    channels: Optional[List[discord.TextChannel]] = None,
    progress_cb: Optional[Callable[[str], None]] = None,
) -> AsyncIterator[Dict]:
    """Yield dicts of the target user's messages across chosen channels.

    Yields {"id","channel","content","timestamp","reply_to"} so callers can
    stream them into the database or a progress UI.
    """
    if progress_cb is None:
        progress_cb = lambda text: None  # noqa: E731

    guild = client.get_guild(guild_id)
    if guild is None:
        log.error("Guild %s not found", guild_id)
        return

    targets = channels or [c for c in guild.text_channels if c.permissions_for(guild.me).read_message_history]

    for channel in targets:
        if not channel.permissions_for(guild.me).read_message_history:
            progress_cb(f"Skpping #{channel.name} (no read-history permission)")
            continue
        progress_cb(f"Scanning #{channel.name}...")
        count = 0
        try:
            async for message in channel.history(limit=None, oldest_first=True):
                if message.author.id == target_user_id and message.content and message.content.strip():
                    yield {
                        "id": str(message.id),
                        "channel": channel.name,
                        "content": message.content,
                        "timestamp": message.created_at.isoformat(),
                        "reply_to": message.reference.message_id if message.reference else None,
                    }
                    count += 1
        except discord.Forbidden:
            progress_cb(f"No access to #{channel.name}, skipping")
            continue
        except Exception as exc:  # noqa: BLE001
            log.warning("Error in #%s: %s", channel.name, exc)
            progress_cb(f"Error in #{channel.name}: {exc}")
            continue
        progress_cb(f"{count} messages from #{channel.name}")