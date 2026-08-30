from __future__ import annotations

from cleanup_article_recirculation import clean_payload


def test_promoted_story_list_is_removed() -> None:
    payload = {
        "stories": [
            {
                "id": "main",
                "source": "London Free Press",
                "title": "Railway City Brewing looks back and ahead",
                "content_blocks": [
                    {"type": "paragraph", "text": "With the brewery back in local hands, several old favourites could return for a short while."},
                    {"type": "heading", "level": 2, "text": "Read More"},
                    {
                        "type": "list",
                        "ordered": True,
                        "items": [
                            "Brews News: A sour suite for summer's end",
                            "Brews News: Anderson marks 10 years with anniversary bash",
                        ],
                    },
                    {"type": "paragraph", "text": "But not everything can be backward-looking."},
                ],
            },
            {"id": "a", "title": "Brews News: A sour suite for summer's end"},
            {"id": "b", "title": "Brews News: Anderson marks 10 years with anniversary bash"},
        ]
    }
    assert clean_payload(payload) == 1
    blocks = payload["stories"][0]["content_blocks"]
    assert not any(block.get("type") == "list" for block in blocks)
    assert not any(block.get("text") == "Read More" for block in blocks)
    assert any(block.get("text") == "But not everything can be backward-looking." for block in blocks)


def test_promoted_story_list_is_removed_even_when_titles_are_not_in_feed() -> None:
    payload = {
        "stories": [{
            "id": "main",
            "source": "London Free Press",
            "title": "Railway City Brewing looks back and ahead",
            "content_blocks": [
                {"type": "paragraph", "text": "Witty Traveller, a Belgian wheat beer, is a contender."},
                {
                    "type": "list",
                    "ordered": True,
                    "items": [
                        "Brews News: A sour suite for summer's end",
                        "Brews News: Anderson marks 10 years with anniversary bash",
                    ],
                },
                {"type": "paragraph", "text": "But not everything can be backward-looking."},
            ],
        }]
    }
    assert clean_payload(payload) == 1
    blocks = payload["stories"][0]["content_blocks"]
    assert not any(block.get("type") == "list" for block in blocks)
    assert any(block.get("text") == "But not everything can be backward-looking." for block in blocks)


def test_rich_promoted_story_list_is_removed() -> None:
    payload = {
        "stories": [{
            "id": "main",
            "source": "London Free Press",
            "title": "Railway City Brewing looks back and ahead",
            "content_blocks": [
                {"type": "paragraph", "text": "Witty Traveller, a Belgian wheat beer, is a contender."},
                {
                    "type": "list",
                    "ordered": True,
                    "items": [
                        {"text": "Brews News: A sour suite for summer's end", "html": "<strong>Brews News:</strong> A sour suite for summer's end"},
                        {"text": "Brews News: Anderson marks 10 years with anniversary bash", "html": "<strong>Brews News:</strong> Anderson marks 10 years with anniversary bash"},
                    ],
                },
                {"type": "paragraph", "text": "But not everything can be backward-looking."},
            ],
        }]
    }
    assert clean_payload(payload) == 1
    assert not any(block.get("type") == "list" for block in payload["stories"][0]["content_blocks"])


def test_labelled_publisher_cards_are_removed_without_feed_matches() -> None:
    payload = {
        "stories": [{
            "id": "main",
            "source": "CTV News",
            "title": "Main article",
            "content_blocks": [
                {"type": "paragraph", "text": "The main article continues with a complete sentence before the inserted module."},
                {"type": "heading", "level": 2, "text": "Recommended for you"},
                {"type": "paragraph", "text": "London council approves major downtown housing proposal"},
                {"type": "image", "url": "https://example.test/promo.jpg", "alt": ""},
                {"type": "paragraph", "text": "Police identify driver in Highway 401 collision near London"},
                {"type": "paragraph", "text": "Officials said the project will return to council next month for a final vote."},
            ],
        }]
    }
    assert clean_payload(payload) == 1
    dumped = " | ".join(str(block.get("text") or block.get("url") or "") for block in payload["stories"][0]["content_blocks"])
    assert "Recommended for you" not in dumped
    assert "downtown housing proposal" not in dumped
    assert "Highway 401 collision" not in dumped
    assert "return to council next month" in dumped


def test_newsletter_module_is_removed() -> None:
    payload = {
        "stories": [{
            "id": "main",
            "source": "Global News London",
            "title": "Main article",
            "content_blocks": [
                {"type": "paragraph", "text": "Residents described the meeting as productive and said more discussion is expected."},
                {"type": "heading", "level": 2, "text": "Newsletter"},
                {"type": "paragraph", "text": "Get the day's top stories delivered to your inbox"},
                {"type": "paragraph", "text": "The committee will meet again on Tuesday to consider the revised proposal."},
            ],
        }]
    }
    assert clean_payload(payload) == 1
    dumped = " | ".join(str(block.get("text") or "") for block in payload["stories"][0]["content_blocks"])
    assert "Newsletter" not in dumped
    assert "delivered to your inbox" not in dumped
    assert "meet again on Tuesday" in dumped


def test_globe_terminal_chrome_is_removed() -> None:
    payload = {
        "stories": [{
            "id": "globe",
            "source": "The Globe and Mail",
            "title": "Main article",
            "content_blocks": [
                {"type": "paragraph", "text": "The final real paragraph of the article ends here."},
                {"type": "paragraph", "text": "Report an editorial error", "html": "<a href='https://example.test/error'>Report an editorial error</a>"},
                {"type": "paragraph", "text": "Report a technical issue"},
                {"type": "heading", "level": 2, "text": "Follow related authors and topics"},
                {"type": "paragraph", "text": "Authors and topics you follow will be added to your personal news feed in Following."},
                {"type": "heading", "level": 2, "text": "Interact with The Globe"},
            ],
        }]
    }
    assert clean_payload(payload) == 1
    blocks = payload["stories"][0]["content_blocks"]
    assert [block.get("text") for block in blocks] == ["The final real paragraph of the article ends here."]


def test_single_linked_globe_related_story_is_removed_mid_article() -> None:
    headline = "B.C. ends provincial state of emergency as wildfires continue to burn"
    payload = {
        "stories": [{
            "id": "globe-inline",
            "source": "The Globe and Mail",
            "title": "Main wildfire article",
            "content_blocks": [
                {"type": "paragraph", "text": "The first real paragraph explains the wildfire situation in British Columbia."},
                {"type": "paragraph", "text": headline, "html": f"<a href='https://example.test/other'>{headline}</a>"},
                {"type": "paragraph", "text": "The article resumes here with another complete sentence from the original report."},
            ],
        }]
    }
    assert clean_payload(payload) == 1
    texts = [str(block.get("text") or "") for block in payload["stories"][0]["content_blocks"]]
    assert headline not in texts
    assert any("article resumes here" in text for text in texts)


def test_toronto_star_trending_rail_is_terminal() -> None:
    payload = {
        "stories": [{
            "id": "star",
            "source": "Toronto Star",
            "title": "Main article",
            "content_blocks": [
                {"type": "paragraph", "text": "The Canadian Press reported the main story from Toronto."},
                {"type": "heading", "level": 3, "text": "Trending"},
                {"type": "image", "url": "https://example.test/lake.jpg"},
                {"type": "heading", "level": 3, "text": "A sign for the times: Doug Ford unveils Lake Ontario sign", "html": "<a href='https://example.test/other'>A sign for the times</a>"},
            ],
        }]
    }
    assert clean_payload(payload) == 1
    blocks = payload["stories"][0]["content_blocks"]
    assert len(blocks) == 1
    assert blocks[0]["type"] == "paragraph"


def test_unlabelled_linked_story_card_run_is_removed_mid_article() -> None:
    payload = {
        "stories": [{
            "id": "post",
            "source": "National Post",
            "title": "Main article",
            "content_blocks": [
                {"type": "paragraph", "text": "The first half of the article explains the issue in detail."},
                {"type": "heading", "level": 3, "text": "First unrelated linked headline here", "html": "<a href='https://example.test/a'>First unrelated linked headline here</a>"},
                {"type": "image", "url": "https://example.test/a.jpg"},
                {"type": "heading", "level": 3, "text": "Second unrelated linked headline here", "html": "<a href='https://example.test/b'>Second unrelated linked headline here</a>"},
                {"type": "image", "url": "https://example.test/b.jpg"},
                {"type": "paragraph", "text": "The article resumes here with another complete sentence after the inserted rail."},
            ],
        }]
    }
    assert clean_payload(payload) == 1
    dumped = " | ".join(str(block.get("text") or block.get("url") or "") for block in payload["stories"][0]["content_blocks"])
    assert "First unrelated linked headline" not in dumped
    assert "Second unrelated linked headline" not in dumped
    assert "article resumes here" in dumped


def test_real_numbered_list_is_preserved() -> None:
    payload = {
        "stories": [
            {
                "id": "main",
                "source": "London Free Press",
                "title": "Three road projects begin next week",
                "content_blocks": [{
                    "type": "list",
                    "ordered": True,
                    "items": [
                        {"text": "Commissioners Road will close overnight on Tuesday.", "html": "Commissioners Road will close overnight on <strong>Tuesday</strong>."},
                        {"text": "Richmond Street will have one lane closed on Wednesday.", "html": "Richmond Street will have one lane closed on Wednesday."},
                        {"text": "Oxford Street work begins Thursday morning.", "html": "Oxford Street work begins Thursday morning."},
                    ],
                }],
            },
            {"id": "other", "title": "City council approves new housing plan"},
        ]
    }
    assert clean_payload(payload) == 0
    assert payload["stories"][0]["content_blocks"][0]["type"] == "list"


def main() -> int:
    test_promoted_story_list_is_removed()
    test_promoted_story_list_is_removed_even_when_titles_are_not_in_feed()
    test_rich_promoted_story_list_is_removed()
    test_labelled_publisher_cards_are_removed_without_feed_matches()
    test_newsletter_module_is_removed()
    test_globe_terminal_chrome_is_removed()
    test_single_linked_globe_related_story_is_removed_mid_article()
    test_toronto_star_trending_rail_is_terminal()
    test_unlabelled_linked_story_card_run_is_removed_mid_article()
    test_real_numbered_list_is_preserved()
    print("PASS recirculation cleanup regressions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
