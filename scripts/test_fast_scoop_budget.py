from __future__ import annotations

import fetch_news
import run_fast_scoop


def test_fast_mode_is_bounded() -> None:
    run_fast_scoop.configure_fast_mode()

    assert fetch_news.REQUEST_TIMEOUT == 8
    assert fetch_news.BACKFILL_PER_RUN == 0
    assert fetch_news.ARTICLE_REFRESH_HOURS == 72

    for source in fetch_news.SOURCES:
        if source.kind == "google_topic":
            assert source.max_items <= 30
        elif source.kind == "page":
            assert source.max_items <= 10
        else:
            assert source.max_items <= 18

    assert fetch_news.SESSION.get_adapter("https://").max_retries.total == 0

    marker = [{"id": "story"}]
    assert fetch_news.add_image_focus(marker) is marker
    assert fetch_news.cache_card_images(marker) is marker


def main() -> int:
    test_fast_mode_is_bounded()
    print("PASS test_fast_mode_is_bounded")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
