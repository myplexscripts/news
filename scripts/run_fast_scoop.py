from __future__ import annotations

"""Latency-bounded Scoop entry point for the frequent headline refresh.

The frequent refresh exists to discover new stories and publish them quickly.
Deep repair, stale-article re-extraction, focal-point analysis, card-image caching,
and legacy backfill belong to the deferred enrichment workflow. Keeping those
jobs off this path prevents one slow publisher or image host from making the
entire news refresh miss its schedule.
"""

from dataclasses import replace

from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

import fetch_news
import run_scoop


FAST_REQUEST_TIMEOUT = 8
FAST_BACKFILL_PER_RUN = 0
FAST_ARTICLE_REFRESH_HOURS = 72
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
    """Leave costly image work to deferred enrichment.

    Existing card-image and focal-point fields remain on cached stories. Newly
    discovered stories can render their normal source image until enrichment
    creates local derivatives.
    """
    return stories


def configure_fast_mode() -> None:
    fetch_news.REQUEST_TIMEOUT = FAST_REQUEST_TIMEOUT
    fetch_news.BACKFILL_PER_RUN = FAST_BACKFILL_PER_RUN
    fetch_news.ARTICLE_REFRESH_HOURS = FAST_ARTICLE_REFRESH_HOURS
    fetch_news.SOURCES = _bounded_sources()

    # The normal collector retries transient publisher failures because deep
    # enrichment can afford to wait. The frequent refresh cannot. One unavailable
    # source should fail quickly while its cached stories remain in the feed.
    no_retry = HTTPAdapter(max_retries=Retry(total=0, connect=0, read=0, status=0))
    fetch_news.SESSION.mount("https://", no_retry)
    fetch_news.SESSION.mount("http://", no_retry)

    # These helpers can each perform many additional network/image operations.
    # Preserve already-computed metadata here and let enrich.yml update it later.
    fetch_news.add_image_focus = _keep_existing_image_metadata
    fetch_news.cache_card_images = _keep_existing_image_metadata


def main() -> int:
    configure_fast_mode()
    return run_scoop.main()


if __name__ == "__main__":
    raise SystemExit(main())
