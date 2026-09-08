from __future__ import annotations

"""Remove Postmedia/London Free Press site navigation from saved article bodies.

Reader/extraction services can serialize the responsive site menu inside the same
container as story prose. This pass is deliberately source-scoped and only strips
high-confidence navigation labels/lists while preserving real editorial lists,
images and media.
"""

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
NEWS_PATH = ROOT / "data" / "news.json"
SCHEMA = 1

NAV_ITEMS = {
    "sections",
    "search",
    "news",
    "sports",
    "opinion",
    "letters",
    "business",
    "arts",
    "life",
    "shopping",
    "newsletters",
    "puzzmo",
    "healthing",
    "driving",
    "epaper",
    "obituaries",
    "classifieds",
    "manage print subscription",
    "manage my account",
    "advice",
    "horoscopes",
    "weather",
    "lives told",
    "tails told",
    "london free press store",
    "diversions",
    "puzzles",
    "comics",
    "vehicle research",
    "reviews",
    "gear guide",
    "ontario farmer",
    "place an obituary",
    "place an in memoriam",
}


def clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def key(value: Any) -> str:
    text = clean(value).lower().replace("’", "'")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9']+", " ", text)).strip()


def words(value: Any) -> int:
    return len(re.findall(r"\b\w+[’'-]?\w*\b", clean(value)))


def item_text(value: Any) -> str:
    if isinstance(value, dict):
        return clean(value.get("text") or value.get("label") or value.get("title"))
    return clean(value)


def block_text(block: dict[str, Any]) -> str:
    if block.get("type") == "list":
        return " ".join(item_text(item) for item in block.get("items", []) if item_text(item))
    for field in ("text", "title", "label", "name", "caption", "alt"):
        if block.get(field):
            return clean(block.get(field))
    return ""


def is_london_free_press(story: dict[str, Any]) -> bool:
    source = clean(story.get("source")).lower()
    host = urlparse(clean(story.get("url"))).netloc.lower().split(":", 1)[0]
    return "free press" in source or host == "lfpress.com" or host.endswith(".lfpress.com")


def is_nav_item(value: Any) -> bool:
    return key(value) in NAV_ITEMS


def is_navigation_list(block: dict[str, Any]) -> bool:
    if block.get("type") != "list":
        return False
    items = [item_text(item) for item in block.get("items", []) if item_text(item)]
    if len(items) < 2:
        return False
    matches = sum(1 for item in items if is_nav_item(item))
    if matches >= 3:
        return True
    return matches >= 2 and matches / len(items) >= 0.60


def substantive_story_prose(block: dict[str, Any]) -> bool:
    if block.get("type") not in {"paragraph", "quote"}:
        return False
    text = block_text(block)
    count = words(text)
    if count < 12 or len(text) < 70:
        return False
    return bool(re.search(r"[.!?][\"'’”)]?$", text)) or count >= 20


def paragraphs_from_blocks(blocks: list[dict[str, Any]]) -> list[str]:
    output: list[str] = []
    for block in blocks:
        kind = block.get("type")
        if kind in {"paragraph", "quote"} and block.get("text"):
            output.append(clean(block.get("text")))
        elif kind == "list":
            output.extend(item_text(item) for item in block.get("items", []) if item_text(item))
    return output


def clean_story(story: dict[str, Any]) -> bool:
    if not is_london_free_press(story):
        return False

    raw = story.get("content_blocks") if isinstance(story.get("content_blocks"), list) else []
    if raw:
        blocks = [dict(block) for block in raw if isinstance(block, dict)]
    else:
        paragraphs = story.get("paragraphs") if isinstance(story.get("paragraphs"), list) else []
        blocks = [
            {"type": "paragraph", "text": clean(paragraph)}
            for paragraph in paragraphs
            if clean(paragraph)
        ]
    if not blocks:
        return False

    out: list[dict[str, Any]] = []
    removed = 0
    nav_run = False
    seen_story_prose = False

    for block in blocks:
        text = block_text(block)

        if substantive_story_prose(block):
            seen_story_prose = True
            nav_run = False
            out.append(block)
            continue

        if is_navigation_list(block):
            nav_run = True
            removed += 1
            continue

        if text and is_nav_item(text):
            nav_run = True
            removed += 1
            continue

        # Once a recognised navigation run starts ahead of the article, discard
        # the surrounding short labels that reader services often split into
        # separate blocks. Genuine photography/media is still retained.
        if nav_run and not seen_story_prose:
            if block.get("type") in {"image", "media"}:
                out.append(block)
                continue
            if block.get("type") in {"heading", "paragraph", "list"} and words(text) <= 18:
                removed += 1
                continue

        out.append(block)

    if removed == 0:
        return False

    paragraphs = paragraphs_from_blocks(out)
    story["content_blocks"] = out
    story["paragraphs"] = paragraphs
    story["content"] = "\n\n".join(paragraphs)
    story["word_count"] = sum(words(paragraph) for paragraph in paragraphs)
    story["postmedia_navigation_schema"] = SCHEMA
    story["postmedia_navigation_removed"] = removed
    story["postmedia_navigation_cleaned_at"] = datetime.now(timezone.utc).isoformat()
    return True


def clean_payload(payload: dict[str, Any]) -> int:
    stories = payload.get("stories") if isinstance(payload.get("stories"), list) else []
    changed = sum(1 for story in stories if isinstance(story, dict) and clean_story(story))
    payload["postmedia_navigation_schema"] = SCHEMA
    payload["postmedia_navigation_cleaned_at"] = datetime.now(timezone.utc).isoformat()
    payload["postmedia_navigation_corrected"] = changed
    return changed


def main() -> int:
    if not NEWS_PATH.exists():
        print("No data/news.json found")
        return 0
    payload = json.loads(NEWS_PATH.read_text(encoding="utf-8"))
    changed = clean_payload(payload)
    NEWS_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Postmedia navigation cleanup corrected {changed} stories")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
