#!/usr/bin/env python3
"""Fail CI if homepage chronology or scope filtering regresses."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TIMELINE = (ROOT / "src/lib/timelineStories.ts").read_text(encoding="utf-8")
HOME = (ROOT / "src/pages/index.astro").read_text(encoding="utf-8")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"Homepage feed contract failed: {message}")


def main() -> None:
    require("seenMultiSourceClusters" not in TIMELINE, "homepage must not collapse articles by event cluster")
    require("cluster_latest_published: story.published || story.cluster_latest_published" in TIMELINE, "homepage cards must use each article's own publication time")
    require("data-scope={story.scope || 'local'}" in (ROOT / "src/components/NewsCard.astro").read_text(encoding="utf-8"), "every homepage card must expose its own scope")
    require("timelineCards.forEach" in HOME and "cardMatches(item, query)" in HOME, "scope filtering must run across the full homepage timeline")
    require("const scopeMatch = activeScope === 'all' || itemScope === activeScope" in HOME, "every timeline card must respect Local, Canada, and All")
    print("Homepage feed contracts passed: every article remains independent, chronological, and scope-filterable.")


if __name__ == "__main__":
    main()
