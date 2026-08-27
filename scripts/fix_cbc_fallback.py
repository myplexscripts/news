from __future__ import annotations

import html
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import feedparser
import requests
from bs4 import BeautifulSoup


ROOT = Path(__file__).resolve().parents[1]
NEWS_PATH = ROOT / "data" / "news.json"
CBC_GOOGLE_NEWS_FEED = (
    "https://news.google.com/rss/search?"
    "q=site%3Acbc.ca%2Fnews%2Fcanada%2Flondon%20London%20Ontario%20when%3A3d&"
    "hl=en-CA&gl=CA&ceid=CA%3Aen"
)
USER_AGENT = "LondonNews/1.0 (+https://myplexscripts.github.io/news/)"
CBC_SUFFIX = re.compile(r"\s+-\s+CBC(?: News|\.ca)?\s*$", re.I)


def clean_text(value: Any) -> str:
    raw = html.unescape(str(value or ""))
    if "<" in raw and ">" in raw:
        raw = BeautifulSoup(raw, "html.parser").get_text(" ", strip=True)
    return re.sub(r"\s+", " ", raw).strip()


def google_story_key(value: Any) -> str:
    parsed = urlparse(str(value or ""))
    if "news.google.com" not in parsed.netloc.lower():
        return ""
    path = parsed.path.rstrip("/")
    return path if "/rss/articles/" in path else ""


def load_google_cbc() -> dict[str, dict[str, str]]:
    response = requests.get(
        CBC_GOOGLE_NEWS_FEED,
        headers={"User-Agent": USER_AGENT, "Accept-Language": "en-CA,en;q=0.9"},
        timeout=15,
    )
    response.raise_for_status()
    feed = feedparser.parse(response.content)
    lookup: dict[str, dict[str, str]] = {}

    for entry in feed.entries:
        source_meta = entry.get("source") or {}
        source_title = clean_text(source_meta.get("title")) if isinstance(source_meta, dict) else clean_text(source_meta)
        raw_title = clean_text(entry.get("title"))
        if "cbc" not in source_title.lower() and not CBC_SUFFIX.search(raw_title):
            continue
        title = CBC_SUFFIX.sub("", raw_title).strip()
        key = google_story_key(entry.get("link") or entry.get("guid"))
        if not title or not key:
            continue
        summary = clean_text(entry.get("summary") or entry.get("description"))
        published = clean_text(entry.get("published") or entry.get("updated") or entry.get("created"))
        lookup[key] = {"title": title, "summary": summary, "published": published}

    return lookup


def repair_object(value: Any, lookup: dict[str, dict[str, str]]) -> int:
    repaired = 0
    if isinstance(value, dict):
        if (
            value.get("source") == "CBC News London"
            and value.get("ingestion_path") == "cbc-google-news-fallback"
        ):
            key = google_story_key(value.get("url"))
            source = lookup.get(key)
            if source:
                value["title"] = source["title"]
                if source["summary"]:
                    value["summary"] = source["summary"]
                value["author"] = "CBC News"
                value["content_status"] = "summary"
                value["paragraphs"] = []
                value["content_blocks"] = []
                value["content"] = ""
                value["word_count"] = 0
                value.pop("scrape_error", None)
                value["scraped_at"] = datetime.now(timezone.utc).isoformat()
                quality = value.get("quality")
                if not isinstance(quality, dict):
                    quality = {}
                    value["quality"] = quality
                quality.update({
                    "score": 30,
                    "grade": "poor",
                    "method": "rss:google-cbc-fallback",
                    "text_blocks": 0,
                    "rich_blocks": 0,
                    "image_blocks": 0,
                })
                repaired += 1
        for child in value.values():
            repaired += repair_object(child, lookup)
    elif isinstance(value, list):
        for child in value:
            repaired += repair_object(child, lookup)
    return repaired


def main() -> int:
    if not NEWS_PATH.exists():
        print("CBC fallback repair skipped: data/news.json does not exist", file=sys.stderr)
        return 0

    try:
        lookup = load_google_cbc()
    except Exception as exc:
        print(f"CBC fallback repair skipped: could not refresh Google News metadata: {exc}", file=sys.stderr)
        return 0

    if not lookup:
        print("CBC fallback repair skipped: no CBC Google News entries found", file=sys.stderr)
        return 0

    payload = json.loads(NEWS_PATH.read_text(encoding="utf-8"))
    repaired = repair_object(payload, lookup)
    if repaired:
        NEWS_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"CBC fallback metadata repair: {repaired} record(s) normalized from {len(lookup)} CBC discovery entries")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
