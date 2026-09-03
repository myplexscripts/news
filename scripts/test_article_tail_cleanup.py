from __future__ import annotations

from trim_article_tails import trim_payload


def dump(story: dict) -> str:
    return " | ".join(
        str(block.get("text") or block.get("title") or block.get("label") or "")
        for block in story.get("content_blocks", [])
    )


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


def main() -> int:
    tests = [
        test_ctv_custom_link_footer_ends_article,
        test_footer_phrase_before_real_prose_does_not_truncate,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
