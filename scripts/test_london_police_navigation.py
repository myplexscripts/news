from __future__ import annotations

from cleanup_london_police_navigation import clean_story


def test_navigation_and_footer_are_trimmed() -> None:
    story = {
        "source": "London Police Service",
        "url": "https://www.londonpolice.ca/news/posts/replica-firearms-drugs-and-identity-documents-seized-26-89754/",
        "title": "Replica firearms, drugs and identity documents seized 26-89754",
        "content_blocks": [
            {"type": "heading", "level": 2, "text": "Services"},
            {"type": "list", "ordered": False, "items": ["Record Checks", "Crime Map", "Online Reporting"]},
            {"type": "heading", "level": 2, "text": "About"},
            {"type": "heading", "level": 2, "text": "REPLICA FIREARMS, DRUGS AND IDENTITY DOCUMENTS SEIZED"},
            {"type": "paragraph", "text": "London man facing multiple charges"},
            {"type": "paragraph", "text": "LONDON, ON (September 8, 2026) – A suspect was arrested within minutes of a weapons complaint Monday evening."},
            {"type": "paragraph", "text": "The following items were seized:"},
            {"type": "list", "ordered": False, "items": ["Two replica firearms", "Multiple bank cards", "Drug paraphernalia"]},
            {"type": "paragraph", "text": "The accused remains in custody and is expected to appear in London court today in relation to the charges."},
            {"type": "paragraph", "text": "For media inquiries, contact:"},
            {"type": "paragraph", "text": "Media Relations Officer"},
            {"type": "paragraph", "text": "Contact Us"},
        ],
    }

    assert clean_story(story)
    blocks = story["content_blocks"]
    text = " | ".join(str(block.get("text") or " ".join(block.get("items", []))) for block in blocks)
    assert "Services" not in text
    assert "Record Checks" not in text
    assert "About" not in text
    assert "For media inquiries" not in text
    assert "Media Relations Officer" not in text
    assert "Two replica firearms" in text
    assert "London man facing multiple charges" in text
    assert story["lps_navigation_removed"] >= 5


def test_dateline_anchor_preserves_editorial_subheading() -> None:
    story = {
        "source": "London Police Service",
        "url": "https://www.londonpolice.ca/news/posts/missing-person/",
        "title": "Missing person 26-88253",
        "content_blocks": [
            {"type": "heading", "level": 2, "text": "Community"},
            {"type": "list", "ordered": False, "items": ["Programs", "Youth Safety", "Crime Prevention Tips"]},
            {"type": "heading", "level": 3, "text": "Seeking the public's assistance"},
            {"type": "paragraph", "text": "LONDON, ON (September 8, 2026) – The London Police Service is requesting the public’s assistance in locating a missing person."},
            {"type": "paragraph", "text": "Anyone with information is asked to contact the London Police Service."},
        ],
    }

    assert clean_story(story)
    assert story["content_blocks"][0]["text"] == "Seeking the public's assistance"
    assert story["content_blocks"][1]["text"].startswith("LONDON, ON")


def test_collapsed_menu_text_is_trimmed_inside_first_paragraph() -> None:
    story = {
        "source": "London Police Service",
        "url": "https://www.londonpolice.ca/news/posts/test-release/",
        "title": "Test release 26-90000",
        "paragraphs": [
            "Services Careers Community Crime Prevention About Expand Search LONDON, ON (September 10, 2026) – This is the real opening paragraph of the release.",
            "This is the second paragraph of the release and should remain intact.",
            "For media enquiries, contact: Media Relations Officer 519-661-5410",
        ],
    }

    assert clean_story(story)
    assert story["paragraphs"][0].startswith("LONDON, ON")
    assert "Services Careers" not in story["content"]
    assert "Media Relations Officer" not in story["content"]


def test_non_lps_story_is_untouched() -> None:
    story = {
        "source": "CBC News London",
        "url": "https://www.cbc.ca/news/canada/london/example",
        "title": "Example",
        "content_blocks": [{"type": "paragraph", "text": "LONDON, ON (September 8, 2026) – Example story."}],
    }
    before = dict(story)
    assert not clean_story(story)
    assert story == before


def main() -> int:
    test_navigation_and_footer_are_trimmed()
    test_dateline_anchor_preserves_editorial_subheading()
    test_collapsed_menu_text_is_trimmed_inside_first_paragraph()
    test_non_lps_story_is_untouched()
    print("London Police navigation cleanup regression tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
