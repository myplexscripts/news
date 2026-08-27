#!/usr/bin/env python3
"""Run Scoop's audit with event-cluster context.

A publisher can legitimately expose only a short brief while another first-party
source in the same event cluster has the complete report. Keep that visible as
an informational extraction note instead of treating the whole event as a broken
article, while preserving every other audit warning and failure unchanged.
"""

from __future__ import annotations

import json
from collections import defaultdict
from typing import Any

import audit_sources


def _complete_sources_by_cluster(payload: dict[str, Any]) -> dict[str, set[str]]:
    complete: dict[str, set[str]] = defaultdict(set)
    for story in payload.get("stories") or []:
        if not isinstance(story, dict):
            continue
        cluster_id = str(story.get("cluster_id") or "").strip()
        source = str(story.get("source") or "").strip()
        status = str(story.get("content_status") or "").strip().lower()
        try:
            words = int(story.get("word_count") or 0)
        except (TypeError, ValueError):
            words = 0
        if cluster_id and source and status in {"full", "partial"} and words >= 80:
            complete[cluster_id].add(source)
    return complete


def _recalculate(result: dict[str, Any]) -> dict[str, Any]:
    issues = result.get("issues") or []
    critical = sum(1 for issue in issues if issue.get("severity") == "critical")
    warnings = sum(1 for issue in issues if issue.get("severity") == "warning")
    infos = sum(1 for issue in issues if issue.get("severity") == "info")
    result["critical_count"] = critical
    result["warning_count"] = warnings
    result["info_count"] = infos
    result["audit_score"] = max(
        0,
        100 - sum(audit_sources.SEVERITY_WEIGHT.get(str(issue.get("severity")), 0) for issue in issues),
    )
    result["audit_status"] = "fail" if critical else "review" if warnings else "pass"
    return result


def install_cluster_aware_audit(payload: dict[str, Any]) -> None:
    complete_sources = _complete_sources_by_cluster(payload)
    original = audit_sources.audit_story

    def cluster_aware_audit_story(story: dict[str, Any], now=None) -> dict[str, Any]:
        result = original(story, now=now)
        cluster_id = str(story.get("cluster_id") or "").strip()
        source = str(story.get("source") or "").strip()
        alternate_sources = complete_sources.get(cluster_id, set()) - {source}
        if not alternate_sources:
            return result

        revised: list[dict[str, Any]] = []
        changed = False
        for issue in result.get("issues") or []:
            if issue.get("code") == "short_body" and issue.get("severity") == "warning":
                revised.append({
                    "severity": "info",
                    "code": "cluster_covered_summary",
                    "message": "Short source brief has a complete alternate report in the same event cluster.",
                    "detail": ", ".join(sorted(alternate_sources)),
                })
                changed = True
            else:
                revised.append(issue)

        if changed:
            result["issues"] = revised
            _recalculate(result)
        return result

    audit_sources.audit_story = cluster_aware_audit_story


def main() -> int:
    if not audit_sources.NEWS_FILE.exists():
        return audit_sources.main()
    try:
        payload = json.loads(audit_sources.NEWS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return audit_sources.main()
    install_cluster_aware_audit(payload)
    return audit_sources.main()


if __name__ == "__main__":
    raise SystemExit(main())
