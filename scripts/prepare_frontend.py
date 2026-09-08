from __future__ import annotations

import hashlib
import json
import re
import shutil
from pathlib import Path

from PIL import Image, ImageOps

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
    "hero_top_colour",
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


def local_public_path(value: object) -> Path | None:
    ref = str(value or "").strip()
    if not ref or ref.startswith(("http://", "https://")):
        return None
    if ref.startswith("/news/"):
        ref = ref[len("/news/"):]
    elif ref.startswith("/"):
        ref = ref[1:]
    if not ref:
        return None

    public_root = PUBLIC.resolve()
    candidate = (PUBLIC / ref).resolve()
    try:
        candidate.relative_to(public_root)
    except ValueError:
        return None
    return candidate if candidate.is_file() else None


def cached_hero_path(story: dict) -> Path | None:
    # Prefer the small card cache. It represents the same selected hero and is much
    # cheaper to decode when this runs across the whole feed during every build.
    for key in ("card_image_small", "card_image", "image"):
        path = local_public_path(story.get(key))
        if path is not None:
            return path
    return None


def representative_top_colour(path: Path, top_fraction: float = 0.16) -> str:
    """Return a robust average colour from the top band of an image.

    The top band is what visually touches the iOS status area. Trim the brightest
    and darkest few percent before averaging so a white logo, black letterbox, or
    tiny text overlay cannot dominate the result.
    """
    try:
        with Image.open(path) as opened:
            image = ImageOps.exif_transpose(opened).convert("RGB")
            width, height = image.size
            if width < 1 or height < 1:
                return ""
            band_height = max(1, min(height, round(height * top_fraction)))
            band = image.crop((0, 0, width, band_height))
            band.thumbnail((64, 32), Image.Resampling.LANCZOS)
            pixels = list(band.getdata())
    except Exception:
        return ""

    if not pixels:
        return ""

    def luminance(pixel: tuple[int, int, int]) -> float:
        r, g, b = pixel
        return 0.2126 * r + 0.7152 * g + 0.0722 * b

    ordered = sorted(pixels, key=luminance)
    trim = int(len(ordered) * 0.05)
    sample = ordered[trim:len(ordered) - trim] if trim and len(ordered) > trim * 2 else ordered
    if not sample:
        sample = ordered

    red = round(sum(pixel[0] for pixel in sample) / len(sample))
    green = round(sum(pixel[1] for pixel in sample) / len(sample))
    blue = round(sum(pixel[2] for pixel in sample) / len(sample))
    return f"#{red:02x}{green:02x}{blue:02x}"


def hero_top_colour(story: dict, cache: dict[str, str]) -> str:
    path = cached_hero_path(story)
    if path is None:
        return ""
    key = str(path)
    if key not in cache:
        cache[key] = representative_top_colour(path)
    return cache[key]


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
    colour_cache: dict[str, str] = {}
    coloured_stories = 0

    for story in stories:
        story_id = str(story.get("id") or "").strip()
        if not story_id:
            continue

        story_payload = dict(story)
        colour = hero_top_colour(story_payload, colour_cache)
        if colour:
            story_payload["hero_top_colour"] = colour
            coloured_stories += 1
        else:
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

    print(f"Prepared SvelteKit data: {len(feed_stories)} stories ({coloured_stories} hero status colours)")


if __name__ == "__main__":
    main()
