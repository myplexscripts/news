from __future__ import annotations

import hashlib
import html
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests

ROOT = Path(__file__).resolve().parents[1]
NEWS_PATH = ROOT / "data" / "news.json"
CACHE_DIR = ROOT / "public" / "cache" / "cbc"
PUBLIC_ROOT = "https://myplexscripts.github.io/news/"
PUBLIC_CACHE_ROOT = f"{PUBLIC_ROOT}cache/cbc/"
USER_AGENT = "LondonNews/1.0 (+https://myplexscripts.github.io/news/)"


def clean_text(value: Any) -> str:
    return html.unescape(str(value or "")).strip()


def is_remote_cbc_image(url: str) -> bool:
    try:
        parsed = urlparse(clean_text(url))
        host = parsed.netloc.lower().split(":", 1)[0]
        return parsed.scheme in {"http", "https"} and (
            host == "i.cbc.ca"
            or host == "cbc.ca"
            or host == "www.cbc.ca"
            or host.endswith(".cbc.ca")
        )
    except Exception:
        return False


def image_key(url: str) -> str:
    parsed = urlparse(url)
    stable = f"{parsed.netloc.lower()}{parsed.path}"
    return hashlib.sha256(stable.encode("utf-8")).hexdigest()[:20]


def sniff_extension(data: bytes) -> str:
    if data.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp"
    if len(data) >= 12 and data[4:12] in {b"ftypavif", b"ftypavis"}:
        return ".avif"
    return ""


def fetch_bytes_with_curl(url: str) -> bytes:
    command = [
        "curl",
        "--location",
        "--fail",
        "--silent",
        "--show-error",
        "--connect-timeout",
        "5",
        "--max-time",
        "25",
        "--user-agent",
        USER_AGENT,
        "--header",
        "Referer: https://www.cbc.ca/",
        "--header",
        "Accept: image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
        url,
    ]
    result = subprocess.run(command, capture_output=True, check=False, timeout=30)
    if result.returncode == 0 and len(result.stdout) >= 1000:
        return result.stdout
    return b""


def fetch_bytes_with_requests(url: str) -> bytes:
    try:
        response = requests.get(
            url,
            headers={
                "User-Agent": USER_AGENT,
                "Referer": "https://www.cbc.ca/",
                "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
            },
            timeout=(5, 25),
            allow_redirects=True,
        )
        if response.status_code == 200 and len(response.content) >= 1000:
            return response.content
    except Exception:
        pass
    return b""


def cache_image(url: str) -> str:
    if not is_remote_cbc_image(url):
        return ""

    key = image_key(url)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    for ext in (".jpg", ".png", ".webp", ".avif"):
        existing = CACHE_DIR / f"cbc-{key}{ext}"
        if existing.exists() and existing.stat().st_size >= 1000:
            return f"{PUBLIC_CACHE_ROOT}{existing.name}"

    data = fetch_bytes_with_curl(url)
    if not data:
        data = fetch_bytes_with_requests(url)
    if not data:
        print(f"CBC image cache miss: could not download {url}", file=sys.stderr)
        return ""

    ext = sniff_extension(data)
    if not ext:
        print(f"CBC image cache miss: unsupported image bytes for {url}", file=sys.stderr)
        return ""

    target = CACHE_DIR / f"cbc-{key}{ext}"
    target.write_bytes(data)
    return f"{PUBLIC_CACHE_ROOT}{target.name}"


def collect_urls(value: Any, urls: set[str]) -> None:
    if isinstance(value, dict):
        if value.get("source") == "CBC News London":
            hero = clean_text(value.get("image"))
            if is_remote_cbc_image(hero):
                urls.add(hero)
            blocks = value.get("content_blocks")
            if isinstance(blocks, list):
                for block in blocks:
                    if not isinstance(block, dict) or block.get("type") != "image":
                        continue
                    image_url = clean_text(block.get("url"))
                    if is_remote_cbc_image(image_url):
                        urls.add(image_url)
        for child in value.values():
            collect_urls(child, urls)
    elif isinstance(value, list):
        for child in value:
            collect_urls(child, urls)


def card_image_url(value: dict[str, Any]) -> str:
    card = clean_text(value.get("card_image"))
    if not card:
        return ""
    if card.startswith("http://") or card.startswith("https://"):
        return card
    return f"{PUBLIC_ROOT}{card.lstrip('/')}"


def rewrite_records(value: Any, cached: dict[str, str]) -> tuple[int, int, int]:
    records_updated = 0
    images_rewritten = 0
    images_removed = 0

    if isinstance(value, dict):
        if value.get("source") == "CBC News London":
            changed = False
            hero = clean_text(value.get("image"))
            if is_remote_cbc_image(hero):
                replacement = cached.get(hero, "")
                if replacement:
                    value["image"] = replacement
                    images_rewritten += 1
                    changed = True
                else:
                    fallback = card_image_url(value)
                    if fallback:
                        value["image"] = fallback
                        images_rewritten += 1
                        changed = True

            blocks = value.get("content_blocks")
            if isinstance(blocks, list):
                rewritten_blocks: list[Any] = []
                for block in blocks:
                    if not isinstance(block, dict) or block.get("type") != "image":
                        rewritten_blocks.append(block)
                        continue
                    image_url = clean_text(block.get("url"))
                    if not is_remote_cbc_image(image_url):
                        rewritten_blocks.append(block)
                        continue
                    replacement = cached.get(image_url, "")
                    if replacement:
                        block["url"] = replacement
                        rewritten_blocks.append(block)
                        images_rewritten += 1
                        changed = True
                    else:
                        images_removed += 1
                        changed = True
                if rewritten_blocks != blocks:
                    value["content_blocks"] = rewritten_blocks

            remaining_remote = is_remote_cbc_image(clean_text(value.get("image")))
            current_blocks = value.get("content_blocks") if isinstance(value.get("content_blocks"), list) else []
            remaining_remote = remaining_remote or any(
                isinstance(block, dict)
                and block.get("type") == "image"
                and is_remote_cbc_image(clean_text(block.get("url")))
                for block in current_blocks
            )
            cache_state = not remaining_remote
            if bool(value.get("cbc_images_cached")) != cache_state:
                value["cbc_images_cached"] = cache_state
                changed = True

            quality = value.get("quality") if isinstance(value.get("quality"), dict) else None
            if quality is not None:
                inline_count = sum(
                    1
                    for block in current_blocks
                    if isinstance(block, dict) and block.get("type") == "image" and clean_text(block.get("url"))
                )
                if int(quality.get("image_blocks") or 0) != inline_count:
                    quality["image_blocks"] = inline_count
                    quality["rich_blocks"] = inline_count
                    changed = True

            if changed:
                records_updated += 1

        for child in list(value.values()):
            child_records, child_rewritten, child_removed = rewrite_records(child, cached)
            records_updated += child_records
            images_rewritten += child_rewritten
            images_removed += child_removed

    elif isinstance(value, list):
        for child in value:
            child_records, child_rewritten, child_removed = rewrite_records(child, cached)
            records_updated += child_records
            images_rewritten += child_rewritten
            images_removed += child_removed

    return records_updated, images_rewritten, images_removed


def main() -> int:
    if not NEWS_PATH.exists():
        return 0

    payload = json.loads(NEWS_PATH.read_text(encoding="utf-8"))
    urls: set[str] = set()
    collect_urls(payload, urls)

    cached: dict[str, str] = {}
    if urls:
        with ThreadPoolExecutor(max_workers=min(6, len(urls))) as executor:
            futures = {executor.submit(cache_image, url): url for url in sorted(urls)}
            for future in as_completed(futures):
                url = futures[future]
                try:
                    cached[url] = future.result()
                except Exception as exc:
                    print(f"CBC image cache worker failed: {type(exc).__name__}: {exc}", file=sys.stderr)
                    cached[url] = ""

    records_updated, images_rewritten, images_removed = rewrite_records(payload, cached)
    if records_updated:
        NEWS_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    cached_count = sum(1 for value in cached.values() if value)
    failed_count = len(urls) - cached_count
    print(
        f"CBC image cache: {cached_count}/{len(urls)} remote image(s) cached; "
        f"{images_rewritten} image reference(s) rewritten across {records_updated} record(s); "
        f"{images_removed} broken inline image block(s) removed; {failed_count} download(s) failed"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
