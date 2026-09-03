from __future__ import annotations

"""Bounded Scoop entry point for the frequent headline refresh.

The base collector also carries legacy article backfill responsibilities. Those
are valuable, but they do not belong on the latency-sensitive refresh path now
that deferred enrichment owns deep article recovery. Keep the collector logic
identical while tightening its network budget and limiting old-story backfill.
"""

import fetch_news
import run_scoop


FAST_REQUEST_TIMEOUT = 12
FAST_BACKFILL_PER_RUN = 8


def main() -> int:
    fetch_news.REQUEST_TIMEOUT = FAST_REQUEST_TIMEOUT
    fetch_news.BACKFILL_PER_RUN = FAST_BACKFILL_PER_RUN
    return run_scoop.main()


if __name__ == "__main__":
    raise SystemExit(main())
