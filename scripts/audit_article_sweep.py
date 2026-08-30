from __future__ import annotations

"""Fold the universal article sweep signals into Scoop's audit report."""

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
NEWS_PATH = ROOT / "data" / "news.json"
AUDIT_PATH = ROOT / "data" / "audit.json"
WEIGHTS = {"critical": 35, "warning": 12, "info": 3}


def clean(value: Any) -> str:
    return " ".join(str(value or "").split())


def recalculate(story: dict[str, Any]) -> None:
    issues = story.get("issues") if isinstance(story.get("issues"), list) else []
    critical = sum(1 for issue in issues if issue.get("severity") == "critical")
    warnings = sum(1 for issue in issues if issue.get("severity") == "warning")
    infos = sum(1 for issue in issues if issue.get("severity") == "info")
    story["critical_count"] = critical
    story["warning_count"] = warnings
    story["info_count"] = infos
    story["audit_score"] = max(0, 100 - sum(WEIGHTS.get(str(issue.get("severity")), 0) for issue in issues))
    story["audit_status"] = "fail" if critical else "review" if warnings else "pass"


def append_issue(story: dict[str, Any], issue: dict[str, str]) -> bool:
    issues = story.setdefault("issues", [])
    if any(existing.get("code") == issue["code"] for existing in issues if isinstance(existing, dict)):
        return False
    issues.append(issue)
    return True


def enrich(news: dict[str, Any], audit: dict[str, Any]) -> dict[str, Any]:
    stories = [story for story in news.get("stories", []) if isinstance(story, dict)]
    sampled = [story for story in audit.get("stories", []) if isinstance(story, dict)]
    sampled_by_id = {clean(story.get("id")): story for story in sampled if clean(story.get("id"))}

    source_counts: dict[str, Counter[str]] = defaultdict(Counter)
    flagged_total = flat_total = pending_total = 0
    sweep_schema = int(news.get("article_sweep_schema") or 0)

    for story in stories:
        source = clean(story.get("source")) or "Unknown source"
        flags = story.get("article_hygiene_flags") if isinstance(story.get("article_hygiene_flags"), list) else []
        flat = story.get("article_format_state") == "flat"
        pending = sweep_schema > 0 and int(story.get("article_sweep_schema") or 0) < sweep_schema
        if flags:
            source_counts[source]["hygiene"] += 1
            flagged_total += 1
        if flat:
            source_counts[source]["flat"] += 1
            flat_total += 1
        if pending:
            source_counts[source]["pending"] += 1
            pending_total += 1

        audited = sampled_by_id.get(clean(story.get("id")))
        if not audited:
            continue
        changed = False
        if flags:
            changed |= append_issue(audited, {
                "severity": "warning",
                "code": "universal_hygiene_flag",
                "message": "Universal article sweep still detects publisher chrome in this story.",
                "detail": ", ".join(str(flag) for flag in flags)[:260],
            })
        if flat and int(story.get("word_count") or 0) >= 120:
            changed |= append_issue(audited, {
                "severity": "warning",
                "code": "flat_article_format",
                "message": "Article remains structurally flat after the universal formatting sweep.",
                "detail": clean(story.get("article_sweep_method") or "no rich extraction recovered")[:260],
            })
        if pending:
            changed |= append_issue(audited, {
                "severity": "info",
                "code": "article_sweep_pending",
                "message": "Universal source-level formatting sweep is still pending for this story.",
                "detail": "",
            })
        if changed:
            recalculate(audited)

    report_by_source = {
        clean(report.get("source")): report
        for report in audit.get("source_reports", [])
        if isinstance(report, dict) and clean(report.get("source"))
    }
    for source, counts in source_counts.items():
        report = report_by_source.get(source)
        if not report:
            continue
        report["article_hygiene_flagged"] = counts.get("hygiene", 0)
        report["flat_articles"] = counts.get("flat", 0)
        report["article_sweep_pending"] = counts.get("pending", 0)
        if (counts.get("hygiene", 0) or counts.get("flat", 0)) and report.get("status") != "error":
            report["status"] = "review"

    overview = audit.setdefault("overview", {})
    overview["article_hygiene_flagged_count"] = flagged_total
    overview["flat_article_count"] = flat_total
    overview["article_sweep_pending_count"] = pending_total
    audit["article_sweep_schema"] = sweep_schema
    audit["article_sweep_stats"] = news.get("article_sweep_stats") or {}

    issues = []
    for sampled_story in sampled:
        for issue in sampled_story.get("issues", []) if isinstance(sampled_story.get("issues"), list) else []:
            if not isinstance(issue, dict):
                continue
            issues.append({
                **issue,
                "story_id": sampled_story.get("id", ""),
                "source": sampled_story.get("source", ""),
                "title": sampled_story.get("title", ""),
                "url": sampled_story.get("url", ""),
                "published": sampled_story.get("published", ""),
                "content_status": sampled_story.get("content_status", ""),
                "word_count": sampled_story.get("word_count", 0),
                "quality_score": sampled_story.get("quality_score", 0),
                "extraction_method": sampled_story.get("extraction_method", ""),
            })
    audit["issues"] = issues
    return audit


def main() -> int:
    if not NEWS_PATH.exists() or not AUDIT_PATH.exists():
        print("Article sweep audit: news.json or audit.json missing")
        return 0
    news = json.loads(NEWS_PATH.read_text(encoding="utf-8"))
    audit = json.loads(AUDIT_PATH.read_text(encoding="utf-8"))
    enrich(news, audit)
    AUDIT_PATH.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    overview = audit.get("overview") or {}
    print(
        "Article sweep audit: "
        f"{overview.get('article_hygiene_flagged_count', 0)} hygiene-flagged, "
        f"{overview.get('flat_article_count', 0)} flat, "
        f"{overview.get('article_sweep_pending_count', 0)} pending"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
