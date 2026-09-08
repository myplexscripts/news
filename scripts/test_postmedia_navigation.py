from __future__ import annotations

from cleanup_postmedia_navigation import clean_payload


def rendered(story: dict) -> str:
    parts: list[str] = []
    for block in story.get("content_blocks", []):
        if block.get("type") == "list":
            parts.extend(str(item.get("text") if isinstance(item, dict) else item) for item in block.get("items", []))
        else:
            parts.append(str(block.get("text") or block.get("caption") or block.get("alt") or ""))
    return " | ".join(parts)


def test_lfpress_navigation_menu_is_removed() -> None:
    story = {
        "source": "London Free Press",
        "url": "https://lfpress.com/news/local-news/example-story",
        "title": "Police seize replica firearms in London investigation",
        "content_blocks": [
            {"type": "image", "url": "https://example.com/hero.jpg", "alt": "Police vehicle"},
            {"type": "list", "ordered": False, "items": ["Advice", "Horoscopes", "Weather"]},
            {"type": "list", "ordered": False, "items": [
                "Lives Told\")", "Tails Told\")", "Shopping\")", "London Free Press Store\")",
                "Puzzmo\")", "Diversions", "Puzzles", "Comics",
            ]},
            {"type": "list", "ordered": False, "items": [
                "Healthing", "Driving", "Vehicle Research\")", "Reviews\")", "News\")", "Gear Guide\")",
            ]},
            {"type": "list", "ordered": False, "items": [
                "Ontario Farmer", "ePaper\")", "Obituaries\")", "Place an Obituary\")", "Place an In Memoriam\")",
            ]},
            {"type": "paragraph", "text": "Police seized two replica firearms, drugs and identity documents belonging to other people during an investigation in London on Tuesday afternoon."},
            {"type": "paragraph", "text": "Investigators said the evidence was collected after officers executed a search warrant and the investigation remains ongoing."},
        ],
    }
    payload = {"stories": [story]}
    assert clean_payload(payload) == 1
    text = rendered(story)
    for junk in [
        "Advice", "Horoscopes", "Weather", "Lives Told", "Puzzmo", "Vehicle Research",
        "Ontario Farmer", "ePaper", "Obituaries", "Place an In Memoriam",
    ]:
        assert junk not in text
    assert "Police seized two replica firearms" in text
    assert "Investigation remains ongoing".lower() in text.lower()
    assert any(block.get("type") == "image" for block in story["content_blocks"])


def test_lfpress_real_editorial_list_is_preserved() -> None:
    story = {
        "source": "London Free Press",
        "url": "https://lfpress.com/news/local-news/road-closures",
        "title": "Road closures planned across London",
        "content_blocks": [
            {"type": "paragraph", "text": "Several London roads will close this week while city crews complete construction work in neighbourhoods across the city."},
            {"type": "list", "ordered": False, "items": [
                "Richmond Street will close Tuesday evening between Oxford Street and Central Avenue.",
                "Dundas Street will have one lane closed Wednesday morning near Adelaide Street.",
                "Wellington Road construction continues Thursday with local access maintained for residents.",
            ]},
        ],
    }
    payload = {"stories": [story]}
    assert clean_payload(payload) == 0
    assert story["content_blocks"][1]["type"] == "list"
    assert len(story["content_blocks"][1]["items"]) == 3


def test_split_lfpress_menu_labels_are_removed_before_story_prose() -> None:
    story = {
        "source": "The London Free Press",
        "url": "https://lfpress.com/news/local-news/example",
        "title": "Local news story",
        "content_blocks": [
            {"type": "paragraph", "text": "News"},
            {"type": "paragraph", "text": "Sports"},
            {"type": "paragraph", "text": "Opinion"},
            {"type": "paragraph", "text": "Manage Print Subscription"},
            {"type": "paragraph", "text": "Police said officers remained at the scene Tuesday evening while investigators gathered evidence and asked nearby residents to avoid the area."},
        ],
    }
    payload = {"stories": [story]}
    assert clean_payload(payload) == 1
    text = rendered(story)
    assert "Manage Print Subscription" not in text
    assert "Sports" not in text
    assert "Police said officers remained" in text


def main() -> int:
    tests = [
        test_lfpress_navigation_menu_is_removed,
        test_lfpress_real_editorial_list_is_preserved,
        test_split_lfpress_menu_labels_are_removed_before_story_prose,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
