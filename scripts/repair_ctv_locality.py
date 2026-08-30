#!/usr/bin/env python3
from __future__ import annotations

import html
import json
import re
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Callable, Iterable
from urllib.parse import urljoin, urlparse
from zoneinfo import ZoneInfo

import feedparser
import requests
from bs4 import BeautifulSoup
from dateutil import parser as date_parser

import fetch_news
import ranking
from sources import Source

ROOT = Path(__file__).resolve().parents[1]
NEWS_FILE = ROOT / "data" / "news.json"
LOCAL_TIMEZONE = ZoneInfo("America/Toronto")
USER_AGENT = "LondonNewsAggregator/3.0 (+https://github.com/)"
CTV_GOOGLE_NEWS_FEED = (
    "https://news.google.com/rss/search?"
    "q=site%3Actvnews.ca%2Flondon%2Farticle%2F%20when%3A3d&"
    "hl=en-CA&gl=CA&ceid=CA%3Aen"
)
CTV_LOCAL_SOURCE = "CTV News"
CTV_CANADA_SOURCE = "CTV News Canada"
CTV_LOCAL_HOME = "https://www.ctvnews.ca/london/"
CTV_ACCENT = "#6155f5"
MAX_NEW_STORIES = 14
MAX_GOOGLE_RESOLVES = 16


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _title_key(value: Any) -> str:
    text = _clean(value)
    text = re.sub(r"\s+-\s+CTV(?: News)?(?: London)?\s*$", "", text, flags=re.I)
    text = text.lower().replace("’", "'")
    text = re.sub(r"[^a-z0-9']+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _parse_date(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = date_parser.parse(str(value))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=LOCAL_TIMEZONE)
        return parsed.astimezone(timezone.utc)
    except Exception:
        return None


def _canonical_ctv_london_url(value: Any) -> str:
    candidate = fetch_news.canonical_url(str(value or "").strip())
    if not candidate:
        return ""
    try:
        parsed = urlparse(candidate)
    except Exception:
        return ""
    host = parsed.netloc.lower().split(":", 1)[0]
    if host not in {"ctvnews.ca", "www.ctvnews.ca"}:
        return ""
    if not parsed.path.lower().startswith("/london/article/"):
        return ""
    return candidate


def _is_ctv_london_url(value: Any) -> bool:
    return bool(_canonical_ctv_london_url(value))


def _entry_source_name(entry: Any) -> str:
    source = entry.get("source") or {}
    if isinstance(source, dict):
        return _clean(source.get("title") or source.get("value"))
    return _clean(source)


def _entry_title(entry: Any) -> str:
    return re.sub(
        r"\s+-\s+CTV(?: News)?(?: London)?\s*$",
        "",
        _clean(entry.get("title")),
        flags=re.I,
    ).strip()


def _entry_summary(entry: Any, title: str) -> str:
    raw = entry.get("summary") or entry.get("description") or ""
    text = BeautifulSoup(str(raw), "html.parser").get_text(" ", strip=True)
    return fetch_news.clean_summary_text(text, title)


def indexed_ctv_dates(entries: Iterable[Any]) -> dict[str, datetime]:
    """Return Google News publication timestamps keyed by normalized CTV headline."""
    indexed: dict[str, datetime] = {}
    for entry in entries:
        source_name = _entry_source_name(entry)
        raw_title = _clean(entry.get("title"))
        if "ctv" not in source_name.lower() and not re.search(r"\s+-\s+CTV(?: News)?", raw_title, flags=re.I):
            continue
        key = _title_key(raw_title)
        published = _parse_date(entry.get("published") or entry.get("updated") or entry.get("created"))
        if not key or published is None:
            continue
        current = indexed.get(key)
        if current is None or published > current:
            indexed[key] = published
    return indexed


def _best_index_match(title: Any, indexed: dict[str, datetime]) -> tuple[str, datetime] | None:
    key = _title_key(title)
    if not key:
        return None
    exact = indexed.get(key)
    if exact is not None:
        return key, exact

    best_key = ""
    best_ratio = 0.0
    for candidate in indexed:
        ratio = SequenceMatcher(None, key, candidate).ratio()
        if ratio > best_ratio:
            best_ratio = ratio
            best_key = candidate
    if best_key and best_ratio >= 0.92:
        return best_key, indexed[best_key]
    return None


def repair_payload(
    payload: dict[str, Any],
    entries: Iterable[Any] = (),
    *,
    now: datetime | None = None,
) -> tuple[dict[str, Any], dict[str, int]]:
    """Restore London ownership and correct stale CTV timestamps."""
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    indexed = indexed_ctv_dates(entries)
    stats = {"reclassified": 0, "timestamps_updated": 0, "matched_index": 0}

    stories = payload.get("stories") or []
    if not isinstance(stories, list):
        return payload, stats

    for story in stories:
        if not isinstance(story, dict):
            continue

        source = _clean(story.get("source"))
        london_url = _is_ctv_london_url(story.get("url"))

        # CTV Canada is collected later than CTV London. Because both can expose
        # the same canonical /london/article/ URL, the Canada copy can overwrite
        # the local copy in the shared merge map. URL ownership is authoritative.
        if source == CTV_CANADA_SOURCE and london_url:
            story["source"] = CTV_LOCAL_SOURCE
            story["source_home"] = CTV_LOCAL_HOME
            story["source_accent"] = CTV_ACCENT
            story["scope"] = "local"
            story["source_repaired_from"] = CTV_CANADA_SOURCE
            stats["reclassified"] += 1
            source = CTV_LOCAL_SOURCE

        if source != CTV_LOCAL_SOURCE or not london_url or not indexed:
            continue

        matched = _best_index_match(story.get("title"), indexed)
        if matched is None:
            continue
        _, indexed_date = matched
        stats["matched_index"] += 1

        # Google News is only a freshness cross-check. Never move an article
        # backwards, and reject obviously stale or future index timestamps.
        if indexed_date > now + timedelta(minutes=30) or indexed_date < now - timedelta(days=5):
            continue

        current_date = _parse_date(story.get("published"))
        if current_date is not None and indexed_date <= current_date + timedelta(minutes=2):
            continue

        if story.get("published"):
            story["published_original"] = story.get("published")
        story["published"] = indexed_date.isoformat()
        story["published_via"] = "google-news-ctv-index"
        stats["timestamps_updated"] += 1

    if stats["reclassified"]:
        for health in payload.get("source_health") or []:
            if not isinstance(health, dict):
                continue
            if _clean(health.get("source")) == CTV_LOCAL_SOURCE:
                health["scope"] = "local"
            elif _clean(health.get("source")) == CTV_CANADA_SOURCE:
                health["scope"] = "canada"

    return payload, stats


def fetch_ctv_index_entries() -> list[Any]:
    response = requests.get(
        CTV_GOOGLE_NEWS_FEED,
        headers={"User-Agent": USER_AGENT, "Accept-Language": "en-CA,en;q=0.9"},
        timeout=12,
    )
    response.raise_for_status()
    feed = feedparser.parse(response.content)
    return list(feed.entries)


def fetch_ctv_landing_urls(limit: int = 90) -> list[str]:
    """Discover CTV London URLs with main-content links before generic page links.

    The generic collector historically scanned every matching anchor first and
    stopped after 30 URLs. On CTV, navigation and recirculation links can consume
    that quota before the newest London cards are reached. This backstop walks the
    actual main content first, then the remaining HTML and hydration payload.
    """
    raw, final_url = fetch_news.fetch_html(CTV_LOCAL_HOME)
    soup = BeautifulSoup(raw, "html.parser")
    found: list[str] = []

    def add(value: Any) -> None:
        candidate = _canonical_ctv_london_url(urljoin(final_url, str(value or "")))
        if candidate and candidate not in found:
            found.append(candidate)

    for selector in (
        "main a[href*='/london/article/']",
        "article a[href*='/london/article/']",
        "a[href*='/london/article/']",
    ):
        for anchor in soup.select(selector):
            add(anchor.get("href"))
            if len(found) >= limit:
                return found

    normalized_raw = html.unescape(raw).replace("\\/", "/")
    pattern = r'(?:https?://(?:www\.)?ctvnews\.ca)?(/london/article/[A-Za-z0-9][^"\'<>\\\s?#]*)'
    for match in re.finditer(pattern, normalized_raw, flags=re.I):
        add(match.group(1))
        if len(found) >= limit:
            break
    return found


def _ctv_source() -> Source:
    return Source(
        name=CTV_LOCAL_SOURCE,
        url=CTV_LOCAL_HOME,
        kind="page",
        homepage=CTV_LOCAL_HOME,
        accent=CTV_ACCENT,
        max_items=30,
    )


def _story_lookup(stories: list[dict[str, Any]]) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    by_url: dict[str, dict[str, Any]] = {}
    by_title: dict[str, dict[str, Any]] = {}
    for story in stories:
        if not isinstance(story, dict):
            continue
        url = _canonical_ctv_london_url(story.get("url"))
        if url:
            by_url[url] = story
        key = _title_key(story.get("title"))
        if key:
            by_title[key] = story
    return by_url, by_title


def _title_already_present(title: str, by_title: dict[str, dict[str, Any]]) -> bool:
    key = _title_key(title)
    if not key:
        return False
    if key in by_title:
        return True
    return any(SequenceMatcher(None, key, candidate).ratio() >= 0.94 for candidate in by_title)


def _resolve_google_entry_url(entry: Any, source: Source) -> str:
    candidate = _canonical_ctv_london_url(entry.get("link") or entry.get("guid"))
    if candidate:
        return candidate

    google_url = fetch_news.canonical_url(entry.get("link") or entry.get("guid") or "")
    if not google_url or "news.google.com" not in urlparse(google_url).netloc.lower():
        return ""
    try:
        raw, final_url = fetch_news.fetch_html(google_url)
        candidate = _canonical_ctv_london_url(final_url)
        if candidate:
            return candidate
        resolved = fetch_news.resolve_google_news(raw, final_url, source)
        return _canonical_ctv_london_url(resolved)
    except Exception:
        return ""


def _safe_enrich(
    basic: dict[str, Any],
    source: Source,
    enrich: Callable[[dict[str, Any], Source], dict[str, Any]] = fetch_news.enrich_article,
) -> dict[str, Any] | None:
    try:
        story = enrich(dict(basic), source)
    except Exception as exc:
        story = dict(basic)
        story["scrape_error"] = str(exc)[:240]

    direct_url = _canonical_ctv_london_url(story.get("url") or basic.get("url"))
    title = fetch_news.clean_story_title(story.get("title") or basic.get("title") or "", CTV_LOCAL_SOURCE)
    if not direct_url or not title:
        return None

    story["id"] = fetch_news.make_id(direct_url)
    story["url"] = direct_url
    story["title"] = title
    story["source"] = CTV_LOCAL_SOURCE
    story["source_home"] = CTV_LOCAL_HOME
    story["source_accent"] = CTV_ACCENT
    story["scope"] = "local"
    if not story.get("published"):
        story["published"] = fetch_news.parse_date(basic.get("published"))
    if not story.get("summary"):
        story["summary"] = _clean(basic.get("summary"))

    if not story.get("content_status"):
        story["content_status"] = "summary"
    if not isinstance(story.get("paragraphs"), list):
        story["paragraphs"] = []
    if not isinstance(story.get("content_blocks"), list):
        story["content_blocks"] = []
    if not isinstance(story.get("quality"), dict):
        story["quality"] = fetch_news.extraction_quality(story, {}, "ctv-discovery:summary")
    story["ctv_discovery_backstop"] = True
    return story


def supplement_ctv_stories(
    payload: dict[str, Any],
    entries: Iterable[Any] = (),
    landing_urls: Iterable[str] = (),
    *,
    now: datetime | None = None,
    max_new: int = MAX_NEW_STORIES,
    resolve_google: Callable[[Any, Source], str] | None = None,
    enrich: Callable[[dict[str, Any], Source], dict[str, Any]] = fetch_news.enrich_article,
) -> tuple[dict[str, Any], dict[str, int]]:
    """Add current first-party CTV London stories missed by the generic 30-link cap."""
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    stories = payload.get("stories") or []
    if not isinstance(stories, list):
        return payload, {"landing_urls": 0, "google_resolved": 0, "added": 0}

    source = _ctv_source()
    resolve_google = resolve_google or _resolve_google_entry_url
    by_url, by_title = _story_lookup(stories)
    stats = {"landing_urls": 0, "google_resolved": 0, "added": 0}

    # First use the recent Google index to identify the stories most likely to be
    # missing. It supplies the headline and publication time, but a story is added
    # only after the link resolves to a canonical ctvnews.ca/london/article URL.
    resolve_count = 0
    for entry in entries:
        if stats["added"] >= max_new or resolve_count >= MAX_GOOGLE_RESOLVES:
            break
        source_name = _entry_source_name(entry)
        raw_title = _clean(entry.get("title"))
        if "ctv" not in source_name.lower() and not re.search(r"\s+-\s+CTV(?: News)?", raw_title, flags=re.I):
            continue
        title = _entry_title(entry)
        if not title or _title_already_present(title, by_title):
            continue
        published_dt = _parse_date(entry.get("published") or entry.get("updated") or entry.get("created"))
        if published_dt is None or published_dt < now - timedelta(days=5) or published_dt > now + timedelta(minutes=30):
            continue
        resolve_count += 1
        direct_url = resolve_google(entry, source)
        if not direct_url:
            continue
        stats["google_resolved"] += 1
        if direct_url in by_url:
            continue
        basic = {
            "id": fetch_news.make_id(direct_url),
            "title": title,
            "source": CTV_LOCAL_SOURCE,
            "source_home": CTV_LOCAL_HOME,
            "source_accent": CTV_ACCENT,
            "url": direct_url,
            "published": published_dt.isoformat(),
            "summary": _entry_summary(entry, title),
            "image": "",
            "author": "CTV News",
            "category": fetch_news.classify(title, _entry_summary(entry, title), CTV_LOCAL_SOURCE),
        }
        story = _safe_enrich(basic, source, enrich)
        if story is None:
            continue
        # Preserve the recent index timestamp if publisher metadata is missing or
        # older. It is never allowed to move a publisher timestamp backwards.
        story_date = _parse_date(story.get("published"))
        if story_date is None or published_dt > story_date + timedelta(minutes=2):
            if story.get("published"):
                story["published_original"] = story.get("published")
            story["published"] = published_dt.isoformat()
            story["published_via"] = "google-news-ctv-index"
        stories.append(story)
        by_url[direct_url] = story
        by_title[_title_key(story.get("title"))] = story
        stats["added"] += 1

    # Then backstop discovery from CTV's own landing page. Main-content links are
    # intentionally prioritized, fixing the old all-anchor-first 30-link cutoff.
    for raw_url in landing_urls:
        if stats["added"] >= max_new:
            break
        direct_url = _canonical_ctv_london_url(raw_url)
        if not direct_url:
            continue
        stats["landing_urls"] += 1
        if direct_url in by_url:
            continue
        basic = {
            "id": fetch_news.make_id(direct_url),
            "title": "",
            "source": CTV_LOCAL_SOURCE,
            "source_home": CTV_LOCAL_HOME,
            "source_accent": CTV_ACCENT,
            "url": direct_url,
            "published": now.isoformat(),
            "summary": "",
            "image": "",
            "author": "",
            "category": "Local",
        }
        story = _safe_enrich(basic, source, enrich)
        if story is None or _title_already_present(story.get("title", ""), by_title):
            continue
        stories.append(story)
        by_url[direct_url] = story
        by_title[_title_key(story.get("title"))] = story
        stats["added"] += 1

    payload["stories"] = stories
    return payload, stats


def refresh_editorial_metadata(payload: dict[str, Any]) -> None:
    stories = payload.get("stories") or []
    if not isinstance(stories, list):
        return
    stories.sort(key=lambda item: ranking._dt(item.get("published")), reverse=True)
    stories[:] = stories[: fetch_news.HISTORY_LIMIT]
    stories, editorial = ranking.apply_editorial_intelligence(stories)
    payload["stories"] = stories
    payload["story_count"] = len(stories)
    payload["full_story_count"] = sum(1 for item in stories if item.get("content_status") == "full")
    payload["partial_story_count"] = sum(1 for item in stories if item.get("content_status") == "partial")
    payload["source_count"] = len({item.get("source") for item in stories if item.get("source")})
    payload["cluster_count"] = editorial.get("cluster_count", 0)
    payload["multi_source_cluster_count"] = editorial.get("multi_source_cluster_count", 0)
    payload["top_story_ids"] = editorial.get("top_story_ids", [])
    payload["editorial_clusters"] = editorial.get("clusters", [])


def main() -> int:
    if not NEWS_FILE.exists():
        print(f"CTV locality repair skipped: {NEWS_FILE} does not exist")
        return 0

    payload = json.loads(NEWS_FILE.read_text(encoding="utf-8"))
    entries: list[Any] = []
    index_error = ""
    landing_urls: list[str] = []
    landing_error = ""

    try:
        entries = fetch_ctv_index_entries()
    except Exception as exc:
        index_error = str(exc)[:240]

    try:
        landing_urls = fetch_ctv_landing_urls()
    except Exception as exc:
        landing_error = str(exc)[:240]

    # Reclaim London URLs from the Canada source before checking for missing URLs.
    payload, repair_stats = repair_payload(payload, entries)
    payload, discovery_stats = supplement_ctv_stories(payload, entries, landing_urls)
    # Newly added stories also need the timestamp cross-check and editorial fields.
    payload, second_pass = repair_payload(payload, entries)
    repair_stats["timestamps_updated"] += second_pass["timestamps_updated"]
    repair_stats["matched_index"] = max(repair_stats["matched_index"], second_pass["matched_index"])
    refresh_editorial_metadata(payload)

    payload["ctv_locality_repair"] = {
        **repair_stats,
        **discovery_stats,
        "index_entries": len(entries),
        "landing_candidates": len(landing_urls),
        "index_error": index_error,
        "landing_error": landing_error,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }
    NEWS_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    message = (
        "CTV London backstop: "
        f"{repair_stats['reclassified']} Canada-owned London record(s) restored; "
        f"{discovery_stats['added']} missing first-party story/stories added; "
        f"{repair_stats['timestamps_updated']} timestamp(s) refreshed; "
        f"{len(entries)} Google index entries; {len(landing_urls)} landing-page candidates"
    )
    if index_error:
        message += f"; index unavailable: {index_error}"
    if landing_error:
        message += f"; landing discovery unavailable: {landing_error}"
    print(message)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
