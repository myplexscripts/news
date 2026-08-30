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
SOURCE_SCOPES = {
    source.name: (source.scope if source.scope in VALID_SCOPES else "local")
    for source in SOURCES
}


def scope_for_story(story: dict[str, Any]) -> str:
    source = str(story.get("source") or "").strip()
    if source in SOURCE_SCOPES:
        return SOURCE_SCOPES[source]

    discovery = str(story.get("discovery_via") or "").strip()
    if discovery in SOURCE_SCOPES:
        return SOURCE_SCOPES[discovery]

    existing = str(story.get("scope") or "").strip().lower()
    return existing if existing in VALID_SCOPES else "local"


def annotate_payload(payload: dict[str, Any]) -> dict[str, Any]:
    stories = payload.get("stories") or []
    counts: Counter[str] = Counter()

    for story in stories:
        if not isinstance(story, dict):
            continue
        scope = scope_for_story(story)
        story["scope"] = scope
        counts[scope] += 1

        # The collector historically used Local as the catch-all category. Once
        # national sources are introduced, make that fallback explicit instead of
        # labelling a federal/national story as local London news.
        if scope == "canada" and str(story.get("category") or "").strip() in {"", "Local"}:
            story["category"] = "Canada"

    for health in payload.get("source_health") or []:
        if not isinstance(health, dict):
            continue
        source = str(health.get("source") or "").strip()
        health["scope"] = SOURCE_SCOPES.get(source, "local")

    payload["scope_schema_version"] = 1
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
