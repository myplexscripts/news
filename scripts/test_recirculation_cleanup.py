from __future__ import annotations

from cleanup_article_recirculation import clean_payload, extract_contextual_images


def dump_blocks(story: dict) -> str:
    return " | ".join(
        str(block.get("text") or block.get("url") or "")
        for block in story.get("content_blocks", [])
    )


def test_promoted_story_list_is_removed() -> None:
    payload = {
        "stories": [
            {
                "id": "main",
                "source": "London Free Press",
                "title": "Railway City Brewing looks back and ahead",
                "content_blocks": [
                    {"type": "paragraph", "text": "With the brewery back in local hands, several old favourites could return for a short while."},
                    {"type": "heading", "level": 2, "text": "Read More"},
                    {
                        "type": "list",
                        "ordered": True,
                        "items": [
                            "Brews News: A sour suite for summer's end",
                            "Brews News: Anderson marks 10 years with anniversary bash",
                        ],
                    },
                    {"type": "paragraph", "text": "But not everything can be backward-looking."},
                ],
            },
            {"id": "a", "title": "Brews News: A sour suite for summer's end"},
            {"id": "b", "title": "Brews News: Anderson marks 10 years with anniversary bash"},
        ]
    }
    assert clean_payload(payload) == 1
    dumped = dump_blocks(payload["stories"][0])
    assert "Read More" not in dumped
    assert "sour suite" not in dumped
    assert "backward-looking" in dumped


def test_unlabelled_promoted_story_list_is_removed() -> None:
    payload = {
        "stories": [{
            "id": "main",
            "source": "London Free Press",
            "title": "Railway City Brewing looks back and ahead",
            "content_blocks": [
                {"type": "paragraph", "text": "Witty Traveller, a Belgian wheat beer, is a contender."},
                {
                    "type": "list",
                    "ordered": True,
                    "items": [
                        {"text": "Brews News: A sour suite for summer's end", "html": "<strong>Brews News:</strong> A sour suite for summer's end"},
                        {"text": "Brews News: Anderson marks 10 years with anniversary bash", "html": "<strong>Brews News:</strong> Anderson marks 10 years with anniversary bash"},
                    ],
                },
                {"type": "paragraph", "text": "But not everything can be backward-looking."},
            ],
        }]
    }
    assert clean_payload(payload) == 1
    assert not any(block.get("type") == "list" for block in payload["stories"][0]["content_blocks"])
    assert "backward-looking" in dump_blocks(payload["stories"][0])


def test_labelled_publisher_cards_are_removed_without_feed_matches() -> None:
    payload = {
        "stories": [{
            "id": "main",
            "source": "CTV News",
            "title": "Main article",
            "content_blocks": [
                {"type": "paragraph", "text": "The main article continues with a complete sentence before the inserted module."},
                {"type": "heading", "level": 2, "text": "Recommended for you"},
                {"type": "paragraph", "text": "London council approves major downtown housing proposal"},
                {"type": "image", "url": "https://example.test/promo.jpg", "alt": ""},
                {"type": "paragraph", "text": "Police identify driver in Highway 401 collision near London"},
                {"type": "paragraph", "text": "Officials said the project will return to council next month for a final vote."},
            ],
        }]
    }
    assert clean_payload(payload) == 1
    dumped = dump_blocks(payload["stories"][0])
    assert "Recommended for you" not in dumped
    assert "downtown housing proposal" not in dumped
    assert "Highway 401 collision" not in dumped
    assert "return to council next month" in dumped


def test_newsletter_module_is_removed() -> None:
    payload = {
        "stories": [{
            "id": "main",
            "source": "Global News London",
            "title": "Main article",
            "content_blocks": [
                {"type": "paragraph", "text": "Residents described the meeting as productive and said more discussion is expected."},
                {"type": "heading", "level": 2, "text": "Newsletter"},
                {"type": "paragraph", "text": "Get the day's top stories delivered to your inbox so you never miss the day."},
                {"type": "paragraph", "text": "The committee will meet again on Tuesday to consider the revised proposal."},
            ],
        }]
    }
    assert clean_payload(payload) == 1
    dumped = dump_blocks(payload["stories"][0])
    assert "Newsletter" not in dumped
    assert "delivered to your inbox" not in dumped
    assert "meet again on Tuesday" in dumped


def test_globe_terminal_chrome_is_removed() -> None:
    payload = {
        "stories": [{
            "id": "globe",
            "source": "The Globe and Mail",
            "title": "Main article",
            "content_blocks": [
                {"type": "paragraph", "text": "The final real paragraph of the article ends here after explaining the issue in enough detail."},
                {"type": "paragraph", "text": "Report an editorial error", "html": "<a href='https://example.test/error'>Report an editorial error</a>"},
                {"type": "paragraph", "text": "Report a technical issue"},
                {"type": "heading", "level": 2, "text": "Follow related authors and topics"},
                {"type": "paragraph", "text": "Authors and topics you follow will be added to your personal news feed in Following."},
                {"type": "heading", "level": 2, "text": "Interact with The Globe"},
            ],
        }]
    }
    assert clean_payload(payload) == 1
    blocks = payload["stories"][0]["content_blocks"]
    assert len(blocks) == 1
    assert "final real paragraph" in blocks[0]["text"]


def test_single_linked_globe_related_story_is_removed_mid_article() -> None:
    headline = "B.C. ends provincial state of emergency as wildfires continue to burn"
    payload = {
        "stories": [{
            "id": "globe-inline",
            "source": "The Globe and Mail",
            "title": "Main wildfire article",
            "content_blocks": [
                {"type": "paragraph", "text": "The first real paragraph explains the wildfire situation in British Columbia."},
                {"type": "paragraph", "text": headline, "html": f"<a href='https://example.test/other'>{headline}</a>"},
                {"type": "paragraph", "text": "The article resumes here with another complete sentence from the original report."},
            ],
        }]
    }
    assert clean_payload(payload) == 1
    dumped = dump_blocks(payload["stories"][0])
    assert headline not in dumped
    assert "article resumes here" in dumped


def test_toronto_star_trending_rail_is_removed() -> None:
    payload = {
        "stories": [{
            "id": "star",
            "source": "Toronto Star",
            "title": "Main article",
            "content_blocks": [
                {"type": "paragraph", "text": "The Canadian Press reported the main story from Toronto in a complete paragraph."},
                {"type": "heading", "level": 3, "text": "Trending"},
                {"type": "image", "url": "https://example.test/lake.jpg"},
                {"type": "heading", "level": 3, "text": "A sign for the times: Doug Ford unveils Lake Ontario sign", "html": "<a href='https://example.test/other'>A sign for the times</a>"},
            ],
        }]
    }
    assert clean_payload(payload) == 1
    assert len(payload["stories"][0]["content_blocks"]) == 1


def test_unlabelled_linked_story_card_run_is_removed_mid_article() -> None:
    payload = {
        "stories": [{
            "id": "post",
            "source": "National Post",
            "title": "Main article",
            "content_blocks": [
                {"type": "paragraph", "text": "The first half of the article explains the issue in enough detail for readers."},
                {"type": "heading", "level": 3, "text": "First unrelated linked headline here", "html": "<a href='https://example.test/a'>First unrelated linked headline here</a>"},
                {"type": "image", "url": "https://example.test/a.jpg"},
                {"type": "heading", "level": 3, "text": "Second unrelated linked headline here", "html": "<a href='https://example.test/b'>Second unrelated linked headline here</a>"},
                {"type": "image", "url": "https://example.test/b.jpg"},
                {"type": "paragraph", "text": "The article resumes here with another complete sentence after the inserted rail."},
            ],
        }]
    }
    assert clean_payload(payload) == 1
    dumped = dump_blocks(payload["stories"][0])
    assert "First unrelated linked headline" not in dumped
    assert "Second unrelated linked headline" not in dumped
    assert "article resumes here" in dumped


def test_real_numbered_list_is_preserved() -> None:
    payload = {
        "stories": [{
            "id": "main",
            "source": "London Free Press",
            "title": "Three road projects begin next week",
            "content_blocks": [{
                "type": "list",
                "ordered": True,
                "items": [
                    {"text": "Commissioners Road will close overnight on Tuesday.", "html": "Commissioners Road will close overnight on <strong>Tuesday</strong>."},
                    {"text": "Richmond Street will have one lane closed on Wednesday.", "html": "Richmond Street will have one lane closed on Wednesday."},
                    {"text": "Oxford Street work begins Thursday morning.", "html": "Oxford Street work begins Thursday morning."},
                ],
            }],
        }]
    }
    assert clean_payload(payload) == 0
    assert payload["stories"][0]["content_blocks"][0]["type"] == "list"


def test_global_ad_marker_does_not_delete_resuming_article() -> None:
    payload = {
        "stories": [{
            "id": "global-ad",
            "source": "Global News Canada",
            "title": "Argos game report",
            "content_blocks": [
                {"type": "paragraph", "text": "The Argos missed the conversion after the touchdown and remained one point behind their opponent."},
                {"type": "paragraph", "text": "Story continues below advertisement"},
                {"type": "image", "url": "https://example.test/ad-placeholder.jpg", "alt": "Advertisement"},
                {"type": "paragraph", "text": "Then later, after a third Toronto touchdown, the kick was blocked and returned for two points."},
            ],
        }]
    }
    assert clean_payload(payload) == 1
    dumped = dump_blocks(payload["stories"][0])
    assert "Story continues below advertisement" not in dumped
    assert "ad-placeholder" not in dumped
    assert "third Toronto touchdown" in dumped


def test_global_related_videos_module_is_removed_but_story_resumes() -> None:
    payload = {
        "stories": [{
            "id": "global-video",
            "source": "Global News Canada",
            "title": "Argos game report",
            "content_blocks": [
                {"type": "paragraph", "text": "The Roughriders scored twice in the second half to take control of the game."},
                {"type": "heading", "level": 2, "text": "Related Videos"},
                {"type": "image", "url": "https://example.test/saskatoon.jpg", "alt": "Global News Saskatoon"},
                {"type": "paragraph", "text": "12:07 Global News at 5 Saskatoon: March 4"},
                {"type": "paragraph", "text": "Argos head coach Mike Miller says it would be unfair to blame the loss on his special teams unit."},
            ],
        }]
    }
    assert clean_payload(payload) == 1
    dumped = dump_blocks(payload["stories"][0])
    assert "Related Videos" not in dumped
    assert "saskatoon.jpg" not in dumped
    assert "12:07 Global News" not in dumped
    assert "Mike Miller" in dumped


def test_global_daily_news_promo_is_removed_mid_story() -> None:
    payload = {
        "stories": [{
            "id": "global-newsletter",
            "source": "Global News Canada",
            "title": "Lake Ontario story",
            "content_blocks": [
                {"type": "paragraph", "text": "The professor said map names can change when governments adopt new official terminology."},
                {"type": "image", "url": "https://example.test/national.jpg", "alt": "National"},
                {"type": "heading", "level": 2, "text": "Get daily National news"},
                {"type": "paragraph", "text": "Get daily Canada news delivered to your inbox so you'll never miss the day's top stories."},
                {"type": "paragraph", "text": "There is a long history of using place naming and renaming as an assertion of power, he said."},
            ],
        }]
    }
    assert clean_payload(payload) == 1
    dumped = dump_blocks(payload["stories"][0])
    assert "Get daily National news" not in dumped
    assert "delivered to your inbox" not in dumped
    assert "long history of using place naming" in dumped


def test_national_post_paywall_becomes_partial_and_stops_at_wall() -> None:
    story = {
        "id": "post-paywall",
        "source": "National Post",
        "title": "Trump hits New York governor",
        "content_status": "full",
        "content_blocks": [
            {"type": "paragraph", "text": "Trump criticized the governor while discussing the naming dispute and Canada's economic position."},
            {"type": "heading", "level": 2, "text": "THIS CONTENT IS RESERVED FOR SUBSCRIBERS"},
            {"type": "paragraph", "text": "Enjoy the latest local, national and international news."},
            {"type": "list", "ordered": False, "items": [
                "Unlimited online access to National Post.",
                "Daily puzzles including the New York Times Crossword.",
                "Support local journalism.",
            ]},
            {"type": "heading", "level": 2, "text": "SUBSCRIBE FOR MORE ARTICLES"},
            {"type": "heading", "level": 2, "text": "Keep reading"},
            {"type": "heading", "level": 2, "text": "More from London"},
        ],
    }
    payload = {"stories": [story]}
    assert clean_payload(payload) == 1
    dumped = dump_blocks(story)
    assert "RESERVED FOR SUBSCRIBERS" not in dumped
    assert "Unlimited online access" not in dumped
    assert "More from London" not in dumped
    assert story["content_status"] == "partial"
    assert story["content_truncated_reason"] == "publisher-paywall"


def test_contextual_image_recovery_keeps_editorial_images_only() -> None:
    first = (
        "Google has jumped into the debate over Lake Ontario's name following a government order, "
        "saying the name shown on Maps depends on where a person is located."
    )
    second = (
        "The company said it updates Google Maps to reflect name changes in official government sources, "
        "including the geographic names information system."
    )
    third = (
        "As a result, people using Maps in Canada will continue to see Lake Ontario while users elsewhere "
        "may see a different label depending on local policy."
    )
    raw = f"""
    <html><body>
      <main>
        <article class="article-body">
          <p>{first}</p>
          <figure class="story-photo"><img src="https://img.test/editorial-1.jpg" alt="People look at Lake Ontario"><figcaption>A view of Lake Ontario.</figcaption></figure>
          <p>{second}</p>
          <section class="related-videos">
            <img src="https://img.test/related-saskatoon.jpg" alt="Global News Saskatoon">
            <a href="/canada/article/other-story">Another news story</a>
          </section>
          <div class="newsletter-promo">
            <img src="https://img.test/national-newsletter.jpg" alt="National">
            <h2>Get daily National news</h2>
          </div>
          <figure><img src="https://img.test/editorial-2.jpg" alt="A map showing the lake"><figcaption>The map uses the Canadian name.</figcaption></figure>
          <p>{third}</p>
        </article>
      </main>
    </body></html>
    """
    story = {
        "title": "Lake Ontario story",
        "image": "https://img.test/hero.jpg",
        "url": "https://example.test/canada/article/lake",
    }
    blocks = [
        {"type": "paragraph", "text": first},
        {"type": "paragraph", "text": second},
        {"type": "paragraph", "text": third},
    ]
    recovered = extract_contextual_images(raw, story["url"], story, blocks)
    urls = [block["url"] for _, block in recovered]
    assert "https://img.test/editorial-1.jpg" in urls
    assert "https://img.test/editorial-2.jpg" in urls
    assert "https://img.test/related-saskatoon.jpg" not in urls
    assert "https://img.test/national-newsletter.jpg" not in urls


def test_contextual_image_recovery_rejects_linked_story_card_image() -> None:
    first = "The first paragraph contains enough reporting text to anchor the correct article body for image recovery."
    second = "The second paragraph continues the report and makes the editorial article container unambiguous."
    raw = f"""
    <article>
      <p>{first}</p>
      <a class="story-card" href="/canada/article/different-story">
        <img src="https://img.test/other-story.jpg" alt="Other story headline">
      </a>
      <figure><img src="https://img.test/real.jpg" alt="Real article photograph"></figure>
      <p>{second}</p>
    </article>
    """
    story = {"title": "Main", "image": "", "url": "https://example.test/canada/article/main"}
    blocks = [{"type": "paragraph", "text": first}, {"type": "paragraph", "text": second}]
    recovered = extract_contextual_images(raw, story["url"], story, blocks)
    urls = [block["url"] for _, block in recovered]
    assert "https://img.test/real.jpg" in urls
    assert "https://img.test/other-story.jpg" not in urls


def main() -> int:
    test_promoted_story_list_is_removed()
    test_unlabelled_promoted_story_list_is_removed()
    test_labelled_publisher_cards_are_removed_without_feed_matches()
    test_newsletter_module_is_removed()
    test_globe_terminal_chrome_is_removed()
    test_single_linked_globe_related_story_is_removed_mid_article()
    test_toronto_star_trending_rail_is_removed()
    test_unlabelled_linked_story_card_run_is_removed_mid_article()
    test_real_numbered_list_is_preserved()
    test_global_ad_marker_does_not_delete_resuming_article()
    test_global_related_videos_module_is_removed_but_story_resumes()
    test_global_daily_news_promo_is_removed_mid_story()
    test_national_post_paywall_becomes_partial_and_stops_at_wall()
    test_contextual_image_recovery_keeps_editorial_images_only()
    test_contextual_image_recovery_rejects_linked_story_card_image()
    print("PASS contextual article cleanup regressions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
