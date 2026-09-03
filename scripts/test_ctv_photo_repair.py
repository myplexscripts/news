from __future__ import annotations

from unittest.mock import patch

import repair_ctv_photos as photos


def sample_html() -> str:
    return """
    <html>
      <head><meta property="og:title" content="Photo-heavy CTV London story"></head>
      <body>
        <script id="fusion-metadata" type="application/javascript">
        Fusion.globalContent={
          "headline": "Photo-heavy CTV London story",
          "content_elements": [
            {
              "type": "text",
              "content": "A short introduction explains why residents gathered at the scene and what viewers are seeing in the photographs below."
            },
            {
              "type": "gallery",
              "content_elements": [
                {
                  "type": "image",
                  "url": "https://cloudfront.example.test/photo-1.jpg",
                  "width": 1600,
                  "height": 1067,
                  "subtitle": "First scene photo",
                  "caption": "The first photograph from the scene."
                },
                {
                  "type": "image",
                  "url": "https://cloudfront.example.test/photo-2.jpg",
                  "width": 1200,
                  "height": 1800,
                  "subtitle": "Second scene photo",
                  "caption": "The second photograph is portrait orientation."
                },
                {
                  "type": "image",
                  "url": "https://cloudfront.example.test/photo-3.jpg",
                  "width": 1800,
                  "height": 1200,
                  "subtitle": "Third scene photo",
                  "caption": "The third photograph closes the gallery."
                }
              ]
            }
          ]
        };Fusion.arcSite="ctvnews";
        </script>
      </body>
    </html>
    """


def test_nested_ctv_gallery_keeps_every_photo_in_source_order() -> None:
    recovered = photos.extract_ctv_photos(
        sample_html(),
        "https://www.ctvnews.ca/london/article/photo-heavy-story/",
    )
    assert [item["url"] for item in recovered] == [
        "https://cloudfront.example.test/photo-1.jpg",
        "https://cloudfront.example.test/photo-2.jpg",
        "https://cloudfront.example.test/photo-3.jpg",
    ]
    assert recovered[1]["width"] == 1200
    assert recovered[1]["height"] == 1800
    assert recovered[1]["caption"] == "The second photograph is portrait orientation."


def test_ctv_gallery_merge_uses_first_photo_as_hero_and_keeps_rest_inline() -> None:
    story = {
        "id": "ctv-photo-story",
        "source": "CTV News London",
        "url": "https://www.ctvnews.ca/london/article/photo-heavy-story/",
        "title": "Photo-heavy CTV London story",
        "summary": "A short introduction explains the photo gallery.",
        "image": "https://cloudfront.example.test/photo-1.jpg",
        "content_status": "partial",
        "paragraphs": ["A short introduction explains the photo gallery and why the images matter."],
        "content_blocks": [
            {"type": "paragraph", "text": "A short introduction explains the photo gallery and why the images matter."},
            {"type": "image", "url": "https://cloudfront.example.test/photo-1.jpg"},
        ],
        "article_images": [],
        "quality": {"score": 70, "method": "embedded-json:ctv"},
        "scraped_at": "2026-09-03T14:00:00+00:00",
    }
    recovered = photos.extract_ctv_photos(sample_html(), story["url"])
    assert photos.merge_photos(story, recovered)

    inline = [block for block in story["content_blocks"] if block.get("type") == "image"]
    assert [block["url"] for block in inline] == [
        "https://cloudfront.example.test/photo-1.jpg",
        "https://cloudfront.example.test/photo-2.jpg",
        "https://cloudfront.example.test/photo-3.jpg",
    ]
    assert [item["url"] for item in story["article_images"]] == [
        "https://cloudfront.example.test/photo-2.jpg",
        "https://cloudfront.example.test/photo-3.jpg",
    ]
    assert story["ctv_photo_count"] == 3


def test_ctv_photo_repair_fetches_publisher_page_state() -> None:
    story = {
        "source": "CTV News London",
        "url": "https://www.ctvnews.ca/london/article/photo-heavy-story/",
    }
    with patch(
        "repair_ctv_photos.fetch_news.fetch_html",
        return_value=(sample_html(), story["url"]),
    ):
        recovered, final_url, error = photos.process_story(story)

    assert not error
    assert final_url == story["url"]
    assert len(recovered) == 3


def main() -> None:
    test_nested_ctv_gallery_keeps_every_photo_in_source_order()
    print("PASS test_nested_ctv_gallery_keeps_every_photo_in_source_order")
    test_ctv_gallery_merge_uses_first_photo_as_hero_and_keeps_rest_inline()
    print("PASS test_ctv_gallery_merge_uses_first_photo_as_hero_and_keeps_rest_inline")
    test_ctv_photo_repair_fetches_publisher_page_state()
    print("PASS test_ctv_photo_repair_fetches_publisher_page_state")


if __name__ == "__main__":
    main()
