from __future__ import annotations

import argparse
import html
import json
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote, urljoin, urlparse, parse_qs

import requests
from bs4 import BeautifulSoup, NavigableString, Tag

from article_source_profiles import profile_for
from fetch_news import author_image_text, fetch_html, valid_article_image

ROOT = Path(__file__).resolve().parents[1]
NEWS_PATH = ROOT / "data" / "news.json"
RICH_ARTICLE_SCHEMA = 1
DEFAULT_LIMIT = max(12, int(os.getenv("RICH_ARTICLE_LIMIT", "64")))
WORKERS = max(2, min(8, int(os.getenv("RICH_ARTICLE_WORKERS", "6"))))
MIN_WORDS = 70

READER_HEADERS = {
    "User-Agent": "LondonNews/1.0 (+https://myplexscripts.github.io/news/)",
    "Accept": "text/plain",
    "X-Retain-Links": "all",
    "X-Retain-Images": "all",
    "X-Retain-Media": "all",
    "X-With-Images-Summary": "all",
}

BLOCK_TAGS = {"p", "h2", "h3", "h4", "blockquote", "ul", "ol", "figure", "img", "iframe", "video", "audio"}
INLINE_ALLOWED = {"a", "strong", "b", "em", "i", "code", "sup", "sub", "br"}
JUNK_CONTAINER_MARKERS = (
    "advert", "sponsor", "newsletter", "subscribe", "paywall", "registration",
    "related", "recommend", "recirc", "outbrain", "taboola", "trending",
    "most-read", "most-popular", "comments", "comment-module", "share-tools",
    "social-share", "author-card", "byline-card", "promo-module", "more-stories",
)
JUNK_TEXT_MARKERS = (
    "sign up for", "subscribe to", "sign in to continue", "create an account to continue",
    "story continues below", "advertisement has not loaded", "this advertisement",
    "related stories", "recommended for you", "more from", "you may also like",
    "all rights reserved", "report an editorial error", "report a technical issue",
    "add cbc news as a preferred source", "download the cbc news app",
    "access articles from across canada with one account", "enjoy additional articles per month",
    "share this article", "share this story", "join the conversation in the comments",
)
MEDIA_LABEL_RE = re.compile(r"^(?:image|photo)\s*\|\s*", re.I)
CAPTION_RE = re.compile(r"^(?:caption|photo caption)\s*:\s*(.+)$", re.I)
PUBLISHER_META_RE = re.compile(
    r"^(?:updated|posted|published|last updated)(?:\s+[a-z .'-]+)?\s*(?:\||:)", re.I
)
TWITTER_STATUS_RE = re.compile(r"https?://(?:www\.)?(?:twitter\.com|x\.com)/[^/]+/status/(\d+)", re.I)
INSTAGRAM_RE = re.compile(r"https?://(?:www\.)?instagram\.com/(?:p|reel|tv)/([^/?#]+)", re.I)
TIKTOK_RE = re.compile(r"https?://(?:www\.)?tiktok\.com/@[^/]+/video/(\d+)", re.I)
YOUTUBE_ID_RE = re.compile(r"(?:youtu\.be/|youtube\.com/(?:watch\?v=|shorts/|embed/))([A-Za-z0-9_-]{6,})", re.I)
VIMEO_ID_RE = re.compile(r"vimeo\.com/(?:video/)?(\d+)", re.I)
MARKDOWN_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\((https?://[^)\s]+)(?:\s+['\"][^'\"]*['\"])?\)", re.I)
MARKDOWN_LINK_ONLY_RE = re.compile(r"^\s*\[([^\]]+)\]\((https?://[^)\s]+)\)\s*$", re.I)
MARKDOWN_HEADING_RE = re.compile(r"^\s{0,3}(#{1,6})\s+(.+?)\s*#*\s*$")
MARKDOWN_UL_RE = re.compile(r"^\s{0,3}[-*+]\s+(.+)$")
MARKDOWN_OL_RE = re.compile(r"^\s{0,3}\d+[.)]\s+(.+)$")
MARKDOWN_QUOTE_RE = re.compile(r"^\s{0,3}>\s?(.*)$")

SAFE_EMBED_HOSTS = {
    "www.youtube.com", "youtube.com", "www.youtube-nocookie.com", "youtube-nocookie.com",
    "player.vimeo.com", "players.brightcove.net", "www.dailymotion.com", "geo.dailymotion.com",
    "platform.twitter.com", "www.instagram.com", "www.tiktok.com", "www.facebook.com",
    "open.spotify.com", "w.soundcloud.com", "omny.fm", "player.simplecast.com",
    "cbc.ca", "www.cbc.ca", "player.cbc.ca", "gem.cbc.ca",
}


def clean(value: Any) -> str:
    return re.sub(r"\s+", " ", html.unescape(str(value or ""))).strip()


def words(value: Any) -> int:
    return len(re.findall(r"\b\w+[’'-]?\w*\b", str(value or "")))


def text_key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", clean(value).lower()).strip()


def safe_http_url(value: Any, base_url: str = "") -> str:
    raw = html.unescape(str(value or "")).strip()
    if not raw or raw.startswith(("javascript:", "data:", "blob:")):
        return ""
    resolved = urljoin(base_url, raw)
    parsed = urlparse(resolved)
    return resolved if parsed.scheme in {"http", "https"} else ""


def image_key(url: str) -> str:
    parsed = urlparse(str(url or ""))
    return f"{parsed.netloc.lower()}{parsed.path.lower()}".rstrip("/")


def srcset_best(value: Any, base_url: str = "") -> str:
    best_url = ""
    best_score = -1.0
    for part in str(value or "").split(","):
        chunk = part.strip()
        if not chunk:
            continue
        bits = chunk.split()
        url = safe_http_url(bits[0], base_url)
        if not url:
            continue
        score = 1.0
        if len(bits) > 1:
            descriptor = bits[-1].lower()
            try:
                if descriptor.endswith("w"):
                    score = float(descriptor[:-1])
                elif descriptor.endswith("x"):
                    score = float(descriptor[:-1]) * 1000
            except ValueError:
                score = 1.0
        if score >= best_score:
            best_score = score
            best_url = url
    return best_url


def image_url(node: Tag, base_url: str) -> str:
    candidates: list[str] = []
    picture = node.find_parent("picture")
    if isinstance(picture, Tag):
        for source in picture.find_all("source"):
            for attr in ("srcset", "data-srcset"):
                candidate = srcset_best(source.get(attr), base_url)
                if candidate:
                    candidates.append(candidate)
    for attr in ("srcset", "data-srcset"):
        candidate = srcset_best(node.get(attr), base_url)
        if candidate:
            candidates.append(candidate)
    for attr in ("data-src", "data-lazy-src", "data-original", "src"):
        candidate = safe_http_url(node.get(attr), base_url)
        if candidate:
            candidates.append(candidate)
    return candidates[0] if candidates else ""


def parse_dimension(value: Any) -> int | None:
    match = re.search(r"\d+", str(value or ""))
    if not match:
        return None
    try:
        parsed = int(match.group(0))
        return parsed if parsed > 0 else None
    except ValueError:
        return None


def class_text(node: Tag) -> str:
    values = [node.get("id") or "", " ".join(node.get("class") or [])]
    for parent in list(node.parents)[:3]:
        if isinstance(parent, Tag):
            values.extend([parent.get("id") or "", " ".join(parent.get("class") or [])])
    return clean(" ".join(values)).lower()


def junk_container(node: Tag) -> bool:
    key = class_text(node)
    return any(marker in key for marker in JUNK_CONTAINER_MARKERS)


def junk_text(value: Any, title: str = "") -> bool:
    text = clean(value)
    key = text.lower()
    if not text:
        return True
    if title and text_key(text) == text_key(title):
        return True
    if MEDIA_LABEL_RE.match(text) or CAPTION_RE.match(text):
        return False
    return any(marker in key for marker in JUNK_TEXT_MARKERS)


def normalize_embed_url(url: str) -> tuple[str, str, str]:
    safe = safe_http_url(url)
    if not safe:
        return "", "", ""

    match = TWITTER_STATUS_RE.search(safe)
    if match:
        return f"https://platform.twitter.com/embed/Tweet.html?id={match.group(1)}&dnt=true", "x", safe

    match = INSTAGRAM_RE.search(safe)
    if match:
        code = match.group(1)
        return f"https://www.instagram.com/p/{code}/embed/captioned/", "instagram", safe

    match = TIKTOK_RE.search(safe)
    if match:
        return f"https://www.tiktok.com/player/v1/{match.group(1)}?autoplay=0", "tiktok", safe

    match = YOUTUBE_ID_RE.search(safe)
    if match:
        return f"https://www.youtube-nocookie.com/embed/{match.group(1)}", "youtube", safe

    match = VIMEO_ID_RE.search(safe)
    if match:
        return f"https://player.vimeo.com/video/{match.group(1)}", "vimeo", safe

    parsed = urlparse(safe)
    host = parsed.netloc.lower().split(":", 1)[0]
    if host in SAFE_EMBED_HOSTS:
        provider = "publisher"
        if "spotify" in host:
            provider = "spotify"
        elif "soundcloud" in host:
            provider = "soundcloud"
        elif "brightcove" in host:
            provider = "video"
        elif "dailymotion" in host:
            provider = "video"
        elif "cbc" in host:
            provider = "video"
        return safe, provider, safe
    return "", "", ""


def social_url_from_node(node: Tag) -> str:
    for attr in ("cite", "data-instgrm-permalink", "data-url", "data-href"):
        value = safe_http_url(node.get(attr))
        if value and (TWITTER_STATUS_RE.search(value) or INSTAGRAM_RE.search(value) or TIKTOK_RE.search(value)):
            return value
    for anchor in node.find_all("a", href=True):
        value = safe_http_url(anchor.get("href"))
        if value and (TWITTER_STATUS_RE.search(value) or INSTAGRAM_RE.search(value) or TIKTOK_RE.search(value)):
            return value
    return ""


def media_block_from_node(node: Tag, base_url: str) -> dict[str, Any] | None:
    name = node.name.lower()
    if name == "blockquote":
        source_url = social_url_from_node(node)
        if source_url:
            embed, provider, original = normalize_embed_url(source_url)
            if embed:
                return {
                    "type": "media",
                    "media_type": "embed",
                    "provider": provider,
                    "url": embed,
                    "source_url": original,
                    "title": clean(node.get_text(" ", strip=True))[:180] or "Embedded post",
                }
        return None

    if name in {"video", "audio"}:
        raw = node.get("src")
        if not raw:
            source = node.find("source", src=True)
            raw = source.get("src") if isinstance(source, Tag) else ""
        url = safe_http_url(raw, base_url)
        if not url:
            return None
        block: dict[str, Any] = {
            "type": "media",
            "media_type": name,
            "url": url,
            "title": clean(node.get("title") or node.get("aria-label") or "")[:180],
        }
        if name == "video":
            poster = safe_http_url(node.get("poster"), base_url)
            if poster:
                block["poster"] = poster
        return block

    if name == "iframe":
        url = safe_http_url(node.get("src") or node.get("data-src"), base_url)
        embed, provider, original = normalize_embed_url(url)
        if not embed:
            return None
        return {
            "type": "media",
            "media_type": "embed",
            "provider": provider,
            "url": embed,
            "source_url": original,
            "title": clean(node.get("title") or node.get("aria-label") or "Embedded media")[:180],
        }
    return None


def safe_inline(node: Tag, base_url: str) -> tuple[str, str]:
    clone_soup = BeautifulSoup(str(node), "html.parser")
    clone = clone_soup.find(node.name)
    if not isinstance(clone, Tag):
        return clean(node.get_text(" ", strip=True)), ""

    for rich in clone.find_all(["img", "picture", "figure", "iframe", "video", "audio", "script", "style", "noscript"]):
        rich.decompose()

    for child in list(clone.find_all(True)):
        if child.name not in INLINE_ALLOWED:
            child.unwrap()
            continue
        attrs: dict[str, Any] = {}
        if child.name == "a":
            href = safe_http_url(child.get("href"), base_url)
            if href:
                attrs = {"href": href, "target": "_blank", "rel": "noopener noreferrer"}
            else:
                child.unwrap()
                continue
        child.attrs = attrs

    text = clean(clone.get_text(" ", strip=True))
    inner = "".join(str(value) for value in clone.contents).strip()
    return text, inner


def figure_block(node: Tag, base_url: str) -> dict[str, Any] | None:
    media = node.find(["iframe", "video", "audio", "blockquote"])
    if isinstance(media, Tag):
        block = media_block_from_node(media, base_url)
        if block:
            caption = node.find("figcaption")
            if isinstance(caption, Tag) and clean(caption.get_text(" ", strip=True)):
                block["title"] = clean(caption.get_text(" ", strip=True))[:180]
            return block

    image = node.find("img")
    if not isinstance(image, Tag):
        return None
    url = image_url(image, base_url)
    if not url or not valid_article_image(url):
        return None
    caption_node = node.find("figcaption")
    caption = clean(caption_node.get_text(" ", strip=True)) if isinstance(caption_node, Tag) else ""
    alt = clean(image.get("alt") or image.get("title") or "")
    identity = " ".join([alt, caption, class_text(image)])
    if author_image_text(identity):
        return None
    block: dict[str, Any] = {"type": "image", "url": url, "alt": alt, "caption": caption}
    width = parse_dimension(image.get("width"))
    height = parse_dimension(image.get("height"))
    if width:
        block["width"] = width
    if height:
        block["height"] = height
    return block


def image_block(node: Tag, base_url: str) -> dict[str, Any] | None:
    if node.find_parent("figure"):
        return None
    url = image_url(node, base_url)
    if not url or not valid_article_image(url):
        return None
    alt = clean(node.get("alt") or node.get("title") or "")
    if author_image_text(" ".join([alt, class_text(node)])):
        return None
    block: dict[str, Any] = {"type": "image", "url": url, "alt": alt, "caption": ""}
    width = parse_dimension(node.get("width"))
    height = parse_dimension(node.get("height"))
    if width:
        block["width"] = width
    if height:
        block["height"] = height
    return block


def root_score(node: Tag) -> float:
    text = clean(node.get_text(" ", strip=True))
    word_count = words(text)
    if word_count < 30:
        return -1
    p_count = len(node.find_all("p"))
    rich_count = len(node.find_all(["figure", "img", "iframe", "video", "audio", "blockquote"] ))
    link_words = sum(words(anchor.get_text(" ", strip=True)) for anchor in node.find_all("a"))
    density_penalty = max(0.0, (link_words / max(1, word_count)) - 0.38) * word_count * 2.5
    return word_count + p_count * 8 + rich_count * 28 - density_penalty


def select_root(soup: BeautifulSoup, source: str, url: str) -> Tag | None:
    profile = profile_for(source, url)
    candidates: list[Tag] = []
    seen: set[int] = set()
    for selector in profile.get("roots", []):
        try:
            found = soup.select(selector)
        except Exception:
            continue
        for node in found[:4]:
            if isinstance(node, Tag) and id(node) not in seen:
                candidates.append(node)
                seen.add(id(node))
    if not candidates:
        candidates = [node for node in (soup.find("article"), soup.find("main"), soup.body) if isinstance(node, Tag)]
    return max(candidates, key=root_score, default=None)


def prune_root(root: Tag, source: str, url: str) -> Tag:
    clone_soup = BeautifulSoup(str(root), "html.parser")
    clone = clone_soup.find(root.name)
    if not isinstance(clone, Tag):
        return root

    for node in clone.find_all(["script", "style", "noscript", "nav", "footer", "form"]):
        node.decompose()

    profile = profile_for(source, url)
    for selector in profile.get("remove", []):
        lowered = selector.lower().strip()
        if lowered == "aside" or any(token in lowered for token in ("video", "player", "embed", "twitter", "instagram", "tiktok")):
            continue
        try:
            for node in clone.select(selector):
                if isinstance(node, Tag):
                    node.decompose()
        except Exception:
            continue
    return clone


def append_unique(blocks: list[dict[str, Any]], block: dict[str, Any], seen_text: set[str], seen_media: set[str], title: str) -> None:
    kind = block.get("type")
    if kind in {"paragraph", "heading", "quote"}:
        text = clean(block.get("text"))
        key = text_key(text)
        if not text or junk_text(text, title) or key in seen_text:
            return
        seen_text.add(key)
        block["text"] = text
        blocks.append(block)
        return
    if kind == "list":
        items = [clean(item.get("text") if isinstance(item, dict) else item) for item in block.get("items", [])]
        items = [item for item in items if item and not junk_text(item, title)]
        key = text_key(" ".join(items))
        if not items or key in seen_text:
            return
        seen_text.add(key)
        block["items"] = items
        blocks.append(block)
        return
    if kind == "image":
        key = f"image:{image_key(str(block.get('url') or ''))}"
    else:
        key = f"media:{block.get('media_type', '')}:{str(block.get('url') or '').split('#', 1)[0]}"
    if not key or key in seen_media:
        return
    seen_media.add(key)
    blocks.append(block)


def parse_dom(raw: str, final_url: str, source: str, title: str, hero_url: str = "") -> list[dict[str, Any]]:
    soup = BeautifulSoup(raw, "html.parser")
    root = select_root(soup, source, final_url)
    if not isinstance(root, Tag):
        return []
    root = prune_root(root, source, final_url)
    blocks: list[dict[str, Any]] = []
    seen_text: set[str] = set()
    seen_media: set[str] = set()
    hero_key = image_key(hero_url) if hero_url else ""

    def walk(node: Tag) -> None:
        for child in list(node.children):
            if isinstance(child, NavigableString) or not isinstance(child, Tag):
                continue
            if junk_container(child):
                continue
            name = child.name.lower()

            if name == "figure":
                block = figure_block(child, final_url)
                if block and not (block.get("type") == "image" and image_key(str(block.get("url") or "")) == hero_key):
                    append_unique(blocks, block, seen_text, seen_media, title)
                continue

            if name in {"iframe", "video", "audio"}:
                block = media_block_from_node(child, final_url)
                if block:
                    append_unique(blocks, block, seen_text, seen_media, title)
                continue

            if name == "blockquote":
                media = media_block_from_node(child, final_url)
                if media:
                    append_unique(blocks, media, seen_text, seen_media, title)
                else:
                    text, inline = safe_inline(child, final_url)
                    if len(text) >= 12:
                        block = {"type": "quote", "text": text}
                        if inline and inline != html.escape(text):
                            block["html"] = inline
                        append_unique(blocks, block, seen_text, seen_media, title)
                continue

            if name in {"h2", "h3", "h4"}:
                text, inline = safe_inline(child, final_url)
                if len(text) >= 3:
                    block = {"type": "heading", "text": text, "level": 3 if name in {"h3", "h4"} else 2}
                    if inline and inline != html.escape(text):
                        block["html"] = inline
                    append_unique(blocks, block, seen_text, seen_media, title)
                continue

            if name == "p":
                social = social_url_from_node(child)
                if social and words(child.get_text(" ", strip=True)) <= 45:
                    embed, provider, original = normalize_embed_url(social)
                    if embed:
                        append_unique(blocks, {
                            "type": "media", "media_type": "embed", "provider": provider,
                            "url": embed, "source_url": original,
                            "title": clean(child.get_text(" ", strip=True))[:180] or "Embedded post",
                        }, seen_text, seen_media, title)
                        continue
                text, inline = safe_inline(child, final_url)
                if len(text) >= 12:
                    block = {"type": "paragraph", "text": text}
                    if inline and inline != html.escape(text):
                        block["html"] = inline
                    append_unique(blocks, block, seen_text, seen_media, title)
                for nested in child.find_all(["img", "iframe", "video", "audio"], recursive=True):
                    if nested.name == "img":
                        block = image_block(nested, final_url)
                    else:
                        block = media_block_from_node(nested, final_url)
                    if block and not (block.get("type") == "image" and image_key(str(block.get("url") or "")) == hero_key):
                        append_unique(blocks, block, seen_text, seen_media, title)
                continue

            if name in {"ul", "ol"}:
                items = [clean(li.get_text(" ", strip=True)) for li in child.find_all("li", recursive=False)]
                if items:
                    append_unique(blocks, {"type": "list", "ordered": name == "ol", "items": items}, seen_text, seen_media, title)
                continue

            if name == "img":
                block = image_block(child, final_url)
                if block and image_key(str(block.get("url") or "")) != hero_key:
                    append_unique(blocks, block, seen_text, seen_media, title)
                continue

            social = social_url_from_node(child)
            if social and any(token in class_text(child) for token in ("twitter", "instagram", "tiktok", "embed")):
                embed, provider, original = normalize_embed_url(social)
                if embed:
                    append_unique(blocks, {
                        "type": "media", "media_type": "embed", "provider": provider,
                        "url": embed, "source_url": original, "title": "Embedded post",
                    }, seen_text, seen_media, title)
                    continue

            walk(child)

    walk(root)
    return repair_blocks(blocks)


def strip_markdown(value: str) -> str:
    text = str(value or "")
    text = re.sub(r"!\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
    text = text.replace("**", "").replace("__", "").replace("`", "")
    text = re.sub(r"(?<!\w)[*_](.+?)[*_](?!\w)", r"\1", text)
    return clean(text)


def parse_markdown(raw: str, title: str, hero_url: str = "") -> list[dict[str, Any]]:
    marker = re.search(r"^Markdown Content:\s*$", raw, flags=re.I | re.M)
    body = raw[marker.end():] if marker else raw
    lines = body.splitlines()
    blocks: list[dict[str, Any]] = []
    seen_text: set[str] = set()
    seen_media: set[str] = set()
    hero_key = image_key(hero_url) if hero_url else ""
    paragraph: list[str] = []
    index = 0

    def flush() -> None:
        nonlocal paragraph
        if not paragraph:
            return
        raw_text = " ".join(line.strip() for line in paragraph if line.strip())
        paragraph = []
        text = strip_markdown(raw_text)
        if len(text) >= 12:
            append_unique(blocks, {"type": "paragraph", "text": text}, seen_text, seen_media, title)

    while index < len(lines):
        stripped = lines[index].strip()
        if not stripped:
            flush()
            index += 1
            continue

        heading = MARKDOWN_HEADING_RE.match(stripped)
        if heading:
            flush()
            text = strip_markdown(heading.group(2))
            append_unique(blocks, {"type": "heading", "text": text, "level": 3 if len(heading.group(1)) >= 3 else 2}, seen_text, seen_media, title)
            index += 1
            continue

        image_match = MARKDOWN_IMAGE_RE.fullmatch(stripped)
        if image_match:
            flush()
            alt = strip_markdown(image_match.group(1))
            url = safe_http_url(image_match.group(2))
            if url and valid_article_image(url) and image_key(url) != hero_key and not author_image_text(alt):
                append_unique(blocks, {"type": "image", "url": url, "alt": alt, "caption": ""}, seen_text, seen_media, title)
            index += 1
            continue

        link = MARKDOWN_LINK_ONLY_RE.match(stripped)
        if link:
            embed, provider, original = normalize_embed_url(link.group(2))
            if embed:
                flush()
                append_unique(blocks, {
                    "type": "media", "media_type": "embed", "provider": provider,
                    "url": embed, "source_url": original, "title": strip_markdown(link.group(1))[:180] or "Embedded media",
                }, seen_text, seen_media, title)
                index += 1
                continue

        quote_match = MARKDOWN_QUOTE_RE.match(stripped)
        if quote_match:
            flush()
            quoted: list[str] = []
            while index < len(lines):
                current = MARKDOWN_QUOTE_RE.match(lines[index].strip())
                if not current:
                    break
                quoted.append(current.group(1))
                index += 1
            text = strip_markdown(" ".join(quoted))
            if len(text) >= 12:
                append_unique(blocks, {"type": "quote", "text": text}, seen_text, seen_media, title)
            continue

        ul = MARKDOWN_UL_RE.match(stripped)
        ol = MARKDOWN_OL_RE.match(stripped)
        if ul or ol:
            flush()
            ordered = bool(ol)
            items: list[str] = []
            while index < len(lines):
                current = lines[index].strip()
                match = MARKDOWN_OL_RE.match(current) if ordered else MARKDOWN_UL_RE.match(current)
                if not match:
                    break
                item = strip_markdown(match.group(1))
                if item:
                    items.append(item)
                index += 1
            if items:
                append_unique(blocks, {"type": "list", "ordered": ordered, "items": items}, seen_text, seen_media, title)
            continue

        paragraph.append(stripped)
        index += 1

    flush()
    return repair_blocks(blocks)


def repair_blocks(blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cleaned: list[dict[str, Any]] = []
    for raw in blocks:
        block = dict(raw)
        kind = block.get("type")
        if kind in {"paragraph", "heading", "quote"}:
            text = clean(block.get("text"))
            if not text:
                continue
            if MEDIA_LABEL_RE.match(text):
                continue
            caption = CAPTION_RE.match(text)
            if caption:
                if cleaned and cleaned[-1].get("type") == "image" and not clean(cleaned[-1].get("caption")):
                    cleaned[-1]["caption"] = clean(caption.group(1))
                continue
            if PUBLISHER_META_RE.match(text) and len(text) <= 260:
                continue
            block["text"] = text
            if kind == "paragraph" and cleaned and cleaned[-1].get("type") == "paragraph":
                previous = clean(cleaned[-1].get("text"))
                if previous and not re.search(r"[.!?;:\u201d\"']$", previous) and text[:1].islower():
                    cleaned[-1]["text"] = f"{previous} {text}"
                    cleaned[-1].pop("html", None)
                    continue
        cleaned.append(block)
    return cleaned


def block_words(blocks: list[dict[str, Any]]) -> int:
    total = 0
    for block in blocks:
        kind = block.get("type")
        if kind in {"paragraph", "heading", "quote"}:
            total += words(block.get("text"))
        elif kind == "list":
            total += sum(words(item.get("text") if isinstance(item, dict) else item) for item in block.get("items", []))
    return total


def richness(blocks: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "paragraphs": sum(1 for block in blocks if block.get("type") == "paragraph"),
        "headings": sum(1 for block in blocks if block.get("type") == "heading"),
        "quotes": sum(1 for block in blocks if block.get("type") == "quote"),
        "lists": sum(1 for block in blocks if block.get("type") == "list"),
        "images": sum(1 for block in blocks if block.get("type") == "image"),
        "embeds": sum(1 for block in blocks if block.get("type") == "media"),
    }


def candidate_score(blocks: list[dict[str, Any]]) -> float:
    stats = richness(blocks)
    return (
        block_words(blocks)
        + stats["paragraphs"] * 5
        + stats["headings"] * 35
        + stats["quotes"] * 25
        + stats["lists"] * 28
        + stats["images"] * 70
        + stats["embeds"] * 130
    )


def nearest_anchor(blocks: list[dict[str, Any]], index: int) -> str:
    for cursor in range(index - 1, -1, -1):
        block = blocks[cursor]
        if block.get("type") in {"paragraph", "heading", "quote"} and block.get("text"):
            return clean(block.get("text"))
    return ""


def match_anchor(blocks: list[dict[str, Any]], anchor: str) -> int | None:
    key = text_key(anchor)
    if not key:
        return None
    anchor_words = set(key.split())
    best_index: int | None = None
    best = 0.0
    for index, block in enumerate(blocks):
        if block.get("type") not in {"paragraph", "heading", "quote"}:
            continue
        candidate = text_key(block.get("text"))
        if not candidate:
            continue
        if candidate == key or candidate in key or key in candidate:
            return index
        candidate_words = set(candidate.split())
        overlap = len(anchor_words & candidate_words) / max(1, min(len(anchor_words), len(candidate_words)))
        if overlap > best:
            best = overlap
            best_index = index
    return best_index if best >= 0.66 else None


def rich_block_key(block: dict[str, Any]) -> str:
    if block.get("type") == "image":
        return f"image:{image_key(str(block.get('url') or ''))}"
    if block.get("type") == "media":
        return f"media:{block.get('media_type', '')}:{str(block.get('url') or '').split('#', 1)[0]}"
    return ""


def merge_rich_blocks(existing: list[dict[str, Any]], candidate: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    result = repair_blocks([dict(block) for block in existing if isinstance(block, dict)])
    seen = {rich_block_key(block) for block in result if rich_block_key(block)}
    inserted = 0
    offset = 0
    for index, block in enumerate(candidate):
        if block.get("type") not in {"image", "media"}:
            continue
        key = rich_block_key(block)
        if not key or key in seen:
            continue
        anchor = nearest_anchor(candidate, index)
        target = match_anchor(result, anchor)
        if target is None:
            continue
        result.insert(target + 1 + offset, dict(block))
        offset += 1
        inserted += 1
        seen.add(key)
    return result, inserted


def fetch_reader(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    target = f"{parsed.netloc}{parsed.path}"
    if parsed.query:
        target += f"?{parsed.query}"
    reader_url = f"https://r.jina.ai/http://{target}"
    try:
        response = requests.get(reader_url, headers=READER_HEADERS, timeout=(4, 24))
        return response.text if response.status_code == 200 and len(response.content) >= 500 else ""
    except Exception:
        return ""


def choose_candidate(existing: list[dict[str, Any]], candidates: list[tuple[str, list[dict[str, Any]]]]) -> tuple[str, list[dict[str, Any]]]:
    existing_words = block_words(existing)
    usable: list[tuple[str, list[dict[str, Any]]]] = []
    for method, blocks in candidates:
        candidate_words = block_words(blocks)
        if candidate_words < MIN_WORDS:
            continue
        if existing_words >= MIN_WORDS and candidate_words < existing_words * 0.82:
            continue
        usable.append((method, blocks))
    if not usable:
        return "", []
    return max(usable, key=lambda item: candidate_score(item[1]))


def process_story(story: dict[str, Any]) -> tuple[list[dict[str, Any]], str, int]:
    url = clean(story.get("url"))
    source = clean(story.get("source"))
    title = clean(story.get("title"))
    hero = clean(story.get("image"))
    existing = repair_blocks(story.get("content_blocks") if isinstance(story.get("content_blocks"), list) else [])
    candidates: list[tuple[str, list[dict[str, Any]]]] = []

    dom_blocks: list[dict[str, Any]] = []
    try:
        raw, final_url = fetch_html(url)
        dom_blocks = parse_dom(raw, final_url, source, title, hero)
        if dom_blocks:
            candidates.append(("dom:semantic-rich-v1", dom_blocks))
    except Exception:
        pass

    dom_words = block_words(dom_blocks)
    dom_rich = richness(dom_blocks)
    existing_words = block_words(existing)
    needs_reader = (
        not dom_blocks
        or dom_words < max(MIN_WORDS, existing_words * 0.92)
        or (dom_rich["images"] + dom_rich["embeds"] + dom_rich["headings"] + dom_rich["lists"] + dom_rich["quotes"]) < 2
    )
    if needs_reader:
        reader = fetch_reader(url)
        if reader:
            reader_blocks = parse_markdown(reader, title, hero)
            if reader_blocks:
                candidates.append(("reader:semantic-rich-v1", reader_blocks))

    method, chosen = choose_candidate(existing, candidates)
    if chosen:
        chosen_words = block_words(chosen)
        existing_score = candidate_score(existing)
        chosen_score = candidate_score(chosen)
        if existing_words < MIN_WORDS or chosen_words >= existing_words * 0.92 or chosen_score > existing_score * 1.12:
            return chosen, method, 0

    best_rich: list[dict[str, Any]] = []
    best_method = ""
    if candidates:
        best_method, best_rich = max(candidates, key=lambda item: candidate_score(item[1]))
    merged, inserted = merge_rich_blocks(existing, best_rich)
    return merged, f"merge:{best_method}" if inserted else "", inserted


def story_priority(story: dict[str, Any]) -> tuple[int, float, int]:
    schema_missing = int(story.get("rich_article_schema") or 0) < RICH_ARTICLE_SCHEMA
    published = str(story.get("published") or "").replace("Z", "+00:00")
    timestamp = 0.0
    try:
        timestamp = datetime.fromisoformat(published).timestamp()
    except Exception:
        pass
    richness_now = richness(story.get("content_blocks") if isinstance(story.get("content_blocks"), list) else [])
    rich_count = richness_now["images"] + richness_now["embeds"] + richness_now["headings"] + richness_now["lists"] + richness_now["quotes"]
    return (1 if schema_missing else 0, timestamp, -rich_count)


def story_needs_work(story: dict[str, Any]) -> bool:
    if not isinstance(story, dict) or not story.get("url") or not story.get("title"):
        return False
    host = urlparse(str(story.get("url") or "")).netloc.lower()
    if "news.google.com" in host:
        return False
    return int(story.get("rich_article_schema") or 0) < RICH_ARTICLE_SCHEMA


def paragraphs_from_blocks(blocks: list[dict[str, Any]]) -> list[str]:
    output: list[str] = []
    for block in blocks:
        if block.get("type") in {"paragraph", "quote"} and block.get("text"):
            output.append(clean(block.get("text")))
        elif block.get("type") == "list":
            output.extend(clean(item.get("text") if isinstance(item, dict) else item) for item in block.get("items", []) if clean(item.get("text") if isinstance(item, dict) else item))
    return output


def apply_result(story: dict[str, Any], blocks: list[dict[str, Any]], method: str, inserted: int) -> bool:
    now = datetime.now(timezone.utc).isoformat()
    story["rich_article_attempted_at"] = now
    if not method or not blocks:
        return False

    blocks = repair_blocks(blocks)
    word_count = block_words(blocks)
    if word_count < MIN_WORDS and story.get("content_status") not in {"full", "partial"}:
        return False

    story["content_blocks"] = blocks
    paragraphs = paragraphs_from_blocks(blocks)
    story["paragraphs"] = paragraphs
    story["content"] = "\n\n".join(paragraphs)
    story["word_count"] = word_count
    if word_count >= MIN_WORDS:
        story["content_status"] = "full"
    story["rich_article_schema"] = RICH_ARTICLE_SCHEMA
    story["rich_article_method"] = method
    story["rich_article_inserted_blocks"] = inserted
    stats = richness(blocks)
    story["rich_article_stats"] = stats
    story["article_format_state"] = "rich" if sum(stats[key] for key in ("images", "embeds", "headings", "quotes", "lists")) > 0 else "structured"
    quality = story.get("quality") if isinstance(story.get("quality"), dict) else {}
    quality.update({
        "score": max(int(quality.get("score") or 0), min(96, 70 + stats["images"] * 3 + stats["embeds"] * 5 + stats["headings"] * 2)),
        "grade": "good" if word_count >= MIN_WORDS else quality.get("grade", "fair"),
        "method": method,
        "text_blocks": stats["paragraphs"] + stats["headings"] + stats["quotes"] + stats["lists"],
        "rich_blocks": stats["images"] + stats["embeds"],
        "image_blocks": stats["images"],
    })
    story["quality"] = quality
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Recover source-agnostic rich article structure and media")
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    args = parser.parse_args()

    if not NEWS_PATH.exists():
        print("No data/news.json found")
        return 0

    payload = json.loads(NEWS_PATH.read_text(encoding="utf-8"))
    stories = payload.get("stories") if isinstance(payload.get("stories"), list) else []
    targets = [story for story in stories if story_needs_work(story)]
    targets.sort(key=story_priority, reverse=True)
    targets = targets[: max(1, args.limit)]
    if not targets:
        print("Rich article enrichment already current")
        return 0

    by_id = {str(story.get("id") or id(story)): story for story in targets}
    results: dict[str, tuple[list[dict[str, Any]], str, int]] = {}
    with ThreadPoolExecutor(max_workers=min(WORKERS, len(targets))) as executor:
        futures = {
            executor.submit(process_story, story): key
            for key, story in by_id.items()
        }
        for future in as_completed(futures):
            key = futures[future]
            try:
                results[key] = future.result()
            except Exception:
                results[key] = ([], "", 0)

    updated = 0
    embeds = 0
    images = 0
    for key, story in by_id.items():
        blocks, method, inserted = results.get(key, ([], "", 0))
        if apply_result(story, blocks, method, inserted):
            updated += 1
            stats = richness(blocks)
            embeds += stats["embeds"]
            images += stats["images"]

    payload["rich_article_schema"] = RICH_ARTICLE_SCHEMA
    NEWS_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Rich article enrichment: {updated}/{len(targets)} updated, {images} inline image(s), {embeds} embed(s) preserved")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
