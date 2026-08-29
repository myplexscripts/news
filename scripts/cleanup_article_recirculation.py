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
    "more to read",
    "read next",
    "more on this topic",
    "trending",
    "most read",
    "most popular",
)

UTILITY_LABELS = (
    "newsletter",
    "newsletters",
    "sign up for our newsletter",
    "sign up for our newsletters",
    "subscribe to our newsletter",
    "download our app",
    "download the app",
    "get the app",
    "follow us",
    "advertisement",
    "sponsored content",
)

PROMO_METADATA_MARKERS = (
    "recirc",
    "recirculation",
    "related",
    "recommend",
    "promotion",
    "promo",
    "newsletter",
    "advert",
    "sponsor",
    "more-from",
    "read-more",
)


def item_text(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("text") or "").strip()
    return str(value or "").strip()


def text_key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", item_text(value).lower()).strip()


def word_count(value: Any) -> int:
    return len(re.findall(r"\b\w+[’'-]?\w*\b", item_text(value)))


def is_recirculation_label(value: Any) -> bool:
    key = text_key(value)
    return bool(key) and any(key == label or key.startswith(f"{label} ") for label in RECIRCULATION_LABELS)


def is_utility_label(value: Any) -> bool:
    key = text_key(value)
    return bool(key) and any(key == label or key.startswith(f"{label} ") for label in UTILITY_LABELS)


def metadata_marks_promo(block: dict[str, Any]) -> bool:
    values = " ".join(
        str(block.get(key) or "")
        for key in ("role", "kind", "module", "module_type", "source_type", "class_name")
    ).lower()
    return bool(values) and any(marker in values for marker in PROMO_METADATA_MARKERS)


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


def headline_like(value: Any) -> bool:
    text = item_text(value)
    count = word_count(text)
    if count < 4 or count > 22:
        return False
    if re.search(r"[.!?][\"'’”)]?$", text):
        return False
    if re.match(r"(?i)^(?:step|tip|reason|rule|item|question)\s+\d+\b", text):
        return False
    return True


def sentence_like(value: Any) -> bool:
    text = item_text(value)
    return word_count(text) >= 8 and bool(re.search(r"[.!?][\"'’”)]?$", text))


def source_is_publisher_with_inline_cards(source: str) -> bool:
    lower = source.lower()
    return any(name in lower for name in ("free press", "postmedia", "ctv", "global news", "cbc"))


def looks_like_promoted_headline_run(items: list[str], ordered: bool, source: str = "") -> bool:
    if len(items) < 2 or len(items) > 8:
        return False
    if shared_headline_prefix(items):
        return True
    headline_count = sum(1 for item in items if headline_like(item))
    if headline_count != len(items):
        return False
    if ordered and all(len(item) >= 24 for item in items):
        return source_is_publisher_with_inline_cards(source)
    return False


def list_is_story_promo(block: dict[str, Any], other_titles: set[str], source: str = "") -> bool:
    if block.get("type") != "list":
        return False
    items = [text for item in block.get("items", []) if (text := item_text(item))]
    if len(items) < 2:
        return False
    matches = sum(1 for item in items if title_match(item, other_titles))
    if matches >= 2 and matches / len(items) >= 0.67:
        return True
    return looks_like_promoted_headline_run(items, bool(block.get("ordered")), source)


def headline_block(block: dict[str, Any], other_titles: set[str]) -> bool:
    if block.get("type") not in {"paragraph", "heading"}:
        return False
    text = str(block.get("text") or "").strip()
    return title_match(text, other_titles) or headline_like(text)


def skip_labelled_module(
    blocks: list[dict[str, Any]],
    start: int,
    other_titles: set[str],
    source: str,
) -> int | None:
    label = blocks[start]
    text = label.get("text")
    recirc = is_recirculation_label(text)
    utility = is_utility_label(text)
    if not recirc and not utility:
        return None

    cursor = start + 1
    headlines = 0
    consumed = 0
    saw_promo_content = False
    while cursor < len(blocks) and consumed < 10:
        block = blocks[cursor]
        kind = block.get("type")

        if metadata_marks_promo(block):
            saw_promo_content = True
            cursor += 1
            consumed += 1
            continue

        if kind == "list" and list_is_story_promo(block, other_titles, source):
            return cursor + 1

        if kind == "image" and (recirc or utility):
            saw_promo_content = True
            cursor += 1
            consumed += 1
            continue

        if headline_block(block, other_titles):
            headlines += 1
            saw_promo_content = True
            cursor += 1
            consumed += 1
            continue

        if kind in {"paragraph", "quote"} and sentence_like(block.get("text")):
            break

        if utility and kind in {"paragraph", "heading"} and word_count(block.get("text")) <= 30:
            saw_promo_content = True
            cursor += 1
            consumed += 1
            continue

        break

    if headlines >= 2 or (utility and saw_promo_content):
        return cursor
    return None


def rebuild_story_text(story: dict[str, Any], blocks: list[dict[str, Any]]) -> None:
    paragraphs: list[str] = []
    for block in blocks:
        kind = block.get("type")
        if kind in {"paragraph", "quote"} and block.get("text"):
            paragraphs.append(str(block["text"]).strip())
        elif kind == "list":
            paragraphs.extend(text for item in block.get("items", []) if (text := item_text(item)))
    story["content_blocks"] = blocks
    story["paragraphs"] = paragraphs
    story["content"] = "\n\n".join(paragraphs)
    story["word_count"] = sum(word_count(paragraph) for paragraph in paragraphs)
    story["recirculation_cleaned"] = True


def prune_story(story: dict[str, Any], all_stories: list[dict[str, Any]]) -> bool:
    blocks = story.get("content_blocks") if isinstance(story.get("content_blocks"), list) else []
    if not blocks:
        return False

    current_id = str(story.get("id") or "")
    current_title = text_key(story.get("title"))
    source = str(story.get("source") or "")
    other_titles = {
        key
        for candidate in all_stories
        if str(candidate.get("id") or "") != current_id
        for key in [text_key(candidate.get("title"))]
        if key and key != current_title
    }

    changed = False
    cleaned: list[dict[str, Any]] = []
    for block in blocks:
        if metadata_marks_promo(block):
            changed = True
            continue
        if list_is_story_promo(block, other_titles, source):
            changed = True
            if cleaned and cleaned[-1].get("type") in {"heading", "paragraph"} and (
                is_recirculation_label(cleaned[-1].get("text")) or is_utility_label(cleaned[-1].get("text"))
            ):
                cleaned.pop()
            continue
        cleaned.append(block)

    final: list[dict[str, Any]] = []
    index = 0
    while index < len(cleaned):
        end = skip_labelled_module(cleaned, index, other_titles, source)
        if end is not None and end > index + 1:
            changed = True
            index = end
            continue
        final.append(cleaned[index])
        index += 1

    if not changed:
        return False

    rebuild_story_text(story, final)
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
