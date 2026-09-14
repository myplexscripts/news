from __future__ import annotations

import repair_ctv_photos_v2 as photos


def modern_html() -> str:
    return """
    <html>
      <head>
        <meta property="og:image" content="https://cloudfront.example.test/hero-modern.jpg">
        <meta property="og:image:width" content="1600">
        <meta property="og:image:height" content="900">
        <script type="application/ld+json">
        {
          "@type": "NewsArticle",
          "mainEntityOfPage": "https://www.ctvnews.ca/canada/article/example",
          "image": {
            "@type": "ImageObject",
            "contentUrl": "https://cloudfront.example.test/hero-modern.jpg",
            "width": 1600,
            "height": 900
          },
          "author": {
            "@type": "Person",
            "image": {
              "@type": "ImageObject",
              "contentUrl": "https://cloudfront.example.test/author-headshot.jpg"
            }
          }
        }
        </script>
        <script>
        window.__STATE__ = {
          "article": {
            "headline": "Current CTV article",
            "canonical_url": "/canada/article/example",
            "content_elements": [
              {
                "type": "image",
                "imageUrl": "https://cloudfront.example.test/inline-modern.jpg",
                "width": 1200,
                "height": 800,
                "caption": "Inline CTV article photo"
              }
            ]
          },
          "related": [
            {
              "headline": "Another story",
              "canonical_url": "/canada/article/another-story",
              "content_elements": [
                {
                  "type": "image",
                  "imageUrl": "https://cloudfront.example.test/unrelated-related.jpg",
                  "width": 1200,
                  "height": 800
                }
              ]
            }
          ]
        };
        </script>
      </head>
      <body>
        <main><article><p>Article body.</p></article></main>
      </body>
    </html>
    """


def legacy_gallery_html() -> str:
    return """
    <html><body><script>
    Fusion.globalContent={
      "headline": "Legacy photo gallery",
      "canonical_url": "/london/article/example",
      "content_elements": [
        {"type":"gallery","content_elements":[
          {"type":"image","url":"https://cloudfront.example.test/one.jpg","width":1600,"height":900},
          {"type":"image","url":"https://cloudfront.example.test/two.jpg","width":900,"height":1600}
        ]}
      ]
    };
    </script></body></html>
    """


def test_modern_ctv_recovers_only_current_article_images() -> None:
    recovered = photos.extract_ctv_photos(
        modern_html(),
        "https://www.ctvnews.ca/canada/article/example",
    )
    urls = [item["url"] for item in recovered]
    assert urls == [
        "https://cloudfront.example.test/hero-modern.jpg",
        "https://cloudfront.example.test/inline-modern.jpg",
    ]
    assert "https://cloudfront.example.test/author-headshot.jpg" not in urls
    assert "https://cloudfront.example.test/unrelated-related.jpg" not in urls


def test_fusion_gallery_still_recovers_all_images() -> None:
    recovered = photos.extract_ctv_photos(
        legacy_gallery_html(),
        "https://www.ctvnews.ca/london/article/example",
    )
    assert [item["url"] for item in recovered] == [
        "https://cloudfront.example.test/one.jpg",
        "https://cloudfront.example.test/two.jpg",
    ]


def test_schema_three_rechecks_polluted_schema_two_story() -> None:
    story = {
        "source": "CTV News Canada",
        "url": "https://www.ctvnews.ca/canada/article/example",
        "ctv_photo_schema": 2,
        "scraped_at": "2026-09-13T22:00:00+00:00",
        "ctv_photo_checked_for_scrape": "2026-09-13T22:00:00+00:00",
    }
    assert photos.CTV_PHOTO_SCHEMA == 3
    assert photos.story_needs_work(story)


def test_schema_two_cleanup_removes_polluted_inline_images_but_keeps_text() -> None:
    story = {
        "ctv_photo_schema": 2,
        "article_images": [{"url": "https://cloudfront.example.test/junk.jpg"}],
        "content_blocks": [
            {"type": "paragraph", "text": "Keep this article paragraph."},
            {"type": "image", "url": "https://cloudfront.example.test/junk.jpg"},
        ],
        "ctv_photo_count": 40,
    }
    photos.reset_polluted_v2_media(story)
    assert story["content_blocks"] == [{"type": "paragraph", "text": "Keep this article paragraph."}]
    assert story["article_images"] == []
    assert story["ctv_photo_count"] == 0


def main() -> None:
    test_modern_ctv_recovers_only_current_article_images()
    print("PASS test_modern_ctv_recovers_only_current_article_images")
    test_fusion_gallery_still_recovers_all_images()
    print("PASS test_fusion_gallery_still_recovers_all_images")
    test_schema_three_rechecks_polluted_schema_two_story()
    print("PASS test_schema_three_rechecks_polluted_schema_two_story")
    test_schema_two_cleanup_removes_polluted_inline_images_but_keeps_text()
    print("PASS test_schema_two_cleanup_removes_polluted_inline_images_but_keeps_text")


if __name__ == "__main__":
    main()
