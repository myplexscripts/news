from __future__ import annotations

"""Universal article quality sweep.

This is the source-agnostic last mile for every publisher in the feed. It cleans
publisher chrome from already-extracted blocks, re-fetches weak/flat articles to
recover source formatting, and makes a readable paragraph fallback when a source
cannot expose rich markup. Source profiles remain useful overrides, but they are
not required for this sweep to work on a new publisher.
"""

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

from bs4 import BeautifulSoup, Tag

try:
    from trafilatura import extract as trafilatura_extract
except Exception:  # pragma: no cover - dependency is installed in production
    trafilatura_extract = None

from fetch_news import clean_text, fetch_html
from refine_article_formatting import extract_dom_blocks, fetch_cbc_blocks
from refine_source_articles import extract_profiled_blocks

ROOT = Path(__file__).resolve().parents[1]
NEWS_PATH = ROOT / "data" / "news.json"
SWEEP_SCHEMA = 1
MAX_REFETCH = max(40, int(os.getenv("ARTICLE_SWEEP_MAX_REFETCH", "180")))
WORKERS = max(2, min(12, int(os.getenv("ARTICLE_SWEEP_WORKERS", "10"))))
RETRY_HOURS = max(3, int(os.getenv("ARTICLE_SWEEP_RETRY_HOURS", "6")))
MIN_ACCEPT_WORDS = 60
MIN_COVERAGE = 0.72

MODULE_LABEL_PATTERNS = (
    re.compile(r"^(?:advertisement|advertising|sponsored(?: content)?|promoted)$", re.I),
    re.compile(
        r"^(?:related(?: stories| story| coverage)?|recommended(?: for you)?|you may also like|"
        r"read more|more from(?: .+)?|more stories|more news|read next|keep reading|also read|"
        r"trending(?: now)?|most read|most popular|top stories)$",
        re.I,
    ),
    re.compile(
        r"^(?:newsletter|newsletters|subscribe|sign up|follow us|follow related authors and topics|"
        r"interact with .+|report an? .+ error|report a technical issue|editorial code of conduct|"
        r"comments?)$",
        re.I,
    ),
)

UTILITY_SENTENCE_PATTERNS = (
    re.compile(r"^enjoy the latest .{0,100}news\.?$", re.I),
    re.compile(
        r"^(?:sign up|subscribe|get .{0,100} delivered to your inbox|download our app|follow us|"
        r"share this (?:story|article)|join the conversation|story continues below|continue reading)\b",
        re.I,
    ),
    re.compile(r"^(?:this )?advertisement(?: has not loaded yet)?\.?$", re.I),
    re.compile(r"^postmedia is committed to maintaining a lively but civil forum", re.I),
    re.compile(r"^authors and topics you follow will be added to your personal news feed", re.I),
    re.compile(r"^(?:report an editorial error|report a technical issue|editorial code of conduct)\.?$", re.I),
)

ATTRIBUTE_MODULE_PHRASES = (
    "advert", "advertisement", "advertising", "ad slot", "ad unit", "ad container",
    "sponsor", "sponsored", "promo", "promoted", "promotion",
    "related", "related stories", "recommend", "recommended", "recommendation",
    "recirc", "recirculation", "read more", "more stories", "more news", "more from",
    "trending", "most read", "most popular", "top stories",
    "outbrain", "taboola", "newsletter", "subscribe", "subscription", "sign up", "signup",
    "social share", "share tools", "sharing", "comments", "comment module",
    "follow author", "author follow", "feedback", "error report", "paywall", "registration",
)

NAV_WORDS = {
    "home", "news", "canada", "ontario", "quebec", "local", "world", "politics",
    "business", "sports", "life", "opinion", "entertainment", "health", "weather",
    "search", "menu", "national", "province", "city",
}

CARD_META_RE = re.compile(
    r"(?:\bcomments?\b|\bwith\s+video\b|\b\d+\s+(?:minutes?|hours?|days?)\s+ago\b|"
    r"\b(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|"
    r"aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\s+\d{1,2},\s+\d{4}\b)",
    re.I,
)

DOM_REMOVE_TAGS = {"script", "style", "noscript", "nav", "footer", "form", "button"}
DOM_MODULE_CONTAINERS = {"aside", "section", "div", "ul", "ol", "figure", "footer", "nav"}
BODY_KEY_RE = re.compile(r"^(?:article|story|body)(?:_|-)?(?:body|content|text)$|^articlebody$|^articlecontent$|^storybody$|^bodycontent$", re.I)


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


def compact(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def text_key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", compact(value).lower()).strip()


def word_count(value: Any) -> int:
    return len(re.findall(r"\b\w+[’'-]?\w*\b", compact(value)))


def item_text(value: Any) -> str:
    return compact(value.get("text")) if isinstance(value, dict) else compact(value)


def item_html(value: Any) -> str:
    return compact(value.get("html")) if isinstance(value, dict) else ""


def block_text(block: dict[str, Any]) -> str:
    if block.get("type") == "list":
        return " ".join(item_text(item) for item in block.get("items", []) if item_text(item))
    return compact(block.get("text") or block.get("caption") or block.get("alt"))


def sentence_like(value: Any) -> bool:
    text = compact(value)
    return word_count(text) >= 8 and bool(re.search(r"[.!?][\"'’”)]?$", text))


def headline_like(value: Any) -> bool:
    text = compact(value)
    count = word_count(text)
    if count < 4 or count > 24 or len(text) < 18 or len(text) > 220:
        return False
    return not (count >= 15 and sentence_like(text) and "," in text)


def single_link_html(value: Any) -> bool:
    markup = compact(value)
    return bool(re.fullmatch(r"<a\b[^>]*>.*</a>", markup, flags=re.I | re.S))


def is_module_label(value: Any) -> bool:
    text = compact(value)
    return bool(text) and any(pattern.match(text) for pattern in MODULE_LABEL_PATTERNS)


def is_utility_sentence(value: Any) -> bool:
    text = compact(value)
    return bool(text) and word_count(text) <= 35 and any(pattern.search(text) for pattern in UTILITY_SENTENCE_PATTERNS)


def metadata_marks_module(block: dict[str, Any]) -> bool:
    raw = " ".join(
        compact(block.get(key))
        for key in ("role", "kind", "module", "module_type", "source_type", "class_name", "component")
        if block.get(key)
    )
    return bool(raw) and attribute_has_module_signal(raw)


def split_attribute_words(value: Any) -> str:
    raw = compact(value)
    raw = re.sub(r"([a-z])([A-Z])", r"\1 \2", raw)
    return re.sub(r"[^a-z0-9]+", " ", raw.lower()).strip()


def attribute_has_module_signal(value: Any) -> bool:
    normalized = f" {split_attribute_words(value)} "
    if not normalized.strip():
        return False
    for phrase in ATTRIBUTE_MODULE_PHRASES:
        if f" {phrase} " in normalized:
            return True
    tokens = normalized.split()
    return any(token in {"ad", "ads", "outbrain", "taboola"} for token in tokens)


def node_signature(node: Tag) -> str:
    values: list[str] = []
    for attr in ("id", "class", "role", "aria-label", "data-testid", "data-component", "data-module", "data-type", "data-content-type"):
        value = node.get(attr)
        if isinstance(value, list):
            values.extend(str(item) for item in value)
        elif value:
            values.append(str(value))
    return " ".join(values)


def node_is_hidden(node: Tag) -> bool:
    if node.has_attr("hidden") or str(node.get("aria-hidden") or "").lower() == "true":
        return True
    style = str(node.get("style") or "").lower().replace(" ", "")
    return "display:none" in style or "visibility:hidden" in style


def visible_module_label(node: Tag) -> bool:
    text = compact(node.get_text(" ", strip=True))
    if not text or word_count(text) > 14:
        return False
    return is_module_label(text) or is_utility_sentence(text)


def looks_like_card_container(node: Tag) -> bool:
    anchors = [a for a in node.find_all("a", href=True) if isinstance(a, Tag)]
    if len(anchors) < 3:
        return False
    total = compact(node.get_text(" ", strip=True))
    if len(total) < 50 or len(total) > 4500:
        return False
    link_texts = [compact(a.get_text(" ", strip=True)) for a in anchors]
    link_texts = [text for text in link_texts if text]
    if len(link_texts) < 3:
        return False
    link_chars = sum(len(text) for text in link_texts)
    density = link_chars / max(1, len(total))
    headline_links = sum(1 for text in link_texts if headline_like(text))
    prose_paragraphs = [
        compact(p.get_text(" ", strip=True))
        for p in node.find_all("p")
        if sentence_like(p.get_text(" ", strip=True))
    ]
    images = len(node.find_all("img"))
    return density >= 0.62 and headline_links >= 3 and len(prose_paragraphs) <= 1 and (
        images >= 2 or attribute_has_module_signal(node_signature(node))
    )


def prune_dom_modules(raw: str) -> str:
    soup = BeautifulSoup(raw, "html.parser")
    for node in list(soup.find_all(True)):
        if not isinstance(node, Tag):
            continue
        if node.name in DOM_REMOVE_TAGS or node_is_hidden(node):
            node.decompose()
    containers = [node for node in soup.find_all(DOM_MODULE_CONTAINERS) if isinstance(node, Tag)]
    containers.sort(key=lambda node: len(list(node.parents)), reverse=True)
    for node in containers:
        if node.parent is None:
            continue
        role = str(node.get("role") or "").lower()
        if role in {"navigation", "complementary"}:
            node.decompose()
            continue
        if attribute_has_module_signal(node_signature(node)):
            node.decompose()
            continue
        if visible_module_label(node) and len(node.find_all("p")) <= 1:
            node.decompose()
            continue
        if looks_like_card_container(node):
            node.decompose()
    return str(soup)


def navigation_list(block: dict[str, Any], position: int) -> bool:
    items = [item for item in block.get("items", []) if item_text(item)]
    if not items:
        return False
    keys = [text_key(item_text(item)) for item in items]
    linked = sum(1 for item in items if single_link_html(item_html(item)))
    if len(items) >= 2 and linked == len(items) and all(word_count(item_text(item)) <= 5 for item in items):
        return True
    if position <= 1 and len(items) <= 8 and all(key in NAV_WORDS for key in keys):
        return True
    return False


def story_card_list(block: dict[str, Any], known_titles: set[str]) -> bool:
    items = [item for item in block.get("items", []) if item_text(item)]
    if len(items) < 2:
        return False
    texts = [item_text(item) for item in items]
    keys = [text_key(text) for text in texts]
    linked = sum(1 for item in items if single_link_html(item_html(item)))
    matches = sum(1 for key in keys if key in known_titles)
    headline_count = sum(1 for text in texts if headline_like(text))
    metadata_count = sum(1 for text in texts if CARD_META_RE.search(text))
    if matches >= 2:
        return True
    if linked >= 2 and linked / len(items) >= 0.67 and headline_count / len(items) >= 0.67:
        return True
    return metadata_count >= 2 and headline_count >= 2


def image_is_ad(block: dict[str, Any]) -> bool:
    if block.get("type") != "image":
        return False
    text = " ".join((compact(block.get("alt")), compact(block.get("caption")), compact(block.get("url"))))
    normalized = text.lower()
    if is_module_label(block.get("alt")) or is_module_label(block.get("caption")):
        return True
    return any(token in normalized for token in ("/advert/", "/advertisement/", "/sponsored/", "doubleclick.net", "adservice"))


def headline_image_run(blocks: list[dict[str, Any]], start: int, known_titles: set[str]) -> int | None:
    if start >= len(blocks):
        return None
    first = blocks[start]
    if first.get("type") not in {"heading", "paragraph"} or not headline_like(first.get("text")):
        return None
    cursor = start
    headings = images = linked = matches = 0
    consumed = 0
    while cursor < len(blocks) and consumed < 18:
        block = blocks[cursor]
        kind = block.get("type")
        if kind in {"heading", "paragraph"} and headline_like(block.get("text")):
            if kind == "paragraph" and sentence_like(block.get("text")) and not single_link_html(block.get("html")):
                break
            headings += 1
            if single_link_html(block.get("html")):
                linked += 1
            if text_key(block.get("text")) in known_titles:
                matches += 1
            cursor += 1
            consumed += 1
            continue
        if kind == "image" and headings:
            images += 1
            cursor += 1
            consumed += 1
            continue
        if kind == "list" and headings:
            items = [item_text(item) for item in block.get("items", []) if item_text(item)]
            if items and all(word_count(item) <= 8 for item in items):
                cursor += 1
                consumed += 1
                continue
        break
    if headings >= 2 and (matches >= 2 or linked >= 2):
        return cursor
    if headings >= 3 and images >= 2:
        return cursor
    return None


def content_word_count(blocks: list[dict[str, Any]]) -> int:
    total = 0
    for block in blocks:
        kind = block.get("type")
        if kind in {"paragraph", "quote"}:
            total += word_count(block.get("text"))
        elif kind == "list":
            total += sum(word_count(item_text(item)) for item in block.get("items", []))
    return total


def clean_blocks(
    blocks: list[dict[str, Any]],
    *,
    title: str = "",
    known_titles: set[str] | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    known = set(known_titles or ())
    known.discard(text_key(title))
    removed: list[str] = []
    preliminary: list[dict[str, Any]] = []
    for position, raw in enumerate(blocks):
        if not isinstance(raw, dict):
            removed.append("invalid-block")
            continue
        block = dict(raw)
        kind = block.get("type")
        text = block_text(block)
        if metadata_marks_module(block):
            removed.append("metadata-module")
            continue
        if kind in {"paragraph", "heading", "quote"} and (is_module_label(text) or is_utility_sentence(text)):
            removed.append("utility-text")
            continue
        if kind == "list" and (navigation_list(block, position) or story_card_list(block, known)):
            removed.append("navigation-or-story-list")
            continue
        if kind in {"paragraph", "heading"} and single_link_html(block.get("html")) and text_key(text) in known:
            removed.append("standalone-related-link")
            continue
        if image_is_ad(block):
            removed.append("advert-image")
            continue
        preliminary.append(block)
    final: list[dict[str, Any]] = []
    index = 0
    while index < len(preliminary):
        end = headline_image_run(preliminary, index, known)
        if end is not None and end > index:
            removed.append("headline-card-run")
            index = end
            continue
        final.append(preliminary[index])
        index += 1
    trimmed: list[dict[str, Any]] = []
    prior_words = 0
    for block in final:
        text = block_text(block)
        terminal_key = text_key(text)
        if prior_words >= 80 and terminal_key in {
            "report an editorial error", "report a technical issue", "follow related authors and topics",
            "interact with the globe", "editorial code of conduct", "comments",
        }:
            removed.append("terminal-publisher-ui")
            break
        trimmed.append(block)
        if block.get("type") in {"paragraph", "quote"}:
            prior_words += word_count(block.get("text"))
        elif block.get("type") == "list":
            prior_words += sum(word_count(item_text(item)) for item in block.get("items", []))
    return trimmed, removed


def split_wall_paragraph(text: str, html_text: str = "") -> list[dict[str, Any]]:
    if html_text and re.search(r"<(?:a|strong|em|sup|sub)\b", html_text, re.I):
        return [{"type": "paragraph", "text": text, "html": html_text}]
    sentences = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9‘'\"“])", compact(text))
    if len(sentences) < 4:
        return [{"type": "paragraph", "text": text, **({"html": html_text} if html_text else {})}]
    output: list[dict[str, Any]] = []
    buffer: list[str] = []
    buffer_words = 0
    for sentence in sentences:
        sentence = compact(sentence)
        if not sentence:
            continue
        buffer.append(sentence)
        buffer_words += word_count(sentence)
        if buffer_words >= 95:
            paragraph = " ".join(buffer)
            output.append({"type": "paragraph", "text": paragraph, "html": html.escape(paragraph, quote=False)})
            buffer = []
            buffer_words = 0
    if buffer:
        paragraph = " ".join(buffer)
        if output and word_count(paragraph) < 30:
            previous = output.pop()
            paragraph = f"{previous['text']} {paragraph}"
        output.append({"type": "paragraph", "text": paragraph, "html": html.escape(paragraph, quote=False)})
    return output


def ensure_readable_fallback(blocks: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], bool]:
    text_blocks = [block for block in blocks if block.get("type") in {"paragraph", "quote"} and compact(block.get("text"))]
    structured = sum(1 for block in blocks if block.get("type") in {"heading", "list", "image", "quote"})
    if structured or len(text_blocks) > 2 or content_word_count(blocks) < 260:
        return blocks, False
    changed = False
    rebuilt: list[dict[str, Any]] = []
    for block in blocks:
        if block.get("type") == "paragraph" and word_count(block.get("text")) >= 180:
            pieces = split_wall_paragraph(compact(block.get("text")), compact(block.get("html")))
            if len(pieces) > 1:
                rebuilt.extend(pieces)
                changed = True
                continue
        rebuilt.append(block)
    return rebuilt, changed


def formatting_strength(blocks: list[dict[str, Any]]) -> tuple[int, int, int]:
    text_blocks = [block for block in blocks if block.get("type") in {"paragraph", "heading", "quote"} and block.get("text")]
    html_blocks = sum(1 for block in text_blocks if compact(block.get("html")))
    structure = sum(1 for block in blocks if block.get("type") in {"heading", "list", "image", "quote"})
    return html_blocks, structure, len(text_blocks)


def needs_format_recovery(story: dict[str, Any], blocks: list[dict[str, Any]], now: datetime) -> bool:
    if story.get("content_status") not in {"full", "partial"}:
        return False
    words = content_word_count(blocks) or int(story.get("word_count") or 0)
    html_blocks, structure, text_blocks = formatting_strength(blocks)
    weak = words < 70 or (words >= 70 and text_blocks >= 2 and html_blocks == 0 and structure <= 1)
    if not weak:
        return False
    attempted = parse_datetime(story.get("article_sweep_attempted_at"))
    return not attempted or now - attempted >= timedelta(hours=RETRY_HOURS)


def extract_json_body_values(raw: str) -> list[str]:
    soup = BeautifulSoup(raw, "html.parser")
    candidates: list[str] = []
    seen: set[str] = set()
    def add(value: Any) -> None:
        if not isinstance(value, str):
            return
        text = html.unescape(value).replace("\\/", "/").strip()
        if len(text) < 220:
            return
        if not re.search(r"<(?:p|h[1-6]|blockquote|ul|ol|strong|em|a)\b", text, re.I):
            return
        signature = text[:500]
        if signature in seen:
            return
        seen.add(signature)
        candidates.append(text)
    def walk(node: Any, depth: int = 0) -> None:
        if depth > 14:
            return
        if isinstance(node, list):
            for child in node:
                walk(child, depth + 1)
            return
        if not isinstance(node, dict):
            return
        for raw_key, value in node.items():
            normalized = re.sub(r"[^a-z0-9]+", "", str(raw_key).lower())
            if BODY_KEY_RE.match(str(raw_key)) or normalized in {"articlebody", "articlecontent", "storybody", "bodycontent", "articletext"}:
                add(value)
            elif normalized == "content" and isinstance(value, str) and len(value) >= 500:
                add(value)
            if isinstance(value, (dict, list)):
                walk(value, depth + 1)
    for script in soup.find_all("script"):
        raw_script = script.string or script.get_text("", strip=False)
        if not raw_script or len(raw_script) < 200:
            continue
        script_type = str(script.get("type") or "").lower()
        if "json" in script_type or str(script.get("id") or "").lower() in {"__next_data__", "__nuxt_data__"}:
            try:
                walk(json.loads(raw_script))
            except Exception:
                pass
    return candidates[:10]


def trafilatura_formatted_blocks(raw: str, final_url: str, title: str, hero: str) -> list[dict[str, Any]]:
    if trafilatura_extract is None:
        return []
    try:
        xml = trafilatura_extract(
            raw,
            url=final_url,
            output_format="xml",
            include_comments=False,
            include_tables=True,
            include_links=True,
            include_images=True,
            include_formatting=True,
            favor_precision=True,
            deduplicate=True,
        )
    except Exception:
        return []
    if not xml or len(xml) < 120:
        return []
    soup = BeautifulSoup(xml, "xml")
    main = soup.find("main") or soup.find("body") or soup.find("doc")
    if not isinstance(main, Tag):
        return []
    for node in list(main.find_all(True)):
        name = str(node.name or "").lower()
        if name == "head":
            rend = str(node.get("rend") or "")
            node.name = "h3" if "3" in rend else "h2"
        elif name == "ref":
            node.name = "a"
            target = node.get("target") or node.get("href")
            if target:
                node["href"] = urljoin(final_url, str(target))
        elif name == "hi":
            rend = str(node.get("rend") or "").lower()
            if any(token in rend for token in ("#b", "bold", "strong")):
                node.name = "strong"
            elif any(token in rend for token in ("#i", "italic", "emph")):
                node.name = "em"
            else:
                node.name = "span"
        elif name == "list":
            list_type = str(node.get("type") or node.get("rend") or "").lower()
            node.name = "ol" if any(token in list_type for token in ("ordered", "number", "decimal")) else "ul"
        elif name == "item":
            node.name = "li"
        elif name in {"quote", "q"}:
            node.name = "blockquote"
        elif name == "graphic":
            src = node.get("src") or node.get("url")
            node.name = "img"
            if src:
                node["src"] = urljoin(final_url, str(src))
        elif name in {"lb", "linebreak"}:
            node.name = "br"
    wrapped = f'<article><div class="article-body">{main.decode_contents()}</div></article>'
    try:
        return extract_dom_blocks(wrapped, final_url, title, hero)
    except Exception:
        return []


def formatted_candidates(raw: str, final_url: str, story: dict[str, Any]) -> list[tuple[list[dict[str, Any]], str]]:
    title = compact(story.get("title"))
    hero = compact(story.get("image"))
    source = compact(story.get("source"))
    candidates: list[tuple[list[dict[str, Any]], str]] = []
    cleaned_raw = prune_dom_modules(raw)
    trafilatura_blocks = trafilatura_formatted_blocks(cleaned_raw, final_url, title, hero)
    if trafilatura_blocks:
        candidates.append((trafilatura_blocks, "universal-trafilatura-xml"))
    generic = extract_dom_blocks(cleaned_raw, final_url, title, hero)
    if generic:
        candidates.append((generic, "universal-dom"))
    try:
        profiled, profile_name = extract_profiled_blocks(cleaned_raw, final_url, source, title, hero)
    except Exception:
        profiled, profile_name = [], ""
    if profiled:
        candidates.append((profiled, f"universal-profile:{profile_name}"))
    for embedded in extract_json_body_values(raw):
        wrapped = f'<article><div class="article-body">{embedded}</div></article>'
        blocks = extract_dom_blocks(wrapped, final_url, title, hero)
        if blocks:
            candidates.append((blocks, "universal-embedded-html"))
    return candidates


def choose_candidate(
    story: dict[str, Any],
    existing: list[dict[str, Any]],
    candidates: list[tuple[list[dict[str, Any]], str]],
    known_titles: set[str],
) -> tuple[list[dict[str, Any]], str]:
    baseline_words = content_word_count(existing)
    baseline_strength = formatting_strength(existing)
    best_blocks = existing
    best_method = "existing-clean"
    best_rank = (baseline_strength[0] * 4 + baseline_strength[1] * 6, baseline_words)
    for raw_blocks, method in candidates:
        cleaned, _ = clean_blocks(raw_blocks, title=compact(story.get("title")), known_titles=known_titles)
        words = content_word_count(cleaned)
        if words < MIN_ACCEPT_WORDS:
            continue
        if baseline_words >= 80 and words < int(baseline_words * MIN_COVERAGE):
            continue
        html_blocks, structure, _ = formatting_strength(cleaned)
        rank = (html_blocks * 4 + structure * 6, words)
        if rank > best_rank:
            best_blocks = cleaned
            best_method = method
            best_rank = rank
    return best_blocks, best_method


def rebuild_story_text(story: dict[str, Any], blocks: list[dict[str, Any]]) -> None:
    paragraphs: list[str] = []
    for block in blocks:
        kind = block.get("type")
        if kind in {"paragraph", "quote"} and block.get("text"):
            paragraphs.append(compact(block.get("text")))
        elif kind == "list":
            paragraphs.extend(item_text(item) for item in block.get("items", []) if item_text(item))
    story["content_blocks"] = blocks
    story["paragraphs"] = paragraphs
    story["content"] = "\n\n".join(paragraphs)
    story["word_count"] = sum(word_count(paragraph) for paragraph in paragraphs)


def process_remote_story(story: dict[str, Any], known_titles: set[str]) -> tuple[list[dict[str, Any]], str, str]:
    source = compact(story.get("source"))
    if source.startswith("CBC News"):
        try:
            cbc_blocks, cbc_method = fetch_cbc_blocks(story)
        except Exception as exc:
            cbc_blocks, cbc_method = [], f"cbc:{type(exc).__name__}"
        if cbc_blocks:
            cleaned, _ = clean_blocks(cbc_blocks, title=compact(story.get("title")), known_titles=known_titles)
            return cleaned, cbc_method, ""
    try:
        raw, final_url = fetch_html(compact(story.get("url")))
    except Exception as exc:
        return [], "", f"fetch:{type(exc).__name__}"
    existing, _ = clean_blocks(
        list(story.get("content_blocks") or []),
        title=compact(story.get("title")),
        known_titles=known_titles,
    )
    candidates = formatted_candidates(raw, final_url, story)
    blocks, method = choose_candidate(story, existing, candidates, known_titles)
    return blocks, method, ""


def remaining_hygiene_flags(blocks: list[dict[str, Any]], known_titles: set[str], title: str) -> list[str]:
    flags: list[str] = []
    for position, block in enumerate(blocks):
        if not isinstance(block, dict):
            flags.append("invalid-block")
            continue
        text = block_text(block)
        if metadata_marks_module(block):
            flags.append("metadata-module")
        if block.get("type") in {"paragraph", "heading", "quote"} and (is_module_label(text) or is_utility_sentence(text)):
            flags.append("publisher-ui-text")
        if block.get("type") == "list" and (navigation_list(block, position) or story_card_list(block, known_titles - {text_key(title)})):
            flags.append("publisher-list")
        if image_is_ad(block):
            flags.append("advert-image")
    index = 0
    while index < len(blocks):
        end = headline_image_run(blocks, index, known_titles - {text_key(title)})
        if end is not None:
            flags.append("publisher-card-run")
            index = end
        else:
            index += 1
    return sorted(set(flags))


def priority(story: dict[str, Any], blocks: list[dict[str, Any]], now: datetime) -> tuple[int, int, float]:
    words = content_word_count(blocks)
    html_blocks, structure, _ = formatting_strength(blocks)
    flat = 1 if words >= 70 and html_blocks == 0 and structure <= 1 else 0
    published = parse_datetime(story.get("published"))
    age = (now - published).total_seconds() / 3600 if published else 99999
    return (flat, 1 if age <= 168 else 0, -age)


def main() -> int:
    if not NEWS_PATH.exists():
        print("Universal article sweep: data/news.json not found", file=sys.stderr)
        return 1
    payload = json.loads(NEWS_PATH.read_text(encoding="utf-8"))
    stories = payload.get("stories") if isinstance(payload.get("stories"), list) else []
    dict_stories = [story for story in stories if isinstance(story, dict)]
    known_titles = {text_key(story.get("title")) for story in dict_stories if text_key(story.get("title"))}
    now = utc_now()
    locally_cleaned = 0
    removed_blocks = 0
    fallback_reflowed = 0
    targets: list[dict[str, Any]] = []
    for story in dict_stories:
        pending = int(story.get("article_sweep_schema") or 0) < SWEEP_SCHEMA
        blocks = list(story.get("content_blocks") or [])
        cleaned, removed = clean_blocks(blocks, title=compact(story.get("title")), known_titles=known_titles)
        cleaned, reflowed = ensure_readable_fallback(cleaned)
        if removed or reflowed or cleaned != blocks:
            rebuild_story_text(story, cleaned)
            locally_cleaned += 1
            removed_blocks += len(removed)
            fallback_reflowed += int(reflowed)
        story["article_sweep_removed_blocks"] = len(removed)
        if reflowed:
            story["article_sweep_reflowed"] = True
        attempted = parse_datetime(story.get("article_sweep_attempted_at"))
        retry_due = not attempted or now - attempted >= timedelta(hours=RETRY_HOURS)
        has_identity = bool(story.get("url") and story.get("title"))
        if has_identity and retry_due and (pending or needs_format_recovery(story, cleaned, now)):
            targets.append(story)
        elif not has_identity:
            story["article_sweep_schema"] = SWEEP_SCHEMA
    targets.sort(key=lambda story: priority(story, list(story.get("content_blocks") or []), now), reverse=True)
    targets = targets[:MAX_REFETCH]
    enriched = 0
    failed = 0
    if targets:
        by_id = {str(story.get("id") or ""): story for story in targets}
        with ThreadPoolExecutor(max_workers=WORKERS) as executor:
            futures = {
                executor.submit(process_remote_story, story, known_titles): str(story.get("id") or "")
                for story in targets
            }
            for future in as_completed(futures):
                story = by_id[futures[future]]
                story["article_sweep_attempted_at"] = now.isoformat()
                try:
                    blocks, method, error = future.result()
                except Exception as exc:
                    blocks, method, error = [], "", f"error:{type(exc).__name__}"
                if error:
                    story["article_sweep_error"] = error
                if not blocks:
                    failed += 1
                    continue
                existing = list(story.get("content_blocks") or [])
                chosen, chosen_method = choose_candidate(story, existing, [(blocks, method or "universal-refetch")], known_titles)
                chosen, reflowed = ensure_readable_fallback(chosen)
                if chosen != existing:
                    rebuild_story_text(story, chosen)
                    enriched += 1
                if reflowed:
                    story["article_sweep_reflowed"] = True
                story["article_sweep_method"] = chosen_method
                story["article_sweep_schema"] = SWEEP_SCHEMA
                recovered_words = content_word_count(chosen)
                if recovered_words >= 120 and story.get("content_status") in {"summary", "failed", "unknown", None, ""}:
                    story["content_status"] = "full"
                    story.pop("scrape_error", None)
                elif recovered_words >= MIN_ACCEPT_WORDS and story.get("content_status") in {"summary", "failed", "unknown", None, ""}:
                    story["content_status"] = "partial"
                    story.pop("scrape_error", None)
                story.pop("article_sweep_error", None)
    flagged = 0
    flat_remaining = 0
    for story in dict_stories:
        blocks = list(story.get("content_blocks") or [])
        flags = remaining_hygiene_flags(blocks, known_titles, compact(story.get("title")))
        if flags:
            story["article_hygiene_flags"] = flags
            flagged += 1
        else:
            story.pop("article_hygiene_flags", None)
        html_blocks, structure, text_blocks = formatting_strength(blocks)
        words = content_word_count(blocks)
        flat = words >= 70 and text_blocks >= 2 and html_blocks == 0 and structure <= 1
        story["article_format_state"] = "flat" if flat else "structured"
        flat_remaining += int(flat)
    payload["article_sweep_schema"] = SWEEP_SCHEMA
    payload["article_sweep_at"] = utc_now().isoformat()
    payload["article_sweep_stats"] = {
        "stories": len(dict_stories),
        "locally_cleaned": locally_cleaned,
        "removed_blocks": removed_blocks,
        "format_refetch_attempted": len(targets),
        "format_enriched": enriched,
        "format_failed_or_deferred": failed,
        "pending_initial_source_sweeps": sum(1 for story in dict_stories if int(story.get("article_sweep_schema") or 0) < SWEEP_SCHEMA),
        "fallback_reflowed": fallback_reflowed,
        "remaining_hygiene_flagged": flagged,
        "flat_articles_remaining": flat_remaining,
    }
    NEWS_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        "Universal article sweep: "
        f"{locally_cleaned} locally cleaned, {removed_blocks} publisher block(s) removed, "
        f"{len(targets)} formatting refetch(es), {enriched} enriched, {fallback_reflowed} reflowed, "
        f"{flagged} hygiene-flagged, {flat_remaining} flat remaining"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
