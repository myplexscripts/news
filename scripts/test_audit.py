#!/usr/bin/env python3
from __future__ import annotations

from datetime import datetime, timezone

from audit_sources import audit_story, build_audit

NOW = datetime(2026, 8, 27, tzinfo=timezone.utc)


def base_story(**overrides):
    story = {
        "id": "story-1",
        "source": "CTV News",
        "title": "London council approves new project",
        "url": "https://www.ctvnews.ca/london/article/test/",
        "published": "2026-08-26T22:00:00+00:00",
        "content_status": "full",
        "content": " ".join(["This is a clean article sentence about London." for _ in range(35)]),
        "word_count": 280,
        "author": "Reporter Name",
        "image": "https://www.ctvnews.ca/image.jpg",
        "content_blocks": [
            {"type": "paragraph", "text": "This is the first paragraph with enough meaningful text to be useful."},
            {"type": "paragraph", "text": "This is the second paragraph with different meaningful reporting from London."},
            {"type": "paragraph", "text": "This is the third paragraph and it completes the clean sample article."},
        ],
        "quality": {"score": 82, "grade": "good", "method": "jsonld:ctv"},
        "extraction_profile": "ctv",
        "local_score": 80,
    }
    story.update(overrides)
    return story


def issue_codes(result):
    return {issue["code"] for issue in result["issues"]}


def run():
    clean_result = audit_story(base_story(), now=NOW)
    assert clean_result["audit_status"] == "pass", clean_result

    lfp = base_story(
        source="London Free Press",
        url="https://lfpress.com/news/local-news/test",
        quality={"score": 75, "grade": "good", "method": "dom:lfp:article"},
        content_blocks=[
            {"type": "paragraph", "text": "The real article begins with a complete paragraph about a London court case."},
            {"type": "heading", "text": "Read More"},
            {"type": "list", "items": ["Loved ones offer update on crash", "SEE IT: Video captures huge crash"]},
            {"type": "paragraph", "text": "The real article continues after the publisher recommendation module."},
        ],
    )
    assert "inline_related_content" in issue_codes(audit_story(lfp, now=NOW))

    failed = base_story(content_status="failed", scrape_error="timeout", word_count=0, content="")
    failed_result = audit_story(failed, now=NOW)
    assert failed_result["audit_status"] == "fail"
    assert "scrape_error" in issue_codes(failed_result)

    duplicate_text = "This duplicated paragraph is long enough to be meaningful and should only appear once in an article."
    duplicate = base_story(content_blocks=[
        {"type": "paragraph", "text": duplicate_text},
        {"type": "paragraph", "text": duplicate_text},
        {"type": "paragraph", "text": "A third unique paragraph keeps the story shape realistic for the audit test."},
    ])
    assert "duplicate_body" in issue_codes(audit_story(duplicate, now=NOW))

    mismatch = base_story(content_status="full", word_count=42)
    assert "status_mismatch" in issue_codes(audit_story(mismatch, now=NOW))

    payload = {
        "schema_version": 12,
        "stories": [base_story(), lfp],
        "source_health": [
            {"source": "CTV News", "status": "healthy", "profile": "ctv", "found_this_run": 10},
            {"source": "London Free Press", "status": "healthy", "profile": "postmedia", "found_this_run": 10},
        ],
    }
    report = build_audit(payload, sample_per_source=10)
    assert report["overview"]["audited_story_count"] == 2
    assert len(report["source_reports"]) == 2
    assert any(issue["code"] == "inline_related_content" for issue in report["issues"])

    print("Audit tests passed")


if __name__ == "__main__":
    run()
