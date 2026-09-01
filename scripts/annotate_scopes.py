#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from apply_local_source_rules import apply_rules, scope_for_story

ROOT = Path(__file__).resolve().parents[1]
NEWS_FILE = ROOT / "data" / "news.json"


def annotate_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Apply the strict Local/Canada source contract.

    Local is determined only by the explicit London-source whitelist. National
    publishers are never promoted into Local because of article text or scores.
    """
    return apply_rules(payload)


def main() -> int:
    if not NEWS_FILE.exists():
        print(f"Scope annotation skipped: {NEWS_FILE} does not exist")
        return 0

    payload = json.loads(NEWS_FILE.read_text(encoding="utf-8"))
    annotate_payload(payload)
    NEWS_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    counts = payload.get("scope_counts") or {}
    print(
        "Story scopes: "
        f"local={counts.get('local', 0)} "
        f"canada={counts.get('canada', 0)} "
        f"all={counts.get('all', 0)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
