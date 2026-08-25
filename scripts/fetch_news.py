from __future__ import annotations

import hashlib
import html
import json
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse, urlunparse

import feedparser
import requests
from bs4 import BeautifulSoup, Tag
from dateutil import parser as date_parser
from trafilatura import bare_extraction, extract

from sources import SOURCES, Source

ROOT = Path(__file__).resolve().parents[1]
DATA_FILE = ROOT / "data" / "news.json"
HISTORY_LIMIT = 750
REQUEST_TIMEOUT = 22
ARTICLE_REFRESH_HOURS = 12
BACKFILL_PER_RUN = 12
MIN_ARTICLE_CHARS = 320
MAX_ARTICLE_IMAGES = 10
USER_AGENT = "LondonNewsAggregator/2.0 (+https://github.com/)"
SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/rss+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-CA,en;q=0.9",
})

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

JUNK_TEXT = (
    "sign up for", "subscribe to", "read more:", "related stories", "related story", "advertisement",
    "story continues below", "continue reading", "click here", "share this article", "copyright",
    "all rights reserved", "download our app", "follow us on", "recommended video", "more from",
)

IMAGE_JUNK = (
    "logo", "icon", "avatar", "author", "profile", "sprite", "pixel", "tracking", "badge", "weather",
    "placeholder", "default", "newsletter", "app-store", "google-play", "social", "facebook", "twitter",
)


def clean_text(value: str | None, limit: int | None = None) -> str:
    if not value:
        return ""
    text = BeautifulSoup(html.unescape(str(value)), "html.parser").get_text(" ", strip=True)
    text = re.sub(r"\s+", " ", text).strip()
    if limit and len(text) > limit:
        return text[: limit - 1].rstrip(" ,;:-") + "…"
    return text


def canonical_url(url: str) -> str:
    if not url:
        return ""
    parsed = urlparse(url.strip())
    # Drop common tracking query strings, but preserve query on Google News because it can be significant.
    clean = parsed._replace(fragment="", query="" if "news.google.com" not in parsed.netloc else parsed.query)
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


def soup_meta(soup: BeautifulSoup, *keys: tuple[str, str]) -> str:
    for attr, value in keys:
        tag = soup.find("meta", attrs={attr: value})
        if tag and tag.get("content"):
            return clean_text(tag.get("content"))
    return ""


def json_ld_objects(soup: BeautifulSoup) -> list[dict[str, Any]]:
    objects: list[dict[str, Any]] = []
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        raw = script.string or script.get_text(strip=True)
        if not raw:
            continue
        try:
            payload = json.loads(raw)
        except Exception:
            continue
        queue: list[Any] = payload if isinstance(payload, list) else [payload]
        while queue:
            item = queue.pop(0)
            if isinstance(item, dict):
                graph = item.get("@graph")
                if isinstance(graph, list):
                    queue.extend(graph)
                objects.append(item)
            elif isinstance(item, list):
                queue.extend(item)
    return objects


def article_json_ld(soup: BeautifulSoup) -> dict[str, Any]:
    preferred = {"NewsArticle", "Article", "ReportageNewsArticle", "BlogPosting"}
    for item in json_ld_objects(soup):
        kinds = item.get("@type", "")
        if isinstance(kinds, str):
            kinds = {kinds}
        elif isinstance(kinds, list):
            kinds = set(str(x) for x in kinds)
        else:
            kinds = set()
        if kinds & preferred:
            return item
    return {}


def json_ld_author(value: Any) -> str:
    if isinstance(value, str):
        return clean_text(value)
    if isinstance(value, dict):
        return clean_text(value.get("name"))
    if isinstance(value, list):
        names = [json_ld_author(item) for item in value]
        return ", ".join(name for name in names if name)
    return ""


def json_ld_images(value: Any) -> list[str]:
    found: list[str] = []
    if isinstance(value, str):
        found.append(value)
    elif isinstance(value, dict):
        for key in ("url", "contentUrl"):
            if value.get(key):
                found.append(str(value[key]))
    elif isinstance(value, list):
        for item in value:
            found.extend(json_ld_images(item))
    return found


def best_img_url(img: Tag, base_url: str) -> str:
    candidates = []
    for attr in ("data-src", "data-lazy-src", "data-original", "src"):
        if img.get(attr):
            candidates.append(str(img.get(attr)))
    srcset = img.get("srcset") or img.get("data-srcset")
    if srcset:
        parsed = []
        for part in str(srcset).split(","):
            bits = part.strip().split()
            if not bits:
                continue
            url = bits[0]
            score = 0
            if len(bits) > 1:
                try:
                    score = int(re.sub(r"\D", "", bits[1]) or "0")
                except Exception:
                    score = 0
            parsed.append((score, url))
        if parsed:
            candidates.insert(0, max(parsed, key=lambda item: item[0])[1])
    for candidate in candidates:
        if not candidate or candidate.startswith(("data:", "blob:")):
            continue
        return urljoin(base_url, candidate)
    return ""


def valid_article_image(url: str, img: Tag | None = None) -> bool:
    if not url or url.lower().endswith(".svg"):
        return False
    lower = url.lower()
    if any(token in lower for token in IMAGE_JUNK):
        return False
    if img is not None:
        try:
            width = int(re.sub(r"\D", "", str(img.get("width") or "0")) or "0")
            height = int(re.sub(r"\D", "", str(img.get("height") or "0")) or "0")
            if width and width < 240:
                return False
            if height and height < 160:
                return False
        except Exception:
            pass
    return True


def collect_article_images(soup: BeautifulSoup, base_url: str, lead_image: str, ld: dict[str, Any]) -> list[dict[str, str]]:
    results: list[dict[str, str]] = []
    seen: set[str] = set()

    def add(url: str, alt: str = "", caption: str = "") -> None:
        url = canonical_url(urljoin(base_url, url)) if url else ""
        if not valid_article_image(url) or url in seen:
            return
        seen.add(url)
        results.append({"url": url, "alt": clean_text(alt, 180), "caption": clean_text(caption, 280)})

    for url in json_ld_images(ld.get("image")):
        add(url)

    selectors = [
        "article figure img", "article picture img", "article img",
        "[itemprop='articleBody'] figure img", "[itemprop='articleBody'] img",
        "main figure img", "main article img",
    ]
    for selector in selectors:
        for img in soup.select(selector):
            if not isinstance(img, Tag):
                continue
            url = best_img_url(img, base_url)
            if not valid_article_image(url, img):
                continue
            figure = img.find_parent("figure")
            caption = ""
            if figure:
                cap = figure.find("figcaption")
                if cap:
                    caption = cap.get_text(" ", strip=True)
            add(url, img.get("alt") or "", caption)
            if len(results) >= MAX_ARTICLE_IMAGES:
                break
        if len(results) >= MAX_ARTICLE_IMAGES:
            break

    lead = canonical_url(lead_image)
    # The hero is rendered separately, so keep it out of the inline image list.
    return [item for item in results if canonical_url(item["url"]) != lead][:MAX_ARTICLE_IMAGES]


def dom_paragraphs(soup: BeautifulSoup) -> list[str]:
    selectors = [
        "[itemprop='articleBody']",
        "article .article-body", "article .article-content", "article .story-body",
        "article .entry-content", "article .post-content", "article",
        "main .article-body", "main .story-body", "main",
    ]
    root: Tag | None = None
    for selector in selectors:
        candidate = soup.select_one(selector)
        if isinstance(candidate, Tag):
            root = candidate
            break
    if root is None:
        return []

    paragraphs: list[str] = []
    seen: set[str] = set()
    for node in root.select("p, h2, h3, blockquote, li"):
        if not isinstance(node, Tag):
            continue
        classes = " ".join(node.get("class", [])).lower()
        node_id = str(node.get("id", "")).lower()
        if any(token in classes or token in node_id for token in ("caption", "related", "promo", "newsletter", "share", "social", "advert", "author", "footer", "nav")):
            continue
        text = clean_text(node.get_text(" ", strip=True))
        if len(text) < 25 or text in seen:
            continue
        lower = text.lower()
        if any(junk in lower for junk in JUNK_TEXT) and len(text) < 220:
            continue
        seen.add(text)
        paragraphs.append(text)
    return paragraphs


def split_extracted_text(text: str) -> list[str]:
    if not text:
        return []
    chunks = []
    for part in re.split(r"\n+", text):
        cleaned = clean_text(part)
        if len(cleaned) < 25:
            continue
        lower = cleaned.lower()
        if any(junk in lower for junk in JUNK_TEXT) and len(cleaned) < 220:
            continue
        if not chunks or cleaned != chunks[-1]:
            chunks.append(cleaned)
    return chunks


def extracted_article_text(raw: str, final_url: str) -> tuple[str, list[str], dict[str, Any]]:
    metadata: dict[str, Any] = {}
    text = ""
    try:
        payload = extract(
            raw,
            url=final_url,
            output_format="json",
            with_metadata=True,
            include_comments=False,
            include_tables=True,
            favor_recall=True,
        )
        if payload:
            metadata = json.loads(payload)
            text = metadata.get("text") or metadata.get("raw_text") or ""
    except Exception:
        metadata = {}

    if len(clean_text(text)) < MIN_ARTICLE_CHARS:
        try:
            doc = bare_extraction(
                raw,
                url=final_url,
                include_comments=False,
                include_tables=True,
                favor_recall=True,
            )
            if doc:
                candidate = getattr(doc, "text", None)
                if candidate is None and isinstance(doc, dict):
                    candidate = doc.get("text") or doc.get("raw_text")
                if candidate:
                    text = candidate
                for key in ("title", "author", "date", "description"):
                    value = getattr(doc, key, None) if not isinstance(doc, dict) else doc.get(key)
                    if value and not metadata.get(key):
                        metadata[key] = value
        except Exception:
            pass

    paragraphs = split_extracted_text(text)
    return "\n\n".join(paragraphs), paragraphs, metadata


def stale(existing: dict[str, Any]) -> bool:
    if not existing.get("content") and not existing.get("paragraphs"):
        return True
    scraped = existing.get("scraped_at")
    if not scraped:
        return True
    try:
        dt = date_parser.parse(scraped)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) - dt.astimezone(timezone.utc) >= timedelta(hours=ARTICLE_REFRESH_HOURS)
    except Exception:
        return True


def resolve_google_news(raw: str, current_url: str, source: Source) -> str:
    if "news.google.com" not in urlparse(current_url).netloc:
        return current_url
    soup = BeautifulSoup(raw, "html.parser")
    wanted_host = urlparse(source.homepage).netloc.lower().replace("www.", "")
    candidates: list[str] = []
    for anchor in soup.find_all("a", href=True):
        href = urljoin(current_url, anchor.get("href"))
        host = urlparse(href).netloc.lower().replace("www.", "")
        if not host or "google." in host or "gstatic." in host:
            continue
        candidates.append(href)
        if wanted_host and (host == wanted_host or host.endswith("." + wanted_host) or wanted_host.endswith("." + host)):
            return href
    return candidates[0] if candidates else current_url


def enrich_article(story: dict[str, Any], source: Source) -> dict[str, Any]:
    url = story.get("url", "")
    if not url:
        return story

    try:
        raw, final_url = fetch_html(url)
        resolved = resolve_google_news(raw, final_url, source)
        if resolved != final_url:
            raw, final_url = fetch_html(resolved)
    except Exception as exc:
        story["scrape_error"] = str(exc)[:240]
        return story

    soup = BeautifulSoup(raw, "html.parser")
    ld = article_json_ld(soup)
    text, paragraphs, extracted_meta = extracted_article_text(raw, final_url)

    dom = dom_paragraphs(soup)
    dom_text = "\n\n".join(dom)
    if len(dom_text) > len(text) * 1.15 and len(dom_text) >= MIN_ARTICLE_CHARS:
        paragraphs = dom
        text = dom_text

    title = (
        clean_text(ld.get("headline"))
        or clean_text(extracted_meta.get("title"))
        or soup_meta(soup, ("property", "og:title"), ("name", "twitter:title"))
        or story.get("title", "")
    )
    summary = (
        clean_text(ld.get("description"), 360)
        or clean_text(extracted_meta.get("description"), 360)
        or soup_meta(soup, ("property", "og:description"), ("name", "description"), ("name", "twitter:description"))
        or story.get("summary", "")
    )
    author = (
        json_ld_author(ld.get("author"))
        or clean_text(extracted_meta.get("author"))
        or soup_meta(soup, ("name", "author"), ("property", "article:author"))
        or story.get("author", "")
    )
    published = (
        ld.get("datePublished")
        or extracted_meta.get("date")
        or soup_meta(soup, ("property", "article:published_time"), ("name", "date"), ("name", "parsely-pub-date"))
        or story.get("published")
    )

    lead_image = (
        (json_ld_images(ld.get("image")) or [""])[0]
        or soup_meta(soup, ("property", "og:image"), ("name", "twitter:image"))
        or story.get("image", "")
    )
    if lead_image:
        lead_image = urljoin(final_url, lead_image)

    images = collect_article_images(soup, final_url, lead_image, ld)
    content_ok = len(text) >= MIN_ARTICLE_CHARS and len(paragraphs) >= 2

    story.update({
        "id": story.get("id") or make_id(final_url),
        "title": title,
        "url": canonical_url(final_url),
        "published": parse_date(published),
        "summary": clean_text(summary, 360),
        "image": canonical_url(lead_image) if lead_image else "",
        "author": clean_text(author),
        "category": classify(title, summary, source.name),
        "content": text if content_ok else "",
        "paragraphs": paragraphs if content_ok else [],
        "article_images": images,
        "word_count": len(re.findall(r"\b\w+[’'-]?\w*\b", text)) if content_ok else 0,
        "scraped_at": datetime.now(timezone.utc).isoformat(),
        "content_status": "full" if content_ok else "summary",
    })
    story.pop("scrape_error", None)
    return story


def load_existing() -> list[dict[str, Any]]:
    if not DATA_FILE.exists():
        return []
    try:
        payload = json.loads(DATA_FILE.read_text(encoding="utf-8"))
        return payload.get("stories", [])
    except Exception:
        return []


def existing_lookup(stories: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    lookup: dict[str, dict[str, Any]] = {}
    for story in stories:
        if story.get("id"):
            lookup[story["id"]] = story
        if story.get("url"):
            lookup[canonical_url(story["url"])] = story
    return lookup


def rss_items(source: Source, existing: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    response = SESSION.get(source.url, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    feed = feedparser.parse(response.content)
    items: list[dict[str, Any]] = []

    for entry in feed.entries[: source.max_items]:
        url = entry.get("link", "")
        title = clean_text(entry.get("title"))
        if not url or not title:
            continue
        summary = clean_text(entry.get("summary") or entry.get("description"), 360)
        published = entry.get("published") or entry.get("updated") or entry.get("created")
        author = clean_text(entry.get("author"))
        image = image_from_entry(entry)

        basic = {
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
        }

        old = existing.get(basic["id"]) or existing.get(basic["url"])
        if old and not stale(old):
            merged = {**basic, **old}
            # Preserve current source branding even if the old record predates a palette change.
            merged.update({"source": source.name, "source_home": source.homepage, "source_accent": source.accent})
            items.append(merged)
        else:
            items.append(enrich_article({**(old or {}), **basic}, source))
            time.sleep(0.14)
    return items


def page_links(source: Source) -> list[str]:
    raw, final_url = fetch_html(source.url)
    soup = BeautifulSoup(raw, "html.parser")
    host = urlparse(final_url).netloc.lower().replace("www.", "")
    links: list[str] = []
    selectors = [
        "main h2 a[href]", "main h3 a[href]", "article h2 a[href]", "article h3 a[href]",
        ".news-item a[href]", ".card a[href]", "a[href*='/news/']",
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


def page_items(source: Source, existing: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for url in page_links(source):
        old = existing.get(make_id(url)) or existing.get(canonical_url(url))
        if old and not stale(old):
            story = {**old, "source": source.name, "source_home": source.homepage, "source_accent": source.accent}
        else:
            story = enrich_article({
                "id": make_id(url),
                "title": old.get("title", "") if old else "",
                "source": source.name,
                "source_home": source.homepage,
                "source_accent": source.accent,
                "url": canonical_url(url),
                "published": old.get("published", datetime.now(timezone.utc).isoformat()) if old else datetime.now(timezone.utc).isoformat(),
                "summary": old.get("summary", "") if old else "",
                "image": old.get("image", "") if old else "",
                "author": old.get("author", "") if old else "",
                "category": old.get("category", "Local") if old else "Local",
            }, source)
            time.sleep(0.14)
        if story.get("title"):
            items.append(story)
    return items


def backfill_missing(stories: list[dict[str, Any]]) -> list[dict[str, Any]]:
    source_by_name = {source.name: source for source in SOURCES}
    done = 0
    for story in stories:
        if done >= BACKFILL_PER_RUN:
            break
        if story.get("content_status") == "full" or story.get("content"):
            continue
        source = source_by_name.get(story.get("source", ""))
        if not source or not story.get("url"):
            continue
        print(f"Backfill: {story.get('source')} | {story.get('title', '')[:70]}")
        enrich_article(story, source)
        done += 1
        time.sleep(0.18)
    return stories


def main() -> int:
    previous = load_existing()
    lookup = existing_lookup(previous)
    fresh: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []

    for source in SOURCES:
        try:
            items = rss_items(source, lookup) if source.kind == "rss" else page_items(source, lookup)
            fresh.extend(items)
            full_count = sum(1 for item in items if item.get("content_status") == "full")
            print(f"{source.name}: {len(items)} items, {full_count} full")
        except Exception as exc:
            errors.append({"source": source.name, "error": str(exc)[:240]})
            print(f"{source.name}: ERROR {exc}", file=sys.stderr)

    merged: dict[str, dict[str, Any]] = {}
    for story in previous + fresh:
        key = story.get("id") or make_id(story.get("url", ""))
        if key:
            merged[key] = story

    stories = sorted(merged.values(), key=lambda item: item.get("published", ""), reverse=True)[:HISTORY_LIMIT]
    stories = backfill_missing(stories)

    now = datetime.now(timezone.utc).isoformat()
    full_count = sum(1 for item in stories if item.get("content_status") == "full" or item.get("content"))
    payload = {
        "generated_at": now,
        "story_count": len(stories),
        "full_story_count": full_count,
        "source_count": len(SOURCES),
        "errors": errors,
        "stories": stories,
    }
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    DATA_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {len(stories)} stories ({full_count} full) to {DATA_FILE}")
    return 0 if stories else 1


if __name__ == "__main__":
    raise SystemExit(main())
