from __future__ import annotations

import json
import re
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
NEWS_PATH = ROOT / "data" / "news.json"

RECIRCULATION_LABELS = (
    "read more",
    "related story",
    "related stories",
    "more from",
    "recommended for you",
    "you may also like",
    "also read",
    "keep reading",
    "more stories",
)


def text_key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def is_recirculation_label(value: Any) -> bool:
    key = text_key(value)
    return bool(key) and any(key == label or key.startswith(f"{label} ") for label in RECIRCULATION_LABELS)


def title_match(item: Any, titles: set[str]) -> bool:
    key = text_key(item)
    if len(key) < 18:
        return False
    if key in titles:
        return True
    for title in titles:
        if len(title) < 18:
            continue
        shorter, longer = (key, title) if len(key) <= len(title) else (title, key)
        if len(shorter) >= 24 and shorter in longer and len(shorter) / len(longer) >= 0.72:
            return True
        if SequenceMatcher(None, key, title).ratio() >= 0.88:
            return True
    return False


def shared_headline_prefix(items: list[str]) -> bool:
    prefixes: list[str] = []
    for item in items:
        if ":" not in item:
            return False
        prefix = text_key(item.split(":", 1)[0])
        if len(prefix) < 4 or len(prefix.split()) > 5:
            return False
        prefixes.append(prefix)
    return len(set(prefixes)) == 1


def headline_like(value: str) -> bool:
    text = str(value or "").strip()
    count = len(re.findall(r"\b\w+[’'-]?\w*\b", text))
    if count < 4 or count > 22:
        return False
    if re.search(r"[.!?][\"'’”)]?$", text):
        return False
    if re.match(r"(?i)^(?:step|tip|reason|rule|item)\s+\d+\b", text):
        return False
    return True


def looks_like_promoted_headline_run(items: list[str], ordered: bool) -> bool:
    if len(items) < 2 or len(items) > 6:
        return False
    if shared_headline_prefix(items):
        return True
    if not ordered:
        return False
    headline_count = sum(1 for item in items if headline_like(item))
    return headline_count == len(items) and all(len(item) >= 24 for item in items)


def list_is_story_promo(block: dict[str, Any], other_titles: set[str]) -> bool:
    if block.get("type") != "list":
        return False
    items = [str(item or "").strip() for item in block.get("items", []) if str(item or "").strip()]
    if len(items) < 2:
        return False
    matches = sum(1 for item in items if title_match(item, other_titles))
    if matches >= 2 and matches / len(items) >= 0.67:
        return True
    return looks_like_promoted_headline_run(items, bool(block.get("ordered")))


def prune_story(story: dict[str, Any], all_stories: list[dict[str, Any]]) -> bool:
    blocks = story.get("content_blocks") if isinstance(story.get("content_blocks"), list) else []
    if not blocks:
        return False

    current_id = str(story.get("id") or "")
    current_title = text_key(story.get("title"))
    other_titles = {
        key
        for candidate in all_stories
        if str(candidate.get("id") or "") != current_id
        for key in [text_key(candidate.get("title"))]
        if key and key != current_title
    }

    cleaned: list[dict[str, Any]] = []
    changed = False
    for block in blocks:
        if list_is_story_promo(block, other_titles):
            changed = True
            if cleaned and cleaned[-1].get("type") in {"heading", "paragraph"} and is_recirculation_label(cleaned[-1].get("text")):
                cleaned.pop()
            continue
        cleaned.append(block)

    index = 0
    final: list[dict[str, Any]] = []
    while index < len(cleaned):
        block = cleaned[index]
        if block.get("type") in {"heading", "paragraph"} and is_recirculation_label(block.get("text")):
            cursor = index + 1
            matched = 0
            while cursor < len(cleaned) and cursor <= index + 6:
                candidate = cleaned[cursor]
                if candidate.get("type") not in {"paragraph", "heading"}:
                    break
                if title_match(candidate.get("text"), other_titles):
                    matched += 1
                    cursor += 1
                    continue
                break
            if matched >= 2:
                changed = True
                index = cursor
                continue
        final.append(block)
        index += 1

    if not changed:
        return False

    story["content_blocks"] = final
    paragraphs: list[str] = []
    for block in final:
        kind = block.get("type")
        if kind in {"paragraph", "quote"} and block.get("text"):
            paragraphs.append(str(block["text"]).strip())
        elif kind == "list":
            paragraphs.extend(str(item).strip() for item in block.get("items", []) if str(item).strip())
    story["paragraphs"] = paragraphs
    story["content"] = "\n\n".join(paragraphs)
    story["word_count"] = sum(len(re.findall(r"\b\w+[’'-]?\w*\b", paragraph)) for paragraph in paragraphs)
    story["recirculation_cleaned"] = True
    return True


def clean_payload(payload: dict[str, Any]) -> int:
    stories = payload.get("stories") if isinstance(payload.get("stories"), list) else []
    return sum(1 for story in stories if isinstance(story, dict) and prune_story(story, stories))


def main() -> int:
    if not NEWS_PATH.exists():
        print("No data/news.json found")
        return 0
    payload = json.loads(NEWS_PATH.read_text(encoding="utf-8"))
    changed = clean_payload(payload)
    if changed:
        NEWS_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Article recirculation cleanup: {changed} stories corrected")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
