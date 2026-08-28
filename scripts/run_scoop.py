from __future__ import annotations

import re
import subprocess
import sys
from datetime import datetime, timezone
from difflib import SequenceMatcher
from typing import Any, Callable
from urllib.parse import urlparse

import feedparser
import requests
from bs4 import BeautifulSoup

import fetch_news
import ranking


CBC_HOSTS = {"cbc.ca", "www.cbc.ca", "rss.cbc.ca"}
CBC_FEEDS = (
    "https://www.cbc.ca/webfeed/rss/rss-canada-london",
    "https://rss.cbc.ca/lineup/canada-london.xml",
)
CBC_GOOGLE_NEWS_FEED = (
    "https://news.google.com/rss/search?"
    "q=site%3Acbc.ca%2Fnews%2Fcanada%2Flondon%20London%20Ontario%20when%3A3d&"
    "hl=en-CA&gl=CA&ceid=CA%3Aen"
)
RETIRED_SOURCE_NAMES = {"London Fire Department"}
SOURCE_JUNK_TITLES: dict[str, set[str]] = {
    "London Police Service": {
        "positions",
        "recruiting events",
        "caught on camera",
        "general releases",
        "london police service",
        "news post - no banner (1)",
    },
}

# These publishers carry material well outside London even when the feed or
# section is branded for the region. Dedicated London sources remain ungated.
PUBLICATION_MIN_LOCAL_SCORE: dict[str, int] = {
    "Global News London": 30,
    "CTV News": 25,
    "104.7 Heart FM": 25,
    "London Free Press": 35,
}

SPORTS_TERMS = (
    "western mustangs", "mustangs quarterback", "quarterback", "running back",
    "wide receiver", "football", "hockey", "basketball", "baseball", "soccer",
    "london knights", "london majors", "ohl", "oua", "playoffs", "training camp",
)

_original_local_relevance = ranking.local_relevance

if not any(label == "London airport" for _, label, _ in ranking.LOCAL_TERMS):
    ranking.LOCAL_TERMS = ranking.LOCAL_TERMS + (
        (26, "London airport", (
            "london international airport", "london airport", "yxu airport", "fly yxu",
        )),
    )

ranking.STOPWORDS.update({
    "charge", "charged", "charges", "charging", "investigation", "investigations",
    "officer", "officers", "suspect", "suspects", "person", "people",
})


def _contains_term(haystack: str, needle: str) -> bool:
    needle = str(needle or "").strip().lower()
    return bool(needle and re.search(rf"(?<![a-z0-9]){re.escape(needle)}(?![a-z0-9])", haystack))


def _safe_classify(title: str, summary: str, source: str) -> str:
    haystack = f"{title} {summary} {source}".lower().replace("’", "'")
    if any(_contains_term(haystack, term) for term in SPORTS_TERMS):
        return "Sports"
    for category, needles in fetch_news.CATEGORY_RULES:
        if any(_contains_term(haystack, word) for word in needles):
            return category
    return "Local"


def _locality_story(story: dict[str, Any]) -> dict[str, Any]:
    cleaned = dict(story)

    def scrub(value: Any) -> str:
        return re.sub(r"\blondon\s+bridge\b", "child care provider", str(value or ""), flags=re.I)

    cleaned["title"] = scrub(story.get("title"))
    cleaned["summary"] = scrub(story.get("summary"))
    paragraphs = story.get("paragraphs") or []
    if isinstance(paragraphs, list):
        cleaned["paragraphs"] = [scrub(value) for value in paragraphs]
    return cleaned


def _safe_local_relevance(story: dict[str, Any]) -> tuple[int, list[str]]:
    return _original_local_relevance(_locality_story(story))


def _is_cbc_url(url: str) -> bool:
    host = urlparse(str(url or "")).netloc.lower().split(":", 1)[0]
    return host in CBC_HOSTS or host.endswith(".cbc.ca")


def _cbc_london_url(url: str) -> str:
    candidate = fetch_news.canonical_url(str(url or "").strip())
    if not candidate or not _is_cbc_url(candidate):
        return ""
    if "/news/canada/london/" not in urlparse(candidate).path.lower():
        return ""
    return candidate


def _curl_response(url: str, timeout: int | float | None = None) -> requests.Response:
    max_time = max(6, min(10, int(float(timeout or 8))))
    command = [
        "curl", "--http1.1", "--location", "--fail", "--silent", "--show-error",
        "--compressed", "--connect-timeout", "4", "--max-time", str(max_time),
        "--user-agent", fetch_news.USER_AGENT,
        "--header", "Accept-Language: en-CA,en;q=0.9",
        "--header", "Accept: text/html,application/xhtml+xml,application/rss+xml,application/xml;q=0.9,*/*;q=0.8",
        url,
    ]
    result = subprocess.run(command, capture_output=True, check=False)
    if result.returncode != 0:
        message = result.stderr.decode("utf-8", "replace").strip() or f"curl exited {result.returncode}"
        raise requests.ConnectionError(f"CBC curl fallback failed: {message[:240]}")
    response = requests.Response()
    response.status_code = 200
    response.url = url
    response._content = result.stdout
    response.encoding = "utf-8"
    response.headers["X-London-News-Transport"] = "curl-fallback"
    return response


def _resilient_cbc_get(original_get: Callable[..., requests.Response]) -> Callable[..., requests.Response]:
    def get(url: str, *args: Any, **kwargs: Any) -> requests.Response:
        if not _is_cbc_url(url):
            return original_get(url, *args, **kwargs)
        first_error: Exception | None = None
        try:
            response = original_get(url, *args, **kwargs)
            if response.status_code < 400:
                return response
            if response.status_code not in {403, 408, 425, 429, 500, 502, 503, 504}:
                return response
            first_error = requests.HTTPError(f"CBC returned HTTP {response.status_code}")
        except requests.RequestException as exc:
            first_error = exc
        try:
            fallback = _curl_response(url, kwargs.get("timeout"))
            print(f"CBC transport fallback: curl succeeded for {url}", file=sys.stderr)
            return fallback
        except requests.RequestException:
            if first_error is not None:
                raise first_error
            raise
    return get


def _cbc_curl_feed_items(
    source: fetch_news.Source,
    existing: dict[str, dict[str, Any]],
    feed_url: str,
) -> list[dict[str, Any]]:
    """Read CBC London RSS with curl and do not touch CBC through requests."""
    response = _curl_response(feed_url, timeout=10)
    feed = feedparser.parse(response.content)
    items: list[dict[str, Any]] = []

    for entry in feed.entries[: source.max_items]:
        url = _cbc_london_url(entry.get("link") or entry.get("guid"))
        if not url:
            continue
        raw_title = fetch_news.clean_text(entry.get("title"))
        title = fetch_news.clean_story_title(raw_title, source.name)
        if not title:
            continue
        summary = fetch_news.clean_summary_text(
            entry.get("summary") or entry.get("description"),
            title,
        )
        published = entry.get("published") or entry.get("updated") or entry.get("created")
        identifier = fetch_news.make_id(url)
        basic = {
            "id": identifier,
            "title": title,
            "source": source.name,
            "source_home": source.homepage,
            "source_accent": source.accent,
            "url": url,
            "published": fetch_news.parse_date(published),
            "summary": summary,
            "image": fetch_news.image_from_entry(entry),
            "author": fetch_news.clean_text(entry.get("author")),
            "category": fetch_news.classify(title, summary, source.name),
        }

        old = existing.get(identifier) or existing.get(url)
        if old:
            merged = {**basic, **old}
            merged.update({
                "title": title,
                "source": source.name,
                "source_home": source.homepage,
                "source_accent": source.accent,
                "url": url,
                "published": basic["published"],
                "summary": summary or old.get("summary", ""),
                "ingestion_path": "cbc-curl-rss",
            })
            if basic["image"]:
                merged["image"] = basic["image"]
            items.append(merged)
        else:
            basic.update({
                "content_status": "summary",
                "paragraphs": [],
                "content_blocks": [],
                "scraped_at": datetime.now(timezone.utc).isoformat(),
                "extraction_schema": fetch_news.EXTRACTION_SCHEMA,
                "ingestion_path": "cbc-curl-rss",
                "word_count": len(summary.split()) if summary else 0,
            })
            basic["quality"] = fetch_news.extraction_quality(basic, {}, "rss:curl")
            items.append(basic)

    if not items:
        raise RuntimeError(f"CBC curl feed returned no London stories: {feed_url}")
    return items


def _existing_cbc_story_by_title(existing: dict[str, dict[str, Any]], title: str) -> dict[str, Any] | None:
    target = ranking._key(title)
    if not target:
        return None
    seen: set[int] = set()
    for story in existing.values():
        if not isinstance(story, dict) or id(story) in seen:
            continue
        seen.add(id(story))
        if str(story.get("source") or "") != "CBC News London":
            continue
        candidate = ranking._key(story.get("title"))
        if candidate and SequenceMatcher(None, target, candidate).ratio() >= 0.94:
            return story
    return None


def _cbc_google_news_items(source: fetch_news.Source, existing: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """Discover CBC London stories without requiring any connection to cbc.ca.

    Google News is only a transport and discovery fallback here. Stories retain
    CBC attribution. The Google News article URL redirects readers to CBC.
    """
    response = requests.get(
        CBC_GOOGLE_NEWS_FEED,
        headers={"User-Agent": fetch_news.USER_AGENT, "Accept-Language": "en-CA,en;q=0.9"},
        timeout=12,
    )
    response.raise_for_status()
    feed = feedparser.parse(response.content)
    items: list[dict[str, Any]] = []

    for entry in feed.entries[: max(source.max_items * 2, 40)]:
        source_meta = entry.get("source") or {}
        if isinstance(source_meta, dict):
            source_title = fetch_news.clean_text(source_meta.get("title"))
        else:
            source_title = fetch_news.clean_text(source_meta)
        raw_title = fetch_news.clean_text(entry.get("title"))
        looks_cbc = "cbc" in source_title.lower() or bool(re.search(r"\s+-\s+CBC(?: News)?\s*$", raw_title, flags=re.I))
        if not looks_cbc:
            continue

        title = re.sub(r"\s+-\s+CBC(?: News)?\s*$", "", raw_title, flags=re.I).strip()
        title = fetch_news.clean_story_title(title, source.name)
        if not title:
            continue

        url = fetch_news.canonical_url(entry.get("link") or entry.get("guid") or "")
        if not url or "news.google.com" not in urlparse(url).netloc.lower():
            continue

        raw_summary = entry.get("summary") or entry.get("description") or ""
        summary_text = BeautifulSoup(str(raw_summary), "html.parser").get_text(" ", strip=True)
        summary = fetch_news.clean_summary_text(summary_text, title)
        published = entry.get("published") or entry.get("updated") or entry.get("created")
        identifier = fetch_news.make_id(url)
        basic = {
            "id": identifier,
            "title": title,
            "source": source.name,
            "source_home": source.homepage,
            "source_accent": source.accent,
            "url": url,
            "published": fetch_news.parse_date(published),
            "summary": summary,
            "image": "",
            "author": "CBC News",
            "category": fetch_news.classify(title, summary, source.name),
        }

        old = _existing_cbc_story_by_title(existing, title)
        if old:
            merged = {**basic, **old}
            merged.update({
                "title": title,
                "source": source.name,
                "source_home": source.homepage,
                "source_accent": source.accent,
                "url": url,
                "published": basic["published"],
                "summary": summary or old.get("summary", ""),
                "ingestion_path": "cbc-google-news-fallback",
            })
            items.append(merged)
        else:
            basic.update({
                "content_status": "summary",
                "paragraphs": [],
                "content_blocks": [],
                "scraped_at": datetime.now(timezone.utc).isoformat(),
                "extraction_schema": fetch_news.EXTRACTION_SCHEMA,
                "ingestion_path": "cbc-google-news-fallback",
                "word_count": len(summary.split()) if summary else 0,
            })
            basic["quality"] = fetch_news.extraction_quality(basic, {}, "rss:google-cbc-fallback")
            items.append(basic)

        if len(items) >= source.max_items:
            break

    if not items:
        raise RuntimeError("CBC Google News fallback returned no CBC London stories")
    return items


def _bounded_cbc_items(source: fetch_news.Source, existing: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    attempts: list[str] = []
    for feed_url in CBC_FEEDS:
        try:
            items = _cbc_curl_feed_items(source, existing, feed_url)
            route = "primary" if feed_url == CBC_FEEDS[0] else "fallback"
            print(f"CBC News London: {len(items)} items via curl RSS ({route})", file=sys.stderr)
            return items
        except Exception as exc:
            attempts.append(f"{feed_url}: {str(exc)[:180]}")

    try:
        items = _cbc_google_news_items(source, existing)
        print(
            f"CBC News London: {len(items)} items via Google News fallback after CBC network failure",
            file=sys.stderr,
        )
        return items
    except Exception as exc:
        attempts.append(f"Google News fallback: {str(exc)[:180]}")

    raise RuntimeError("CBC discovery routes unavailable; cached CBC stories retained: " + " | ".join(attempts))


def _similarity_text(story: dict[str, Any]) -> str:
    paragraphs = story.get("paragraphs") or []
    if not isinstance(paragraphs, list):
        paragraphs = []
    body = " ".join(ranking._clean(value) for value in paragraphs[:8])
    return f"{story.get('title', '')} {story.get('summary', '')} {body}"


def _body_aware_story_similarity(left: dict[str, Any], right: dict[str, Any]) -> tuple[float, dict[str, float]]:
    left_title = ranking._key(left.get("title"))
    right_title = ranking._key(right.get("title"))
    if not left_title or not right_title:
        return 0.0, {}
    left_tokens = ranking._tokens(_similarity_text(left))
    right_tokens = ranking._tokens(_similarity_text(right))
    shared = left_tokens & right_tokens
    union = left_tokens | right_tokens
    jaccard = len(shared) / max(1, len(union))
    containment = len(shared) / max(1, min(len(left_tokens), len(right_tokens)))

    # Preserve a headline-only signal so very different article bodies do
    # not erase an otherwise distinctive cross-publisher event match.
    left_title_tokens = ranking._tokens(str(left.get("title") or ""))
    right_title_tokens = ranking._tokens(str(right.get("title") or ""))
    title_shared = left_title_tokens & right_title_tokens
    title_containment = len(title_shared) / max(1, min(len(left_title_tokens), len(right_title_tokens)))
    literal_title_ratio = SequenceMatcher(None, left_title, right_title).ratio()
    token_title_ratio = ranking.fuzz.token_set_ratio(left_title, right_title) / 100.0
    title_ratio = max(literal_title_ratio, token_title_ratio * 0.96)
    entity_overlap = bool(ranking._story_entities(left) & ranking._story_entities(right))
    score = (title_ratio * 0.48) + (containment * 0.36) + (jaccard * 0.16)
    if entity_overlap:
        score += 0.05
    return min(1.0, score), {
        "title": round(title_ratio, 3),
        "literal_title": round(literal_title_ratio, 3),
        "token_title": round(token_title_ratio, 3),
        "containment": round(containment, 3),
        "jaccard": round(jaccard, 3),
        "shared": float(len(shared)),
        "title_containment": round(title_containment, 3),
        "title_shared": float(len(title_shared)),
        "entity": 1.0 if entity_overlap else 0.0,
    }


def _body_aware_should_cluster(left: dict[str, Any], right: dict[str, Any]) -> bool:
    delta_hours = abs((ranking._dt(left.get("published")) - ranking._dt(right.get("published"))).total_seconds()) / 3600
    if delta_hours > ranking.CLUSTER_WINDOW_HOURS:
        return False
    score, parts = _body_aware_story_similarity(left, right)
    shared = int(parts.get("shared", 0))
    title_shared = int(parts.get("title_shared", 0))
    same_source = ranking._clean(left.get("source")) == ranking._clean(right.get("source"))
    if same_source:
        return bool(parts.get("literal_title", 0) >= 0.86 or (parts.get("containment", 0) >= 0.82 and shared >= 5))
    if parts.get("literal_title", 0) >= 0.80 and shared >= 3:
        return True
    if (
        parts.get("token_title", 0) >= 0.84
        and parts.get("title_containment", 0) >= 0.72
        and title_shared >= 4
    ):
        return True
    if parts.get("containment", 0) >= 0.64 and shared >= 4 and score >= 0.58:
        return True
    if parts.get("entity", 0) and shared >= 4 and score >= 0.60:
        return True
    return bool(delta_hours <= 30 and shared >= 4 and parts.get("containment", 0) >= 0.60)


def _junk_reason(story: dict[str, Any]) -> str:
    source = str(story.get("source") or "").strip()
    title = re.sub(r"\s+", " ", str(story.get("title") or "")).strip().lower()
    if title in SOURCE_JUNK_TITLES.get(source, set()):
        return "publisher navigation/template item"
    return ""


def _publication_filter(stories: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    kept: list[dict[str, Any]] = []
    dropped: list[dict[str, Any]] = []
    for story in stories:
        source = str(story.get("source") or "")
        junk_reason = _junk_reason(story)
        if junk_reason:
            dropped.append({
                "id": story.get("id", ""), "source": source, "title": story.get("title", ""),
                "local_score": 0, "threshold": "source-cleanup", "reasons": [junk_reason],
            })
            continue
        if source in RETIRED_SOURCE_NAMES:
            dropped.append({
                "id": story.get("id", ""), "source": source, "title": story.get("title", ""),
                "local_score": 0, "threshold": "retired", "reasons": ["retired source"],
            })
            continue
        threshold = PUBLICATION_MIN_LOCAL_SCORE.get(source)
        if threshold is None:
            kept.append(story)
            continue
        score, reasons = _safe_local_relevance(story)
        if score >= threshold:
            kept.append(story)
            continue
        dropped.append({
            "id": story.get("id", ""), "source": source, "title": story.get("title", ""),
            "local_score": score, "threshold": threshold, "reasons": reasons,
        })
    return kept, dropped


def _apply_local_editorial_policy(stories: list[dict[str, Any]], now=None):
    kept, dropped = _publication_filter(stories)
    if dropped:
        by_source: dict[str, int] = {}
        for item in dropped:
            by_source[item["source"]] = by_source.get(item["source"], 0) + 1
        summary = ", ".join(f"{source} {count}" for source, count in sorted(by_source.items()))
        print(f"Publication gate: removed {len(dropped)} stories ({summary})", file=sys.stderr)
    annotated, metadata = ranking.apply_editorial_intelligence(kept, now)
    metadata["locality_filtered_count"] = len(dropped)
    metadata["locality_filtered_by_source"] = {
        source: sum(1 for item in dropped if item["source"] == source)
        for source in sorted({item["source"] for item in dropped})
    }
    return annotated, metadata


def install_runtime_safeguards() -> None:
    if getattr(fetch_news, "_runtime_safeguards_installed", False):
        return
    fetch_news.FAST_SESSION.get = _resilient_cbc_get(fetch_news.FAST_SESSION.get)
    fetch_news.SESSION.get = _resilient_cbc_get(fetch_news.SESSION.get)
    fetch_news.cbc_items = _bounded_cbc_items
    fetch_news.classify = _safe_classify
    ranking.local_relevance = _safe_local_relevance
    ranking.story_similarity = _body_aware_story_similarity
    ranking._should_cluster = _body_aware_should_cluster
    fetch_news.apply_editorial_intelligence = _apply_local_editorial_policy
    fetch_news._runtime_safeguards_installed = True


def main() -> int:
    install_runtime_safeguards()
    return fetch_news.main()


if __name__ == "__main__":
    raise SystemExit(main())
