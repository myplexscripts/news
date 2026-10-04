from __future__ import annotations

"""Cache article editorial images as high quality, size efficient WebP files.

Original publisher URLs remain in the feed. Optimized local paths are stored in
separate fields so scraper and repair passes can continue using source media.
"""

import hashlib
import io
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests
from PIL import Image, ImageOps, UnidentifiedImageError
from image_assets import attach_cached_images

ROOT = Path(__file__).resolve().parents[1]
NEWS_PATH = ROOT / "data" / "news.json"
CACHE_DIR = ROOT / "public" / "cache" / "editorial"
MAX_DIMENSION = max(1600, int(os.getenv("EDITORIAL_IMAGE_MAX_DIMENSION", "2400")))
WEBP_QUALITY = max(82, min(92, int(os.getenv("EDITORIAL_IMAGE_WEBP_QUALITY", "86"))))
MAX_STORIES = max(8, int(os.getenv("EDITORIAL_IMAGE_STORIES", "36")))
MAX_IMAGES_PER_STORY = max(2, int(os.getenv("EDITORIAL_IMAGES_PER_STORY", "20")))
MAX_UNIQUE_IMAGES = max(24, int(os.getenv("EDITORIAL_IMAGE_LIMIT", "160")))
MAX_DOWNLOAD_BYTES = max(2_000_000, int(os.getenv("EDITORIAL_IMAGE_MAX_DOWNLOAD_BYTES", "18000000")))
TIME_BUDGET = max(30, int(os.getenv("EDITORIAL_IMAGE_TIME_BUDGET", "240")))
WORKERS = max(2, min(8, int(os.getenv("EDITORIAL_IMAGE_WORKERS", "6"))))
CACHE_VERSION = "v2"
USER_AGENT = "ForestCityNews/2.0 (+https://myplexscripts.github.io/news/)"


def is_remote_image(value: Any) -> bool:
    raw = str(value or "").strip()
    if not raw:
        return False
    parsed = urlparse(raw)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def published_timestamp(story: dict[str, Any]) -> float:
    raw = str(story.get("cluster_latest_published") or story.get("published") or "").strip().replace("Z", "+00:00")
    if not raw:
        return 0.0
    try:
        return datetime.fromisoformat(raw).timestamp()
    except Exception:
        return 0.0


def cache_path_for(url: str) -> Path:
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:24]
    return CACHE_DIR / f"{CACHE_VERSION}-{digest}.webp"


def public_path(path: Path) -> str:
    return path.relative_to(ROOT / "public").as_posix()


def read_response_bytes(response: requests.Response) -> bytes:
    declared = response.headers.get("content-length")
    if declared:
        try:
            if int(declared) > MAX_DOWNLOAD_BYTES:
                raise ValueError("image exceeds download limit")
        except ValueError as exc:
            if str(exc) == "image exceeds download limit":
                raise

    chunks: list[bytes] = []
    total = 0
    deadline = time.monotonic() + 24
    for chunk in response.iter_content(chunk_size=64 * 1024):
        if time.monotonic() > deadline:
            raise ValueError("image download exceeded time budget")
        if not chunk:
            continue
        total += len(chunk)
        if total > MAX_DOWNLOAD_BYTES:
            raise ValueError("image exceeds download limit")
        chunks.append(chunk)
    return b"".join(chunks)


def encode_webp(source_bytes: bytes) -> tuple[bytes, int, int]:
    with Image.open(io.BytesIO(source_bytes)) as opened:
        image = ImageOps.exif_transpose(opened)
        image.load()
        if image.width < 80 or image.height < 80:
            raise ValueError("image is too small")

        has_alpha = image.mode in {"RGBA", "LA"} or "transparency" in image.info
        image = image.convert("RGBA" if has_alpha else "RGB")
        image.thumbnail((MAX_DIMENSION, MAX_DIMENSION), Image.Resampling.LANCZOS)

        output = io.BytesIO()
        image.save(
            output,
            "WEBP",
            quality=WEBP_QUALITY,
            method=6,
            exact=has_alpha,
        )
        return output.getvalue(), image.width, image.height


def optimize_url(url: str) -> tuple[str, int, int] | None:
    target = cache_path_for(url)
    if target.exists() and target.stat().st_size > 0:
        try:
            with Image.open(target) as cached:
                return public_path(target), int(cached.width), int(cached.height)
        except Exception:
            target.unlink(missing_ok=True)

    try:
        with requests.get(
            url,
            headers={"User-Agent": USER_AGENT, "Accept": "image/avif,image/webp,image/*,*/*;q=0.8"},
            timeout=(5, 12),
            stream=True,
        ) as response:
            response.raise_for_status()
            content_type = str(response.headers.get("content-type") or "").lower()
            if content_type and not content_type.startswith("image/"):
                return None
            source_bytes = read_response_bytes(response)

        if not source_bytes:
            return None
        optimized, width, height = encode_webp(source_bytes)

        # Keep the publisher file when it is already smaller. Re-encoding should
        # only be selected when it actually reduces transfer size.

        target.parent.mkdir(parents=True, exist_ok=True)
        temp = target.with_suffix(".tmp")
        temp.write_bytes(optimized)
        temp.replace(target)
        return public_path(target), width, height
    except (requests.RequestException, OSError, ValueError, UnidentifiedImageError):
        return None


def selected_stories(payload: dict[str, Any]) -> list[dict[str, Any]]:
    stories = [story for story in payload.get("stories") or [] if isinstance(story, dict)]
    stories.sort(key=lambda story: (str(story.get("image_optimization_checked_at") or ""), -published_timestamp(story)))
    # Process stories that do not yet have the current high-resolution cache.
    # Older v1 files remain readable as fallbacks, but they should not prevent a
    # v2 refresh from upgrading a full-viewport editorial cover.
    pending = [
        story for story in stories
        if any(not cache_path_for(url).is_file() for url in collect_targets([story]))
    ]
    return pending[:MAX_STORIES]


def collect_targets(stories: list[dict[str, Any]]) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()

    for story in stories:
        candidates: list[str] = []
        hero = str(story.get("image") or "").strip()
        if is_remote_image(hero):
            candidates.append(hero)

        block_count = 0
        for block in story.get("content_blocks") or []:
            if not isinstance(block, dict) or block.get("type") != "image":
                continue
            url = str(block.get("url") or "").strip()
            if not is_remote_image(url):
                continue
            candidates.append(url)
            block_count += 1
            if block_count >= MAX_IMAGES_PER_STORY:
                break

        for url in candidates:
            if url in seen:
                continue
            seen.add(url)
            ordered.append(url)
            if len(ordered) >= MAX_UNIQUE_IMAGES:
                return ordered

    return ordered


def apply_result(container: dict[str, Any], source_key: str, output_key: str, result: tuple[str, int, int] | None) -> bool:
    source = str(container.get(source_key) or "").strip()
    if not source:
        return False

    source_field = f"{output_key}_source"
    width_field = f"{output_key}_width"
    height_field = f"{output_key}_height"

    if result is None:
        changed = False
        for key in (output_key, source_field, width_field, height_field):
            if key in container:
                container.pop(key, None)
                changed = True
        return changed

    path, width, height = result
    desired = {
        output_key: path,
        source_field: source,
        width_field: width,
        height_field: height,
    }
    changed = any(container.get(key) != value for key, value in desired.items())
    container.update(desired)
    return changed


def optimize_payload(payload: dict[str, Any]) -> tuple[int, int, int]:
    attach_cached_images(payload.get("stories") or [])
    stories = selected_stories(payload)
    targets = collect_targets(stories)
    if not targets:
        return 0, 0, 0

    results: dict[str, tuple[str, int, int] | None] = {}
    deadline = time.monotonic() + TIME_BUDGET
    # Submit only one worker batch at a time so a slow publisher cannot leave
    # hundreds of queued downloads running after the maintenance budget expires.
    with ThreadPoolExecutor(max_workers=WORKERS) as executor:
        for offset in range(0, len(targets), WORKERS):
            if time.monotonic() >= deadline:
                break
            futures = {executor.submit(optimize_url, url): url for url in targets[offset:offset + WORKERS]}
            for future in as_completed(futures):
                url = futures[future]
                try:
                    results[url] = future.result()
                except Exception:
                    results[url] = None

    changed_stories = 0
    optimized_refs = 0
    for story in stories:
        changed = False
        if any(url in results for url in collect_targets([story])):
            story["image_optimization_checked_at"] = datetime.now().isoformat()
        hero = str(story.get("image") or "").strip()
        if hero in results:
            result = results[hero]
            changed |= apply_result(story, "image", "editorial_image", result)
            if result:
                optimized_refs += 1

        for block in story.get("content_blocks") or []:
            if not isinstance(block, dict) or block.get("type") != "image":
                continue
            url = str(block.get("url") or "").strip()
            if url not in results:
                continue
            result = results[url]
            changed |= apply_result(block, "url", "optimized_url", result)
            if result:
                optimized_refs += 1

        if changed:
            changed_stories += 1

    attach_cached_images(stories)
    payload["editorial_image_schema"] = 2
    return changed_stories, len(results), optimized_refs


def main() -> int:
    if not NEWS_PATH.exists():
        print("No data/news.json found")
        return 0

    payload = json.loads(NEWS_PATH.read_text(encoding="utf-8"))
    changed_stories, attempted, optimized_refs = optimize_payload(payload)
    payload["editorial_image_schema"] = 2
    NEWS_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        f"Editorial image optimization: {optimized_refs}/{attempted} references optimized "
        f"across {changed_stories} changed stories"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
