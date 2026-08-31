from __future__ import annotations

import json
import tempfile
from pathlib import Path

from merge_enriched_output import merge


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        enriched = root / "enriched.json"
        latest = root / "latest.json"
        output = root / "merged.json"

        latest.write_text(json.dumps({
            "generated_at": "2026-08-31T12:00:00+00:00",
            "top_story_ids": ["a", "b"],
            "stories": [
                {
                    "id": "a",
                    "title": "Latest headline wording",
                    "summary": "Latest feed summary",
                    "published": "2026-08-31T11:55:00+00:00",
                    "rank_score": 91,
                    "scope": "local",
                    "card_image": "cache/news/new.webp",
                    "content_status": "summary",
                    "content": "",
                    "quality": {"score": 40},
                },
                {
                    "id": "b",
                    "title": "Brand new story",
                    "published": "2026-08-31T11:58:00+00:00",
                    "rank_score": 88,
                    "scope": "local",
                    "content_status": "summary",
                    "quality": {"score": 35},
                },
            ],
        }), encoding="utf-8")

        enriched.write_text(json.dumps({
            "generated_at": "2026-08-31T11:40:00+00:00",
            "last_enrichment_at": "2026-08-31T12:02:00+00:00",
            "last_enrichment_count": 1,
            "stories": [
                {
                    "id": "a",
                    "title": "Cleaned article title",
                    "summary": "Richer extracted summary",
                    "published": "2026-08-31T11:30:00+00:00",
                    "rank_score": 70,
                    "scope": "canada",
                    "card_image": "cache/news/old.webp",
                    "content_status": "full",
                    "content": "Full article body",
                    "paragraphs": ["Full article body"],
                    "word_count": 600,
                    "quality": {"score": 90},
                    "enriched_at": "2026-08-31T12:02:00+00:00",
                }
            ],
        }), encoding="utf-8")

        merged_count, story_count = merge(enriched, latest, output)
        payload = json.loads(output.read_text(encoding="utf-8"))
        by_id = {story["id"]: story for story in payload["stories"]}

        assert merged_count == 1
        assert story_count == 2
        assert payload["generated_at"] == "2026-08-31T12:00:00+00:00"
        assert payload["top_story_ids"] == ["a", "b"]
        assert payload["last_enrichment_count"] == 1
        assert payload["full_story_count"] == 1
        assert payload["story_count"] == 2

        story = by_id["a"]
        assert story["title"] == "Cleaned article title"
        assert story["summary"] == "Richer extracted summary"
        assert story["content"] == "Full article body"
        assert story["content_status"] == "full"
        assert story["published"] == "2026-08-31T11:55:00+00:00"
        assert story["rank_score"] == 91
        assert story["scope"] == "local"
        assert story["card_image"] == "cache/news/new.webp"
        assert by_id["b"]["title"] == "Brand new story"

    print("Safe enrichment merge test passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
