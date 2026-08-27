#!/usr/bin/env python3
"""Audit Scoop's published archive and write data/audit.json.

This is intentionally a verification layer, not another extractor. It inspects the
same post-Scoop records Astro is about to publish, combining article-shape checks,
known publisher-furniture checks, source health, and extraction metadata into a
review queue for /admin/.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
NEWS_FILE = ROOT / "data" / "news.json"
AUDIT_FILE = ROOT / "data" / "audit.json"
LONDON_TZ = ZoneInfo("America/Toronto")

SEVERITY_WEIGHT = {"critical": 35, "warning": 12, "info": 3}
SEVERITY_ORDER = {"critical": 0, "warning": 1, "info": 2}

# Publishers where a tiny body is more likely to mean extraction failed than that
# the publisher intentionally posted a one-paragraph public notice.
ARTICLE_PUBLISHERS = {
    "CBC News London",
    "CTV News",
    "Global News London",
    "London Free Press",
    "104.7 Heart FM",
    "106.9 The X",
}

# These are intentionally narrow. The audit should catch obvious page furniture,
# not flag an article merely because it happens to discuss newsletters or videos.
MODULE_HEADING_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("inline_related_content", re.compile(r"^(?:read more|more from(?: local news)?|related(?: stories| coverage)?|recommended(?: for you)?|you may also like|most read|trending(?: now)?|top stories)$", re.I)),
    ("publisher_furniture", re.compile(r"^(?:sponsored content|report an error|journalistic standards|stick to the facts|comments?)$", re.I)),
    ("video_module", re.compile(r"^(?:watch(?: more)?|previous video|next video|recommended video)$", re.I)),
)

TAIL_FURNITURE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("publisher_furniture", re.compile(r"\b(?:sponsored content|report an error|journalistic standards|add .{0,40} as a preferred source on google|stick to the facts)\b", re.I)),
    ("newsletter_leak", re.compile(r"\b(?:sign up for (?:our|the)|get daily .{0,35} news|newsletter signup|subscribe to (?:our|the) newsletter)\b", re.I)),
    ("inline_related_content", re.compile(r"\bmore from local news\b", re.I)),
)


@dataclass
class Issue:
    severity: str
    code: str
    message: str
    detail: str = ""


def clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def parse_dt(value: Any) -> datetime | None:
    text = clean(value)
    if not text:
        return None
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (ValueError, TypeError):
        return None


def block_text(block: dict[str, Any]) -> str:
    kind = clean(block.get("type")).lower()
    if kind == "list":
        items = block.get("items") or []
        if isinstance(items, list):
            return " \n ".join(clean(item) for item in items if clean(item))
    return clean(block.get("text") or block.get("caption") or "")


def text_blocks(story: dict[str, Any]) -> list[dict[str, Any]]:
    blocks = story.get("content_blocks") or []
    return [block for block in blocks if isinstance(block, dict) and clean(block.get("type")).lower() in {"paragraph", "heading", "quote", "list"}]


def image_blocks(story: dict[str, Any]) -> list[dict[str, Any]]:
    blocks = story.get("content_blocks") or []
    return [block for block in blocks if isinstance(block, dict) and clean(block.get("type")).lower() == "image"]


def normalized_paragraph(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", clean(value).lower()).strip()


def valid_http_url(value: Any) -> bool:
    try:
        parsed = urlparse(clean(value))
        return parsed.scheme in {"http", "https"} and bool(parsed.netloc)
    except Exception:
        return False


def consecutive_image_run(blocks: Iterable[dict[str, Any]]) -> int:
    longest = current = 0
    for block in blocks:
        if clean(block.get("type")).lower() == "image":
            current += 1
            longest = max(longest, current)
        else:
            current = 0
    return longest


def quality_meta(story: dict[str, Any]) -> tuple[int, str, str]:
    quality = story.get("quality") or {}
    try:
        score = int(quality.get("score") or 0)
    except (TypeError, ValueError):
        score = 0
    return score, clean(quality.get("grade") or "unknown"), clean(quality.get("method") or "unknown")


def add_once(issues: list[Issue], issue: Issue) -> None:
    if any(existing.code == issue.code and existing.message == issue.message for existing in issues):
        return
    issues.append(issue)


def audit_story(story: dict[str, Any], now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    issues: list[Issue] = []
    source = clean(story.get("source")) or "Unknown source"
    title = clean(story.get("title"))
    content = clean(story.get("content"))
    status = clean(story.get("content_status")).lower() or "unknown"
    try:
        words = int(story.get("word_count") or 0)
    except (TypeError, ValueError):
        words = 0
    score, grade, method = quality_meta(story)
    blocks = story.get("content_blocks") or []
    blocks = [block for block in blocks if isinstance(block, dict)]
    text_parts = text_blocks(story)
    images = image_blocks(story)

    if not title:
        add_once(issues, Issue("critical", "missing_title", "Headline is missing."))
    if not valid_http_url(story.get("url")):
        add_once(issues, Issue("critical", "invalid_url", "Publisher URL is missing or invalid."))

    published = parse_dt(story.get("published"))
    if not published:
        add_once(issues, Issue("warning", "missing_date", "Publish date could not be verified."))
    elif published > now + timedelta(hours=6):
        add_once(issues, Issue("warning", "future_date", "Publish date is unexpectedly in the future.", published.isoformat()))

    scrape_error = clean(story.get("scrape_error"))
    if scrape_error:
        add_once(issues, Issue("critical", "scrape_error", "Scoop recorded a scraping error.", scrape_error[:260]))
    if status == "failed":
        add_once(issues, Issue("critical", "failed_body", "Article extraction failed."))

    if status == "full" and words < 80:
        add_once(issues, Issue("critical", "status_mismatch", "Story is marked full but the extracted body is extremely short.", f"{words} words"))
    elif source in ARTICLE_PUBLISHERS and status in {"summary", "unknown"} and words < 55:
        add_once(issues, Issue("warning", "short_body", "Article publisher returned only a very short body.", f"{words} words"))
    elif source in ARTICLE_PUBLISHERS and status == "partial" and words < 95:
        add_once(issues, Issue("warning", "short_partial_body", "Partial extraction may be missing article content.", f"{words} words"))

    if words > 4500:
        add_once(issues, Issue("warning", "oversized_body", "Extracted body is unusually long and may contain page furniture.", f"{words} words"))

    if content.endswith(("...", "…")) and words >= 50:
        add_once(issues, Issue("warning", "truncated_ending", "Article body appears to end with an ellipsis."))

    if score and score < 25:
        add_once(issues, Issue("warning", "low_quality", "Scoop extraction quality is low.", f"Quality {score}/100"))
    elif not score and words:
        add_once(issues, Issue("info", "missing_quality", "Extraction quality metadata is missing."))

    # Known module/furniture markers are most meaningful when they appear as their
    # own heading or list label, rather than in ordinary article prose.
    for block in text_parts:
        kind = clean(block.get("type")).lower()
        if kind not in {"heading", "list"}:
            continue
        candidates: list[str]
        if kind == "list" and isinstance(block.get("items"), list):
            candidates = [clean(item) for item in block.get("items") if clean(item)]
        else:
            candidates = [block_text(block)]
        for candidate in candidates:
            for code, pattern in MODULE_HEADING_PATTERNS:
                if pattern.search(candidate):
                    add_once(issues, Issue("warning", code, "Possible publisher module leaked into the article body.", candidate[:220]))

    # Furniture usually leaks near the end of an article. Restrict prose checks to
    # the tail to avoid false positives from legitimate reporting.
    tail_parts = [block_text(block) for block in text_parts if block_text(block)]
    tail_count = max(2, len(tail_parts) // 3) if tail_parts else 0
    tail = " ".join(tail_parts[-tail_count:]) if tail_count else ""
    for code, pattern in TAIL_FURNITURE_PATTERNS:
        match = pattern.search(tail)
        if match:
            add_once(issues, Issue("warning", code, "Possible publisher furniture appears near the end of the article.", clean(match.group(0))[:220]))

    paragraphs = [clean(block.get("text")) for block in text_parts if clean(block.get("type")).lower() == "paragraph" and clean(block.get("text"))]
    normalized = [normalized_paragraph(p) for p in paragraphs if len(normalized_paragraph(p)) >= 45]
    duplicates = [text for text, count in Counter(normalized).items() if count > 1]
    if duplicates:
        add_once(issues, Issue("warning", "duplicate_body", "Duplicate article paragraphs were detected.", f"{len(duplicates)} duplicated paragraph pattern(s)"))

    if len(images) > 8:
        add_once(issues, Issue("warning", "too_many_images", "Article contains an unusually large number of inline images.", f"{len(images)} inline images"))
    max_image_run = consecutive_image_run(blocks)
    if max_image_run >= 3:
        add_once(issues, Issue("warning", "image_gallery_leak", "Several images appear consecutively with no article text between them.", f"{max_image_run} consecutive images"))
    bad_images = [clean(block.get("url")) for block in images if not valid_http_url(block.get("url"))]
    if bad_images:
        add_once(issues, Issue("warning", "invalid_inline_image", "One or more inline image URLs are invalid.", f"{len(bad_images)} invalid image URL(s)"))

    hero = clean(story.get("image"))
    if hero and not valid_http_url(hero) and not hero.startswith("/"):
        add_once(issues, Issue("warning", "invalid_hero_image", "Hero image URL is invalid.", hero[:220]))
    elif not hero:
        add_once(issues, Issue("info", "missing_hero_image", "Story has no hero image."))

    author = clean(story.get("author"))
    if not author and source in ARTICLE_PUBLISHERS:
        add_once(issues, Issue("info", "missing_author", "No author/byline was captured."))

    try:
        local_score = int(story.get("local_score") or 0)
    except (TypeError, ValueError):
        local_score = 0
    if story.get("local_score") is not None and local_score < 20 and source not in {"City of London Newsroom", "London Police Service", "London Fire Department"}:
        add_once(issues, Issue("info", "low_local_relevance", "Story has a low London relevance score.", f"Local score {local_score}/100"))

    critical = sum(1 for issue in issues if issue.severity == "critical")
    warnings = sum(1 for issue in issues if issue.severity == "warning")
    infos = sum(1 for issue in issues if issue.severity == "info")
    audit_score = max(0, 100 - sum(SEVERITY_WEIGHT.get(issue.severity, 0) for issue in issues))
    audit_status = "fail" if critical else "review" if warnings else "pass"

    return {
        "id": clean(story.get("id")),
        "source": source,
        "title": title or "Untitled story",
        "url": clean(story.get("url")),
        "published": clean(story.get("published")),
        "audit_status": audit_status,
        "audit_score": audit_score,
        "critical_count": critical,
        "warning_count": warnings,
        "info_count": infos,
        "content_status": status,
        "word_count": words,
        "paragraph_count": len(paragraphs),
        "inline_image_count": len(images),
        "quality_score": score,
        "quality_grade": grade,
        "extraction_method": method,
        "extraction_profile": clean(story.get("extraction_profile")) or "unknown",
        "local_score": local_score,
        "issues": [asdict(issue) for issue in issues],
    }


def source_report(source: str, audited: list[dict[str, Any]], health: dict[str, Any] | None) -> dict[str, Any]:
    health = health or {}
    sample_size = len(audited)
    passes = sum(1 for item in audited if item["audit_status"] == "pass")
    reviews = sum(1 for item in audited if item["audit_status"] == "review")
    fails = sum(1 for item in audited if item["audit_status"] == "fail")
    usable = sum(1 for item in audited if item["content_status"] in {"full", "partial"})
    qualities = [item["quality_score"] for item in audited if item["quality_score"]]
    words = [item["word_count"] for item in audited if item["word_count"]]
    methods = Counter(item["extraction_method"] for item in audited if item["extraction_method"] and item["extraction_method"] != "unknown")
    issues = Counter(issue["severity"] for item in audited for issue in item["issues"])
    latest = max((item["published"] for item in audited if item["published"]), default="")
    collector_status = clean(health.get("status")) or "unknown"

    pass_rate = round((passes / sample_size) * 100) if sample_size else 0
    usable_rate = round((usable / sample_size) * 100) if sample_size else 0
    if not sample_size:
        status = "waiting"
    elif collector_status == "error" or (fails and pass_rate < 60):
        status = "error"
    elif fails or reviews or collector_status == "degraded" or pass_rate < 80:
        status = "review"
    else:
        status = "healthy"

    return {
        "source": source,
        "status": status,
        "collector_status": collector_status,
        "profile": clean(health.get("profile")) or (audited[0]["extraction_profile"] if audited else "unknown"),
        "sample_size": sample_size,
        "pass": passes,
        "review": reviews,
        "fail": fails,
        "pass_rate": pass_rate,
        "usable_body_rate": usable_rate,
        "average_words": round(sum(words) / len(words)) if words else 0,
        "average_quality": round(sum(qualities) / len(qualities)) if qualities else 0,
        "primary_method": methods.most_common(1)[0][0] if methods else "unknown",
        "method_counts": dict(methods),
        "critical_issues": issues.get("critical", 0),
        "warning_issues": issues.get("warning", 0),
        "info_issues": issues.get("info", 0),
        "latest_published": latest,
        "found_this_run": int(health.get("found_this_run") or 0),
        "tracked": int(health.get("tracked") or 0),
        "last_scrape": clean(health.get("last_scrape")),
        "last_error": clean(health.get("last_error")),
    }


def build_audit(payload: dict[str, Any], sample_per_source: int = 10) -> dict[str, Any]:
    stories = payload.get("stories") or []
    stories = [story for story in stories if isinstance(story, dict)]
    health_items = payload.get("source_health") or []
    health_map = {clean(item.get("source")): item for item in health_items if isinstance(item, dict) and clean(item.get("source"))}

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for story in stories:
        grouped[clean(story.get("source")) or "Unknown source"].append(story)

    for items in grouped.values():
        items.sort(key=lambda item: clean(item.get("published")), reverse=True)

    source_names = list(dict.fromkeys([*health_map.keys(), *sorted(grouped.keys())]))
    audited: list[dict[str, Any]] = []
    source_reports: list[dict[str, Any]] = []
    now = datetime.now(timezone.utc)

    for source in source_names:
        sample = grouped.get(source, [])[: max(1, sample_per_source)]
        source_audited = [audit_story(story, now=now) for story in sample]
        audited.extend(source_audited)
        source_reports.append(source_report(source, source_audited, health_map.get(source)))

    issue_rows: list[dict[str, Any]] = []
    for story in audited:
        for issue in story["issues"]:
            issue_rows.append({
                "severity": issue["severity"],
                "code": issue["code"],
                "message": issue["message"],
                "detail": issue.get("detail", ""),
                "story_id": story["id"],
                "source": story["source"],
                "title": story["title"],
                "url": story["url"],
                "published": story["published"],
                "content_status": story["content_status"],
                "word_count": story["word_count"],
                "quality_score": story["quality_score"],
                "extraction_method": story["extraction_method"],
            })

    issue_rows.sort(key=lambda item: (SEVERITY_ORDER.get(item["severity"], 9), item.get("source", ""), item.get("title", "")))
    source_reports.sort(key=lambda item: ({"error": 0, "review": 1, "waiting": 2, "healthy": 3}.get(item["status"], 9), item["source"]))

    pass_count = sum(1 for item in audited if item["audit_status"] == "pass")
    review_count = sum(1 for item in audited if item["audit_status"] == "review")
    fail_count = sum(1 for item in audited if item["audit_status"] == "fail")
    severity_counts = Counter(item["severity"] for item in issue_rows)
    source_status_counts = Counter(item["status"] for item in source_reports)

    return {
        "audit_schema_version": 1,
        "news_schema_version": payload.get("schema_version"),
        "generated_at": now.isoformat(),
        "generated_at_london": now.astimezone(LONDON_TZ).isoformat(),
        "news_generated_at": payload.get("generated_at"),
        "sample_per_source": sample_per_source,
        "overview": {
            "archive_story_count": len(stories),
            "source_count": len(source_reports),
            "audited_story_count": len(audited),
            "pass_story_count": pass_count,
            "review_story_count": review_count,
            "fail_story_count": fail_count,
            "critical_issue_count": severity_counts.get("critical", 0),
            "warning_issue_count": severity_counts.get("warning", 0),
            "info_issue_count": severity_counts.get("info", 0),
            "healthy_source_count": source_status_counts.get("healthy", 0),
            "review_source_count": source_status_counts.get("review", 0),
            "error_source_count": source_status_counts.get("error", 0),
            "waiting_source_count": source_status_counts.get("waiting", 0),
        },
        "source_reports": source_reports,
        "issues": issue_rows,
        "stories": audited,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit Scoop output and generate data/audit.json")
    parser.add_argument("--input", type=Path, default=NEWS_FILE, help="Path to news.json")
    parser.add_argument("--output", type=Path, default=AUDIT_FILE, help="Path for audit.json")
    parser.add_argument("--sample-per-source", type=int, default=10, help="Newest stories to audit per source")
    args = parser.parse_args()

    if not args.input.exists():
        print(f"Audit input does not exist: {args.input}")
        return 2

    try:
        payload = json.loads(args.input.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"Could not read {args.input}: {exc}")
        return 2

    report = build_audit(payload, sample_per_source=max(1, args.sample_per_source))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    overview = report["overview"]
    print(
        "Scoop audit: "
        f"{overview['audited_story_count']} stories across {overview['source_count']} sources | "
        f"{overview['pass_story_count']} pass, {overview['review_story_count']} review, {overview['fail_story_count']} fail | "
        f"{overview['critical_issue_count']} critical, {overview['warning_issue_count']} warnings"
    )
    print(f"Wrote audit report to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
