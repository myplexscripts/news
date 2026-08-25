from __future__ import annotations

import hashlib
import html
import json
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

import feedparser
import requests
from bs4 import BeautifulSoup, Tag
from dateutil import parser as date_parser
from trafilatura import bare_extraction, extract

from sources import SOURCES, Source

ROOT = Path(__file__).resolve().parents[1]
DATA_FILE = ROOT / "data" / "news.json"
HISTORY_LIMIT = 750
REQUEST_TIMEOUT = 22
ARTICLE_REFRESH_HOURS = 12
BACKFILL_PER_RUN = 12
MIN_ARTICLE_CHARS = 320
MAX_ARTICLE_IMAGES = 10
EXTRACTION_SCHEMA = 3
USER_AGENT = "LondonNewsAggregator/3.0 (+https://github.com/)"

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/rss+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-CA,en;q=0.9",
})

CATEGORY_RULES = [
    ("Public Safety", ("police", "arrest", "charged", "shooting", "collision", "fire", "fraud", "missing", "court", "crime")),
    ("City Hall", ("council", "mayor", "city hall", "municipal", "zoning", "budget", "ward", "election", "city of london")),
    ("Traffic", ("road", "closure", "traffic", "transit", "construction", "highway", "street", "lane")),
    ("Business", ("business", "jobs", "employer", "economy", "development", "retail", "housing", "market")),
    ("Education", ("western", "fanshawe", "school", "student", "university", "college", "tvdsb", "ldcsb")),
    ("Health", ("hospital", "health", "lhsc", "outbreak", "doctor", "nurse", "clinic")),
    ("Sports", ("knights", "sports", "hockey", "soccer", "baseball", "basketball", "football", "game")),
    ("Community", ("festival", "community", "event", "arts", "music", "theatre", "restaurant", "park", "recreation")),
]

GENERIC_BOILERPLATE = (
    "sign up for", "subscribe to", "sign in to continue", "create an account to continue",
    "sign in or create an account", "already a subscriber", "manage your subscription",
    "subscribe now to read", "subscribe to continue reading", "register to continue reading",
    "thanks for signing up", "join the conversation in the comments", "share this article",
    "get email updates from your favourite authors", "get email updates from your favorite authors",
    "this advertisement has not loaded yet", "advertisement has not loaded yet",
    "story continues below", "continue reading", "download our app", "follow us on",
    "recommended video", "related stories", "related story", "more from", "all rights reserved",
)

POSTMEDIA_BOILERPLATE = (
    "london free press epaper", "electronic replica of the print edition",
    "daily puzzles, including the new york times crossword",
    "daily puzzles including the new york times crossword", "support local journalism",
    "create an account or sign in to continue with your reading experience",
    "access articles from across canada with one account",
    "share your thoughts and join the conversation in the comments",
    "enjoy additional articles per month", "get email updates from your favourite authors",
    "get email updates from your favorite authors", "sign in or create an account",
    "unlock more articles", "manage print subscription",
)

SOURCE_PROFILES: dict[str, dict[str, Any]] = {
    "Global News London": {
        "profile": "global",
        "roots": [".l-article__body", ".article-content", "[itemprop='articleBody']", "article"],
        "remove": [".l-article__related", ".c-ad", ".ad", ".newsletter", ".share"],
    },
    "CBC News London": {
        "profile": "cbc",
        "roots": ["[data-cy='storyWrapper']", ".story-content", "[itemprop='articleBody']", "article"],
        "remove": ["[data-cy*='related']", ".related", ".newsletter", ".share", ".ad"],
    },
    "London Free Press": {
        "profile": "postmedia",
        "roots": ["[data-testid='article-body']", ".article-content", ".article-body", "[itemprop='articleBody']", "article"],
        "remove": [
            ".subscription", ".subscribe", ".paywall", ".registration", ".account",
            ".newsletter", ".related", ".share", ".social", ".ad", ".advertisement",
            "[class*='subscription']", "[class*='paywall']", "[class*='registration']",
            "[class*='epaper']", "[class*='puzzle']", "[class*='comment']",
        ],
    },
    "CTV News": {
        "profile": "ctv",
        "roots": [".articleBody", ".article-body", "[itemprop='articleBody']", "article"],
        "remove": [".related", ".newsletter", ".share", ".social", ".ad"],
    },
    "106.9 The X": {
        "profile": "wordpress",
        "roots": [".entry-content", ".post-content", "[itemprop='articleBody']", "article"],
        "remove": [".sharedaddy", ".jp-relatedposts", ".newsletter", ".ad"],
    },
    "City of London Newsroom": {
        "profile": "municipal",
        "roots": [".field--name-body", ".node__content", ".article-content", "article", "main"],
        "remove": [".related", ".share", ".social", ".feedback", ".webform"],
    },
    "London Police Service": {
        "profile": "police",
        "roots": [".news-article-content", ".field--name-body", ".article-content", "[itemprop='articleBody']", "article", "main"],
        "remove": [".related", ".share", ".social", ".newsletter"],
    },
    "London Fire Department": {
        "profile": "fire",
        "roots": ["[itemprop='articleBody']", ".article-content", "article", "main"],
        "remove": [".related", ".share", ".social", ".newsletter"],
    },
}

GENERIC_ROOTS = [
    "[itemprop='articleBody']", "article .article-body", "article .article-content",
    "article .story-body", "article .entry-content", "article .post-content", "article",
    "main .article-body", "main .story-body", "main",
]

GENERIC_REMOVE_SELECTORS = [
    "script", "style", "noscript", "nav", "footer", "form", "button", "iframe",
    "aside", "[role='complementary']", "[aria-label*='related' i]", "[aria-label*='advert' i]",
]

JUNK_CLASS_TOKENS = (
    "caption", "related", "promo", "newsletter", "share", "social", "advert", "author-card",
    "footer", "nav", "subscription", "subscribe", "paywall", "registration", "register",
    "account", "epaper", "puzzle", "comment", "recommend", "most-popular", "outbrain", "taboola",
)

IMAGE_JUNK = (
    "logo", "icon", "avatar", "author", "profile", "sprite", "pixel", "tracking", "badge",
    "weather", "placeholder", "default", "newsletter", "app-store", "google-play", "social",
    "facebook", "twitter", "instagram", "tiktok", "favicon", "headshot",
)

ACRONYMS = {
    "CBC", "CTV", "LPS", "OPP", "RCMP", "SIU", "EMS", "LHSC", "MLHU", "TVDSB",
    "LDCSB", "NHL", "OHL", "CFL", "NBA", "MLB", "COVID", "DNA", "CEO", "CFO",
    "MPP", "MP", "CA", "US", "USA",
}

PROPER_WORDS = {
    "london": "London", "ontario": "Ontario", "canada": "Canada", "thames": "Thames",
    "western": "Western", "fanshawe": "Fanshawe", "middlesex": "Middlesex", "sarnia": "Sarnia",
    "strathroy": "Strathroy", "january": "January", "february": "February", "march": "March",
    "april": "April", "may": "May", "june": "June", "july": "July", "august": "August",
    "september": "September", "october": "October", "november": "November", "december": "December",
}


def clean_text(value: str | None, limit: int | None = None) -> str:
    if not value:
        return ""
    raw = html.unescape(str(value))
    text = BeautifulSoup(raw, "html.parser").get_text(" ", strip=True) if "<" in raw and ">" in raw else raw
    text = re.sub(r"\s+", " ", text).strip()
    if limit and len(text) > limit:
        return text[: limit - 1].rstrip(" ,;:-") + "…"
    return text


def boilerplate_key(value: str) -> str:
    value = clean_text(value).lower().replace("’", "'")
    value = re.sub(r"[^a-z0-9']+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def normalize_source_case(value: str) -> str:
    text = clean_text(value)
    if not text:
        return ""

    def restore(segment: str) -> str:
        for acronym in sorted(ACRONYMS, key=len, reverse=True):
            segment = re.sub(rf"\b{re.escape(acronym.lower())}\b", acronym, segment, flags=re.I)
        for lower, canonical in PROPER_WORDS.items():
            segment = re.sub(rf"\b{re.escape(lower)}\b", canonical, segment, flags=re.I)
        segment = re.sub(r",\s+on\b", ", ON", segment, flags=re.I)
        return segment

    def fix(segment: str) -> str:
        letters = [char for char in segment if char.isalpha()]
        if len(letters) < 8:
            return segment
        upper_ratio = sum(char.isupper() for char in letters) / len(letters)
        if upper_ratio < 0.80:
            def fix_word(match: re.Match[str]) -> str:
                token = match.group(0)
                if token in ACRONYMS:
                    return token
                return token[:1].upper() + token[1:].lower()
            segment = re.sub(r"\b[A-Z][A-Z'’]{3,}\b", fix_word, segment)
            return restore(segment)
        lowered = segment.lower()
        lowered = re.sub(r"(^|[.!?]\s+)([a-z])", lambda match: match.group(1) + match.group(2).upper(), lowered)
        return restore(lowered)

    parts = re.split(r"(\s+[|•]\s+)", text)
    return "".join(part if re.fullmatch(r"\s+[|•]\s+", part) else fix(part) for part in parts)


def clean_story_title(value: str, source_name: str = "") -> str:
    title = clean_text(value)
    if not title:
        return ""
    if source_name:
        title = re.sub(rf"\s*(?:\||•| - )\s*{re.escape(source_name)}\s*$", "", title, flags=re.I).strip()
    if "london police" in source_name.lower():
        title = re.sub(r"\s+\d{2,4}[-–]\d{4,}\s*$", "", title).strip()
    return normalize_source_case(title)


def source_boilerplate(source_name: str) -> tuple[str, ...]:
    if "free press" in source_name.lower():
        return POSTMEDIA_BOILERPLATE
    return ()


def is_boilerplate_block(value: str, source_name: str = "") -> bool:
    text = clean_text(value)
    if not text:
        return True
    key = boilerplate_key(text)
    if any(boilerplate_key(phrase) in key for phrase in GENERIC_BOILERPLATE + source_boilerplate(source_name)):
        return True
    if len(text) <= 90 and re.fullmatch(
        r"(?i)(sign in|log in|create an account|subscribe|subscribe now|register|comments?|share|advertisement|recommended|most popular|latest news)[.!]?",
        text.strip(),
    ):
        return True
    if len(text) <= 150 and any(key.startswith(prefix) for prefix in (
        "newsletter", "recommended from editorial", "top stories", "read next", "more on this topic",
        "you might also like", "related content", "most read", "trending now",
    )):
        return True
    return False


def comparison_key(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", clean_text(value).lower())).strip()


def near_duplicate(left: str, right: str) -> bool:
    a, b = comparison_key(left), comparison_key(right)
    if not a or not b:
        return False
    if a == b:
        return True
    short, long = (a, b) if len(a) <= len(b) else (b, a)
    if len(short) >= 28 and long.startswith(short) and len(short) / max(1, len(long)) >= 0.58:
        return True
    return len(short) >= 44 and SequenceMatcher(None, a, b).ratio() >= 0.88


def title_stems(title: str) -> list[str]:
    base = re.split(r"\s+[|•]\s+", clean_text(title), maxsplit=1)[0].strip()
    if not base:
        return []
    stems = [base]
    no_file = re.sub(r"\s+\d{2,4}[-–]\d{4,}\s*$", "", base).strip()
    if len(no_file) >= 18 and no_file not in stems:
        stems.append(no_file)
    return stems


def strip_title_echo(value: str, title: str) -> str:
    text = clean_text(value)
    if not text or not title:
        return text
    for stem in sorted(title_stems(title), key=len, reverse=True):
        if near_duplicate(text, stem) and len(text) <= len(stem) + 45:
            return ""
        text_words = list(re.finditer(r"[A-Za-z0-9]+(?:[-’'][A-Za-z0-9]+)?", text))
        stem_words = re.findall(r"[A-Za-z0-9]+(?:[-’'][A-Za-z0-9]+)?", stem)
        common = 0
        for match, word in zip(text_words, stem_words):
            if comparison_key(match.group(0)) != comparison_key(word):
                break
            common += 1
        if common >= 4 and sum(len(word) for word in stem_words[:common]) >= 20:
            end = text_words[common - 1].end()
            remainder = text[end:].lstrip(" \t|:;,.!?-–—")
            return remainder if len(remainder) >= 20 else ""
    return text


def clean_article_blocks(blocks: list[str], source_name: str = "", title: str = "", stats: dict[str, int] | None = None) -> list[str]:
    cleaned: list[str] = []
    for block in blocks:
        if stats is not None:
            stats["raw_text_blocks"] = stats.get("raw_text_blocks", 0) + 1
        text = clean_text(strip_title_echo(normalize_source_case(block), title))
        if len(text) < 25:
            if stats is not None:
                stats["short_removed"] = stats.get("short_removed", 0) + 1
            continue
        if is_boilerplate_block(text, source_name):
            if stats is not None:
                stats["boilerplate_removed"] = stats.get("boilerplate_removed", 0) + 1
            continue
        if any(near_duplicate(text, earlier) for earlier in cleaned[-12:]):
            if stats is not None:
                stats["duplicates_removed"] = stats.get("duplicates_removed", 0) + 1
            continue
        cleaned.append(text)
    return cleaned


def clean_summary_text(value: str, title: str, paragraphs: list[str] | None = None) -> str:
    summary = normalize_source_case(value)
    for _ in range(3):
        previous = summary
        summary = strip_title_echo(summary, title)
        summary = re.sub(r"^\s*\d{2,4}[-–]\d{4,}\s*(?:[|:;-]\s*)?", "", summary).strip()
        summary = normalize_source_case(summary)
        if summary == previous:
            break
    summary = clean_text(summary, 360)
    if not summary or near_duplicate(summary, title):
        return ""
    if paragraphs and near_duplicate(summary, paragraphs[0]):
        return clean_text(summary, 360)
    return summary


def canonical_url(url: str) -> str:
    if not url:
        return ""
    parsed = urlparse(url.strip())
    query = parsed.query if "news.google.com" in parsed.netloc else ""
    return urlunparse(parsed._replace(fragment="", query=query)).rstrip("/")


def normalize_image_url(url: str, base_url: str = "") -> str:
    if not url:
        return ""
    absolute = urljoin(base_url, str(url).strip())
    parsed = urlparse(absolute)
    return urlunparse(parsed._replace(fragment=""))


def image_dedupe_key(url: str) -> str:
    parsed = urlparse(normalize_image_url(url))
    ignored = {"w", "width", "h", "height", "q", "quality", "fit", "crop", "auto", "format", "fm"}
    query = [(key, value) for key, value in parse_qsl(parsed.query, keep_blank_values=True) if key.lower() not in ignored]
    return urlunparse(parsed._replace(query=urlencode(query), fragment=""))


def make_id(url: str) -> str:
    return hashlib.sha1(canonical_url(url).encode("utf-8")).hexdigest()[:16]


def parse_date(value: Any) -> str:
    if not value:
        return datetime.now(timezone.utc).isoformat()
    try:
        dt = date_parser.parse(str(value))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()
    except Exception:
        return datetime.now(timezone.utc).isoformat()


def classify(title: str, summary: str, source: str) -> str:
    haystack = f"{title} {summary} {source}".lower()
    for category, needles in CATEGORY_RULES:
        if any(word in haystack for word in needles):
            return category
    return "Local"


def image_from_entry(entry: Any) -> str:
    candidates: list[str] = []
    for field in ("media_content", "media_thumbnail"):
        for media in entry.get(field, []) or []:
            if isinstance(media, dict) and media.get("url"):
                candidates.append(media["url"])
    for enclosure in entry.get("enclosures", []) or []:
        if enclosure.get("href") and str(enclosure.get("type", "")).startswith("image"):
            candidates.append(enclosure["href"])
    return candidates[0] if candidates else ""


def fetch_html(url: str) -> tuple[str, str]:
    response = SESSION.get(url, timeout=REQUEST_TIMEOUT, allow_redirects=True)
    response.raise_for_status()
    return response.text, response.url


def soup_meta(soup: BeautifulSoup, *keys: tuple[str, str]) -> str:
    for attr, value in keys:
        tag = soup.find("meta", attrs={attr: value})
        if tag and tag.get("content"):
            return clean_text(tag.get("content"))
    return ""


def json_ld_objects(soup: BeautifulSoup) -> list[dict[str, Any]]:
    objects: list[dict[str, Any]] = []
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        raw = script.string or script.get_text(strip=True)
        if not raw:
            continue
        try:
            payload = json.loads(raw)
        except Exception:
            continue
        queue: list[Any] = payload if isinstance(payload, list) else [payload]
        while queue:
            item = queue.pop(0)
            if isinstance(item, dict):
                graph = item.get("@graph")
                if isinstance(graph, list):
                    queue.extend(graph)
                objects.append(item)
            elif isinstance(item, list):
                queue.extend(item)
    return objects


def article_json_ld(soup: BeautifulSoup) -> dict[str, Any]:
    preferred = {"NewsArticle", "Article", "ReportageNewsArticle", "BlogPosting"}
    for item in json_ld_objects(soup):
        kinds = item.get("@type", "")
        kinds = {kinds} if isinstance(kinds, str) else set(str(x) for x in kinds) if isinstance(kinds, list) else set()
        if kinds & preferred:
            return item
    return {}


def json_ld_author(value: Any) -> str:
    if isinstance(value, str):
        return clean_text(value)
    if isinstance(value, dict):
        return clean_text(value.get("name"))
    if isinstance(value, list):
        return ", ".join(name for name in (json_ld_author(item) for item in value) if name)
    return ""


def json_ld_image_objects(value: Any) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    if isinstance(value, str):
        found.append({"url": value})
    elif isinstance(value, dict):
        url = value.get("url") or value.get("contentUrl")
        if url:
            found.append({
                "url": str(url),
                "width": value.get("width"),
                "height": value.get("height"),
                "caption": value.get("caption") or value.get("description") or "",
            })
    elif isinstance(value, list):
        for item in value:
            found.extend(json_ld_image_objects(item))
    return found


def best_img_url(img: Tag, base_url: str) -> str:
    candidates: list[tuple[int, str]] = []
    for attr in ("data-src", "data-lazy-src", "data-original", "src"):
        if img.get(attr):
            candidates.append((1, str(img.get(attr))))
    srcset = img.get("srcset") or img.get("data-srcset")
    if srcset:
        for part in str(srcset).split(","):
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
    for _, candidate in sorted(candidates, key=lambda item: item[0], reverse=True):
        if candidate and not candidate.startswith(("data:", "blob:")):
            return normalize_image_url(candidate, base_url)
    return ""


def int_attr(value: Any) -> int:
    try:
        return int(re.sub(r"\D", "", str(value or "0")) or "0")
    except Exception:
        return 0


def valid_article_image(url: str, img: Tag | None = None) -> bool:
    if not url or url.lower().endswith((".svg", ".gif")):
        return False
    lower = url.lower()
    if any(token in lower for token in IMAGE_JUNK):
        return False
    if img is not None:
        alt = clean_text(img.get("alt") or "").lower()
        classes = " ".join(img.get("class", [])).lower()
        if any(token in f"{alt} {classes}" for token in IMAGE_JUNK):
            return False
        width, height = int_attr(img.get("width")), int_attr(img.get("height"))
        if width and width < 240:
            return False
        if height and height < 160:
            return False
        if width and height and width * height < 60000:
            return False
    return True


def figure_caption(img: Tag) -> str:
    figure = img.find_parent("figure")
    if figure:
        cap = figure.find("figcaption")
        if cap:
            return clean_text(cap.get_text(" ", strip=True), 320)
    return ""


def collect_image_candidates(soup: BeautifulSoup, base_url: str, ld: dict[str, Any], feed_image: str = "") -> list[dict[str, Any]]:
    candidates: dict[str, dict[str, Any]] = {}

    def add(url: str, score: int, alt: str = "", caption: str = "", width: int = 0, height: int = 0, img: Tag | None = None) -> None:
        url = normalize_image_url(url, base_url)
        if not valid_article_image(url, img):
            return
        key = image_dedupe_key(url)
        if not key:
            return
        dimensions = width * height if width and height else 0
        candidate = {
            "url": url,
            "alt": clean_text(alt, 180),
            "caption": clean_text(caption, 320),
            "width": width or None,
            "height": height or None,
            "score": score + min(220, dimensions // 12000),
        }
        if key not in candidates or candidate["score"] > candidates[key]["score"]:
            candidates[key] = candidate

    for item in json_ld_image_objects(ld.get("image")):
        add(item.get("url", ""), 1000, caption=item.get("caption", ""), width=int_attr(item.get("width")), height=int_attr(item.get("height")))

    og_image = soup_meta(soup, ("property", "og:image"))
    twitter_image = soup_meta(soup, ("name", "twitter:image"), ("property", "twitter:image"))
    if og_image:
        add(og_image, 940)
    if twitter_image:
        add(twitter_image, 900)
    if feed_image:
        add(feed_image, 840)

    selectors = [
        "article figure img", "[itemprop='articleBody'] figure img", "article picture img",
        "[itemprop='articleBody'] picture img", "article img", "[itemprop='articleBody'] img", "main figure img",
    ]
    order = 0
    for selector in selectors:
        for img in soup.select(selector):
            if not isinstance(img, Tag):
                continue
            url = best_img_url(img, base_url)
            if not valid_article_image(url, img):
                continue
            width, height = int_attr(img.get("width")), int_attr(img.get("height"))
            classes = " ".join(img.get("class", [])).lower()
            parent_classes = " ".join((img.parent.get("class", []) if isinstance(img.parent, Tag) else [])).lower()
            hero_bonus = 120 if any(token in f"{classes} {parent_classes}" for token in ("hero", "lead", "featured", "main-image")) else 0
            add(url, 720 + hero_bonus - min(order, 80), img.get("alt") or "", figure_caption(img), width, height, img)
            order += 1

    return sorted(candidates.values(), key=lambda item: item["score"], reverse=True)


def profile_for(source_name: str) -> dict[str, Any]:
    return SOURCE_PROFILES.get(source_name, {"profile": "generic", "roots": GENERIC_ROOTS, "remove": []})


def tag_signature(tag: Tag) -> str:
    classes = " ".join(tag.get("class", [])).lower()
    return f"{tag.name} {tag.get('id', '')} {classes}".lower()


def has_junk_ancestor(tag: Tag, root: Tag) -> bool:
    current: Tag | None = tag
    while isinstance(current, Tag):
        signature = tag_signature(current)
        if any(token in signature for token in JUNK_CLASS_TOKENS):
            return True
        if current is root:
            break
        current = current.parent if isinstance(current.parent, Tag) else None
    return False


def score_root(tag: Tag) -> int:
    text_nodes = tag.select("p, h2, h3, blockquote, li")
    text_chars = sum(len(clean_text(node.get_text(" ", strip=True))) for node in text_nodes)
    link_chars = sum(len(clean_text(node.get_text(" ", strip=True))) for node in tag.select("a"))
    paragraphs = len(tag.select("p"))
    return text_chars + paragraphs * 90 - int(link_chars * 0.35)


def choose_article_root(soup: BeautifulSoup, source_name: str) -> tuple[Tag | None, str]:
    profile = profile_for(source_name)
    profile_roots = profile.get("roots", [])
    selectors = list(dict.fromkeys(profile_roots + GENERIC_ROOTS))
    candidates: list[tuple[int, int, Tag, str]] = []
    for priority, selector in enumerate(selectors):
        for candidate in soup.select(selector):
            if isinstance(candidate, Tag):
                raw_score = score_root(candidate)
                if raw_score > 80:
                    profile_bonus = 1500 if priority < len(profile_roots) else 0
                    candidates.append((raw_score + profile_bonus, -priority, candidate, selector))
    if not candidates:
        return None, "none"
    _, _, root, selector = max(candidates, key=lambda item: (item[0], item[1]))
    return root, selector


def clean_structured_text(value: str, source_name: str, title: str, seen: list[str], stats: dict[str, int], min_length: int = 18) -> str:
    stats["raw_text_blocks"] = stats.get("raw_text_blocks", 0) + 1
    text = clean_text(strip_title_echo(normalize_source_case(value), title))
    if len(text) < min_length:
        stats["short_removed"] = stats.get("short_removed", 0) + 1
        return ""
    if is_boilerplate_block(text, source_name):
        stats["boilerplate_removed"] = stats.get("boilerplate_removed", 0) + 1
        return ""
    if any(near_duplicate(text, earlier) for earlier in seen[-14:]):
        stats["duplicates_removed"] = stats.get("duplicates_removed", 0) + 1
        return ""
    seen.append(text)
    return text


def extract_dom_blocks(soup: BeautifulSoup, base_url: str, source_name: str, title: str, lead_image: str = "") -> tuple[list[dict[str, Any]], dict[str, int], str]:
    stats: dict[str, int] = {"raw_text_blocks": 0, "boilerplate_removed": 0, "duplicates_removed": 0, "short_removed": 0, "images_rejected": 0}
    root, root_selector = choose_article_root(soup, source_name)
    if root is None:
        return [], stats, "dom:none"

    clone_soup = BeautifulSoup(str(root), "html.parser")
    clone_root = clone_soup.find()
    if not isinstance(clone_root, Tag):
        return [], stats, "dom:none"

    profile = profile_for(source_name)
    for selector in GENERIC_REMOVE_SELECTORS + profile.get("remove", []):
        try:
            for node in clone_root.select(selector):
                node.decompose()
        except Exception:
            continue

    blocks: list[dict[str, Any]] = []
    seen_text: list[str] = []
    seen_images: set[str] = set()
    lead_key = image_dedupe_key(lead_image)

    nodes = clone_root.find_all(["h2", "h3", "p", "blockquote", "ul", "ol", "figure", "img"], recursive=True)
    for node in nodes:
        if not isinstance(node, Tag) or has_junk_ancestor(node, clone_root):
            continue

        if node.name == "p" and node.find_parent(["blockquote", "li", "figcaption"]):
            continue
        if node.name in ("ul", "ol") and node.find_parent(["ul", "ol"]):
            continue
        if node.name == "img" and node.find_parent("figure"):
            continue

        if node.name in ("p", "h2", "h3", "blockquote"):
            min_length = 4 if node.name in ("h2", "h3") else 18
            text = clean_structured_text(node.get_text(" ", strip=True), source_name, title, seen_text, stats, min_length=min_length)
            if not text:
                continue
            if node.name == "p":
                blocks.append({"type": "paragraph", "text": text})
            elif node.name in ("h2", "h3"):
                blocks.append({"type": "heading", "level": int(node.name[-1]), "text": text})
            else:
                blocks.append({"type": "quote", "text": text})
            continue

        if node.name in ("ul", "ol"):
            items: list[str] = []
            for li in node.find_all("li", recursive=False):
                text = clean_text(normalize_source_case(li.get_text(" ", strip=True)))
                if len(text) >= 5 and not is_boilerplate_block(text, source_name):
                    items.append(text)
            if items:
                joined = " ".join(items)
                if not any(near_duplicate(joined, earlier) for earlier in seen_text[-10:]):
                    seen_text.append(joined)
                    blocks.append({"type": "list", "ordered": node.name == "ol", "items": items})
            continue

        img = node.find("img") if node.name == "figure" else node if node.name == "img" else None
        if not isinstance(img, Tag):
            continue
        url = best_img_url(img, base_url)
        if not valid_article_image(url, img):
            stats["images_rejected"] = stats.get("images_rejected", 0) + 1
            continue
        key = image_dedupe_key(url)
        if not key or key == lead_key or key in seen_images:
            continue
        seen_images.add(key)
        blocks.append({
            "type": "image",
            "url": url,
            "alt": clean_text(img.get("alt") or "", 180),
            "caption": figure_caption(img),
        })

    method = f"dom:{profile.get('profile', 'generic')}:{root_selector}"
    return blocks, stats, method


def text_from_blocks(blocks: list[dict[str, Any]]) -> tuple[list[str], str]:
    paragraphs: list[str] = []
    for block in blocks:
        kind = block.get("type")
        if kind in ("paragraph", "quote") and block.get("text"):
            paragraphs.append(clean_text(block["text"]))
        elif kind == "list":
            paragraphs.extend(clean_text(item) for item in block.get("items", []) if clean_text(item))
    return paragraphs, "\n\n".join(paragraphs)


def fallback_blocks(paragraphs: list[str], images: list[dict[str, Any]]) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    if not paragraphs:
        return blocks
    interval = max(3, len(paragraphs) // (len(images) + 1)) if images else 0
    image_index = 0
    for index, paragraph in enumerate(paragraphs):
        blocks.append({"type": "paragraph", "text": paragraph})
        if images and image_index < len(images) and interval and (index + 1) % interval == 0:
            image = images[image_index]
            blocks.append({"type": "image", "url": image["url"], "alt": image.get("alt", ""), "caption": image.get("caption", "")})
            image_index += 1
    return blocks


def extracted_article_text(raw: str, final_url: str, source_name: str = "", title: str = "") -> tuple[str, list[str], dict[str, Any]]:
    metadata: dict[str, Any] = {}
    text = ""
    try:
        payload = extract(
            raw, url=final_url, output_format="json", with_metadata=True, include_comments=False,
            include_tables=True, favor_recall=True,
        )
        if payload:
            metadata = json.loads(payload)
            text = metadata.get("text") or metadata.get("raw_text") or ""
    except Exception:
        metadata = {}

    if len(clean_text(text)) < MIN_ARTICLE_CHARS:
        try:
            doc = bare_extraction(raw, url=final_url, include_comments=False, include_tables=True, favor_recall=True)
            if doc:
                candidate = getattr(doc, "text", None) if not isinstance(doc, dict) else doc.get("text") or doc.get("raw_text")
                if candidate:
                    text = candidate
                for key in ("title", "author", "date", "description"):
                    value = getattr(doc, key, None) if not isinstance(doc, dict) else doc.get(key)
                    if value and not metadata.get(key):
                        metadata[key] = value
        except Exception:
            pass

    paragraphs = clean_article_blocks([part for part in re.split(r"\n+", text) if clean_text(part)], source_name, title)
    return "\n\n".join(paragraphs), paragraphs, metadata


def extraction_quality(story: dict[str, Any], stats: dict[str, int], method: str) -> dict[str, Any]:
    word_count = int(story.get("word_count") or 0)
    blocks = story.get("content_blocks") or []
    text_blocks = sum(1 for block in blocks if block.get("type") in ("paragraph", "heading", "quote", "list"))
    rich_blocks = sum(1 for block in blocks if block.get("type") in ("heading", "quote", "list"))
    image_blocks = sum(1 for block in blocks if block.get("type") == "image")

    score = 12
    if word_count >= 700:
        score += 35
    elif word_count >= 400:
        score += 30
    elif word_count >= 250:
        score += 25
    elif word_count >= 150:
        score += 18
    elif word_count >= 80:
        score += 9

    if text_blocks >= 10:
        score += 16
    elif text_blocks >= 6:
        score += 13
    elif text_blocks >= 3:
        score += 9
    elif text_blocks >= 2:
        score += 5

    score += min(6, rich_blocks * 2)
    if story.get("image"):
        score += 6
    if image_blocks:
        score += min(5, image_blocks * 2)
    if story.get("author"):
        score += 5
    if story.get("published"):
        score += 3
    if method.startswith("dom:") and ":generic:" not in method and ":none" not in method:
        score += 9
    elif method.startswith("dom:") and ":none" not in method:
        score += 6
    elif method.startswith("trafilatura"):
        score += 4

    removed = stats.get("boilerplate_removed", 0) + stats.get("duplicates_removed", 0)
    raw = max(1, stats.get("raw_text_blocks", 0))
    removal_ratio = removed / raw
    if removal_ratio > 0.55 and word_count < 180:
        score -= 12
    elif removal_ratio > 0.35 and word_count < 120:
        score -= 7

    paragraphs = story.get("paragraphs") or []
    if paragraphs and str(paragraphs[-1]).rstrip().endswith(("...", "…")):
        score -= 8
    if story.get("scrape_error"):
        score -= 30

    score = max(0, min(100, score))
    grade = "excellent" if score >= 85 else "good" if score >= 65 else "partial" if score >= 45 else "poor"
    return {
        "score": score,
        "grade": grade,
        "method": method,
        "text_blocks": text_blocks,
        "rich_blocks": rich_blocks,
        "image_blocks": image_blocks,
        "boilerplate_removed": stats.get("boilerplate_removed", 0),
        "duplicates_removed": stats.get("duplicates_removed", 0),
        "images_rejected": stats.get("images_rejected", 0),
    }


def stale(existing: dict[str, Any]) -> bool:
    if existing.get("extraction_schema") != EXTRACTION_SCHEMA:
        return True
    if not existing.get("content") and not existing.get("content_blocks"):
        return True
    scraped = existing.get("scraped_at")
    if not scraped:
        return True
    try:
        dt = date_parser.parse(scraped)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) - dt.astimezone(timezone.utc) >= timedelta(hours=ARTICLE_REFRESH_HOURS)
    except Exception:
        return True


def resolve_google_news(raw: str, current_url: str, source: Source) -> str:
    if "news.google.com" not in urlparse(current_url).netloc:
        return current_url
    soup = BeautifulSoup(raw, "html.parser")
    wanted_host = urlparse(source.homepage).netloc.lower().replace("www.", "")
    candidates: list[str] = []
    for anchor in soup.find_all("a", href=True):
        href = urljoin(current_url, anchor.get("href"))
        host = urlparse(href).netloc.lower().replace("www.", "")
        if not host or "google." in host or "gstatic." in host:
            continue
        candidates.append(href)
        if wanted_host and (host == wanted_host or host.endswith("." + wanted_host) or wanted_host.endswith("." + host)):
            return href
    return candidates[0] if candidates else current_url


def enrich_article(story: dict[str, Any], source: Source) -> dict[str, Any]:
    url = story.get("url", "")
    if not url:
        return story

    try:
        raw, final_url = fetch_html(url)
        resolved = resolve_google_news(raw, final_url, source)
        if resolved != final_url:
            raw, final_url = fetch_html(resolved)
    except Exception as exc:
        story["scrape_error"] = str(exc)[:240]
        story["scraped_at"] = datetime.now(timezone.utc).isoformat()
        story["content_status"] = "failed"
        story["quality"] = extraction_quality(story, {}, "failed:request")
        return story

    soup = BeautifulSoup(raw, "html.parser")
    ld = article_json_ld(soup)

    _, initial_paragraphs, extracted_meta = extracted_article_text(raw, final_url, source.name)
    raw_title = (
        clean_text(ld.get("headline")) or clean_text(extracted_meta.get("title"))
        or soup_meta(soup, ("property", "og:title"), ("name", "twitter:title")) or story.get("title", "")
    )
    title = clean_story_title(raw_title, source.name)

    image_candidates = collect_image_candidates(soup, final_url, ld, story.get("image", ""))
    lead_image = image_candidates[0]["url"] if image_candidates else normalize_image_url(story.get("image", ""), final_url)
    inline_candidates = [item for item in image_candidates if image_dedupe_key(item["url"]) != image_dedupe_key(lead_image)][:MAX_ARTICLE_IMAGES]

    dom_blocks, stats, method = extract_dom_blocks(soup, final_url, source.name, title, lead_image)
    dom_paragraphs, dom_text = text_from_blocks(dom_blocks)

    extracted_text, extracted_paragraphs, extracted_meta = extracted_article_text(raw, final_url, source.name, title)
    if len(dom_text) < MIN_ARTICLE_CHARS or len(dom_paragraphs) < 2:
        paragraphs = clean_article_blocks(extracted_paragraphs or initial_paragraphs, source.name, title, stats)
        blocks = fallback_blocks(paragraphs, inline_candidates)
        text = "\n\n".join(paragraphs)
        method = "trafilatura:fallback"
    else:
        blocks = dom_blocks
        paragraphs, text = text_from_blocks(blocks)

    raw_summary = (
        clean_text(ld.get("description"), 360) or clean_text(extracted_meta.get("description"), 360)
        or soup_meta(soup, ("property", "og:description"), ("name", "description"), ("name", "twitter:description"))
        or story.get("summary", "")
    )
    summary = clean_summary_text(raw_summary, title, paragraphs)
    if not summary and paragraphs:
        summary = clean_text(paragraphs[0], 360)

    author = (
        json_ld_author(ld.get("author")) or clean_text(extracted_meta.get("author"))
        or soup_meta(soup, ("name", "author"), ("property", "article:author")) or story.get("author", "")
    )
    published = (
        ld.get("datePublished") or extracted_meta.get("date")
        or soup_meta(soup, ("property", "article:published_time"), ("name", "date"), ("name", "parsely-pub-date"))
        or story.get("published")
    )

    word_count = len(re.findall(r"\b\w+[’'-]?\w*\b", text))
    story.update({
        "id": story.get("id") or make_id(final_url),
        "title": title,
        "url": canonical_url(final_url),
        "published": parse_date(published),
        "summary": clean_text(summary, 360),
        "image": lead_image,
        "author": clean_text(author),
        "category": classify(title, summary, source.name),
        "content": text,
        "paragraphs": paragraphs,
        "content_blocks": blocks,
        "article_images": [
            {"url": item["url"], "alt": item.get("alt", ""), "caption": item.get("caption", "")}
            for item in inline_candidates
        ],
        "word_count": word_count,
        "scraped_at": datetime.now(timezone.utc).isoformat(),
        "extraction_schema": EXTRACTION_SCHEMA,
        "extraction_profile": profile_for(source.name).get("profile", "generic"),
    })
    story.pop("scrape_error", None)
    story["quality"] = extraction_quality(story, stats, method)
    score = story["quality"]["score"]
    complete_shape = word_count >= 120 or len(paragraphs) >= 3
    story["content_status"] = "full" if score >= 55 and complete_shape else "partial" if word_count >= 55 else "summary"
    return story


def load_existing() -> list[dict[str, Any]]:
    if not DATA_FILE.exists():
        return []
    try:
        payload = json.loads(DATA_FILE.read_text(encoding="utf-8"))
        return payload.get("stories", [])
    except Exception:
        return []


def existing_lookup(stories: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    lookup: dict[str, dict[str, Any]] = {}
    for story in stories:
        if story.get("id"):
            lookup[story["id"]] = story
        if story.get("url"):
            lookup[canonical_url(story["url"])] = story
    return lookup


def rss_items(source: Source, existing: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    response = SESSION.get(source.url, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    feed = feedparser.parse(response.content)
    items: list[dict[str, Any]] = []

    for entry in feed.entries[: source.max_items]:
        url = entry.get("link", "")
        title = clean_story_title(entry.get("title"), source.name)
        if not url or not title:
            continue
        summary = clean_summary_text(entry.get("summary") or entry.get("description"), title)
        published = entry.get("published") or entry.get("updated") or entry.get("created")
        basic = {
            "id": make_id(url), "title": title, "source": source.name, "source_home": source.homepage,
            "source_accent": source.accent, "url": canonical_url(url), "published": parse_date(published),
            "summary": summary, "image": image_from_entry(entry), "author": clean_text(entry.get("author")),
            "category": classify(title, summary, source.name),
        }
        old = existing.get(basic["id"]) or existing.get(basic["url"])
        if old and not stale(old):
            merged = {**basic, **old}
            merged.update({"source": source.name, "source_home": source.homepage, "source_accent": source.accent})
            items.append(merged)
        else:
            items.append(enrich_article({**(old or {}), **basic}, source))
            time.sleep(0.14)
    return items


def page_links(source: Source) -> list[str]:
    raw, final_url = fetch_html(source.url)
    soup = BeautifulSoup(raw, "html.parser")
    host = urlparse(final_url).netloc.lower().replace("www.", "")
    links: list[str] = []
    selectors = [
        "main h2 a[href]", "main h3 a[href]", "article h2 a[href]", "article h3 a[href]",
        ".news-item a[href]", ".card a[href]", "a[href*='/news/']",
    ]
    for selector in selectors:
        for anchor in soup.select(selector):
            href = anchor.get("href")
            if not href:
                continue
            url = urljoin(final_url, href)
            if urlparse(url).netloc.lower().replace("www.", "") != host:
                continue
            if canonical_url(url) == canonical_url(source.url) or len(clean_text(anchor.get_text(" ", strip=True))) < 8:
                continue
            clean = canonical_url(url)
            if clean not in links:
                links.append(clean)
            if len(links) >= source.max_items:
                return links
    return links


def page_items(source: Source, existing: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for url in page_links(source):
        old = existing.get(make_id(url)) or existing.get(canonical_url(url))
        if old and not stale(old):
            story = {**old, "source": source.name, "source_home": source.homepage, "source_accent": source.accent}
        else:
            story = enrich_article({
                "id": make_id(url), "title": old.get("title", "") if old else "", "source": source.name,
                "source_home": source.homepage, "source_accent": source.accent, "url": canonical_url(url),
                "published": old.get("published", datetime.now(timezone.utc).isoformat()) if old else datetime.now(timezone.utc).isoformat(),
                "summary": old.get("summary", "") if old else "", "image": old.get("image", "") if old else "",
                "author": old.get("author", "") if old else "", "category": old.get("category", "Local") if old else "Local",
            }, source)
            time.sleep(0.14)
        if story.get("title"):
            items.append(story)
    return items


def sanitize_content_blocks(blocks: list[dict[str, Any]], source_name: str, title: str) -> list[dict[str, Any]]:
    cleaned: list[dict[str, Any]] = []
    seen: list[str] = []
    for block in blocks:
        if not isinstance(block, dict):
            continue
        kind = block.get("type")
        if kind in ("paragraph", "heading", "quote"):
            text = clean_text(strip_title_echo(normalize_source_case(block.get("text", "")), title))
            min_length = 4 if kind == "heading" else 18
            if len(text) < min_length or is_boilerplate_block(text, source_name) or any(near_duplicate(text, prior) for prior in seen[-12:]):
                continue
            seen.append(text)
            cleaned.append({**block, "text": text})
        elif kind == "list":
            items = [clean_text(normalize_source_case(item)) for item in block.get("items", [])]
            items = [item for item in items if len(item) >= 5 and not is_boilerplate_block(item, source_name)]
            if items:
                cleaned.append({"type": "list", "ordered": bool(block.get("ordered")), "items": items})
        elif kind == "image" and valid_article_image(block.get("url", "")):
            cleaned.append({
                "type": "image", "url": normalize_image_url(block.get("url", "")),
                "alt": clean_text(block.get("alt", ""), 180), "caption": clean_text(block.get("caption", ""), 320),
            })
    return cleaned


def sanitize_cached_story(story: dict[str, Any]) -> dict[str, Any]:
    source_name = story.get("source", "")
    title = clean_story_title(story.get("title", ""), source_name)
    story["title"] = title

    existing_blocks = story.get("content_blocks") if isinstance(story.get("content_blocks"), list) else []
    if existing_blocks:
        blocks = sanitize_content_blocks(existing_blocks, source_name, title)
        paragraphs, text = text_from_blocks(blocks)
    else:
        raw_blocks = story.get("paragraphs") or re.split(r"\n+", str(story.get("content", "")))
        paragraphs = clean_article_blocks([str(block) for block in raw_blocks], source_name, title)
        text = "\n\n".join(paragraphs)
        blocks = fallback_blocks(paragraphs, story.get("article_images") or [])

    story["paragraphs"] = paragraphs
    story["content"] = text
    story["content_blocks"] = blocks
    story["word_count"] = len(re.findall(r"\b\w+[’'-]?\w*\b", text))
    summary = clean_summary_text(story.get("summary", ""), title, paragraphs)
    story["summary"] = summary or (clean_text(paragraphs[0], 360) if paragraphs else "")
    story["category"] = classify(title, story["summary"], source_name)

    if not isinstance(story.get("quality"), dict):
        story["quality"] = extraction_quality(story, {}, "cached:legacy")
    if story.get("content_status") == "full" and story["word_count"] < 55:
        story["content_status"] = "summary"
    return story


def backfill_missing(stories: list[dict[str, Any]]) -> list[dict[str, Any]]:
    source_by_name = {source.name: source for source in SOURCES}
    done = 0
    for story in stories:
        if done >= BACKFILL_PER_RUN:
            break
        needs_upgrade = story.get("extraction_schema") != EXTRACTION_SCHEMA
        needs_content = story.get("content_status") not in ("full", "partial") or not story.get("content")
        if not needs_upgrade and not needs_content:
            continue
        source = source_by_name.get(story.get("source", ""))
        if not source or not story.get("url"):
            continue
        print(f"Backfill: {story.get('source')} | {story.get('title', '')[:70]}")
        enrich_article(story, source)
        done += 1
        time.sleep(0.18)
    return stories


def build_source_health(stories: list[dict[str, Any]], run_counts: dict[str, int], run_errors: dict[str, str]) -> list[dict[str, Any]]:
    health: list[dict[str, Any]] = []
    now = datetime.now(timezone.utc).isoformat()
    for source in SOURCES:
        recent = [story for story in stories if story.get("source") == source.name][:30]
        scores = [int((story.get("quality") or {}).get("score") or 0) for story in recent]
        grades = [str((story.get("quality") or {}).get("grade") or "poor") for story in recent]
        full = sum(1 for story in recent if story.get("content_status") == "full")
        partial = sum(1 for story in recent if story.get("content_status") in ("partial", "summary"))
        failed = sum(1 for story in recent if story.get("content_status") == "failed" or story.get("scrape_error"))
        avg = round(sum(scores) / len(scores)) if scores else 0
        last_scrape = max((story.get("scraped_at", "") for story in recent), default="")
        error = run_errors.get(source.name, "")
        status = (
            "error" if error and not recent
            else "degraded" if error
            else "healthy" if avg >= 65 and failed == 0
            else "degraded" if recent
            else "waiting"
        )
        health.append({
            "source": source.name,
            "accent": source.accent,
            "profile": profile_for(source.name).get("profile", "generic"),
            "status": status,
            "checked_at": now,
            "found_this_run": run_counts.get(source.name, 0),
            "tracked": len(recent),
            "full": full,
            "partial": partial,
            "failed": failed,
            "excellent": grades.count("excellent"),
            "good": grades.count("good"),
            "poor": grades.count("poor"),
            "average_quality": avg,
            "last_scrape": last_scrape,
            "last_error": error,
        })
    return health


def main() -> int:
    previous = load_existing()
    lookup = existing_lookup(previous)
    fresh: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    run_errors: dict[str, str] = {}
    run_counts: dict[str, int] = {}

    for source in SOURCES:
        try:
            items = rss_items(source, lookup) if source.kind == "rss" else page_items(source, lookup)
            fresh.extend(items)
            run_counts[source.name] = len(items)
            full_count = sum(1 for item in items if item.get("content_status") == "full")
            print(f"{source.name}: {len(items)} items, {full_count} full")
        except Exception as exc:
            message = str(exc)[:240]
            errors.append({"source": source.name, "error": message})
            run_errors[source.name] = message
            print(f"{source.name}: ERROR {exc}", file=sys.stderr)

    merged: dict[str, dict[str, Any]] = {}
    for story in previous + fresh:
        key = story.get("id") or make_id(story.get("url", ""))
        if key:
            merged[key] = story

    stories = sorted(merged.values(), key=lambda item: item.get("published", ""), reverse=True)[:HISTORY_LIMIT]
    stories = [sanitize_cached_story(story) for story in stories]
    stories = backfill_missing(stories)

    now = datetime.now(timezone.utc).isoformat()
    full_count = sum(1 for item in stories if item.get("content_status") == "full")
    partial_count = sum(1 for item in stories if item.get("content_status") == "partial")
    scores = [int((item.get("quality") or {}).get("score") or 0) for item in stories if item.get("quality")]
    payload = {
        "schema_version": EXTRACTION_SCHEMA,
        "generated_at": now,
        "story_count": len(stories),
        "full_story_count": full_count,
        "partial_story_count": partial_count,
        "average_quality": round(sum(scores) / len(scores)) if scores else 0,
        "source_count": len(SOURCES),
        "errors": errors,
        "source_health": build_source_health(stories, run_counts, run_errors),
        "stories": stories,
    }
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    DATA_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {len(stories)} stories ({full_count} full, {partial_count} partial) to {DATA_FILE}")
    return 0 if stories else 1


if __name__ == "__main__":
    raise SystemExit(main())
