from __future__ import annotations

from refine_article_formatting import extract_dom_blocks, markdown_inline_html, parse_cbc_markdown


def test_dom_preserves_strong_emphasis_and_links() -> None:
    raw = """
    <article>
      <div class="article-body">
        <p>This is <strong>important</strong>, <em>carefully worded</em> reporting with a <a href="/local/context">source link</a>.</p>
        <p><strong>Nav Nanwa: What made you decide to move to Canada?</strong></p>
        <p>Seth Guikema said the research environment was a major reason for the move.</p>
      </div>
    </article>
    """
    blocks = extract_dom_blocks(raw, "https://example.test/story", "Example story")
    first = blocks[0]
    assert first["type"] == "paragraph"
    assert "<strong>important</strong>" in first["html"]
    assert "<em>carefully worded</em>" in first["html"]
    assert 'href="https://example.test/local/context"' in first["html"]
    assert blocks[1]["type"] == "paragraph"
    assert "<strong>Nav Nanwa:" in blocks[1]["html"]
    assert not any(block.get("type") == "heading" and "Nav Nanwa" in block.get("text", "") for block in blocks)


def test_dom_strips_unsafe_inline_markup() -> None:
    raw = """
    <article>
      <p>A paragraph with <script>alert('x')</script><span style="font-weight: 700">safe bold text</span> and <a href="javascript:alert(1)">unsafe link text</a>.</p>
      <p>A second complete paragraph ensures the article root has enough real prose to extract correctly, while also giving the test article the same approximate body density that a normal publisher story would contain.</p>
      <p>The article then continues with another ordinary sentence so the extractor has no reason to reject the body as a tiny fragment or navigation shell.</p>
    </article>
    """
    blocks = extract_dom_blocks(raw, "https://example.test/story", "Example story")
    rendered = blocks[0]["html"]
    assert "<script" not in rendered
    assert "javascript:" not in rendered
    assert "<strong>safe bold text</strong>" in rendered
    assert "unsafe link text" in rendered


def test_dom_list_items_keep_inline_formatting() -> None:
    raw = """
    <article>
      <p>Officials outlined the following changes for residents in the neighbourhood this week, with work expected to continue through several overnight construction windows.</p>
      <ul>
        <li><strong>Tuesday:</strong> overnight road closure</li>
        <li><em>Wednesday:</em> one lane remains open</li>
      </ul>
      <p>The city said regular traffic is expected to resume by Thursday morning after the work is complete, although crews may return for finishing work if weather causes delays.</p>
    </article>
    """
    blocks = extract_dom_blocks(raw, "https://example.test/story", "Road work")
    listing = next(block for block in blocks if block.get("type") == "list")
    assert isinstance(listing["items"][0], dict)
    assert "<strong>Tuesday:</strong>" in listing["items"][0]["html"]
    assert "<em>Wednesday:</em>" in listing["items"][1]["html"]


def test_markdown_inline_preserves_emphasis_and_link() -> None:
    rendered = markdown_inline_html(
        "This *interview* includes **important context** and a [source](https://example.test/source).",
        "https://example.test/",
    )
    assert "<em>interview</em>" in rendered
    assert "<strong>important context</strong>" in rendered
    assert 'href="https://example.test/source"' in rendered


def test_cbc_strong_question_stays_paragraph() -> None:
    raw = """
Markdown Content:

This interview has been *edited for length and clarity*.

**Nav Nanwa: What made you decide to leave the U.S. and come to Canada?**

Seth Guikema: Well, Western offers an incredibly strong environment for doing this sort of research and the opportunity was attractive.

**NV: How significant is it for Canada to make this kind of investment?**

SG: It is a large and powerful investment in research and in furthering the Canadian economy.
"""
    blocks = parse_cbc_markdown(raw, "Western recruits researcher")
    questions = [block for block in blocks if "Nav Nanwa" in block.get("text", "") or block.get("text", "").startswith("NV:")]
    assert questions
    assert all(block["type"] == "paragraph" for block in questions)
    assert all("<strong>" in block.get("html", "") for block in questions)
    intro = blocks[0]
    assert "<em>edited for length and clarity</em>" in intro.get("html", "")


def main() -> int:
    tests = [
        test_dom_preserves_strong_emphasis_and_links,
        test_dom_strips_unsafe_inline_markup,
        test_dom_list_items_keep_inline_formatting,
        test_markdown_inline_preserves_emphasis_and_link,
        test_cbc_strong_question_stays_paragraph,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
