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
          "image": {
            "@type": "ImageObject",
            "contentUrl": "https://cloudfront.example.test/hero-modern.jpg",
            "width": 1600,
            "height": 900
          },
          "articleBody": [
            {
              "type": "image",
              "imageUrl": "https://cloudfront.example.test/inline-modern.jpg",
              "width": 1200,
              "height": 800,
              "caption": "Inline CTV article photo"
            }
          ],
          "author": {
            "@type": "Person",
            "image": {
              "@type": "ImageObject",
              "contentUrl": "https://cloudfront.example.test/author-headshot.jpg"
            }
          }
        }
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
      "content_elements": [
        {"type":"gallery","content_elements":[
          {"type":"image","url":"https://cloudfront.example.test/one.jpg","width":1600,"height":900},
          {"type":"image","url":"https://cloudfront.example.test/two.jpg","width":900,"height":1600}
        ]}
      ]
    };
    </script></body></html>
    """


def test_modern_ctv_recovers_metadata_and_structured_images() -> None:
    recovered = photos.extract_ctv_photos(
        modern_html(),
        "https://www.ctvnews.ca/canada/article/example",
    )
    urls = [item["url"] for item in recovered]
    assert urls[0] == "https://cloudfront.example.test/hero-modern.jpg"
    assert "https://cloudfront.example.test/inline-modern.jpg" in urls
    assert "https://cloudfront.example.test/author-headshot.jpg" not in urls


def test_fusion_gallery_still_recovers_all_images() -> None:
    recovered = photos.extract_ctv_photos(
        legacy_gallery_html(),
        "https://www.ctvnews.ca/london/article/example",
    )
    assert [item["url"] for item in recovered] == [
        "https://cloudfront.example.test/one.jpg",
        "https://cloudfront.example.test/two.jpg",
    ]


def test_schema_two_rechecks_previously_checked_ctv_story() -> None:
    story = {
        "source": "CTV News Canada",
        "url": "https://www.ctvnews.ca/canada/article/example",
        "ctv_photo_schema": 1,
        "scraped_at": "2026-09-13T22:00:00+00:00",
        "ctv_photo_checked_for_scrape": "2026-09-13T22:00:00+00:00",
    }
    assert photos.CTV_PHOTO_SCHEMA == 2
    assert photos.story_needs_work(story)


def main() -> None:
    test_modern_ctv_recovers_metadata_and_structured_images()
    print("PASS test_modern_ctv_recovers_metadata_and_structured_images")
    test_fusion_gallery_still_recovers_all_images()
    print("PASS test_fusion_gallery_still_recovers_all_images")
    test_schema_two_rechecks_previously_checked_ctv_story()
    print("PASS test_schema_two_rechecks_previously_checked_ctv_story")


if __name__ == "__main__":
    main()
