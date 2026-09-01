#!/usr/bin/env python3
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from sources import SOURCES

ROOT = Path(__file__).resolve().parents[1]
NEWS_FILE = ROOT / "data" / "news.json"
VALID_SCOPES = {"local", "canada"}
LOCAL_SCOPE_MIN_SCORE = 25
SOURCE_SCOPES = {
    source.name: (source.scope if source.scope in VALID_SCOPES else "local")
    for source in SOURCES
}

# These publishers are themselves London-area institutions, so their own news is
# inherently local even when the headline does not repeat the city name.
ALWAYS_LOCAL_SOURCES = {
    "City of London Newsroom",
    "London Police Service",
    "London Fire Department",
    "Middlesex-London Health Unit",
    "London Health Sciences Centre",
    "St. Joseph's Health Care London",
    "Western News",
    "Fanshawe College Newsroom",
    "Thames Valley District School Board",
    "London District Catholic School Board",
    "London Transit Commission",
    "Middlesex County",
    "Environment Canada London Alerts",
}


def _source_scope(name: str) -> str:
    return SOURCE_SCOPES.get(str(name or "").strip(), "")


def _has_story_level_local_evidence(story: dict[str, Any]) -> bool:
    """Require London-area evidence beyond the publisher's local-feed prior."""
    try:
        score = int(story.get("local_score") or 0)
    except (TypeError, ValueError):
        score = 0
    if score < LOCAL_SCOPE_MIN_SCORE:
        return False

    reasons = story.get("local_reasons") or []
    if not isinstance(reasons, list):
        return False

    for reason in reasons:
        text = str(reason or "").strip().lower()
        if not text:
            continue
        if text.startswith("local publisher"):
            continue
        # Negative locality evidence, such as London, UK, must never qualify a
        # story for the London feed.
        if " -" in text or "london, uk" in text or "united kingdom" in text:
            continue
        return True
    return False


def scope_for_story(story: dict[str, Any]) -> str:
    source = str(story.get("source") or "").strip()
    discovery = str(story.get("discovery_via") or "").strip()

    # National collections stay in Canada. A London-focused version of an event
    # will normally also be available from the local collectors.
    if _source_scope(source) == "canada" or _source_scope(discovery) == "canada":
        return "canada"

    if source in ALWAYS_LOCAL_SOURCES:
        return "local"

    # Newsroom feeds such as CBC London, CTV London, Global London and the Free
    # Press occasionally carry broader Ontario or Canadian stories. Those only
    # belong in Local when the story itself contains London-area evidence.
    if _has_story_level_local_evidence(story):
        return "local"

    return "canada"


def annotate_payload(payload: dict[str, Any]) -> dict[str, Any]:
    stories = payload.get("stories") or []
    counts: Counter[str] = Counter()

    for story in stories:
        if not isinstance(story, dict):
            continue
        scope = scope_for_story(story)
        story["scope"] = scope
        counts[scope] += 1

        category = str(story.get("category") or "").strip()
        if scope == "canada" and category in {"", "Local"}:
            story["category"] = "Canada"
        elif scope == "local" and category == "Canada":
            story["category"] = "Local"

    # Source health describes where a collector comes from, not whether every
    # story that collector publishes is locally relevant.
    for health in payload.get("source_health") or []:
        if not isinstance(health, dict):
            continue
        source = str(health.get("source") or "").strip()
        health["scope"] = SOURCE_SCOPES.get(source, "local")

    payload["scope_schema_version"] = 2
    payload["scope_counts"] = {
        "local": counts.get("local", 0),
        "canada": counts.get("canada", 0),
        "all": counts.get("local", 0) + counts.get("canada", 0),
    }
    return payload


def main() -> int:
    if not NEWS_FILE.exists():
        print(f"Scope annotation skipped: {NEWS_FILE} does not exist")
        return 0

    payload = json.loads(NEWS_FILE.read_text(encoding="utf-8"))
    annotate_payload(payload)
    NEWS_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    counts = payload.get("scope_counts") or {}
    print(
        "Story scopes: "
        f"local={counts.get('local', 0)} "
        f"canada={counts.get('canada', 0)} "
        f"all={counts.get('all', 0)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
