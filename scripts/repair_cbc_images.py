from __future__ import annotations

import html
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any
from urllib.parse import urlparse

import requests

import cache_cbc_images as cbc


CBC_SOURCE_PREFIX = "cbc news"
CBC_STORY_ID = re.compile(r"(?<!\d)(\d+\.\d+)(?!\d)")


def clean(value: Any) -> str:
    return cbc.clean_text(value)


def is_cbc_record(record: dict[str, Any]) -> bool:
    source = clean(record.get("source")).lower()
    url = clean(record.get("url"))
    return source.startswith(CBC_SOURCE_PREFIX) or cbc.is_cbc_article_url(url)


def collect_records(value: Any, records: list[dict[str, Any]], seen: set[int]) -> None:
    if isinstance(value, dict):
        if is_cbc_record(value) and (value.get("title") or value.get("url")):
            marker = id(value)
            if marker not in seen:
                seen.add(marker)
                records.append(value)
        for child in value.values():
            collect_records(child, records, seen)
    elif isinstance(value, list):
        for child in value:
            collect_records(child, records, seen)


def promote_existing_hero(record: dict[str, Any]) -> bool:
    """Promote any useful CBC image already present in the record to card hero."""
    if cbc.usable_hero(record):
        return False

    candidates: list[str] = []
    for key in ("lead_image", "hero_image", "og_image", "twitter_image"):
        value = clean(record.get(key))
        if value:
            candidates.append(value)

    blocks = record.get("content_blocks")
    if isinstance(blocks, list):
        for block in blocks:
            if not isinstance(block, dict) or block.get("type") != "image":
                continue
            value = clean(block.get("url"))
            if value:
                candidates.append(value)

    for candidate in candidates:
        normalized = cbc.normalize_local_image(candidate)
        if normalized and (cbc.is_remote_cbc_image(normalized) or not cbc.is_remote_url(normalized)):
            record["image"] = normalized
            record["card_image"] = normalized if not cbc.is_remote_url(normalized) else ""
            return True
    return False


def reader_image_candidates(story_url: str) -> list[str]:
    parsed = urlparse(story_url)
    if parsed.scheme not in {"http", "https"}:
        return []
    host = parsed.netloc.lower().split(":", 1)[0]
    if host != "cbc.ca" and host != "www.cbc.ca" and not host.endswith(".cbc.ca"):
        return []

    target = f"{parsed.netloc}{parsed.path}"
    if parsed.query:
        target += f"?{parsed.query}"
    reader_url = f"https://r.jina.ai/http://{target}"

    try:
        response = requests.get(reader_url, headers=cbc.READER_HEADERS, timeout=(4, 22))
        if response.status_code != 200 or len(response.content) < 400:
            return []
    except Exception:
        return []

    scored: list[tuple[int, str]] = []
    seen: set[str] = set()
    for _, raw_url in cbc.MARKDOWN_IMAGE.findall(response.text):
        image_url = html.unescape(raw_url.strip())
        score = cbc.image_score(image_url)
        if score <= 0:
            continue
        key = f"{urlparse(image_url).netloc.lower()}{urlparse(image_url).path.lower()}"
        if key in seen:
            continue
        seen.add(key)
        scored.append((score, image_url))

    # Jina occasionally emits a bare CBC image URL instead of Markdown image syntax.
    for raw_url in re.findall(r"https?://i\.cbc\.ca/[^\s)\]>\"']+", response.text, flags=re.I):
        image_url = html.unescape(raw_url.strip())
        score = cbc.image_score(image_url)
        if score <= 0:
            continue
        key = f"{urlparse(image_url).netloc.lower()}{urlparse(image_url).path.lower()}"
        if key in seen:
            continue
        seen.add(key)
        scored.append((score, image_url))

    scored.sort(key=lambda item: item[0], reverse=True)
    return [url for _, url in scored]


def discover_hero(record: dict[str, Any]) -> str:
    story_url = clean(record.get("url"))
    if not story_url:
        return ""

    candidates = reader_image_candidates(story_url)
    if candidates:
        return candidates[0]

    match = CBC_STORY_ID.search(story_url)
    if match:
        lite_url = f"https://www.cbc.ca/lite/story/{match.group(1)}"
        candidates = reader_image_candidates(lite_url)
        if candidates:
            return candidates[0]

    return ""


def main() -> int:
    if not cbc.NEWS_PATH.exists():
        return 0

    payload = json.loads(cbc.NEWS_PATH.read_text(encoding="utf-8"))
    records: list[dict[str, Any]] = []
    collect_records(payload, records, set())

    prechanged = 0
    for record in records:
        if cbc.prepare_record(record):
            prechanged += 1
        if promote_existing_hero(record):
            prechanged += 1

    discovery_targets = [
        record
        for record in records
        if not cbc.usable_hero(record) and cbc.is_cbc_article_url(clean(record.get("url")))
    ]

    discovered_by_record: dict[int, str] = {}
    if discovery_targets:
        with ThreadPoolExecutor(max_workers=min(5, len(discovery_targets))) as executor:
            futures = {executor.submit(discover_hero, record): record for record in discovery_targets}
            for future in as_completed(futures):
                record = futures[future]
                try:
                    discovered_by_record[id(record)] = future.result()
                except Exception as exc:
                    print(f"CBC hero discovery worker failed: {type(exc).__name__}: {exc}", file=sys.stderr)
                    discovered_by_record[id(record)] = ""

    urls: set[str] = set()
    for record in records:
        urls.update(cbc.remote_image_urls(record))
        discovered = discovered_by_record.get(id(record), "")
        if cbc.is_remote_cbc_image(discovered):
            urls.add(discovered)

    cached: dict[str, str] = {}
    if urls:
        with ThreadPoolExecutor(max_workers=min(6, len(urls))) as executor:
            futures = {executor.submit(cbc.cache_image, url): url for url in sorted(urls)}
            for future in as_completed(futures):
                url = futures[future]
                try:
                    cached[url] = future.result()
                except Exception as exc:
                    print(f"CBC image cache worker failed: {type(exc).__name__}: {exc}", file=sys.stderr)
                    cached[url] = ""

    records_updated = prechanged
    images_rewritten = 0
    for record in records:
        changed, rewritten, _ = cbc.rewrite_record(
            record,
            cached,
            discovered_by_record.get(id(record), ""),
        )
        if changed:
            records_updated += 1
        images_rewritten += rewritten

    if records_updated:
        cbc.NEWS_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    hero_count = sum(1 for record in records if cbc.usable_hero(record))
    discovered_count = sum(1 for value in discovered_by_record.values() if value)
    cached_count = sum(1 for value in cached.values() if value)
    print(
        f"CBC image repair: {hero_count}/{len(records)} CBC record(s) have hero images; "
        f"{discovered_count}/{len(discovery_targets)} missing hero(s) rediscovered; "
        f"{cached_count}/{len(urls)} remote image(s) cached; "
        f"{images_rewritten} reference(s) rewritten"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
