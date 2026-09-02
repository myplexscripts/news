from __future__ import annotations

import argparse
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from bs4 import BeautifulSoup

import fetch_news


ROOT = Path(__file__).resolve().parents[1]
NEWS_PATH = ROOT / "data" / "news.json"
SOURCE_NAME = "National Post"
REPAIR_SCHEMA = 1
MAX_PER_RUN = max(5, int(os.getenv("NATIONAL_POST_REPAIR_MAX", "30")))

POSTMEDIA_EXTRA_BOILERPLATE = (
    "more from national post",
    "recommended from national post",
    "recommended for you",
    "most popular",
    "most read",
    "trending",
    "sign in or create an account",
    "create an account or sign in",
    "subscribe to continue",
    "story continues below",
    "this advertisement has not loaded yet",
)


def words(value: str) -> int:
    return len(re.findall(r"\b\w+[’'-]?\w*\b", str(value or "")))


def article_path_ok(url: str) -> bool:
    parsed = urlparse(str(url or ""))
    host = parsed.netloc.lower().replace("www.", "")
    path = parsed.path.lower().rstrip("/")
    if host != "nationalpost.com":
        return False
    if "/category/" in path or path in {"", "/", "/news", "/news/canada"}:
        return False
    return path.startswith("/news/")


def story_is_article(story: dict[str, Any]) -> bool:
    if str(story.get("source") or "").strip() != SOURCE_NAME:
        return True
    title = fetch_news.clean_text(story.get("title", "")).lower()
    if title in {"national post", "news", "canada"}:
        return False
    return article_path_ok(str(story.get("url") or ""))


def clean_candidate_paragraphs(paragraphs: list[str], title: str) -> list[str]:
    cleaned = fetch_news.clean_article_blocks(paragraphs, SOURCE_NAME, title)
    result: list[str] = []
    for paragraph in cleaned:
        key = fetch_news.boilerplate_key(paragraph)
        if any(marker in key for marker in POSTMEDIA_EXTRA_BOILERPLATE):
            continue
        result.append(paragraph)
    return result


def candidate_details(method: str, blocks: list[dict[str, Any]]) -> dict[str, Any] | None:
    blocks = [block for block in blocks if isinstance(block, dict)]
    paragraphs, text = fetch_news.text_from_blocks(blocks)
    word_count = words(text)
    paragraph_count = len(paragraphs)
    if word_count < 70 or paragraph_count < 2:
        return None
    rich_count = sum(
        1 for block in blocks
        if block.get("type") in {"heading", "quote", "list", "image"}
    )
    # Text completeness is dominant. Rich structure and paragraph separation are
    # useful tie breakers so a nearly equal DOM candidate keeps original layout.
    score = (word_count * 10) + (min(paragraph_count, 40) * 5) + (min(rich_count, 12) * 18)
    return {
        "method": method,
        "blocks": blocks,
        "paragraphs": paragraphs,
        "text": text,
        "word_count": word_count,
        "paragraph_count": paragraph_count,
        "rich_count": rich_count,
        "score": score,
    }


def choose_candidate(candidates: list[dict[str, Any]]) -> dict[str, Any] | None:
    plausible = [candidate for candidate in candidates if candidate]
    if not plausible:
        return None
    plausible.sort(
        key=lambda candidate: (
            int(candidate.get("score") or 0),
            int(candidate.get("word_count") or 0),
            int(candidate.get("paragraph_count") or 0),
        ),
        reverse=True,
    )
    return plausible[0]


def image_fallbacks(soup: BeautifulSoup, final_url: str, ld: dict[str, Any], lead_image: str) -> list[dict[str, Any]]:
    images = fetch_news.collect_image_candidates(soup, final_url, ld, lead_image)
    result: list[dict[str, Any]] = []
    for image in images:
        if fetch_news.same_image(str(image.get("url") or ""), lead_image):
            continue
        if any(fetch_news.same_image(str(image.get("url") or ""), str(prior.get("url") or "")) for prior in result):
            continue
        result.append(image)
        if len(result) >= fetch_news.MAX_ARTICLE_IMAGES:
            break
    return result


def extract_candidates(story: dict[str, Any]) -> list[dict[str, Any]]:
    url = str(story.get("url") or "").strip()
    raw, final_url = fetch_news.fetch_html(url)
    soup = BeautifulSoup(raw, "html.parser")
    ld = fetch_news.article_json_ld(soup)
    title = fetch_news.clean_story_title(
        fetch_news.clean_text(ld.get("headline")) or str(story.get("title") or ""),
        SOURCE_NAME,
    )
    lead_image = str(story.get("image") or "")
    inline_images = image_fallbacks(soup, final_url, ld, lead_image)
    candidates: list[dict[str, Any]] = []

    dom_blocks, _dom_stats, dom_method = fetch_news.extract_dom_blocks(
        soup,
        final_url,
        SOURCE_NAME,
        title,
        lead_image,
    )
    dom_blocks = fetch_news.sanitize_content_blocks(dom_blocks, SOURCE_NAME, title, lead_image)
    dom_candidate = candidate_details(dom_method, dom_blocks)
    if dom_candidate:
        candidates.append(dom_candidate)

    ld_paragraphs = fetch_news.json_ld_body_paragraphs(ld, SOURCE_NAME, title)
    ld_paragraphs = clean_candidate_paragraphs(ld_paragraphs, title)
    if ld_paragraphs:
        ld_blocks = fetch_news.fallback_blocks(ld_paragraphs, inline_images)
        ld_candidate = candidate_details("jsonld:postmedia-repair", ld_blocks)
        if ld_candidate:
            candidates.append(ld_candidate)

    _extracted_text, extracted_paragraphs, _meta = fetch_news.extracted_article_text(
        raw,
        final_url,
        SOURCE_NAME,
        title,
    )
    extracted_paragraphs = clean_candidate_paragraphs(extracted_paragraphs, title)
    if extracted_paragraphs:
        extracted_blocks = fetch_news.fallback_blocks(extracted_paragraphs, inline_images)
        extracted_candidate = candidate_details("trafilatura:postmedia-repair", extracted_blocks)
        if extracted_candidate:
            candidates.append(extracted_candidate)

    return candidates


def should_replace(story: dict[str, Any], candidate: dict[str, Any]) -> bool:
    existing_words = int(story.get("word_count") or 0)
    if existing_words <= 0:
        existing_words = words(str(story.get("content") or ""))
    existing_paragraphs = story.get("paragraphs") if isinstance(story.get("paragraphs"), list) else []
    existing_paragraph_count = len([item for item in existing_paragraphs if str(item or "").strip()])
    candidate_words = int(candidate.get("word_count") or 0)
    candidate_paragraph_count = int(candidate.get("paragraph_count") or 0)

    if existing_words < 70 or existing_paragraph_count < 2:
        return candidate_words >= 90 and candidate_paragraph_count >= 2
    if candidate_words >= max(existing_words + 90, int(existing_words * 1.28)):
        return True
    if existing_paragraph_count <= 2 and candidate_paragraph_count >= 5 and candidate_words >= existing_words:
        return True
    return False


def apply_candidate(story: dict[str, Any], candidate: dict[str, Any]) -> None:
    story["content_blocks"] = candidate["blocks"]
    story["paragraphs"] = candidate["paragraphs"]
    story["content"] = candidate["text"]
    story["word_count"] = candidate["word_count"]
    story["content_status"] = "full" if candidate["word_count"] >= 120 and candidate["paragraph_count"] >= 2 else "partial"
    story["national_post_repair_method"] = candidate["method"]
    story["national_post_repaired_at"] = datetime.now(timezone.utc).isoformat()
    story["quality"] = fetch_news.extraction_quality(story, {}, candidate["method"])
    # Any older structure annotation described the body we just replaced. Let the
    # normal structure pass inspect the repaired blocks again on this run.
    for key in (
        "structure_schema",
        "structure_method",
        "structure_status",
        "structure_richness",
        "structured_at",
        "structure_attempted_at",
    ):
        story.pop(key, None)


def repair_payload(payload: dict[str, Any], filter_only: bool = False, limit: int = MAX_PER_RUN) -> tuple[int, int, int]:
    stories = payload.get("stories") if isinstance(payload.get("stories"), list) else []
    before = len(stories)
    stories = [story for story in stories if not isinstance(story, dict) or story_is_article(story)]
    removed = before - len(stories)
    payload["stories"] = stories
    if filter_only:
        return removed, 0, 0

    targets = [
        story for story in stories
        if isinstance(story, dict)
        and str(story.get("source") or "").strip() == SOURCE_NAME
        and int(story.get("national_post_repair_schema") or 0) < REPAIR_SCHEMA
    ]
    targets.sort(key=lambda story: str(story.get("published") or ""), reverse=True)
    targets = targets[: max(1, limit)]

    attempted = 0
    repaired = 0
    for story in targets:
        attempted += 1
        try:
            candidate = choose_candidate(extract_candidates(story))
            if candidate and should_replace(story, candidate):
                old_words = int(story.get("word_count") or 0)
                apply_candidate(story, candidate)
                repaired += 1
                print(
                    f"National Post repaired: {old_words} -> {candidate['word_count']} words | "
                    f"{str(story.get('title') or '')[:80]}"
                )
            story["national_post_repair_schema"] = REPAIR_SCHEMA
            story["national_post_repair_checked_at"] = datetime.now(timezone.utc).isoformat()
        except Exception as exc:
            story["national_post_repair_error"] = str(exc)[:240]
            story["national_post_repair_checked_at"] = datetime.now(timezone.utc).isoformat()
            print(f"National Post repair deferred: {str(story.get('title') or '')[:70]} | {exc}")

    return removed, attempted, repaired


def main() -> int:
    parser = argparse.ArgumentParser(description="Repair National Post article bodies and reject category-page false positives")
    parser.add_argument("--filter-only", action="store_true")
    parser.add_argument("--limit", type=int, default=MAX_PER_RUN)
    args = parser.parse_args()

    payload = json.loads(NEWS_PATH.read_text(encoding="utf-8"))
    removed, attempted, repaired = repair_payload(
        payload,
        filter_only=args.filter_only,
        limit=max(1, args.limit),
    )
    payload["national_post_repair_schema"] = REPAIR_SCHEMA
    payload["national_post_repair_at"] = datetime.now(timezone.utc).isoformat()
    NEWS_PATH.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"National Post repair: {removed} invalid pages removed, {repaired}/{attempted} article bodies improved")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
