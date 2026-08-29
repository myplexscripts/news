from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA_FILE = ROOT / "data" / "news.json"


ROUNDUP_TITLE_PATTERNS: dict[str, tuple[re.Pattern[str], ...]] = {
    "London Free Press": (
        re.compile(r"^\s*news\s+of\s+the\s+day\b", flags=re.I),
    ),
}


def is_redundant_roundup(story: dict[str, Any]) -> bool:
    source = str(story.get("source") or "").strip()
    title = str(story.get("title") or "").strip()
    if not source or not title:
        return False
    return any(pattern.search(title) for pattern in ROUNDUP_TITLE_PATTERNS.get(source, ()))


def _clean_editorial_metadata(payload: dict[str, Any], removed_ids: set[str]) -> None:
    if not removed_ids:
        return

    payload["top_story_ids"] = [
        story_id for story_id in payload.get("top_story_ids", [])
        if str(story_id) not in removed_ids
    ]

    cleaned_clusters: list[dict[str, Any]] = []
    for cluster in payload.get("editorial_clusters", []) or []:
        if not isinstance(cluster, dict):
            continue
        member_ids = [
            str(story_id) for story_id in cluster.get("member_ids", [])
            if str(story_id) not in removed_ids
        ]
        if not member_ids:
            continue
        updated = dict(cluster)
        updated["member_ids"] = member_ids
        updated["member_count"] = len(member_ids)
        if str(updated.get("representative_id") or "") in removed_ids:
            updated["representative_id"] = member_ids[0]
        cleaned_clusters.append(updated)

    payload["editorial_clusters"] = cleaned_clusters
    payload["cluster_count"] = len(cleaned_clusters)
    payload["multi_source_cluster_count"] = sum(
        1 for cluster in cleaned_clusters if int(cluster.get("source_count") or 0) > 1
    )


def filter_payload(payload: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    stories = payload.get("stories") or []
    if not isinstance(stories, list):
        return payload, []

    removed = [story for story in stories if isinstance(story, dict) and is_redundant_roundup(story)]
    if not removed:
        return payload, []

    removed_ids = {str(story.get("id") or "") for story in removed if story.get("id")}
    kept = [story for story in stories if not (isinstance(story, dict) and is_redundant_roundup(story))]

    payload["stories"] = kept
    payload["story_count"] = len(kept)
    payload["full_story_count"] = sum(1 for story in kept if story.get("content_status") == "full")
    payload["partial_story_count"] = sum(1 for story in kept if story.get("content_status") == "partial")
    payload["source_count"] = len({story.get("source") for story in kept if story.get("source")})
    _clean_editorial_metadata(payload, removed_ids)
    return payload, removed


def main() -> int:
    if not DATA_FILE.exists():
        print("Publication roundup filter: data/news.json not found")
        return 0

    payload = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    payload, removed = filter_payload(payload)
    if not removed:
        print("Publication roundup filter: no redundant roundup stories found")
        return 0

    DATA_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    labels = ", ".join(f"{story.get('source')}: {story.get('title')}" for story in removed)
    print(f"Publication roundup filter: removed {len(removed)} redundant story/stories ({labels})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
