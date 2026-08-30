from __future__ import annotations

from audit_article_sweep import enrich


def run() -> None:
    news = {
        "article_sweep_schema": 1,
        "article_sweep_stats": {"stories": 3},
        "stories": [
            {"id": "a", "source": "Future News", "word_count": 300, "article_sweep_schema": 1, "article_hygiene_flags": ["publisher-card-run"], "article_format_state": "structured"},
            {"id": "b", "source": "Future News", "word_count": 500, "article_sweep_schema": 1, "article_format_state": "flat", "article_sweep_method": "existing-clean"},
            {"id": "c", "source": "Other News", "word_count": 100, "article_sweep_schema": 0, "article_format_state": "structured"},
        ],
    }
    audit = {
        "overview": {},
        "stories": [
            {"id": "a", "source": "Future News", "issues": [], "audit_status": "pass", "audit_score": 100},
            {"id": "b", "source": "Future News", "issues": [], "audit_status": "pass", "audit_score": 100},
        ],
        "source_reports": [{"source": "Future News", "status": "healthy"}, {"source": "Other News", "status": "healthy"}],
        "issues": [],
    }
    result = enrich(news, audit)
    future = next(row for row in result["source_reports"] if row["source"] == "Future News")
    assert future["status"] == "review"
    assert future["article_hygiene_flagged"] == 1
    assert future["flat_articles"] == 1
    assert result["overview"]["article_hygiene_flagged_count"] == 1
    assert result["overview"]["flat_article_count"] == 1
    assert result["overview"]["article_sweep_pending_count"] == 1
    codes = {issue["code"] for issue in result["issues"]}
    assert "universal_hygiene_flag" in codes
    assert "flat_article_format" in codes
    print("PASS article sweep audit integration")


if __name__ == "__main__":
    run()
