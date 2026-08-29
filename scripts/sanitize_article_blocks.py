from __future__ import annotations

import ast
import html
import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
NEWS_PATH = ROOT / "data" / "news.json"
SANITIZE_SCHEMA = 1

JUNK_TEXT_MARKERS = (
    "open full embed in new tab loading external pages",
    "may require significantly more data usage than loading cbc lite story pages",
)

SHARE_MARKERS = (
    "share this story",
    "copy link email x reddit pinterest linkedin tumblr",
    "copy link email facebook x reddit pinterest linkedin tumblr",
)


def item_text(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("text") or "").strip()
    raw = str(value or "").strip()
    if raw.startswith("{") and ("'text':" in raw or '"text":' in raw):
        try:
            parsed = ast.literal_eval(raw)
        except Exception:
            try:
                parsed = json.loads(raw)
            except Exception:
                parsed = None
        if isinstance(parsed, dict):
            return str(parsed.get("text") or "").strip()
    return raw


def clean_outer_markdown(value: str) -> tuple[str, str]:
    text = str(value or "").strip()
    if len(text) >= 2 and text.startswith("_") and text.endswith("_") and not text.startswith("__"):
        inner = text[1:-1].strip()
        return inner, f"<em>{html.escape(inner)}</em>"
    return text, ""


def is_junk_text(value: Any) -> bool:
    key = re.sub(r"\s+", " ", item_text(value).lower()).strip()
    return bool(key) and any(marker in key for marker in JUNK_TEXT_MARKERS)


def is_share_text(value: Any) -> bool:
    key = re.sub(r"\s+", " ", item_text(value).lower()).strip()
    return bool(key) and any(marker in key for marker in SHARE_MARKERS)


def normalize_list_items(items: list[Any]) -> list[Any]:
    normalized: list[Any] = []
    for item in items:
        if isinstance(item, dict):
            text = item_text(item)
            if not text or is_junk_text(text) or is_share_text(text):
                continue
            clone = dict(item)
            clone["text"] = text
            normalized.append(clone)
            continue

        raw = str(item or "").strip()
        parsed: Any = None
        if raw.startswith("{") and ("'text':" in raw or '"text":' in raw):
            try:
                parsed = ast.literal_eval(raw)
            except Exception:
                try:
                    parsed = json.loads(raw)
                except Exception:
                    parsed = None
        if isinstance(parsed, dict):
            text = item_text(parsed)
            if text and not is_junk_text(text) and not is_share_text(text):
                normalized.append({"text": text, **({"html": parsed.get("html")} if parsed.get("html") else {})})
            continue

        text = item_text(raw)
        if text and not is_junk_text(text) and not is_share_text(text):
            normalized.append(text)
    return normalized


def sanitize_story(story: dict[str, Any]) -> bool:
    blocks = story.get("content_blocks") if isinstance(story.get("content_blocks"), list) else []
    if not blocks:
        return False

    source = str(story.get("source") or "")
    is_cbc = source == "CBC News London"
    changed = False
    cleaned: list[dict[str, Any]] = []
    has_media = any(isinstance(block, dict) and block.get("type") == "media" for block in blocks)
    listen_index: int | None = None
    listen_title = ""

    for raw_block in blocks:
        if not isinstance(raw_block, dict):
            changed = True
            continue
        block = dict(raw_block)
        kind = block.get("type")

        if kind == "list":
            items = normalize_list_items(block.get("items") if isinstance(block.get("items"), list) else [])
            if not items:
                changed = True
                continue
            if all(is_share_text(item) for item in items):
                changed = True
                continue
            if items != block.get("items"):
                block["items"] = items
                changed = True
            cleaned.append(block)
            continue

        if kind in {"paragraph", "heading", "quote"}:
            text = item_text(block.get("text"))
            if not text or is_junk_text(text) or is_share_text(text):
                changed = True
                continue

            plain, markdown_html = clean_outer_markdown(text)
            if plain != text:
                block["text"] = plain
                if not block.get("html"):
                    block["html"] = markdown_html
                changed = True
            else:
                block["text"] = text

            upper = plain.upper()
            if is_cbc and (plain.startswith("Nav Nanwa:") or plain.startswith("NV:")) and plain.rstrip().endswith("?"):
                desired = f"<strong>{html.escape(plain)}</strong>"
                if block.get("html") != desired:
                    block["html"] = desired
                    changed = True

            if is_cbc and upper.startswith("LISTEN |"):
                desired = f"<strong><em>{html.escape(plain)}</em></strong>"
                if block.get("html") != desired:
                    block["html"] = desired
                    changed = True
                listen_index = len(cleaned)
                listen_title = plain

            cleaned.append(block)
            continue

        cleaned.append(block)

    if is_cbc and listen_index is not None and not has_media and story.get("url"):
        insert_at = min(len(cleaned), listen_index + 1)
        cleaned.insert(insert_at, {
            "type": "media",
            "media_type": "link",
            "url": str(story["url"]),
            "title": listen_title or "Listen at CBC",
        })
        changed = True

    paragraphs: list[str] = []
    for block in cleaned:
        kind = block.get("type")
        if kind in {"paragraph", "quote"} and block.get("text"):
            paragraphs.append(str(block["text"]).strip())
        elif kind == "list":
            paragraphs.extend(text for item in block.get("items", []) if (text := item_text(item)))

    if changed or story.get("paragraphs") != paragraphs:
        story["content_blocks"] = cleaned
        story["paragraphs"] = paragraphs
        story["content"] = "\n\n".join(paragraphs)
        story["word_count"] = sum(len(re.findall(r"\b\w+[’'-]?\w*\b", paragraph)) for paragraph in paragraphs)
        story["sanitize_schema"] = SANITIZE_SCHEMA
        return True

    story["sanitize_schema"] = SANITIZE_SCHEMA
    return False


def sanitize_payload(payload: dict[str, Any]) -> int:
    stories = payload.get("stories") if isinstance(payload.get("stories"), list) else []
    changed = sum(1 for story in stories if isinstance(story, dict) and sanitize_story(story))
    payload["sanitize_schema"] = SANITIZE_SCHEMA
    return changed


def main() -> int:
    if not NEWS_PATH.exists():
        print("No data/news.json found")
        return 0
    payload = json.loads(NEWS_PATH.read_text(encoding="utf-8"))
    changed = sanitize_payload(payload)
    NEWS_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Article presentation sanitation: {changed} stories corrected")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
