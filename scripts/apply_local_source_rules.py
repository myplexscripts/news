#!/usr/bin/env python3
"""Apply the explicit London-source contract after story-level scope annotation.

The Local feed is the union of:
1. stories published by a defined London-area source, and
2. stories from any other publisher that the existing locality scorer identifies
   as being from or about London, Ontario.
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
NEWS_FILE = ROOT / "data" / "news.json"

SOURCE_ALIASES = {
    "CTV News": "CTV News London",
}

# Direct local publishers and institutions confirmed for the Local feed.
LOCAL_SOURCES = {
    "104.7 Heart FM",
    "106.9 The X",
    "CBC News London",
    "CTV News London",
    "City of London Newsroom",
    "Environment Canada London Alerts",
    "Fanshawe College Newsroom",
    "Global News London",
    "London District Catholic School Board",
    "London Free Press",
    "London Health Sciences Centre",
    "London Police Service",
    "London Transit Commission",
    "Middlesex County",
    "Middlesex-London Health Unit",
    "St. Joseph's Health Care London",
    "Thames Valley District School Board",
    "Western News",
    # Keep this if it is discovered even though it is not currently a direct source.
    "London Fire Department",
}


def canonical_source(value: Any) -> str:
    name = str(value or "").strip()
    return SOURCE_ALIASES.get(name, name)


def normalise_story_names(story: dict[str, Any]) -> None:
    source = canonical_source(story.get("source"))
    if source:
        story["source"] = source

    discovery = canonical_source(story.get("discovery_via"))
    if discovery:
        story["discovery_via"] = discovery

    cluster_sources = story.get("cluster_sources")
    if isinstance(cluster_sources, list):
        seen: set[str] = set()
        normalised: list[str] = []
        for value in cluster_sources:
            name = canonical_source(value)
            if not name or name in seen:
                continue
            seen.add(name)
            normalised.append(name)
        story["cluster_sources"] = normalised
        if normalised:
            story["cluster_source_count"] = len(normalised)


def apply_rules(payload: dict[str, Any]) -> dict[str, Any]:
    counts: Counter[str] = Counter()

    for story in payload.get("stories") or []:
        if not isinstance(story, dict):
            continue
        normalise_story_names(story)

        # Direct London-area sources are always Local. For every other publisher,
        # keep the story-level result produced by annotate_scopes.py.
        if canonical_source(story.get("source")) in LOCAL_SOURCES:
            story["scope"] = "local"
            if str(story.get("category") or "").strip() == "Canada":
                story["category"] = "Local"

        scope = "local" if str(story.get("scope") or "").lower() == "local" else "canada"
        story["scope"] = scope
        counts[scope] += 1

    for health in payload.get("source_health") or []:
        if not isinstance(health, dict):
            continue
        source = canonical_source(health.get("source"))
        health["source"] = source
        if source in LOCAL_SOURCES:
            health["scope"] = "local"

    payload["scope_schema_version"] = max(int(payload.get("scope_schema_version") or 0), 4)
    payload["scope_counts"] = {
        "local": counts.get("local", 0),
        "canada": counts.get("canada", 0),
        "all": counts.get("local", 0) + counts.get("canada", 0),
    }
    return payload


def main() -> int:
    if not NEWS_FILE.exists():
        print(f"Local-source rules skipped: {NEWS_FILE} does not exist")
        return 0

    payload = json.loads(NEWS_FILE.read_text(encoding="utf-8"))
    apply_rules(payload)
    NEWS_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    counts = payload.get("scope_counts") or {}
    print(
        "Explicit local-source rules applied: "
        f"local={counts.get('local', 0)} "
        f"canada={counts.get('canada', 0)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
