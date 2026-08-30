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


def main() -> int:
    test_share_dictionary_string_is_removed()
    test_separate_share_controls_are_removed()
    test_globe_utility_text_is_removed()
    test_dictionary_string_list_item_is_normalized()
    test_cbc_markdown_embed_placeholder_and_fake_player_are_cleaned()
    test_real_audio_media_is_preserved()
    print("PASS article presentation sanitizer regressions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
