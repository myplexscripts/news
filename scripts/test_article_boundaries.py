from __future__ import annotations

from article_source_profiles import profile_for
from sanitize_article_blocks import sanitize_payload


def test_specific_profiles_do_not_compete_with_page_wrappers() -> None:
    profile = profile_for("CTV News", "https://www.ctvnews.ca/london/article/example/")
    assert profile["name"] == "ctv"
    assert "[data-testid='article-body']" in profile["roots"]
    assert ".articleBody" in profile["roots"]
    assert "article" not in profile["roots"]
    assert "main" not in profile["roots"]
    assert "main article" not in profile["roots"]


def test_page_shell_and_recirculation_are_trimmed_around_article() -> None:
    story = {
        "id": "ctv-page-shell",
        "source": "CTV News",
        "title": "Tornado watch lifted for London and Middlesex County, power outages remain across the region",
        "author": "Koylan Azofeifa Rueda",
        "url": "https://www.ctvnews.ca/london/article/example/",
        "content_status": "full",
        "content_blocks": [
            {"type": "paragraph", "text": "Skip to main content"},
            {"type": "heading", "text": "Sections Sections", "level": 2},
            {"type": "paragraph", "text": "Image 2: CTV News HomepageLocalCanadaWatchIn PicturesCTV Your MorningShopping TrendsCTV News NowLive"},
            {"type": "paragraph", "text": "Show Canada sub sections Canada Local Spotlight Royal Family Wildfires Alberta Referendum"},
            {"type": "paragraph", "text": "Share current article via Email Share current article via X Share current article via Reddit Share current article via LinkedIn"},
            {"type": "paragraph", "text": "By Koylan Azofeifa Rueda Opens in new window"},
            {"type": "image", "url": "https://images.example.test/storm.jpg", "alt": "Tree damage in Vanastra, Ont.", "caption": "Tree damage in Vanastra, Ont. (Source: Abigail Walter)"},
            {"type": "paragraph", "text": "Thousands of people remained without power across several southwestern Ontario communities after severe thunderstorms moved through the region Wednesday evening and damaged trees and utility lines."},
            {"type": "paragraph", "text": "Officials said crews were assessing outages and road closures while residents were asked to avoid downed wires and continue watching local weather alerts overnight."},
            {"type": "list", "ordered": False, "items": [
                "Highway 8 from Clinton to Road 140",
                "Highway 21 in Zurich between Zurich-Hensall Road and Sararas Road",
            ]},
            {"type": "paragraph", "text": "Report an Error"},
            {"type": "paragraph", "text": "Editorial standards & policies"},
            {"type": "paragraph", "text": "Why you can trust CTV News"},
            {"type": "heading", "text": "Koylan Azofeifa Rueda Opens in new window", "level": 2},
            {"type": "paragraph", "text": "Multimedia Journalist"},
            {"type": "heading", "text": "This nearly $26M cottage in Muskoka has a two-storey boathouse and enough space for 26 people", "level": 2},
            {"type": "heading", "text": "DVP closed due to flooding, thousands still without power after thunderstorms hit Toronto, GTA", "level": 2},
            {"type": "paragraph", "text": "Image 20: WATCH: Police help stranded drivers in flooded downtown Toronto underpass Video"},
            {"type": "heading", "text": "Potential tornado reported near Kitchener, Ont.", "level": 2},
        ],
    }
    payload = {"stories": [story]}

    assert sanitize_payload(payload) == 1

    blocks = story["content_blocks"]
    rendered = " | ".join(
        str(block.get("text") or block.get("caption") or " ".join(block.get("items", [])) or "")
        for block in blocks
    )

    assert "Tree damage in Vanastra" in rendered
    assert "Thousands of people remained without power" in rendered
    assert "Highway 8 from Clinton" in rendered
    assert "Skip to main content" not in rendered
    assert "Show Canada sub sections" not in rendered
    assert "Share current article" not in rendered
    assert "Report an Error" not in rendered
    assert "Editorial standards" not in rendered
    assert "$26M cottage" not in rendered
    assert "DVP closed" not in rendered
    assert "Image 20:" not in rendered
    assert "Potential tornado reported near Kitchener" not in rendered
    assert "article-start-boundary" in story.get("article_hygiene_flags", [])
    assert "article-end-boundary" in story.get("article_hygiene_flags", [])


def test_numbered_raw_image_labels_never_become_paragraphs() -> None:
    story = {
        "id": "raw-image-label",
        "source": "Example Publisher",
        "content_blocks": [
            {"type": "paragraph", "text": "The first real paragraph contains enough reporting to stand on its own in the article reader."},
            {"type": "paragraph", "text": "Image 21: Potential tornado reported near Kitchener, Ont."},
            {"type": "paragraph", "text": "The second real paragraph continues the report with additional context for readers in the region."},
        ],
    }
    payload = {"stories": [story]}
    assert sanitize_payload(payload) == 1
    assert len(story["content_blocks"]) == 2
    assert all("Image 21:" not in block.get("text", "") for block in story["content_blocks"])


def main() -> int:
    tests = [
        test_specific_profiles_do_not_compete_with_page_wrappers,
        test_page_shell_and_recirculation_are_trimmed_around_article,
        test_numbered_raw_image_labels_never_become_paragraphs,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
