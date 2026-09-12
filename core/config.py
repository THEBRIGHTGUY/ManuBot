"""Thread-safe JSON persistence + per-guild bot configuration."""

from __future__ import annotations

import json
import os
import threading
from typing import Any, Dict, Optional

DEFAULT_CONFIG = {
    "active_personality": "default",
    "model": "qwen/qwen3.8-27b",
    "temperature": 0.9,
    "max_tokens": 900,
    "auto_reply": True,
    "auto_train": False,
    "respond_on_mention": True,
    "monitored_channels": [],
    "train_user_filter": 0,
    "log_channel": 0,
    "history_length": 12,
    "cooldown_seconds": 5,
    "min_response_length": 3,
}


class JsonStore:
    """Small atomic, thread-safe JSON file store."""

    def __init__(self, path: str):
        self.path = path
        self._lock = threading.RLock()
        self._data: Dict[str, Any] = self._load()

    def _load(self) -> Dict[str, Any]:
        if not os.path.exists(self.path):
            return {}
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
                return loaded if isinstance(loaded, dict) else {}
        except (json.JSONDecodeError, OSError, UnicodeDecodeError):
            return {}

    def save(self) -> None:
        with self._lock:
            tmp = f"{self.path}.tmp"
            try:
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump(self._data, f, indent=2, ensure_ascii=False)
                os.replace(tmp, self.path)
            except OSError:
                pass

    def get(self, key: str, default: Any = None) -> Any:
        with self._lock:
            return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            self._data[key] = value
        self.save()

    def remove(self, key: str) -> None:
        with self._lock:
            self._data.pop(key, None)
        self.save()

    def replace(self, new_data: Dict[str, Any]) -> None:
        with self._lock:
            self._data = dict(new_data)
        self.save()

    def data(self) -> Dict[str, Any]:
        with self._lock:
            return {k: v for k, v in self._data.items()}


class ConfigStore(JsonStore):
    """Legacy single-file store (used for message doc map, incidents)."""


class BotConfig:
    """Per-guild configuration backed by server_configs.json."""

    def __init__(self, path: str = "server_configs.json"):
        self._store = JsonStore(path)

    # --- guild-level helpers ---
    def _guild(self, guild_id: int) -> Dict[str, Any]:
        guilds = self._store.get("guilds", {})
        gid = str(guild_id)
        if gid not in guilds:
            guilds[gid] = {}
            self._store.set("guilds", guilds)
        guild = guilds[gid]
        for key, default in DEFAULT_CONFIG.items():
            guild.setdefault(key, default)
        return guild

    def get(self, guild_id: int, key: str, default: Any = None) -> Any:
        return self._guild(guild_id).get(key, default if default is not None else DEFAULT_CONFIG.get(key))

    def set(self, guild_id: int, key: str, value: Any) -> None:
        guild = self._guild(guild_id)
        guild[key] = value
        self._store.set("guilds", self._store.get("guilds"))

    def reset_guild(self, guild_id: int) -> None:
        guilds = self._store.get("guilds", {})
        guilds.pop(str(guild_id), None)
        self._store.set("guilds", guilds)

    def all_guilds(self) -> Dict[str, Dict[str, Any]]:
        return self._store.get("guilds", {})

    # --- personalities registry (global, not per-guild) ---
    def personalities(self) -> Dict[str, Dict[str, Any]]:
        return self._store.get("personalities", {})

    def add_personality(self, name: str, data: Dict[str, Any]) -> None:
        reg = self._store.get("personalities", {})
        reg[name] = data
        self._store.set("personalities", reg)

    def remove_personality(self, name: str) -> None:
        reg = self._store.get("personalities", {})
        reg.pop(name, None)
        self._store.set("personalities", reg)

    def personality(self, name: str) -> Optional[Dict[str, Any]]:
        return self._store.get("personalities", {}).get(name)

    def set_default_guild_config(self, guild_id: int):
        self._guild(guild_id)
        self._store.set("guilds", self._store.get("guilds"))