from __future__ import annotations

import argparse
import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import fetch_news
import hydrate_cbc_lite


ROOT = Path(__file__).resolve().parents[1]
NEWS_PATH = ROOT / "data" / "news.json"
CBC_READER_SCHEMA = 2

NATIONAL_POST_PROMOS = tuple(
    fetch_news.boilerplate_key(value)
    for value in (
        "Enjoy the latest local, national and international news.",
        "Access articles from across Canada with one account.",
        "Enjoy additional articles per month.",
        "Create an account or sign in to continue with your reading experience.",
        "Sign in or create an account.",
        "Unlock more articles.",
        "Manage print subscription.",
    )
)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def word_count(value: Any) -> int:
    return len(re.findall(r"\b\w+[’'-]?\w*\b", str(value or "")))


def national_post_promo(value: Any) -> bool:
    key = fetch_news.boilerplate_key(str(value or ""))
    if not key:
        return False
    return any(marker and marker in key for marker in NATIONAL_POST_PROMOS)


def repair_national_post_story(story: dict[str, Any]) -> bool:
    if str(story.get("source") or "") != "National Post":
        return False

    changed = False
    title = fetch_news.clean_text(story.get("title", ""))
    lead_image = fetch_news.clean_text(story.get("image", ""))
    blocks = story.get("content_blocks") if isinstance(story.get("content_blocks"), list) else []

    if blocks:
        cleaned_blocks: list[dict[str, Any]] = []
        for block in blocks:
            if not isinstance(block, dict):
                continue
            kind = str(block.get("type") or "")
            if kind in {"paragraph", "heading", "quote"}:
                if national_post_promo(block.get("text")):
                    changed = True
                    continue
                cleaned_blocks.append(block)
                continue
            if kind == "list":
                raw_items = block.get("items") if isinstance(block.get("items"), list) else []
                items = [item for item in raw_items if not national_post_promo(item)]
                if len(items) != len(raw_items):
                    changed = True
                if items:
                    cleaned_blocks.append({**block, "items": items})
                elif raw_items:
                    changed = True
                continue
            cleaned_blocks.append(block)

        cleaned_blocks = fetch_news.sanitize_content_blocks(cleaned_blocks, "National Post", title, lead_image)
        if cleaned_blocks != blocks:
            story["content_blocks"] = cleaned_blocks
            changed = True
        paragraphs, text = fetch_news.text_from_blocks(cleaned_blocks)
    else:
        raw_paragraphs = story.get("paragraphs") if isinstance(story.get("paragraphs"), list) else []
        paragraphs = [
            fetch_news.clean_text(value)
            for value in raw_paragraphs
            if fetch_news.clean_text(value) and not national_post_promo(value)
        ]
        text = "\n\n".join(paragraphs)
        if paragraphs != raw_paragraphs:
            story["paragraphs"] = paragraphs
            story["content_blocks"] = fetch_news.fallback_blocks(paragraphs, story.get("article_images") or [])
            changed = True

    if national_post_promo(story.get("summary")):
        story["summary"] = fetch_news.clean_text(paragraphs[0], 360) if paragraphs else ""
        changed = True

    old_content = str(story.get("content") or "")
    old_paragraphs = story.get("paragraphs") if isinstance(story.get("paragraphs"), list) else []
    if text != old_content or paragraphs != old_paragraphs:
        story["paragraphs"] = paragraphs
        story["content"] = text
        story["word_count"] = word_count(text)
        changed = True

    if changed:
        method = str((story.get("quality") or {}).get("method") or "sanitized:national-post")
        story["quality"] = fetch_news.extraction_quality(story, {}, method)
        story["national_post_promo_cleaned_at"] = now_iso()
    return changed


def local_cbc_cache(value: str) -> bool:
    normalized = str(value or "").strip().replace("\\", "/")
    if normalized.startswith("https://myplexscripts.github.io/news/"):
        normalized = normalized[len("https://myplexscripts.github.io/news/"):]
    normalized = normalized.lstrip("/")
    if normalized.startswith("news/"):
        normalized = normalized[len("news/"):]
    return normalized.startswith("cache/cbc/")


def remote_cbc_image(value: str) -> bool:
    try:
        parsed = urlparse(str(value or "").strip())
        host = parsed.netloc.lower().split(":", 1)[0]
        if parsed.scheme not in {"http", "https"}:
            return False
        return host == "i.cbc.ca" or host == "cbc.ca" or host == "www.cbc.ca" or host.endswith(".cbc.ca")
    except Exception:
        return False


def safe_cbc_image(value: Any) -> bool:
    src = str(value or "").strip()
    if not src:
        return False
    return remote_cbc_image(src) or local_cbc_cache(src)


def strip_non_cbc_images(story: dict[str, Any]) -> tuple[bool, bool]:
    changed = False
    removed_bad_hero = False

    for key in ("image", "card_image"):
        src = str(story.get(key) or "").strip()
        if src and not safe_cbc_image(src):
            story[key] = ""
            changed = True
            if key == "image":
                removed_bad_hero = True

    blocks = story.get("content_blocks") if isinstance(story.get("content_blocks"), list) else []
    if blocks:
        cleaned_blocks: list[Any] = []
        for block in blocks:
            if not isinstance(block, dict) or block.get("type") != "image":
                cleaned_blocks.append(block)
                continue
            if safe_cbc_image(block.get("url")):
                cleaned_blocks.append(block)
            else:
                changed = True
        if cleaned_blocks != blocks:
            story["content_blocks"] = cleaned_blocks

    article_images = story.get("article_images") if isinstance(story.get("article_images"), list) else []
    if article_images:
        cleaned_images = [
            image for image in article_images
            if isinstance(image, dict) and safe_cbc_image(image.get("url"))
        ]
        if cleaned_images != article_images:
            story["article_images"] = cleaned_images
            changed = True

    if changed:
        story["cbc_images_cached"] = bool(
            local_cbc_cache(str(story.get("image") or ""))
            or local_cbc_cache(str(story.get("card_image") or ""))
        )
        if removed_bad_hero:
            story["cbc_media_hydrated"] = False
    return changed, removed_bad_hero


def cbc_story_needs_reader(story: dict[str, Any], bad_hero_removed: bool = False) -> bool:
    if str(story.get("source") or "") != "CBC News London":
        return False
    url = fetch_news.clean_text(story.get("url", ""))
    if not hydrate_cbc_lite.is_cbc_article_url(url):
        return False
    if int(story.get("cbc_reader_repair_schema") or 0) < CBC_READER_SCHEMA:
        return True
    if bad_hero_removed or not safe_cbc_image(story.get("image")):
        return True
    paragraphs = story.get("paragraphs") if isinstance(story.get("paragraphs"), list) else []
    if story.get("content_status") != "full" or len(paragraphs) < 2:
        return True
    if int(story.get("word_count") or 0) < 90:
        return True
    return False


def fetch_cbc_reader_result(story: dict[str, Any]) -> tuple[dict[str, Any] | None, list[dict[str, str]]]:
    url = fetch_news.clean_text(story.get("url", ""))
    title = fetch_news.clean_text(story.get("title", ""))
    story_id = hydrate_cbc_lite.article_id(url)
    if not story_id or not title:
        return None, []
    body = hydrate_cbc_lite.fetch_reader(story_id, title)
    images = hydrate_cbc_lite.fetch_images(url, story_id)
    return body, images


def should_apply_reader(story: dict[str, Any], result: dict[str, Any]) -> bool:
    reader_words = int(result.get("word_count") or 0)
    if reader_words < 90:
        return False
    existing_words = int(story.get("word_count") or 0)
    if existing_words <= 0:
        existing_words = word_count(story.get("content", ""))
    paragraphs = story.get("paragraphs") if isinstance(story.get("paragraphs"), list) else []
    if story.get("content_status") != "full" or existing_words < 90 or len(paragraphs) < 2:
        return True
    if reader_words >= existing_words + 35:
        return True
    if reader_words >= int(existing_words * 1.08):
        return True
    if str(story.get("body_transport") or "") != "jina-reader" and reader_words >= int(existing_words * 0.94):
        return True
    return False


def apply_cbc_reader_result(
    story: dict[str, Any],
    body: dict[str, Any] | None,
    images: list[dict[str, str]],
) -> bool:
    changed = False

    if images:
        hero = images[0]
        hero_url = str(hero.get("url") or "").strip()
        if safe_cbc_image(hero_url) and (
            not safe_cbc_image(story.get("image"))
            or str(story.get("image") or "") != hero_url
        ):
            story["image"] = hero_url
            story["card_image"] = ""
            if hero.get("alt"):
                story["image_alt"] = fetch_news.clean_text(hero.get("alt"), 180)
            story["cbc_images_cached"] = False
            changed = True

    if body and int(body.get("word_count") or 0) >= 90:
        merged = hydrate_cbc_lite.merge_reader_media(body, images)
        if should_apply_reader(story, merged):
            story["paragraphs"] = merged["paragraphs"]
            story["content_blocks"] = merged["content_blocks"]
            story["content"] = merged["content"]
            story["word_count"] = merged["word_count"]
            story["content_status"] = "full"
            story["body_transport"] = merged.get("transport", "jina-reader")
            story["cbc_lite_url"] = merged.get("lite_url", "")
            story["ingestion_path"] = "cbc-lite-reader-repair"

            hero = merged.get("hero") or {}
            hero_url = str(hero.get("url") or "").strip()
            if safe_cbc_image(hero_url):
                story["image"] = hero_url
                story["card_image"] = ""
                story["cbc_images_cached"] = False
                if hero.get("alt"):
                    story["image_alt"] = fetch_news.clean_text(hero.get("alt"), 180)
            if merged.get("hero_caption"):
                story["image_caption"] = fetch_news.clean_text(merged.get("hero_caption"), 320)

            story["cbc_media_hydrated"] = bool(merged.get("media_complete"))
            quality = story.get("quality") if isinstance(story.get("quality"), dict) else {}
            quality.update({
                "score": max(80, int(quality.get("score") or 0)),
                "grade": "good",
                "method": "reader:cbc:lite-repair",
                "text_blocks": len(merged["paragraphs"]),
                "rich_blocks": int(merged.get("image_blocks") or 0),
                "image_blocks": int(merged.get("image_blocks") or 0),
            })
            story["quality"] = quality
            for key in (
                "structure_schema",
                "structure_method",
                "structure_status",
                "structure_richness",
                "structured_at",
                "structure_attempted_at",
            ):
                story.pop(key, None)
            changed = True

        story["cbc_reader_repair_schema"] = CBC_READER_SCHEMA
        story["cbc_reader_checked_at"] = now_iso()

    if changed:
        story["scraped_at"] = now_iso()
    return changed


def repair_payload(payload: dict[str, Any], cbc_limit: int = 20) -> tuple[int, int, int, int]:
    stories = payload.get("stories") if isinstance(payload.get("stories"), list) else []
    national_post_cleaned = 0
    cbc_images_cleaned = 0
    cbc_reader_attempted = 0
    cbc_reader_updated = 0

    for story in stories:
        if not isinstance(story, dict):
            continue
        if repair_national_post_story(story):
            national_post_cleaned += 1

    targets: list[dict[str, Any]] = []
    for story in stories:
        if not isinstance(story, dict) or str(story.get("source") or "") != "CBC News London":
            continue
        changed, bad_hero_removed = strip_non_cbc_images(story)
        if changed:
            cbc_images_cleaned += 1
        if cbc_story_needs_reader(story, bad_hero_removed):
            targets.append(story)

    targets.sort(key=lambda story: str(story.get("published") or ""), reverse=True)
    if cbc_limit <= 0:
        targets = []
    else:
        targets = targets[:cbc_limit]

    if targets:
        with ThreadPoolExecutor(max_workers=min(4, len(targets))) as executor:
            futures = {executor.submit(fetch_cbc_reader_result, story): story for story in targets}
            for future in as_completed(futures):
                story = futures[future]
                cbc_reader_attempted += 1
                try:
                    body, images = future.result()
                except Exception as exc:
                    story["cbc_reader_repair_error"] = str(exc)[:240]
                    story["cbc_reader_checked_at"] = now_iso()
                    continue
                if apply_cbc_reader_result(story, body, images):
                    cbc_reader_updated += 1

    payload["source_content_repair_at"] = now_iso()
    payload["cbc_reader_repair_schema"] = CBC_READER_SCHEMA
    return national_post_cleaned, cbc_images_cleaned, cbc_reader_attempted, cbc_reader_updated


def main() -> int:
    parser = argparse.ArgumentParser(description="Clean National Post subscription promos and harden CBC reader bodies/media")
    parser.add_argument("--cbc-limit", type=int, default=20)
    args = parser.parse_args()

    if not NEWS_PATH.exists():
        return 0

    payload = json.loads(NEWS_PATH.read_text(encoding="utf-8"))
    np_cleaned, cbc_images, attempted, updated = repair_payload(payload, max(0, args.cbc_limit))
    NEWS_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        f"Source content repair: {np_cleaned} National Post record(s) cleaned, "
        f"{cbc_images} CBC record(s) stripped of non-CBC images, "
        f"{updated}/{attempted} CBC reader record(s) improved"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
