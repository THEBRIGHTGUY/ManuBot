"""Permission guards and rate limiting helpers for slash commands."""

from __future__ import annotations

import os
import time
from typing import Set

import discord

OWNER_IDS = {int(x) for x in os.getenv("OWNER_IDS", "0").split(",") if x.strip().lstrip("-").isdigit()}


def is_owner(interaction: discord.Interaction, bot) -> bool:
    if interaction.user.id in OWNER_IDS:
        return True
    if bot.owner_id and interaction.user.id == bot.owner_id:
        return True
    return False


def is_owner_admin(interaction: discord.Interaction, bot) -> bool:
    if is_owner(interaction, bot):
        return True
    if isinstance(interaction.user, discord.Member):
        return interaction.user.guild_permissions.administrator or interaction.user.guild_permissions.manage_guild
    return False


class RateLimiter:
    def __init__(self):
        self._hits: dict = {}

    def check(self, key: str, cooldown: float) -> bool:
        now = time.monotonic()
        last = self._hits.get(key)
        if last is None or now - last > cooldown:
            self._hits[key] = now
            return True
        return False


_global_limiter = RateLimiter()


def rate_limit(key: str, seconds: float) -> bool:
    """Non-decorator limiter used inside commands: returns True if allowed."""
    return _global_limiter.check(key, seconds)


def owner_only():
    """Decorator for owner-only commands via app_commands.check."""

    def predicate(interaction: discord.Interaction) -> bool:
        return is_owner(interaction, interaction.client)

    from discord.app_commands import check
    return check(predicate)


def admin_only():
    """Decorator for admin/owner commands via app_commands.check."""

    def predicate(interaction: discord.Interaction) -> bool:
        return is_owner_admin(interaction, interaction.client)

    from discord.app_commands import check
    return check(predicate)