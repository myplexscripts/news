from __future__ import annotations

from cleanup_article_recirculation import clean_payload


def test_promoted_story_list_is_removed() -> None:
    payload = {
        "stories": [
            {
                "id": "main",
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
        "stories": [
            {
                "id": "main",
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
            }
        ]
    }

    assert clean_payload(payload) == 1
    blocks = payload["stories"][0]["content_blocks"]
    assert not any(block.get("type") == "list" for block in blocks)
    assert any(block.get("text") == "But not everything can be backward-looking." for block in blocks)


def test_real_numbered_list_is_preserved() -> None:
    payload = {
        "stories": [
            {
                "id": "main",
                "title": "Three road projects begin next week",
                "content_blocks": [
                    {
                        "type": "list",
                        "ordered": True,
                        "items": [
                            "Commissioners Road will close overnight on Tuesday",
                            "Richmond Street will have one lane closed on Wednesday",
                            "Oxford Street work begins Thursday morning",
                        ],
                    }
                ],
            },
            {"id": "other", "title": "City council approves new housing plan"},
        ]
    }

    assert clean_payload(payload) == 0
    assert payload["stories"][0]["content_blocks"][0]["type"] == "list"


def main() -> int:
    test_promoted_story_list_is_removed()
    test_promoted_story_list_is_removed_even_when_titles_are_not_in_feed()
    test_real_numbered_list_is_preserved()
    print("PASS recirculation cleanup regressions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
