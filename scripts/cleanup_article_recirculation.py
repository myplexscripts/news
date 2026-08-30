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
    "more news",
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
    "follow related authors and topics",
    "interact with the globe",
    "report an editorial error",
    "report a technical issue",
    "editorial code of conduct",
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

TITLE_TOKEN_STOPWORDS = {
    "about",
    "after",
    "amid",
    "from",
    "have",
    "into",
    "london",
    "more",
    "news",
    "over",
    "that",
    "their",
    "this",
    "with",
    "will",
    "your",
}


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


def title_tokens(key: str) -> set[str]:
    return {token for token in key.split() if len(token) >= 4 and token not in TITLE_TOKEN_STOPWORDS}


def build_title_index(stories: list[dict[str, Any]]) -> tuple[set[str], dict[str, set[str]]]:
    titles = {key for story in stories if (key := text_key(story.get("title")))}
    by_token: dict[str, set[str]] = {}
    for title in titles:
        for token in title_tokens(title):
            by_token.setdefault(token, set()).add(title)
    return titles, by_token


def title_match(item: Any, titles: set[str], title_index: dict[str, set[str]], current_title: str = "") -> bool:
    key = text_key(item)
    if len(key) < 18:
        return False
    if key in titles and key != current_title:
        return True

    candidates: set[str] = set()
    for token in title_tokens(key):
        candidates.update(title_index.get(token, ()))

    for title in candidates:
        if title == current_title or len(title) < 18:
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
    return any(name in lower for name in ("free press", "postmedia", "national post", "ctv", "global news", "cbc", "toronto star"))


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


def list_is_story_promo(
    block: dict[str, Any],
    titles: set[str],
    title_index: dict[str, set[str]],
    current_title: str,
    source: str = "",
) -> bool:
    if block.get("type") != "list":
        return False
    items = [text for item in block.get("items", []) if (text := item_text(item))]
    if len(items) < 2:
        return False
    matches = sum(1 for item in items if title_match(item, titles, title_index, current_title))
    if matches >= 2 and matches / len(items) >= 0.67:
        return True
    return looks_like_promoted_headline_run(items, bool(block.get("ordered")), source)


def headline_block(block: dict[str, Any], titles: set[str], title_index: dict[str, set[str]], current_title: str) -> bool:
    if block.get("type") not in {"paragraph", "heading"}:
        return False
    text = str(block.get("text") or "").strip()
    return title_match(text, titles, title_index, current_title) or headline_like(text)


def linked_headline_block(block: dict[str, Any]) -> bool:
    if block.get("type") not in {"heading", "paragraph"}:
        return False
    markup = str(block.get("html") or "").lower()
    return "<a " in markup and "href=" in markup and headline_like(block.get("text"))


def skip_linked_card_run(blocks: list[dict[str, Any]], start: int) -> int | None:
    if start >= len(blocks) or not linked_headline_block(blocks[start]):
        return None

    cursor = start
    headlines = 0
    consumed = 0
    while cursor < len(blocks) and consumed < 18:
        block = blocks[cursor]
        kind = block.get("type")
        if linked_headline_block(block):
            headlines += 1
            cursor += 1
            consumed += 1
            continue
        if kind == "image" and headlines:
            cursor += 1
            consumed += 1
            continue
        if kind == "list" and headlines:
            items = [item_text(item) for item in block.get("items", []) if item_text(item)]
            if items and all(word_count(item) <= 8 for item in items):
                cursor += 1
                consumed += 1
                continue
        break

    return cursor if headlines >= 2 else None


def terminal_cut_index(story: dict[str, Any], blocks: list[dict[str, Any]]) -> int | None:
    source = str(story.get("source") or "").lower()
    for index, block in enumerate(blocks):
        key = text_key(block.get("text"))
        kind = block.get("type")

        if "globe and mail" in source and key in {
            "report an editorial error",
            "report a technical issue",
            "follow related authors and topics",
            "interact with the globe",
        }:
            return index

        if "toronto star" in source and kind == "heading" and key in {"trending", "more news"}:
            return index

        if "national post" in source and key.startswith("postmedia is committed to maintaining a lively but civil forum for discussion"):
            return index

    return None


def skip_labelled_module(
    blocks: list[dict[str, Any]],
    start: int,
    titles: set[str],
    title_index: dict[str, set[str]],
    current_title: str,
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

        if kind == "list" and list_is_story_promo(block, titles, title_index, current_title, source):
            return cursor + 1

        if kind == "image" and (recirc or utility):
            saw_promo_content = True
            cursor += 1
            consumed += 1
            continue

        if headline_block(block, titles, title_index, current_title):
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


def prune_story(story: dict[str, Any], titles: set[str], title_index: dict[str, set[str]]) -> bool:
    blocks = story.get("content_blocks") if isinstance(story.get("content_blocks"), list) else []
    if not blocks:
        return False

    current_title = text_key(story.get("title"))
    source = str(story.get("source") or "")

    changed = False
    cleaned: list[dict[str, Any]] = []
    for block in blocks:
        if metadata_marks_promo(block):
            changed = True
            continue
        if list_is_story_promo(block, titles, title_index, current_title, source):
            changed = True
            if cleaned and cleaned[-1].get("type") in {"heading", "paragraph"} and (
                is_recirculation_label(cleaned[-1].get("text")) or is_utility_label(cleaned[-1].get("text"))
            ):
                cleaned.pop()
            continue
        cleaned.append(block)

    cut = terminal_cut_index(story, cleaned)
    if cut is not None:
        cleaned = cleaned[:cut]
        changed = True

    labelled: list[dict[str, Any]] = []
    index = 0
    while index < len(cleaned):
        end = skip_labelled_module(cleaned, index, titles, title_index, current_title, source)
        if end is not None and end > index + 1:
            changed = True
            index = end
            continue
        labelled.append(cleaned[index])
        index += 1

    final: list[dict[str, Any]] = []
    index = 0
    while index < len(labelled):
        end = skip_linked_card_run(labelled, index)
        if end is not None and end > index:
            changed = True
            index = end
            continue
        final.append(labelled[index])
        index += 1

    if not changed:
        return False

    rebuild_story_text(story, final)
    return True


def clean_payload(payload: dict[str, Any]) -> int:
    stories = payload.get("stories") if isinstance(payload.get("stories"), list) else []
    dict_stories = [story for story in stories if isinstance(story, dict)]
    titles, title_index = build_title_index(dict_stories)
    return sum(1 for story in dict_stories if prune_story(story, titles, title_index))


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
