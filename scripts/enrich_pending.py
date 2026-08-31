from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import fetch_news
import run_scoop
from sources import SOURCES, Source


ROOT = Path(__file__).resolve().parents[1]
DATA_FILE = ROOT / "data" / "news.json"


def _source_map() -> dict[str, Source]:
    mapping: dict[str, Source] = {}
    for source in SOURCES:
        mapping[source.name] = source
        mapping[fetch_news.canonical_source_name(source.name)] = source
    return mapping


def _needs_enrichment(story: dict[str, Any]) -> bool:
    if str(story.get("refresh_stage") or "").lower() == "metadata":
        return True
    if str(story.get("content_status") or "").lower() not in {"summary", "partial", "failed"}:
        return False
    blocks = story.get("content_blocks")
    paragraphs = story.get("paragraphs")
    has_body = bool(
        (isinstance(blocks, list) and blocks)
        or (isinstance(paragraphs, list) and any(str(item or "").strip() for item in paragraphs))
        or str(story.get("content") or "").strip()
    )
    return not has_body


def _published_key(story: dict[str, Any]) -> str:
    return str(story.get("cluster_latest_published") or story.get("published") or "")


def enrich_pending(limit: int) -> tuple[int, int]:
    payload = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    stories = payload.get("stories") or []
    if not isinstance(stories, list):
        raise RuntimeError("data/news.json does not contain a stories list")

    run_scoop.install_runtime_safeguards()
    sources = _source_map()
    candidates = [story for story in stories if isinstance(story, dict) and _needs_enrichment(story)]
    candidates.sort(key=_published_key, reverse=True)

    attempted = 0
    completed = 0
    now = datetime.now(timezone.utc).isoformat()

    for story in candidates:
        if attempted >= limit:
            break
        url = str(story.get("url") or "").strip()
        if not url or "news.google.com" in urlparse(url).netloc.lower():
            continue
        source_name = fetch_news.canonical_source_name(story.get("source"))
        source = sources.get(source_name)
        if source is None:
            continue

        attempted += 1
        try:
            enriched = fetch_news.enrich_article(dict(story), source)
            enriched["refresh_stage"] = "enriched"
            enriched["enriched_at"] = now
            story.clear()
            story.update(enriched)
            completed += 1
            print(f"Enriched: {source_name} | {str(story.get('title') or '')[:90]}")
        except Exception as exc:
            story["refresh_stage"] = "metadata"
            story["enrichment_error"] = str(exc)[:240]
            story["enrichment_attempted_at"] = now
            print(f"Deferred enrichment failed: {source_name} | {str(story.get('title') or '')[:70]} | {exc}")

    payload["last_enrichment_at"] = now
    payload["last_enrichment_count"] = completed
    DATA_FILE.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return attempted, completed


def main() -> int:
    parser = argparse.ArgumentParser(description="Enrich metadata-only London News stories")
    parser.add_argument("--limit", type=int, default=48)
    args = parser.parse_args()
    attempted, completed = enrich_pending(max(1, args.limit))
    print(f"Article enrichment: {completed}/{attempted} completed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
