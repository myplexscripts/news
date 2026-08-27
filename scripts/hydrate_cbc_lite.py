from __future__ import annotations

import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from trafilatura import extract

ROOT = Path(__file__).resolve().parents[1]
NEWS_PATH = ROOT / "data" / "news.json"
CBC_ID = re.compile(r"(?<!\d)([19]\.\d{5,})(?!\d)")
HEADERS = {
    "User-Agent": "LondonNews/1.0 (+https://myplexscripts.github.io/news/)",
    "Accept-Language": "en-CA,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
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
)


def clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def article_id(url: str) -> str:
    matches = CBC_ID.findall(urlparse(url).path)
    return matches[-1] if matches else ""


def good_paragraph(text: str, title: str) -> bool:
    text = clean_text(text)
    if len(text) < 35:
        return False
    lowered = text.lower()
    if lowered == clean_text(title).lower():
        return False
    return not any(marker in lowered for marker in BOILERPLATE)


def dedupe(values: list[str], title: str) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = clean_text(value)
        key = re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()
        if not key or key in seen or not good_paragraph(text, title):
            continue
        seen.add(key)
        output.append(text)
    return output


def parse_lite(html: str, title: str) -> tuple[list[str], str, str]:
    soup = BeautifulSoup(html, "html.parser")

    image = ""
    image_meta = soup.select_one("meta[property='og:image'], meta[name='twitter:image']")
    if image_meta:
        image = clean_text(image_meta.get("content"))

    author = ""
    author_meta = soup.select_one("meta[name='author'], meta[property='article:author']")
    if author_meta:
        author = clean_text(author_meta.get("content"))

    for node in soup.select("script, style, nav, footer, aside, form, header, [class*='related'], [class*='newsletter'], [class*='advert']"):
        node.decompose()

    roots = [
        soup.select_one("article"),
        soup.select_one("[role='main']"),
        soup.select_one("main"),
    ]
    for root in roots:
        if root is None:
            continue
        paragraphs = dedupe([node.get_text(" ", strip=True) for node in root.select("p")], title)
        if sum(len(p.split()) for p in paragraphs) >= 90:
            return paragraphs, image, author

    try:
        text = extract(html, include_comments=False, include_tables=False, favor_precision=True) or ""
    except Exception:
        text = ""
    paragraphs = dedupe(re.split(r"\n+", text), title)
    return paragraphs, image, author


def fetch_lite(story_id: str, title: str) -> dict[str, Any] | None:
    urls = [
        f"https://www.cbc.ca/lite/story/{story_id}",
        f"https://cbc.ca/lite/story/{story_id}",
    ]
    last_status = ""
    for url in urls:
        try:
            response = requests.get(url, headers=HEADERS, timeout=(3, 9), allow_redirects=True)
            last_status = f"{response.status_code}/{len(response.content)}B"
            if response.status_code >= 400 or len(response.content) < 500:
                continue
            paragraphs, image, author = parse_lite(response.text, title)
            words = sum(len(p.split()) for p in paragraphs)
            if words < 90:
                last_status = f"{last_status}/{words}w"
                continue
            return {
                "paragraphs": paragraphs,
                "content_blocks": [{"type": "paragraph", "text": p} for p in paragraphs],
                "content": "\n\n".join(paragraphs),
                "word_count": words,
                "image": image,
                "author": author,
                "lite_url": str(response.url),
            }
        except Exception as exc:
            last_status = f"error:{type(exc).__name__}:{exc}"
    print(f"CBC Lite miss {story_id}: {last_status}", file=sys.stderr)
    return None


def collect_targets(value: Any, targets: dict[str, tuple[str, str]]) -> None:
    if isinstance(value, dict):
        if value.get("source") == "CBC News London" and value.get("content_status") != "full":
            url = clean_text(value.get("url"))
            story_id = article_id(url)
            title = clean_text(value.get("title"))
            if story_id and title:
                targets.setdefault(story_id, (title, url))
        for child in value.values():
            collect_targets(child, targets)
    elif isinstance(value, list):
        for child in value:
            collect_targets(child, targets)


def apply_bodies(value: Any, bodies: dict[str, dict[str, Any] | None]) -> int:
    hydrated = 0
    if isinstance(value, dict):
        if value.get("source") == "CBC News London" and value.get("content_status") != "full":
            story_id = article_id(clean_text(value.get("url")))
            body = bodies.get(story_id)
            if body:
                value["paragraphs"] = body["paragraphs"]
                value["content_blocks"] = body["content_blocks"]
                value["content"] = body["content"]
                value["word_count"] = body["word_count"]
                value["content_status"] = "full"
                value["ingestion_path"] = "cbc-google-news-lite"
                value["scraped_at"] = datetime.now(timezone.utc).isoformat()
                value["cbc_lite_url"] = body["lite_url"]
                if body.get("image") and not value.get("image"):
                    value["image"] = body["image"]
                if body.get("author"):
                    value["author"] = body["author"]
                quality = value.get("quality") if isinstance(value.get("quality"), dict) else {}
                quality.update({
                    "score": max(75, int(quality.get("score") or 0)),
                    "grade": "good",
                    "method": "dom:cbc:lite",
                    "text_blocks": len(body["paragraphs"]),
                    "rich_blocks": 0,
                    "image_blocks": 0,
                })
                value["quality"] = quality
                hydrated += 1
        for child in list(value.values()):
            hydrated += apply_bodies(child, bodies)
    elif isinstance(value, list):
        for child in value:
            hydrated += apply_bodies(child, bodies)
    return hydrated


def main() -> int:
    if not NEWS_PATH.exists():
        return 0
    payload = json.loads(NEWS_PATH.read_text(encoding="utf-8"))
    targets: dict[str, tuple[str, str]] = {}
    collect_targets(payload, targets)
    if not targets:
        print("CBC Lite hydration: no summary-only CBC stories to hydrate")
        return 0

    bodies: dict[str, dict[str, Any] | None] = {}
    with ThreadPoolExecutor(max_workers=min(5, len(targets))) as executor:
        futures = {
            executor.submit(fetch_lite, story_id, title): story_id
            for story_id, (title, _) in targets.items()
        }
        for future in as_completed(futures):
            story_id = futures[future]
            try:
                bodies[story_id] = future.result()
            except Exception as exc:
                print(f"CBC Lite worker failed {story_id}: {exc}", file=sys.stderr)
                bodies[story_id] = None

    hydrated = apply_bodies(payload, bodies)
    if hydrated:
        NEWS_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"CBC Lite hydration: {hydrated}/{len(targets)} unique CBC stories received full bodies")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
