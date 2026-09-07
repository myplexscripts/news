from __future__ import annotations

import repair_card_image_refs as card_guard
import repair_cbc_lite_heroes as repair


TINY = (
    "https://i.cbc.ca/ais/1.7528226,1746569401000/full/max/0/default.jpg?"
    "im=Crop%2Crect%3D%280%2C0%2C3395%2C3395%29%3BResize%3D76"
)
GOOD = "https://i.cbc.ca/ais/story/full/max/0/default.jpg?im=Resize%3D1180"


def make_story() -> dict:
    return {
        "source": "CBC News London",
        "title": "Here's what you need to know about London's new centre-running bus lanes",
        "url": "https://news.google.com/rss/articles/example",
        "cbc_lite_url": "https://www.cbc.ca/lite/story/9.7334426",
        "image": TINY,
        "card_image": "cache/news/stale-headshot.webp",
        "card_image_small": "cache/news/stale-headshot-sm.webp",
        "image_alt": "New LTC centre bus lanes",
        "image_caption": "Tariq Alyousif boarding the Express Route 90 from the new platform.",
        "content_blocks": [],
    }


def test_lite_url_is_preferred_reader_surface() -> None:
    story = make_story()
    assert repair.candidate_reader_urls(story) == ["https://www.cbc.ca/lite/story/9.7334426"]
    assert repair.hero_needs_repair(story)
    assert card_guard.is_tiny_remote_derivative(story["image"])


def test_tiny_reader_candidate_is_rejected() -> None:
    story = make_story()
    assert not repair.acceptable_candidate(story, TINY)
    assert repair.acceptable_candidate(story, GOOD)


def test_repair_uses_real_lite_story_image(monkeypatch=None) -> None:
    story = make_story()

    original_reader = repair.cbc_repair.reader_image_candidates
    original_cache = repair.cbc.cache_image
    try:
        repair.cbc_repair.reader_image_candidates = lambda url, record: [TINY, GOOD]
        repair.cbc.cache_image = lambda url: "cache/cbc/cbc-real-story.jpg" if url == GOOD else ""
        assert repair.repair_record(story)
    finally:
        repair.cbc_repair.reader_image_candidates = original_reader
        repair.cbc.cache_image = original_cache

    assert story["image"] == "cache/cbc/cbc-real-story.jpg"
    assert story["card_image"] == "cache/cbc/cbc-real-story.jpg"
    assert story["card_image_small"] == ""
    assert story["cbc_lite_hero_source"] == "https://www.cbc.ca/lite/story/9.7334426"


def main() -> None:
    test_lite_url_is_preferred_reader_surface()
    test_tiny_reader_candidate_is_rejected()
    test_repair_uses_real_lite_story_image()
    print("CBC Lite hero repair regression tests passed")


if __name__ == "__main__":
    main()
