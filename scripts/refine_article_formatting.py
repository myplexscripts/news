from __future__ import annotations

import html
import json
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup, NavigableString, Tag

from fetch_news import author_image_text, clean_text, fetch_html, valid_article_image

ROOT = Path(__file__).resolve().parents[1]
NEWS_PATH = ROOT / "data" / "news.json"
FORMAT_SCHEMA = 2
MAX_PER_RUN = max(8, int(os.getenv("FORMAT_MAX_PER_RUN", "36")))
RECENT_HOURS = max(24, int(os.getenv("FORMAT_RECENT_HOURS", "120")))
WORKERS = max(2, min(8, int(os.getenv("FORMAT_WORKERS", "6"))))
MIN_WORDS = 70
CBC_ID = re.compile(r"(?<!\d)([19]\.\d{5,})(?!\d)")
MARKDOWN_IMAGE = re.compile(r"!\[([^\]]*)\]\((https?://[^)\s]+)(?:\s+['\"][^'\"]*['\"])?\)", re.I)
MARKDOWN_HEADING = re.compile(r"^\s{0,3}(#{1,6})\s+(.+?)\s*#*\s*$")
MARKDOWN_UL = re.compile(r"^\s{0,3}[-*+]\s+(.+)$")
MARKDOWN_OL = re.compile(r"^\s{0,3}\d+[.)]\s+(.+)$")
MARKDOWN_QUOTE = re.compile(r"^\s{0,3}>\s?(.*)$")
MARKDOWN_STRONG = re.compile(r"^\s*\*\*(.+?)\*\*\s*$")

CBC_HEADERS = {
    "User-Agent": "LondonNews/1.0 (+https://myplexscripts.github.io/news/)",
    "Accept": "text/plain",
    "X-Retain-Links": "text",
    "X-Retain-Images": "all",
    "X-Retain-Media": "none",
    "X-With-Images-Summary": "all",
}

GENERIC_ROOTS = (
    "[itemprop='articleBody']",
    "[data-testid='article-body']",
    "article .article-body",
    "article .article-content",
    "article .story-body",
    "article .entry-content",
    "article .post-content",
    "article",
    "main",
)

GENERIC_REMOVE = (
    "script", "style", "noscript", "nav", "footer", "form", "button",
    "aside", "[role='complementary']", "[aria-hidden='true']",
    "[class*='advert']", "[class*='newsletter']", "[class*='subscribe']",
    "[class*='related']", "[class*='recommend']", "[class*='recirc']",
    "[class*='read-more']", "[class*='readmore']", "[class*='outbrain']",
    "[class*='taboola']", "[data-testid*='related']", "[data-testid*='recommend']",
)

BOILERPLATE = (
    "sign up for",
    "subscribe to",
    "advertisement",
    "recommended for you",
    "related stories",
    "related story",
    "more from",
    "download our app",
    "follow us on",
)


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


def text_key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", clean_text(str(value or "")).lower()).strip()


def is_boilerplate(value: Any, title: str = "") -> bool:
    text = clean_text(str(value or ""))
    if not text:
        return True
    key = text.lower()
    if title and text_key(text) == text_key(title):
        return True
    return any(marker in key for marker in BOILERPLATE)


def safe_inline_url(value: Any, base_url: str) -> str:
    raw = str(value or "").strip()
    if not raw or raw.startswith(("javascript:", "data:", "blob:")):
        return ""
    resolved = urljoin(base_url, raw)
    parsed = urlparse(resolved)
    if parsed.scheme not in {"http", "https"}:
        return ""
    return resolved


def serialize_inline(node: Any, base_url: str) -> str:
    if isinstance(node, NavigableString):
        return html.escape(str(node), quote=False)
    if not isinstance(node, Tag):
        return ""

    name = node.name.lower()
    children = "".join(serialize_inline(child, base_url) for child in node.children)
    if name == "br":
        return "<br>"
    if name in {"strong", "b"}:
        return f"<strong>{children}</strong>"
    if name in {"em", "i"}:
        return f"<em>{children}</em>"
    if name in {"sup", "sub"}:
        return f"<{name}>{children}</{name}>"
    if name == "a":
        href = safe_inline_url(node.get("href"), base_url)
        if not href:
            return children
        safe_href = html.escape(href, quote=True)
        return f'<a href="{safe_href}" target="_blank" rel="noopener noreferrer">{children}</a>'
    if name == "span":
        style = str(node.get("style") or "").lower().replace(" ", "")
        if "font-weight:bold" in style or re.search(r"font-weight:(?:[6-9]00)", style):
            return f"<strong>{children}</strong>"
        if "font-style:italic" in style:
            return f"<em>{children}</em>"
    return children


def inline_html(tag: Tag, base_url: str) -> str:
    return "".join(serialize_inline(child, base_url) for child in tag.children).strip()


def markdown_inline_html(value: str, base_url: str) -> str:
    raw = html.unescape(str(value or ""))
    placeholders: list[str] = []

    def hold(fragment: str) -> str:
        token = f"@@INLINE{len(placeholders)}@@"
        placeholders.append(fragment)
        return token

    def link_repl(match: re.Match[str]) -> str:
        label = match.group(1)
        href = safe_inline_url(match.group(2), base_url)
        if not href:
            return label
        label_html = html.escape(label, quote=False)
        return hold(f'<a href="{html.escape(href, quote=True)}" target="_blank" rel="noopener noreferrer">{label_html}</a>')

    raw = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", link_repl, raw)
    escaped = html.escape(raw, quote=False)
    escaped = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)
    escaped = re.sub(r"__(.+?)__", r"<strong>\1</strong>", escaped)
    escaped = re.sub(r"(?<!\*)\*([^*\n]+?)\*(?!\*)", r"<em>\1</em>", escaped)
    escaped = re.sub(r"(?<!\w)_([^_\n]+?)_(?!\w)", r"<em>\1</em>", escaped)
    for index, fragment in enumerate(placeholders):
        escaped = escaped.replace(f"@@INLINE{index}@@", fragment)
    return escaped.strip()


def normalize_image_key(url: str) -> str:
    try:
        parsed = urlparse(url)
        return f"{parsed.netloc.lower()}{parsed.path.lower()}".rstrip("/")
    except Exception:
        return str(url or "").split("?", 1)[0].lower().rstrip("/")


def srcset_candidates(value: Any) -> list[tuple[int, str]]:
    candidates: list[tuple[int, str]] = []
    for part in str(value or "").split(","):
        bits = part.strip().split()
        if not bits:
            continue
        score = 1
        if len(bits) > 1:
            raw_score = re.sub(r"[^0-9.]", "", bits[1])
            try:
                score = int(float(raw_score) * (1000 if bits[1].endswith("x") else 1))
            except Exception:
                score = 1
        candidates.append((score, bits[0]))
    return candidates


def int_attr(value: Any) -> int:
    try:
        return int(re.sub(r"\D", "", str(value or "0")) or "0")
    except Exception:
        return 0


def best_img_url(img: Tag, base_url: str) -> str:
    candidates: list[tuple[int, str]] = []
    picture = img.find_parent("picture")
    if isinstance(picture, Tag):
        for source in picture.find_all("source"):
            if not isinstance(source, Tag):
                continue
            candidates.extend(srcset_candidates(source.get("srcset") or source.get("data-srcset")))
            for attr in ("data-src", "data-lazy-src", "data-original", "src"):
                if source.get(attr):
                    candidates.append((1, str(source.get(attr))))
    for attr in ("data-src", "data-lazy-src", "data-original", "data-full-src", "data-zoom-src", "data-image", "data-image-src", "data-img-url", "src"):
        if img.get(attr):
            candidates.append((1, str(img.get(attr))))
    candidates.extend(srcset_candidates(img.get("srcset") or img.get("data-srcset")))
    for _, candidate in sorted(candidates, key=lambda item: item[0], reverse=True):
        if candidate and not candidate.startswith(("data:", "blob:")):
            return urljoin(base_url, candidate)
    return ""


def choose_root(soup: BeautifulSoup) -> Tag | None:
    candidates: list[tuple[int, Tag]] = []
    for priority, selector in enumerate(GENERIC_ROOTS):
        for candidate in soup.select(selector):
            if not isinstance(candidate, Tag):
                continue
            paragraphs = candidate.select("p")
            text_chars = sum(len(clean_text(p.get_text(" ", strip=True))) for p in paragraphs)
            if text_chars < 160:
                continue
            link_chars = sum(len(clean_text(a.get_text(" ", strip=True))) for a in candidate.select("a"))
            score = text_chars + len(paragraphs) * 80 - int(link_chars * 0.25) - priority * 5
            candidates.append((score, candidate))
    return max(candidates, key=lambda item: item[0])[1] if candidates else None


def extract_dom_blocks(raw: str, final_url: str, title: str, hero_url: str = "") -> list[dict[str, Any]]:
    soup = BeautifulSoup(raw, "html.parser")
    root = choose_root(soup)
    if root is None:
        return []
    clone = BeautifulSoup(str(root), "html.parser")
    clone_root = clone.find()
    if not isinstance(clone_root, Tag):
        return []

    for selector in GENERIC_REMOVE:
        try:
            for node in clone_root.select(selector):
                node.decompose()
        except Exception:
            continue

    blocks: list[dict[str, Any]] = []
    seen_text: set[str] = set()
    seen_images: set[str] = set()
    hero_key = normalize_image_key(hero_url)

    for node in clone_root.find_all(["h2", "h3", "h4", "p", "blockquote", "ul", "ol", "figure", "img"], recursive=True):
        if not isinstance(node, Tag):
            continue
        if node.name == "p" and node.find_parent(["blockquote", "li", "figcaption"]):
            continue
        if node.name in {"ul", "ol"} and node.find_parent(["ul", "ol"]):
            continue
        if node.name == "img" and node.find_parent("figure"):
            continue

        if node.name in {"h2", "h3", "h4", "p", "blockquote"}:
            text = clean_text(node.get_text(" ", strip=True))
            minimum = 4 if node.name.startswith("h") else 12
            key = text_key(text)
            if len(text) < minimum or is_boilerplate(text, title) or not key or key in seen_text:
                continue
            seen_text.add(key)
            rendered = inline_html(node, final_url)
            block: dict[str, Any] = {"text": text}
            if rendered:
                block["html"] = rendered
            if node.name.startswith("h"):
                block.update({"type": "heading", "level": 3 if node.name in {"h3", "h4"} else 2})
            elif node.name == "blockquote":
                block["type"] = "quote"
            else:
                block["type"] = "paragraph"
            blocks.append(block)
            continue

        if node.name in {"ul", "ol"}:
            items: list[dict[str, str]] = []
            item_texts: list[str] = []
            for li in node.find_all("li", recursive=False):
                text = clean_text(li.get_text(" ", strip=True))
                if len(text) < 2 or is_boilerplate(text, title):
                    continue
                item = {"text": text, "html": inline_html(li, final_url) or html.escape(text)}
                items.append(item)
                item_texts.append(text)
            joined_key = text_key(" ".join(item_texts))
            if items and joined_key and joined_key not in seen_text:
                seen_text.add(joined_key)
                blocks.append({"type": "list", "ordered": node.name == "ol", "items": items})
            continue

        img = node.find("img") if node.name == "figure" else node if node.name == "img" else None
        if not isinstance(img, Tag):
            continue
        url = best_img_url(img, final_url)
        key = normalize_image_key(url)
        if not url or not key or key == hero_key or key in seen_images:
            continue
        lower = url.lower()
        if lower.endswith((".svg", ".gif")) or any(token in lower for token in ("logo", "avatar", "icon", "sprite", "tracking", "pixel")):
            continue
        seen_images.add(key)
        figure = img.find_parent("figure")
        caption = ""
        if isinstance(figure, Tag):
            cap = figure.find("figcaption")
            if isinstance(cap, Tag):
                caption = clean_text(cap.get_text(" ", strip=True), 320)
        blocks.append({
            "type": "image",
            "url": url,
            "alt": clean_text(img.get("alt") or "", 180),
            "caption": caption,
            **({"width": int_attr(img.get("width"))} if int_attr(img.get("width")) else {}),
            **({"height": int_attr(img.get("height"))} if int_attr(img.get("height")) else {}),
        })

    return blocks


def cbc_story_id(url: str) -> str:
    matches = CBC_ID.findall(urlparse(str(url or "")).path)
    return matches[-1] if matches else ""


def parse_cbc_markdown(raw: str, title: str, hero_url: str = "") -> list[dict[str, Any]]:
    marker = re.search(r"^Markdown Content:\s*$", raw, flags=re.I | re.M)
    body = raw[marker.end():] if marker else raw
    lines = body.splitlines()
    blocks: list[dict[str, Any]] = []
    seen: set[str] = set()
    seen_images: set[str] = set()
    hero_key = normalize_image_key(hero_url)
    paragraph_lines: list[str] = []
    index = 0

    def append_text(kind: str, raw_text: str, level: int = 2) -> None:
        text = clean_text(re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", raw_text).replace("**", "").replace("__", "").replace("`", ""))
        text = re.sub(r"(?<!\w)[*_](.+?)[*_](?!\w)", r"\1", text)
        key = text_key(text)
        minimum = 4 if kind == "heading" else 12
        if len(text) < minimum or is_boilerplate(text, title) or not key or key in seen:
            return
        seen.add(key)
        block: dict[str, Any] = {"type": kind, "text": text, "html": markdown_inline_html(raw_text, "https://www.cbc.ca")}
        if kind == "heading":
            block["level"] = 3 if level >= 3 else 2
        blocks.append(block)

    def flush() -> None:
        nonlocal paragraph_lines
        if not paragraph_lines:
            return
        raw_text = " ".join(line.strip() for line in paragraph_lines if line.strip())
        paragraph_lines = []
        append_text("paragraph", raw_text)

    while index < len(lines):
        stripped = lines[index].strip()
        if not stripped:
            flush()
            index += 1
            continue

        heading = MARKDOWN_HEADING.match(stripped)
        if heading:
            flush()
            append_text("heading", heading.group(2), len(heading.group(1)))
            index += 1
            continue

        strong = MARKDOWN_STRONG.match(stripped)
        if strong:
            flush()
            append_text("paragraph", stripped)
            index += 1
            continue

        image_matches = list(MARKDOWN_IMAGE.finditer(stripped))
        if image_matches:
            remaining = MARKDOWN_IMAGE.sub("", stripped).strip()
            if not remaining:
                flush()
                for match in image_matches:
                    url = html.unescape(match.group(2).strip())
                    key = normalize_image_key(url)
                    if not key or key == hero_key or key in seen_images:
                        continue
                    if not valid_article_image(url) or author_image_text(match.group(1)):
                        continue
                    seen_images.add(key)
                    blocks.append({"type": "image", "url": url, "alt": clean_text(match.group(1)), "caption": ""})
                index += 1
                continue

        quote = MARKDOWN_QUOTE.match(stripped)
        if quote:
            flush()
            quote_lines: list[str] = []
            while index < len(lines):
                match = MARKDOWN_QUOTE.match(lines[index].strip())
                if not match:
                    break
                quote_lines.append(match.group(1))
                index += 1
            append_text("quote", " ".join(quote_lines))
            continue

        ul = MARKDOWN_UL.match(stripped)
        ol = MARKDOWN_OL.match(stripped)
        if ul or ol:
            flush()
            ordered = bool(ol)
            items: list[dict[str, str]] = []
            raw_joined: list[str] = []
            while index < len(lines):
                current = lines[index].strip()
                match = MARKDOWN_OL.match(current) if ordered else MARKDOWN_UL.match(current)
                if not match:
                    break
                raw_item = match.group(1).strip()
                text = clean_text(re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", raw_item).replace("**", ""))
                if text:
                    items.append({"text": text, "html": markdown_inline_html(raw_item, "https://www.cbc.ca")})
                    raw_joined.append(text)
                index += 1
            key = text_key(" ".join(raw_joined))
            if items and key and key not in seen:
                seen.add(key)
                blocks.append({"type": "list", "ordered": ordered, "items": items})
            continue

        paragraph_lines.append(stripped)
        index += 1

    flush()
    return blocks


def fetch_cbc_blocks(story: dict[str, Any]) -> tuple[list[dict[str, Any]], str]:
    story_id = cbc_story_id(story.get("url", ""))
    if not story_id:
        return [], "cbc:no-id"
    reader_url = f"https://r.jina.ai/http://www.cbc.ca/lite/story/{story_id}"
    try:
        response = requests.get(reader_url, headers=CBC_HEADERS, timeout=(4, 24))
        response.raise_for_status()
    except Exception as exc:
        return [], f"cbc:{type(exc).__name__}"
    if len(response.text) < 500:
        return [], "cbc:short"
    return parse_cbc_markdown(response.text, clean_text(story.get("title", "")), clean_text(story.get("image", ""))), "cbc:jina-format-v1"


def block_word_count(blocks: list[dict[str, Any]]) -> int:
    total = 0
    for block in blocks:
        kind = block.get("type")
        if kind in {"paragraph", "heading", "quote"}:
            total += words(block.get("text"))
        elif kind == "list":
            for item in block.get("items", []):
                total += words(item.get("text") if isinstance(item, dict) else item)
    return total


def text_from_blocks(blocks: list[dict[str, Any]]) -> tuple[list[str], str]:
    paragraphs: list[str] = []
    for block in blocks:
        kind = block.get("type")
        if kind in {"paragraph", "quote"} and block.get("text"):
            paragraphs.append(clean_text(block.get("text")))
        elif kind == "list":
            for item in block.get("items", []):
                text = clean_text(item.get("text") if isinstance(item, dict) else item)
                if text:
                    paragraphs.append(text)
    return paragraphs, "\n\n".join(paragraphs)


def body_coverage_ok(story: dict[str, Any], blocks: list[dict[str, Any]]) -> bool:
    extracted = block_word_count(blocks)
    if extracted < MIN_WORDS:
        return False
    existing = int(story.get("word_count") or 0) or words(story.get("content"))
    if existing <= 0:
        return True
    return extracted >= max(MIN_WORDS, int(existing * 0.75))


def process_story(story: dict[str, Any]) -> tuple[list[dict[str, Any]], str]:
    source = clean_text(story.get("source", ""))
    if source == "CBC News London":
        blocks, method = fetch_cbc_blocks(story)
        if body_coverage_ok(story, blocks):
            return blocks, method
    try:
        raw, final_url = fetch_html(clean_text(story.get("url", "")))
    except Exception as exc:
        return [], f"dom:{type(exc).__name__}"
    blocks = extract_dom_blocks(raw, final_url, clean_text(story.get("title", "")), clean_text(story.get("image", "")))
    return blocks, "dom:formatted-generic-v1"


def story_needs_work(story: dict[str, Any], now: datetime) -> bool:
    if not isinstance(story, dict) or not story.get("url") or not story.get("title"):
        return False
    if story.get("content_status") not in {"full", "partial"}:
        return False
    if int(story.get("format_schema") or 0) >= FORMAT_SCHEMA:
        return False
    attempted = parse_datetime(story.get("format_attempted_at"))
    return not attempted or now - attempted >= timedelta(hours=6)


def priority(story: dict[str, Any], now: datetime) -> tuple[int, float]:
    published = parse_datetime(story.get("published"))
    age_hours = (now - published).total_seconds() / 3600 if published else 99999
    return (1 if age_hours <= RECENT_HOURS else 0, -age_hours)


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
        print("Inline article formatting already current")
        return 0

    accepted = 0
    failed = 0
    by_id = {str(story.get("id") or ""): story for story in targets}
    with ThreadPoolExecutor(max_workers=WORKERS) as executor:
        futures = {executor.submit(process_story, story): str(story.get("id") or "") for story in targets}
        for future in as_completed(futures):
            story = by_id[futures[future]]
            story["format_attempted_at"] = now.isoformat()
            try:
                blocks, method = future.result()
            except Exception as exc:
                story["format_method"] = f"error:{type(exc).__name__}"
                failed += 1
                continue
            if not body_coverage_ok(story, blocks):
                story["format_method"] = method
                failed += 1
                continue
            paragraphs, text = text_from_blocks(blocks)
            if not paragraphs:
                failed += 1
                continue
            story["content_blocks"] = blocks
            story["paragraphs"] = paragraphs
            story["content"] = text
            story["word_count"] = words(text)
            story["format_schema"] = FORMAT_SCHEMA
            story["format_method"] = method
            story["formatted_at"] = utc_now().isoformat()
            accepted += 1

    payload["format_schema"] = FORMAT_SCHEMA
    payload["format_enriched_at"] = utc_now().isoformat()
    NEWS_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Inline article formatting: {accepted} accepted, {failed} deferred, {len(targets)} attempted")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
