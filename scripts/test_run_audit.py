from __future__ import annotations

from datetime import datetime, timezone

import audit_sources
import run_audit

NOW = datetime(2026, 8, 27, tzinfo=timezone.utc)


def story(identifier: str, source: str, status: str, words: int) -> dict:
    return {
        "id": identifier,
        "cluster_id": "cluster-case",
        "cluster_source_count": 2,
        "cluster_sources": ["CTV News", "London Police Service"],
        "source": source,
        "title": "Child sexual abuse material investigation update",
        "url": "https://example.com/story",
        "published": "2026-08-26T20:00:00+00:00",
        "content_status": status,
        "content": "A London Police investigation update." if words else "",
        "word_count": words,
        "author": "Reporter" if source == "CTV News" else "London Police Service",
        "image": "https://example.com/image.jpg",
        "content_blocks": [],
        "quality": {"score": 80, "grade": "good", "method": "fixture"},
        "extraction_profile": "fixture",
        "local_score": 90,
    }


def main() -> None:
    brief = story("ctv", "CTV News", "summary", 0)
    full = story("lps", "London Police Service", "full", 180)
    payload = {"stories": [brief, full]}

    original = audit_sources.audit_story
    try:
        run_audit.install_cluster_aware_audit(payload)
        result = audit_sources.audit_story(brief, now=NOW)
    finally:
        audit_sources.audit_story = original

    codes = {issue["code"] for issue in result["issues"]}
    assert "short_body" not in codes
    assert "cluster_covered_summary" in codes
    assert result["warning_count"] == 0
    assert result["audit_status"] == "pass"

    isolated = dict(brief)
    isolated["cluster_id"] = "cluster-isolated"
    original = audit_sources.audit_story
    try:
        run_audit.install_cluster_aware_audit({"stories": [isolated]})
        result = audit_sources.audit_story(isolated, now=NOW)
    finally:
        audit_sources.audit_story = original
    codes = {issue["code"] for issue in result["issues"]}
    assert "short_body" in codes
    assert result["warning_count"] == 1

    print("Cluster-aware audit tests passed")


if __name__ == "__main__":
    main()
