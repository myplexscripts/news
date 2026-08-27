from __future__ import annotations

import re
import subprocess
import sys
from difflib import SequenceMatcher
from typing import Any, Callable
from urllib.parse import urlparse

import requests

import fetch_news
import ranking


CBC_HOSTS = {"cbc.ca", "www.cbc.ca", "rss.cbc.ca"}
CBC_FEEDS = (
    "https://www.cbc.ca/webfeed/rss/rss-canada-london",
    "https://rss.cbc.ca/lineup/canada-london.xml",
)
RETIRED_SOURCE_NAMES = {"London Fire Department"}

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
            "london international airport",
            "london airport",
            "yxu airport",
            "fly yxu",
        )),
    )

# Generic crime words should not be enough to merge two unrelated police
# stories. The richer body-aware comparison below still keeps distinctive event
# terms such as child, sexual, abuse and material.
ranking.STOPWORDS.update({
    "charge", "charged", "charges", "charging",
    "investigation", "investigations", "officer", "officers",
    "suspect", "suspects", "person", "people",
})


def _contains_term(haystack: str, needle: str) -> bool:
    needle = str(needle or "").strip().lower()
    if not needle:
        return False
    return bool(re.search(rf"(?<![a-z0-9]){re.escape(needle)}(?![a-z0-9])", haystack))


def _safe_classify(title: str, summary: str, source: str) -> str:
    haystack = f"{title} {summary} {source}".lower().replace("’", "'")

    # Sports language gets an explicit first pass so names such as Rancourt do
    # not accidentally match the Public Safety keyword "court".
    if any(_contains_term(haystack, term) for term in SPORTS_TERMS):
        return "Sports"

    for category, needles in fetch_news.CATEGORY_RULES:
        if any(_contains_term(haystack, word) for word in needles):
            return category
    return "Local"


def _locality_story(story: dict[str, Any]) -> dict[str, Any]:
    """Remove known false geographic phrases before locality scoring."""
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


def _curl_response(url: str, timeout: int | float | None = None) -> requests.Response:
    max_time = max(6, min(10, int(float(timeout or 8))))
    command = [
        "curl",
        "--http1.1",
        "--location",
        "--fail",
        "--silent",
        "--show-error",
        "--compressed",
        "--connect-timeout", "4",
        "--max-time", str(max_time),
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


def _bounded_cbc_items(source: fetch_news.Source, existing: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """Try two first-party CBC feeds quickly, then let Scoop retain cached CBC stories."""
    attempts: list[str] = []
    for feed_url in CBC_FEEDS:
        candidate = fetch_news.Source(
            name=source.name,
            logo=getattr(source, "logo", ""),
            url=feed_url,
            kind="rss",
            homepage=source.homepage,
            accent=source.accent,
            max_items=source.max_items,
        )
        try:
            items = fetch_news.rss_items(candidate, existing, request_timeout=5)
            if items:
                for item in items:
                    item["ingestion_path"] = "cbc-rss" if feed_url == CBC_FEEDS[0] else "cbc-rss-fallback"
                if feed_url != CBC_FEEDS[0]:
                    print(f"CBC News London: primary feed unavailable; using {feed_url}", file=sys.stderr)
                return items
            attempts.append(f"{feed_url}: no items")
        except Exception as exc:
            attempts.append(f"{feed_url}: {str(exc)[:140]}")

    raise RuntimeError("CBC first-party feeds unavailable; cached CBC stories retained: " + " | ".join(attempts))


def _similarity_text(story: dict[str, Any]) -> str:
    paragraphs = story.get("paragraphs") or []
    if not isinstance(paragraphs, list):
        paragraphs = []
    body = " ".join(ranking._clean(value) for value in paragraphs[:3])
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
    title_ratio = SequenceMatcher(None, left_title, right_title).ratio()
    entity_overlap = bool(ranking._story_entities(left) & ranking._story_entities(right))
    score = (title_ratio * 0.48) + (containment * 0.36) + (jaccard * 0.16)
    if entity_overlap:
        score += 0.05
    score = min(1.0, score)
    return score, {
        "title": round(title_ratio, 3),
        "containment": round(containment, 3),
        "jaccard": round(jaccard, 3),
        "shared": float(len(shared)),
        "entity": 1.0 if entity_overlap else 0.0,
    }


def _body_aware_should_cluster(left: dict[str, Any], right: dict[str, Any]) -> bool:
    delta_hours = abs((ranking._dt(left.get("published")) - ranking._dt(right.get("published"))).total_seconds()) / 3600
    if delta_hours > ranking.CLUSTER_WINDOW_HOURS:
        return False

    score, parts = _body_aware_story_similarity(left, right)
    shared = int(parts.get("shared", 0))
    same_source = ranking._clean(left.get("source")) == ranking._clean(right.get("source"))

    if same_source:
        return bool(parts.get("title", 0) >= 0.86 or (parts.get("containment", 0) >= 0.82 and shared >= 5))

    if parts.get("title", 0) >= 0.80 and shared >= 3:
        return True
    if parts.get("containment", 0) >= 0.64 and shared >= 4 and score >= 0.58:
        return True
    if parts.get("entity", 0) and shared >= 4 and score >= 0.60:
        return True
    # Short wire-style summaries can use very different headlines from the full
    # first-party report. Four distinctive shared terms inside 30 hours is a
    # strong same-event signal once generic crime/news words are removed.
    if delta_hours <= 30 and shared >= 4 and parts.get("containment", 0) >= 0.60:
        return True
    return False


def _publication_filter(stories: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    kept: list[dict[str, Any]] = []
    dropped: list[dict[str, Any]] = []

    for story in stories:
        source = str(story.get("source") or "")
        if source in RETIRED_SOURCE_NAMES:
            dropped.append({
                "id": story.get("id", ""),
                "source": source,
                "title": story.get("title", ""),
                "local_score": 0,
                "threshold": "retired",
                "reasons": ["retired source"],
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
            "id": story.get("id", ""),
            "source": source,
            "title": story.get("title", ""),
            "local_score": score,
            "threshold": threshold,
            "reasons": reasons,
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
