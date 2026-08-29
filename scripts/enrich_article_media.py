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
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup, Tag

from fetch_news import clean_text, fetch_html

ROOT = Path(__file__).resolve().parents[1]
NEWS_PATH = ROOT / "data" / "news.json"
MEDIA_SCHEMA = 1
MAX_PER_RUN = max(8, int(os.getenv("MEDIA_MAX_PER_RUN", "36")))
RECENT_HOURS = max(24, int(os.getenv("MEDIA_RECENT_HOURS", "120")))
WORKERS = max(2, min(8, int(os.getenv("MEDIA_WORKERS", "6"))))
CBC_ID = re.compile(r"(?<!\d)([19]\.\d{5,})(?!\d)")
MARKDOWN_LINK = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", re.I)
MEDIA_CUE = re.compile(r"\b(?:listen|watch|video|audio)\b", re.I)
DIRECT_AUDIO = (".mp3", ".m4a", ".aac", ".ogg", ".oga", ".wav")
DIRECT_VIDEO = (".mp4", ".m4v", ".webm", ".ogv")
SAFE_EMBED_HOSTS = (
    "youtube.com",
    "www.youtube.com",
    "youtube-nocookie.com",
    "www.youtube-nocookie.com",
    "player.vimeo.com",
    "cbc.ca",
    "www.cbc.ca",
    "player.cbc.ca",
    "gem.cbc.ca",
)
CBC_HEADERS = {
    "User-Agent": "LondonNews/1.0 (+https://myplexscripts.github.io/news/)",
    "Accept": "text/plain",
    "X-Retain-Links": "all",
    "X-Retain-Images": "all",
    "X-Retain-Media": "all",
    "X-With-Images-Summary": "all",
}


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


def text_key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", clean_text(str(value or "")).lower()).strip()


def safe_http_url(value: Any, base_url: str = "") -> str:
    raw = html.unescape(str(value or "")).strip()
    if not raw or raw.startswith(("javascript:", "data:", "blob:")):
        return ""
    resolved = urljoin(base_url, raw)
    parsed = urlparse(resolved)
    return resolved if parsed.scheme in {"http", "https"} else ""


def classify_media_url(url: str) -> str:
    path = urlparse(url).path.lower()
    if path.endswith(DIRECT_AUDIO):
        return "audio"
    if path.endswith(DIRECT_VIDEO):
        return "video"
    return ""


def safe_embed_url(url: str) -> str:
    parsed = urlparse(url)
    host = parsed.netloc.lower().split(":", 1)[0]
    if host in SAFE_EMBED_HOSTS or any(host.endswith(f".{allowed}") for allowed in SAFE_EMBED_HOSTS):
        return url
    return ""


def media_key(block: dict[str, Any]) -> str:
    return f"{block.get('media_type', '')}:{str(block.get('url') or '').split('#', 1)[0]}"


def media_block(url: str, title: str = "", poster: str = "", media_type: str = "") -> dict[str, Any] | None:
    safe = safe_http_url(url)
    if not safe:
        return None
    kind = media_type or classify_media_url(safe)
    if kind in {"audio", "video"}:
        block: dict[str, Any] = {
            "type": "media",
            "media_type": kind,
            "url": safe,
            "title": clean_text(title, 180),
        }
        if kind == "video" and poster:
            poster_url = safe_http_url(poster)
            if poster_url:
                block["poster"] = poster_url
        return block
    embed = safe_embed_url(safe)
    if embed:
        return {
            "type": "media",
            "media_type": "embed",
            "url": embed,
            "title": clean_text(title, 180) or "Embedded media",
        }
    if MEDIA_CUE.search(title or ""):
        return {
            "type": "media",
            "media_type": "link",
            "url": safe,
            "title": clean_text(title, 180) or "Open media at source",
        }
    return None


def node_media(node: Tag, base_url: str) -> dict[str, Any] | None:
    name = node.name.lower()
    if name in {"audio", "video"}:
        raw_url = node.get("src")
        if not raw_url:
            source = node.find("source", src=True)
            raw_url = source.get("src") if isinstance(source, Tag) else ""
        url = safe_http_url(raw_url, base_url)
        if not url:
            return None
        title = clean_text(node.get("aria-label") or node.get("title") or "")
        poster = safe_http_url(node.get("poster"), base_url) if name == "video" else ""
        return media_block(url, title, poster, name)

    if name == "iframe":
        url = safe_http_url(node.get("src"), base_url)
        if not url:
            return None
        embed = safe_embed_url(url)
        if not embed:
            return None
        return media_block(embed, clean_text(node.get("title") or "Embedded media"), media_type="embed")

    if name == "a":
        url = safe_http_url(node.get("href"), base_url)
        title = clean_text(node.get_text(" ", strip=True) or node.get("title") or "")
        if not url:
            return None
        kind = classify_media_url(url)
        if kind or MEDIA_CUE.search(title):
            return media_block(url, title, media_type=kind)
    return None


def nearest_preceding_text(node: Tag) -> str:
    for prior in node.find_all_previous(["p", "h2", "h3", "h4"], limit=8):
        if not isinstance(prior, Tag):
            continue
        text = clean_text(prior.get_text(" ", strip=True), 240)
        if len(text) >= 12:
            return text
    return ""


def extract_dom_media(raw: str, final_url: str) -> list[tuple[str, dict[str, Any]]]:
    soup = BeautifulSoup(raw, "html.parser")
    found: list[tuple[str, dict[str, Any]]] = []
    seen: set[str] = set()
    for node in soup.find_all(["audio", "video", "iframe", "a"]):
        if not isinstance(node, Tag):
            continue
        block = node_media(node, final_url)
        if not block:
            continue
        key = media_key(block)
        if key in seen:
            continue
        seen.add(key)
        found.append((nearest_preceding_text(node), block))
    return found[:8]


def cbc_story_id(url: str) -> str:
    matches = CBC_ID.findall(urlparse(str(url or "")).path)
    return matches[-1] if matches else ""


def extract_cbc_media(story: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    story_id = cbc_story_id(story.get("url", ""))
    if not story_id:
        return []
    reader_url = f"https://r.jina.ai/http://www.cbc.ca/lite/story/{story_id}"
    try:
        response = requests.get(reader_url, headers=CBC_HEADERS, timeout=(4, 24))
        response.raise_for_status()
    except Exception:
        return []
    if len(response.text) < 500:
        return []

    found: list[tuple[str, dict[str, Any]]] = []
    seen: set[str] = set()
    cue = ""
    lines = response.text.splitlines()
    for line in lines:
        stripped = line.strip()
        plain = re.sub(r"[*_`#>]", "", stripped).strip()
        if MEDIA_CUE.search(plain) and len(plain) <= 260:
            cue = clean_text(re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", plain), 240)
        for label, raw_url in MARKDOWN_LINK.findall(stripped):
            url = safe_http_url(raw_url)
            title = clean_text(label, 180)
            kind = classify_media_url(url)
            if not kind and not MEDIA_CUE.search(title) and not cue:
                continue
            block = media_block(url, cue or title, media_type=kind)
            if not block:
                continue
            key = media_key(block)
            if key in seen:
                continue
            seen.add(key)
            found.append((cue, block))
            cue = ""
    return found[:6]


def block_text(block: dict[str, Any]) -> str:
    if block.get("type") in {"paragraph", "heading", "quote"}:
        return clean_text(block.get("text"))
    return ""


def match_anchor(blocks: list[dict[str, Any]], anchor: str) -> int | None:
    key = text_key(anchor)
    if not key:
        return None
    best_index: int | None = None
    best_score = 0.0
    anchor_words = set(key.split())
    for index, block in enumerate(blocks):
        candidate = text_key(block_text(block))
        if not candidate:
            continue
        if candidate == key or candidate in key or key in candidate:
            return index
        words = set(candidate.split())
        if not words:
            continue
        overlap = len(anchor_words & words) / max(1, min(len(anchor_words), len(words)))
        if overlap > best_score:
            best_score = overlap
            best_index = index
    return best_index if best_score >= 0.68 else None


def merge_media(blocks: list[dict[str, Any]], media: list[tuple[str, dict[str, Any]]]) -> tuple[list[dict[str, Any]], int]:
    if not media:
        return blocks, 0
    result = list(blocks)
    existing = {media_key(block) for block in result if block.get("type") == "media"}
    inserted = 0
    offset = 0
    for anchor, block in media:
        key = media_key(block)
        if key in existing:
            continue
        index = match_anchor(result, anchor)
        if index is None:
            continue
        result.insert(index + 1 + offset, block)
        offset += 1
        inserted += 1
        existing.add(key)
    return result, inserted


def process_story(story: dict[str, Any]) -> tuple[list[tuple[str, dict[str, Any]]], str]:
    source = clean_text(story.get("source", ""))
    if source == "CBC News London":
        media = extract_cbc_media(story)
        if media:
            return media, "cbc:jina-media-v1"
    url = clean_text(story.get("url", ""))
    if not url:
        return [], "dom:no-url"
    try:
        raw, final_url = fetch_html(url)
    except Exception as exc:
        return [], f"dom:{type(exc).__name__}"
    return extract_dom_media(raw, final_url), "dom:media-v1"


def story_needs_work(story: dict[str, Any], now: datetime) -> bool:
    if not isinstance(story, dict) or not story.get("url") or not story.get("title"):
        return False
    if story.get("content_status") not in {"full", "partial"}:
        return False
    if int(story.get("media_schema") or 0) >= MEDIA_SCHEMA:
        return False
    attempted = parse_datetime(story.get("media_attempted_at"))
    return not attempted or now - attempted >= timedelta(hours=6)


def priority(story: dict[str, Any], now: datetime) -> tuple[int, float]:
    published = parse_datetime(story.get("published"))
    age_hours = (now - published).total_seconds() / 3600 if published else 99999
    return (1 if age_hours <= RECENT_HOURS else 0, -age_hours)


def main() -> int:
    if not NEWS_PATH.exists():
        print("No data/news.json found", file=sys.stderr)
        return 1
    payload = json.loads(NEWS_PATH.read_text(encoding="utf-8"))
    stories = payload.get("stories") if isinstance(payload.get("stories"), list) else []
    now = utc_now()
    targets = [story for story in stories if story_needs_work(story, now)]
    targets.sort(key=lambda story: priority(story, now), reverse=True)
    targets = targets[:MAX_PER_RUN]
    if not targets:
        print("Article media already current")
        return 0

    by_id = {str(story.get("id") or ""): story for story in targets}
    inserted_total = 0
    attempted = 0
    with ThreadPoolExecutor(max_workers=WORKERS) as executor:
        futures = {executor.submit(process_story, story): str(story.get("id") or "") for story in targets}
        for future in as_completed(futures):
            story = by_id[futures[future]]
            attempted += 1
            story["media_attempted_at"] = now.isoformat()
            try:
                media, method = future.result()
            except Exception as exc:
                story["media_method"] = f"error:{type(exc).__name__}"
                continue
            blocks = story.get("content_blocks") if isinstance(story.get("content_blocks"), list) else []
            merged, inserted = merge_media(blocks, media)
            if inserted:
                story["content_blocks"] = merged
                inserted_total += inserted
            story["media_schema"] = MEDIA_SCHEMA
            story["media_method"] = method
            story["media_blocks"] = sum(1 for block in merged if block.get("type") == "media")
            story["media_enriched_at"] = utc_now().isoformat()

    payload["media_schema"] = MEDIA_SCHEMA
    payload["media_enriched_at"] = utc_now().isoformat()
    NEWS_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Article media: {inserted_total} blocks inserted across {attempted} attempted stories")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
