from __future__ import annotations

from datetime import datetime, timezone

import repair_ctv_locality


class Entry(dict):
    pass


def make_entry(title: str, published: str, source: str = "CTV News") -> Entry:
    return Entry({
        "title": title,
        "published": published,
        "source": {"title": source},
    })


def test_canada_copy_of_london_url_is_restored_to_local_source() -> None:
    payload = {
        "stories": [{
            "id": "abc",
            "title": "CAMI plant to remain open, hope for potential armoured vehicle production",
            "source": "CTV News Canada",
            "scope": "canada",
            "source_home": "https://www.ctvnews.ca/canada/",
            "url": "https://www.ctvnews.ca/london/article/cami-plant-to-remain-open/",
            "published": "2026-08-30T01:00:00+00:00",
        }],
        "source_health": [],
    }

    repaired, stats = repair_ctv_locality.repair_payload(
        payload,
        [],
        now=datetime(2026, 8, 30, 10, 45, tzinfo=timezone.utc),
    )

    story = repaired["stories"][0]
    assert stats["reclassified"] == 1
    assert story["source"] == "CTV News"
    assert story["scope"] == "local"
    assert story["source_home"] == "https://www.ctvnews.ca/london/"
    assert story["source_repaired_from"] == "CTV News Canada"


def test_non_london_canada_story_stays_canada() -> None:
    payload = {
        "stories": [{
            "id": "national",
            "title": "National story",
            "source": "CTV News Canada",
            "scope": "canada",
            "url": "https://www.ctvnews.ca/canada/article/national-story/",
            "published": "2026-08-30T01:00:00+00:00",
        }]
    }

    repaired, stats = repair_ctv_locality.repair_payload(payload, [])
    assert stats["reclassified"] == 0
    assert repaired["stories"][0]["source"] == "CTV News Canada"
    assert repaired["stories"][0]["scope"] == "canada"


def test_google_news_timestamp_can_move_existing_ctv_story_forward() -> None:
    payload = {
        "stories": [{
            "id": "ltc",
            "title": "LTC seeks additional $2M for 2027 budget",
            "source": "CTV News",
            "scope": "local",
            "url": "https://www.ctvnews.ca/london/article/ltc-seeks-additional-2m-for-2027-budget/",
            "published": "2026-08-29T15:00:00+00:00",
        }]
    }
    entries = [
        make_entry(
            "LTC seeks additional $2M for 2027 budget - CTV News",
            "Sat, 29 Aug 2026 23:15:00 GMT",
        )
    ]

    repaired, stats = repair_ctv_locality.repair_payload(
        payload,
        entries,
        now=datetime(2026, 8, 30, 10, 45, tzinfo=timezone.utc),
    )

    story = repaired["stories"][0]
    assert stats["matched_index"] == 1
    assert stats["timestamps_updated"] == 1
    assert story["published"] == "2026-08-29T23:15:00+00:00"
    assert story["published_original"] == "2026-08-29T15:00:00+00:00"
    assert story["published_via"] == "google-news-ctv-index"


def test_google_news_never_moves_story_backwards() -> None:
    payload = {
        "stories": [{
            "id": "weather",
            "title": "Sunny Saturday but thunderstorms possible Sunday",
            "source": "CTV News",
            "scope": "local",
            "url": "https://www.ctvnews.ca/london/article/sunny-saturday-but-thunderstorms-possible-sunday/",
            "published": "2026-08-30T01:00:00+00:00",
        }]
    }
    entries = [
        make_entry(
            "Sunny Saturday but thunderstorms possible Sunday - CTV News London",
            "Sat, 29 Aug 2026 14:00:00 GMT",
        )
    ]

    repaired, stats = repair_ctv_locality.repair_payload(
        payload,
        entries,
        now=datetime(2026, 8, 30, 10, 45, tzinfo=timezone.utc),
    )

    assert stats["matched_index"] == 1
    assert stats["timestamps_updated"] == 0
    assert repaired["stories"][0]["published"] == "2026-08-30T01:00:00+00:00"


def main() -> None:
    test_canada_copy_of_london_url_is_restored_to_local_source()
    print("PASS test_canada_copy_of_london_url_is_restored_to_local_source")
    test_non_london_canada_story_stays_canada()
    print("PASS test_non_london_canada_story_stays_canada")
    test_google_news_timestamp_can_move_existing_ctv_story_forward()
    print("PASS test_google_news_timestamp_can_move_existing_ctv_story_forward")
    test_google_news_never_moves_story_backwards()
    print("PASS test_google_news_never_moves_story_backwards")


if __name__ == "__main__":
    main()
