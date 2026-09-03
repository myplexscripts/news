from __future__ import annotations

from enrich_rich_articles import (
    block_words,
    merge_rich_blocks,
    normalize_embed_url,
    parse_dom,
    repair_blocks,
    richness,
)


def test_semantic_order_and_original_image_ratio() -> None:
    raw = """
    <html><body><article>
      <p>The storm crossed the region Wednesday afternoon and left thousands of customers without power.</p>
      <figure>
        <picture>
          <source srcset="/storm-640.jpg 640w, /storm-1600.jpg 1600w">
          <img src="/storm-thumb.jpg" width="1600" height="1067" alt="Dark skies over London">
        </picture>
        <figcaption>Dark skies over London, Ont.</figcaption>
      </figure>
      <h2>Power outages continue</h2>
      <p>Hydro crews continued restoration work into the evening across several affected communities.</p>
      <ul><li>Grand Bend</li><li>Goderich</li></ul>
      <blockquote>Residents should stay clear of downed power lines.</blockquote>
    </article></body></html>
    """
    blocks = parse_dom(raw, "https://example.test/news/storm", "Example News", "Storm update")
    kinds = [block["type"] for block in blocks]
    assert kinds == ["paragraph", "image", "heading", "paragraph", "list", "quote"]
    image = blocks[1]
    assert image["url"] == "https://example.test/storm-1600.jpg"
    assert image["width"] == 1600
    assert image["height"] == 1067
    assert image["caption"] == "Dark skies over London, Ont."


def test_twitter_post_becomes_real_embed() -> None:
    raw = """
    <article>
      <p>Police shared an update from the affected area shortly after the storm passed through.</p>
      <blockquote class="twitter-tweet">
        <p>Crews are responding to several roads blocked by fallen trees.</p>
        <a href="https://twitter.com/OPP_WR/status/1234567890123456789">September 2, 2026</a>
      </blockquote>
      <p>Officials asked drivers to avoid the area while cleanup continued.</p>
    </article>
    """
    blocks = parse_dom(raw, "https://example.test/story", "Example News", "Storm update")
    assert [block["type"] for block in blocks] == ["paragraph", "media", "paragraph"]
    embed = blocks[1]
    assert embed["provider"] == "x"
    assert "platform.twitter.com/embed/Tweet.html?id=1234567890123456789" in embed["url"]
    assert embed["source_url"].startswith("https://twitter.com/")


def test_instagram_youtube_and_tiktok_normalization() -> None:
    instagram, provider, _ = normalize_embed_url("https://www.instagram.com/p/ABC123xyz/")
    assert provider == "instagram" and "/p/ABC123xyz/embed/captioned/" in instagram
    youtube, provider, _ = normalize_embed_url("https://www.youtube.com/watch?v=abcDEF123")
    assert provider == "youtube" and "youtube-nocookie.com/embed/abcDEF123" in youtube
    tiktok, provider, _ = normalize_embed_url("https://www.tiktok.com/@news/video/7412345678901234567")
    assert provider == "tiktok" and "/player/v1/7412345678901234567" in tiktok


def test_article_chrome_and_author_images_are_not_content() -> None:
    raw = """
    <article>
      <div class="author-card"><img src="/reporter.jpg" alt="Reporter headshot"></div>
      <p>Officials said the cleanup would continue through Thursday after the severe storm.</p>
      <div class="advertisement"><img src="/ad.jpg" alt="Sponsored advertisement"></div>
      <p>Residents were asked to report downed lines and avoid damaged trees.</p>
    </article>
    """
    blocks = parse_dom(raw, "https://example.test/story", "Example News", "Cleanup continues")
    assert [block["type"] for block in blocks] == ["paragraph", "paragraph"]


def test_fragmented_paragraphs_and_raw_media_labels_are_repaired() -> None:
    blocks = repair_blocks([
        {"type": "paragraph", "text": "Updated CBC News | Posted: September 2, 2026 11:01 AM | Last Updated: 1 hour ago"},
        {"type": "paragraph", "text": "Image | Dark skies over London, Ont."},
        {"type": "image", "url": "https://i.cbc.ca/storm.jpg", "alt": "Dark skies", "caption": ""},
        {"type": "paragraph", "text": "Caption: Dark skies formed over London as thunderstorms passed through the region."},
        {"type": "paragraph", "text": "Several roads in the region"},
        {"type": "paragraph", "text": "have also been impacted by fallen trees and downed power lines."},
    ])
    assert blocks[0]["type"] == "image"
    assert blocks[0]["caption"].startswith("Dark skies formed")
    assert blocks[1]["text"] == "Several roads in the region have also been impacted by fallen trees and downed power lines."


def test_rich_media_can_merge_without_replacing_longer_body() -> None:
    existing = [
        {"type": "paragraph", "text": "The first paragraph contains the complete article text and enough words to anchor media correctly."},
        {"type": "paragraph", "text": "The second paragraph continues the complete report with more details from officials and residents."},
    ]
    candidate = [
        {"type": "paragraph", "text": existing[0]["text"]},
        {"type": "media", "media_type": "embed", "provider": "x", "url": "https://platform.twitter.com/embed/Tweet.html?id=123&dnt=true"},
        {"type": "paragraph", "text": existing[1]["text"]},
    ]
    merged, inserted = merge_rich_blocks(existing, candidate)
    assert inserted == 1
    assert merged[1]["type"] == "media"
    assert block_words(merged) == block_words(existing)
    assert richness(merged)["embeds"] == 1


def main() -> int:
    tests = [
        test_semantic_order_and_original_image_ratio,
        test_twitter_post_becomes_real_embed,
        test_instagram_youtube_and_tiktok_normalization,
        test_article_chrome_and_author_images_are_not_content,
        test_fragmented_paragraphs_and_raw_media_labels_are_repaired,
        test_rich_media_can_merge_without_replacing_longer_body,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print("Rich article contracts passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
