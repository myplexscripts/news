from __future__ import annotations

from merge_refresh_output import merge_story, should_preserve_article


def paragraph(text: str) -> dict[str, str]:
    return {"type": "paragraph", "text": text}


def test_rich_article_survives_stale_refresh_snapshot() -> None:
    current = {
        "id": "story-1",
        "title": "Original headline",
        "published": "2026-09-02T20:00:00Z",
        "summary": "Current feed summary",
        "scope": "local",
        "content_status": "full",
        "word_count": 640,
        "content_blocks": [
            paragraph("A complete article paragraph with reporting and context."),
            {"type": "image", "url": "https://example.test/inline.jpg", "caption": "Scene from the story"},
            {"type": "media", "media_type": "embed", "provider": "x", "url": "https://platform.twitter.com/embed/Tweet.html?id=123&dnt=true"},
        ],
        "content": "A complete article paragraph with reporting and context.",
        "paragraphs": ["A complete article paragraph with reporting and context."],
        "rich_article_schema": 1,
        "rich_article_method": "dom:semantic-rich-v1",
        "quality": {"score": 92},
        "image": "https://example.test/original-hero.jpg",
    }
    fresh = {
        "id": "story-1",
        "title": "Updated headline from feed",
        "published": "2026-09-02T20:05:00Z",
        "summary": "Updated summary from feed",
        "scope": "canada",
        "content_status": "summary",
        "word_count": 32,
        "content_blocks": [paragraph("A short feed summary that should not replace the complete article body.")],
        "content": "A short feed summary that should not replace the complete article body.",
        "paragraphs": ["A short feed summary that should not replace the complete article body."],
        "quality": {"score": 35},
        "image": "https://example.test/feed-image.jpg",
    }

    assert should_preserve_article(current, fresh)
    merged, preserved = merge_story(fresh, current)
    assert preserved
    assert merged["title"] == "Updated headline from feed"
    assert merged["published"] == "2026-09-02T20:05:00Z"
    assert merged["summary"] == "Updated summary from feed"
    assert merged["scope"] == "canada"
    assert merged["content_status"] == "full"
    assert merged["word_count"] == 640
    assert merged["rich_article_schema"] == 1
    assert any(block.get("type") == "media" for block in merged["content_blocks"])
    assert merged["image"] == "https://example.test/original-hero.jpg"


def test_genuinely_better_fresh_article_can_win() -> None:
    current = {
        "id": "story-2",
        "content_status": "partial",
        "word_count": 180,
        "content_blocks": [paragraph("Older partial copy.")],
        "quality": {"score": 55},
    }
    fresh = {
        "id": "story-2",
        "content_status": "full",
        "word_count": 900,
        "content_blocks": [
            paragraph("A much more complete refreshed article body with substantially greater reporting depth."),
            {"type": "image", "url": "https://example.test/new-inline.jpg"},
        ],
        "quality": {"score": 88},
    }

    assert not should_preserve_article(current, fresh)
    merged, preserved = merge_story(fresh, current)
    assert not preserved
    assert merged == fresh


def main() -> int:
    test_rich_article_survives_stale_refresh_snapshot()
    test_genuinely_better_fresh_article_can_win()
    print("PASS refresh merge preserves richer articles")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
