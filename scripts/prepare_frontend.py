from __future__ import annotations

import hashlib
import json
import re
import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed
from io import BytesIO
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

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

HEX_COLOUR = re.compile(r"^#[0-9a-f]{6}$", re.I)
REMOTE_SAMPLE_LIMIT = 6 * 1024 * 1024
REMOTE_SAMPLE_WORKERS = 12
STATUS_MIN_LUMINANCE = 42.0
STATUS_MAX_LUMINANCE = 218.0


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
    for key in ("card_image_small", "card_image", "image"):
        path = local_public_path(story.get(key))
        if path is not None:
            return path
    return None


def remote_hero_url(story: dict) -> str:
    for key in ("card_image_small", "card_image", "image"):
        value = str(story.get(key) or "").strip()
        if value.startswith(("http://", "https://")):
            return value
    return ""


def pixel_luminance(pixel: tuple[int, int, int]) -> float:
    r, g, b = pixel
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def colour_luminance(colour: str) -> float:
    if not HEX_COLOUR.fullmatch(str(colour or "")):
        return -1.0
    value = colour.lstrip("#")
    return pixel_luminance(tuple(int(value[index:index + 2], 16) for index in (0, 2, 4)))


def status_colour_allowed(colour: str) -> bool:
    luminance = colour_luminance(colour)
    return STATUS_MIN_LUMINANCE <= luminance <= STATUS_MAX_LUMINANCE


def constrain_status_pixel(pixel: tuple[int, int, int]) -> tuple[int, int, int]:
    luminance = pixel_luminance(pixel)
    if STATUS_MIN_LUMINANCE <= luminance <= STATUS_MAX_LUMINANCE:
        return pixel

    if luminance < STATUS_MIN_LUMINANCE:
        denominator = max(1.0, 255.0 - luminance)
        amount = min(1.0, (STATUS_MIN_LUMINANCE - luminance) / denominator)
        return tuple(round(channel + (255 - channel) * amount) for channel in pixel)

    scale = STATUS_MAX_LUMINANCE / max(1.0, luminance)
    return tuple(max(0, min(255, round(channel * scale))) for channel in pixel)


def _representative_top_colour(opened: Image.Image, top_fraction: float = 0.16) -> str:
    image = ImageOps.exif_transpose(opened).convert("RGB")
    width, height = image.size
    if width < 1 or height < 1:
        return ""

    band_height = max(1, min(height, round(height * top_fraction)))
    band = image.crop((0, 0, width, band_height))
    band.thumbnail((64, 32), Image.Resampling.LANCZOS)
    pixels = list(band.getdata())
    if not pixels:
        return ""

    # Do not let white logos, black wordmarks, letterboxing, or very bright/dark
    # image edges become the status-strip colour. Prefer the meaningful mid-range
    # pixels from the top band instead.
    eligible = [
        pixel for pixel in pixels
        if STATUS_MIN_LUMINANCE <= pixel_luminance(pixel) <= STATUS_MAX_LUMINANCE
    ]
    sample_source = eligible if eligible else pixels
    ordered = sorted(sample_source, key=pixel_luminance)
    trim = int(len(ordered) * 0.05)
    sample = ordered[trim:len(ordered) - trim] if trim and len(ordered) > trim * 2 else ordered
    if not sample:
        sample = ordered

    averaged = (
        round(sum(pixel[0] for pixel in sample) / len(sample)),
        round(sum(pixel[1] for pixel in sample) / len(sample)),
        round(sum(pixel[2] for pixel in sample) / len(sample)),
    )
    red, green, blue = constrain_status_pixel(averaged)
    return f"#{red:02x}{green:02x}{blue:02x}"


def representative_top_colour(path: Path, top_fraction: float = 0.16) -> str:
    try:
        with Image.open(path) as opened:
            return _representative_top_colour(opened, top_fraction)
    except Exception:
        return ""


def representative_top_colour_bytes(payload: bytes, top_fraction: float = 0.16) -> str:
    if not payload:
        return ""
    try:
        with Image.open(BytesIO(payload)) as opened:
            return _representative_top_colour(opened, top_fraction)
    except Exception:
        return ""


def representative_top_colour_url(url: str, timeout: float = 6.0) -> str:
    if not str(url or "").startswith(("http://", "https://")):
        return ""

    parsed = urlparse(url)
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) "
            "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1"
        ),
        "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
    }
    if parsed.scheme and parsed.netloc:
        headers["Referer"] = f"{parsed.scheme}://{parsed.netloc}/"

    try:
        request = Request(url, headers=headers)
        with urlopen(request, timeout=timeout) as response:
            content_type = str(response.headers.get("Content-Type") or "").lower()
            if content_type and "image/" not in content_type:
                return ""
            payload = response.read(REMOTE_SAMPLE_LIMIT + 1)
    except Exception:
        return ""

    if len(payload) > REMOTE_SAMPLE_LIMIT:
        return ""
    return representative_top_colour_bytes(payload)


def existing_story_colour(story: dict) -> str:
    colour = str(story.get("hero_top_colour") or "").strip().lower()
    return colour if HEX_COLOUR.fullmatch(colour) and status_colour_allowed(colour) else ""


def build_remote_colour_cache(stories: list[dict]) -> dict[str, str]:
    urls = {
        remote_hero_url(story)
        for story in stories
        if not existing_story_colour(story)
        and cached_hero_path(story) is None
        and remote_hero_url(story)
    }
    if not urls:
        return {}

    colours: dict[str, str] = {}
    workers = min(REMOTE_SAMPLE_WORKERS, len(urls))
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(representative_top_colour_url, url): url for url in urls}
        for future in as_completed(futures):
            url = futures[future]
            try:
                colour = future.result()
            except Exception:
                colour = ""
            if colour:
                colours[url] = colour
    return colours


def hero_top_colour(story: dict, local_cache: dict[str, str], remote_cache: dict[str, str]) -> str:
    existing = existing_story_colour(story)
    if existing:
        return existing

    path = cached_hero_path(story)
    if path is not None:
        key = str(path)
        if key not in local_cache:
            local_cache[key] = representative_top_colour(path)
        return local_cache[key]

    url = remote_hero_url(story)
    return remote_cache.get(url, "") if url else ""


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
    local_colour_cache: dict[str, str] = {}
    remote_colour_cache = build_remote_colour_cache(stories)
    coloured_stories = 0
    remote_coloured_stories = 0

    for story in stories:
        story_id = str(story.get("id") or "").strip()
        if not story_id:
            continue

        story_payload = dict(story)
        had_existing = bool(existing_story_colour(story_payload))
        local_path = cached_hero_path(story_payload)
        colour = hero_top_colour(story_payload, local_colour_cache, remote_colour_cache)
        if colour:
            story_payload["hero_top_colour"] = colour
            coloured_stories += 1
            if not had_existing and local_path is None:
                remote_coloured_stories += 1
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

    print(
        f"Prepared SvelteKit data: {len(feed_stories)} stories "
        f"({coloured_stories} hero status colours, {remote_coloured_stories} sampled remotely)"
    )


if __name__ == "__main__":
    main()
