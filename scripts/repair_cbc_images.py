from __future__ import annotations

import html
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any
from urllib.parse import urlparse

import requests
from PIL import Image

import cache_cbc_images as cbc


CBC_SOURCE_PREFIX = "cbc news"
CBC_STORY_ID = re.compile(r"(?<!\d)(\d+\.\d+)(?!\d)")
AUTHOR_URL_MARKERS = (
    "/author/", "/authors/", "/staff/", "author-", "byline", "headshot",
    "avatar", "profile-photo", "profile_image", "profile-image",
)
AUTHOR_TEXT_MARKERS = (
    "author photo", "author headshot", "staff photo", "reporter photo",
    "journalist photo", "cbc reporter", "cbc journalist", "headshot",
)
AUTHOR_STOPWORDS = {
    "by", "cbc", "news", "reporter", "journalist", "staff", "senior", "producer",
    "editor", "correspondent", "writer", "digital", "video", "photo", "photos",
}


def clean(value: Any) -> str:
    return cbc.clean_text(value)


def normalized_words(value: Any) -> list[str]:
    return [
        token
        for token in re.findall(r"[a-z0-9]+", clean(value).lower())
        if len(token) >= 2 and token not in AUTHOR_STOPWORDS
    ]


def author_tokens(record: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for key in ("author", "byline"):
        value = record.get(key)
        if isinstance(value, str) and clean(value):
            values.append(clean(value))
    authors = record.get("authors")
    if isinstance(authors, list):
        for value in authors:
            if isinstance(value, dict):
                value = value.get("name")
            if clean(value):
                values.append(clean(value))

    tokens: list[str] = []
    for value in values:
        value = re.sub(r"^by\s+", "", value, flags=re.I)
        value = re.split(r"\s*[|·•]\s*|,\s*cbc\b", value, maxsplit=1, flags=re.I)[0]
        for token in normalized_words(value):
            if token not in tokens:
                tokens.append(token)
    return tokens[:5]


def author_mentioned(record: dict[str, Any], value: Any) -> bool:
    words = set(normalized_words(value))
    tokens = author_tokens(record)
    if len(tokens) < 2 or not words:
        return False
    matches = sum(1 for token in tokens if token in words)
    return matches >= min(2, len(tokens))


def looks_like_author_image(
    record: dict[str, Any],
    url: str = "",
    alt: str = "",
    caption: str = "",
) -> bool:
    normalized_url = clean(url).lower()
    normalized_alt = clean(alt)
    normalized_caption = clean(caption)
    descriptive = f"{normalized_alt} {normalized_caption}".strip().lower()

    # CBC captions often credit the reporter who took a legitimate story photo,
    # so an author name in a caption alone is not enough to reject the image.
    # Profile photos are much more reliably identified by the URL, a short alt
    # label that is the reporter's name, or explicit author/headshot wording.
    if author_mentioned(record, normalized_url):
        return True
    if normalized_alt and len(normalized_alt) <= 120 and author_mentioned(record, normalized_alt):
        return True
    if any(marker in normalized_url for marker in AUTHOR_URL_MARKERS):
        return True
    if any(marker in descriptive for marker in AUTHOR_TEXT_MARKERS):
        return True
    return False


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


def same_reference(left: Any, right: Any) -> bool:
    a = cbc.normalize_local_image(left)
    b = cbc.normalize_local_image(right)
    if not a or not b:
        return False
    if a == b:
        return True
    try:
        pa = urlparse(a)
        pb = urlparse(b)
        if pa.scheme and pb.scheme:
            return pa.netloc.lower() == pb.netloc.lower() and pa.path == pb.path
    except Exception:
        pass
    return False


def block_metadata_for(record: dict[str, Any], url: str) -> tuple[str, str]:
    blocks = record.get("content_blocks")
    if not isinstance(blocks, list):
        return "", ""
    for block in blocks:
        if not isinstance(block, dict) or block.get("type") != "image":
            continue
        if same_reference(block.get("url"), url):
            return clean(block.get("alt")), clean(block.get("caption"))
    return "", ""


def current_hero_is_author(record: dict[str, Any]) -> bool:
    for key in ("card_image", "image"):
        url = clean(record.get(key))
        if not url:
            continue
        alt, caption = block_metadata_for(record, url)
        if not alt and key == "image":
            alt = clean(record.get("image_alt"))
        if looks_like_author_image(record, url, alt, caption):
            return True
    return False


def local_image_dimensions(value: Any) -> tuple[int, int]:
    src = cbc.normalize_local_image(value)
    if not src or cbc.is_remote_url(src):
        return 0, 0
    relative = src.lstrip("/")
    if relative.startswith("news/"):
        relative = relative[5:]
    if not relative.startswith("cache/"):
        return 0, 0
    path = cbc.ROOT / "public" / relative
    try:
        with Image.open(path) as image:
            return int(image.width), int(image.height)
    except Exception:
        return 0, 0


def probable_small_square_profile(record: dict[str, Any]) -> bool:
    if len(author_tokens(record)) < 2:
        return False
    hero = cbc.usable_hero(record)
    width, height = local_image_dimensions(hero)
    if not width or not height:
        return False
    ratio = width / max(1, height)
    return 0.82 <= ratio <= 1.22 and max(width, height) <= 640


def remove_author_image_blocks(record: dict[str, Any]) -> bool:
    blocks = record.get("content_blocks")
    if not isinstance(blocks, list):
        return False
    cleaned_blocks: list[Any] = []
    changed = False
    for block in blocks:
        if not isinstance(block, dict) or block.get("type") != "image":
            cleaned_blocks.append(block)
            continue
        if looks_like_author_image(
            record,
            clean(block.get("url")),
            clean(block.get("alt")),
            clean(block.get("caption")),
        ):
            changed = True
            continue
        cleaned_blocks.append(block)
    if changed:
        record["content_blocks"] = cleaned_blocks
    return changed


def clear_author_hero(record: dict[str, Any]) -> bool:
    if not current_hero_is_author(record):
        return False
    changed = False
    for key in ("image", "card_image", "card_image_small"):
        if clean(record.get(key)):
            record[key] = ""
            changed = True
    if clean(record.get("image_alt")) and author_mentioned(record, record.get("image_alt")):
        record["image_alt"] = ""
        changed = True
    record["cbc_author_image_rejected"] = True
    return changed


def promote_existing_hero(record: dict[str, Any]) -> bool:
    """Promote an existing non-author article image to the card hero."""
    if cbc.usable_hero(record) and not current_hero_is_author(record):
        return False

    candidates: list[tuple[str, str, str]] = []
    for key in ("lead_image", "hero_image", "og_image", "twitter_image"):
        value = clean(record.get(key))
        if value:
            candidates.append((value, "", ""))

    blocks = record.get("content_blocks")
    if isinstance(blocks, list):
        for block in blocks:
            if not isinstance(block, dict) or block.get("type") != "image":
                continue
            value = clean(block.get("url"))
            if value:
                candidates.append((value, clean(block.get("alt")), clean(block.get("caption"))))

    for candidate, alt, caption in candidates:
        normalized = cbc.normalize_local_image(candidate)
        if not normalized:
            continue
        if looks_like_author_image(record, normalized, alt, caption):
            continue
        if cbc.is_remote_cbc_image(normalized) or not cbc.is_remote_url(normalized):
            record["image"] = normalized
            record["card_image"] = normalized if not cbc.is_remote_url(normalized) else ""
            if alt:
                record["image_alt"] = alt
            return True
    return False


def title_overlap_score(record: dict[str, Any], alt: str) -> int:
    title_words = set(normalized_words(record.get("title")))
    alt_words = set(normalized_words(alt))
    overlap = len(title_words & alt_words)
    if overlap >= 3:
        return 36
    if overlap == 2:
        return 24
    if overlap == 1:
        return 8
    return 0


def reader_image_candidates(story_url: str, record: dict[str, Any]) -> list[str]:
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
    markdown_found = False
    for index, (raw_alt, raw_url) in enumerate(cbc.MARKDOWN_IMAGE.findall(response.text)):
        image_url = html.unescape(raw_url.strip())
        alt = clean(raw_alt)
        score = cbc.image_score(image_url)
        if score <= 0 or looks_like_author_image(record, image_url, alt, ""):
            continue
        key = f"{urlparse(image_url).netloc.lower()}{urlparse(image_url).path.lower()}"
        if key in seen:
            continue
        seen.add(key)
        markdown_found = True
        lower_url = image_url.lower()
        score += title_overlap_score(record, alt)
        score += 12 if len(alt) >= 24 else 0
        score += 20 if any(marker in lower_url for marker in ("16x9", "1180", "1280", "1920")) else 0
        score -= min(index, 24)
        scored.append((score, image_url))

    # Bare i.cbc.ca URLs have no descriptive text, so only use them if Jina did
    # not expose any usable Markdown image. This prevents an unlabelled profile
    # photo near the byline from outranking a real story image.
    if not markdown_found:
        for index, raw_url in enumerate(re.findall(r"https?://i\.cbc\.ca/[^\s)\]>\"']+", response.text, flags=re.I)):
            image_url = html.unescape(raw_url.strip())
            score = cbc.image_score(image_url)
            if score <= 0 or looks_like_author_image(record, image_url, "", ""):
                continue
            key = f"{urlparse(image_url).netloc.lower()}{urlparse(image_url).path.lower()}"
            if key in seen:
                continue
            seen.add(key)
            lower_url = image_url.lower()
            score += 20 if any(marker in lower_url for marker in ("16x9", "1180", "1280", "1920")) else 0
            score -= min(index, 24)
            scored.append((score, image_url))

    scored.sort(key=lambda item: item[0], reverse=True)
    return [url for _, url in scored]


def discover_hero(record: dict[str, Any]) -> str:
    story_url = clean(record.get("url"))
    if not story_url:
        return ""

    candidates = reader_image_candidates(story_url, record)
    if candidates:
        return candidates[0]

    match = CBC_STORY_ID.search(story_url)
    if match:
        lite_url = f"https://www.cbc.ca/lite/story/{match.group(1)}"
        candidates = reader_image_candidates(lite_url, record)
        if candidates:
            return candidates[0]

    return ""


def apply_discovered_validation(
    record: dict[str, Any],
    discovered: str,
    cached: dict[str, str],
) -> bool:
    if not discovered or looks_like_author_image(record, discovered, "", ""):
        return False
    replacement = cached.get(discovered, "") or discovered
    current = cbc.usable_hero(record)
    if same_reference(current, replacement):
        return False
    record["image"] = replacement
    if cbc.is_remote_url(replacement):
        record["card_image"] = ""
        record["cbc_image_hotlink"] = True
    else:
        record["card_image"] = replacement
        record.pop("cbc_image_hotlink", None)
    record["cbc_author_image_rejected"] = True
    return True


def main() -> int:
    if not cbc.NEWS_PATH.exists():
        return 0

    payload = json.loads(cbc.NEWS_PATH.read_text(encoding="utf-8"))
    records: list[dict[str, Any]] = []
    collect_records(payload, records, set())

    records_updated = 0
    validation_ids: set[int] = set()
    author_blocks_removed = 0
    author_heroes_cleared = 0

    for record in records:
        changed = False
        if cbc.prepare_record(record):
            changed = True
        if remove_author_image_blocks(record):
            changed = True
            author_blocks_removed += 1

        suspicious = current_hero_is_author(record)
        low_res_square = probable_small_square_profile(record)
        if suspicious or low_res_square:
            validation_ids.add(id(record))
        if suspicious and clear_author_hero(record):
            changed = True
            author_heroes_cleared += 1
        if promote_existing_hero(record):
            changed = True
        if changed:
            records_updated += 1

    discovery_targets = [
        record
        for record in records
        if (
            not cbc.usable_hero(record)
            or id(record) in validation_ids
        )
        and cbc.is_cbc_article_url(clean(record.get("url")))
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

    images_rewritten = 0
    validated_replacements = 0
    for record in records:
        discovered = discovered_by_record.get(id(record), "")
        if id(record) in validation_ids and apply_discovered_validation(record, discovered, cached):
            records_updated += 1
            validated_replacements += 1

        changed, rewritten, _ = cbc.rewrite_record(record, cached, discovered)
        if changed:
            records_updated += 1
        images_rewritten += rewritten

        # A final guard catches metadata introduced by rewrite_record itself.
        if remove_author_image_blocks(record):
            records_updated += 1
            author_blocks_removed += 1
        if current_hero_is_author(record):
            if clear_author_hero(record):
                records_updated += 1
                author_heroes_cleared += 1
            if promote_existing_hero(record):
                records_updated += 1

    if records_updated:
        cbc.NEWS_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    hero_count = sum(1 for record in records if cbc.usable_hero(record) and not current_hero_is_author(record))
    discovered_count = sum(1 for value in discovered_by_record.values() if value)
    cached_count = sum(1 for value in cached.values() if value)
    print(
        f"CBC image repair: {hero_count}/{len(records)} CBC record(s) have non-author hero images; "
        f"{discovered_count}/{len(discovery_targets)} hero(s) rediscovered or validated; "
        f"{validated_replacements} suspicious hero(s) replaced; "
        f"{author_heroes_cleared} author hero(s) rejected; "
        f"{author_blocks_removed} record(s) had author image blocks removed; "
        f"{cached_count}/{len(urls)} remote image(s) cached; "
        f"{images_rewritten} reference(s) rewritten"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
