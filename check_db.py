"""Inspect the ChromaDB collections (updated to use core.database)."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.database import Database

db = Database()

for name in db.list_collections():
    print(f"- {name}: {db.count(name):,} documents")

personality = input("\nCollection to peek (default: friend_messages): ").strip() or "friend_messages"
if db.has_collection(personality):
    result = db.get_where(personality, {}, limit=5)
    for doc in result.get("documents", []):
        print("  ", doc[:120])
else:
    print("collection does not exist")