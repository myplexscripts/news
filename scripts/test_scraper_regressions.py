from __future__ import annotations

from bs4 import BeautifulSoup

import fetch_news as scoop


def text_dump(blocks: list[dict]) -> str:
    return "\n".join(
        block.get("text", "") if block.get("type") != "list" else " | ".join(block.get("items", []))
        for block in blocks
    )


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


def main() -> int:
    tests = [
        test_postmedia_read_more_is_not_article_copy,
        test_ctv_inline_recirculation_does_not_truncate_story,
        test_ctv_linked_promo_image_is_rejected,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
