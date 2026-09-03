from __future__ import annotations

from article_source_profiles import profile_for
from refine_source_articles import coverage_ok, extract_profiled_blocks


def dump(blocks: list[dict]) -> str:
    parts: list[str] = []
    for block in blocks:
        if block.get("text"):
            parts.append(str(block["text"]))
        for item in block.get("items", []) if isinstance(block.get("items"), list) else []:
            parts.append(str(item.get("text") if isinstance(item, dict) else item))
    return " | ".join(parts)


def article_fixture(root_class: str, promo_class: str, promo_label: str = "Read More") -> str:
    return f"""
    <html><body>
      <article>
        <div class="{root_class}">
          <p>London residents gathered Tuesday evening to discuss a local proposal that has been under review for several months.</p>
          <p>Officials said the revised plan responds to concerns raised during earlier public meetings and includes several new safeguards.</p>
          <section class="{promo_class}">
            <h2>{promo_label}</h2>
            <a href="/other-story">Unrelated promoted headline about another London story</a>
            <a href="/second-story">Another unrelated story promoted by the publisher</a>
          </section>
          <h2>What happens next</h2>
          <p>The proposal will return for another public meeting next month before a final decision is made by the responsible body.</p>
        </div>
      </article>
    </body></html>
    """


def assert_profile(source: str, url: str, expected: str, root_class: str, promo_class: str) -> None:
    profile = profile_for(source, url)
    assert profile["name"] == expected
    blocks, used = extract_profiled_blocks(article_fixture(root_class, promo_class), url, source, "Local proposal moves forward")
    assert used == expected
    text = dump(blocks)
    assert "London residents gathered" in text
    assert "What happens next" in text
    assert "return for another public meeting" in text
    assert "Unrelated promoted headline" not in text
    assert "Another unrelated story" not in text


def test_postmedia_profile() -> None:
    assert_profile(
        "London Free Press",
        "https://lfpress.com/news/local/example",
        "postmedia",
        "article-content",
        "read-more-module",
    )


def test_ctv_profile() -> None:
    assert_profile(
        "CTV News",
        "https://www.ctvnews.ca/london/article/example/",
        "ctv",
        "articleBody",
        "related-stories",
    )


def test_global_profile() -> None:
    assert_profile(
        "Global News London",
        "https://globalnews.ca/news/example/",
        "global",
        "l-article__body",
        "l-article__related",
    )


def test_globe_profile_removes_diversions() -> None:
    assert_profile(
        "The Globe and Mail",
        "https://www.theglobeandmail.com/canada/article-example/",
        "globe",
        "c-article-body",
        "diversions-module",
    )


def test_star_profile_removes_dropdown_navigation() -> None:
    assert_profile(
        "Toronto Star",
        "https://www.thestar.com/news/canada/example.html",
        "star",
        "asset-content",
        "dropdown-menu",
    )


def test_western_profile() -> None:
    assert_profile(
        "Western News",
        "https://news.westernu.ca/2026/08/example/",
        "western",
        "entry-content",
        "related-posts",
    )


def test_london_police_profile() -> None:
    assert_profile(
        "London Police Service",
        "https://www.londonpolice.ca/news/example",
        "police",
        "news-article-content",
        "related",
    )


def test_city_profile() -> None:
    assert_profile(
        "City of London Newsroom",
        "https://london.ca/newsroom/example",
        "municipal",
        "field--name-body",
        "related",
    )


def test_cbc_profile_is_explicit() -> None:
    profile = profile_for("CBC News London", "https://www.cbc.ca/news/canada/london/example-1.1234567")
    assert profile["name"] == "cbc"
    assert "[data-cy='storyWrapper']" in profile["roots"]


def test_profile_candidate_can_replace_known_chrome_contamination() -> None:
    story = {
        "source": "Toronto Star",
        "word_count": 900,
        "content_blocks": [
            {"type": "heading", "text": "Today's paper"},
            {"type": "list", "items": ["Ontario", "Alberta", "Quebec", "Wildfires"]},
        ],
    }
    prose = "Officials said the proposal would return next month after another public meeting with residents and community groups. "
    blocks = [
        {"type": "paragraph", "text": prose * 3},
        {"type": "paragraph", "text": prose * 3},
        {"type": "paragraph", "text": prose * 3},
    ]
    assert coverage_ok(story, blocks)


def test_unknown_source_uses_generic_fallback() -> None:
    profile = profile_for("Independent Publisher", "https://example.test/local/story")
    assert profile["name"] == "generic"
    blocks, used = extract_profiled_blocks(
        article_fixture("article-body", "related-stories"),
        "https://example.test/local/story",
        "Independent Publisher",
        "Independent story",
    )
    assert used == "generic"
    text = dump(blocks)
    assert "London residents gathered" in text
    assert "Unrelated promoted headline" not in text


def main() -> int:
    tests = [
        test_postmedia_profile,
        test_ctv_profile,
        test_global_profile,
        test_globe_profile_removes_diversions,
        test_star_profile_removes_dropdown_navigation,
        test_western_profile,
        test_london_police_profile,
        test_city_profile,
        test_cbc_profile_is_explicit,
        test_profile_candidate_can_replace_known_chrome_contamination,
        test_unknown_source_uses_generic_fallback,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
