from __future__ import annotations

import hashlib
import html
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse, urlunparse

import feedparser
import requests
from bs4 import BeautifulSoup
from dateutil import parser as date_parser
from trafilatura import bare_extraction

from sources import SOURCES, Source

ROOT = Path(__file__).resolve().parents[1]
DATA_FILE = ROOT / "data" / "news.json"
HISTORY_LIMIT = 750
REQUEST_TIMEOUT = 18
USER_AGENT = "LondonNewsAggregator/1.0 (+https://github.com/)"
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml,application/rss+xml,application/xml;q=0.9,*/*;q=0.8"})

CATEGORY_RULES = [
    ("Public Safety", ("police", "arrest", "charged", "shooting", "collision", "fire", "fraud", "missing", "court", "crime")),
    ("City Hall", ("council", "mayor", "city hall", "municipal", "zoning", "budget", "ward", "election", "city of london")),
    ("Traffic", ("road", "closure", "traffic", "transit", "construction", "highway", "street", "lane")),
    ("Business", ("business", "jobs", "employer", "economy", "development", "retail", "housing", "market")),
    ("Education", ("western", "fanshawe", "school", "student", "university", "college", "tvdsb", "ldcsb")),
    ("Health", ("hospital", "health", "lhsc", "outbreak", "doctor", "nurse", "clinic")),
    ("Sports", ("knights", "sports", "hockey", "soccer", "baseball", "basketball", "football", "game")),
    ("Community", ("festival", "community", "event", "arts", "music", "theatre", "restaurant", "park", "recreation")),
]


def clean_text(value: str | None, limit: int | None = None) -> str:
    if not value:
        return ""
    text = BeautifulSoup(html.unescape(value), "html.parser").get_text(" ", strip=True)
    text = re.sub(r"\s+", " ", text).strip()
    if limit and len(text) > limit:
        return text[: limit - 1].rstrip(" ,;:-") + "…"
    return text


def canonical_url(url: str) -> str:
    parsed = urlparse(url.strip())
    clean = parsed._replace(fragment="", query="")
    return urlunparse(clean).rstrip("/")


def make_id(url: str) -> str:
    return hashlib.sha1(canonical_url(url).encode("utf-8")).hexdigest()[:16]


def parse_date(value: Any) -> str:
    if not value:
        return datetime.now(timezone.utc).isoformat()
    try:
        dt = date_parser.parse(str(value))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()
    except Exception:
        return datetime.now(timezone.utc).isoformat()


def classify(title: str, summary: str, source: str) -> str:
    haystack = f"{title} {summary} {source}".lower()
    for category, needles in CATEGORY_RULES:
        if any(word in haystack for word in needles):
            return category
    return "Local"


def image_from_entry(entry: Any) -> str:
    candidates: list[str] = []
    for field in ("media_content", "media_thumbnail"):
        for media in entry.get(field, []) or []:
            if isinstance(media, dict) and media.get("url"):
                candidates.append(media["url"])
    for enclosure in entry.get("enclosures", []) or []:
        if enclosure.get("href") and str(enclosure.get("type", "")).startswith("image"):
            candidates.append(enclosure["href"])
    return candidates[0] if candidates else ""


def fetch_html(url: str) -> tuple[str, str]:
    response = SESSION.get(url, timeout=REQUEST_TIMEOUT, allow_redirects=True)
    response.raise_for_status()
    return response.text, response.url


def page_metadata(url: str) -> dict[str, str]:
    try:
        raw, final_url = fetch_html(url)
    except Exception:
        return {}

    soup = BeautifulSoup(raw, "html.parser")
    result: dict[str, str] = {"url": final_url}

    def meta(*keys: tuple[str, str]) -> str:
        for attr, value in keys:
            tag = soup.find("meta", attrs={attr: value})
            if tag and tag.get("content"):
                return clean_text(tag.get("content"))
        return ""

    result["title"] = meta(("property", "og:title"), ("name", "twitter:title"))
    result["summary"] = meta(("property", "og:description"), ("name", "description"), ("name", "twitter:description"))
    result["image"] = meta(("property", "og:image"), ("name", "twitter:image"))
    result["author"] = meta(("name", "author"), ("property", "article:author"))
    result["published"] = meta(("property", "article:published_time"), ("name", "date"), ("name", "parsely-pub-date"))

    if not result["summary"]:
        try:
            extracted = bare_extraction(raw, url=final_url, include_comments=False, include_tables=False)
            if extracted:
                text = getattr(extracted, "text", None) or (extracted.get("text") if isinstance(extracted, dict) else "")
                result["summary"] = clean_text(text, 280)
        except Exception:
            pass

    result["summary"] = clean_text(result.get("summary"), 280)
    return result


def rss_items(source: Source) -> list[dict[str, Any]]:
    response = SESSION.get(source.url, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    feed = feedparser.parse(response.content)
    items: list[dict[str, Any]] = []

    for entry in feed.entries[: source.max_items]:
        url = entry.get("link", "")
        title = clean_text(entry.get("title"))
        if not url or not title:
            continue
        summary = clean_text(entry.get("summary") or entry.get("description"), 280)
        published = entry.get("published") or entry.get("updated") or entry.get("created")
        author = clean_text(entry.get("author"))
        image = image_from_entry(entry)

        items.append({
            "id": make_id(url),
            "title": title,
            "source": source.name,
            "source_home": source.homepage,
            "source_accent": source.accent,
            "url": canonical_url(url),
            "published": parse_date(published),
            "summary": summary,
            "image": image,
            "author": author,
            "category": classify(title, summary, source.name),
        })
    return items


def page_links(source: Source) -> list[str]:
    raw, final_url = fetch_html(source.url)
    soup = BeautifulSoup(raw, "html.parser")
    host = urlparse(final_url).netloc.lower().replace("www.", "")
    links: list[str] = []

    selectors = [
        "main h2 a[href]", "main h3 a[href]", "article h2 a[href]", "article h3 a[href]",
        ".news-item a[href]", ".card a[href]", "a[href*='/news/']"
    ]
    for selector in selectors:
        for anchor in soup.select(selector):
            href = anchor.get("href")
            if not href:
                continue
            url = urljoin(final_url, href)
            parsed = urlparse(url)
            if parsed.netloc.lower().replace("www.", "") != host:
                continue
            if canonical_url(url) == canonical_url(source.url):
                continue
            text = clean_text(anchor.get_text(" ", strip=True))
            if len(text) < 8:
                continue
            clean = canonical_url(url)
            if clean not in links:
                links.append(clean)
            if len(links) >= source.max_items:
                return links
    return links


def page_items(source: Source) -> list[dict[str, Any]]:
    items = []
    for url in page_links(source):
        meta = page_metadata(url)
        title = clean_text(meta.get("title"))
        if not title:
            continue
        summary = clean_text(meta.get("summary"), 280)
        final_url = canonical_url(meta.get("url") or url)
        items.append({
            "id": make_id(final_url),
            "title": title,
            "source": source.name,
            "source_home": source.homepage,
            "source_accent": source.accent,
            "url": final_url,
            "published": parse_date(meta.get("published")),
            "summary": summary,
            "image": meta.get("image", ""),
            "author": clean_text(meta.get("author")),
            "category": classify(title, summary, source.name),
        })
        time.sleep(0.12)
    return items


def load_existing() -> list[dict[str, Any]]:
    if not DATA_FILE.exists():
        return []
    try:
        payload = json.loads(DATA_FILE.read_text(encoding="utf-8"))
        return payload.get("stories", [])
    except Exception:
        return []


def main() -> int:
    fresh: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []

    for source in SOURCES:
        try:
            items = rss_items(source) if source.kind == "rss" else page_items(source)
            fresh.extend(items)
            print(f"{source.name}: {len(items)} items")
        except Exception as exc:
            errors.append({"source": source.name, "error": str(exc)[:240]})
            print(f"{source.name}: ERROR {exc}", file=sys.stderr)

    merged: dict[str, dict[str, Any]] = {}
    for story in load_existing() + fresh:
        key = story.get("id") or make_id(story.get("url", ""))
        if key:
            merged[key] = story

    stories = sorted(merged.values(), key=lambda item: item.get("published", ""), reverse=True)[:HISTORY_LIMIT]
    now = datetime.now(timezone.utc).isoformat()
    payload = {
        "generated_at": now,
        "story_count": len(stories),
        "source_count": len(SOURCES),
        "errors": errors,
        "stories": stories,
    }
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    DATA_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {len(stories)} stories to {DATA_FILE}")
    return 0 if stories else 1


if __name__ == "__main__":
    raise SystemExit(main())
