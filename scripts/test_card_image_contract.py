from __future__ import annotations

import hashlib

import repair_card_image_refs as repair


def test_rejected_hero_clears_stale_card_cache() -> None:
    story = {
        "source": "CBC News London",
        "image": "",
        "card_image": "cache/news/old-author-headshot.webp",
        "card_image_small": "cache/news/old-author-headshot-sm.webp",
        "content_blocks": [],
    }
    assert repair.repair_story(story)
    assert story["image"] == ""
    assert story["card_image"] == ""
    assert story["card_image_small"] == ""


def test_remaining_article_photo_is_promoted() -> None:
    story = {
        "source": "CBC News London",
        "image": "",
        "card_image": "cache/news/old-author-headshot.webp",
        "content_blocks": [
            {"type": "paragraph", "text": "Article prose"},
            {
                "type": "image",
                "url": "https://i.cbc.ca/article/bus-lane.jpg",
                "alt": "A London Transit bus travelling in the centre-running lane.",
                "caption": "A Route 90 bus travels along Wellington Road.",
            },
        ],
    }
    assert repair.repair_story(story)
    assert story["image"] == "https://i.cbc.ca/article/bus-lane.jpg"
    assert story["card_image"] == ""
    assert story["image_alt"].startswith("A London Transit bus")


def test_remote_hero_only_accepts_matching_cache_name() -> None:
    hero = "https://example.com/story/photo.jpg"
    stem = hashlib.sha1(hero.encode("utf-8", "ignore")).hexdigest()[:20]
    story = {
        "image": hero,
        "card_image": "cache/news/unrelated.webp",
        "card_image_small": "cache/news/unrelated-sm.webp",
        "content_blocks": [],
    }
    assert repair.repair_story(story)
    assert story["card_image"] == ""
    assert story["card_image_small"] == ""
    expected, expected_small = repair.expected_remote_cards(hero)
    assert expected == f"cache/news/{stem}.webp"
    assert expected_small == f"cache/news/{stem}-sm.webp"


def test_local_hero_replaces_stale_cache_reference() -> None:
    story = {
        "image": "cache/cbc/real-story.webp",
        "card_image": "cache/news/old-headshot.webp",
        "card_image_small": "cache/news/old-headshot-sm.webp",
        "content_blocks": [],
    }
    assert repair.repair_story(story)
    assert story["card_image"] == "cache/cbc/real-story.webp"
    assert story["card_image_small"] == ""


def main() -> None:
    test_rejected_hero_clears_stale_card_cache()
    test_remaining_article_photo_is_promoted()
    test_remote_hero_only_accepts_matching_cache_name()
    test_local_hero_replaces_stale_cache_reference()
    print("Card image contract regression tests passed")


if __name__ == "__main__":
    main()
