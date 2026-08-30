from __future__ import annotations

import sweep_article_quality as sweep
from sweep_article_quality import (
    clean_blocks,
    ensure_readable_fallback,
    prune_dom_modules,
    remaining_hygiene_flags,
    text_key,
)


def titles(*values: str) -> set[str]:
    return {text_key(value) for value in values}


def test_ad_and_publisher_utility_are_removed() -> None:
    blocks = [
        {"type": "paragraph", "text": "The real article begins with a complete sentence about the event."},
        {"type": "paragraph", "text": "Advertisement"},
        {"type": "paragraph", "text": "Enjoy the latest local, national and international news."},
        {"type": "paragraph", "text": "The article continues after the publisher interruption with another complete sentence."},
    ]
    cleaned, removed = clean_blocks(blocks, title="Main story", known_titles=set())
    dumped = " | ".join(str(block.get("text") or "") for block in cleaned)
    assert "Advertisement" not in dumped
    assert "Enjoy the latest" not in dumped
    assert "article continues" in dumped
    assert removed


def test_related_heading_image_rail_is_removed_but_article_resumes() -> None:
    related_a = "Council approves a different downtown housing proposal"
    related_b = "Police identify driver in Highway 401 collision"
    related_c = "Province announces new transit funding for London"
    blocks = [
        {"type": "paragraph", "text": "The first half of the article contains normal reporting and ends with a complete sentence."},
        {"type": "heading", "level": 3, "text": related_a},
        {"type": "image", "url": "https://example.test/a.jpg", "alt": "City hall"},
        {"type": "heading", "level": 3, "text": related_b},
        {"type": "image", "url": "https://example.test/b.jpg", "alt": "Highway"},
        {"type": "heading", "level": 3, "text": related_c},
        {"type": "image", "url": "https://example.test/c.jpg", "alt": "Bus"},
        {"type": "paragraph", "text": "The real article resumes here with another complete sentence after the inserted publisher rail."},
    ]
    cleaned, _ = clean_blocks(blocks, title="Main story", known_titles=titles(related_a, related_b))
    dumped = " | ".join(str(block.get("text") or block.get("url") or "") for block in cleaned)
    assert related_a not in dumped
    assert related_b not in dumped
    assert "real article resumes" in dumped


def test_unlabelled_future_publisher_card_rail_is_removed_without_title_matches() -> None:
    blocks = [
        {"type": "paragraph", "text": "The article opens with ordinary prose about the subject being reported."},
        {"type": "heading", "level": 3, "text": "First unrelated headline about another event"},
        {"type": "image", "url": "https://example.test/a.jpg", "alt": "Photo A"},
        {"type": "heading", "level": 3, "text": "Second unrelated headline about another event"},
        {"type": "image", "url": "https://example.test/b.jpg", "alt": "Photo B"},
        {"type": "heading", "level": 3, "text": "Third unrelated headline about another event"},
        {"type": "image", "url": "https://example.test/c.jpg", "alt": "Photo C"},
        {"type": "paragraph", "text": "The article resumes with substantive reporting after the unrelated cards."},
    ]
    cleaned, _ = clean_blocks(blocks, title="Main story", known_titles=set())
    dumped = " | ".join(str(block.get("text") or "") for block in cleaned)
    assert "First unrelated headline" not in dumped
    assert "article resumes" in dumped


def test_real_article_headings_and_images_are_preserved() -> None:
    blocks = [
        {"type": "heading", "level": 2, "text": "What happens next"},
        {"type": "paragraph", "text": "Officials said the proposal will return to council next month for a final vote."},
        {"type": "image", "url": "https://example.test/council.jpg", "alt": "Council chamber", "caption": "Council met Tuesday."},
        {"type": "heading", "level": 2, "text": "Public response"},
        {"type": "paragraph", "text": "Residents said they plan to attend the next meeting and submit written comments."},
    ]
    cleaned, removed = clean_blocks(blocks, title="Main story", known_titles=set())
    assert cleaned == blocks
    assert removed == []


def test_real_unlinked_list_is_preserved() -> None:
    blocks = [{
        "type": "list",
        "ordered": False,
        "items": [
            "Possession of a controlled substance for the purpose of trafficking;",
            "Unauthorized possession of a firearm;",
            "Possession of property obtained by crime over $5,000.",
        ],
    }]
    cleaned, removed = clean_blocks(blocks, title="Police release", known_titles=set())
    assert cleaned == blocks
    assert removed == []


def test_breadcrumb_navigation_list_is_removed() -> None:
    blocks = [
        {"type": "list", "ordered": False, "items": [
            {"text": "Home", "html": '<a href="https://example.test/">Home</a>'},
            {"text": "News", "html": '<a href="https://example.test/news">News</a>'},
            {"text": "Canada", "html": '<a href="https://example.test/canada">Canada</a>'},
        ]},
        {"type": "paragraph", "text": "The actual article begins here with a complete sentence about the news."},
    ]
    cleaned, _ = clean_blocks(blocks, title="Main story", known_titles=set())
    assert len(cleaned) == 1
    assert cleaned[0]["type"] == "paragraph"


def test_standalone_related_link_is_removed_but_inline_link_stays() -> None:
    related = "Another publisher headline that is also in our feed"
    blocks = [
        {
            "type": "paragraph",
            "text": "The city report can be read online and contains the complete findings.",
            "html": 'The <a href="https://example.test/report">city report</a> can be read online and contains the complete findings.',
        },
        {
            "type": "paragraph",
            "text": related,
            "html": f'<a href="https://example.test/related">{related}</a>',
        },
    ]
    cleaned, _ = clean_blocks(blocks, title="Main story", known_titles=titles(related))
    assert len(cleaned) == 1
    assert "city report" in cleaned[0]["html"]


def test_generic_dom_pruner_removes_future_modules() -> None:
    raw = """
    <html><body><main><article>
      <div class="articleBody">
        <p>The real article starts here with enough meaningful reporting to keep.</p>
        <div class="recommendationRail"><h3>Related stories</h3><a href="/a">Unrelated headline one here</a><a href="/b">Unrelated headline two here</a></div>
        <section data-component="ad-slot"><p>Advertisement</p></section>
        <p>The real article continues here after the modules have been removed.</p>
      </div>
    </article></main></body></html>
    """
    cleaned = prune_dom_modules(raw)
    assert "recommendationRail" not in cleaned
    assert "Advertisement" not in cleaned
    assert "real article starts" in cleaned
    assert "real article continues" in cleaned


def test_wall_of_text_fallback_only_splits_flat_copy() -> None:
    sentence = "This sentence contains useful reporting about the event and ends normally."
    long_text = " ".join(sentence for _ in range(45))
    blocks = [{"type": "paragraph", "text": long_text}]
    rebuilt, changed = ensure_readable_fallback(blocks)
    assert changed
    assert len(rebuilt) >= 3
    assert all(block["type"] == "paragraph" for block in rebuilt)


def test_hygiene_flags_are_empty_after_cleanup() -> None:
    related_a = "First unrelated headline about another event"
    related_b = "Second unrelated headline about another event"
    blocks = [
        {"type": "paragraph", "text": "Normal article prose begins here with a complete sentence."},
        {"type": "heading", "text": related_a, "level": 3},
        {"type": "image", "url": "https://example.test/a.jpg"},
        {"type": "heading", "text": related_b, "level": 3},
        {"type": "image", "url": "https://example.test/b.jpg"},
        {"type": "heading", "text": "Third unrelated headline from the publisher", "level": 3},
        {"type": "image", "url": "https://example.test/c.jpg"},
        {"type": "paragraph", "text": "Normal article prose resumes here with another complete sentence."},
    ]
    cleaned, _ = clean_blocks(blocks, title="Main story", known_titles=titles(related_a, related_b))
    assert remaining_hygiene_flags(cleaned, titles(related_a, related_b), "Main story") == []


def test_trafilatura_xml_candidate_preserves_structure() -> None:
    xml = """<doc><main><head rend="#h2">Key findings</head><p>The report contains <hi rend="#b">important</hi> findings and <ref target="/report">supporting documents</ref>.</p><list><item>First finding is documented.</item><item>Second finding is documented.</item></list></main></doc>"""
    original = sweep.trafilatura_extract
    original_dom = sweep.extract_dom_blocks
    captured = {}
    try:
        sweep.trafilatura_extract = lambda *args, **kwargs: xml
        def fake_dom(raw: str, final_url: str, title: str, hero: str):
            captured["raw"] = raw
            return [{"type": "paragraph", "text": "ok", "html": "ok"}]
        sweep.extract_dom_blocks = fake_dom
        blocks = sweep.trafilatura_formatted_blocks("<html></html>", "https://example.test/story", "Story", "")
    finally:
        sweep.trafilatura_extract = original
        sweep.extract_dom_blocks = original_dom
    assert blocks
    transformed = captured["raw"]
    assert "<h2" in transformed
    assert "<strong" in transformed
    assert '<a href="https://example.test/report"' in transformed
    assert "<ul" in transformed and "<li" in transformed


def main() -> int:
    tests = [value for name, value in globals().items() if name.startswith("test_") and callable(value)]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print(f"PASS universal article sweep regressions ({len(tests)} tests)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
