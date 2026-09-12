"""Per-guild / per-channel conversation memory with atomic JSON persistence."""

from __future__ import annotations

import logging
import threading
from typing import Dict, List

from core.config import JsonStore

log = logging.getLogger("manubot.memory")


class ConversationMemory:
    """Stores {guild_id: {channel_id: [{role, content}, ...]}} in a JSON file."""

    def __init__(self, path: str = "conversation_history.json"):
        self._store = JsonStore(path)
        self._lock = threading.RLock()

    def _guild_map(self, guild_id: int) -> Dict[str, list]:
        gid = str(guild_id)
        guild = self._store.get(gid, {})
        if not isinstance(guild, dict):
            guild = {}
            self._store.set(gid, guild)
        return guild

    def push(self, guild_id: int, channel_id: int, role: str, content: str, max_len: int = 12) -> None:
        with self._lock:
            gid, cid = str(guild_id), str(channel_id)
            guild = self._guild_map(guild_id)
            history = guild.get(cid) or []
            history.append({"role": role, "content": content})
            guild[cid] = history[-max_len * 2:] if max_len else history
            self._store.set(gid, guild)

    def get(self, guild_id: int, channel_id: int, max_len: int = 12) -> List[dict]:
        with self._lock:
            guild = self._guild_map(guild_id)
            history = guild.get(str(channel_id)) or []
            return history[-max_len * 2:] if max_len else history[:]

    def clear(self, guild_id: int, channel_id: int) -> None:
        with self._lock:
            guild = self._guild_map(guild_id)
            guild.pop(str(channel_id), None)
            self._store.set(str(guild_id), guild)

    def clear_guild(self, guild_id: int) -> None:
        with self._lock:
            self._store.set(str(guild_id), {})

    def total_entries(self) -> int:
        count = 0
        for key, value in self._store.data().items():
            if isinstance(value, dict):
                for history in value.values():
                    if isinstance(history, list):
                        count += len(history)
        return count