from __future__ import annotations

"""Final article guard for publisher chrome, navigation dumps and recirculation.

This runs after extraction/merging. It deliberately accepts loose block shapes so
footer links, dropdown/menu dumps and publisher modules represented as custom
blocks cannot evade the normal reader sanitizers.
"""

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
NEWS_PATH = ROOT / "data" / "news.json"
TAIL_SCHEMA = 2
MIN_COMPLETE_WORDS = 55

CTV_TERMINAL_MARKERS = (
    "report an error",
    "editorial standards policies",
    "editorial standards and policies",
    "why you can trust ctv news",
)

GLOBE_TERMINAL_MARKERS = (
    "diversions",
    "puzzles games",
    "puzzles and games",
    "latest videos",
    "more videos",
    "watch more videos",
)

STAR_TERMINAL_MARKERS = (
    "you have permission to edit this article",
    "site search search",
    "site search",
    "today s paper",
    "todays paper",
)

STAR_LEADING_MARKERS = STAR_TERMINAL_MARKERS + (
    "play now",
    "readers choice awards",
    "shopping and services",
)

GENERIC_TERMINAL_MARKERS = (
    "report an editorial error",
    "report a technical issue",
)

STAR_NAV_TOKENS = {
    "top 100 restaurants",
    "if i were mayor",
    "the signal",
    "wildfires",
    "tariffs",
    "readers choice awards",
    "shopping and services",
    "ontario",
    "alberta",
    "quebec",
}

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


def sentence_like(value: Any) -> bool:
    text = item_text(value)
    return words(text) >= 5 and bool(re.search(r"[.!?][\"'’”)]?$", text))


def prose_words(block: dict[str, Any]) -> int:
    if block.get("type") not in {"paragraph", "quote", "list"}:
        return 0
    return words(block_text(block))


def substantive_prose(block: dict[str, Any]) -> bool:
    if block.get("type") not in {"paragraph", "quote"}:
        return False
    text = item_text(block.get("text"))
    return words(text) >= 10 and (sentence_like(text) or words(text) >= 18)


def contains_marker(text: str, markers: tuple[str, ...]) -> bool:
    normalized = key(text)
    if not normalized or len(normalized) > 260:
        return False
    return any(marker in normalized for marker in markers)


def matches_label(text: str, markers: tuple[str, ...]) -> bool:
    normalized = key(text)
    if not normalized or len(normalized) > 140 or words(normalized) > 12:
        return False
    return any(normalized == marker or normalized.startswith(marker + " ") for marker in markers)


def linked_list_items(block: dict[str, Any]) -> int:
    items = block.get("items") if isinstance(block.get("items"), list) else []
    linked = 0
    for item in items:
        if not isinstance(item, dict):
            continue
        markup = str(item.get("html") or "").strip()
        if re.fullmatch(r"<a\b[^>]*>.*</a>", markup, flags=re.I | re.S):
            linked += 1
    return linked


def looks_like_navigation_list(story: dict[str, Any], block: dict[str, Any]) -> bool:
    if block.get("type") != "list":
        return False
    items = [item_text(item) for item in block.get("items", []) if item_text(item)]
    if len(items) < 4:
        return False

    short = sum(1 for item in items if words(item) <= 10)
    sentences = sum(1 for item in items if sentence_like(item))
    linked = linked_list_items(block)
    short_ratio = short / len(items)
    sentence_ratio = sentences / len(items)
    if linked >= 3 and linked / len(items) >= 0.6 and short_ratio >= 0.7 and sentence_ratio <= 0.25:
        return True

    source = key(story.get("source"))
    if "toronto star" not in source:
        return False
    item_keys = {key(item) for item in items}
    marker_hits = sum(1 for marker in STAR_NAV_TOKENS if marker in item_keys)
    return marker_hits >= 2 and short_ratio >= 0.65 and sentence_ratio <= 0.25


def leading_chrome(story: dict[str, Any], block: dict[str, Any]) -> bool:
    text = block_text(block)
    source = key(story.get("source"))
    if looks_like_navigation_list(story, block):
        return True
    if "toronto star" in source and matches_label(text, STAR_LEADING_MARKERS):
        return True
    if "globe and mail" in source and matches_label(text, GLOBE_TERMINAL_MARKERS):
        return True
    return False


def terminal_tail(story: dict[str, Any], block: dict[str, Any], accumulated_words: int, prose_blocks: int) -> bool:
    if accumulated_words < 45 and prose_blocks < 2:
        return False

    text = block_text(block)
    source = key(story.get("source"))
    if "ctv" in source and contains_marker(text, CTV_TERMINAL_MARKERS):
        return True
    if "globe and mail" in source and matches_label(text, GLOBE_TERMINAL_MARKERS):
        return True
    if "toronto star" in source and (
        matches_label(text, STAR_TERMINAL_MARKERS) or looks_like_navigation_list(story, block)
    ):
        return True
    return contains_marker(text, GENERIC_TERMINAL_MARKERS)


def rebuild(story: dict[str, Any], blocks: list[dict[str, Any]], flag: str) -> None:
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
    flags = [str(value) for value in story.get("article_hygiene_flags", []) if value]
    if flag not in flags:
        flags.append(flag)
    story["article_hygiene_flags"] = flags
    if int(story.get("word_count") or 0) < MIN_COMPLETE_WORDS:
        story["content_status"] = "partial"
        story["article_format_state"] = "needs-recovery"


def strip_leading_chrome(story: dict[str, Any], blocks: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], bool]:
    out: list[dict[str, Any]] = []
    changed = False
    chrome_run = False
    real_words = 0

    for block in blocks:
        if real_words < 45 and leading_chrome(story, block):
            changed = True
            chrome_run = True
            continue

        if chrome_run:
            if substantive_prose(block):
                chrome_run = False
            else:
                changed = True
                continue

        out.append(block)
        real_words += prose_words(block)

    return out, changed


def trim_story(story: dict[str, Any]) -> bool:
    raw_blocks = story.get("content_blocks")
    if not isinstance(raw_blocks, list) or not raw_blocks:
        return False

    blocks = [dict(block) for block in raw_blocks if isinstance(block, dict)]
    blocks, leading_changed = strip_leading_chrome(story, blocks)

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

    tail_changed = end is not None
    if not leading_changed and not tail_changed:
        story["article_tail_schema"] = TAIL_SCHEMA
        return False

    if tail_changed:
        blocks = blocks[:end]
    flag = "publisher-chrome-leading" if leading_changed and not tail_changed else "publisher-footer-tail"
    rebuild(story, blocks, flag)
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
