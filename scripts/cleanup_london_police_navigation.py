from __future__ import annotations

"""Keep London Police Service article bodies inside the actual release boundary.

The LPS Govstack pages place large navigation/category/footer regions close to the
article container. Generic reader passes can serialize those menus as article
lists or paragraphs. This source-scoped cleanup trims only when it can identify a
high-confidence LPS article start, preserves editorial lists/media, and stops at
the media-contact/footer boundary.
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

CASE_NUMBER_RE = re.compile(r"\s+\d{2,4}[-–—]\d{4,}\s*$", re.I)
DATELINE_RE = re.compile(
    r"(?:^|\s)(?:update\s*[-:–—]\s*)?london\s*,?\s*(?:on|ont\.?)\s*\(",
    re.I,
)

NAV_LABELS = {
    "services",
    "careers",
    "community",
    "crime prevention",
    "about",
    "news",
    "general releases",
    "positions",
    "recruiting events",
    "back to news search",
    "subscribe",
    "expand search",
    "make an online report",
    "contact us",
    "resources",
    "sitemap",
    "accessibility",
    "website feedback",
    "privacy policy",
    "alerts",
    "connect with us",
    "made with govstack",
}

END_PREFIXES = (
    "for media inquiries",
    "for media enquiries",
    "media relations officer",
    "media relations unit",
    "contact media relations",
)


def clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def key(value: Any) -> str:
    text = clean(value).lower().replace("’", "'")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9']+", " ", text)).strip()


def word_count(value: Any) -> int:
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


def is_lps_story(story: dict[str, Any]) -> bool:
    source = clean(story.get("source")).lower()
    host = urlparse(clean(story.get("url"))).netloc.lower().split(":", 1)[0]
    return "london police" in source or host == "londonpolice.ca" or host.endswith(".londonpolice.ca")


def title_key(story: dict[str, Any]) -> str:
    title = CASE_NUMBER_RE.sub("", clean(story.get("title"))).strip()
    return key(title)


def heading_matches_title(block: dict[str, Any], story: dict[str, Any]) -> bool:
    if block.get("type") != "heading":
        return False
    heading = key(block_text(block))
    title = title_key(story)
    if len(heading) < 12 or len(title) < 12:
        return False
    if heading == title:
        return True
    shorter, longer = (heading, title) if len(heading) <= len(title) else (title, heading)
    return len(shorter) >= 18 and shorter in longer and len(shorter) / len(longer) >= 0.72


def is_navigation_heading(block: dict[str, Any]) -> bool:
    return block.get("type") == "heading" and key(block_text(block)) in NAV_LABELS


def is_end_marker(value: Any) -> bool:
    text_key = key(value)
    if not text_key:
        return False
    if text_key == "contact us":
        return True
    return any(text_key.startswith(prefix) for prefix in END_PREFIXES)


def find_dateline(value: Any) -> re.Match[str] | None:
    return DATELINE_RE.search(clean(value))


def source_blocks(story: dict[str, Any]) -> list[dict[str, Any]]:
    raw = story.get("content_blocks") if isinstance(story.get("content_blocks"), list) else []
    blocks = [dict(block) for block in raw if isinstance(block, dict)]
    if blocks:
        return blocks

    paragraphs = story.get("paragraphs") if isinstance(story.get("paragraphs"), list) else []
    if not paragraphs:
        content = str(story.get("content") or "")
        paragraphs = [part for part in re.split(r"\n{2,}", content) if clean(part)]
    return [
        {"type": "paragraph", "text": clean(paragraph)}
        for paragraph in paragraphs
        if clean(paragraph)
    ]


def trim_start(blocks: list[dict[str, Any]], story: dict[str, Any]) -> tuple[list[dict[str, Any]], int]:
    start_index: int | None = None
    replacement: dict[str, Any] | None = None

    # Prefer an article-title heading when a reader retained it. The application
    # already renders the story title, so start after this echo rather than keeping
    # a duplicate H2 inside the article body.
    for index, block in enumerate(blocks):
        if heading_matches_title(block, story):
            start_index = index + 1
            break

    # Otherwise anchor on the actual LONDON, ON (...) release dateline. Some reader
    # services collapse the menu and opening paragraph into one text block, so trim
    # within that block when necessary.
    if start_index is None:
        for index, block in enumerate(blocks):
            if block.get("type") not in {"paragraph", "quote"}:
                continue
            text = block_text(block)
            match = find_dateline(text)
            if not match:
                continue
            start_index = index
            if match.start() > 0:
                replacement = {**block, "text": clean(text[match.start():])}
            else:
                # Preserve a short editorial subheading immediately before the
                # dateline, for example "Seeking the public's assistance".
                back = index - 1
                kept = 0
                while back >= 0 and kept < 2:
                    previous = blocks[back]
                    if previous.get("type") != "heading" or is_navigation_heading(previous):
                        break
                    previous_text = block_text(previous)
                    if key(previous_text) in NAV_LABELS or word_count(previous_text) > 16:
                        break
                    start_index = back
                    kept += 1
                    back -= 1
            break

    if start_index is None:
        return blocks, 0

    trimmed = [dict(block) for block in blocks[start_index:]]
    if replacement is not None and trimmed:
        trimmed[0] = replacement
    changes = start_index + (1 if replacement is not None else 0)
    return trimmed, changes


def trim_end(blocks: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    output: list[dict[str, Any]] = []
    removed = 0

    for index, block in enumerate(blocks):
        text = block_text(block)
        if text:
            if is_end_marker(text):
                removed += len(blocks) - index
                break

            lowered = text.lower()
            marker_positions = [
                pos for phrase in ("for media inquiries", "for media enquiries")
                if (pos := lowered.find(phrase)) >= 0
            ]
            if marker_positions and block.get("type") in {"paragraph", "quote"}:
                cut = min(marker_positions)
                before = clean(text[:cut])
                if len(before) >= 25:
                    output.append({**block, "text": before})
                removed += len(blocks) - index
                break

        output.append(block)

    return output, removed


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
    if not is_lps_story(story):
        return False

    blocks = source_blocks(story)
    if not blocks:
        return False

    original_count = len(blocks)
    bounded, removed_before = trim_start(blocks, story)
    if removed_before == 0 and bounded is blocks:
        # No trustworthy article anchor means do not risk trimming a legitimate
        # older story shape merely because it came from LPS.
        return False

    bounded, removed_after = trim_end(bounded)
    if not bounded:
        return False

    removed = removed_before + removed_after
    if removed <= 0:
        return False

    paragraphs = paragraphs_from_blocks(bounded)
    story["content_blocks"] = bounded
    story["paragraphs"] = paragraphs
    story["content"] = "\n\n".join(paragraphs)
    story["word_count"] = sum(word_count(paragraph) for paragraph in paragraphs)
    story["lps_navigation_schema"] = SCHEMA
    story["lps_navigation_removed"] = removed
    story["lps_navigation_original_blocks"] = original_count
    story["lps_navigation_cleaned_at"] = datetime.now(timezone.utc).isoformat()
    return True


def clean_payload(payload: dict[str, Any]) -> int:
    stories = payload.get("stories") if isinstance(payload.get("stories"), list) else []
    changed = sum(1 for story in stories if isinstance(story, dict) and clean_story(story))
    payload["lps_navigation_schema"] = SCHEMA
    payload["lps_navigation_cleaned_at"] = datetime.now(timezone.utc).isoformat()
    payload["lps_navigation_corrected"] = changed
    return changed


def main() -> int:
    if not NEWS_PATH.exists():
        print("No data/news.json found")
        return 0
    payload = json.loads(NEWS_PATH.read_text(encoding="utf-8"))
    changed = clean_payload(payload)
    NEWS_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"London Police navigation cleanup corrected {changed} stories")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
