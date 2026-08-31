from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from io import BytesIO
from typing import Any

import fetch_news
import run_scoop


_original_enrich_article = fetch_news.enrich_article


def _has_reader_body(story: dict[str, Any]) -> bool:
    paragraphs = story.get("paragraphs")
    blocks = story.get("content_blocks")
    return bool(
        (isinstance(paragraphs, list) and any(str(item or "").strip() for item in paragraphs))
        or (isinstance(blocks, list) and len(blocks) > 0)
        or str(story.get("content") or "").strip()
    )


def _metadata_first_enrich(story: dict[str, Any], source: fetch_news.Source) -> dict[str, Any]:
    """Publish useful feed metadata without blocking on full article extraction.

    First-party page sources still need their article page opened to discover a title,
    summary and hero image, so those fall through to the normal extractor. Google
    News discovery also needs the normal extractor to resolve its redirect.
    """
    title = str(story.get("title") or "").strip()
    url = str(story.get("url") or "").strip()

    if source.kind == "google_topic" or not title or not url:
        enriched = _original_enrich_article(story, source)
        enriched["refresh_stage"] = "enriched"
        enriched["enriched_at"] = datetime.now(timezone.utc).isoformat()
        return enriched

    if _has_reader_body(story):
        story["refresh_stage"] = "enriched"
        return story

    now = datetime.now(timezone.utc).isoformat()
    story.setdefault("paragraphs", [])
    story.setdefault("content_blocks", [])
    story.setdefault("content", "")
    story["content_status"] = "summary"
    story["word_count"] = int(story.get("word_count") or len(str(story.get("summary") or "").split()))
    story["scraped_at"] = str(story.get("scraped_at") or now)
    story["discovered_at"] = str(story.get("discovered_at") or now)
    story["refresh_stage"] = "metadata"
    story["extraction_schema"] = fetch_news.EXTRACTION_SCHEMA
    story["quality"] = fetch_news.extraction_quality(story, {}, "fast:feed-metadata")
    return story


def _skip_backfill(stories, skip_sources=None):
    """Full article backfill belongs to the deferred enrichment workflow."""
    return stories


def _cache_news_filename(value: Any) -> str:
    """Return a cache/news filename from a stored public path or URL."""
    text = fetch_news.clean_text(value)
    if not text:
        return ""
    marker = "cache/news/"
    index = text.find(marker)
    if index < 0:
        return ""
    tail = text[index + len(marker):].split("?", 1)[0].split("#", 1)[0].strip("/")
    if not tail or "/" in tail or not tail.lower().endswith(".webp"):
        return ""
    return tail


def _local_public_asset(value: Any) -> str:
    """Return a repo-local public path when the referenced asset exists."""
    text = fetch_news.clean_text(value)
    if not text or text.startswith(("http://", "https://")):
        return ""

    normalized = text
    if normalized.startswith("/news/"):
        normalized = normalized[len("/news/"):]
    elif normalized.startswith("/"):
        normalized = normalized[1:]

    if not normalized.startswith("cache/"):
        return ""
    target = fetch_news.ROOT / "public" / normalized
    return normalized if target.exists() and target.is_file() else ""


def _repair_card_references(stories: list[dict[str, Any]]) -> None:
    """Remove dangling thumbnails and prefer an existing local hero when available."""
    for story in stories:
        for key in ("card_image", "card_image_small"):
            filename = _cache_news_filename(story.get(key))
            if filename and not (fetch_news.CARD_IMAGE_DIR / filename).exists():
                story.pop(key, None)

        local_hero = _local_public_asset(story.get("image"))
        if local_hero and not fetch_news.clean_text(story.get("card_image")):
            story["card_image"] = local_hero


def _safe_cache_card_images(stories: list[dict[str, Any]], limit: int = 140) -> list[dict[str, Any]]:
    """Cache card art without deleting files that are still referenced by stories.

    The original cleanup builds its keep-set only from remote images processed in
    the current run. Deferred enrichment can turn a story's hero into a local asset,
    leaving its previously generated card thumbnail referenced in news.json but no
    longer counted by that keep-set. This version derives cleanup from the final
    story references instead, preventing published cards from pointing at deleted
    files.
    """
    fetch_news.CARD_IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    _repair_card_references(stories)

    done = 0
    for story in sorted(stories, key=lambda item: item.get("published", ""), reverse=True):
        if done >= limit:
            break

        image_url = fetch_news.clean_text(story.get("image"))
        if not image_url or not image_url.startswith(("http://", "https://")):
            continue

        stem = hashlib.sha1(image_url.encode("utf-8", "ignore")).hexdigest()[:20]
        filename = stem + ".webp"
        small_filename = stem + "-sm.webp"
        target = fetch_news.CARD_IMAGE_DIR / filename
        small_target = fetch_news.CARD_IMAGE_DIR / small_filename
        relative = f"cache/news/{filename}"
        small_relative = f"cache/news/{small_filename}"

        if not target.exists():
            try:
                response = fetch_news.SESSION.get(image_url, timeout=12)
                response.raise_for_status()
                image = fetch_news.Image.open(BytesIO(response.content)).convert("RGB")
                width, height = image.size
                if min(width, height) < 160:
                    continue
                focus_x = float(story.get("image_focus_x") or 50) / 100.0
                focus_y = float(story.get("image_focus_y") or 50) / 100.0
                side = min(width, height)
                center_x = max(side / 2, min(width - side / 2, width * focus_x))
                center_y = max(side / 2, min(height - side / 2, height * focus_y))
                left = int(center_x - side / 2)
                top = int(center_y - side / 2)
                image = image.crop((left, top, left + side, top + side))
                image.thumbnail((720, 720), fetch_news.Image.Resampling.LANCZOS)
                image.save(target, "WEBP", quality=82, method=6)
            except Exception:
                # Keep any older valid card reference. The UI also has a source-image
                # fallback, so a publisher outage must not turn into a broken icon.
                continue

        if target.exists() and not small_target.exists():
            try:
                small_image = fetch_news.Image.open(target).convert("RGB")
                small_image.thumbnail((420, 420), fetch_news.Image.Resampling.LANCZOS)
                small_image.save(small_target, "WEBP", quality=76, method=6)
            except Exception:
                pass

        if target.exists():
            story["card_image"] = relative
            if small_target.exists():
                story["card_image_small"] = small_relative
            else:
                story.pop("card_image_small", None)
            done += 1

    _repair_card_references(stories)

    # Cleanup is based on what the finished feed actually references, not what the
    # current network run happened to download.
    wanted: set[str] = set()
    for story in stories:
        for key in ("card_image", "card_image_small"):
            filename = _cache_news_filename(story.get(key))
            if filename:
                wanted.add(filename)

    for path in fetch_news.CARD_IMAGE_DIR.glob("*.webp"):
        if path.name not in wanted:
            try:
                path.unlink()
            except OSError:
                pass

    return stories


def main() -> int:
    fetch_news.enrich_article = _metadata_first_enrich
    fetch_news.backfill_missing = _skip_backfill
    fetch_news.cache_card_images = _safe_cache_card_images
    return run_scoop.main()


if __name__ == "__main__":
    raise SystemExit(main())
