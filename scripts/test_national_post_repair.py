from __future__ import annotations

from repair_national_post_articles import article_path_ok, candidate_details, choose_candidate, should_replace


def paragraph(text: str) -> dict[str, str]:
    return {"type": "paragraph", "text": text}


def repeated_sentence(label: str, count: int) -> str:
    return " ".join([f"{label} contains enough ordinary article prose to represent a complete sentence."] * count)


def main() -> int:
    assert article_path_ok("https://nationalpost.com/news/canada/example-story")
    assert article_path_ok("https://nationalpost.com/news/politics/example-story")
    assert not article_path_ok("https://nationalpost.com/category/news/canada/")
    assert not article_path_ok("https://nationalpost.com/news/canada/")
    assert not article_path_ok("https://example.com/news/canada/example-story")

    short = candidate_details(
        "dom:postmedia:article",
        [
            paragraph(repeated_sentence("Lead", 2)),
            paragraph(repeated_sentence("Second", 2)),
        ],
    )
    long = candidate_details(
        "trafilatura:postmedia-repair",
        [
            paragraph(repeated_sentence(f"Paragraph {index}", 2))
            for index in range(8)
        ],
    )
    assert short is not None
    assert long is not None
    assert choose_candidate([short, long])["method"] == "trafilatura:postmedia-repair"

    existing = {
        "word_count": short["word_count"],
        "paragraphs": short["paragraphs"],
        "content": short["text"],
    }
    assert should_replace(existing, long)

    healthy = {
        "word_count": long["word_count"],
        "paragraphs": long["paragraphs"],
        "content": long["text"],
    }
    assert not should_replace(healthy, short)

    print("National Post repair contracts passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
