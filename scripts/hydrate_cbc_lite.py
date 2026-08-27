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
HEADERS = {
    "User-Agent": "LondonNews/1.0 (+https://myplexscripts.github.io/news/)",
    "Accept": "text/plain",
    "X-Retain-Links": "text",
    "X-Retain-Images": "alt",
    "X-Retain-Media": "none",
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


def good_paragraph(text: str, title: str) -> bool:
    text = clean_text(text)
    if len(text) < 35:
        return False
    lowered = text.lower()
    title_key = clean_text(title).lower()
    if title_key and (lowered == title_key or lowered.startswith(title_key + " ")):
        return False
    if any(marker in lowered for marker in BOILERPLATE):
        return False
    return True


def dedupe(values: list[str], title: str) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = strip_markdown(value)
        key = re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()
        if not key or key in seen or not good_paragraph(text, title):
            continue
        seen.add(key)
        output.append(text)
    return output


def parse_reader(text: str, title: str) -> list[str]:
    match = MARKDOWN_CONTENT.search(text)
    body = text[match.end():] if match else text

    blocks = re.split(r"\n\s*\n+", body)
    paragraphs: list[str] = []
    for block in blocks:
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if not lines:
            continue
        if len(lines) == 1 and re.match(r"^#{1,6}\s", lines[0]):
            continue
        joined = " ".join(lines)
        paragraphs.append(joined)

    return dedupe(paragraphs, title)


def fetch_reader(story_id: str, title: str) -> dict[str, Any] | None:
    lite_url = f"https://www.cbc.ca/lite/story/{story_id}"
    reader_url = f"https://r.jina.ai/http://www.cbc.ca/lite/story/{story_id}"
    try:
        response = requests.get(reader_url, headers=HEADERS, timeout=(4, 24))
        status = f"{response.status_code}/{len(response.content)}B"
        if response.status_code != 200 or len(response.content) < 500:
            print(f"CBC Reader miss {story_id}: {status}", file=sys.stderr)
            return None
        paragraphs = parse_reader(response.text, title)
        words = sum(len(p.split()) for p in paragraphs)
        if words < 90:
            print(f"CBC Reader miss {story_id}: {status}/{words}w after cleanup", file=sys.stderr)
            return None
        return {
            "paragraphs": paragraphs,
            "content_blocks": [{"type": "paragraph", "text": p} for p in paragraphs],
            "content": "\n\n".join(paragraphs),
            "word_count": words,
            "lite_url": lite_url,
            "transport": "jina-reader",
        }
    except Exception as exc:
        print(f"CBC Reader miss {story_id}: {type(exc).__name__}: {exc}", file=sys.stderr)
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
                value["ingestion_path"] = "cbc-google-news-lite-reader"
                value["scraped_at"] = datetime.now(timezone.utc).isoformat()
                value["cbc_lite_url"] = body["lite_url"]
                value["body_transport"] = body["transport"]
                quality = value.get("quality") if isinstance(value.get("quality"), dict) else {}
                quality.update({
                    "score": max(75, int(quality.get("score") or 0)),
                    "grade": "good",
                    "method": "reader:cbc:lite",
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
        print("CBC Reader hydration: no summary-only CBC stories to hydrate")
        return 0

    bodies: dict[str, dict[str, Any] | None] = {}
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

    hydrated = apply_bodies(payload, bodies)
    if hydrated:
        NEWS_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    unique_full = sum(1 for body in bodies.values() if body)
    print(
        f"CBC Reader hydration: {unique_full}/{len(targets)} unique CBC stories received full bodies; "
        f"{hydrated} CBC record(s) updated"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
