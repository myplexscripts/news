from __future__ import annotations

from trim_article_tails import trim_payload


def dump(story: dict) -> str:
    parts: list[str] = []
    for block in story.get("content_blocks", []):
        text = str(block.get("text") or block.get("title") or block.get("label") or "")
        if text:
            parts.append(text)
        for item in block.get("items", []) if isinstance(block.get("items"), list) else []:
            parts.append(str(item.get("text") if isinstance(item, dict) else item))
    return " | ".join(parts)


def test_ctv_custom_link_footer_ends_article() -> None:
    story = {
        "id": "ctv-footer-tail",
        "source": "CTV News London",
        "title": "Knights captain hopes to bring another trophy home",
        "content_blocks": [
            {"type": "paragraph", "text": "The captain said last season was a dream come true after the club completed a memorable championship run."},
            {"type": "paragraph", "text": "He is hoping the next trophy he brings home for a meet and greet will be the Stanley Cup."},
            {"type": "quote", "text": "That's the one I really want, said Cowan. Looking forward to the challenge to get there and excited to get started."},
            {"type": "link", "label": "CTV NEWS Report an Error", "url": "https://www.ctvnews.ca/report-error"},
            {"type": "link", "label": "CTV NEWS Editorial standards & policies", "url": "https://www.ctvnews.ca/editorial"},
            {"type": "link", "label": "CTV NEWS Why you can trust CTV News", "url": "https://www.ctvnews.ca/trust"},
            {"type": "heading", "text": "This nearly $26M cottage in Muskoka has a two-storey boathouse and enough space for 26 people"},
            {"type": "heading", "text": "This Toronto home backing onto a ravine underwent a $6-million renovation. Take a look inside"},
            {"type": "heading", "text": "Toronto"},
            {"type": "heading", "text": "DVP closed due to flooding, thousands still without power after thunderstorms hit Toronto, GTA"},
            {"type": "heading", "text": "Vancouver"},
            {"type": "heading", "text": "Kelowna, B.C., mayor asks feds to shut consumption site after 3,400 police visits"},
        ],
    }
    payload = {"stories": [story]}

    assert trim_payload(payload) == 1
    rendered = dump(story)
    assert "Stanley Cup" in rendered
    assert "Report an Error" not in rendered
    assert "$26M cottage" not in rendered
    assert "DVP closed" not in rendered
    assert "Kelowna" not in rendered
    assert "publisher-footer-tail" in story.get("article_hygiene_flags", [])


def test_footer_phrase_before_real_prose_does_not_truncate() -> None:
    story = {
        "source": "Example Publisher",
        "content_blocks": [
            {"type": "paragraph", "text": "A report an editorial error link was discussed as part of the redesign."},
            {"type": "paragraph", "text": "The actual article then continues with enough reporting to make clear that this sentence belongs to the story itself."},
        ],
    }
    assert trim_payload({"stories": [story]}) == 0
    assert len(story["content_blocks"]) == 2


def test_globe_diversions_tail_is_removed() -> None:
    story = {
        "source": "The Globe and Mail",
        "content_blocks": [
            {"type": "paragraph", "text": "The federal government announced a new program on Thursday after months of negotiations with provinces and industry groups across the country."},
            {"type": "paragraph", "text": "Officials said the changes will begin this fall and that more implementation details will be released before the end of the month."},
            {"type": "heading", "text": "Diversions"},
            {"type": "list", "items": ["Sudoku", "Crossword", "Cryptic Crossword", "Word Flower"]},
            {"type": "heading", "text": "Latest videos"},
            {"type": "heading", "text": "Markets react to another rate decision"},
        ],
    }
    assert trim_payload({"stories": [story]}) == 1
    rendered = dump(story)
    assert "implementation details" in rendered
    assert "Diversions" not in rendered
    assert "Sudoku" not in rendered
    assert "Latest videos" not in rendered


def test_star_leading_dropdown_dump_is_skipped_until_article_prose() -> None:
    story = {
        "source": "Toronto Star",
        "content_status": "full",
        "content_blocks": [
            {"type": "paragraph", "text": "You have permission to edit this article."},
            {"type": "list", "items": ["22° | Thursday, Sept. 3", "Play Now! $20M Image 2: OLG Lottery"]},
            {"type": "paragraph", "text": "Site search Search"},
            {"type": "heading", "text": "Today's paper"},
            {"type": "list", "items": [
                "Top 100 restaurants", "If I Were Mayor", "The Signal", "Wildfires", "Tariffs",
                "Readers’ Choice Awards", "Shopping and Services", "Ontario", "Alberta", "Quebec",
            ]},
            {"type": "paragraph", "text": "The city approved the revised housing proposal after councillors debated the plan for more than three hours at Wednesday's meeting."},
            {"type": "paragraph", "text": "The final version adds new affordability requirements and directs staff to report back on the first phase early next year."},
        ],
    }
    assert trim_payload({"stories": [story]}) == 1
    rendered = dump(story)
    assert "housing proposal" in rendered
    assert "affordability requirements" in rendered
    assert "permission to edit" not in rendered
    assert "Site search" not in rendered
    assert "Top 100 restaurants" not in rendered
    assert "Ontario" not in rendered
    assert "publisher-chrome-leading" in story.get("article_hygiene_flags", [])


def test_real_article_bullet_list_is_preserved() -> None:
    story = {
        "source": "Example Publisher",
        "content_blocks": [
            {"type": "paragraph", "text": "The report recommends several changes that would be introduced over the next year if council approves the proposal."},
            {"type": "list", "items": [
                "Increase the annual housing target by 15 per cent.",
                "Create a dedicated office for permit reviews.",
                "Publish quarterly progress reports for council.",
                "Review the program again after twelve months.",
            ]},
            {"type": "paragraph", "text": "Staff will return to council next month with a detailed implementation schedule and updated cost estimates."},
        ],
    }
    assert trim_payload({"stories": [story]}) == 0
    assert "Increase the annual housing target" in dump(story)


def main() -> int:
    tests = [
        test_ctv_custom_link_footer_ends_article,
        test_footer_phrase_before_real_prose_does_not_truncate,
        test_globe_diversions_tail_is_removed,
        test_star_leading_dropdown_dump_is_skipped_until_article_prose,
        test_real_article_bullet_list_is_preserved,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
