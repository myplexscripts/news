from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


ARTICLE_KEYS = {
    "author",
    "image",
    "image_alt",
    "image_caption",
    "article_images",
    "content_status",
    "paragraphs",
    "content_blocks",
    "content",
    "word_count",
    "quality",
    "scraped_at",
    "extraction_schema",
    "ingestion_path",
    "body_transport",
    "reader_schema",
    "reader_method",
    "reader_status",
    "reader_attempted_at",
    "reader_checked_at",
    "structure_schema",
    "structure_method",
    "structure_status",
    "structure_richness",
    "structured_at",
    "structure_attempted_at",
    "media_schema",
    "media_attempted_at",
    "media_method",
    "rich_article_schema",
    "rich_article_method",
    "rich_article_attempted_at",
    "rich_article_inserted_blocks",
    "rich_article_stats",
    "article_format_state",
    "article_hygiene_flags",
    "sanitize_schema",
    "content_truncated_reason",
    "cbc_lite_url",
    "cbc_media_hydrated",
    "cbc_images_cached",
    "cbc_image_hotlink",
    "cbc_reader_repair_schema",
    "cbc_reader_checked_at",
    "cbc_reader_repair_error",
    "national_post_promo_cleaned_at",
}

TOP_LEVEL_ARTICLE_KEYS = {
    "last_enrichment_at",
    "last_enrichment_count",
    "rich_article_schema",
    "sanitize_schema",
    "cbc_reader_repair_schema",
}


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def rich_counts(story: dict[str, Any]) -> tuple[int, int]:
    blocks = story.get("content_blocks") if isinstance(story.get("content_blocks"), list) else []
    media = sum(1 for block in blocks if isinstance(block, dict) and block.get("type") in {"image", "media"})
    structure = sum(1 for block in blocks if isinstance(block, dict) and block.get("type") in {"heading", "quote", "list"})
    return media, structure


def article_score(story: dict[str, Any]) -> int:
    status = str(story.get("content_status") or "").lower()
    status_rank = {"failed": 0, "summary": 1, "partial": 2, "full": 3}.get(status, 0)
    try:
        word_count = int(story.get("word_count") or 0)
    except (TypeError, ValueError):
        word_count = 0
    if word_count <= 0:
        content = str(story.get("content") or "")
        word_count = len(content.split())
    try:
        quality = int((story.get("quality") or {}).get("score") or 0)
    except (TypeError, ValueError, AttributeError):
        quality = 0
    media, structure = rich_counts(story)
    rich_schema = int(story.get("rich_article_schema") or 0)
    return (
        status_rank * 10_000
        + min(word_count, 5_000)
        + min(quality, 100) * 8
        + media * 180
        + structure * 70
        + rich_schema * 250
    )


def should_preserve_article(current: dict[str, Any], fresh: dict[str, Any]) -> bool:
    current_score = article_score(current)
    fresh_score = article_score(fresh)
    if current_score > fresh_score:
        return True
    if current_score < fresh_score:
        return False

    current_rich = int(current.get("rich_article_schema") or 0)
    fresh_rich = int(fresh.get("rich_article_schema") or 0)
    if current_rich != fresh_rich:
        return current_rich > fresh_rich

    current_scraped = str(current.get("scraped_at") or current.get("rich_article_attempted_at") or "")
    fresh_scraped = str(fresh.get("scraped_at") or fresh.get("rich_article_attempted_at") or "")
    return bool(current_scraped and current_scraped > fresh_scraped)


def merge_story(fresh: dict[str, Any], current: dict[str, Any] | None) -> tuple[dict[str, Any], bool]:
    if not current or not should_preserve_article(current, fresh):
        return dict(fresh), False

    merged = dict(fresh)
    for key in ARTICLE_KEYS:
        if key in current:
            merged[key] = current[key]
        elif key in merged:
            merged.pop(key, None)
    return merged, True


def recompute_counts(payload: dict[str, Any]) -> None:
    stories = [story for story in (payload.get("stories") or []) if isinstance(story, dict)]
    payload["story_count"] = len(stories)
    payload["full_story_count"] = sum(1 for story in stories if story.get("content_status") == "full")
    payload["partial_story_count"] = sum(1 for story in stories if story.get("content_status") == "partial")
    scores = [int((story.get("quality") or {}).get("score") or 0) for story in stories if isinstance(story.get("quality"), dict)]
    payload["average_quality"] = round(sum(scores) / len(scores)) if scores else 0


def merge(fresh_path: Path, current_path: Path, output_path: Path) -> tuple[int, int]:
    fresh_payload = load(fresh_path)
    current_payload = load(current_path)
    current_by_id = {
        str(story.get("id")): story
        for story in (current_payload.get("stories") or [])
        if isinstance(story, dict) and story.get("id")
    }

    preserved = 0
    stories: list[dict[str, Any]] = []
    for fresh_story in fresh_payload.get("stories") or []:
        if not isinstance(fresh_story, dict):
            continue
        current_story = current_by_id.get(str(fresh_story.get("id") or ""))
        merged_story, kept = merge_story(fresh_story, current_story)
        preserved += int(kept)
        stories.append(merged_story)

    fresh_payload["stories"] = stories
    for key in TOP_LEVEL_ARTICLE_KEYS:
        if key in current_payload:
            fresh_payload[key] = current_payload[key]
    recompute_counts(fresh_payload)
    output_path.write_text(json.dumps(fresh_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return preserved, len(stories)


def main() -> int:
    parser = argparse.ArgumentParser(description="Merge fresh headline metadata without erasing newer rich article content")
    parser.add_argument("fresh_snapshot", type=Path)
    parser.add_argument("current_feed", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    preserved, story_count = merge(args.fresh_snapshot, args.current_feed, args.output)
    print(f"Protected richer article content for {preserved}/{story_count} refreshed stories")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
