from __future__ import annotations

from sanitize_article_blocks import sanitize_payload


def test_raw_publisher_labels_and_fragments_are_repaired() -> None:
    story = {
        "id": "generic-rich-guard",
        "source": "Example Publisher",
        "content_status": "full",
        "content_blocks": [
            {"type": "paragraph", "text": "Updated Example News | Posted: September 2, 2026 11:01 AM | Last Updated: 1 hour ago"},
            {"type": "paragraph", "text": "Image | Dark skies over London, Ont., looking from the south end."},
            {"type": "image", "url": "https://images.example.test/storm.jpg", "alt": "Dark skies over London", "caption": ""},
            {"type": "paragraph", "text": "Caption: Dark skies formed in London as thunderstorms passed through the region."},
            {"type": "paragraph", "text": "Several roads in the region"},
            {"type": "paragraph", "text": "have also been impacted by fallen trees and downed power lines."},
        ],
    }
    payload = {"stories": [story]}
    assert sanitize_payload(payload) == 1
    blocks = story["content_blocks"]
    assert [block["type"] for block in blocks] == ["image", "paragraph"]
    assert blocks[0]["caption"] == "Dark skies formed in London as thunderstorms passed through the region."
    assert blocks[1]["text"] == "Several roads in the region have also been impacted by fallen trees and downed power lines."
    assert "Updated Example News" not in story["content"]
    assert "Image |" not in story["content"]
    assert "Caption:" not in story["content"]


def test_real_social_embed_survives_final_guard() -> None:
    story = {
        "id": "generic-social",
        "source": "Example Publisher",
        "content_status": "full",
        "content_blocks": [
            {"type": "paragraph", "text": "Police posted an update as crews worked through the affected area."},
            {
                "type": "media",
                "media_type": "embed",
                "provider": "x",
                "url": "https://platform.twitter.com/embed/Tweet.html?id=1234567890123456789&dnt=true",
                "source_url": "https://twitter.com/OPP_WR/status/1234567890123456789",
                "title": "",
            },
            {"type": "paragraph", "text": "Cleanup work continued into the evening."},
        ],
    }
    payload = {"stories": [story]}
    assert sanitize_payload(payload) == 1
    media = next(block for block in story["content_blocks"] if block.get("type") == "media")
    assert media["media_type"] == "embed"
    assert media["provider"] == "x"
    assert "platform.twitter.com" in media["url"]
    assert "twitter.com/OPP_WR/status/" in media["source_url"]


def main() -> int:
    test_raw_publisher_labels_and_fragments_are_repaired()
    test_real_social_embed_survives_final_guard()
    print("PASS final rich article guard regressions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
