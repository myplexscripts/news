from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
NEWS_FILE = ROOT / "data" / "news.json"
OUTPUT_FILE = ROOT / "public" / "data" / "search-index.json"
MAX_BODY_CHARS = 1800


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _block_text(block: Any) -> str:
    if not isinstance(block, dict):
        return ""
    if block.get("text"):
        return _clean(block.get("text"))
    items = block.get("items")
    if isinstance(items, list):
        return " ".join(_clean(item if isinstance(item, str) else item.get("text")) for item in items)
    return ""


def _body(story: dict[str, Any]) -> str:
    blocks = story.get("content_blocks")
    if isinstance(blocks, list) and blocks:
        text = " ".join(_block_text(block) for block in blocks[:24])
    else:
        paragraphs = story.get("paragraphs")
        if isinstance(paragraphs, list):
            text = " ".join(_clean(item) for item in paragraphs[:16])
        else:
            text = _clean(story.get("content"))
    return _clean(text)[:MAX_BODY_CHARS]


def main() -> int:
    payload = json.loads(NEWS_FILE.read_text(encoding="utf-8"))
    source_scopes = {
        _clean(item.get("source")): _clean(item.get("scope")).lower()
        for item in (payload.get("source_health") or [])
        if isinstance(item, dict)
    }

    documents = []
    for story in payload.get("stories") or []:
        if not isinstance(story, dict) or not story.get("id") or not story.get("title"):
            continue
        source = _clean(story.get("source"))
        explicit_scope = _clean(story.get("scope")).lower()
        scope = "canada" if explicit_scope == "canada" or source_scopes.get(source) == "canada" else "local"
        documents.append({
            "id": str(story.get("id")),
            "title": _clean(story.get("title")),
            "summary": _clean(story.get("summary")),
            "source": source,
            "category": _clean(story.get("category")) or "Local",
            "scope": scope,
            "published": _clean(story.get("cluster_latest_published") or story.get("published")),
            "topics": [_clean(item) for item in (story.get("story_topics") or []) if _clean(item)],
            "body": _body(story),
            "image": _clean(story.get("card_image_small") or story.get("card_image") or story.get("image")),
            "readMinutes": max(1, round(int(story.get("word_count") or 0) / 220)) if int(story.get("word_count") or 0) > 0 else None,
        })

    documents.sort(key=lambda item: item.get("published") or "", reverse=True)
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(
        json.dumps({"generated_at": payload.get("generated_at"), "documents": documents}, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    print(f"Search index: {len(documents)} documents -> {OUTPUT_FILE.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
