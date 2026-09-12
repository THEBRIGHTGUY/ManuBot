"""Delete all generated (bot-made) entries from a collection.

Usage: python db_cleanup.py [collection]
Default collection: friend_messages
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

result = db.get_where(collection, {"source": "generated"})
bad_ids = result.get("ids", [])
if bad_ids:
    deleted = db.delete_where(collection, {"source": "generated"})
    print(f"Deleted {deleted:,} generated entries")
else:
    print("Nothing to delete")