from __future__ import annotations

import argparse
import html
import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from bs4 import BeautifulSoup, Tag

import fetch_news


ROOT = Path(__file__).resolve().parents[1]
NEWS_PATH = ROOT / "data" / "news.json"
CTV_PHOTO_SCHEMA = 1
MAX_CTV_PHOTOS = 40
WORKERS = 6

GLOBAL_CONTENT_MARKERS = (
    "Fusion.globalContent=",
    "window.Fusion.globalContent=",
)
BODY_KEYS = {"content_elements", "contentelements"}
NESTED_PHOTO_KEYS = {
    "content_elements",
    "contentelements",
    "images",
    "photos",
    "slides",
    "items",
}
IMAGE_TYPES = {
    "image",
    "photo",
    "picture",
}
GALLERY_TYPES = {
    "gallery",
    "photo_gallery",
    "photogallery",
    "slideshow",
    "photo-slideshow",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def clean_key(value: Any) -> str:
    return str(value or "").lower().replace("-", "_").replace(" ", "")


def is_ctv_story(story: dict[str, Any]) -> bool:
    source = fetch_news.clean_text(story.get("source", "")).lower()
    if "ctv" not in source:
        return False
    path = urlparse(fetch_news.clean_text(story.get("url", ""))).path.lower()
    return any(
        marker in path
        for marker in (
            "/london/article/",
            "/canada/article/",
            "/london/photos/",
            "/canada/photos/",
        )
    )


def story_needs_work(story: dict[str, Any]) -> bool:
    if not is_ctv_story(story):
        return False
    if int(story.get("ctv_photo_schema") or 0) < CTV_PHOTO_SCHEMA:
        return True
    scraped_at = str(story.get("scraped_at") or "").strip()
    checked_for = str(story.get("ctv_photo_checked_for_scrape") or "").strip()
    return bool(scraped_at and scraped_at != checked_for)


def image_block(node: dict[str, Any], base_url: str) -> dict[str, Any] | None:
    url = fetch_news.ctv_image_url(node, base_url)
    if not url:
        return None
    width = fetch_news.int_attr(node.get("width"))
    height = fetch_news.int_attr(node.get("height"))
    block: dict[str, Any] = {
        "type": "image",
        "url": url,
        "alt": fetch_news.clean_text(
            node.get("alt_text") or node.get("alt") or node.get("subtitle") or "",
            180,
        ),
        "caption": fetch_news.clean_text(
            node.get("caption") or node.get("description") or "",
            320,
        ),
    }
    if width:
        block["width"] = width
    if height:
        block["height"] = height
    return block


def looks_like_image(node: dict[str, Any]) -> bool:
    node_type = clean_key(node.get("type"))
    if node_type in IMAGE_TYPES:
        return True
    props = node.get("additional_properties") if isinstance(node.get("additional_properties"), dict) else {}
    has_image_prop = any(props.get(key) for key in ("fullSizeResizeUrl", "resizeUrl", "proxyUrl", "originalUrl"))
    if not has_image_prop and not node.get("url"):
        return False
    return bool(
        has_image_prop
        and (
            node.get("width")
            or node.get("height")
            or node.get("caption")
            or node.get("subtitle")
            or node.get("alt_text")
        )
    )


def walk_photo_container(
    value: Any,
    base_url: str,
    found: list[dict[str, Any]],
    seen: list[str],
    depth: int = 0,
) -> None:
    if depth > 12 or len(found) >= MAX_CTV_PHOTOS:
        return
    if isinstance(value, list):
        for item in value:
            walk_photo_container(item, base_url, found, seen, depth + 1)
            if len(found) >= MAX_CTV_PHOTOS:
                return
        return
    if not isinstance(value, dict):
        return

    if looks_like_image(value):
        block = image_block(value, base_url)
        if block:
            url = str(block.get("url") or "")
            if url and not any(fetch_news.same_image(url, prior) for prior in seen):
                seen.append(url)
                found.append(block)
        return

    node_type = clean_key(value.get("type"))
    for key, child in value.items():
        normalized = clean_key(key)
        if normalized not in NESTED_PHOTO_KEYS:
            continue
        if node_type in GALLERY_TYPES or normalized in BODY_KEYS or normalized in {"images", "photos", "slides"}:
            walk_photo_container(child, base_url, found, seen, depth + 1)


def body_sequences(global_content: Any) -> list[Any]:
    if not isinstance(global_content, dict):
        return []
    sequences: list[Any] = []
    for key, value in global_content.items():
        if clean_key(key) in BODY_KEYS and isinstance(value, list):
            sequences.append(value)
    return sequences


def global_content_values(node: Any, depth: int = 0) -> list[dict[str, Any]]:
    if depth > 14:
        return []
    found: list[dict[str, Any]] = []
    if isinstance(node, list):
        for item in node:
            found.extend(global_content_values(item, depth + 1))
        return found
    if not isinstance(node, dict):
        return found

    for key, value in node.items():
        normalized = clean_key(key)
        if normalized in {"globalcontent", "global_content"} and isinstance(value, dict):
            found.append(value)
        if isinstance(value, (dict, list)):
            found.extend(global_content_values(value, depth + 1))
    return found


def decode_global_content(raw_text: str) -> list[dict[str, Any]]:
    if not raw_text:
        return []
    text = html.unescape(raw_text)
    decoder = json.JSONDecoder()
    values: list[dict[str, Any]] = []

    for marker in GLOBAL_CONTENT_MARKERS:
        cursor = 0
        while True:
            start = text.find(marker, cursor)
            if start < 0:
                break
            tail = text[start + len(marker):].lstrip()
            try:
                value, consumed = decoder.raw_decode(tail)
            except Exception:
                cursor = start + len(marker)
                continue
            if isinstance(value, dict):
                values.append(value)
            cursor = start + len(marker) + max(consumed, 1)

    try:
        parsed = json.loads(text)
    except Exception:
        parsed = None
    if parsed is not None:
        values.extend(global_content_values(parsed))
        if isinstance(parsed, dict) and body_sequences(parsed):
            values.append(parsed)

    if "__next_f.push" in text:
        for match in re.finditer(
            r'self\.__next_f\.push\(\s*\[\s*\d+\s*,\s*("(?:\\.|[^"\\])*")\s*\]\s*\)',
            text,
            flags=re.S,
        ):
            try:
                payload = json.loads(match.group(1))
            except Exception:
                continue
            values.extend(decode_global_content(payload))

    return values


def extract_ctv_photos(raw: str, base_url: str) -> list[dict[str, Any]]:
    soup = BeautifulSoup(raw, "html.parser")
    found: list[dict[str, Any]] = []
    seen: list[str] = []

    for script in soup.find_all("script"):
        if not isinstance(script, Tag):
            continue
        script_text = script.string or script.get_text("", strip=False)
        if not script_text or len(script_text) < 80:
            continue
        for global_content in decode_global_content(script_text):
            for sequence in body_sequences(global_content):
                walk_photo_container(sequence, base_url, found, seen)
                if len(found) >= MAX_CTV_PHOTOS:
                    return found

    return found


def update_existing_image(block: dict[str, Any], source_block: dict[str, Any]) -> None:
    for key in ("alt", "caption", "width", "height"):
        if not block.get(key) and source_block.get(key):
            block[key] = source_block[key]


def merge_photos(story: dict[str, Any], photos: list[dict[str, Any]]) -> bool:
    if not photos:
        return False

    changed = False
    hero = fetch_news.clean_text(story.get("image", ""))
    if not hero:
        story["image"] = str(photos[0].get("url") or "")
        hero = story["image"]
        if photos[0].get("alt"):
            story["image_alt"] = photos[0]["alt"]
        if photos[0].get("caption"):
            story["image_caption"] = photos[0]["caption"]
        changed = bool(hero)

    if hero:
        for photo in photos:
            if fetch_news.same_image(hero, str(photo.get("url") or "")):
                if not story.get("image_alt") and photo.get("alt"):
                    story["image_alt"] = photo["alt"]
                    changed = True
                if not story.get("image_caption") and photo.get("caption"):
                    story["image_caption"] = photo["caption"]
                    changed = True
                break

    blocks = story.get("content_blocks") if isinstance(story.get("content_blocks"), list) else []
    if not blocks:
        paragraphs = story.get("paragraphs") if isinstance(story.get("paragraphs"), list) else []
        if not paragraphs:
            summary = fetch_news.clean_text(story.get("summary", ""), 720)
            paragraphs = [summary] if summary else []
        blocks = [{"type": "paragraph", "text": text} for text in paragraphs if fetch_news.clean_text(text)]

    merged = [dict(block) if isinstance(block, dict) else block for block in blocks]
    for photo in photos:
        url = str(photo.get("url") or "")
        if not url or (hero and fetch_news.same_image(url, hero)):
            continue
        existing = next(
            (
                block
                for block in merged
                if isinstance(block, dict)
                and block.get("type") == "image"
                and fetch_news.same_image(url, str(block.get("url") or ""))
            ),
            None,
        )
        if isinstance(existing, dict):
            before = dict(existing)
            update_existing_image(existing, photo)
            if existing != before:
                changed = True
            continue
        merged.append(dict(photo))
        changed = True

    if merged != blocks:
        story["content_blocks"] = merged

    inline_images: list[dict[str, Any]] = []
    seen_inline: list[str] = []
    for block in merged:
        if not isinstance(block, dict) or block.get("type") != "image":
            continue
        url = str(block.get("url") or "")
        if not url or (hero and fetch_news.same_image(url, hero)):
            continue
        if any(fetch_news.same_image(url, prior) for prior in seen_inline):
            continue
        seen_inline.append(url)
        inline_images.append({
            "url": url,
            "alt": fetch_news.clean_text(block.get("alt", ""), 180),
            "caption": fetch_news.clean_text(block.get("caption", ""), 320),
            **({"width": block.get("width")} if block.get("width") else {}),
            **({"height": block.get("height")} if block.get("height") else {}),
        })

    if story.get("article_images") != inline_images:
        story["article_images"] = inline_images
        changed = True

    source_photo_count = len(photos)
    if story.get("ctv_photo_count") != source_photo_count:
        story["ctv_photo_count"] = source_photo_count
        changed = True

    if source_photo_count >= 2:
        story["article_format_state"] = "structured"
        if story.get("content_status") == "summary" and merged:
            story["content_status"] = "partial"
            quality = story.get("quality") if isinstance(story.get("quality"), dict) else {}
            if int(quality.get("score") or 0) < 45:
                story["quality"] = {**quality, "score": 55, "grade": "fair"}
            changed = True

    return changed


def process_story(story: dict[str, Any]) -> tuple[list[dict[str, Any]], str, str]:
    url = fetch_news.clean_text(story.get("url", ""))
    if not url:
        return [], "", "missing-url"
    try:
        raw, final_url = fetch_news.fetch_html(url)
    except Exception as exc:
        return [], "", f"{type(exc).__name__}: {exc}"[:240]
    return extract_ctv_photos(raw, final_url), final_url, ""


def main() -> int:
    parser = argparse.ArgumentParser(description="Recover CTV article photo galleries from publisher page state.")
    parser.add_argument("--limit", type=int, default=80)
    args = parser.parse_args()

    if not NEWS_PATH.exists():
        print("No data/news.json found")
        return 1

    payload = json.loads(NEWS_PATH.read_text(encoding="utf-8"))
    stories = payload.get("stories") if isinstance(payload.get("stories"), list) else []
    targets = [story for story in stories if isinstance(story, dict) and story_needs_work(story)]
    targets.sort(key=lambda story: str(story.get("published") or ""), reverse=True)
    targets = targets[: max(0, args.limit)]

    if not targets:
        print("CTV photo recovery already current")
        return 0

    results: dict[str, tuple[list[dict[str, Any]], str, str]] = {}
    with ThreadPoolExecutor(max_workers=min(WORKERS, max(1, len(targets)))) as pool:
        futures = {
            pool.submit(process_story, dict(story)): str(story.get("id") or story.get("url") or index)
            for index, story in enumerate(targets)
        }
        for future in as_completed(futures):
            key = futures[future]
            try:
                results[key] = future.result()
            except Exception as exc:
                results[key] = ([], "", f"{type(exc).__name__}: {exc}"[:240])

    changed_stories = 0
    galleries = 0
    recovered_images = 0
    checked = 0

    for index, story in enumerate(targets):
        key = str(story.get("id") or story.get("url") or index)
        photos, final_url, error = results.get(key, ([], "", "missing-result"))
        before = json.dumps(story, sort_keys=True, ensure_ascii=False)

        if photos:
            merge_photos(story, photos)
            if len(photos) >= 2:
                galleries += 1
                recovered_images += max(0, len(photos) - 1)

        story["ctv_photo_schema"] = CTV_PHOTO_SCHEMA
        story["ctv_photo_checked_at"] = now_iso()
        story["ctv_photo_checked_for_scrape"] = str(story.get("scraped_at") or "")
        if final_url:
            story["ctv_photo_source_url"] = fetch_news.canonical_url(final_url)
        if error:
            story["ctv_photo_error"] = error
        else:
            story.pop("ctv_photo_error", None)
        checked += 1

        after = json.dumps(story, sort_keys=True, ensure_ascii=False)
        if before != after:
            changed_stories += 1

    if changed_stories:
        payload["stories"] = stories
        NEWS_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(
        f"CTV photo recovery: {checked} checked, {galleries} photo-rich stories, "
        f"{recovered_images} inline gallery photos recovered, {changed_stories} stories updated"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
