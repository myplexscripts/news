from __future__ import annotations

import hashlib
import json
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_FILE = ROOT / "data" / "news.json"
PUBLIC = ROOT / "public"
PUBLIC_DATA = PUBLIC / "data"
STORY_DATA = PUBLIC_DATA / "stories"

FEED_FIELDS = {
    "id",
    "title",
    "summary",
    "source",
    "discovery_via",
    "scope",
    "category",
    "published",
    "cluster_latest_published",
    "card_image_small",
    "card_image",
    "image",
    "image_alt",
    "image_focus_x",
    "image_focus_y",
    "image_caption",
    "word_count",
    "cluster_sources",
    "cluster_source_count",
    "cluster_id",
    "cluster_representative",
    "quality",
    "content_status",
    "author",
    "url",
    "story_topics",
}


def safe_story_filename(story_id: str) -> str:
    if re.fullmatch(r"[A-Za-z0-9_-]{1,160}", story_id):
        return f"{story_id}.json"
    return f"{hashlib.sha1(story_id.encode('utf-8')).hexdigest()}.json"


def copy_if_exists(source: Path, destination: Path) -> None:
    if not source.exists():
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    if source.is_dir():
        shutil.copytree(source, destination, dirs_exist_ok=True)
    else:
        shutil.copy2(source, destination)


def main() -> None:
    if not DATA_FILE.exists():
        raise SystemExit(f"Missing news data: {DATA_FILE}")

    with DATA_FILE.open("r", encoding="utf-8") as handle:
        news = json.load(handle)

    PUBLIC_DATA.mkdir(parents=True, exist_ok=True)
    if STORY_DATA.exists():
        shutil.rmtree(STORY_DATA)
    STORY_DATA.mkdir(parents=True, exist_ok=True)

    stories = news.get("stories") or []
    feed_stories = []

    for story in stories:
        story_id = str(story.get("id") or "").strip()
        if not story_id:
            continue

        story_payload = dict(story)
        story_payload.pop("hero_top_colour", None)

        filename = safe_story_filename(story_id)
        with (STORY_DATA / filename).open("w", encoding="utf-8") as handle:
            json.dump(story_payload, handle, ensure_ascii=False, separators=(",", ":"))

        card = {key: story_payload.get(key) for key in FEED_FIELDS if key in story_payload}
        card["_data_file"] = filename
        feed_stories.append(card)

    feed = {
        "generated_at": news.get("generated_at"),
        "source_health": news.get("source_health") or {},
        "stories": feed_stories,
    }

    with (PUBLIC_DATA / "app-feed.json").open("w", encoding="utf-8") as handle:
        json.dump(feed, handle, ensure_ascii=False, separators=(",", ":"))

    shutil.copy2(DATA_FILE, PUBLIC_DATA / "news.json")

    audit = ROOT / "data" / "audit.json"
    if audit.exists():
        shutil.copy2(audit, PUBLIC_DATA / "audit.json")

    copy_if_exists(ROOT / "images" / "logos", PUBLIC / "images" / "logos")
    copy_if_exists(ROOT / "images" / "social.png", PUBLIC / "images" / "social.png")

    print(f"Prepared SvelteKit data: {len(feed_stories)} stories")


if __name__ == "__main__":
    main()
