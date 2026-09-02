from __future__ import annotations

from repair_source_content import (
    repair_national_post_story,
    safe_cbc_image,
    should_apply_reader,
    strip_non_cbc_images,
)


def main() -> int:
    national_post = {
        "source": "National Post",
        "title": "Example National Post story",
        "image": "",
        "content_status": "full",
        "content_blocks": [
            {"type": "paragraph", "text": "This is the first real paragraph of the article and it contains enough text to survive normal cleanup."},
            {"type": "paragraph", "text": "Enjoy the latest local, national and international news."},
            {"type": "paragraph", "text": "Access articles from across Canada with one account."},
            {"type": "paragraph", "text": "Enjoy additional articles per month."},
            {"type": "paragraph", "text": "This is the second real paragraph of the article and it should remain in the reader after cleanup."},
        ],
        "paragraphs": [],
        "content": "",
        "word_count": 0,
    }
    assert repair_national_post_story(national_post)
    combined = national_post["content"].lower()
    assert "enjoy the latest local" not in combined
    assert "access articles from across canada" not in combined
    assert "enjoy additional articles" not in combined
    assert "first real paragraph" in combined
    assert "second real paragraph" in combined

    assert safe_cbc_image("https://i.cbc.ca/1.12345.1234567890!/fileImage/httpImage/image.jpg")
    assert safe_cbc_image("cache/cbc/cbc-example.jpg")
    assert not safe_cbc_image("https://lh3.googleusercontent.com/example.jpg")
    assert not safe_cbc_image("cache/news/google-placeholder.webp")

    cbc_story = {
        "source": "CBC News London",
        "image": "https://lh3.googleusercontent.com/google-news-placeholder.jpg",
        "card_image": "cache/news/google-news-placeholder.webp",
        "content_blocks": [
            {"type": "paragraph", "text": "A real CBC paragraph remains."},
            {"type": "image", "url": "https://lh3.googleusercontent.com/inline.jpg"},
            {"type": "image", "url": "https://i.cbc.ca/1.12345.1234567890!/fileImage/httpImage/real.jpg"},
        ],
        "article_images": [
            {"url": "https://lh3.googleusercontent.com/inline.jpg"},
            {"url": "https://i.cbc.ca/1.12345.1234567890!/fileImage/httpImage/real.jpg"},
        ],
    }
    changed, bad_hero = strip_non_cbc_images(cbc_story)
    assert changed and bad_hero
    assert cbc_story["image"] == ""
    assert cbc_story["card_image"] == ""
    assert len([block for block in cbc_story["content_blocks"] if block.get("type") == "image"]) == 1
    assert len(cbc_story["article_images"]) == 1

    short_existing = {
        "content_status": "full",
        "word_count": 105,
        "paragraphs": ["one", "two"],
        "content": "",
        "body_transport": "direct",
    }
    fuller_reader = {
        "word_count": 640,
        "paragraphs": ["one", "two", "three"],
    }
    assert should_apply_reader(short_existing, fuller_reader)

    already_reader = {
        "content_status": "full",
        "word_count": 640,
        "paragraphs": ["one", "two", "three"],
        "content": "",
        "body_transport": "jina-reader",
    }
    shorter_reader = {
        "word_count": 500,
        "paragraphs": ["one", "two", "three"],
    }
    assert not should_apply_reader(already_reader, shorter_reader)

    print("Source content repair contracts passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
