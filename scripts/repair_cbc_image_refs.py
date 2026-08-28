from __future__ import annotations

import html
import json
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests

ROOT = Path(__file__).resolve().parents[1]
NEWS_PATH = ROOT / "data" / "news.json"
PUBLIC_DIR = ROOT / "public"
PUBLIC_ROOT = "https://myplexscripts.github.io/news/"
USER_AGENT = "LondonNews/1.0 (+https://myplexscripts.github.io/news/)"
MARKDOWN_IMAGE = re.compile(r"!\[([^\]]*)\]\((https?://[^)]+)\)", re.I)
HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/plain",
    "X-Retain-Links": "text",
    "X-Retain-Images": "all",
    "X-Retain-Media": "none",
    "X-With-Images-Summary": "all",
}


def clean_text(value: Any) -> str:
    return html.unescape(str(value or "")).strip()


def is_remote(value: Any) -> bool:
    try:
        return urlparse(clean_text(value)).scheme in {"http", "https"}
    except Exception:
        return False


def local_public_path(value: Any) -> Path | None:
    src = clean_text(value)
    if not src or is_remote(src):
        return None

    if src.startswith(PUBLIC_ROOT):
        src = src[len(PUBLIC_ROOT):]
    if src.startswith("/news/"):
        src = src[len("/news/"):]
    src = src.lstrip("/")
    if not src.startswith("cache/"):
        return None
    return PUBLIC_DIR / src


def valid_local_ref(value: Any) -> bool:
    path = local_public_path(value)
    return bool(path and path.exists() and path.is_file() and path.stat().st_size >= 1000)


def is_cbc_article(value: Any) -> bool:
    try:
        parsed = urlparse(clean_text(value))
        host = parsed.netloc.lower().split(":", 1)[0]
        return (
            parsed.scheme in {"http", "https"}
            and (host == "cbc.ca" or host == "www.cbc.ca" or host.endswith(".cbc.ca"))
            and "/news/" in parsed.path.lower()
        )
    except Exception:
        return False


def image_score(url: str) -> int:
    try:
        parsed = urlparse(url)
    except Exception:
        return -1000
    host = parsed.netloc.lower().split(":", 1)[0]
    path = parsed.path.lower()
    lowered = url.lower()
    if host != "i.cbc.ca":
        return -1000
    if path.endswith((".svg", ".gif")):
        return -1000
    if any(marker in lowered for marker in ("texttospeech", "nojsimg", "logo_", "/akam/", "pixel_", "favicon")):
        return -1000

    score = 100
    if path.endswith((".jpg", ".jpeg", ".png", ".webp", ".avif")):
        score += 20
    if "/ais/" in path:
        score += 15
    if "resize%3d76" in lowered or "resize=76" in lowered:
        score -= 80
    return score


def discover_hero(story_url: str) -> str:
    if not is_cbc_article(story_url):
        return ""
    parsed = urlparse(story_url)
    target = f"{parsed.netloc}{parsed.path}"
    if parsed.query:
        target += f"?{parsed.query}"
    reader_url = f"https://r.jina.ai/http://{target}"

    try:
        response = requests.get(reader_url, headers=HEADERS, timeout=(4, 24))
        if response.status_code != 200 or len(response.content) < 500:
            return ""
        candidates: list[tuple[int, str]] = []
        seen: set[str] = set()
        for _, raw_url in MARKDOWN_IMAGE.findall(response.text):
            image_url = html.unescape(raw_url.strip())
            score = image_score(image_url)
            if score <= 0:
                continue
            parsed_image = urlparse(image_url)
            key = f"{parsed_image.netloc.lower()}{parsed_image.path.lower()}"
            if key in seen:
                continue
            seen.add(key)
            candidates.append((score, image_url))
        if not candidates:
            return ""
        candidates.sort(key=lambda item: item[0], reverse=True)
        return candidates[0][1]
    except Exception as exc:
        print(f"CBC image reference discovery miss: {type(exc).__name__}: {exc}", file=sys.stderr)
        return ""


def collect_records(value: Any, records: list[dict[str, Any]]) -> None:
    if isinstance(value, dict):
        if value.get("source") == "CBC News London" and (value.get("title") or value.get("url")):
            records.append(value)
        for child in value.values():
            collect_records(child, records)
    elif isinstance(value, list):
        for child in value:
            collect_records(child, records)


def repair_record(record: dict[str, Any]) -> tuple[bool, bool, int]:
    changed = False
    rediscovered = False
    removed_blocks = 0

    for key in ("image", "card_image"):
        value = clean_text(record.get(key))
        if value and not is_remote(value) and not valid_local_ref(value):
            record[key] = ""
            changed = True

    blocks = record.get("content_blocks")
    if isinstance(blocks, list):
        cleaned_blocks: list[Any] = []
        for block in blocks:
            if not isinstance(block, dict) or block.get("type") != "image":
                cleaned_blocks.append(block)
                continue
            url = clean_text(block.get("url"))
            if url and not is_remote(url) and not valid_local_ref(url):
                removed_blocks += 1
                changed = True
                continue
            cleaned_blocks.append(block)
        if cleaned_blocks != blocks:
            record["content_blocks"] = cleaned_blocks

    image = clean_text(record.get("image"))
    card = clean_text(record.get("card_image"))

    # A valid local card is a safe fallback when the hero reference vanished.
    if not image and card and valid_local_ref(card):
        record["image"] = card
        image = card
        changed = True

    if not image:
        discovered = discover_hero(clean_text(record.get("url")))
        if discovered:
            record["image"] = discovered
            record["card_image"] = card if valid_local_ref(card) else ""
            record["cbc_image_hotlink"] = True
            record["cbc_images_cached"] = False
            rediscovered = True
            changed = True
            image = discovered

    # Never claim the image is cached unless the referenced local file exists.
    image_is_valid_local = bool(image and not is_remote(image) and valid_local_ref(image))
    card_is_valid_local = bool(card and not is_remote(card) and valid_local_ref(card))
    has_remote = is_remote(image) or is_remote(card)
    cache_state = (image_is_valid_local or card_is_valid_local) and not has_remote
    if bool(record.get("cbc_images_cached")) != cache_state:
        record["cbc_images_cached"] = cache_state
        changed = True

    if image_is_valid_local and record.get("cbc_image_hotlink"):
        record["cbc_image_hotlink"] = False
        changed = True

    return changed, rediscovered, removed_blocks


def main() -> int:
    if not NEWS_PATH.exists():
        return 0

    payload = json.loads(NEWS_PATH.read_text(encoding="utf-8"))
    records: list[dict[str, Any]] = []
    collect_records(payload, records)

    updated = 0
    rediscovered = 0
    removed_blocks = 0
    missing_after = 0

    for record in records:
        changed, found, removed = repair_record(record)
        updated += int(changed)
        rediscovered += int(found)
        removed_blocks += removed
        if not clean_text(record.get("image")):
            missing_after += 1

    if updated:
        NEWS_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(
        f"CBC image reference repair: {updated}/{len(records)} record(s) updated, "
        f"{rediscovered} hero(s) rediscovered, {removed_blocks} stale inline image(s) removed, "
        f"{missing_after} record(s) still without a hero"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
