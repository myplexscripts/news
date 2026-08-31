from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import fetch_news
import run_scoop


_original_enrich_article = fetch_news.enrich_article


def _has_reader_body(story: dict[str, Any]) -> bool:
    paragraphs = story.get("paragraphs")
    blocks = story.get("content_blocks")
    return bool(
        (isinstance(paragraphs, list) and any(str(item or "").strip() for item in paragraphs))
        or (isinstance(blocks, list) and len(blocks) > 0)
        or str(story.get("content") or "").strip()
    )


def _metadata_first_enrich(story: dict[str, Any], source: fetch_news.Source) -> dict[str, Any]:
    """Publish useful feed metadata without blocking on full article extraction.

    First-party page sources still need their article page opened to discover a title,
    summary and hero image, so those fall through to the normal extractor. Google
    News discovery also needs the normal extractor to resolve its redirect.
    """
    title = str(story.get("title") or "").strip()
    url = str(story.get("url") or "").strip()

    if source.kind == "google_topic" or not title or not url:
        enriched = _original_enrich_article(story, source)
        enriched["refresh_stage"] = "enriched"
        enriched["enriched_at"] = datetime.now(timezone.utc).isoformat()
        return enriched

    if _has_reader_body(story):
        story["refresh_stage"] = "enriched"
        return story

    now = datetime.now(timezone.utc).isoformat()
    story.setdefault("paragraphs", [])
    story.setdefault("content_blocks", [])
    story.setdefault("content", "")
    story["content_status"] = "summary"
    story["word_count"] = int(story.get("word_count") or len(str(story.get("summary") or "").split()))
    story["scraped_at"] = str(story.get("scraped_at") or now)
    story["discovered_at"] = str(story.get("discovered_at") or now)
    story["refresh_stage"] = "metadata"
    story["extraction_schema"] = fetch_news.EXTRACTION_SCHEMA
    story["quality"] = fetch_news.extraction_quality(story, {}, "fast:feed-metadata")
    return story


def _skip_backfill(stories, skip_sources=None):
    """Full article backfill belongs to the deferred enrichment workflow."""
    return stories


def main() -> int:
    fetch_news.enrich_article = _metadata_first_enrich
    fetch_news.backfill_missing = _skip_backfill
    return run_scoop.main()


if __name__ == "__main__":
    raise SystemExit(main())
