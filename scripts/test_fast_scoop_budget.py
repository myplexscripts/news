from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from unittest.mock import patch

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


def test_fast_editorial_pass_is_bounded_and_locality_aware() -> None:
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
    assert stories[0]["ranking_reasons"]
    assert metadata["multi_source_cluster_count"] == 0
    assert metadata["top_story_ids"] == []



def test_real_coverage_survives_repeated_fast_refreshes() -> None:
    reports = json.loads((Path(__file__).parent / "fixtures/officer-coverage.json").read_text())
    now = datetime(2026, 10, 2, 16, tzinfo=timezone.utc)
    unrelated = {**reports[0], "id": "separate", "title": "Western University opens student residence", "summary": "New housing for students.", "paragraphs": ["Western University opens a new residence for students."]}
    stories = reports + [unrelated]
    for _ in range(2):
        stories, metadata = run_fast_scoop._fast_editorial_intelligence(stories, now)
        assert len({item["cluster_id"] for item in stories[:4]}) == 1
        assert stories[0]["cluster_source_count"] == 4
        assert stories[4]["cluster_id"] != stories[0]["cluster_id"]
        assert sum(item["cluster_representative"] for item in stories[:4]) == 1
        assert len(metadata["top_story_ids"]) == 2


def test_archive_clusters_are_preserved_without_archive_comparisons() -> None:
    now = datetime(2026, 10, 2, 16, tzinfo=timezone.utc)
    archive = [{"id": str(i), "title": "Archived event", "source": str(i), "published": (now - timedelta(days=10)).isoformat(), "cluster_id": "archived-coverage"} for i in range(2)]
    with patch.object(run_fast_scoop.run_scoop.ranking, "_should_cluster", side_effect=AssertionError("archive was compared")):
        annotated, metadata = run_fast_scoop._fast_editorial_intelligence(archive, now)
    assert annotated[0]["cluster_id"] == annotated[1]["cluster_id"]
    assert metadata["multi_source_cluster_count"] == 1


def test_separate_arrests_do_not_match_on_shared_release_template() -> None:
    now = datetime(2026, 10, 2, 16, tzinfo=timezone.utc)
    template = "The use of force is subject to mandatory reporting requirements and a subsequent review process. Concerns identified during the review prompted a criminal investigation."
    reports = [
        {"id": "one", "source": "CTV News", "title": "Officer charged after arrest of woman", "published": now.isoformat(), "paragraphs": ["Brandon Mihalides arrested a woman on April 29. " + template]},
        {"id": "two", "source": "CBC News", "title": "Officer charged after arrest of man", "published": now.isoformat(), "paragraphs": ["James Anderson arrested a man on June 12. " + template]},
    ]
    # Do not let generic headlines or police-release boilerplate override different incident identities.
    assert not run_fast_scoop.run_scoop.ranking._should_cluster(*reports)

def main() -> int:
    tests = [
        test_fast_mode_is_bounded,
        test_fast_editorial_pass_is_bounded_and_locality_aware,
        test_real_coverage_survives_repeated_fast_refreshes,
        test_archive_clusters_are_preserved_without_archive_comparisons,
        test_separate_arrests_do_not_match_on_shared_release_template,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
