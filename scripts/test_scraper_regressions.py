from __future__ import annotations

from unittest.mock import patch

from bs4 import BeautifulSoup

import fetch_news as scoop
from enrich_article_structure import parse_cbc_markdown, prune_recirculation_modules


def text_dump(blocks: list[dict]) -> str:
    return "\n".join(
        block.get("text", "") if block.get("type") != "list" else " | ".join(block.get("items", []))
        for block in blocks
    )


def test_normal_us_is_not_forced_to_country_acronym() -> None:
    assert scoop.normalize_source_case("Contact us if you can help.") == "Contact us if you can help."
    assert scoop.normalize_source_case("US officials visited London.") == "US officials visited London."


def test_postmedia_read_more_is_not_article_copy() -> None:
    html = """
    <article>
      <div class="article-body">
        <p>Police said the roads would remain closed for an undetermined amount of time as the investigation continued.</p>
        <p>Anyone who witnessed the collision or has footage is asked to call OPP at 1-888-310-1122. Anonymous tips can also be submitted.</p>
        <section class="article-read-more">
          <h2>Read More</h2>
          <a href="/news/windsor-man-wanted"><h3>Windsor man wanted since 2024 turns himself in to police</h3>
          <p>A Windsor man facing charges related to kidnapping, assault and extortion has surrendered after allegedly evading police since 2024.</p></a>
          <a href="/news/crash-video"><h3>SEE IT: Stunning video captures huge crash outside London school</h3></a>
        </section>
        <p>The investigation remains ongoing and police asked drivers to avoid the area while officers remained on scene.</p>
      </div>
    </article>
    """
    blocks, _, _ = scoop.extract_dom_blocks(
        BeautifulSoup(html, "html.parser"),
        "https://lfpress.com/news/local/collision-story",
        "London Free Press",
        "Collision closes area roads",
    )
    dumped = text_dump(blocks)
    assert "Windsor man wanted" not in dumped
    assert "Stunning video captures" not in dumped
    assert "investigation remains ongoing" in dumped.lower()


def test_postmedia_long_read_more_headline_does_not_resume_copy() -> None:
    blocks = [
        {
            "type": "paragraph",
            "text": "Sydney requires cranio-cervical fusion surgery and her family is raising money while pursuing medical coverage.",
        },
        {"type": "heading", "level": 2, "text": "Read More"},
        {
            "type": "paragraph",
            "text": "London dad pushing daughter's wheelchair 200 km in fight for $493K surgery as family appeals for out-of-country funding",
        },
        {
            "type": "paragraph",
            "text": "Union analysis warns of hospital woes ahead without jacked-up funding as Ontario health-care pressures continue",
        },
        {
            "type": "paragraph",
            "text": "Sydney has so far been denied out-of-country OHIP coverage. Her family says the appeal continues while they raise money for the surgery.",
        },
    ]
    cleaned = scoop.sanitize_content_blocks(
        blocks,
        "London Free Press",
        "London dad pushes wheelchair to raise money for daughter's surgery",
    )
    dumped = text_dump(cleaned)
    assert "wheelchair 200 km" not in dumped
    assert "hospital woes ahead" not in dumped
    assert "Sydney has so far been denied" in dumped


def test_ctv_inline_recirculation_does_not_truncate_story() -> None:
    html = """
    <article>
      <div class="article-body">
        <p>The London Police has laid more charges against a man in a child sexual abuse material investigation.</p>
        <p>The man initially was charged in May, after an investigation was launched in October 2025.</p>
        <h2>More from CTV News</h2>
        <a href="/london/article/unrelated-story"><p>This unrelated recommended story has enough words that a simple length test must not mistake it for the article body.</p></a>
        <p>Additional charges come after police say they found more evidence on seized devices during the continuing investigation.</p>
        <ul>
          <li>Possession of child pornography</li>
          <li>Import, sell or distribute child sexual abuse material</li>
          <li>Luring a person under 16 years of age by means of telecommunication</li>
        </ul>
        <p>He was initially charged after a search warrant was carried out at a home near Elias Street and Adelaide Street North.</p>
      </div>
    </article>
    """
    blocks, _, _ = scoop.extract_dom_blocks(
        BeautifulSoup(html, "html.parser"),
        "https://www.ctvnews.ca/london/article/london-police-charges/",
        "CTV News",
        "London police lay additional charges",
    )
    blocks = scoop.sanitize_content_blocks(blocks, "CTV News", "London police lay additional charges")
    dumped = text_dump(blocks)
    assert "unrelated recommended story" not in dumped.lower()
    assert "Additional charges come after police" in dumped
    assert "search warrant was carried out" in dumped
    lists = [block for block in blocks if block.get("type") == "list"]
    assert lists and len(lists[0].get("items", [])) == 3


def test_ctv_linked_promo_image_is_rejected() -> None:
    html = """
    <article>
      <div class="article-body">
        <p>Parents are worried about before and after school care in Huron County after another provider closed programs.</p>
        <p>Families say they are scrambling to make alternate arrangements before classes begin in September.</p>
        <a href="/london/article/unrelated-police-story">
          <img src="https://images.example.test/durham-police.jpg" width="900" height="600" alt="Durham police vehicle and unrelated person">
        </a>
        <p>School board officials said they continue to work with providers to find additional spaces for families.</p>
      </div>
    </article>
    """
    blocks, stats, _ = scoop.extract_dom_blocks(
        BeautifulSoup(html, "html.parser"),
        "https://www.ctvnews.ca/london/article/child-care-shortage/",
        "CTV News",
        "Parents frustrated by child-care shortage",
    )
    assert not any(block.get("type") == "image" for block in blocks)
    assert stats.get("images_rejected", 0) >= 1


def test_ctv_embedded_content_elements_keep_article_images() -> None:
    html = """
    <script id="fusion-metadata" type="application/javascript">
    Fusion.globalContent={
      "content_elements": [
        {"type": "text", "content": "The first paragraph has enough reporting about a local event to be useful, including where it happened, who attended, and why organizers said the gathering mattered to the surrounding neighbourhood."},
        {
          "type": "image",
          "url": "https://cloudfront.example.test/story-photo.jpg",
          "width": 1600,
          "height": 900,
          "subtitle": "The local event",
          "caption": "People gathered for the local event Tuesday."
        },
        {"type": "text", "content": "The second paragraph adds another useful detail from officials at the scene, including comments about next steps and how residents can expect the work to continue over the coming weeks."}
      ]
    };Fusion.arcSite="ctvnews";
    </script>
    """
    blocks, _ = scoop.extract_ctv_embedded_blocks(
        BeautifulSoup(html, "html.parser"),
        "Local event draws crowd",
        "https://www.ctvnews.ca/london/article/local-event/",
    )
    images = [block for block in blocks if block.get("type") == "image"]
    assert len(images) == 1
    assert images[0]["url"] == "https://cloudfront.example.test/story-photo.jpg"
    assert images[0]["width"] == 1600
    assert images[0]["height"] == 900


def test_ctv_canada_page_links_stay_in_canada_section() -> None:
    html = """
    <main>
      <a href="/canada/article/national-story-alpha">National story alpha</a>
      <a href="/london/article/local-story-beta">Local story beta</a>
    </main>
    """
    source = scoop.Source(
        name="CTV News Canada",
        url="https://www.ctvnews.ca/canada/",
        kind="page",
        homepage="https://www.ctvnews.ca/canada/",
        max_items=10,
    )

    with patch("fetch_news.fetch_html", return_value=(html, source.url)):
        links = scoop.page_links(source)

    assert links == ["https://www.ctvnews.ca/canada/article/national-story-alpha"]


def test_ctv_canada_enrich_uses_structured_embedded_body() -> None:
    html = """
    <html>
      <head>
        <meta property="og:title" content="National CTV story keeps its paragraphs">
        <meta property="og:description" content="A national story description.">
      </head>
      <body>
        <script id="fusion-metadata" type="application/javascript">
        Fusion.globalContent={
          "content_elements": [
            {"type": "text", "content": "The first paragraph explains the national story with enough detail about where it happened, who was involved, and why readers should understand the broader context."},
            {"type": "text", "content": "The second paragraph adds another full piece of reporting from officials and witnesses, keeping the article readable instead of merging every sentence into one long block."},
            {"type": "text", "content": "The third paragraph closes with practical next steps and additional background that belongs in the body, not in a flattened summary fallback."}
          ]
        };Fusion.arcSite="ctvnews";
        </script>
      </body>
    </html>
    """
    url = "https://www.ctvnews.ca/canada/article/national-story-alpha"
    source = scoop.Source(
        name="CTV News Canada",
        url="https://www.ctvnews.ca/canada/",
        kind="page",
        homepage="https://www.ctvnews.ca/canada/",
    )
    story = {
        "id": scoop.make_id(url),
        "title": "National CTV story keeps its paragraphs",
        "source": source.name,
        "source_home": source.homepage,
        "source_accent": source.accent,
        "url": url,
        "published": "2026-09-01T12:00:00+00:00",
        "summary": "A national story description.",
        "image": "",
        "author": "",
        "category": "Local",
    }

    with patch("fetch_news.fetch_html", return_value=(html, url)):
        enriched = scoop.enrich_article(story, source)

    assert enriched["quality"]["method"] == "embedded-json:ctv"
    assert len(enriched["paragraphs"]) == 3
    assert len(enriched["content_blocks"]) == 3
    assert all(block["type"] == "paragraph" for block in enriched["content_blocks"])
    assert all(len(paragraph) < 220 for paragraph in enriched["paragraphs"])


def test_author_images_are_rejected_from_article_blocks() -> None:
    html = """
    <article>
      <div class="article-body">
        <p>The article begins with real reporting from city hall about a budget update.</p>
        <figure>
          <img src="https://images.example.test/jane-smith.jpg" width="900" height="600" alt="Reporter Jane Smith headshot">
        </figure>
        <p>The article continues with more details about councillors and the public consultation process.</p>
      </div>
    </article>
    """
    blocks, _, _ = scoop.extract_dom_blocks(
        BeautifulSoup(html, "html.parser"),
        "https://example.test/story",
        "CBC News London",
        "Budget update",
    )
    assert not any(block.get("type") == "image" for block in blocks)


def test_ctv_embedded_author_image_is_rejected() -> None:
    html = """
    <script id="fusion-metadata" type="application/javascript">
    Fusion.globalContent={
      "content_elements": [
        {"type": "text", "content": "The first paragraph has enough reporting about a local event to be useful, including where it happened, who attended, and why organizers said the gathering mattered to the surrounding neighbourhood."},
        {
          "type": "image",
          "url": "https://cloudfront.example.test/reporter.jpg",
          "width": 1200,
          "height": 800,
          "subtitle": "Jane Smith",
          "caption": "CTV News reporter Jane Smith"
        },
        {"type": "text", "content": "The second paragraph adds another useful detail from officials at the scene, including comments about next steps and how residents can expect the work to continue over the coming weeks."}
      ]
    };Fusion.arcSite="ctvnews";
    </script>
    """
    blocks, _ = scoop.extract_ctv_embedded_blocks(
        BeautifulSoup(html, "html.parser"),
        "Local event draws crowd",
        "https://www.ctvnews.ca/london/article/local-event/",
    )
    assert not any(block.get("type") == "image" for block in blocks)


def test_cbc_markdown_author_image_is_rejected() -> None:
    raw = """
Markdown Content:

![Reporter Jane Smith headshot](https://images.example.test/jane-smith.jpg)

City officials said a budget update will be discussed at next week's council meeting, with transit and infrastructure spending both expected to be part of the debate.

Residents who spoke to CBC News said they want clearer timelines before councillors make a final decision on the proposal.
"""
    blocks = parse_cbc_markdown(raw, "Budget update heads to council")
    assert not any(block.get("type") == "image" for block in blocks)


def test_cbc_standalone_bold_is_not_promoted_to_heading() -> None:
    raw = """
Markdown Content:

Guikema spoke with the host a short time after Thursday's announcement and discussed the move to Canada.

**Nav Nanwa: What made you decide to leave the U.S. and come to Canada and Western University at this particular point of your career?**

Seth Guikema: Well, when looking at where things are going in my future career, I think Western offers an incredibly strong environment for doing this sort of research.
"""
    blocks = parse_cbc_markdown(raw, "Western recruits leading researcher")
    question = next(block for block in blocks if block.get("text", "").startswith("Nav Nanwa:"))
    assert question.get("type") == "paragraph"
    assert question.get("emphasis") == "strong"
    assert not any(block.get("type") == "heading" and block.get("text", "").startswith("Nav Nanwa:") for block in blocks)


def test_cbc_related_story_list_is_not_article_copy() -> None:
    raw = """
Markdown Content:

The judge heard testimony from several witnesses before delivering the decision in the case.

## Read More

1. [Why a judge rejected self-defence in police officer stabbing case](https://www.cbc.ca/news/canada/london/story-one-1.1234567)
2. [Youth who murdered 11-year-old girl could be sentenced in October](https://www.cbc.ca/news/canada/london/story-two-1.1234568)

Jeff Chapman, a neighbourhood resident, said the case has had a lasting effect on people who live nearby.
"""
    blocks = parse_cbc_markdown(raw, "Court case continues in London")
    dumped = text_dump(blocks)
    assert "judge rejected self-defence" not in dumped
    assert "Youth who murdered" not in dumped
    assert "Jeff Chapman" in dumped
    assert not any(block.get("type") == "list" for block in blocks)


def test_generic_read_more_card_module_is_pruned_before_extraction() -> None:
    html = """
    <article>
      <p>The brewery is considering bringing back several older beers for a limited time as part of its relaunch.</p>
      <div>
        <h2>Read More</h2>
        <div>
          <a href="/news/local-news/sour-suite">Brews News: A sour suite for summer's end</a>
          <a href="/news/local-news/anniversary">Brews News: Anderson marks 10 years with anniversary bash</a>
        </div>
      </div>
      <p>But not everything can be backward-looking, and the current brewers are introducing new recipes as well.</p>
    </article>
    """
    soup = BeautifulSoup(html, "html.parser")
    prune_recirculation_modules(soup)
    text = soup.get_text(" ", strip=True)
    assert "sour suite" not in text
    assert "Anderson marks" not in text
    assert "bringing back several older beers" in text
    assert "current brewers are introducing" in text


def main() -> int:
    tests = [
        test_normal_us_is_not_forced_to_country_acronym,
        test_postmedia_read_more_is_not_article_copy,
        test_postmedia_long_read_more_headline_does_not_resume_copy,
        test_ctv_inline_recirculation_does_not_truncate_story,
        test_ctv_linked_promo_image_is_rejected,
        test_ctv_embedded_content_elements_keep_article_images,
        test_ctv_canada_page_links_stay_in_canada_section,
        test_ctv_canada_enrich_uses_structured_embedded_body,
        test_author_images_are_rejected_from_article_blocks,
        test_ctv_embedded_author_image_is_rejected,
        test_cbc_markdown_author_image_is_rejected,
        test_cbc_standalone_bold_is_not_promoted_to_heading,
        test_cbc_related_story_list_is_not_article_copy,
        test_generic_read_more_card_module_is_pruned_before_extraction,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
