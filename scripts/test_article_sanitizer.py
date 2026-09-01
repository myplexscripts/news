from __future__ import annotations

from sanitize_article_blocks import sanitize_payload


def test_share_dictionary_string_is_removed() -> None:
    payload = {
        "stories": [{
            "id": "lfp",
            "source": "London Free Press",
            "content_blocks": [{
                "type": "list",
                "ordered": False,
                "items": ["{'text': 'Share this Story : London Free Press Copy Link Email X Reddit Pinterest LinkedIn Tumblr', 'html': 'Share this Story'}"],
            }, {"type": "paragraph", "text": "The real article continues here with useful reporting."}],
        }]
    }
    assert sanitize_payload(payload) == 1
    blocks = payload["stories"][0]["content_blocks"]
    assert not any(block.get("type") == "list" for block in blocks)


def test_separate_share_controls_are_removed() -> None:
    payload = {
        "stories": [{
            "id": "star-share",
            "source": "Toronto Star",
            "content_blocks": [
                {"type": "list", "ordered": False, "items": [
                    {"text": "Email", "html": "Email"},
                    {"text": "Copy Link", "html": "Copy Link"},
                    {"text": "Share on X", "html": "<a href='https://example.test/share'>Share on X</a>"},
                    {"text": "Share on Reddit", "html": "<a href='https://example.test/share'>Share on Reddit</a>"},
                ]},
                {"type": "paragraph", "text": "The real article begins here with useful reporting."},
            ],
        }]
    }
    assert sanitize_payload(payload) == 1
    blocks = payload["stories"][0]["content_blocks"]
    assert not any(block.get("type") == "list" for block in blocks)
    assert blocks[0]["text"].startswith("The real article")


def test_globe_utility_text_is_removed() -> None:
    payload = {
        "stories": [{
            "id": "globe-chrome",
            "source": "The Globe and Mail",
            "content_blocks": [
                {"type": "paragraph", "text": "The real article ends here."},
                {"type": "paragraph", "text": "Report an editorial error"},
                {"type": "paragraph", "text": "Report a technical issue"},
                {"type": "heading", "text": "Follow related authors and topics", "level": 2},
                {"type": "list", "ordered": False, "items": ["Jason Tchir You must be logged in to follow. Log In Create free account"]},
                {"type": "paragraph", "text": "Authors and topics you follow will be added to your personal news feed in Following."},
                {"type": "heading", "text": "Interact with The Globe", "level": 2},
            ],
        }]
    }
    assert sanitize_payload(payload) == 1
    blocks = payload["stories"][0]["content_blocks"]
    assert [block.get("text") for block in blocks] == ["The real article ends here."]


def test_dictionary_string_list_item_is_normalized() -> None:
    payload = {
        "stories": [{
            "id": "list",
            "source": "City of London Newsroom",
            "content_blocks": [{
                "type": "list",
                "ordered": False,
                "items": ["{'text': 'Richmond Street closes Tuesday.', 'html': '<strong>Richmond Street</strong> closes Tuesday.'}"],
            }],
        }]
    }
    assert sanitize_payload(payload) == 1
    item = payload["stories"][0]["content_blocks"][0]["items"][0]
    assert item["text"] == "Richmond Street closes Tuesday."
    assert "<strong>Richmond Street</strong>" in item["html"]


def test_cbc_markdown_embed_placeholder_and_fake_player_are_cleaned() -> None:
    article_url = "https://www.cbc.ca/news/canada/london/example-1.2345"
    payload = {
        "stories": [{
            "id": "cbc",
            "source": "CBC News London",
            "url": article_url,
            "content_blocks": [
                {"type": "paragraph", "text": "_This interview has been edited for length and clarity._"},
                {"type": "paragraph", "text": "Guikema spoke with interim _Afternoon Drive_ host Nav Nanwa a short time after Thursday's announcement."},
                {"type": "paragraph", "text": "Nav Nanwa: What made you decide to move to Canada?"},
                {"type": "paragraph", "text": "The researcher said Western offered a strong environment for the work."},
                {"type": "paragraph", "text": "_LISTEN | Seth Guikema on why he's continuing his research in Canada:_"},
                {"type": "media", "media_type": "link", "url": article_url, "title": "LISTEN | Seth Guikema on why he's continuing his research in Canada:"},
                {"type": "paragraph", "text": "Open full embed in new tab Loading external pages May require significantly more data usage than loading CBC Lite story pages."},
            ],
        }]
    }
    assert sanitize_payload(payload) == 1
    blocks = payload["stories"][0]["content_blocks"]
    assert blocks[0]["text"] == "This interview has been edited for length and clarity."
    assert "<em>" in blocks[0]["html"]
    inline = next(block for block in blocks if block.get("text", "").startswith("Guikema spoke"))
    assert "_Afternoon Drive_" not in inline["text"]
    assert "<em>Afternoon Drive</em>" in inline["html"]
    question = next(block for block in blocks if block.get("text", "").startswith("Nav Nanwa:"))
    assert "<strong>" in question["html"]
    assert not any("Open full embed" in block.get("text", "") for block in blocks)
    assert not any(block.get("type") == "media" for block in blocks)


def test_real_audio_media_is_preserved() -> None:
    payload = {
        "stories": [{
            "id": "cbc-real-audio",
            "source": "CBC News London",
            "url": "https://www.cbc.ca/news/canada/london/example-1.2345",
            "content_blocks": [
                {"type": "paragraph", "text": "_LISTEN | Interview clip:_"},
                {"type": "media", "media_type": "audio", "url": "https://example.test/interview.mp3", "title": "Interview clip"},
            ],
        }]
    }
    assert sanitize_payload(payload) == 1
    media = next(block for block in payload["stories"][0]["content_blocks"] if block.get("type") == "media")
    assert media["media_type"] == "audio"
    assert media["url"].endswith("interview.mp3")


def test_global_newsletter_image_and_copy_are_removed() -> None:
    story = {
        "id": "global-newsletter-live-shape",
        "source": "Global News Canada",
        "content_status": "full",
        "content_blocks": [
            {"type": "paragraph", "text": "The professor said place names often change when governments change official terminology."},
            {"type": "image", "url": "https://example.test/national.jpg", "alt": "Get daily Canada news delivered to your inbox so you'll never miss the day's top stories."},
            {"type": "heading", "level": 2, "text": "Get daily National news"},
            {"type": "paragraph", "text": "Get daily Canada news delivered to your inbox so you'll never miss the day's top stories."},
            {"type": "paragraph", "text": "There is a long history of using place names as an assertion of political power."},
            {"type": "paragraph", "text": "© 2026 Global News, a division of Corus Entertainment Inc."},
        ],
    }
    payload = {"stories": [story]}
    assert sanitize_payload(payload) == 1
    dumped = " | ".join(str(block.get("text") or block.get("alt") or block.get("url") or "") for block in story["content_blocks"])
    assert "daily National news" not in dumped
    assert "delivered to your inbox" not in dumped
    assert "national.jpg" not in dumped
    assert "Corus Entertainment" not in dumped
    assert "assertion of political power" in dumped


def test_author_image_blocks_are_removed() -> None:
    story = {
        "id": "cbc-author-headshot",
        "source": "CBC News London",
        "content_status": "full",
        "content_blocks": [
            {"type": "paragraph", "text": "Council members discussed transit funding during Tuesday's budget meeting."},
            {"type": "image", "url": "https://images.example.test/reporter.jpg", "alt": "CBC News reporter Jane Smith headshot"},
            {"type": "paragraph", "text": "The proposal will return to committee after staff prepare a revised report."},
        ],
    }
    payload = {"stories": [story]}
    assert sanitize_payload(payload) == 1
    assert not any(block.get("type") == "image" for block in story["content_blocks"])
    assert "transit funding" in story["content"]
    assert "revised report" in story["content"]


def test_location_selector_dump_is_removed_and_forces_reader_retry() -> None:
    states = (
        "State Alabama Alaska Arizona Arkansas California Colorado Connecticut Delaware Florida Georgia Hawaii Idaho Illinois "
        "Indiana Iowa Kansas Kentucky Louisiana Maine Maryland Massachusetts Michigan Minnesota Mississippi Missouri Montana "
        "Nebraska Nevada New Hampshire New Jersey New Mexico New York North Carolina North Dakota Ohio Oklahoma Oregon "
        "Pennsylvania Rhode Island South Carolina South Dakota Tennessee Texas Utah Vermont Virginia Washington Wisconsin Wyoming"
    )
    countries = (
        "Country United States of America US Virgin Islands Canada Mexico Afghanistan Albania Algeria American Samoa Andorra "
        "Angola Argentina Armenia Australia Austria Azerbaijan Bahamas Bahrain Bangladesh Barbados Belarus Belgium Belize Benin "
        "Bhutan Bolivia Bosnia Botswana Brazil Brunei Bulgaria Burkina Faso Burundi Cambodia Cameroon Chile China Colombia"
    )
    story = {
        "id": "star-location-selector",
        "source": "Toronto Star",
        "content_status": "full",
        "reader_schema": 1,
        "reader_attempted_at": "2026-08-30T18:36:20+00:00",
        "content_blocks": [
            {"type": "paragraph", "text": states},
            {"type": "paragraph", "text": countries},
        ],
    }
    payload = {"stories": [story]}
    assert sanitize_payload(payload) == 1
    assert story["content_blocks"] == []
    assert story["content_status"] == "summary"
    assert story["content_truncated_reason"] == "publisher-form-chrome"
    assert story["reader_schema"] == 0
    assert "reader_attempted_at" not in story
    assert "form-selector-dump" in story["article_hygiene_flags"]


def main() -> int:
    test_share_dictionary_string_is_removed()
    test_separate_share_controls_are_removed()
    test_globe_utility_text_is_removed()
    test_dictionary_string_list_item_is_normalized()
    test_cbc_markdown_embed_placeholder_and_fake_player_are_cleaned()
    test_real_audio_media_is_preserved()
    test_global_newsletter_image_and_copy_are_removed()
    test_author_image_blocks_are_removed()
    test_location_selector_dump_is_removed_and_forces_reader_retry()
    print("PASS article presentation sanitizer regressions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
