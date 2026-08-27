from __future__ import annotations

import html
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlparse

import feedparser
import requests
from bs4 import BeautifulSoup
from trafilatura import extract


ROOT = Path(__file__).resolve().parents[1]
NEWS_PATH = ROOT / "data" / "news.json"
CBC_GOOGLE_NEWS_FEED = (
    "https://news.google.com/rss/search?"
    "q=site%3Acbc.ca%2Fnews%2Fcanada%2Flondon%20London%20Ontario%20when%3A3d&"
    "hl=en-CA&gl=CA&ceid=CA%3Aen"
)
USER_AGENT = "LondonNews/1.0 (+https://myplexscripts.github.io/news/)"
CBC_SUFFIX = re.compile(r"\s+-\s+CBC(?: News|\.ca)?\s*$", re.I)
CBC_ID = re.compile(r"(?<!\d)([19]\.\d{5,})(?!\d)")
BOILERPLATE = (
    "sign up for", "subscribe", "download the cbc news app", "read more from cbc",
    "add cbc news as a preferred source", "related stories", "recommended for you",
    "copyright cbc", "all rights reserved", "this advertisement",
)
HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept-Language": "en-CA,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


def clean_text(value: Any) -> str:
    raw = html.unescape(str(value or ""))
    if "<" in raw and ">" in raw:
        raw = BeautifulSoup(raw, "html.parser").get_text(" ", strip=True)
    return re.sub(r"\s+", " ", raw).strip()


def google_story_key(value: Any) -> str:
    parsed = urlparse(str(value or ""))
    if "news.google.com" not in parsed.netloc.lower():
        return ""
    path = parsed.path.rstrip("/")
    return path if "/rss/articles/" in path else ""


def load_google_cbc() -> dict[str, dict[str, str]]:
    response = requests.get(CBC_GOOGLE_NEWS_FEED, headers=HEADERS, timeout=(4, 10))
    response.raise_for_status()
    feed = feedparser.parse(response.content)
    lookup: dict[str, dict[str, str]] = {}

    for entry in feed.entries:
        source_meta = entry.get("source") or {}
        source_title = clean_text(source_meta.get("title")) if isinstance(source_meta, dict) else clean_text(source_meta)
        raw_title = clean_text(entry.get("title"))
        if "cbc" not in source_title.lower() and not CBC_SUFFIX.search(raw_title):
            continue
        title = CBC_SUFFIX.sub("", raw_title).strip()
        link = clean_text(entry.get("link") or entry.get("guid"))
        key = google_story_key(link)
        if not title or not key:
            continue
        summary = clean_text(entry.get("summary") or entry.get("description"))
        published = clean_text(entry.get("published") or entry.get("updated") or entry.get("created"))
        lookup[key] = {"title": title, "summary": summary, "published": published, "url": link}

    return lookup


def _good_paragraph(text: str, title: str = "") -> bool:
    text = clean_text(text)
    if len(text) < 35:
        return False
    lowered = text.lower()
    if title and lowered == clean_text(title).lower():
        return False
    if any(marker in lowered for marker in BOILERPLATE):
        return False
    return True


def _dedupe_paragraphs(values: list[str], title: str = "") -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = clean_text(value)
        key = re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()
        if not key or key in seen or not _good_paragraph(text, title):
            continue
        seen.add(key)
        result.append(text)
    return result


def _jsonld_article_body(soup: BeautifulSoup) -> list[str]:
    candidates: list[str] = []

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            body = value.get("articleBody")
            if isinstance(body, str) and len(body) >= 320:
                candidates.append(body)
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    for script in soup.select("script[type='application/ld+json']"):
        try:
            walk(json.loads(script.string or script.get_text() or ""))
        except Exception:
            continue

    paragraphs: list[str] = []
    for body in candidates:
        paragraphs.extend(re.split(r"(?:\r?\n){2,}", body))
    return paragraphs


def _extract_cbc_body(page_html: str, title: str) -> tuple[list[str], str, str]:
    soup = BeautifulSoup(page_html, "html.parser")
    for node in soup.select("script, style, nav, footer, aside, form, [class*='related'], [class*='newsletter'], [class*='advert']"):
        node.decompose()

    roots = [
        soup.select_one("[itemprop='articleBody']"),
        soup.select_one("[data-cy='storyWrapper']"),
        soup.select_one(".story-content"),
        soup.select_one("article"),
        soup.select_one("main"),
    ]
    paragraphs: list[str] = []
    for root in roots:
        if root is None:
            continue
        found = _dedupe_paragraphs([p.get_text(" ", strip=True) for p in root.select("p")], title)
        if sum(len(p.split()) for p in found) >= 90:
            paragraphs = found
            break

    if sum(len(p.split()) for p in paragraphs) < 90:
        paragraphs = _dedupe_paragraphs(_jsonld_article_body(soup), title)

    if sum(len(p.split()) for p in paragraphs) < 90:
        try:
            text = extract(page_html, include_comments=False, include_tables=False, favor_precision=True) or ""
        except Exception:
            text = ""
        paragraphs = _dedupe_paragraphs(re.split(r"\n+", text), title)

    image = ""
    image_meta = soup.select_one("meta[property='og:image'], meta[name='twitter:image']")
    if image_meta:
        image = clean_text(image_meta.get("content"))

    author = ""
    author_meta = soup.select_one("meta[name='author'], meta[property='article:author']")
    if author_meta:
        author = clean_text(author_meta.get("content"))

    return paragraphs, image, author


def _decode_cbc_url(google_url: str) -> str:
    parsed = urlparse(google_url)
    parts = [part for part in parsed.path.split("/") if part]
    if parsed.netloc.lower() != "news.google.com" or len(parts) < 2 or parts[-2] not in {"articles", "read"}:
        return ""
    encoded_id = parts[-1]

    signature = ""
    timestamp = ""
    for prefix in ("articles", "rss/articles"):
        try:
            response = requests.get(
                f"https://news.google.com/{prefix}/{encoded_id}",
                headers=HEADERS,
                timeout=(3, 6),
            )
            response.raise_for_status()
            node = BeautifulSoup(response.text, "html.parser").select_one("c-wiz > div[jscontroller]")
            if node:
                signature = clean_text(node.get("data-n-a-sg"))
                timestamp = clean_text(node.get("data-n-a-ts"))
            if signature and timestamp:
                break
        except Exception:
            continue

    if not signature or not timestamp:
        return ""

    rpc_payload = [
        "Fbv4je",
        f'["garturlreq",[["X","X",["X","X"],null,null,1,1,"CA:en",null,1,null,null,null,null,null,0,1],"X","X",1,[1,1,1],1,1,null,0,0,null,0],"{encoded_id}",{timestamp},"{signature}"]',
    ]
    try:
        response = requests.post(
            "https://news.google.com/_/DotsSplashUi/data/batchexecute",
            headers={
                **HEADERS,
                "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
            },
            data=f"f.req={quote(json.dumps([[rpc_payload]]))}",
            timeout=(3, 6),
        )
        response.raise_for_status()
    except Exception:
        return ""

    decoded_url = ""
    for chunk in response.text.split("\n\n"):
        try:
            rows = json.loads(chunk)
        except Exception:
            continue
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, list) or len(row) < 3 or not isinstance(row[2], str):
                continue
            try:
                payload = json.loads(row[2])
            except Exception:
                continue
            if isinstance(payload, list) and len(payload) > 1 and isinstance(payload[1], str):
                decoded_url = payload[1]
                break
        if decoded_url:
            break

    url = clean_text(decoded_url)
    target = urlparse(url)
    host = target.netloc.lower().split(":", 1)[0]
    if host not in {"cbc.ca", "www.cbc.ca"} and not host.endswith(".cbc.ca"):
        return ""
    if "/news/canada/london/" not in target.path.lower():
        return ""
    return url


def _article_id(url: str) -> str:
    matches = CBC_ID.findall(urlparse(url).path)
    return matches[-1] if matches else ""


def _hydrate_cbc_story(google_url: str, title: str) -> dict[str, Any] | None:
    real_url = _decode_cbc_url(google_url)
    if not real_url:
        return None

    article_id = _article_id(real_url)
    attempts: list[tuple[str, str]] = []
    if article_id:
        attempts.append(("amp-cache", f"https://www-cbc-ca.cdn.ampproject.org/c/s/www.cbc.ca/amp/{article_id}"))
    attempts.append(("direct", real_url))
    if article_id:
        attempts.append(("direct-amp", f"https://www.cbc.ca/amp/{article_id}"))

    for method, url in attempts:
        try:
            response = requests.get(url, headers=HEADERS, timeout=(3, 8))
            if response.status_code >= 400 or len(response.content) < 400:
                continue
            paragraphs, image, author = _extract_cbc_body(response.text, title)
        except Exception:
            continue

        word_count = sum(len(p.split()) for p in paragraphs)
        if word_count < 90:
            continue
        return {
            "url": real_url,
            "full": True,
            "paragraphs": paragraphs,
            "content_blocks": [{"type": "paragraph", "text": p} for p in paragraphs],
            "content": "\n\n".join(paragraphs),
            "word_count": word_count,
            "image": image,
            "author": author,
            "method": method,
        }

    return {"url": real_url, "full": False}


def _already_full(value: dict[str, Any]) -> bool:
    paragraphs = value.get("paragraphs") or []
    if not isinstance(paragraphs, list):
        paragraphs = []
    word_count = int(value.get("word_count") or 0)
    if not word_count:
        word_count = sum(len(clean_text(p).split()) for p in paragraphs)
    return value.get("content_status") == "full" and word_count >= 90 and len(paragraphs) >= 2


def _collect_targets(value: Any, lookup: dict[str, dict[str, str]], targets: dict[str, tuple[str, str]]) -> None:
    if isinstance(value, dict):
        if value.get("source") == "CBC News London" and str(value.get("ingestion_path") or "").startswith("cbc-google-news"):
            discovery_url = clean_text(value.get("discovery_url") or value.get("url"))
            key = google_story_key(discovery_url)
            source = lookup.get(key)
            if key and source:
                targets.setdefault(key, (discovery_url, source["title"]))
        for child in value.values():
            _collect_targets(child, lookup, targets)
    elif isinstance(value, list):
        for child in value:
            _collect_targets(child, lookup, targets)


def _hydrate_targets(targets: dict[str, tuple[str, str]]) -> dict[str, dict[str, Any] | None]:
    cache: dict[str, dict[str, Any] | None] = {}
    if not targets:
        return cache
    workers = min(4, len(targets))
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(_hydrate_cbc_story, url, title): key
            for key, (url, title) in targets.items()
        }
        for future in as_completed(futures):
            key = futures[future]
            try:
                cache[key] = future.result()
            except Exception:
                cache[key] = None
    return cache


def repair_object(
    value: Any,
    lookup: dict[str, dict[str, str]],
    hydrate_cache: dict[str, dict[str, Any] | None],
) -> tuple[int, int, int]:
    repaired = 0
    resolved = 0
    hydrated = 0
    if isinstance(value, dict):
        if value.get("source") == "CBC News London" and str(value.get("ingestion_path") or "").startswith("cbc-google-news"):
            discovery_url = clean_text(value.get("discovery_url") or value.get("url"))
            key = google_story_key(discovery_url)
            source = lookup.get(key)
            if source:
                value["title"] = source["title"]
                if source["summary"]:
                    value["summary"] = source["summary"]
                value["author"] = value.get("author") or "CBC News"
                value["discovery_url"] = discovery_url
                value.pop("scrape_error", None)
                repaired += 1

                body = hydrate_cache.get(key)
                if body and body.get("url"):
                    value["url"] = body["url"]
                    resolved += 1

                if _already_full(value):
                    pass
                elif body and body.get("full"):
                    value["paragraphs"] = body["paragraphs"]
                    value["content_blocks"] = body["content_blocks"]
                    value["content"] = body["content"]
                    value["word_count"] = body["word_count"]
                    value["content_status"] = "full"
                    value["ingestion_path"] = f"cbc-google-news-{body['method']}"
                    value["scraped_at"] = datetime.now(timezone.utc).isoformat()
                    if body.get("image") and not value.get("image"):
                        value["image"] = body["image"]
                    if body.get("author"):
                        value["author"] = body["author"]
                    quality = value.get("quality") if isinstance(value.get("quality"), dict) else {}
                    quality.update({
                        "score": max(70, int(quality.get("score") or 0)),
                        "grade": "good",
                        "method": f"dom:cbc:{body['method']}",
                        "text_blocks": len(body["paragraphs"]),
                        "rich_blocks": 0,
                        "image_blocks": 0,
                    })
                    value["quality"] = quality
                    hydrated += 1
                else:
                    value["content_status"] = "summary"
                    value["paragraphs"] = []
                    value["content_blocks"] = []
                    value["content"] = ""
                    value["word_count"] = 0
                    value["scraped_at"] = datetime.now(timezone.utc).isoformat()
                    quality = value.get("quality") if isinstance(value.get("quality"), dict) else {}
                    quality.update({
                        "score": 30,
                        "grade": "poor",
                        "method": "rss:google-cbc-fallback",
                        "text_blocks": 0,
                        "rich_blocks": 0,
                        "image_blocks": 0,
                    })
                    value["quality"] = quality

        for child in list(value.values()):
            child_repaired, child_resolved, child_hydrated = repair_object(child, lookup, hydrate_cache)
            repaired += child_repaired
            resolved += child_resolved
            hydrated += child_hydrated
    elif isinstance(value, list):
        for child in value:
            child_repaired, child_resolved, child_hydrated = repair_object(child, lookup, hydrate_cache)
            repaired += child_repaired
            resolved += child_resolved
            hydrated += child_hydrated
    return repaired, resolved, hydrated


def main() -> int:
    if not NEWS_PATH.exists():
        print("CBC fallback repair skipped: data/news.json does not exist", file=sys.stderr)
        return 0

    try:
        lookup = load_google_cbc()
    except Exception as exc:
        print(f"CBC fallback repair skipped: could not refresh Google News metadata: {exc}", file=sys.stderr)
        return 0

    if not lookup:
        print("CBC fallback repair skipped: no CBC Google News entries found", file=sys.stderr)
        return 0

    payload = json.loads(NEWS_PATH.read_text(encoding="utf-8"))
    targets: dict[str, tuple[str, str]] = {}
    _collect_targets(payload, lookup, targets)
    hydrate_cache = _hydrate_targets(targets)
    repaired, resolved, hydrated = repair_object(payload, lookup, hydrate_cache)
    if repaired:
        NEWS_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        f"CBC fallback repair: {repaired} record(s) normalized, "
        f"{resolved} publisher URL(s) resolved, {hydrated} record(s) hydrated with full article bodies "
        f"across {len(targets)} unique CBC fallback stories"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
