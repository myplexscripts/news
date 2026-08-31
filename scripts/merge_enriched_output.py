from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


# Feed freshness, clustering and card-cache fields belong to the fast publisher.
# Everything else may be improved by the slower article enrichment pass.
PROTECTED_STORY_KEYS = {
    "id",
    "published",
    "scope",
    "card_image",
    "card_image_small",
    "cluster_id",
    "cluster_size",
    "cluster_source_count",
    "cluster_sources",
    "cluster_member_ids",
    "cluster_representative_id",
    "cluster_representative",
    "cluster_local_score",
    "cluster_freshness_score",
    "cluster_latest_published",
    "rank_score",
    "ranking_reasons",
    "freshness_score",
    "local_score",
    "local_reasons",
    "image_score",
    "source_health_status",
    "hero_eligible",
    "story_topics",
}


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def merge_story(latest: dict[str, Any], enriched: dict[str, Any]) -> dict[str, Any]:
    merged = dict(latest)
    for key, value in enriched.items():
        if key in PROTECTED_STORY_KEYS:
            continue
        merged[key] = value
    return merged


def recompute_counts(payload: dict[str, Any]) -> None:
    stories = [story for story in (payload.get("stories") or []) if isinstance(story, dict)]
    payload["story_count"] = len(stories)
    payload["full_story_count"] = sum(1 for story in stories if story.get("content_status") == "full")
    payload["partial_story_count"] = sum(1 for story in stories if story.get("content_status") == "partial")
    scores = [int((story.get("quality") or {}).get("score") or 0) for story in stories if story.get("quality")]
    payload["average_quality"] = round(sum(scores) / len(scores)) if scores else 0


def merge(enriched_path: Path, latest_path: Path, output_path: Path) -> tuple[int, int]:
    enriched_payload = load(enriched_path)
    latest_payload = load(latest_path)

    enriched_by_id = {
        str(story.get("id")): story
        for story in (enriched_payload.get("stories") or [])
        if isinstance(story, dict) and story.get("id")
    }

    merged_count = 0
    stories = []
    for latest_story in latest_payload.get("stories") or []:
        if not isinstance(latest_story, dict):
            continue
        story_id = str(latest_story.get("id") or "")
        enriched_story = enriched_by_id.get(story_id)
        if enriched_story is None:
            stories.append(latest_story)
            continue
        stories.append(merge_story(latest_story, enriched_story))
        merged_count += 1

    latest_payload["stories"] = stories
    for key in ("last_enrichment_at", "last_enrichment_count"):
        if key in enriched_payload:
            latest_payload[key] = enriched_payload[key]
    recompute_counts(latest_payload)

    output_path.write_text(json.dumps(latest_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return merged_count, len(stories)


def main() -> int:
    parser = argparse.ArgumentParser(description="Merge deferred article enrichment into the newest published feed")
    parser.add_argument("enriched_snapshot", type=Path)
    parser.add_argument("latest_feed", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    merged_count, story_count = merge(args.enriched_snapshot, args.latest_feed, args.output)
    print(f"Merged enrichment into {merged_count}/{story_count} current stories")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
