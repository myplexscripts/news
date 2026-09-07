from __future__ import annotations

from unittest.mock import patch

from bs4 import BeautifulSoup

import enrich_article_media as media
import fetch_news as scoop


def test_cbc_srcset_keeps_literal_asset_comma() -> None:
    value = (
        "https://i.cbc.ca/ais/abc-123,1788727815050/full/max/0/default.jpg?im=Resize%3D796 796w,"
        "https://i.cbc.ca/ais/abc-123,1788727815050/full/max/0/default.jpg?im=Resize%3D1280 1280w"
    )
    candidates = scoop.srcset_candidates(value)
    assert candidates[-1][0] == 1280
    best = max(candidates, key=lambda item: item[0])[1]
    assert best.startswith("https://i.cbc.ca/ais/abc-123,1788727815050/")
    assert "/default.jpg" in best


def test_cbc_default_jpg_is_not_treated_as_placeholder() -> None:
    url = "https://i.cbc.ca/ais/abc-123,1788727815050/full/max/0/default.jpg?im=Resize%3D1280"
    assert scoop.valid_article_image(url)


def test_cbc_story_wrapper_keeps_real_photos_and_drops_player_thumbnail() -> None:
    raw = """
    <main>
      <div data-cy="storyWrapper">
        <p>London transit riders are using the new centre-running lanes after construction was completed.</p>
        <div class="player-placeholder-video-ui" data-cy="player-placeholder-ui-container">
          <img src="https://i.cbc.ca/ais/video,1700000000000/full/max/0/default.jpg?im=Resize%3D620" width="620" height="349">
        </div>
        <figure class="imageMedia image full">
          <picture>
            <img src="https://i.cbc.ca/ais/photo,1788727815050/full/max/0/default.jpg"
                 srcset="https://i.cbc.ca/ais/photo,1788727815050/full/max/0/default.jpg?im=Resize%3D796 796w,https://i.cbc.ca/ais/photo,1788727815050/full/max/0/default.jpg?im=Resize%3D1280 1280w"
                 width="1200" height="675" alt="A rider boards the bus">
          </picture>
          <figcaption>A rider boards from the new centre platform. (CBC)</figcaption>
        </figure>
        <p>Officials said the platform and signals are intended to make service faster and safer.</p>
      </div>
    </main>
    """
    blocks, stats, method = scoop.extract_dom_blocks(
        BeautifulSoup(raw, "html.parser"),
        "https://www.cbc.ca/news/canada/london/example-9.1234567",
        "CBC News London",
        "London bus lanes open",
        "",
    )
    images = [block for block in blocks if block.get("type") == "image"]
    assert method.startswith("dom:cbc:")
    assert len(images) == 1, (images, stats)
    assert images[0]["url"].startswith("https://i.cbc.ca/ais/photo,1788727815050/")
    assert "Resize%3D1280" in images[0]["url"]


def test_globe_prefers_content_gate_over_whole_main() -> None:
    raw = """
    <main id="main-content">
      <article id="content-gate">
        <p>The first reported paragraph contains enough detail to identify the actual article body for extraction.</p>
        <figure><img src="https://www.theglobeandmail.com/resizer/v2/REAL.JPG?width=1200" width="600" height="400"></figure>
        <p>The second reported paragraph continues the story with additional information from the scene.</p>
      </article>
      <section class="recommendations">
        <article><p>Recommended story text that should not cause the whole main element to win article-root scoring.</p></article>
        <article><p>Another recommended story with extra copy that belongs outside the current article.</p></article>
        <article><p>A third recommendation makes the main container deliberately larger than the real body.</p></article>
      </section>
    </main>
    """
    root, selector = scoop.choose_article_root(BeautifulSoup(raw, "html.parser"), "The Globe and Mail")
    assert root is not None
    assert root.get("id") == "content-gate", selector


def test_ctv_media_pass_uses_embedded_story_images_not_page_cards() -> None:
    raw = """
    <html><body>
      <script id="fusion-metadata" type="application/javascript">
      Fusion.globalContent={
        "content_elements": [
          {"type":"text","content":"The first paragraph explains the program and provides enough reporting detail about the people involved and why the approach is being used."},
          {"type":"image","url":"https://www.ctvnews.ca/resizer/v2/INLINE.jpeg?auth=abc","width":1920,"height":1080,"subtitle":"Program participant","caption":"A participant speaks outside the store. (CTV News)"},
          {"type":"text","content":"The second paragraph adds comments from organizers and describes what they hope customers and security staff will experience."},
          {"type":"image","url":"https://www.ctvnews.ca/resizer/v2/HERO.jpeg?auth=xyz","width":1920,"height":1080,"subtitle":"Community ambassador","caption":"The community ambassador outside the store. (CTV News)"}
        ]
      };Fusion.arcSite="ctvnews";
      </script>
      <article><a href="/canada/article/unrelated"><img src="https://www.ctvnews.ca/resizer/v2/RECIRC.jpg?width=800" width="800" height="450" alt="Unrelated story"></a></article>
    </body></html>
    """
    story = {
        "source": "CTV News Canada",
        "url": "https://www.ctvnews.ca/canada/article/example/",
        "title": "Program aims to create a calmer store environment",
        "image": "https://www.ctvnews.ca/resizer/v2/HERO.jpeg?auth=xyz",
    }
    with patch.object(media, "fetch_html", return_value=(raw, story["url"])):
        found, method = media.process_story(story)
    urls = [block.get("url", "") for _, block in found if block.get("type") == "image"]
    assert method == "ctv:embedded-dom-media-images-v4"
    assert any("/INLINE.jpeg" in url for url in urls)
    assert not any("/HERO.jpeg" in url for url in urls)
    assert not any("/RECIRC.jpg" in url for url in urls)


def test_cbc_audio_does_not_prevent_photo_recovery() -> None:
    raw = """
    <main><div data-cy="storyWrapper">
      <p>The researcher described how historical work patterns shaped modern ideas about exhaustion and labour.</p>
      <figure><img src="https://i.cbc.ca/ais/researcher,1788290677516/full/max/0/default.jpg" width="1200" height="675" alt="A researcher at Western University"><figcaption>The researcher at Western University. (CBC)</figcaption></figure>
      <p>The interview also connected those patterns to the way modern workplaces measure time and productivity.</p>
    </div></main>
    """
    story = {
        "source": "CBC News London",
        "url": "https://www.cbc.ca/news/canada/london/example-9.1234567",
        "title": "Burnout is not new",
        "image": "",
    }
    audio = (
        "Listen to the interview",
        {"type": "media", "media_type": "audio", "url": "https://media.example.test/interview.mp3", "title": "Interview"},
    )
    with patch.object(media, "extract_cbc_media", return_value=[audio]), patch.object(media, "fetch_html", return_value=(raw, story["url"])):
        found, method = media.process_story(story)
    kinds = [block.get("type") for _, block in found]
    assert method == "cbc:jina-dom-media-images-v4"
    assert "media" in kinds
    assert "image" in kinds


def main() -> int:
    tests = [
        test_cbc_srcset_keeps_literal_asset_comma,
        test_cbc_default_jpg_is_not_treated_as_placeholder,
        test_cbc_story_wrapper_keeps_real_photos_and_drops_player_thumbnail,
        test_globe_prefers_content_gate_over_whole_main,
        test_ctv_media_pass_uses_embedded_story_images_not_page_cards,
        test_cbc_audio_does_not_prevent_photo_recovery,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
