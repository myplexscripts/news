from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup, Tag

ROOT = Path(__file__).resolve().parents[1]
NEWS_PATH = ROOT / "data" / "news.json"
SOURCE = "London Police Service"
SCHEMA = 1
HEADERS = {
    "User-Agent": "LondonNews/1.0 (+https://myplexscripts.github.io/news/)",
    "Accept-Language": "en-CA,en;q=0.9",
}

TAXONOMY = {
    "general releases",
    "caught on camera",
    "positions",
    "recruiting events",
    "all categories",
    "subscribe",
}
STOP_PREFIXES = (
    "for media inquiries",
    "for media enquiries",
    "media relations officer",
    "media relations unit",
    "contact media relations",
)


def clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", clean_text(value).lower()).strip()


def is_taxonomy(value: Any) -> bool:
    return key(value) in TAXONOMY


def is_start_paragraph(value: str) -> bool:
    return bool(re.match(r"(?i)^(?:update\s*[-:–—]\s*)?london,?\s+(?:on|ont\.)\s*\(", clean_text(value)))


def is_stop(value: str) -> bool:
    lowered = key(value)
    return any(lowered.startswith(prefix) for prefix in STOP_PREFIXES)


def full_govstack_image(url: str, base_url: str) -> str:
    absolute = urljoin(base_url, clean_text(url))
    parsed = urlparse(absolute)
    if "govstack.com" not in parsed.netloc.lower() or "/londonpolice-018-ca/media/" not in parsed.path.lower():
        return absolute
    query = [
        (name, value)
        for name, value in parse_qsl(parsed.query, keep_blank_values=True)
        if name.lower() not in {"rmode", "width", "height", "quality", "format"}
    ]
    return urlunparse(parsed._replace(query=urlencode(query), fragment=""))


def valid_photo(img: Tag, base_url: str) -> tuple[str, str]:
    src = img.get("data-src") or img.get("src") or ""
    url = full_govstack_image(str(src), base_url)
    if not url:
        return "", ""
    lower = url.lower()
    if lower.endswith((".svg", ".gif")):
        return "", ""
    if any(marker in lower for marker in ("logo", "icon", "facebook", "instagram", "youtube", "twitter", "shoulder_flash")):
        return "", ""
    alt = clean_text(img.get("alt"))
    parent_classes = " ".join(img.parent.get("class", []) if isinstance(img.parent, Tag) else []).lower()
    if "image" not in parent_classes and not alt:
        return "", ""
    return url, alt


def strip_title_prefix(text: str, title: str) -> str:
    text = clean_text(text)
    title = clean_text(title)
    if not text or not title:
        return text

    token_pattern = re.compile(r"[A-Za-z0-9]+(?:[’'][A-Za-z0-9]+)?")
    text_tokens = list(token_pattern.finditer(text))
    title_tokens = [match.group(0).lower() for match in token_pattern.finditer(title)]
    if not title_tokens or len(text_tokens) < len(title_tokens):
        return text

    leading = [match.group(0).lower() for match in text_tokens[: len(title_tokens)]]
    if leading != title_tokens:
        return text

    end = text_tokens[len(title_tokens) - 1].end()
    remainder = text[end:].lstrip(" \t|:;,.!?-–—")
    return clean_text(remainder)


def parse_article(html: str, url: str) -> dict[str, Any] | None:
    soup = BeautifulSoup(html, "html.parser")
    main = soup.find("main")
    if not isinstance(main, Tag):
        return None

    title_node = main.find("h1") or soup.find("h1")
    title = clean_text(title_node.get_text(" ", strip=True) if isinstance(title_node, Tag) else "")

    blocks: list[dict[str, Any]] = []
    paragraphs: list[str] = []
    photos: list[dict[str, str]] = []
    seen_text: set[str] = set()
    seen_images: set[str] = set()
    started = False

    for node in main.find_all(["h2", "h3", "p", "blockquote", "ul", "ol", "figure", "img"], recursive=True):
        if not isinstance(node, Tag):
            continue
        if node.name == "p" and node.find_parent(["blockquote", "li", "figcaption"]):
            continue
        if node.name in {"ul", "ol"} and node.find_parent(["ul", "ol"]):
            continue
        if node.name == "img" and node.find_parent("figure"):
            continue

        if node.name in {"h2", "h3", "p", "blockquote"}:
            text = clean_text(node.get_text(" ", strip=True))
            if not text or is_taxonomy(text):
                continue
            if is_stop(text):
                break
            if re.fullmatch(r"\d{2}-\d{4,}", text):
                continue

            if not started:
                if node.name == "p" and is_start_paragraph(text):
                    started = True
                elif node.name in {"h2", "h3"}:
                    candidate = strip_title_prefix(text, title)
                    if candidate and not is_taxonomy(candidate):
                        if len(candidate) <= 140:
                            blocks.append({"type": "heading", "level": 3, "text": candidate})
                    continue
                else:
                    continue

            text = strip_title_prefix(text, title)
            normalized = key(text)
            if not text or is_taxonomy(text) or normalized in seen_text:
                continue
            seen_text.add(normalized)

            if node.name == "p":
                blocks.append({"type": "paragraph", "text": text})
                paragraphs.append(text)
            elif node.name in {"h2", "h3"}:
                blocks.append({"type": "heading", "level": int(node.name[-1]), "text": text})
            else:
                blocks.append({"type": "quote", "text": text})
                paragraphs.append(text)
            continue

        if node.name in {"ul", "ol"}:
            if not started:
                continue
            items = []
            for li in node.find_all("li", recursive=False):
                text = clean_text(li.get_text(" ", strip=True))
                if text and not is_taxonomy(text):
                    items.append(text)
            if items:
                blocks.append({"type": "list", "ordered": node.name == "ol", "items": items})
                paragraphs.extend(items)
            continue

        img = node.find("img") if node.name == "figure" else node if node.name == "img" else None
        if not isinstance(img, Tag):
            continue
        photo_url, alt = valid_photo(img, url)
        if not photo_url or photo_url in seen_images:
            continue
        seen_images.add(photo_url)
        photos.append({"url": photo_url, "alt": alt, "caption": ""})
        if len(photos) > 1 and started:
            blocks.append({"type": "image", "url": photo_url, "alt": alt, "caption": ""})

    if len(paragraphs) < 2:
        return None

    return {
        "title": title,
        "blocks": blocks,
        "paragraphs": paragraphs,
        "photos": photos,
    }


def needs_fix(story: dict[str, Any]) -> bool:
    if story.get("source") != SOURCE:
        return False
    if story.get("lps_article_schema") != SCHEMA:
        return True
    if not story.get("image"):
        return True
    for block in story.get("content_blocks") or []:
        if isinstance(block, dict) and is_taxonomy(block.get("text", "")):
            return True
    return False


def apply_story(story: dict[str, Any], parsed: dict[str, Any]) -> bool:
    photos = parsed["photos"]
    paragraphs = parsed["paragraphs"]
    blocks = parsed["blocks"]
    text = "\n\n".join(paragraphs)

    if parsed.get("title"):
        story["title"] = parsed["title"]
    if photos:
        story["image"] = photos[0]["url"]
        story["image_alt"] = photos[0].get("alt", "")
    story["article_images"] = photos[1:]
    story["content_blocks"] = blocks
    story["paragraphs"] = paragraphs
    story["content"] = text
    story["word_count"] = len(re.findall(r"\b\w+[’'-]?\w*\b", text))
    story["content_status"] = "full" if story["word_count"] >= 80 else "partial"
    story["lps_article_schema"] = SCHEMA
    story["scraped_at"] = datetime.now(timezone.utc).isoformat()
    story.pop("scrape_error", None)

    quality = story.get("quality") if isinstance(story.get("quality"), dict) else {}
    quality.update({
        "score": max(75, int(quality.get("score") or 0)),
        "grade": "good",
        "method": "dom:police:govstack-main",
        "text_blocks": sum(1 for block in blocks if block.get("type") in {"paragraph", "heading", "quote", "list"}),
        "image_blocks": sum(1 for block in blocks if block.get("type") == "image"),
    })
    story["quality"] = quality
    return True


def main() -> int:
    if not NEWS_PATH.exists():
        return 0
    payload = json.loads(NEWS_PATH.read_text(encoding="utf-8"))
    stories = payload.get("stories") or []
    targets = [story for story in stories if isinstance(story, dict) and needs_fix(story)][:25]
    if not targets:
        print("London Police normalization: no stories need repair")
        return 0

    session = requests.Session()
    session.headers.update(HEADERS)
    repaired = 0
    images = 0
    failed = 0

    for story in targets:
        url = clean_text(story.get("url"))
        if not url or "londonpolice.ca" not in urlparse(url).netloc.lower():
            failed += 1
            continue
        try:
            response = session.get(url, timeout=(4, 18), allow_redirects=True)
            response.raise_for_status()
            parsed = parse_article(response.text, str(response.url))
            if not parsed:
                failed += 1
                continue
            apply_story(story, parsed)
            repaired += 1
            images += len(parsed["photos"])
        except Exception as exc:
            print(f"London Police repair miss: {url}: {type(exc).__name__}: {exc}")
            failed += 1

    if repaired:
        NEWS_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"London Police normalization: {repaired}/{len(targets)} stories repaired, {images} publisher photo(s) found, {failed} failed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
