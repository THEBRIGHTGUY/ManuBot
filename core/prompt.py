"""Prompt construction for personality mimicry."""

from __future__ import annotations

from typing import Dict, List, Optional

from utils.helpers import truncate


def select_examples(results: List[Dict], max_examples: int = 8, prefer_quality: bool = True) -> List[Dict]:
    """Pick good example messages from retrieval results.

    Prefer real original messages and generated ones rated >= 0.6.
    """
    if not results:
        return []
    if not prefer_quality:
        return results[:max_examples]

    good = [r for r in results if r["metadata"].get("source") == "original" or float(r["metadata"].get("quality", 0)) >= 0.6]
    fallback = [r for r in results if r not in good]

    chopped = good[:max_examples]
    if len(chopped) < max_examples:
        chopped += fallback[: max_examples - len(chopped)]
    return chopped


def format_examples(examples: List[Dict]) -> str:
    lines = []
    for ex in examples:
        content = truncate(ex.get("doc", ""), 400)
        origin = ""
        if ex["metadata"].get("source") == "generated":
            q = float(ex["metadata"].get("quality", 0))
            origin = f"  [note: this was one of your own replies, rated {q:.0%} by someone]"
        lines.append(f'- "{content}"{origin}')
    return "\n".join(lines) if lines else "(no examples available)"


def format_lore(incidents: Dict[str, Dict]) -> str:
    if not incidents:
        return ""
    lines = []
    for name, info in list(incidents.items())[:5]:
        desc = truncate(str(info.get("description", "")), 160)
        lines.append(f"- **{name}**: {desc}")
    return "\n".join(lines)


def build_system_prompt(
    personality_name: str,
    examples: List[Dict],
    lore: Optional[Dict[str, Dict]] = None,
    extra_instructions: Optional[str] = None,
) -> str:
    examples_block = format_examples(examples)
    lore_block = format_lore(lore or {})

    instruct = extra_instructions or (
        "Study their tone, slang, punctuation habits, and message length. "
        "Respond the way THIS PERSON would respond, not generically and not like a helpful assistant. "
        "Keep responses short and casual like real Discord messages, matching their typical style. "
        "Stay consistent with the ongoing conversation. Do not use emojis. Do not use hashtags."
    )

    parts = [
        f"You are a Discord bot that imitates the texting style of a specific person ({personality_name}).",
        "",
        "Here are REAL messages this person has sent in similar contexts:",
        examples_block,
    ]

    if lore_block:
        parts += [
            "",
            "Related lore / inside jokes about this server's community that you should reflect in your tone when relevant:",
            lore_block,
        ]

    parts += [
        "",
        f"Instructions: {instruct}",
    ]

    return "\n\n".join(parts)