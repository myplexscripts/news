#!/usr/bin/env python3
"""Fail CI if homepage deduplication, chronology, or scope filtering regresses."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TIMELINE = (ROOT / "src/lib/timelineStories.ts").read_text(encoding="utf-8")
HOME = (ROOT / "src/pages/index.astro").read_text(encoding="utf-8")
HOME_CSS = (ROOT / "src/styles/editorial-home.css").read_text(encoding="utf-8")
CARD = (ROOT / "src/components/NewsCard.astro").read_text(encoding="utf-8")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"Homepage feed contract failed: {message}")


def main() -> None:
    require("seenMultiSourceClusters" in TIMELINE, "homepage must collapse duplicate multi-source event clusters")
    require("sourceCount < 2 || !clusterId" in TIMELINE, "single-source stories must remain independent")
    require("const sorted = [...input].sort" in TIMELINE, "homepage clustering must keep the newest report from each cluster")
    require("const newestFirst = (pool) => collapseTimelineStories(pool)" in HOME, "homepage pools must be deduplicated before carousel selection")
    require("data-scope={story.scope || 'local'}" in CARD, "every homepage card must expose its own scope")
    require("timelineCards.forEach" in HOME and "cardMatches(item, query)" in HOME, "scope filtering must run across the full homepage timeline")
    require("const scopeMatch = activeScope === 'all' || itemScope === activeScope" in HOME, "every timeline card must respect Local, Canada, and All")
    require(".home-page .news-card.filtered-out" in HOME_CSS and "display: none !important" in HOME_CSS, "cards rejected by the homepage filter must actually be hidden")
    print("Homepage feed contracts passed: duplicate multi-source events collapse before carousel selection while chronology and scope filtering remain intact.")


if __name__ == "__main__":
    main()
