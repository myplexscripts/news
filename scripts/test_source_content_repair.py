from __future__ import annotations

from repair_source_content import (
    apply_ctv_source_result,
    ctv_story_needs_repair,
    degrade_broken_ctv_story,
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

    broken_ctv = {
        "id": "ctv-example",
        "source": "CTV News London",
        "scope": "local",
        "title": "Storm cleanup continues",
        "url": "https://www.ctvnews.ca/london/article/storm-cleanup-continues",
        "summary": "Crews are cleaning up across the region after a powerful storm damaged trees, hydro lines and several properties on Wednesday evening.",
        "content_status": "full",
        "content": "",
        "paragraphs": [],
        "content_blocks": [
            {"type": "media", "media_type": "embed", "url": "https://www.ctvnews.ca/video/player"},
        ],
        "word_count": 0,
        "quality": {"score": 96, "grade": "excellent", "method": "dom:semantic-rich-v1"},
        "rich_article_method": "dom:semantic-rich-v1",
    }
    assert ctv_story_needs_repair(broken_ctv)

    first = (
        "Cleanup crews worked through the morning after strong winds knocked down mature trees and damaged hydro lines across the region. "
        "Municipal officials said several roads were temporarily closed while workers removed debris and assessed damaged infrastructure. "
        "Emergency crews also checked neighbourhoods where branches had fallen onto homes, vehicles and sidewalks during the storm."
    )
    second = (
        "Hydro crews restored service to most customers by Thursday afternoon, while a smaller number of properties remained without power. "
        "Residents were asked to keep away from downed wires and report damaged trees that could pose a public safety risk. "
        "Officials said cleanup work would continue through the day and asked drivers to give maintenance vehicles extra room."
    )
    candidate = {
        **broken_ctv,
        "content_status": "full",
        "content": f"{first}\n\n{second}",
        "paragraphs": [first, second],
        "content_blocks": [
            {"type": "paragraph", "text": first},
            {"type": "image", "url": "https://www.ctvnews.ca/content/dam/ctvnews/images/storm.jpg", "alt": "Storm damage"},
            {"type": "paragraph", "text": second},
        ],
        "word_count": len((first + " " + second).split()),
        "quality": {"score": 82, "grade": "good", "method": "embedded-json:ctv"},
    }
    assert candidate["word_count"] >= 90
    assert apply_ctv_source_result(broken_ctv, candidate)
    assert broken_ctv["quality"]["method"] == "embedded-json:ctv"
    assert broken_ctv["ctv_source_repair_schema"] == 1
    assert broken_ctv["rich_article_schema"] >= 1
    assert broken_ctv["media_schema"] >= 3
    assert broken_ctv["reader_schema"] >= 2
    assert any(block.get("type") == "image" for block in broken_ctv["content_blocks"])
    assert not ctv_story_needs_repair(broken_ctv)

    fallback_ctv = {
        "source": "CTV News Canada",
        "title": "A national story",
        "url": "https://www.ctvnews.ca/canada/article/a-national-story",
        "summary": "Federal officials provided an update Thursday after several agencies met to discuss the new national program and the next steps for provinces.",
        "content_status": "full",
        "content": "",
        "paragraphs": [],
        "content_blocks": [{"type": "media", "media_type": "embed", "url": "https://example.test/player"}],
        "word_count": 0,
        "quality": {"score": 96, "method": "dom:semantic-rich-v1"},
    }
    assert degrade_broken_ctv_story(fallback_ctv, "ctv:no-trusted-body")
    assert fallback_ctv["content_status"] == "summary"
    assert fallback_ctv["word_count"] > 0
    assert fallback_ctv["content_blocks"] == [{"type": "paragraph", "text": fallback_ctv["summary"]}]
    assert fallback_ctv["quality"]["method"] == "ctv:summary-fallback"

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
