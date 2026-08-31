from __future__ import annotations

import json
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup, Tag

from article_source_profiles import profile_for
from fetch_news import clean_text, fetch_html
from refine_article_formatting import extract_dom_blocks

ROOT = Path(__file__).resolve().parents[1]
NEWS_PATH = ROOT / "data" / "news.json"
PROFILE_SCHEMA = 2
MAX_PER_RUN = max(8, int(os.getenv("PROFILE_MAX_PER_RUN", "42")))
RECENT_HOURS = max(24, int(os.getenv("PROFILE_RECENT_HOURS", "168")))
WORKERS = max(2, min(8, int(os.getenv("PROFILE_WORKERS", "6"))))
MIN_WORDS = 70


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def parse_datetime(value: Any) -> datetime | None:
    raw = str(value or "").strip().replace("Z", "+00:00")
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except Exception:
        return None


def words(value: Any) -> int:
    return len(re.findall(r"\b\w+[’'-]?\w*\b", str(value or "")))


def list_item_text(item: Any) -> str:
    return clean_text(item.get("text")) if isinstance(item, dict) else clean_text(item)


def block_word_count(blocks: list[dict[str, Any]]) -> int:
    total = 0
    for block in blocks:
        kind = block.get("type")
        if kind in {"paragraph", "heading", "quote"}:
            total += words(block.get("text"))
        elif kind == "list":
            total += sum(words(list_item_text(item)) for item in block.get("items", []))
    return total


def text_from_blocks(blocks: list[dict[str, Any]]) -> tuple[list[str], str]:
    paragraphs: list[str] = []
    for block in blocks:
        kind = block.get("type")
        if kind in {"paragraph", "quote"} and block.get("text"):
            paragraphs.append(clean_text(block.get("text")))
        elif kind == "list":
            paragraphs.extend(text for item in block.get("items", []) if (text := list_item_text(item)))
    return paragraphs, "\n\n".join(paragraphs)


def choose_profile_root(soup: BeautifulSoup, roots: list[str]) -> Tag | None:
    candidates: list[tuple[int, Tag]] = []
    for priority, selector in enumerate(roots):
        try:
            matches = soup.select(selector)
        except Exception:
            continue
        for candidate in matches:
            if not isinstance(candidate, Tag):
                continue
            paragraphs = candidate.select("p")
            paragraph_chars = sum(len(clean_text(p.get_text(" ", strip=True))) for p in paragraphs)
            list_chars = sum(len(clean_text(li.get_text(" ", strip=True))) for li in candidate.select("li"))
            heading_chars = sum(len(clean_text(h.get_text(" ", strip=True))) for h in candidate.select("h2,h3,h4"))
            content_chars = paragraph_chars + int(list_chars * 0.7) + int(heading_chars * 0.4)
            if content_chars < 120:
                continue
            link_chars = sum(len(clean_text(a.get_text(" ", strip=True))) for a in candidate.select("a"))
            score = content_chars + len(paragraphs) * 90 - int(link_chars * 0.18) - priority * 12
            candidates.append((score, candidate))
    return max(candidates, key=lambda item: item[0])[1] if candidates else None


def prune_profile_root(root: Tag, selectors: list[str]) -> Tag:
    clone = BeautifulSoup(str(root), "html.parser")
    clone_root = clone.find()
    if not isinstance(clone_root, Tag):
        return root
    for selector in selectors:
        try:
            for node in clone_root.select(selector):
                node.decompose()
        except Exception:
            continue
    return clone_root


def extract_profiled_blocks(
    raw: str,
    final_url: str,
    source: str,
    title: str,
    hero_url: str = "",
) -> tuple[list[dict[str, Any]], str]:
    profile = profile_for(source, final_url)
    soup = BeautifulSoup(raw, "html.parser")
    root = choose_profile_root(soup, profile["roots"])
    if root is None:
        return [], profile["name"]
    cleaned = prune_profile_root(root, profile["remove"])
    wrapped = f'<article><div class="article-body">{cleaned.decode_contents()}</div></article>'
    blocks = extract_dom_blocks(wrapped, final_url, title, hero_url)
    return blocks, profile["name"]


def coverage_ok(story: dict[str, Any], blocks: list[dict[str, Any]]) -> bool:
    extracted = block_word_count(blocks)
    if extracted < MIN_WORDS:
        return False
    existing = int(story.get("word_count") or 0) or words(story.get("content"))
    if existing <= 0:
        return True
    return extracted >= max(MIN_WORDS, int(existing * 0.72))


def process_story(story: dict[str, Any]) -> tuple[list[dict[str, Any]], str, str]:
    source = clean_text(story.get("source", ""))
    url = clean_text(story.get("url", ""))
    profile = profile_for(source, url)
    if profile["name"] == "cbc":
        return [], "cbc", "cbc:jina-source-profile-v1"
    try:
        raw, final_url = fetch_html(url)
    except Exception as exc:
        return [], profile["name"], f"{profile['name']}:{type(exc).__name__}"
    blocks, profile_name = extract_profiled_blocks(
        raw,
        final_url,
        source,
        clean_text(story.get("title", "")),
        clean_text(story.get("image", "")),
    )
    return blocks, profile_name, f"{profile_name}:profiled-dom-v1"


def story_needs_work(story: dict[str, Any], now: datetime) -> bool:
    if not isinstance(story, dict) or not story.get("url") or not story.get("title"):
        return False
    if story.get("content_status") not in {"full", "partial"}:
        return False
    if int(story.get("source_profile_schema") or 0) >= PROFILE_SCHEMA:
        return False
    attempted = parse_datetime(story.get("source_profile_attempted_at"))
    return not attempted or now - attempted >= timedelta(hours=6)


def priority(story: dict[str, Any], now: datetime) -> tuple[int, int, float]:
    published = parse_datetime(story.get("published"))
    age_hours = (now - published).total_seconds() / 3600 if published else 99999
    profile_name = profile_for(clean_text(story.get("source", "")), clean_text(story.get("url", "")))["name"]
    specific = 1 if profile_name != "generic" else 0
    return specific, 1 if age_hours <= RECENT_HOURS else 0, -age_hours


def main() -> int:
    if not NEWS_PATH.exists():
        print("No data/news.json found", file=sys.stderr)
        return 1
    payload = json.loads(NEWS_PATH.read_text(encoding="utf-8"))
    stories = payload.get("stories") if isinstance(payload.get("stories"), list) else []
    now = utc_now()
    targets = [story for story in stories if story_needs_work(story, now)]
    targets.sort(key=lambda story: priority(story, now), reverse=True)
    targets = targets[:MAX_PER_RUN]
    if not targets:
        print("Source specific article extraction already current")
        return 0

    by_id = {str(story.get("id") or ""): story for story in targets}
    accepted = 0
    profiled = 0
    with ThreadPoolExecutor(max_workers=WORKERS) as executor:
        futures = {executor.submit(process_story, story): str(story.get("id") or "") for story in targets}
        for future in as_completed(futures):
            story = by_id[futures[future]]
            story["source_profile_attempted_at"] = now.isoformat()
            try:
                blocks, profile_name, method = future.result()
            except Exception as exc:
                story["source_profile_method"] = f"error:{type(exc).__name__}"
                continue

            story["source_profile"] = profile_name
            story["source_profile_method"] = method

            if profile_name == "cbc":
                story["source_profile_schema"] = PROFILE_SCHEMA
                story["source_profiled_at"] = utc_now().isoformat()
                accepted += 1
                profiled += 1
                continue

            if not coverage_ok(story, blocks):
                continue
            paragraphs, text = text_from_blocks(blocks)
            if not paragraphs:
                continue
            story["content_blocks"] = blocks
            story["paragraphs"] = paragraphs
            story["content"] = text
            story["word_count"] = words(text)
            story["source_profile_schema"] = PROFILE_SCHEMA
            story["source_profiled_at"] = utc_now().isoformat()
            accepted += 1
            if profile_name != "generic":
                profiled += 1

    payload["source_profile_schema"] = PROFILE_SCHEMA
    payload["source_profiled_at"] = utc_now().isoformat()
    NEWS_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Source specific extraction: {accepted} accepted, {profiled} source-profiled, {len(targets)} attempted")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
