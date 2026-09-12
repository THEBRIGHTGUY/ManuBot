"""Personality registry: which person the bot imitates and its data collection."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional

from core.config import BotConfig
from core.database import DEFAULT_COLLECTION, sanitize_collection_name

DEFAULT_PERSONALITY = "default"


@dataclass
class Personality:
    name: str
    collection: str
    description: str = ""
    target_user_id: int = 0
    created_at: str = ""
    message_count: int = 0
    guild_id: int = 0

    @classmethod
    def from_dict(cls, data: Dict) -> "Personality":
        return cls(
            name=data.get("name", DEFAULT_PERSONALITY),
            collection=data.get("collection", DEFAULT_COLLECTION),
            description=data.get("description", ""),
            target_user_id=int(data.get("target_user_id") or 0),
            created_at=data.get("created_at", ""),
            message_count=int(data.get("message_count") or 0),
            guild_id=int(data.get("guild_id") or 0),
        )

    def to_dict(self) -> Dict:
        return asdict(self)


class PersonalityManager:
    def __init__(self, config: BotConfig):
        self._config = config
        self._ensure_default()

    def _ensure_default(self) -> None:
        if not self._config.personality(DEFAULT_PERSONALITY):
            self.add(
                name=DEFAULT_PERSONALITY,
                description="Default personality - mimics big bhav",
                collection=DEFAULT_COLLECTION,
                target_user_id=0,
            )

    def add(self, name: str, collection: str, description: str = "", target_user_id: int = 0, guild_id: int = 0) -> Personality:
        assert sanitize_collection_name(collection), "invalid collection name"
        person = Personality(
            name=name,
            collection=sanitize_collection_name(collection),
            description=description,
            target_user_id=target_user_id,
            created_at=datetime.now(timezone.utc).isoformat(),
            guild_id=guild_id,
        )
        self._config.add_personality(name, person.to_dict())
        return person

    def remove(self, name: str) -> bool:
        if name == DEFAULT_PERSONALITY:
            return False
        self._config.remove_personality(name)
        return True

    def get(self, name: str) -> Optional[Personality]:
        data = self._config.personality(name)
        return Personality.from_dict(data) if data else None

    def list(self) -> List[Personality]:
        return sorted(
            (Personality.from_dict(data) for data in self._config.personalities().values()),
            key=lambda p: p.name,
        )

    def get_active(self, guild_id: int) -> Personality:
        name = self._config.get(guild_id, "active_personality", DEFAULT_PERSONALITY)
        person = self.get(name)
        if person:
            return person
        return self.get(DEFAULT_PERSONALITY)  # type: ignore[return-value]

    def set_active(self, guild_id: int, name: str) -> bool:
        if not self.get(name):
            return False
        self._config.set(guild_id, "active_personality", name)
        return True