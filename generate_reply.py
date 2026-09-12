"""CLI reply generator - test the mimic pipeline from the terminal.

Usage: python generate_reply.py ["optional message"]
If no message is given it will prompt interactively.
"""

import os
import sys

from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

load_dotenv(".env")
load_dotenv("env")

from core.config import BotConfig
from core.database import Database
from core.groq_client import GroqClient
from core.personality import PersonalityManager
from core.prompt import build_system_prompt, select_examples


def main():
    collection = os.environ.get("CLI_COLLECTION", "friend_messages")
    db = Database()
    llm = GroqClient()
    cfg = BotConfig()
    personalities = PersonalityManager(cfg)

    if not db.has_collection(collection):
        print(f"Collection '{collection}' not found")
        return

    test_input = sys.argv[1] if len(sys.argv) > 1 else input("Say something to the bot: ").strip()
    if not test_input:
        return

    results = db.query(collection, test_input, n_results=12)
    examples = select_examples(results, max_examples=8)
    system = build_system_prompt("cli-person", examples)
    reply = llm.generate(system, [{"role": "user", "content": test_input}])
    print(f"\nBot reply: {reply}")


if __name__ == "__main__":
    main()