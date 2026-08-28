from __future__ import annotations

import hashlib
import html
import json
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlparse

import requests

ROOT = Path(__file__).resolve().parents[1]
NEWS_PATH = ROOT / "data" / "news.json"
CACHE_DIR = ROOT / "public" / "cache" / "cbc"
PUBLIC_ROOT = "https://myplexscripts.github.io/news/"
CACHE_REL_ROOT = "cache/cbc/"
USER_AGENT = "LondonNews/1.0 (+https://myplexscripts.github.io/news/)"
MARKDOWN_IMAGE = re.compile(r"!\[([^\]]*)\]\((https?://[^)]+)\)", re.I)
READER_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/plain",
    "X-Retain-Links": "text",
    "X-Retain-Images": "all",
    "X-Retain-Media": "none",
    "X-With-Images-Summary": "all",
}


def clean_text(value: Any) -> str:
    return html.unescape(str(value or "")).strip()


def is_remote_url(url: str) -> bool:
    try:
        return urlparse(clean_text(url)).scheme in {"http", "https"}
    except Exception:
        return False


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


def is_cbc_article_url(url: str) -> bool:
    try:
        parsed = urlparse(clean_text(url))
        host = parsed.netloc.lower().split(":", 1)[0]
        return (
            parsed.scheme in {"http", "https"}
            and (host == "cbc.ca" or host == "www.cbc.ca" or host.endswith(".cbc.ca"))
            and "/news/" in parsed.path.lower()
        )
    except Exception:
        return False


def normalize_local_image(value: Any) -> str:
    src = clean_text(value)
    if not src:
        return ""

    public_cache = f"{PUBLIC_ROOT}{CACHE_REL_ROOT}"
    if src.startswith(public_cache):
        return f"{CACHE_REL_ROOT}{src[len(public_cache):].lstrip('/')}"

    for prefix in ("/news/", "/"):
        candidate = src[len(prefix):] if src.startswith(prefix) else ""
        if candidate.startswith("cache/"):
            return candidate

    return src


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
        "4",
        "--max-time",
        "12",
        "--user-agent",
        USER_AGENT,
        "--header",
        "Referer: https://www.cbc.ca/",
        "--header",
        "Accept: image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
        url,
    ]
    try:
        result = subprocess.run(command, capture_output=True, check=False, timeout=15)
    except Exception:
        return b""
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
            timeout=(4, 12),
            allow_redirects=True,
        )
        if response.status_code == 200 and len(response.content) >= 1000:
            return response.content
    except Exception:
        pass
    return b""


def fetch_bytes_via_proxy(url: str) -> bytes:
    # GitHub-hosted runners intermittently cannot reach CBC's image CDN. wsrv.nl
    # fetches the origin image from a different network, then this workflow saves
    # the returned bytes into our own GitHub Pages cache. The live site never
    # depends on the proxy URL.
    proxy_url = f"https://wsrv.nl/?url={quote(url, safe='')}"
    try:
        response = requests.get(
            proxy_url,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
            },
            timeout=(5, 20),
            allow_redirects=True,
        )
        if response.status_code == 200 and len(response.content) >= 1000:
            return response.content
        print(
            f"CBC image proxy miss: HTTP {response.status_code} for {url}",
            file=sys.stderr,
        )
    except Exception as exc:
        print(f"CBC image proxy miss: {type(exc).__name__} for {url}", file=sys.stderr)
    return b""


def cache_image(url: str) -> str:
    if not is_remote_cbc_image(url):
        return ""

    key = image_key(url)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    for ext in (".jpg", ".png", ".webp", ".avif"):
        existing = CACHE_DIR / f"cbc-{key}{ext}"
        if existing.exists() and existing.stat().st_size >= 1000:
            return f"{CACHE_REL_ROOT}{existing.name}"

    # Try the cache proxy first because CBC's image CDN is the path known to
    # stall on GitHub-hosted runners. Direct fetches remain as fallbacks.
    data = fetch_bytes_via_proxy(url)
    if not data:
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
    return f"{CACHE_REL_ROOT}{target.name}"


def image_score(url: str) -> int:
    try:
        parsed = urlparse(url)
    except Exception:
        return -1000
    host = parsed.netloc.lower().split(":", 1)[0]
    path = parsed.path.lower()
    lowered = url.lower()
    if any(marker in lowered for marker in ("texttospeech", "nojsimg", "logo_", "/akam/", "pixel_", "favicon")):
        return -1000
    if path.endswith((".svg", ".gif")):
        return -1000

    score = 0
    if host == "i.cbc.ca":
        score += 100
    elif host.endswith(".cbc.ca") or host == "cbc.ca":
        score += 25
    else:
        return -1000
    if path.endswith((".jpg", ".jpeg", ".png", ".webp", ".avif")):
        score += 20
    if "/ais/" in path:
        score += 15
    return score


def discover_cbc_hero(story_url: str) -> str:
    if not is_cbc_article_url(story_url):
        return ""

    parsed = urlparse(story_url)
    target = f"{parsed.netloc}{parsed.path}"
    if parsed.query:
        target += f"?{parsed.query}"
    reader_url = f"https://r.jina.ai/http://{target}"

    try:
        response = requests.get(reader_url, headers=READER_HEADERS, timeout=(4, 24))
        if response.status_code != 200 or len(response.content) < 500:
            return ""
        candidates: list[tuple[int, str]] = []
        seen: set[str] = set()
        for _, raw_url in MARKDOWN_IMAGE.findall(response.text):
            image_url = html.unescape(raw_url.strip())
            score = image_score(image_url)
            if score <= 0:
                continue
            key = f"{urlparse(image_url).netloc.lower()}{urlparse(image_url).path.lower()}"
            if key in seen:
                continue
            seen.add(key)
            candidates.append((score, image_url))
        if not candidates:
            return ""
        candidates.sort(key=lambda item: item[0], reverse=True)
        return candidates[0][1]
    except Exception as exc:
        print(f"CBC hero discovery miss: {type(exc).__name__}: {exc}", file=sys.stderr)
        return ""


def collect_cbc_records(value: Any, records: list[dict[str, Any]]) -> None:
    if isinstance(value, dict):
        if value.get("source") == "CBC News London" and (value.get("title") or value.get("url")):
            records.append(value)
        for child in value.values():
            collect_cbc_records(child, records)
    elif isinstance(value, list):
        for child in value:
            collect_cbc_records(child, records)


def remote_image_urls(record: dict[str, Any]) -> set[str]:
    urls: set[str] = set()
    for key in ("image", "card_image"):
        url = clean_text(record.get(key))
        if is_remote_cbc_image(url):
            urls.add(url)

    blocks = record.get("content_blocks")
    if isinstance(blocks, list):
        for block in blocks:
            if not isinstance(block, dict) or block.get("type") != "image":
                continue
            url = clean_text(block.get("url"))
            if is_remote_cbc_image(url):
                urls.add(url)
    return urls


def usable_hero(record: dict[str, Any]) -> str:
    card = normalize_local_image(record.get("card_image"))
    image = normalize_local_image(record.get("image"))
    return card or image


def prepare_record(record: dict[str, Any]) -> bool:
    changed = False
    image = normalize_local_image(record.get("image"))
    card = normalize_local_image(record.get("card_image"))

    if image != clean_text(record.get("image")):
        record["image"] = image
        changed = True
    if card != clean_text(record.get("card_image")):
        record["card_image"] = card
        changed = True

    if not image and card:
        record["image"] = card
        image = card
        changed = True
    if not card and image and not is_remote_url(image):
        record["card_image"] = image
        changed = True

    return changed


def rewrite_record(record: dict[str, Any], cached: dict[str, str], discovered: str = "") -> tuple[bool, int, int]:
    changed = prepare_record(record)
    rewritten = 0
    removed = 0

    image = clean_text(record.get("image"))
    card = clean_text(record.get("card_image"))

    if is_remote_cbc_image(image):
        replacement = cached.get(image, "")
        if replacement:
            record["image"] = replacement
            record["card_image"] = replacement
            image = replacement
            card = replacement
            rewritten += 1
            changed = True

    if is_remote_cbc_image(card):
        replacement = cached.get(card, "")
        if replacement:
            record["card_image"] = replacement
            if not clean_text(record.get("image")) or is_remote_cbc_image(clean_text(record.get("image"))):
                record["image"] = replacement
            image = clean_text(record.get("image"))
            card = replacement
            rewritten += 1
            changed = True
        elif is_remote_cbc_image(image):
            # Avoid the homepage treating an absolute card URL as a local path.
            record["card_image"] = ""
            card = ""
            changed = True

    if not usable_hero(record) and discovered:
        replacement = cached.get(discovered, "")
        if replacement:
            record["image"] = replacement
            record["card_image"] = replacement
            image = replacement
            card = replacement
            rewritten += 1
            changed = True

    blocks = record.get("content_blocks")
    if isinstance(blocks, list):
        rewritten_blocks: list[Any] = []
        for block in blocks:
            if not isinstance(block, dict) or block.get("type") != "image":
                rewritten_blocks.append(block)
                continue
            image_url = clean_text(block.get("url"))
            if not is_remote_cbc_image(image_url):
                if image_url:
                    normalized = normalize_local_image(image_url)
                    if normalized != image_url:
                        block["url"] = normalized
                        changed = True
                rewritten_blocks.append(block)
                continue
            replacement = cached.get(image_url, "")
            if replacement:
                block["url"] = replacement
                rewritten_blocks.append(block)
                rewritten += 1
                changed = True
            else:
                removed += 1
                changed = True
        if rewritten_blocks != blocks:
            record["content_blocks"] = rewritten_blocks

    # One final synchronization pass after cache/discovery rewrites.
    if prepare_record(record):
        changed = True

    remaining_remote = bool(remote_image_urls(record))
    has_hero = bool(usable_hero(record))
    cache_state = has_hero and not remaining_remote
    if bool(record.get("cbc_images_cached")) != cache_state:
        record["cbc_images_cached"] = cache_state
        changed = True

    quality = record.get("quality") if isinstance(record.get("quality"), dict) else None
    if quality is not None:
        current_blocks = record.get("content_blocks") if isinstance(record.get("content_blocks"), list) else []
        inline_count = sum(
            1
            for block in current_blocks
            if isinstance(block, dict) and block.get("type") == "image" and clean_text(block.get("url"))
        )
        if int(quality.get("image_blocks") or 0) != inline_count:
            quality["image_blocks"] = inline_count
            quality["rich_blocks"] = inline_count
            changed = True

    return changed, rewritten, removed


def main() -> int:
    if not NEWS_PATH.exists():
        return 0

    payload = json.loads(NEWS_PATH.read_text(encoding="utf-8"))
    records: list[dict[str, Any]] = []
    collect_cbc_records(payload, records)

    prechanged = 0
    for record in records:
        if prepare_record(record):
            prechanged += 1

    discovery_targets: list[dict[str, Any]] = []
    for record in records:
        if usable_hero(record):
            continue
        story_url = clean_text(record.get("url"))
        if is_cbc_article_url(story_url):
            discovery_targets.append(record)

    discovered_by_record: dict[int, str] = {}
    if discovery_targets:
        with ThreadPoolExecutor(max_workers=min(4, len(discovery_targets))) as executor:
            futures = {
                executor.submit(discover_cbc_hero, clean_text(record.get("url"))): record
                for record in discovery_targets
            }
            for future in as_completed(futures):
                record = futures[future]
                try:
                    discovered_by_record[id(record)] = future.result()
                except Exception as exc:
                    print(f"CBC hero discovery worker failed: {type(exc).__name__}: {exc}", file=sys.stderr)
                    discovered_by_record[id(record)] = ""

    urls: set[str] = set()
    for record in records:
        urls.update(remote_image_urls(record))
        discovered = discovered_by_record.get(id(record), "")
        if is_remote_cbc_image(discovered):
            urls.add(discovered)

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

    records_updated = prechanged
    images_rewritten = 0
    images_removed = 0
    for record in records:
        changed, rewritten, removed = rewrite_record(
            record,
            cached,
            discovered_by_record.get(id(record), ""),
        )
        if changed:
            records_updated += 1
        images_rewritten += rewritten
        images_removed += removed

    # A record can be touched in both preparation and rewrite; report unique changed records approximately,
    # but always write whenever either phase changed anything.
    if records_updated:
        NEWS_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    cached_count = sum(1 for value in cached.values() if value)
    failed_count = len(urls) - cached_count
    discovered_count = sum(1 for value in discovered_by_record.values() if value)
    hero_count = sum(1 for record in records if usable_hero(record))
    print(
        f"CBC image cache: {cached_count}/{len(urls)} remote image(s) cached; "
        f"{discovered_count}/{len(discovery_targets)} missing hero(s) rediscovered; "
        f"{hero_count}/{len(records)} CBC record(s) now have a hero; "
        f"{images_rewritten} image reference(s) rewritten; "
        f"{images_removed} broken inline image block(s) removed; {failed_count} download(s) failed"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
