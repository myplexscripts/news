from __future__ import annotations

"""Latency-bounded Scoop entry point for the frequent headline refresh.

The frequent refresh exists to discover new stories and publish them quickly.
Deep repair, stale-article re-extraction, image processing, archive-wide fuzzy
clustering and legacy backfill belong to the deferred enrichment workflow.
"""

from dataclasses import replace
from datetime import datetime, timezone

from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

import fetch_news
import run_scoop


FAST_REQUEST_TIMEOUT = 8
FAST_BACKFILL_PER_RUN = 0
# Existing stories are never deliberately re-scraped by the frequent path.
# Newly discovered URLs are still extracted immediately because they have no
# cached article. Deferred enrichment owns all later body refreshes and repairs.
FAST_ARTICLE_REFRESH_HOURS = 24 * 3650
FAST_PAGE_MAX_ITEMS = 10
FAST_RSS_MAX_ITEMS = 18
FAST_GOOGLE_MAX_ITEMS = 30


def _bounded_sources():
    bounded = []
    for source in fetch_news.SOURCES:
        if source.kind == "google_topic":
            limit = FAST_GOOGLE_MAX_ITEMS
        elif source.kind == "page":
            limit = FAST_PAGE_MAX_ITEMS
        else:
            limit = FAST_RSS_MAX_ITEMS
        bounded.append(replace(source, max_items=min(source.max_items, limit)))
    return bounded


def _keep_existing_image_metadata(stories, *args, **kwargs):
    """Leave costly image work to deferred enrichment."""
    return stories


def _fast_editorial_intelligence(stories, now=None):
    """Apply the O(n) metadata needed by the live feed.

    Full event clustering performs fuzzy pair comparisons across the archive and
    is intentionally deferred. The homepage is chronological, so the frequent
    refresh only needs locality, freshness and safe singleton cluster metadata.
    Enrichment later replaces these singleton values with real multi-source
    clusters without delaying discovery of new headlines.
    """
    ranking = run_scoop.ranking
    now = now or datetime.now(timezone.utc)

    for story in stories:
        local, local_reasons = ranking.local_relevance(story)
        freshness = ranking.freshness_score(story.get("published"), now)
        story_id = str(story.get("id") or "")
        source = str(story.get("source") or "")

        story["local_score"] = local
        story["local_reasons"] = local_reasons
        story["image_score"] = ranking.image_quality_score(story)
        story["freshness_score"] = freshness
        story["cluster_id"] = f"refresh-{story_id}" if story_id else ""
        story["cluster_size"] = 1
        story["cluster_source_count"] = 1 if source else 0
        story["cluster_sources"] = [source] if source else []
        story["cluster_member_ids"] = [story_id] if story_id else []
        story["cluster_representative_id"] = story_id
        story["cluster_representative"] = True
        story["cluster_local_score"] = local
        story["cluster_freshness_score"] = freshness
        story["cluster_latest_published"] = story.get("published", "")
        story["rank_score"] = freshness
        story["ranking_reasons"] = ["chronological frequent refresh"]

    return stories, {
        "clusters": [],
        "top_story_ids": [],
        "cluster_count": len(stories),
        "multi_source_cluster_count": 0,
    }


def configure_fast_mode() -> None:
    fetch_news.REQUEST_TIMEOUT = FAST_REQUEST_TIMEOUT
    fetch_news.BACKFILL_PER_RUN = FAST_BACKFILL_PER_RUN
    fetch_news.ARTICLE_REFRESH_HOURS = FAST_ARTICLE_REFRESH_HOURS
    fetch_news.SOURCES = _bounded_sources()

    # The deep collector retries transient failures. The frequent refresh cannot
    # let one unavailable publisher consume minutes while cached stories already
    # provide a safe fallback.
    no_retry = HTTPAdapter(max_retries=Retry(total=0, connect=0, read=0, status=0))
    fetch_news.SESSION.mount("https://", no_retry)
    fetch_news.SESSION.mount("http://", no_retry)

    fetch_news.add_image_focus = _keep_existing_image_metadata
    fetch_news.cache_card_images = _keep_existing_image_metadata

    # run_scoop's locality gate calls this ranking function after installing its
    # runtime safeguards, so replacing it here keeps locality filtering intact
    # while removing archive-wide fuzzy clustering from the frequent path.
    run_scoop.ranking.apply_editorial_intelligence = _fast_editorial_intelligence


def main() -> int:
    configure_fast_mode()
    return run_scoop.main()


if __name__ == "__main__":
    raise SystemExit(main())
