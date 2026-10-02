from __future__ import annotations

"""Latency-bounded Scoop entry point for the frequent headline refresh.

The frequent refresh exists to discover new stories and publish them quickly.
Recent event clustering happens before publication. Deep repair, stale-article
re-extraction, image processing, archive-wide comparisons and legacy backfill
belong to the deferred enrichment workflow.
"""

from dataclasses import replace
from datetime import datetime, timedelta, timezone

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


# Capture the full implementation before installing the frequent-path wrapper.
_cluster_editorial_intelligence = run_scoop.ranking.apply_editorial_intelligence
FAST_CLUSTER_LOOKBACK_HOURS = 72


def _fast_editorial_intelligence(stories, now=None):
    """Cluster recent events without comparing the entire historical archive."""
    now = now or datetime.now(timezone.utc)
    return _cluster_editorial_intelligence(
        stories, now,
        comparison_since=now - timedelta(hours=FAST_CLUSTER_LOOKBACK_HOURS),
    )


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
    # while bounding fuzzy comparisons to recent events.
    run_scoop.ranking.apply_editorial_intelligence = _fast_editorial_intelligence


def main() -> int:
    configure_fast_mode()
    return run_scoop.main()


if __name__ == "__main__":
    raise SystemExit(main())
