from __future__ import annotations

import html
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests

ROOT = Path(__file__).resolve().parents[1]
NEWS_PATH = ROOT / "data" / "news.json"
CBC_ID = re.compile(r"(?<!\d)([19]\.\d{5,})(?!\d)")
MARKDOWN_CONTENT = re.compile(r"^Markdown Content:\s*$", re.I | re.M)
MARKDOWN_IMAGE = re.compile(r"!\[([^\]]*)\]\((https?://[^)]+)\)", re.I)
IMAGE_LABEL = re.compile(r"^(?:Image|Photo)\s*\|\s*(.+)$", re.I)
CAPTION_LABEL = re.compile(r"^Caption:\s*(.+)$", re.I)
HEADERS = {
    "User-Agent": "LondonNews/1.0 (+https://myplexscripts.github.io/news/)",
    "Accept": "text/plain",
    "X-Retain-Links": "text",
    "X-Retain-Images": "alt",
    "X-Retain-Media": "none",
}
IMAGE_HEADERS = {
    "User-Agent": "LondonNews/1.0 (+https://myplexscripts.github.io/news/)",
    "Accept": "text/plain",
    "X-Retain-Links": "text",
    "X-Retain-Images": "all",
    "X-Retain-Media": "none",
    "X-With-Images-Summary": "all",
}
BOILERPLATE = (
    "more from cbc",
    "more stories like this",
    "read more",
    "sign up",
    "subscribe",
    "copyright cbc",
    "all rights reserved",
    "add cbc news as a preferred source",
    "download the cbc news app",
    "go to cbc.ca",
    "cbc news homepage",
    "top stories",
    "about cbc",
    "contact cbc",
    "accessibility",
)


def clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", html.unescape(str(value or ""))).strip()


def article_id(url: str) -> str:
    matches = CBC_ID.findall(urlparse(url).path)
    return matches[-1] if matches else ""


def is_cbc_article_url(url: str) -> bool:
    parsed = urlparse(clean_text(url))
    host = parsed.netloc.lower().split(":", 1)[0]
    return (
        (host == "cbc.ca" or host == "www.cbc.ca" or host.endswith(".cbc.ca"))
        and "/news/" in parsed.path.lower()
        and bool(article_id(url))
    )


def strip_markdown(value: str) -> str:
    text = str(value or "")
    text = re.sub(r"!\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"^\s{0,3}#{1,6}\s+", "", text)
    text = re.sub(r"^\s*>\s?", "", text)
    text = re.sub(r"^\s*[-*+]\s+", "", text)
    text = re.sub(r"^\s*\d+[.)]\s+", "", text)
    text = text.replace("**", "").replace("__", "").replace("`", "")
    return clean_text(text)


def clean_image_alt(value: str) -> str:
    text = strip_markdown(value)
    text = re.sub(r"^Image\s+\d+(?:,\d+)*(?::\s*)?", "", text, flags=re.I).strip()
    if not text or re.fullmatch(r"(?:Image|Photo)(?:\s+\d+)?", text, flags=re.I):
        return ""
    return text


def paragraph_key(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", clean_text(text).lower()).strip()


def good_paragraph(text: str, title: str) -> bool:
    text = clean_text(text)
    if len(text) < 35:
        return False
    lowered = text.lower()
    title_key = clean_text(title).lower()
    if title_key and (lowered == title_key or lowered.startswith(title_key + " ")):
        return False
    if IMAGE_LABEL.match(text) or CAPTION_LABEL.match(text):
        return False
    if any(marker in lowered for marker in BOILERPLATE):
        return False
    return True


def parse_reader_units(text: str, title: str) -> list[dict[str, str]]:
    match = MARKDOWN_CONTENT.search(text)
    body = text[match.end():] if match else text
    units: list[dict[str, str]] = []
    seen_paragraphs: set[str] = set()

    for block in re.split(r"\n\s*\n+", body):
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if not lines:
            continue
        if len(lines) == 1 and re.match(r"^#{1,6}\s", lines[0]):
            continue

        joined = " ".join(lines)
        text_value = strip_markdown(joined)
        if not text_value:
            continue

        image_match = IMAGE_LABEL.match(text_value)
        if image_match:
            units.append({"type": "image_marker", "alt": clean_text(image_match.group(1))})
            continue

        caption_match = CAPTION_LABEL.match(text_value)
        if caption_match:
            units.append({"type": "caption", "text": clean_text(caption_match.group(1))})
            continue

        if MARKDOWN_IMAGE.search(joined) and re.fullmatch(r"Image(?:\s+\d+(?:,\d+)*)?(?::.*)?", text_value, flags=re.I):
            continue
        if not good_paragraph(text_value, title):
            continue

        key = paragraph_key(text_value)
        if not key or key in seen_paragraphs:
            continue
        seen_paragraphs.add(key)
        units.append({"type": "paragraph", "text": text_value})

    return units


def fetch_reader(story_id: str, title: str) -> dict[str, Any] | None:
    lite_url = f"https://www.cbc.ca/lite/story/{story_id}"
    reader_url = f"https://r.jina.ai/http://www.cbc.ca/lite/story/{story_id}"
    try:
        response = requests.get(reader_url, headers=HEADERS, timeout=(4, 24))
        status = f"{response.status_code}/{len(response.content)}B"
        if response.status_code != 200 or len(response.content) < 500:
            print(f"CBC Reader miss {story_id}: {status}", file=sys.stderr)
            return None
        units = parse_reader_units(response.text, title)
        paragraphs = [unit["text"] for unit in units if unit.get("type") == "paragraph" and unit.get("text")]
        words = sum(len(p.split()) for p in paragraphs)
        if words < 90:
            print(f"CBC Reader miss {story_id}: {status}/{words}w after cleanup", file=sys.stderr)
            return None
        return {
            "units": units,
            "paragraphs": paragraphs,
            "word_count": words,
            "lite_url": lite_url,
            "transport": "jina-reader",
        }
    except Exception as exc:
        print(f"CBC Reader miss {story_id}: {type(exc).__name__}: {exc}", file=sys.stderr)
        return None


def image_score(url: str) -> int:
    parsed = urlparse(url)
    host = parsed.netloc.lower().split(":", 1)[0]
    path = parsed.path.lower()
    lowered = url.lower()
    if any(marker in lowered for marker in ("texttospeech", "nojsimg", "logo_", "/akam/", "pixel_")):
        return -1000
    if path.endswith((".svg", ".gif")):
        return -1000

    score = 0
    if host == "i.cbc.ca":
        score += 100
    elif host.endswith(".cbc.ca"):
        score += 25
    else:
        return -1000
    if path.endswith((".jpg", ".jpeg", ".png", ".webp")):
        score += 20
    if "/ais/" in path:
        score += 15
    return score


def normalize_image_key(url: str) -> str:
    try:
        parsed = urlparse(url)
        return f"{parsed.netloc.lower()}{parsed.path.lower()}".rstrip("/")
    except Exception:
        return clean_text(url).split("?", 1)[0].lower().rstrip("/")


def fetch_images(story_url: str, story_id: str) -> list[dict[str, str]]:
    if not is_cbc_article_url(story_url):
        return []
    parsed = urlparse(story_url)
    target = f"{parsed.netloc}{parsed.path}"
    if parsed.query:
        target += f"?{parsed.query}"
    reader_url = f"https://r.jina.ai/http://{target}"
    try:
        response = requests.get(reader_url, headers=IMAGE_HEADERS, timeout=(4, 24))
        if response.status_code != 200 or len(response.content) < 500:
            print(f"CBC image miss {story_id}: {response.status_code}/{len(response.content)}B", file=sys.stderr)
            return []

        images: list[dict[str, str]] = []
        seen: set[str] = set()
        for raw_alt, raw_url in MARKDOWN_IMAGE.findall(response.text):
            image_url = html.unescape(raw_url.strip())
            if image_score(image_url) <= 0:
                continue
            key = normalize_image_key(image_url)
            if not key or key in seen:
                continue
            seen.add(key)
            images.append({"url": image_url, "alt": clean_image_alt(raw_alt)})
        if not images:
            print(f"CBC image miss {story_id}: no usable CBC image URL", file=sys.stderr)
        return images
    except Exception as exc:
        print(f"CBC image miss {story_id}: {type(exc).__name__}: {exc}", file=sys.stderr)
        return []


def has_media_junk(value: dict[str, Any]) -> bool:
    blocks = value.get("content_blocks") if isinstance(value.get("content_blocks"), list) else []
    paragraphs = value.get("paragraphs") if isinstance(value.get("paragraphs"), list) else []
    for item in [*paragraphs, *[block.get("text") for block in blocks if isinstance(block, dict)]]:
        text = clean_text(item)
        if IMAGE_LABEL.match(text) or CAPTION_LABEL.match(text):
            return True
    return False


def collect_targets(value: Any, targets: dict[str, tuple[str, str]]) -> None:
    if isinstance(value, dict):
        if value.get("source") == "CBC News London":
            url = clean_text(value.get("url"))
            story_id = article_id(url)
            title = clean_text(value.get("title"))
            needs_media = not bool(value.get("cbc_media_hydrated"))
            needs_body = value.get("content_status") != "full"
            needs_cleanup = has_media_junk(value)
            if story_id and title and is_cbc_article_url(url) and (needs_media or needs_body or needs_cleanup):
                targets.setdefault(story_id, (title, url))
        for child in value.values():
            collect_targets(child, targets)
    elif isinstance(value, list):
        for child in value:
            collect_targets(child, targets)


def merge_reader_media(body: dict[str, Any], images: list[dict[str, str]]) -> dict[str, Any]:
    units = body.get("units") if isinstance(body.get("units"), list) else []
    blocks: list[dict[str, Any]] = []
    paragraphs: list[str] = []
    image_cursor = 0
    marker_count = 0
    pending_block_index: int | None = None
    pending_hero = False
    hero: dict[str, str] | None = images[0] if images else None
    hero_caption = ""

    for unit in units:
        unit_type = unit.get("type")
        if unit_type == "paragraph":
            text = clean_text(unit.get("text"))
            if text:
                paragraphs.append(text)
                blocks.append({"type": "paragraph", "text": text})
            pending_block_index = None
            pending_hero = False
            continue

        if unit_type == "image_marker":
            marker_count += 1
            pending_block_index = None
            pending_hero = False
            image = images[image_cursor] if image_cursor < len(images) else None
            image_cursor += 1
            if not image:
                continue

            marker_alt = clean_text(unit.get("alt"))
            alt = marker_alt or clean_text(image.get("alt"))
            if marker_count == 1:
                hero = {"url": image["url"], "alt": alt}
                pending_hero = True
            else:
                block = {"type": "image", "url": image["url"], "alt": alt}
                blocks.append(block)
                pending_block_index = len(blocks) - 1
            continue

        if unit_type == "caption":
            caption = clean_text(unit.get("text"))
            if not caption:
                continue
            if pending_hero:
                hero_caption = caption
            elif pending_block_index is not None and 0 <= pending_block_index < len(blocks):
                blocks[pending_block_index]["caption"] = caption
            continue

    word_count = sum(len(p.split()) for p in paragraphs)
    inline_count = sum(1 for block in blocks if block.get("type") == "image" and block.get("url"))
    media_complete = marker_count == 0 or len(images) >= marker_count
    return {
        "paragraphs": paragraphs,
        "content_blocks": blocks,
        "content": "\n\n".join(paragraphs),
        "word_count": word_count,
        "hero": hero,
        "hero_caption": hero_caption,
        "image_blocks": inline_count,
        "marker_count": marker_count,
        "media_complete": media_complete,
        "lite_url": body.get("lite_url", ""),
        "transport": body.get("transport", "jina-reader"),
    }


def apply_results(value: Any, results: dict[str, dict[str, Any] | None]) -> tuple[int, int]:
    updated = 0
    media_complete = 0
    if isinstance(value, dict):
        if value.get("source") == "CBC News London":
            story_id = article_id(clean_text(value.get("url")))
            result = results.get(story_id)
            if result and result.get("word_count", 0) >= 90:
                value["paragraphs"] = result["paragraphs"]
                value["content_blocks"] = result["content_blocks"]
                value["content"] = result["content"]
                value["word_count"] = result["word_count"]
                value["content_status"] = "full"
                value["ingestion_path"] = "cbc-google-news-lite-reader"
                value["scraped_at"] = datetime.now(timezone.utc).isoformat()
                value["cbc_lite_url"] = result["lite_url"]
                value["body_transport"] = result["transport"]

                hero = result.get("hero") or {}
                if hero.get("url"):
                    value["image"] = hero["url"]
                    if hero.get("alt"):
                        value["image_alt"] = hero["alt"]
                if result.get("hero_caption"):
                    value["image_caption"] = result["hero_caption"]

                value["cbc_media_hydrated"] = bool(result.get("media_complete"))
                quality = value.get("quality") if isinstance(value.get("quality"), dict) else {}
                quality.update({
                    "score": max(75, int(quality.get("score") or 0)),
                    "grade": "good",
                    "method": "reader:cbc:lite",
                    "text_blocks": len(result["paragraphs"]),
                    "rich_blocks": int(result.get("image_blocks") or 0),
                    "image_blocks": int(result.get("image_blocks") or 0),
                })
                value["quality"] = quality
                updated += 1
                if result.get("media_complete"):
                    media_complete += 1

        for child in list(value.values()):
            child_updated, child_complete = apply_results(child, results)
            updated += child_updated
            media_complete += child_complete
    elif isinstance(value, list):
        for child in value:
            child_updated, child_complete = apply_results(child, results)
            updated += child_updated
            media_complete += child_complete
    return updated, media_complete


def main() -> int:
    if not NEWS_PATH.exists():
        return 0

    payload = json.loads(NEWS_PATH.read_text(encoding="utf-8"))
    targets: dict[str, tuple[str, str]] = {}
    collect_targets(payload, targets)
    if not targets:
        print("CBC media hydration: nothing to update")
        return 0

    bodies: dict[str, dict[str, Any] | None] = {}
    images: dict[str, list[dict[str, str]]] = {}

    with ThreadPoolExecutor(max_workers=min(4, len(targets))) as executor:
        futures = {
            executor.submit(fetch_reader, story_id, title): story_id
            for story_id, (title, _) in targets.items()
        }
        for future in as_completed(futures):
            story_id = futures[future]
            try:
                bodies[story_id] = future.result()
            except Exception as exc:
                print(f"CBC Reader worker failed {story_id}: {exc}", file=sys.stderr)
                bodies[story_id] = None

    with ThreadPoolExecutor(max_workers=min(4, len(targets))) as executor:
        futures = {
            executor.submit(fetch_images, url, story_id): story_id
            for story_id, (_, url) in targets.items()
        }
        for future in as_completed(futures):
            story_id = futures[future]
            try:
                images[story_id] = future.result()
            except Exception as exc:
                print(f"CBC image worker failed {story_id}: {exc}", file=sys.stderr)
                images[story_id] = []

    results: dict[str, dict[str, Any] | None] = {}
    for story_id in targets:
        body = bodies.get(story_id)
        results[story_id] = merge_reader_media(body, images.get(story_id, [])) if body else None

    updated, complete = apply_results(payload, results)
    if updated:
        NEWS_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    inline_images = sum(
        int(result.get("image_blocks") or 0)
        for result in results.values()
        if isinstance(result, dict)
    )
    print(
        f"CBC media hydration: {updated} record(s) cleaned/hydrated across {len(targets)} unique stories; "
        f"{complete} record(s) fully matched to CBC media; {inline_images} inline image block(s) preserved"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
