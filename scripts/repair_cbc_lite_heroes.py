from __future__ import annotations

"""Recover CBC story heroes from the canonical CBC/Lite article surface.

CBC discovery frequently enters Scoop through Google News. The feed image can be a
small reporter/avatar derivative even when the article body and caption are valid.
CBC records already retain ``cbc_lite_url`` after body hydration, so use that
publisher-owned article surface as the preferred source of truth whenever the
current hero is missing or fails the final card-image quality contract.
"""

import json
from typing import Any
from urllib.parse import urlparse

import cache_cbc_images as cbc
import repair_card_image_refs as card_guard
import repair_cbc_images as cbc_repair

SCHEMA = 1


def clean(value: Any) -> str:
    return cbc.clean_text(value)


def is_cbc_reader_url(value: Any) -> bool:
    text = clean(value)
    if not text:
        return False
    try:
        parsed = urlparse(text)
    except Exception:
        return False
    host = parsed.netloc.lower().split(":", 1)[0]
    if parsed.scheme not in {"http", "https"}:
        return False
    if host not in {"cbc.ca", "www.cbc.ca"} and not host.endswith(".cbc.ca"):
        return False
    path = parsed.path.lower()
    return "/lite/story/" in path or "/news/" in path


def candidate_reader_urls(record: dict[str, Any]) -> list[str]:
    urls: list[str] = []
    for key in (
        "cbc_lite_url",
        "canonical_url",
        "resolved_url",
        "article_url",
        "original_url",
        "url",
    ):
        value = clean(record.get(key))
        if value and is_cbc_reader_url(value) and value not in urls:
            urls.append(value)
    return urls


def hero_needs_repair(record: dict[str, Any]) -> bool:
    hero = cbc.usable_hero(record)
    if not hero:
        return True
    if card_guard.is_tiny_remote_derivative(hero):
        return True
    if cbc_repair.current_hero_is_author(record):
        return True
    if cbc_repair.probable_small_square_profile(record):
        return True
    return False


def acceptable_candidate(record: dict[str, Any], candidate: Any) -> bool:
    value = clean(candidate)
    if not value:
        return False
    if card_guard.is_tiny_remote_derivative(value):
        return False
    if cbc_repair.looks_like_author_image(record, value, "", ""):
        return False
    return cbc.is_remote_cbc_image(value) or not cbc.is_remote_url(value)


def discover_from_cbc(record: dict[str, Any]) -> str:
    for article_url in candidate_reader_urls(record):
        for candidate in cbc_repair.reader_image_candidates(article_url, record):
            if acceptable_candidate(record, candidate):
                return clean(candidate)
    return ""


def clear_invalid_hero(record: dict[str, Any]) -> bool:
    if not hero_needs_repair(record):
        return False
    changed = False
    for key in ("image", "card_image", "card_image_small"):
        if clean(record.get(key)):
            record[key] = ""
            changed = True
    if changed:
        record["cbc_invalid_hero_cleared"] = True
    return changed


def repair_record(record: dict[str, Any]) -> bool:
    if not cbc_repair.is_cbc_record(record):
        return False
    if not hero_needs_repair(record):
        return False

    changed = clear_invalid_hero(record)
    discovered = discover_from_cbc(record)
    if not discovered:
        if changed:
            record["cbc_lite_hero_repair_schema"] = SCHEMA
        return changed

    cached = cbc.cache_image(discovered)
    selected = cached or discovered
    record["image"] = selected
    record["card_image"] = selected if cached else ""
    record["card_image_small"] = ""
    record["cbc_lite_hero_source"] = next(
        (url for url in candidate_reader_urls(record) if "/lite/story/" in urlparse(url).path.lower()),
        candidate_reader_urls(record)[0] if candidate_reader_urls(record) else "",
    )
    record["cbc_lite_hero_repair_schema"] = SCHEMA
    record["cbc_invalid_hero_cleared"] = True
    if cached:
        record["cbc_images_cached"] = True
        record.pop("cbc_image_hotlink", None)
    else:
        record["cbc_image_hotlink"] = True
    return True


def repair_payload(payload: dict[str, Any]) -> int:
    stories = payload.get("stories")
    if not isinstance(stories, list):
        return 0
    corrected = 0
    for story in stories:
        if isinstance(story, dict) and repair_record(story):
            corrected += 1
    payload["cbc_lite_hero_repair_schema"] = SCHEMA
    payload["cbc_lite_hero_repair_corrected"] = corrected
    return corrected


def main() -> int:
    if not cbc.NEWS_PATH.exists():
        print("No data/news.json found")
        return 0
    payload = json.loads(cbc.NEWS_PATH.read_text(encoding="utf-8"))
    corrected = repair_payload(payload)
    if corrected:
        cbc.NEWS_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"CBC Lite hero repair corrected {corrected} story/stories")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
