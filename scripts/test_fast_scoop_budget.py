from __future__ import annotations

import fetch_news
import run_fast_scoop


def test_fast_mode_is_bounded() -> None:
    run_fast_scoop.configure_fast_mode()

    assert fetch_news.REQUEST_TIMEOUT == 8
    assert fetch_news.BACKFILL_PER_RUN == 0
    assert fetch_news.ARTICLE_REFRESH_HOURS >= 365 * 24

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


def test_fast_editorial_pass_is_linear_and_locality_aware() -> None:
    story = {
        "id": "example",
        "source": "CBC News London",
        "title": "London council meets Tuesday",
        "summary": "Councillors in London, Ontario will discuss the proposal.",
        "published": "2026-09-03T08:00:00+00:00",
        "quality": {"score": 80},
    }
    stories, metadata = run_fast_scoop._fast_editorial_intelligence([story])

    assert stories[0]["local_score"] > 0
    assert stories[0]["cluster_size"] == 1
    assert stories[0]["cluster_member_ids"] == ["example"]
    assert stories[0]["ranking_reasons"] == ["chronological frequent refresh"]
    assert metadata["multi_source_cluster_count"] == 0
    assert metadata["top_story_ids"] == []


def main() -> int:
    tests = [
        test_fast_mode_is_bounded,
        test_fast_editorial_pass_is_linear_and_locality_aware,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
