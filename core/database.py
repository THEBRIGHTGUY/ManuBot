"""Thin, safe wrapper around ChromaDB for ManuBot."""

from __future__ import annotations

import logging
import re
import threading
import uuid
from typing import Dict, Iterable, List, Optional

import chromadb

log = logging.getLogger("manubot.db")

_PERSIST_PATH = "chroma_db"

_ID_SAFE = re.compile(r"[^a-zA-Z0-9_-]")
_DEFAULT_COLLECTION = "friend_messages"
_ARCHIVE_COLLECTION = "server_archive"


def sanitize_collection_name(name: str) -> str:
    """Chroma collection names must be <= 3-63 chars, start+end alnum, allow [a-zA-Z0-9._-]."""
    cleaned = _ID_SAFE.sub("_", name.strip().lower())
    cleaned = cleaned.strip("._")
    cleaned = cleaned[:63] or "unnamed"
    return cleaned


class Database:
    def __init__(self, persist_path: str = _PERSIST_PATH):
        # chromadb.sparse vs dense: default embedder downloads onnx model on first query.
        self._client = chromadb.PersistentClient(path=persist_path)
        self._lock = threading.RLock()
        self._collections: Dict[str, "chromadb.Collection"] = {}
        self._warmed = False

    def warm_up(self) -> bool:
        """Trigger the embedding model download so first real query isn't slow."""
        if self._warmed:
            return True
        try:
            self.query("friend_messages", "warmup", n_results=1)
            self._warmed = True
            return True
        except Exception as exc:  # noqa: BLE001
            log.warning("warm_up failed: %s", exc)
            return False

    # -- collection management ------------------------------------------------
    def collection(self, name: str, create: bool = True) -> "chromadb.Collection":
        name = sanitize_collection_name(name)
        with self._lock:
            if name in self._collections:
                return self._collections[name]
            if create:
                coll = self._client.get_or_create_collection(name=name)
            else:
                coll = self._client.get_collection(name=name)
            self._collections[name] = coll
            return coll

    def has_collection(self, name: str) -> bool:
        return sanitize_collection_name(name) in {c.name for c in self._client.list_collections()}

    def list_collections(self) -> List[str]:
        return [c.name for c in self._client.list_collections()]

    def drop_collection(self, name: str) -> bool:
        name = sanitize_collection_name(name)
        with self._lock:
            if name in self._collections:
                del self._collections[name]
            try:
                self._client.delete_collection(name)
                return True
            except Exception as exc:  # noqa: BLE001
                log.warning("drop_collection(%s) failed: %s", name, exc)
                return False

    # -- ops ------------------------------------------------------------------
    def count(self, collection: str) -> int:
        try:
            return self.collection(collection).count()
        except Exception as exc:  # noqa: BLE001
            log.warning("count(%s) failed: %s", collection, exc)
            return 0

    def add(self, collection: str, text: str, metadata: Optional[Dict] = None, doc_id: Optional[str] = None) -> Optional[str]:
        doc_id = doc_id or str(uuid.uuid4())
        try:
            self.collection(collection).upsert(
                ids=[doc_id],
                documents=[text],
                metadatas=[metadata or {}],
            )
            return doc_id
        except Exception as exc:  # noqa: BLE001
            log.error("add failed on %s: %s", collection, exc)
            return None

    def query(self, collection: str, text: str, n_results: int = 8) -> List[Dict]:
        """Return up to n_results dicts with keys: doc, metadata, distance, id."""
        try:
            results = self.collection(collection).query(
                query_texts=[text],
                n_results=max(1, min(n_results, 50)),
                include=["documents", "metadatas", "distances"],
            )
        except Exception as exc:  # noqa: BLE001
            log.error("query failed: %s", exc)
            return []

        documents = (results.get("documents") or [[]])[0]
        metadatas = (results.get("metadatas") or [[]])[0]
        distances = (results.get("distances") or [[]])[0]
        ids = (results.get("ids") or [[]])[0]

        out = []
        for i, doc in enumerate(documents):
            out.append({
                "doc": doc,
                "metadata": (metadatas[i] if i < len(metadatas) else {}) or {},
                "distance": (distances[i] if i < len(distances) else None),
                "id": (ids[i] if i < len(ids) else None),
            })
        return out

    def update_metadata(self, collection: str, doc_id: str, metadata: Dict) -> bool:
        try:
            self.collection(collection).update(
                ids=[doc_id],
                metadatas=[metadata],
            )
            return True
        except Exception as exc:  # noqa: BLE001
            log.warning("update_metadata failed: %s", exc)
            return False

    def delete(self, collection: str, doc_id: str) -> bool:
        try:
            self.collection(collection).delete(ids=[doc_id])
            return True
        except Exception as exc:  # noqa: BLE001
            log.warning("delete failed: %s", exc)
            return False

    def get_by_ids(self, collection: str, ids: Iterable[str]) -> Dict:
        try:
            return self.collection(collection).get(ids=list(ids))
        except Exception as exc:  # noqa: BLE001
            log.warning("get_by_ids failed: %s", exc)
            return {"ids": [], "documents": [], "metadatas": []}

    def get_where(self, collection: str, where: Dict, limit: int = 1000) -> Dict:
        try:
            return self.collection(collection).get(where=where, limit=limit)
        except Exception as exc:  # noqa: BLE001
            log.warning("get_where failed: %s", exc)
            return {"ids": [], "documents": [], "metadatas": []}

    def delete_where(self, collection: str, where: Dict) -> int:
        try:
            result = self.collection(collection).delete(where=where)
            return int(result.get("deleted", 0)) if isinstance(result, dict) else 1
        except Exception as exc:  # noqa: BLE001
            log.warning("delete_where failed: %s", exc)
            return 0

    def add_batch(self, collection: str, texts: List[str], metadatas: List[Dict], ids: Optional[List[str]] = None, batch_size: int = 500) -> int:
        """Return number of docs added. Falls back to per-doc upserts on failure."""
        if not texts:
            return 0
        ids = ids or [str(uuid.uuid4()) for _ in texts]
        coll = self.collection(collection)
        added = 0
        try:
            for i in range(0, len(texts), batch_size):
                coll.upsert(
                    ids=ids[i:i + batch_size],
                    documents=texts[i:i + batch_size],
                    metadatas=metadatas[i:i + batch_size],
                )
                added += len(texts[i:i + batch_size])
            return added
        except Exception as exc:  # noqa: BLE001
            log.error("batch upsert failed (%s), falling back per-doc", exc)
        for i, text in enumerate(texts):
            if self.add(collection, text, metadatas[i], ids[i]):
                added += 1
        return added


DEFAULT_COLLECTION = _DEFAULT_COLLECTION
ARCHIVE_COLLECTION = _ARCHIVE_COLLECTION