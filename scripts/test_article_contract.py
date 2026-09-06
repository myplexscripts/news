from __future__ import annotations

"""Regression tests for the cross-publisher article contract."""

from copy import deepcopy

import enforce_article_contract as contract


def all_text(story) -> str:
    return " ".join(
        contract.block_text(block)
        for block in story.get("content_blocks", [])
        if isinstance(block, dict)
    ).lower()


def test_global_cleanup() -> None:
    story = {
        "source": "Global News London",
        "author": "John Smith",
        "content_blocks": [
            {"type": "image", "url": "https://globalnews.ca/author/john-smith.jpg", "alt": "John Smith"},
            {"type": "paragraph", "text": "If you get Global News from Instagram or Facebook - that will be changing. Find out how you can still connect with us."},
            {"type": "heading", "text": "Share"},
            {"type": "paragraph", "text": "Friends and family are remembering an Indigenous filmmaker and actor described by her family as a trailblazer after she died at an Alberta rodeo."},
            {"type": "paragraph", "text": "RCMP confirmed Alberta Occupational Health and Safety has taken over the investigation and the family says a tribute is planned."},
            {"type": "image", "url": "cache/news/real-story-photo.webp", "alt": "Family members gather at the rodeo grounds after the incident."},
            {"type": "image", "url": "https://globalnews.ca/assets/preferred-source-google.png", "alt": "Add as a preferred source on Google"},
            {"type": "heading", "text": "Keep reading"},
            {"type": "heading", "text": "More from London"},
            {"type": "image", "url": "cache/news/related-story.webp", "alt": "Related story"},
        ],
    }
    assert contract.enforce_story(story)
    text = all_text(story)
    for forbidden in ("if you get global news", "share", "keep reading", "more from london"):
        assert forbidden not in text
    urls = [contract.image_url(b) for b in story["content_blocks"] if b.get("type") == "image"]
    assert "https://globalnews.ca/author/john-smith.jpg" not in urls
    assert "https://globalnews.ca/assets/preferred-source-google.png" not in urls
    assert "cache/news/related-story.webp" not in urls
    assert "cache/news/real-story-photo.webp" in urls


def test_cbc_author_hero_repair() -> None:
    story = {
        "source": "CBC News London",
        "author": "Jack Sutton",
        "image": "https://i.cbc.ca/profile/jack-sutton.jpg",
        "image_alt": "Jack Sutton",
        "card_image": "cache/news/jack-sutton-square.webp",
        "content_blocks": [
            {"type": "image", "url": "https://i.cbc.ca/profile/jack-sutton.jpg", "alt": "Jack Sutton"},
            {"type": "paragraph", "text": "London's Express Route 90 bus is now driving on a short section of the city's first centre-running bus lane."},
            {"type": "paragraph", "text": "The new lanes run on Wellington Road between Simcoe Street and Grand Avenue and are intended to improve transit reliability."},
            {"type": "image", "url": "cache/cbc/bus-lane.webp", "alt": "A London Transit bus travelling on Wellington Road."},
        ],
    }
    contract.enforce_story(story)
    assert story["image"] == "cache/cbc/bus-lane.webp"
    assert story["card_image"] == "cache/cbc/bus-lane.webp"
    assert not story.get("card_image_small")


def test_legitimate_square_image_after_prose_survives() -> None:
    story = {
        "source": "CTV News",
        "author": "Reporter Name",
        "content_blocks": [
            {"type": "paragraph", "text": "Police are asking the public for information after a missing person investigation continued through the weekend in London."},
            {"type": "paragraph", "text": "Investigators released an additional photograph and said anyone with information should contact police."},
            {"type": "image", "url": "cache/news/missing-person.webp", "alt": "Photo supplied by London Police Service."},
        ],
    }
    before = deepcopy(story["content_blocks"])
    contract.enforce_story(story)
    assert story["content_blocks"] == before


def test_mid_article_newsletter_does_not_truncate_story() -> None:
    story = {
        "source": "Global News Canada",
        "content_blocks": [
            {"type": "paragraph", "text": "The first section of the story contains enough detail to establish that this is real editorial article prose for readers."},
            {"type": "heading", "text": "Get daily National news"},
            {"type": "paragraph", "text": "Get daily Canada news delivered to your inbox so you'll never miss the day's top stories."},
            {"type": "paragraph", "text": "The story continues here with additional reporting after the newsletter module and this paragraph must remain in the final article."},
        ],
    }
    contract.enforce_story(story)
    text = all_text(story)
    assert "get daily national news" not in text
    assert "delivered to your inbox" not in text
    assert "story continues here" in text


def main() -> None:
    test_global_cleanup()
    test_cbc_author_hero_repair()
    test_legitimate_square_image_after_prose_survives()
    test_mid_article_newsletter_does_not_truncate_story()
    print("Article contract regression tests passed")


if __name__ == "__main__":
    main()
