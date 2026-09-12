"""Test semantic search against a collection.

Usage: python test_query.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.database import Database

collection = sys.argv[1] if len(sys.argv) > 1 else "friend_messages"

db = Database()
if not db.has_collection(collection):
    print(f"Collection '{collection}' does not exist")
    sys.exit(1)

while True:
    query = input("\nQuery (or 'q' to quit): ").strip()
    if query.lower() in ("q", "quit", "exit"):
        break
    if not query:
        continue
    results = db.query(collection, query, n_results=5)
    for i, r in enumerate(results, start=1):
        print(f"{i}. {r['doc'][:160]}")