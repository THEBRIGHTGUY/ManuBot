"""Embed scraped messages into a ChromaDB collection in batches."""

from __future__ import annotations

import logging
import uuid as _uuid
from typing import Callable, Dict, List, Optional

from core.database import Database

log = logging.getLogger("manubot.embedder")


def embed_messages(
    db: Database,
    collection: str,
    messages: List[Dict],
    source: str = "original",
    quality: float = 1.0,
    batch_size: int = 500,
    progress_cb: Optional[Callable[[str], None]] = None,
) -> int:
    """Add messages to the given collection. Returns number added."""
    if progress_cb is None:
        progress_cb = lambda text: None  # noqa: E731

    ids: List[str] = []
    texts: List[str] = []
    metadatas: List[Dict] = []

    for msg in messages:
        content = (msg.get("content") or "").strip()
        if not content:
            continue
        ids.append(str(msg["id"]) if msg.get("id") else str(_uuid.uuid4()))
        texts.append(content)
        metadatas.append({
            "channel": msg.get("channel", ""),
            "timestamp": msg.get("timestamp", ""),
            "source": source,
            "quality": quality,
            "author": str(msg.get("author", "")),
        })

    added = 0
    for i in range(0, len(texts), batch_size):
        chunk_ids = ids[i : i + batch_size]
        chunk_texts = texts[i : i + batch_size]
        chunk_meta = metadatas[i : i + batch_size]
        batch = db.add_batch(collection, chunk_texts, chunk_meta, chunk_ids)
        added += batch
        progress_cb(f"Embedded {i + len(chunk_texts)}/{len(texts)}")
    return added