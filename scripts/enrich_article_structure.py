from __future__ import annotations

import html
import json
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from fetch_news import (
    clean_text,
    extract_dom_blocks,
    fetch_html,
    sanitize_content_blocks,
    text_from_blocks,
)

ROOT = Path(__file__).resolve().parents[1]
NEWS_PATH = ROOT / "data" / "news.json"
STRUCTURE_SCHEMA = 2
MAX_PER_RUN = max(8, int(os.getenv("STRUCTURE_MAX_PER_RUN", "36")))
RECENT_HOURS = max(24, int(os.getenv("STRUCTURE_RECENT_HOURS", "120")))
WORKERS = max(2, min(8, int(os.getenv("STRUCTURE_WORKERS", "6"))))
MIN_WORDS = 70
CBC_ID = re.compile(r"(?<!\d)([19]\.\d{5,})(?!\d)")
MARKDOWN_IMAGE = re.compile(r"!\[([^\]]*)\]\((https?://[^)\s]+)(?:\s+['\"][^'\"]*['\"])?\)", re.I)
MARKDOWN_HEADING = re.compile(r"^\s{0,3}(#{1,6})\s+(.+?)\s*#*\s*$")
MARKDOWN_UL = re.compile(r"^\s{0,3}[-*+]\s+(.+)$")
MARKDOWN_OL = re.compile(r"^\s{0,3}\d+[.)]\s+(.+)$")
MARKDOWN_QUOTE = re.compile(r"^\s{0,3}>\s?(.*)$")

CBC_HEADERS = {
    "User-Agent": "LondonNews/1.0 (+https://myplexscripts.github.io/news/)",
    "Accept": "text/plain",
    "X-Retain-Links": "text",
    "X-Retain-Images": "all",
    "X-Retain-Media": "none",
    "X-With-Images-Summary": "all",
}

BOILERPLATE = (
    "more from cbc",
    "more stories like this",
    "read more",
    "sign up",
    "subscribe",
    "copyright cbc",
    "all rights reserved",
    "add cbc news as a preferred source",
    "download the cbc news app",
    "go to cbc.ca",
    "cbc news homepage",
    "top stories",
    "about cbc",
    "contact cbc",
    "accessibility",
    "report an error",
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def parse_datetime(value: Any) -> datetime | None:
    raw = str(value or "").strip().replace("Z", "+00:00")
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except Exception:
        return None


def words(value: str) -> int:
    return len(re.findall(r"\b\w+[’'-]?\w*\b", str(value or "")))


def block_word_count(blocks: list[dict[str, Any]]) -> int:
    count = 0
    for block in blocks:
        kind = block.get("type")
        if kind in {"paragraph", "heading", "quote"}:
            count += words(block.get("text", ""))
        elif kind == "list":
            count += sum(words(item) for item in block.get("items", []) if isinstance(item, str))
    return count


def richness(blocks: list[dict[str, Any]]) -> tuple[int, int, int, int]:
    headings = sum(1 for block in blocks if block.get("type") == "heading" and block.get("text"))
    images = sum(1 for block in blocks if block.get("type") == "image" and block.get("url"))
    quotes = sum(1 for block in blocks if block.get("type") == "quote" and block.get("text"))
    lists = sum(1 for block in blocks if block.get("type") == "list" and block.get("items"))
    return headings, images, quotes, lists


def has_rich_structure(blocks: list[dict[str, Any]]) -> bool:
    headings, images, quotes, lists = richness(blocks)
    return headings > 0 or images > 0 or quotes > 0 or lists > 0


def clean_markdown_text(value: str) -> str:
    text = html.unescape(str(value or ""))
    text = re.sub(r"!\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = text.replace("**", "").replace("__", "").replace("`", "")
    text = re.sub(r"(?<!\w)[*_](.+?)[*_](?!\w)", r"\1", text)
    return clean_text(text)


def text_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", clean_markdown_text(value).lower()).strip()


def near_duplicate(left: str, right: str) -> bool:
    a, b = text_key(left), text_key(right)
    if not a or not b:
        return False
    if a == b:
        return True
    shorter, longer = (a, b) if len(a) <= len(b) else (b, a)
    return len(shorter) >= 34 and longer.startswith(shorter) and len(shorter) / len(longer) >= 0.72


def is_boilerplate(value: str, title: str = "") -> bool:
    text = clean_markdown_text(value)
    key = text.lower()
    if not text:
        return True
    if title and near_duplicate(text, title):
        return True
    return any(marker in key for marker in BOILERPLATE)


def normalize_image_key(url: str) -> str:
    try:
        parsed = urlparse(url)
        return f"{parsed.netloc.lower()}{parsed.path.lower()}".rstrip("/")
    except Exception:
        return str(url or "").split("?", 1)[0].lower().rstrip("/")


def cbc_story_id(url: str) -> str:
    matches = CBC_ID.findall(urlparse(str(url or "")).path)
    return matches[-1] if matches else ""


def append_text_block(
    blocks: list[dict[str, Any]],
    kind: str,
    raw_text: str,
    title: str,
    seen_text: list[str],
    level: int | None = None,
) -> None:
    text = clean_markdown_text(raw_text)
    min_len = 4 if kind == "heading" else 12
    if len(text) < min_len or is_boilerplate(text, title):
        return
    if any(near_duplicate(text, prior) for prior in seen_text[-18:]):
        return
    seen_text.append(text)
    block: dict[str, Any] = {"type": kind, "text": text}
    if kind == "heading":
        block["level"] = 3 if level == 3 else 2
    blocks.append(block)


def parse_cbc_markdown(raw: str, title: str, hero_url: str = "") -> list[dict[str, Any]]:
    marker = re.search(r"^Markdown Content:\s*$", raw, flags=re.I | re.M)
    body = raw[marker.end():] if marker else raw
    blocks: list[dict[str, Any]] = []
    seen_text: list[str] = []
    seen_images: set[str] = set()
    hero_key = normalize_image_key(hero_url)
    pending_image_index: int | None = None

    lines = body.splitlines()
    index = 0
    paragraph_lines: list[str] = []

    def flush_paragraph() -> None:
        nonlocal paragraph_lines
        if not paragraph_lines:
            return
        text = " ".join(line.strip() for line in paragraph_lines if line.strip())
        paragraph_lines = []
        append_text_block(blocks, "paragraph", text, title, seen_text)

    while index < len(lines):
        line = lines[index].rstrip()
        stripped = line.strip()
        if not stripped:
            flush_paragraph()
            index += 1
            continue

        heading = MARKDOWN_HEADING.match(stripped)
        if heading:
            flush_paragraph()
            level = len(heading.group(1))
            append_text_block(blocks, "heading", heading.group(2), title, seen_text, level=level)
            pending_image_index = None
            index += 1
            continue

        image_matches = list(MARKDOWN_IMAGE.finditer(stripped))
        if image_matches and clean_markdown_text(stripped) in {clean_markdown_text(m.group(1)) for m in image_matches}:
            flush_paragraph()
            for match in image_matches:
                alt = clean_markdown_text(match.group(1))
                url = html.unescape(match.group(2).strip())
                key = normalize_image_key(url)
                if not key or key == hero_key or key in seen_images:
                    continue
                if not url.lower().startswith(("http://", "https://")):
                    continue
                seen_images.add(key)
                blocks.append({"type": "image", "url": url, "alt": alt, "caption": ""})
                pending_image_index = len(blocks) - 1
            index += 1
            continue

        caption_match = re.match(r"^(?:Caption|Photo caption)\s*:\s*(.+)$", stripped, flags=re.I)
        if caption_match:
            flush_paragraph()
            caption = clean_markdown_text(caption_match.group(1))
            if pending_image_index is not None and 0 <= pending_image_index < len(blocks) and caption:
                blocks[pending_image_index]["caption"] = caption
            index += 1
            continue

        quote = MARKDOWN_QUOTE.match(stripped)
        if quote:
            flush_paragraph()
            quote_lines: list[str] = []
            while index < len(lines):
                qmatch = MARKDOWN_QUOTE.match(lines[index].strip())
                if not qmatch:
                    break
                quote_lines.append(qmatch.group(1))
                index += 1
            append_text_block(blocks, "quote", " ".join(quote_lines), title, seen_text)
            pending_image_index = None
            continue

        ul = MARKDOWN_UL.match(stripped)
        ol = MARKDOWN_OL.match(stripped)
        if ul or ol:
            flush_paragraph()
            ordered = bool(ol)
            items: list[str] = []
            while index < len(lines):
                current = lines[index].strip()
                match = MARKDOWN_OL.match(current) if ordered else MARKDOWN_UL.match(current)
                if not match:
                    break
                item = clean_markdown_text(match.group(1))
                if len(item) >= 2 and not is_boilerplate(item, title):
                    items.append(item)
                index += 1
            if items:
                joined = " ".join(items)
                if not any(near_duplicate(joined, prior) for prior in seen_text[-18:]):
                    seen_text.append(joined)
                    blocks.append({"type": "list", "ordered": ordered, "items": items})
            pending_image_index = None
            continue

        if stripped.startswith(("---", "___")) and len(stripped.replace("-", "").replace("_", "")) == 0:
            flush_paragraph()
            index += 1
            continue

        paragraph_lines.append(stripped)
        pending_image_index = None
        index += 1

    flush_paragraph()

    first_prose = next((i for i, block in enumerate(blocks) if block.get("type") in {"paragraph", "quote"} and words(block.get("text", "")) >= 12), 0)
    if first_prose > 1:
        start = first_prose - 1 if blocks[first_prose - 1].get("type") == "heading" else first_prose
        blocks = blocks[start:]

    return blocks


def fetch_cbc_blocks(story: dict[str, Any]) -> tuple[list[dict[str, Any]], str]:
    story_id = cbc_story_id(story.get("url", ""))
    if not story_id:
        return [], "cbc:no-id"
    reader_url = f"https://r.jina.ai/http://www.cbc.ca/lite/story/{story_id}"
    try:
        response = requests.get(reader_url, headers=CBC_HEADERS, timeout=(4, 24))
        response.raise_for_status()
    except Exception as exc:
        return [], f"cbc:{type(exc).__name__}"
    if len(response.text) < 500:
        return [], "cbc:short-response"
    blocks = parse_cbc_markdown(response.text, clean_text(story.get("title", "")), clean_text(story.get("image", "")))
    return blocks, "cbc:jina-lite-structured"


def fetch_dom_structure(story: dict[str, Any]) -> tuple[list[dict[str, Any]], str]:
    url = clean_text(story.get("url", ""))
    if not url:
        return [], "dom:no-url"
    try:
        raw, final_url = fetch_html(url)
    except Exception as exc:
        return [], f"dom:{type(exc).__name__}"
    soup = BeautifulSoup(raw, "html.parser")
    title = clean_text(story.get("title", ""))
    lead_image = clean_text(story.get("image", ""))
    blocks, _stats, method = extract_dom_blocks(soup, final_url, clean_text(story.get("source", "")), title, lead_image)
    blocks = sanitize_content_blocks(blocks, clean_text(story.get("source", "")), title, lead_image)
    return blocks, method


def body_coverage_ok(story: dict[str, Any], blocks: list[dict[str, Any]]) -> bool:
    extracted_words = block_word_count(blocks)
    if extracted_words < MIN_WORDS:
        return False
    existing_words = int(story.get("word_count") or 0)
    if existing_words <= 0:
        existing_words = words(story.get("content", ""))
    if existing_words <= 0:
        return True
    return extracted_words >= max(MIN_WORDS, int(existing_words * 0.72))


def preserve_story_metadata(story: dict[str, Any], blocks: list[dict[str, Any]], method: str) -> bool:
    if not body_coverage_ok(story, blocks):
        return False
    paragraphs, text = text_from_blocks(blocks)
    if not paragraphs or words(text) < MIN_WORDS:
        return False
    old_blocks = story.get("content_blocks") if isinstance(story.get("content_blocks"), list) else []
    if old_blocks == blocks:
        story["structure_schema"] = STRUCTURE_SCHEMA
        story["structure_method"] = method
        story["structured_at"] = utc_now().isoformat()
        return True

    story["content_blocks"] = blocks
    story["paragraphs"] = paragraphs
    story["content"] = text
    story["word_count"] = words(text)
    story["content_status"] = "full"
    story["structure_schema"] = STRUCTURE_SCHEMA
    story["structure_method"] = method
    story["structured_at"] = utc_now().isoformat()
    story["structure_richness"] = {
        "headings": richness(blocks)[0],
        "inline_images": richness(blocks)[1],
        "quotes": richness(blocks)[2],
        "lists": richness(blocks)[3],
    }
    return True


def story_needs_work(story: dict[str, Any], now: datetime) -> bool:
    if not isinstance(story, dict) or not story.get("url") or not story.get("title"):
        return False
    if story.get("content_status") not in {"full", "partial"}:
        return False
    if int(story.get("structure_schema") or 0) >= STRUCTURE_SCHEMA:
        return False
    attempted = parse_datetime(story.get("structure_attempted_at"))
    if attempted and now - attempted < timedelta(hours=6):
        return False
    return True


def priority(story: dict[str, Any], now: datetime) -> tuple[int, float, int]:
    published = parse_datetime(story.get("published"))
    age_hours = (now - published).total_seconds() / 3600 if published else 99999
    recent = 1 if age_hours <= RECENT_HOURS else 0
    blocks = story.get("content_blocks") if isinstance(story.get("content_blocks"), list) else []
    plain = 1 if not has_rich_structure(blocks) else 0
    return recent, -age_hours, plain


def process_story(story: dict[str, Any]) -> tuple[str, list[dict[str, Any]], str]:
    source = clean_text(story.get("source", ""))
    if source == "CBC News London":
        blocks, method = fetch_cbc_blocks(story)
        if not body_coverage_ok(story, blocks):
            dom_blocks, dom_method = fetch_dom_structure(story)
            if body_coverage_ok(story, dom_blocks):
                return str(story.get("id", "")), dom_blocks, dom_method
        return str(story.get("id", "")), blocks, method
    blocks, method = fetch_dom_structure(story)
    return str(story.get("id", "")), blocks, method


def main() -> int:
    if not NEWS_PATH.exists():
        print("No data/news.json found", file=sys.stderr)
        return 1
    payload = json.loads(NEWS_PATH.read_text(encoding="utf-8"))
    stories = payload.get("stories") if isinstance(payload.get("stories"), list) else []
    if not stories:
        print("No stories to enrich")
        return 0

    now = utc_now()
    targets = [story for story in stories if story_needs_work(story, now)]
    targets.sort(key=lambda story: priority(story, now), reverse=True)
    targets = targets[:MAX_PER_RUN]
    if not targets:
        print("Article structure already current")
        return 0

    by_id = {str(story.get("id", "")): story for story in targets}
    accepted = 0
    rich = 0
    failed = 0

    with ThreadPoolExecutor(max_workers=WORKERS) as executor:
        futures = {executor.submit(process_story, story): str(story.get("id", "")) for story in targets}
        for future in as_completed(futures):
            story_id = futures[future]
            story = by_id[story_id]
            story["structure_attempted_at"] = now.isoformat()
            try:
                _, blocks, method = future.result()
            except Exception as exc:
                story["structure_status"] = "failed"
                story["structure_method"] = f"error:{type(exc).__name__}"
                failed += 1
                continue

            if preserve_story_metadata(story, blocks, method):
                story["structure_status"] = "enriched" if has_rich_structure(blocks) else "plain-source"
                accepted += 1
                if has_rich_structure(blocks):
                    rich += 1
            else:
                story["structure_status"] = "failed"
                story["structure_method"] = method
                failed += 1

    payload["structure_schema"] = STRUCTURE_SCHEMA
    payload["structure_enriched_at"] = utc_now().isoformat()
    NEWS_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Article structure: {accepted} accepted, {rich} rich, {failed} deferred, {len(targets)} attempted")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
