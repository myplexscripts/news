from __future__ import annotations

import filter_publication_roundups as filters


def test_lfp_news_of_the_day_is_excluded() -> None:
    story = {
        "id": "roundup-1",
        "source": "London Free Press",
        "title": "News of the day: Elderly woman dies after stabbing, $5.5-million London mansion and more . . .",
        "content_status": "partial",
    }
    assert filters.is_redundant_roundup(story)


def test_regular_lfp_story_is_kept() -> None:
    story = {
        "id": "normal-1",
        "source": "London Free Press",
        "title": "London council approves new downtown housing project",
        "content_status": "full",
    }
    assert not filters.is_redundant_roundup(story)


def test_filter_updates_payload_counts_and_metadata() -> None:
    payload = {
        "story_count": 2,
        "full_story_count": 1,
        "partial_story_count": 1,
        "source_count": 1,
        "top_story_ids": ["roundup-1", "normal-1"],
        "editorial_clusters": [
            {
                "id": "cluster-roundup",
                "representative_id": "roundup-1",
                "member_ids": ["roundup-1"],
                "member_count": 1,
                "source_count": 1,
            },
            {
                "id": "cluster-normal",
                "representative_id": "normal-1",
                "member_ids": ["normal-1"],
                "member_count": 1,
                "source_count": 1,
            },
        ],
        "cluster_count": 2,
        "multi_source_cluster_count": 0,
        "stories": [
            {
                "id": "roundup-1",
                "source": "London Free Press",
                "title": "News of the day: Roundup of other stories",
                "content_status": "partial",
            },
            {
                "id": "normal-1",
                "source": "London Free Press",
                "title": "A normal London Free Press article",
                "content_status": "full",
            },
        ],
    }

    filtered, removed = filters.filter_payload(payload)
    assert len(removed) == 1
    assert [story["id"] for story in filtered["stories"]] == ["normal-1"]
    assert filtered["story_count"] == 1
    assert filtered["full_story_count"] == 1
    assert filtered["partial_story_count"] == 0
    assert filtered["top_story_ids"] == ["normal-1"]
    assert filtered["cluster_count"] == 1
    assert filtered["editorial_clusters"][0]["id"] == "cluster-normal"


def main() -> int:
    tests = [
        test_lfp_news_of_the_day_is_excluded,
        test_regular_lfp_story_is_kept,
        test_filter_updates_payload_counts_and_metadata,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
