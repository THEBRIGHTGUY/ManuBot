"""Misc helpers: text cleaning, time formatting, chunking."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Iterable, List, Sequence, TypeVar

T = TypeVar("T")

_MENTION_RE = re.compile(r"<@!?&?\d+>")


def strip_mentions(content: str) -> str:
    return _MENTION_RE.sub("", content).strip()


def truncate(text: str, max_len: int = 200) -> str:
    text = (text or "").strip()
    if len(text) <= max_len:
        return text
    return text[: max_len - 1].rstrip() + "\u2026"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def is_snowflake(value) -> bool:
    try:
        v = int(value)
        return v > 0
    except (TypeError, ValueError):
        return False


def chunk(items: Sequence[T], size: int) -> List[Sequence[T]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def format_duration(seconds: float) -> str:
    seconds = int(seconds)
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, sec = divmod(rem, 60)
    parts = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    if sec or not parts:
        parts.append(f"{sec}s")
    return " ".join(parts[:3])


def parse_int_list(raw: str) -> List[int]:
    """Parse '123, 456,789' into a list of ints, ignoring junk."""
    out: List[int] = []
    for token in re.split(r"[,\s]+", raw.strip()):
        t = token.strip()
        if t.lstrip("-").isdigit():
            out.append(int(t))
    return out


def uniq(values: Iterable[T]) -> List[T]:
    seen = set()
    out = []
    for v in values:
        if v not in seen:
            seen.add(v)
            out.append(v)
    return out