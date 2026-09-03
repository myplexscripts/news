from __future__ import annotations

"""Final article-tail guard for publisher footer chrome and recirculation.

This runs after extraction/merging. It deliberately accepts loose block shapes so
footer links represented as custom/link blocks cannot evade the normal reader
sanitizers.
"""

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
NEWS_PATH = ROOT / "data" / "news.json"
TAIL_SCHEMA = 1

CTV_TERMINAL_MARKERS = (
    "report an error",
    "editorial standards policies",
    "editorial standards and policies",
    "why you can trust ctv news",
)

GENERIC_TERMINAL_MARKERS = (
    "report an editorial error",
    "report a technical issue",
)

TEXT_FIELDS = ("text", "title", "label", "name", "caption", "alt", "aria_label", "aria-label")


def item_text(value: Any) -> str:
    if isinstance(value, dict):
        for field in TEXT_FIELDS:
            raw = value.get(field)
            if raw:
                return str(raw).strip()
        return ""
    return str(value or "").strip()


def block_text(block: dict[str, Any]) -> str:
    values: list[str] = []
    for field in TEXT_FIELDS:
        raw = block.get(field)
        if raw:
            values.append(str(raw).strip())
    items = block.get("items")
    if isinstance(items, list):
        values.extend(item_text(item) for item in items if item_text(item))
    return " ".join(value for value in values if value).strip()


def key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def words(value: Any) -> int:
    return len(re.findall(r"\b\w+[’'-]?\w*\b", str(value or "")))


def prose_words(block: dict[str, Any]) -> int:
    if block.get("type") not in {"paragraph", "quote", "list"}:
        return 0
    return words(block_text(block))


def contains_marker(text: str, markers: tuple[str, ...]) -> bool:
    normalized = key(text)
    if not normalized or len(normalized) > 260:
        return False
    return any(marker in normalized for marker in markers)


def terminal_tail(story: dict[str, Any], block: dict[str, Any], accumulated_words: int, prose_blocks: int) -> bool:
    if accumulated_words < 45 and prose_blocks < 2:
        return False

    text = block_text(block)
    source = key(story.get("source"))
    if "ctv" in source and contains_marker(text, CTV_TERMINAL_MARKERS):
        return True
    return contains_marker(text, GENERIC_TERMINAL_MARKERS)


def rebuild(story: dict[str, Any], blocks: list[dict[str, Any]]) -> None:
    paragraphs: list[str] = []
    for block in blocks:
        kind = block.get("type")
        if kind in {"paragraph", "quote"}:
            text = item_text(block.get("text"))
            if text:
                paragraphs.append(text)
        elif kind == "list":
            paragraphs.extend(item_text(item) for item in block.get("items", []) if item_text(item))

    story["content_blocks"] = blocks
    story["paragraphs"] = paragraphs
    story["content"] = "\n\n".join(paragraphs)
    story["word_count"] = sum(words(paragraph) for paragraph in paragraphs)
    story["article_tail_schema"] = TAIL_SCHEMA
    story["article_tail_trimmed"] = True
    flags = [str(flag) for flag in story.get("article_hygiene_flags", []) if flag]
    if "publisher-footer-tail" not in flags:
        flags.append("publisher-footer-tail")
    story["article_hygiene_flags"] = flags


def trim_story(story: dict[str, Any]) -> bool:
    raw_blocks = story.get("content_blocks")
    if not isinstance(raw_blocks, list) or not raw_blocks:
        return False

    blocks = [dict(block) for block in raw_blocks if isinstance(block, dict)]
    accumulated_words = 0
    prose_blocks = 0
    end: int | None = None

    for index, block in enumerate(blocks):
        if terminal_tail(story, block, accumulated_words, prose_blocks):
            end = index
            break
        count = prose_words(block)
        if count:
            accumulated_words += count
            prose_blocks += 1

    if end is None:
        story["article_tail_schema"] = TAIL_SCHEMA
        return False

    rebuild(story, blocks[:end])
    return True


def trim_payload(payload: dict[str, Any]) -> int:
    stories = payload.get("stories") if isinstance(payload.get("stories"), list) else []
    changed = sum(1 for story in stories if isinstance(story, dict) and trim_story(story))
    payload["article_tail_schema"] = TAIL_SCHEMA
    payload["article_tail_cleanup_at"] = datetime.now(timezone.utc).isoformat()
    payload["article_tail_cleanup_corrected"] = changed
    return changed


def main() -> int:
    if not NEWS_PATH.exists():
        print("No data/news.json found")
        return 0
    payload = json.loads(NEWS_PATH.read_text(encoding="utf-8"))
    changed = trim_payload(payload)
    NEWS_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Article tail cleanup: {changed} stories trimmed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
