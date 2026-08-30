#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import feedparser
import requests
from dateutil import parser as date_parser

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


def _is_ctv_london_url(value: Any) -> bool:
    try:
        parsed = urlparse(str(value or ""))
    except Exception:
        return False
    host = parsed.netloc.lower().split(":", 1)[0]
    if host not in {"ctvnews.ca", "www.ctvnews.ca"}:
        return False
    return parsed.path.lower().startswith("/london/article/")


def _entry_source_name(entry: Any) -> str:
    source = entry.get("source") or {}
    if isinstance(source, dict):
        return _clean(source.get("title") or source.get("value"))
    return _clean(source)


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
    """Repair CTV London stories that were overwritten by the Canada collector.

    CTV's Canada landing page can surface the same /london/article/ URL after the
    dedicated London source has already collected it. The shared URL/id then causes
    the later Canada-source copy to win during merging, which incorrectly moves a
    London story into the Canada feed. Restore London ownership by canonical URL.

    CTV article metadata can also lag the current landing page. Google News RSS is
    used only as an external timestamp cross-check for titles already collected from
    CTV itself. It never creates a new article or replaces the first-party URL/body.
    """
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

        # Ignore obviously stale/future search-index timestamps. Google News is a
        # freshness cross-check, not the canonical historical archive.
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

    # Keep source health honest when London-path records were accidentally counted
    # under the Canada source. This is presentation metadata only; the collector
    # remains responsible for its detailed quality metrics on the next full run.
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


def main() -> int:
    if not NEWS_FILE.exists():
        print(f"CTV locality repair skipped: {NEWS_FILE} does not exist")
        return 0

    payload = json.loads(NEWS_FILE.read_text(encoding="utf-8"))
    entries: list[Any] = []
    index_error = ""
    try:
        entries = fetch_ctv_index_entries()
    except Exception as exc:
        index_error = str(exc)[:240]

    payload, stats = repair_payload(payload, entries)
    payload["ctv_locality_repair"] = {
        **stats,
        "index_entries": len(entries),
        "index_error": index_error,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }
    NEWS_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    message = (
        "CTV locality repair: "
        f"{stats['reclassified']} Canada-owned London record(s) restored; "
        f"{stats['timestamps_updated']} timestamp(s) refreshed from "
        f"{stats['matched_index']} matched Google News title(s)"
    )
    if index_error:
        message += f"; timestamp index unavailable: {index_error}"
    print(message)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
