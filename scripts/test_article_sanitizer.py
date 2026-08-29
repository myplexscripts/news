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


def test_cbc_markdown_and_embed_placeholder_are_cleaned() -> None:
    payload = {
        "stories": [{
            "id": "cbc",
            "source": "CBC News London",
            "url": "https://www.cbc.ca/news/canada/london/example-1.2345",
            "content_blocks": [
                {"type": "paragraph", "text": "_This interview has been edited for length and clarity._"},
                {"type": "paragraph", "text": "Nav Nanwa: What made you decide to move to Canada?"},
                {"type": "paragraph", "text": "The researcher said Western offered a strong environment for the work."},
                {"type": "paragraph", "text": "_LISTEN | Seth Guikema on why he's continuing his research in Canada:_"},
                {"type": "paragraph", "text": "Open full embed in new tab Loading external pages May require significantly more data usage than loading CBC Lite story pages."},
            ],
        }]
    }
    assert sanitize_payload(payload) == 1
    blocks = payload["stories"][0]["content_blocks"]
    assert blocks[0]["text"] == "This interview has been edited for length and clarity."
    assert "<em>" in blocks[0]["html"]
    question = next(block for block in blocks if block.get("text", "").startswith("Nav Nanwa:"))
    assert "<strong>" in question["html"]
    assert not any("Open full embed" in block.get("text", "") for block in blocks)
    media = next(block for block in blocks if block.get("type") == "media")
    assert media["media_type"] == "link"


def main() -> int:
    test_share_dictionary_string_is_removed()
    test_dictionary_string_list_item_is_normalized()
    test_cbc_markdown_and_embed_placeholder_are_cleaned()
    print("PASS article presentation sanitizer regressions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
