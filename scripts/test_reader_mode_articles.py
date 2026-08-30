from __future__ import annotations

from reader_mode_articles import (
    article_format_state,
    choose_reader_result,
    html_to_blocks,
    normalize_ctv_attribution,
    obvious_chrome_count,
    reader_candidate,
    text_from_blocks,
    trafilatura_candidate,
)


def run() -> None:
    london = {
        "source": "CTV News Canada",
        "scope": "canada",
        "url": "https://www.ctvnews.ca/london/article/a-local-story/",
    }
    assert normalize_ctv_attribution(london) == "reassign"
    assert london["source"] == "CTV News"
    assert london["scope"] == "local"

    canada = {
        "source": "CTV News",
        "scope": "local",
        "url": "https://www.ctvnews.ca/canada/article/a-national-story/",
    }
    assert normalize_ctv_attribution(canada) == "reassign"
    assert canada["source"] == "CTV News Canada"
    assert canada["scope"] == "canada"

    unrelated = {
        "source": "CTV News Canada",
        "scope": "canada",
        "url": "https://www.ctvnews.ca/world/article/not-a-canada-story/",
    }
    assert normalize_ctv_attribution(unrelated) == "drop"

    fragment = """
    <article>
      <h2>What changed</h2>
      <p>The first paragraph contains <strong>important context</strong> and a
         <a href="/background">background link</a> for readers.</p>
      <ul>
        <li>First confirmed fact</li>
        <li>Second confirmed fact</li>
      </ul>
      <blockquote>A direct quote from the source appears here.</blockquote>
      <p>The final paragraph contains enough reporting to make this a real article.</p>
    </article>
    """
    blocks = html_to_blocks(fragment, "https://example.com/story", "Different title", "")
    kinds = [block["type"] for block in blocks]
    assert "heading" in kinds
    assert "list" in kinds
    assert "quote" in kinds
    assert any("<strong>" in block.get("html", "") for block in blocks)
    assert any('href="https://example.com/background"' in block.get("html", "") for block in blocks)
    assert article_format_state(blocks) == "structured"

    page = """
    <!doctype html><html><body>
      <header><nav><a href="/">Home</a><a href="/sports">Sports</a></nav></header>
      <main>
        <article class="story-content">
          <h1>City approves major transit project</h1>
          <p>City council approved the transit project Tuesday after a long public debate that lasted several hours.</p>
          <h2>What happens next</h2>
          <p>Construction is expected to begin next spring, with the first phase scheduled to open the following year.</p>
          <p>Officials said <strong>service will continue</strong> during construction and published a
             <a href="/plan">detailed construction plan</a>.</p>
          <ul><li>Phase one begins downtown.</li><li>Phase two extends east.</li></ul>
          <p>Residents will receive another update before work begins, according to the city.</p>
        </article>
        <aside class="advertisement"><p>Advertisement</p><a href="/ad">Buy this product</a></aside>
        <section class="related-stories"><h2>Related Stories</h2>
          <a href="/other-1">Another city story makes headlines today</a>
          <a href="/other-2">A second unrelated headline appears here</a>
        </section>
      </main>
      <footer>Subscribe to our newsletter</footer>
    </body></html>
    """
    story = {
        "title": "City approves major transit project",
        "word_count": 90,
        "content_status": "partial",
    }
    read_blocks, read_method = reader_candidate(page, "https://example.com/news/transit", story["title"], "")
    traf_blocks, traf_method = trafilatura_candidate(page, "https://example.com/news/transit", story["title"], "")
    selected, method, metrics = choose_reader_result(story, [(read_blocks, read_method), (traf_blocks, traf_method)])
    assert selected, (read_blocks, traf_blocks)
    assert method in {"readability-lxml", "trafilatura-html"}
    assert metrics["words"] >= 55
    assert obvious_chrome_count(selected) == 0
    text = text_from_blocks(selected)[1].lower()
    assert "city council approved" in text
    assert "advertisement" not in text
    assert "related stories" not in text
    assert "another city story makes headlines" not in text

    print("Reader-mode article tests passed")


if __name__ == "__main__":
    run()
