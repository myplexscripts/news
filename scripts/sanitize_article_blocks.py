from __future__ import annotations

"""Final source-agnostic article guard before refreshed data is published."""

import ast
import html
import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
NEWS_PATH = ROOT / "data" / "news.json"
SANITIZE_SCHEMA = 6

JUNK_TEXT_MARKERS = (
    "open full embed in new tab loading external pages",
    "may require significantly more data usage than loading cbc lite story pages",
    "report an editorial error",
    "report a technical issue",
    "editorial code of conduct",
    "follow related authors and topics",
    "interact with the globe",
    "authors and topics you follow will be added to your personal news feed",
    "you must be logged in to follow",
    "postmedia is committed to maintaining a lively but civil forum for discussion",
    "story continues below advertisement",
    "get daily national news",
    "get daily canada news delivered to your inbox",
    "never miss the day's top stories",
    "never miss the day’s top stories",
    "a division of corus entertainment inc",
)

SHARE_MARKERS = (
    "share this story",
    "copy link email x reddit pinterest linkedin tumblr",
    "copy link email facebook x reddit pinterest linkedin tumblr",
    "share on x",
    "share on linkedin",
    "share on reddit",
    "share on whatsapp",
    "share on bluesky",
    "share on threads",
)

SHARE_EXACT_MARKERS = {
    "email",
    "copy link",
    "facebook",
    "x",
    "reddit",
    "linkedin",
    "whatsapp",
    "bluesky",
    "threads",
}

LOCATION_SELECTOR_PREFIX_RE = re.compile(r"^(?:state|country|province|region|territory)\b", re.I)
AUTHOR_IMAGE_TEXT_RE = re.compile(
    r"\b(?:author|byline|columnist|correspondent|headshot|journalist|portrait|profile|reporter)\b",
    re.I,
)
RAW_MEDIA_LABEL_RE = re.compile(r"^(?:image|photo)\s*\|\s*", re.I)
RAW_CAPTION_RE = re.compile(r"^(?:caption|photo caption)\s*:\s*(.+)$", re.I)
PUBLISHER_META_RE = re.compile(
    r"^(?:updated|posted|published|last updated)(?:\s+[a-z .'-]+)?\s*(?:\||:)",
    re.I,
)
LOCATION_SELECTOR_MARKERS = (
    "alabama",
    "alaska",
    "arizona",
    "california",
    "florida",
    "new york",
    "north carolina",
    "texas",
    "washington",
    "wisconsin",
    "wyoming",
    "canada",
    "mexico",
    "afghanistan",
    "albania",
    "algeria",
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


def markdown_inline(value: str) -> tuple[str, str]:
    raw = str(value or "").strip()
    if not raw:
        return "", ""

    rendered = html.escape(raw, quote=False)
    rendered = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", rendered)
    rendered = re.sub(r"__(.+?)__", r"<strong>\1</strong>", rendered)
    rendered = re.sub(r"(?<!\*)\*([^*\n]+?)\*(?!\*)", r"<em>\1</em>", rendered)
    rendered = re.sub(r"(?<!\w)_([^_\n]+?)_(?!\w)", r"<em>\1</em>", rendered)

    plain = re.sub(r"\*\*(.+?)\*\*", r"\1", raw)
    plain = re.sub(r"__(.+?)__", r"\1", plain)
    plain = re.sub(r"(?<!\*)\*([^*\n]+?)\*(?!\*)", r"\1", plain)
    plain = re.sub(r"(?<!\w)_([^_\n]+?)_(?!\w)", r"\1", plain)
    return plain.strip(), rendered.strip()


def normalized_key(value: Any) -> str:
    return re.sub(r"\s+", " ", item_text(value).lower()).strip()


def looks_like_location_selector_dump(value: Any) -> bool:
    text = item_text(value)
    key = normalized_key(text)
    if len(key) < 260 or len(re.findall(r"\b\w+\b", key)) < 40:
        return False
    if not LOCATION_SELECTOR_PREFIX_RE.search(key):
        return False
    marker_count = sum(1 for marker in LOCATION_SELECTOR_MARKERS if marker in key)
    return marker_count >= 5


def is_junk_text(value: Any) -> bool:
    key = normalized_key(value)
    return bool(key) and (
        any(marker in key for marker in JUNK_TEXT_MARKERS)
        or looks_like_location_selector_dump(value)
    )


def is_share_text(value: Any) -> bool:
    key = normalized_key(value)
    return bool(key) and (key in SHARE_EXACT_MARKERS or any(marker in key for marker in SHARE_MARKERS))


def is_author_image_text(value: Any) -> bool:
    key = normalized_key(value)
    return bool(key and AUTHOR_IMAGE_TEXT_RE.search(key))


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


def repair_fragmented_paragraphs(blocks: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], bool]:
    repaired: list[dict[str, Any]] = []
    changed = False
    for block in blocks:
        if block.get("type") == "paragraph" and repaired and repaired[-1].get("type") == "paragraph":
            previous = item_text(repaired[-1].get("text"))
            current = item_text(block.get("text"))
            if (
                previous
                and current
                and not re.search(r"[.!?;:\u201d\"']$", previous)
                and current[:1].islower()
            ):
                repaired[-1]["text"] = f"{previous} {current}"
                repaired[-1].pop("html", None)
                changed = True
                continue
        repaired.append(block)
    return repaired, changed


def sanitize_story(story: dict[str, Any]) -> bool:
    blocks = story.get("content_blocks") if isinstance(story.get("content_blocks"), list) else []
    if not blocks:
        return False

    source = str(story.get("source") or "")
    is_cbc = source == "CBC News London"
    story_url = str(story.get("url") or "").strip()
    changed = False
    selector_removed = False
    cleaned: list[dict[str, Any]] = []

    for raw_block in blocks:
        if not isinstance(raw_block, dict):
            changed = True
            continue
        block = dict(raw_block)
        kind = block.get("type")

        if kind == "media":
            media_type = str(block.get("media_type") or "")
            media_url = str(block.get("url") or "").strip()
            title = item_text(block.get("title"))
            if media_type == "link" and story_url and media_url == story_url and title.upper().startswith("LISTEN |"):
                changed = True
                continue
            cleaned.append(block)
            continue

        if kind == "image":
            image_text = " ".join(
                part for part in (
                    item_text(block.get("alt")),
                    item_text(block.get("caption")),
                    item_text(block.get("title")),
                ) if part
            )
            if image_text and (is_junk_text(image_text) or is_share_text(image_text) or is_author_image_text(image_text)):
                changed = True
                selector_removed = selector_removed or looks_like_location_selector_dump(image_text)
                continue
            cleaned.append(block)
            continue

        if kind == "list":
            original_items = block.get("items") if isinstance(block.get("items"), list) else []
            if any(looks_like_location_selector_dump(item) for item in original_items):
                selector_removed = True
            items = normalize_list_items(original_items)
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
            if looks_like_location_selector_dump(text):
                selector_removed = True
                changed = True
                continue
            if not text or is_junk_text(text) or is_share_text(text):
                changed = True
                continue

            if kind == "paragraph" and RAW_MEDIA_LABEL_RE.match(text):
                changed = True
                continue

            if kind == "paragraph":
                caption_match = RAW_CAPTION_RE.match(text)
                if caption_match:
                    caption = item_text(caption_match.group(1))
                    if caption and cleaned and cleaned[-1].get("type") == "image" and not item_text(cleaned[-1].get("caption")):
                        cleaned[-1]["caption"] = caption
                    changed = True
                    continue

            if PUBLISHER_META_RE.match(text) and len(text) <= 280:
                changed = True
                continue

            plain, rendered = markdown_inline(text)
            if plain != text:
                block["text"] = plain
                block["html"] = rendered
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

            cleaned.append(block)
            continue

        cleaned.append(block)

    cleaned, fragments_repaired = repair_fragmented_paragraphs(cleaned)
    changed = changed or fragments_repaired

    paragraphs: list[str] = []
    for block in cleaned:
        kind = block.get("type")
        if kind in {"paragraph", "quote"} and block.get("text"):
            paragraphs.append(str(block["text"]).strip())
        elif kind == "list":
            paragraphs.extend(text for item in block.get("items", []) if (text := item_text(item)))

    if selector_removed:
        story["reader_schema"] = 0
        story.pop("reader_attempted_at", None)
        flags = [str(flag) for flag in story.get("article_hygiene_flags", []) if flag]
        if "form-selector-dump" not in flags:
            flags.append("form-selector-dump")
        story["article_hygiene_flags"] = flags
        story["article_format_state"] = "flat"
        if not paragraphs:
            story["content_status"] = "summary"
            story["content_truncated_reason"] = "publisher-form-chrome"
        elif story.get("content_truncated_reason") == "publisher-form-chrome":
            story.pop("content_truncated_reason", None)

    if changed or story.get("paragraphs") != paragraphs or int(story.get("sanitize_schema") or 0) < SANITIZE_SCHEMA:
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
