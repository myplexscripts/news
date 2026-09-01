#!/usr/bin/env python3
"""Apply the explicit Forest City News source-scope contract.

Local is a strict publisher whitelist. Story text, discovery source, locality score,
and article topic do not promote a national publisher into Local.
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
NEWS_FILE = ROOT / "data" / "news.json"

# Exact London-area publishers/institutions confirmed for the Local feed.
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
    "London Fire Department",
    "London Free Press",
    "London Health Sciences Centre",
    "London Police Service",
    "London Transit Commission",
    "Middlesex County",
    "Middlesex-London Health Unit",
    "St. Joseph's Health Care London",
    "Thames Valley District School Board",
    "Western News",
}


def _record_urls(record: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for key in ("url", "link", "canonical_url", "original_url", "homepage", "source_url"):
        value = str(record.get(key) or "").strip()
        if value:
            values.append(value)
    return values


def is_ctv_london_record(record: dict[str, Any]) -> bool:
    """Only CTV's London edition is Local."""
    for value in _record_urls(record):
        try:
            parsed = urlparse(value)
        except Exception:
            continue
        host = parsed.netloc.lower().split(":", 1)[0]
        path = parsed.path.lower()
        if host in {"ctvnews.ca", "www.ctvnews.ca"} and (path == "/london" or path.startswith("/london/")):
            return True
    return False


def canonical_source(value: Any, record: dict[str, Any] | None = None) -> str:
    name = str(value or "").strip()
    if name == "CTV News" and record and is_ctv_london_record(record):
        return "CTV News London"
    return name


def normalise_story_names(story: dict[str, Any]) -> None:
    source = canonical_source(story.get("source"), story)
    if source:
        story["source"] = source

    cluster_sources = story.get("cluster_sources")
    if isinstance(cluster_sources, list):
        seen: set[str] = set()
        normalised: list[str] = []
        for value in cluster_sources:
            name = str(value or "").strip()
            if name == "CTV News" and is_ctv_london_record(story):
                name = "CTV News London"
            if not name or name in seen:
                continue
            seen.add(name)
            normalised.append(name)
        story["cluster_sources"] = normalised
        if normalised:
            story["cluster_source_count"] = len(normalised)


def scope_for_story(story: dict[str, Any]) -> str:
    source = canonical_source(story.get("source"), story)
    return "local" if source in LOCAL_SOURCES else "canada"


def apply_rules(payload: dict[str, Any]) -> dict[str, Any]:
    counts: Counter[str] = Counter()

    for story in payload.get("stories") or []:
        if not isinstance(story, dict):
            continue

        normalise_story_names(story)
        scope = scope_for_story(story)
        story["scope"] = scope
        counts[scope] += 1

        category = str(story.get("category") or "").strip()
        if scope == "local" and category == "Canada":
            story["category"] = "Local"
        elif scope == "canada" and category in {"", "Local"}:
            story["category"] = "Canada"

    for health in payload.get("source_health") or []:
        if not isinstance(health, dict):
            continue

        source = str(health.get("source") or "").strip()
        # Old source-health snapshots called the London collector "CTV News".
        # Only migrate that legacy health record when it was the local collector.
        if source == "CTV News" and (
            is_ctv_london_record(health)
            or str(health.get("scope") or "").strip().lower() == "local"
        ):
            source = "CTV News London"
        health["source"] = source
        health["scope"] = "local" if source in LOCAL_SOURCES else "canada"

    payload["scope_schema_version"] = 5
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
        "Strict local-source whitelist applied: "
        f"local={counts.get('local', 0)} "
        f"canada={counts.get('canada', 0)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
