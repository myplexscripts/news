from __future__ import annotations

import hashlib
import html
import json
from io import BytesIO
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

import feedparser
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from bs4 import BeautifulSoup, Tag
from dateutil import parser as date_parser
from trafilatura import bare_extraction, extract
from PIL import Image, ImageFilter

from sources import SOURCES, Source
from ranking import GOOGLE_DISCOVERY_MIN_LOCAL_SCORE, apply_editorial_intelligence

ROOT = Path(__file__).resolve().parents[1]
DATA_FILE = ROOT / "data" / "news.json"
CARD_IMAGE_DIR = ROOT / "public" / "cache" / "news"
HISTORY_LIMIT = 750
REQUEST_TIMEOUT = 30
ARTICLE_REFRESH_HOURS = 12
BACKFILL_PER_RUN = 36
MIN_ARTICLE_CHARS = 320
MAX_ARTICLE_IMAGES = 10
EXTRACTION_SCHEMA = 11
LOCAL_TIMEZONE = ZoneInfo("America/Toronto")
USER_AGENT = "LondonNewsAggregator/3.0 (+https://github.com/)"

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/rss+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-CA,en;q=0.9",
})
RETRY_POLICY = Retry(
    total=2,
    connect=2,
    read=2,
    status=2,
    backoff_factor=0.65,
    status_forcelist=(429, 500, 502, 503, 504),
    allowed_methods=frozenset({"GET"}),
    raise_on_status=False,
)
SESSION.mount("https://", HTTPAdapter(max_retries=RETRY_POLICY))
SESSION.mount("http://", HTTPAdapter(max_retries=RETRY_POLICY))

# CBC occasionally stalls from GitHub-hosted runners. Fail fast for CBC requests
# and keep the last successful cached stories instead of spending minutes retrying.
CBC_REQUEST_TIMEOUT = 12
CBC_FEED_TIMEOUT = 8
FAST_SESSION = requests.Session()
FAST_SESSION.headers.update(SESSION.headers)
FAST_SESSION.mount("https://", HTTPAdapter(max_retries=Retry(total=0)))
FAST_SESSION.mount("http://", HTTPAdapter(max_retries=Retry(total=0)))

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
    "recommended video", "related stories", "related story", "more from", "you may also like", "read more from", "all rights reserved",
    "back to news search subscribe", "back to news search", "trending stories", "trending now", "most popular", "top stories", "watch more",
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
    "unlock more articles", "manage print subscription", "trending", "most read",
    "exclusive articles from", "noon news roundup newsletter", "lfp weekender newsletter",
)

GLOBAL_BOILERPLATE = (
    "if you get global news from instagram or facebook",
    "find out how you can still connect with us",
    "hide message bar",
    "leave a comment share this item",
    "share this item on facebook",
    "share this item via whatsapp",
    "send this page to someone via email",
    "see more sharing options",
    "decrease article font size",
    "descrease article font size",
    "increase article font size",
    "get daily national news",
    "get daily canada news delivered to your inbox",
    "get daily national news delivered to your inbox",
    "add global news as a preferred source on google",
    "previous video",
    "next video",
    "click to play video",
    "recommended video",
)


CTV_BOILERPLATE = (
    "ctv news app", "download the ctv news app", "contact us", "newsletters",
    "sign up for our newsletters", "more from ctv news", "related stories",
    "recommended for you", "watch more", "latest videos", "advertisement",
    "bell media", "privacy policy", "terms and conditions", "team",
)

CTV_STOP_MARKERS = (
    "ctv news app", "contact us", "faq", "newsletters", "team",
    "related stories", "more from ctv news", "recommended for you",
    "latest videos", "watch more",
)


SOURCE_NAME_ALIASES = {
    "CBC": "CBC News London",
    "CBC.ca": "CBC News London",
    "Global News": "Global News London",
    "CTV News London": "CTV News",
    "CTV London": "CTV News",
    "The London Free Press": "London Free Press",
    "London Free Press": "London Free Press",
    "104.7 Heart FM": "104.7 Heart FM",
    "Heart FM": "104.7 Heart FM",
}

SOURCE_ACCENTS = {
    "Global News London": "#0088ff",
    "CBC News London": "#ff383c",
    "London Free Press": "#6155f5",
    "CTV News": "#6155f5",
    "106.9 The X": "#ff8d28",
    "City of London Newsroom": "#cb30e0",
    "London Police Service": "#0088ff",
    "London Fire Department": "#ff383c",
    "104.7 Heart FM": "#ff2d55",
}


def canonical_source_name(value: str | None) -> str:
    name = clean_text(value) if 'clean_text' in globals() else (value or '').strip()
    return SOURCE_NAME_ALIASES.get(name, name) or "Unknown source"



DIRECT_SOURCE_NAMES = {
    canonical_source_name(source.name)
    for source in SOURCES
    if source.kind != "google_topic"
}


def is_unusable_google_story(story: dict[str, Any]) -> bool:
    """Reject unresolved Google News shells and discovery copies of direct sources."""
    if not story:
        return True
    title = clean_text(story.get("title", "")).lower()
    url = story.get("url", "")
    host = urlparse(url).netloc.lower()
    source_name = canonical_source_name(story.get("source", ""))
    via_google = bool(story.get("discovery_via"))
    if title in {"google news", "google"}:
        return True
    if via_google and "news.google.com" in host:
        return True
    if via_google and source_name in DIRECT_SOURCE_NAMES:
        return True
    return False


def accent_for_source(name: str) -> str:
    if name in SOURCE_ACCENTS:
        return SOURCE_ACCENTS[name]
    palette = ["#0088ff", "#ff383c", "#ff8d28", "#34c759", "#00c8b3", "#00c3d0", "#6155f5", "#cb30e0", "#ff2d55"]
    digest = hashlib.sha1(name.encode("utf-8", "ignore")).digest()
    return palette[digest[0] % len(palette)]


SOURCE_PROFILES: dict[str, dict[str, Any]] = {
    "Global News London": {
        "profile": "global",
        "roots": [
            ".l-article__body", ".l-article__content", ".article-content",
            "[data-testid='article-body']", "[itemprop='articleBody']", "article"
        ],
        "remove": [
            ".l-article__related", ".l-relatedStories", ".l-inlineStories", ".c-posts",
            ".c-readmore", "[data-shortcode='readmore']", "[data-shortcode*='video']",
            ".c-ad", ".ad", "[class*='advert']", "[class*='sponsor']",
            ".newsletter", "[class*='newsletter']", "[class*='email-signup']",
            ".share", "[class*='share']", "[class*='social']",
            "[class*='video']", "[class*='Video']", "[data-testid*='video']",
            "[class*='player']", "[class*='playlist']", "[class*='message-bar']",
            "[class*='recirc']", "[class*='recommended']", "[class*='preferred-source']"
        ],
        "strict_dom": True,
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
            "[class*='trending']", "[id*='trending']", "[data-testid*='trending']",
            "[class*='most-read']", "[class*='most-popular']", "[class*='popular']",
        ],
    },
    "CTV News": {
        "profile": "ctv",
        "roots": [
            "[data-testid='article-body']", "[data-testid*='article-body']",
            "[data-testid*='articleBody']", "[class*='articleBody']", "[class*='ArticleBody']",
            ".articleBody", ".article-body", ".article__body", ".article-content",
            ".story-body", "[class*='storyBody']", "[class*='StoryBody']",
            "[itemprop='articleBody']", "main article", "article", "main"
        ],
        "remove": [
            ".related", ".newsletter", ".share", ".social", ".ad", ".advertisement",
            "[class*='related']", "[class*='recommend']", "[class*='advert']",
            "[class*='newsletter']", "[class*='recirc']", "[class*='popular']",
            "[class*='video']", "[data-testid*='video']", "[class*='player']",
            "nav", "footer", "aside"
        ],
    },
    "104.7 Heart FM": {
        "profile": "heartfm",
        "roots": [
            ".news-article", ".article-body", ".story-body", ".entry-content",
            ".content-body", "[itemprop='articleBody']", "article", "main"
        ],
        "remove": [
            ".related", ".share", ".social", ".newsletter", ".advert", ".ad",
            ".on-air", ".now-playing", "nav", "footer", "aside",
            "[class*='related']", "[class*='more-from']", "[class*='morefrom']",
            "[class*='recommend']", "[class*='comments']", "[id*='comments']"
        ],
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
        "roots": [".news-article-content", ".news-post-content", ".news-post__content", ".field--name-body", ".article-content", "[itemprop='articleBody']", "article", "main"],
        "remove": [".related", ".share", ".social", ".newsletter", ".news-search", ".subscribe", "[class*='back-to']"],
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
    "account", "epaper", "puzzle", "comment", "recommend", "most-popular", "most-read", "trending", "popular", "outbrain", "taboola",
)

IMAGE_JUNK = (
    "logo", "icon", "avatar", "author", "profile", "sprite", "pixel", "tracking", "badge",
    "weather", "placeholder", "default", "newsletter", "app-store", "google-play", "social",
    "facebook", "twitter", "instagram", "tiktok", "favicon", "headshot", "crest", "coat-of-arms", "coat_of_arms", "emblem",
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
    lower = source_name.lower()
    if "free press" in lower:
        return POSTMEDIA_BOILERPLATE
    if "global news" in lower:
        return GLOBAL_BOILERPLATE
    if "ctv" in lower:
        return CTV_BOILERPLATE
    return ()



def ctv_stop_text(value: str) -> bool:
    key = boilerplate_key(value)
    if not key:
        return False
    return any(key == boilerplate_key(marker) or key.startswith(boilerplate_key(marker) + " ") for marker in CTV_STOP_MARKERS)


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
        if is_global_source(source_name) and global_stop_text(text):
            break
        if source_name == "CTV News" and ctv_stop_text(text):
            break
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


def image_path_key(url: str) -> str:
    parsed = urlparse(normalize_image_url(url))
    path = parsed.path.lower().rstrip("/")
    if not path:
        return ""
    parts = [part for part in path.split("/") if part]
    if not parts:
        return ""
    filename = re.sub(r"[-_](?:\d{2,5})x(?:\d{2,5})(?=\.[a-z0-9]{2,5}$)", "", parts[-1])
    filename = re.sub(r"[-_](?:w|h)\d{2,5}(?=\.[a-z0-9]{2,5}$)", "", filename)
    parent = parts[-2] if len(parts) > 1 else ""
    return f"{parent}/{filename}" if parent else filename


def same_image(left: str, right: str) -> bool:
    if not left or not right:
        return False
    if image_dedupe_key(left) == image_dedupe_key(right):
        return True
    left_key, right_key = image_path_key(left), image_path_key(right)
    if left_key and right_key and left_key == right_key:
        return True
    left_name = left_key.rsplit("/", 1)[-1] if left_key else ""
    right_name = right_key.rsplit("/", 1)[-1] if right_key else ""
    return len(left_name) >= 14 and left_name == right_name


def make_id(url: str) -> str:
    return hashlib.sha1(canonical_url(url).encode("utf-8")).hexdigest()[:16]


def parse_date(value: Any) -> str:
    if not value:
        return datetime.now(timezone.utc).isoformat()
    try:
        dt = date_parser.parse(str(value))
        # Local publishers often omit a zone. Treat naive timestamps as London, Ontario time.
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=LOCAL_TIMEZONE)
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
    host = urlparse(url).netloc.lower()
    is_cbc = host == "cbc.ca" or host.endswith(".cbc.ca")
    session = FAST_SESSION if is_cbc else SESSION
    timeout = CBC_REQUEST_TIMEOUT if is_cbc else REQUEST_TIMEOUT
    response = session.get(url, timeout=timeout, allow_redirects=True)
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
        if current.has_attr("hidden") or str(current.get("aria-hidden", "")).lower() == "true":
            return True
        style = str(current.get("style", "")).lower().replace(" ", "")
        if "display:none" in style or "visibility:hidden" in style:
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


def is_police_source(source_name: str) -> bool:
    return "london police" in source_name.lower()


def is_postmedia_source(source_name: str) -> bool:
    return "free press" in source_name.lower()


def is_global_source(source_name: str) -> bool:
    return "global news" in source_name.lower()


def is_heartfm_source(source_name: str) -> bool:
    lower = source_name.lower()
    return "heart fm" in lower or "104.7" in lower


def heartfm_stop_text(value: str) -> bool:
    key = boilerplate_key(value)
    return any(key.startswith(prefix) for prefix in (
        "more from local news",
        "more local news",
        "related stories",
        "related news",
        "comments",
        "add a comment",
        "weather",
        "recently played",
    ))


def global_stop_text(value: str) -> bool:
    key = boilerplate_key(value)
    return key.startswith((
        "stick to the facts", "sponsored content", "report an error",
        "journalistic standards", "journalistic standards comment",
        "copyright 202", "all rights reserved",
    ))


def police_stop_text(value: str) -> bool:
    key = boilerplate_key(value)
    return key.startswith((
        "for media inquiries", "for media enquiries", "media relations officer",
        "media relations unit", "contact media relations", "contact us",
    ))


def police_start_text(value: str) -> bool:
    text = clean_text(value)
    return bool(re.match(r"(?i)^(?:update\s*[-:]\s*)?london,?\s+on(?:t\.)?\s*\(", text))


def strip_postmedia_trending_blocks(blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not blocks:
        return blocks
    cleaned: list[dict[str, Any]] = []
    skipping = False
    for block in blocks:
        kind = block.get("type")
        text = clean_text(block.get("text", "")) if kind in ("paragraph", "heading", "quote") else ""
        key = boilerplate_key(text)
        if kind == "heading" and (key.startswith("trending") or key.startswith("most read") or key.startswith("most popular")):
            skipping = True
            continue
        if skipping:
            # Trending modules are usually a run of short linked headlines. Resume at real prose.
            if kind == "paragraph" and len(text) >= 70 and (police_start_text(text) or re.search(r"[.!?][\"'’)]?$", text)):
                skipping = False
            else:
                continue
        cleaned.append(block)
    return cleaned



CTV_EMBEDDED_BODY_KEYS = {
    "articlebody", "article_body", "articlecontent", "article_content",
    "storybody", "story_body", "bodycontent", "body_content", "body",
}
CTV_EMBEDDED_TEXT_KEYS = {"text", "html", "value", "content", "paragraph", "description"}


def _ctv_value_blocks(value: Any, source_name: str, title: str, stats: dict[str, int]) -> list[dict[str, Any]]:
    """Turn a CTV embedded JSON body value into clean structured blocks."""
    raw_blocks: list[dict[str, Any]] = []

    def append_text(raw_value: str) -> None:
        value_text = html.unescape(str(raw_value or "")).strip()
        if len(value_text) < 18:
            return
        fragment = BeautifulSoup(value_text, "html.parser")
        rich_nodes = fragment.find_all(["h2", "h3", "p", "blockquote", "li"])
        if rich_nodes:
            for node in rich_nodes:
                text = clean_text(node.get_text(" ", strip=True))
                if not text:
                    continue
                if node.name == "h2":
                    raw_blocks.append({"type": "heading", "level": 2, "text": text})
                elif node.name == "h3":
                    raw_blocks.append({"type": "heading", "level": 3, "text": text})
                elif node.name == "blockquote":
                    raw_blocks.append({"type": "quote", "text": text})
                elif node.name == "li":
                    raw_blocks.append({"type": "paragraph", "text": text})
                else:
                    raw_blocks.append({"type": "paragraph", "text": text})
            return

        # Some CTV page-state payloads store prose as escaped newline-delimited text.
        parts = [clean_text(part) for part in re.split(r"(?:\\n|\n){1,2}", value_text)]
        parts = [part for part in parts if len(part) >= 18]
        if len(parts) == 1 and len(parts[0]) > 650:
            # Last-resort sentence grouping keeps a large JSON string from becoming
            # one unreadable paragraph without inventing or rewriting any prose.
            sentences = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9‘'\"“])", parts[0])
            grouped: list[str] = []
            buffer = ""
            for sentence in sentences:
                if not sentence:
                    continue
                buffer = f"{buffer} {sentence}".strip()
                if len(buffer) >= 220:
                    grouped.append(buffer)
                    buffer = ""
            if buffer:
                grouped.append(buffer)
            if len(grouped) >= 2:
                parts = grouped
        raw_blocks.extend({"type": "paragraph", "text": part} for part in parts)

    def walk(node: Any, depth: int = 0) -> None:
        if depth > 10:
            return
        if isinstance(node, str):
            append_text(node)
            return
        if isinstance(node, list):
            for item in node:
                walk(item, depth + 1)
            return
        if isinstance(node, dict):
            preferred = []
            fallback = []
            for key, child in node.items():
                lowered = str(key).lower().replace("-", "_")
                if lowered in CTV_EMBEDDED_TEXT_KEYS:
                    preferred.append(child)
                elif isinstance(child, (dict, list)):
                    fallback.append(child)
            for child in preferred or fallback:
                walk(child, depth + 1)

    walk(value)

    cleaned: list[dict[str, Any]] = []
    seen: list[str] = []
    for block in raw_blocks:
        raw_text = clean_text(block.get("text", ""))
        min_length = 4 if block.get("type") == "heading" else 18
        text = clean_structured_text(raw_text, source_name, title, seen, stats, min_length=min_length)
        if text:
            cleaned.append({**block, "text": text})
    return cleaned


def extract_ctv_embedded_blocks(soup: BeautifulSoup, title: str) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Extract CTV article prose from any server-provided application state.

    CTV has used several React/Next rendering shapes. Some pages expose ordinary
    JSON in __NEXT_DATA__, while newer pages can serialize the same state inside
    self.__next_f.push() strings. Decode both before looking for body fields.
    """
    stats: dict[str, int] = {"raw_text_blocks": 0, "boilerplate_removed": 0, "duplicates_removed": 0, "short_removed": 0}
    candidates: list[list[dict[str, Any]]] = []

    def consider(value: Any) -> None:
        blocks = _ctv_value_blocks(value, "CTV News", title, stats)
        paragraphs, text = text_from_blocks(blocks)
        if len(paragraphs) >= 2 and len(text) >= 180:
            candidates.append(blocks)

    def scan_object(node: Any, depth: int = 0) -> None:
        if depth > 14:
            return
        if isinstance(node, list):
            for item in node:
                scan_object(item, depth + 1)
            return
        if not isinstance(node, dict):
            return
        for key, value in node.items():
            normalized = str(key).lower().replace("-", "_")
            compact = normalized.replace("_", "")
            if normalized in CTV_EMBEDDED_BODY_KEYS or compact in CTV_EMBEDDED_BODY_KEYS:
                consider(value)
            elif normalized == "content" and (
                isinstance(value, (dict, list)) or (isinstance(value, str) and len(value) > 420)
            ):
                consider(value)
            if isinstance(value, (dict, list)):
                scan_object(value, depth + 1)

    def scan_serialized_text(raw_text: str) -> None:
        if not raw_text:
            return
        text = html.unescape(raw_text)

        # First try the whole value as JSON.
        try:
            scan_object(json.loads(text))
        except Exception:
            pass

        # Pull JSON string values directly after known article-body keys. This is
        # more stable than relying on one exact application-state object shape.
        key_pattern = re.compile(
            r'["\\\'](?:articleBody|article_body|articleContent|article_content|storyBody|story_body|bodyContent|body_content|body|content)["\\\']\\s*:\\s*',
            re.I,
        )
        decoder = json.JSONDecoder()
        for match in key_pattern.finditer(text):
            tail = text[match.end():].lstrip()
            if not tail:
                continue
            try:
                value, _ = decoder.raw_decode(tail)
            except Exception:
                continue
            if isinstance(value, str) and len(value) < 160:
                continue
            consider(value)

        # Some scripts remain one level escaped after hydration serialization.
        # Decode common escaped quote/slash sequences and scan once more.
        if '\\"' in text or '\\/' in text:
            decoded = text.replace('\\/', '/').replace('\\"', '"')
            if decoded != text:
                try:
                    scan_object(json.loads(decoded))
                except Exception:
                    pass
                for match in key_pattern.finditer(decoded):
                    tail = decoded[match.end():].lstrip()
                    try:
                        value, _ = decoder.raw_decode(tail)
                    except Exception:
                        continue
                    consider(value)

    for script in soup.find_all("script"):
        raw = script.string or script.get_text("", strip=False)
        if not raw or len(raw) < 120:
            continue
        script_type = (script.get("type") or "").lower()
        script_id = (script.get("id") or "").lower()

        if "json" in script_type or script_id in {"__next_data__", "__nuxt_data__"}:
            scan_serialized_text(raw)

        # Next.js App Router stores hydration data as JSON-encoded strings inside
        # self.__next_f.push([id, "..."]). Decode each payload before scanning.
        if "__next_f.push" in raw:
            for match in re.finditer(
                r'self\.__next_f\.push\(\s*\[\s*\d+\s*,\s*("(?:\\.|[^"\\])*")\s*\]\s*\)',
                raw,
                flags=re.S,
            ):
                try:
                    payload = json.loads(match.group(1))
                except Exception:
                    continue
                scan_serialized_text(payload)

        # Legacy JavaScript assignments can contain body strings without being a
        # complete JSON document. Scan every script, but only known body keys.
        if any(key.lower() in raw.lower() for key in ("articleBody", "articleContent", "storyBody", "bodyContent")):
            scan_serialized_text(raw)

    if not candidates:
        return [], stats

    # Prefer the most complete candidate after boilerplate/duplicate cleanup.
    candidates.sort(
        key=lambda blocks: (len(text_from_blocks(blocks)[1]), len(text_from_blocks(blocks)[0])),
        reverse=True,
    )
    return candidates[0], stats

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
    seen_images: list[str] = []
    police_mode = is_police_source(source_name)
    police_started = not police_mode
    postmedia_mode = is_postmedia_source(source_name)
    postmedia_trending = False
    heartfm_mode = is_heartfm_source(source_name)
    heartfm_content_started = False
    ctv_mode = source_name == "CTV News"

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
            raw_node_text = clean_text(node.get_text(" ", strip=True))
            raw_key = boilerplate_key(raw_node_text)
            if is_global_source(source_name) and global_stop_text(raw_node_text):
                break
            if ctv_mode and ctv_stop_text(raw_node_text):
                break
            # Heart FM places a large "More from Local News" module inside the
            # same broad page region as the article. Ignore the breadcrumb copy
            # before the story, but once genuine article prose has started this
            # heading marks the hard end of the article.
            if heartfm_mode and heartfm_stop_text(raw_node_text):
                if heartfm_content_started:
                    break
                continue
            if postmedia_mode and node.name in ("h2", "h3") and (raw_key.startswith("trending") or raw_key.startswith("most read") or raw_key.startswith("most popular")):
                postmedia_trending = True
                continue
            if postmedia_trending:
                if node.name == "p" and len(raw_node_text) >= 70 and re.search(r"[.!?][\"'’)]?$", raw_node_text):
                    postmedia_trending = False
                else:
                    continue
            if police_mode and not police_started:
                if node.name in ("h2", "h3") or police_start_text(raw_node_text):
                    police_started = True
                else:
                    continue
            if police_mode and police_stop_text(raw_node_text):
                break
            min_length = 4 if node.name in ("h2", "h3") else 18
            text = clean_structured_text(raw_node_text, source_name, title, seen_text, stats, min_length=min_length)
            if not text:
                continue
            if node.name == "p":
                blocks.append({"type": "paragraph", "text": text})
                if heartfm_mode:
                    heartfm_content_started = True
            elif node.name in ("h2", "h3"):
                blocks.append({"type": "heading", "level": int(node.name[-1]), "text": text})
            else:
                blocks.append({"type": "quote", "text": text})
                if heartfm_mode:
                    heartfm_content_started = True
            continue

        if node.name in ("ul", "ol"):
            if heartfm_mode:
                anchor_texts = [clean_text(a.get_text(" ", strip=True)).lower() for a in node.select("a[href]")]
                if not heartfm_content_started and anchor_texts and all(
                    text in {"news home", "more from local news", "more local news"} for text in anchor_texts
                ):
                    continue
                related_links = []
                for anchor in node.select("a[href]"):
                    href = urljoin(base_url, str(anchor.get("href") or ""))
                    if "/news/local-news/" in href and canonical_url(href) != canonical_url(base_url):
                        related_links.append(href)
                if len(related_links) >= 2:
                    # This is Heart FM's related-story list, not article copy.
                    if heartfm_content_started:
                        break
                    continue
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
        if heartfm_mode:
            linked = img.find_parent("a", href=True)
            if isinstance(linked, Tag):
                linked_url = urljoin(base_url, str(linked.get("href") or ""))
                if "/news/local-news/" in linked_url and canonical_url(linked_url) != canonical_url(base_url):
                    stats["images_rejected"] = stats.get("images_rejected", 0) + 1
                    continue
        if not valid_article_image(url, img):
            stats["images_rejected"] = stats.get("images_rejected", 0) + 1
            continue
        key = image_dedupe_key(url)
        if not key or same_image(url, lead_image) or any(same_image(url, prior) for prior in seen_images):
            continue
        seen_images.append(url)
        blocks.append({
            "type": "image",
            "url": url,
            "alt": clean_text(img.get("alt") or "", 180),
            "caption": figure_caption(img),
        })

    if is_postmedia_source(source_name):
        blocks = strip_postmedia_trending_blocks(blocks)
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


def json_ld_body_paragraphs(ld: dict[str, Any], source_name: str, title: str, stats: dict[str, int] | None = None) -> list[str]:
    body = ld.get("articleBody") or ld.get("text") or ""
    if not body:
        return []
    if isinstance(body, list):
        raw = "\n\n".join(clean_text(str(item)) for item in body if clean_text(str(item)))
    else:
        raw = BeautifulSoup(str(body), "html.parser").get_text("\n", strip=True)
    parts = [part for part in re.split(r"\n{2,}|\r\n{2,}", raw) if clean_text(part)]
    if len(parts) <= 1 and len(clean_text(raw)) > 700:
        sentence_text = clean_text(raw)
        # Python look-behind must be fixed-width. Mark sentence boundaries in two
        # ordinary substitutions instead, including punctuation followed by a quote.
        sentence_text = re.sub(r"([.!?])([\"'’”])\s+(?=[A-Z0-9\"'“‘])", r"\1\2\n", sentence_text)
        sentence_text = re.sub(r"([.!?])\s+(?=[A-Z0-9\"'“‘])", r"\1\n", sentence_text)
        sentences = [part.strip() for part in sentence_text.split("\n") if part.strip()]
        parts = []
        chunk: list[str] = []
        size = 0
        for sentence in sentences:
            chunk.append(sentence)
            size += len(sentence)
            if size >= 300:
                parts.append(" ".join(chunk))
                chunk, size = [], 0
        if chunk:
            parts.append(" ".join(chunk))
    return clean_article_blocks(parts, source_name, title, stats)


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
    elif method.startswith(("jsonld:", "embedded-json:")):
        # Publisher-supplied structured article bodies are first-party extraction
        # paths, not lower-confidence fallbacks. CTV in particular relies on them.
        score += 9
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



def image_focus_point(url: str) -> tuple[int, int]:
    """Return a lightweight visual-saliency focal point for card cropping.

    This deliberately avoids heavyweight computer-vision dependencies. It downsizes
    the image, finds high-contrast edge energy, applies a gentle centre bias, and
    returns the weighted centroid. It is not semantic face/object detection, but it
    usually keeps the visually important region inside a square crop.
    """
    if not url or not valid_article_image(url):
        return 50, 50
    try:
        response = SESSION.get(url, timeout=10, stream=True)
        response.raise_for_status()
        content_type = (response.headers.get("content-type") or "").lower()
        if "image" not in content_type:
            return 50, 50
        data = response.content
        if not data or len(data) > 5_000_000:
            return 50, 50
        image = Image.open(BytesIO(data)).convert("L")
        original_w, original_h = image.size
        if original_w < 80 or original_h < 80:
            return 50, 50
        image.thumbnail((96, 96))
        edge = image.filter(ImageFilter.FIND_EDGES)
        w, h = edge.size
        pixels = list(edge.getdata())
        total = 0.0
        x_sum = 0.0
        y_sum = 0.0
        for y in range(h):
            for x in range(w):
                energy = float(pixels[y * w + x])
                if energy < 22:
                    continue
                nx = (x + 0.5) / w
                ny = (y + 0.5) / h
                centre_bias = max(0.34, 1.0 - 0.78 * (((nx - 0.5) ** 2 + (ny - 0.46) ** 2) ** 0.5))
                weight = (energy ** 1.25) * centre_bias
                total += weight
                x_sum += nx * weight
                y_sum += ny * weight
        if total <= 0:
            return 50, 45 if original_h > original_w else 50
        x_pct = round(max(18, min(82, (x_sum / total) * 100)))
        y_pct = round(max(18, min(82, (y_sum / total) * 100)))
        if original_h > original_w * 1.18:
            y_pct = round((y_pct * 0.72) + (38 * 0.28))
        return x_pct, y_pct
    except Exception:
        return 50, 50


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

    if story.get("discovery_via"):
        current_home = story.get("source_home", "")
        if not current_home or "news.google.com" in urlparse(current_home).netloc:
            parsed_final = urlparse(final_url)
            if parsed_final.scheme and parsed_final.netloc:
                story["source_home"] = f"{parsed_final.scheme}://{parsed_final.netloc}/"

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
    inline_candidates: list[dict[str, Any]] = []
    for item in image_candidates:
        if same_image(item["url"], lead_image):
            continue
        if any(same_image(item["url"], prior["url"]) for prior in inline_candidates):
            continue
        inline_candidates.append(item)
        if len(inline_candidates) >= MAX_ARTICLE_IMAGES:
            break

    dom_blocks, stats, method = extract_dom_blocks(soup, final_url, source.name, title, lead_image)
    dom_paragraphs, dom_text = text_from_blocks(dom_blocks)
    ld_paragraphs = json_ld_body_paragraphs(ld, source.name, title, stats)
    ld_text = "\n\n".join(ld_paragraphs)

    extracted_text, extracted_paragraphs, extracted_meta = extracted_article_text(raw, final_url, source.name, title)
    ctv_blocks: list[dict[str, Any]] = []
    ctv_text = ""
    if source.name == "CTV News":
        ctv_blocks, ctv_stats = extract_ctv_embedded_blocks(soup, title)
        for key, value in ctv_stats.items():
            stats[key] = stats.get(key, 0) + value
        _, ctv_text = text_from_blocks(ctv_blocks)

    # CTV changes its rendering shape frequently. Treat DOM, JSON-LD, embedded
    # React state and readability extraction as parallel first-party candidates,
    # clean each one, then use the most complete plausible article body.
    if source.name == "CTV News":
        ctv_candidates: list[tuple[int, int, str, list[dict[str, Any]], list[str], str]] = []

        def add_ctv_candidate(candidate_method: str, candidate_blocks: list[dict[str, Any]], priority: int) -> None:
            candidate_paragraphs, candidate_text = text_from_blocks(candidate_blocks)
            candidate_paragraphs = clean_article_blocks(candidate_paragraphs, source.name, title)
            if len(candidate_paragraphs) < 2 or len(candidate_text) < 150:
                return
            # Rebuild the final CTV block list from the cleaned prose every time.
            # This prevents a footer/related module removed from paragraphs from
            # surviving separately inside content_blocks.
            candidate_blocks = fallback_blocks(candidate_paragraphs, inline_candidates)
            candidate_text = "\n\n".join(candidate_paragraphs)
            ctv_candidates.append((len(candidate_text), priority, candidate_method, candidate_blocks, candidate_paragraphs, candidate_text))

        if ctv_blocks:
            add_ctv_candidate("embedded-json:ctv", ctv_blocks, 4)
        if ld_paragraphs:
            add_ctv_candidate("jsonld:ctv", fallback_blocks(ld_paragraphs, inline_candidates), 3)
        if dom_blocks:
            add_ctv_candidate(method, dom_blocks, 2)
        cleaned_extracted = clean_article_blocks(extracted_paragraphs or initial_paragraphs, source.name, title)
        if cleaned_extracted:
            add_ctv_candidate("trafilatura:ctv", fallback_blocks(cleaned_extracted, inline_candidates), 1)

        if ctv_candidates:
            # Length is the strongest completeness signal; priority only breaks
            # near-ties in favour of publisher-structured data.
            ctv_candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
            _, _, method, blocks, paragraphs, text = ctv_candidates[0]
        else:
            blocks, paragraphs, text = [], [], ""
            method = "ctv:no-trusted-body"
    elif is_global_source(source.name):
        # Scoop treats Global as a strict source. Whole-page readability extraction can
        # accidentally ingest video rails, newsletter modules and hidden recirculation.
        # Prefer the visible article DOM, then publisher-supplied JSON-LD. If neither is
        # trustworthy, return a partial article instead of inventing a longer one.
        if len(dom_text) >= 160 and len(dom_paragraphs) >= 2:
            blocks = dom_blocks
            paragraphs, text = text_from_blocks(blocks)
            method = f"{method}:strict"
        elif len(ld_text) >= 160 and len(ld_paragraphs) >= 2:
            paragraphs = ld_paragraphs
            blocks = fallback_blocks(paragraphs, inline_candidates)
            text = ld_text
            method = "jsonld:global-strict"
        elif dom_paragraphs:
            blocks = dom_blocks
            paragraphs, text = text_from_blocks(blocks)
            method = f"{method}:partial-strict"
        elif ld_paragraphs:
            paragraphs = ld_paragraphs
            blocks = fallback_blocks(paragraphs, inline_candidates)
            text = ld_text
            method = "jsonld:global-partial"
        else:
            paragraphs, blocks, text = [], [], ""
            method = "global:no-trusted-body"
    elif len(dom_text) < MIN_ARTICLE_CHARS or len(dom_paragraphs) < 2:
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
    trusted_ctv_body = source.name == "CTV News" and method.startswith(("jsonld:ctv", "embedded-json:ctv"))
    full_enough = (score >= 55 and complete_shape) or (trusted_ctv_body and score >= 45 and word_count >= 90 and len(paragraphs) >= 2)
    story["content_status"] = "full" if full_enough else "partial" if word_count >= 55 else "summary"
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


def google_entry_source(entry: Any) -> tuple[str, str]:
    raw_source = entry.get("source") or {}
    if isinstance(raw_source, dict):
        name = raw_source.get("title") or raw_source.get("value") or ""
        home = raw_source.get("href") or raw_source.get("url") or ""
    else:
        name = getattr(raw_source, "title", "") or str(raw_source or "")
        home = getattr(raw_source, "href", "") or ""
    return canonical_source_name(name), clean_text(home, 500)


def rss_items(source: Source, existing: dict[str, dict[str, Any]], request_timeout: int | None = None) -> list[dict[str, Any]]:
    is_cbc = source.name == "CBC News London"
    session = FAST_SESSION if is_cbc else SESSION
    timeout = request_timeout if request_timeout is not None else (CBC_REQUEST_TIMEOUT if is_cbc else REQUEST_TIMEOUT)
    response = session.get(source.url, timeout=timeout)
    response.raise_for_status()
    feed = feedparser.parse(response.content)
    items: list[dict[str, Any]] = []
    google_discovery = source.kind == "google_topic"

    for entry in feed.entries[: source.max_items]:
        url = entry.get("link", "")
        effective_source = source
        display_source = source.name
        source_home = source.homepage
        source_accent = source.accent
        if google_discovery:
            discovered_name, discovered_home = google_entry_source(entry)
            if discovered_name and discovered_name != "Unknown source":
                display_source = discovered_name
            display_source = canonical_source_name(display_source)

            # Publishers that already have a first-party source must never be
            # reintroduced through Google News. This keeps CTV, CBC, Global,
            # Free Press, etc. strictly first-party.
            if display_source in DIRECT_SOURCE_NAMES:
                continue

            if discovered_home:
                source_home = discovered_home
            source_accent = accent_for_source(display_source)
            effective_source = Source(
                name=display_source,
                url=url,
                kind="page",
                homepage=source_home,
                accent=source_accent,
                max_items=1,
            )

        raw_entry_title = clean_text(entry.get("title"))
        if google_discovery and display_source:
            raw_entry_title = re.sub(rf"\s+-\s+{re.escape(display_source)}\s*$", "", raw_entry_title, flags=re.I)
        title = clean_story_title(raw_entry_title, display_source)
        if not url or not title:
            continue
        if google_discovery and clean_text(title).lower() in {"google news", "google"}:
            continue
        summary = clean_summary_text(entry.get("summary") or entry.get("description"), title)
        published = entry.get("published") or entry.get("updated") or entry.get("created")
        basic = {
            "id": make_id(url), "title": title, "source": display_source, "source_home": source_home,
            "source_accent": source_accent, "url": canonical_url(url), "published": parse_date(published),
            "summary": summary, "image": image_from_entry(entry), "author": clean_text(entry.get("author")),
            "category": classify(title, summary, display_source),
        }
        if google_discovery:
            basic["discovery_via"] = source.name
        old = existing.get(basic["id"]) or existing.get(basic["url"])
        if old and not stale(old):
            merged = {**basic, **old}
            merged.update({"source": display_source, "source_home": source_home, "source_accent": source_accent})
            items.append(merged)
        else:
            try:
                enriched = enrich_article({**(old or {}), **basic}, effective_source)
            except Exception as exc:
                # One malformed publisher page should degrade one story, not the
                # entire source refresh. Keep the feed metadata as a safe fallback.
                enriched = {**(old or {}), **basic}
                enriched["scrape_error"] = str(exc)[:240]
                enriched["scraped_at"] = datetime.now(timezone.utc).isoformat()
                enriched["content_status"] = "summary"
                enriched["extraction_schema"] = EXTRACTION_SCHEMA
                enriched["quality"] = extraction_quality(enriched, {}, "failed:story")
                print(f"Story skipped: {display_source} | {title[:70]} | {exc}", file=sys.stderr)
            # If a Google News redirect resolved, replace its temporary id with the
            # canonical article id so a direct-feed copy merges cleanly later.
            if google_discovery:
                if is_unusable_google_story(enriched):
                    continue
                if enriched.get("url") and "news.google.com" not in urlparse(enriched["url"]).netloc:
                    enriched["id"] = make_id(enriched["url"])
            items.append(enriched)
            time.sleep(0.14)
    return items



def cbc_items(source: Source, existing: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """Fetch CBC London without making one Akamai RSS endpoint a single point of failure."""
    attempts: list[str] = []
    feed_urls = [
        source.url,
        "https://rss.cbc.ca/lineup/canada-london.xml",
        "https://www.cbc.ca/cmlink/rss-canada-london",
    ]
    seen_urls: set[str] = set()

    for feed_url in feed_urls:
        if not feed_url or feed_url in seen_urls:
            continue
        seen_urls.add(feed_url)
        candidate = Source(
            name=source.name,
            logo=getattr(source, "logo", ""),
            url=feed_url,
            kind="rss",
            homepage=source.homepage,
            accent=source.accent,
            max_items=source.max_items,
        )
        try:
            items = rss_items(candidate, existing, request_timeout=CBC_FEED_TIMEOUT)
            if items:
                for item in items:
                    item["ingestion_path"] = "cbc-rss" if feed_url == source.url else "cbc-rss-fallback"
                if feed_url != source.url:
                    print(f"CBC News London: primary feed unavailable; using {feed_url}", file=sys.stderr)
                return items
            attempts.append(f"{feed_url}: empty feed")
        except Exception as exc:
            attempts.append(f"{feed_url}: {str(exc)[:110]}")

    # Final first-party fallback: discover only CBC London article links from the
    # regional landing page. This is intentionally narrow so national CBC stories
    # cannot leak into the local feed.
    page_source = Source(
        name=source.name,
        logo=getattr(source, "logo", ""),
        url=source.homepage or "https://www.cbc.ca/news/canada/london",
        kind="page",
        homepage=source.homepage or "https://www.cbc.ca/news/canada/london",
        accent=source.accent,
        max_items=source.max_items,
    )
    try:
        items = page_items(page_source, existing)
        if items:
            for item in items:
                item["ingestion_path"] = "cbc-regional-page"
            print("CBC News London: RSS unavailable; using regional page discovery", file=sys.stderr)
            return items
        attempts.append("regional page: no London article links")
    except Exception as exc:
        attempts.append(f"regional page: {str(exc)[:110]}")

    raise RuntimeError("CBC London unavailable through all first-party paths: " + " | ".join(attempts[-4:]))

def page_links(source: Source) -> list[str]:
    raw, final_url = fetch_html(source.url)
    soup = BeautifulSoup(raw, "html.parser")
    host = urlparse(final_url).netloc.lower().replace("www.", "")
    links: list[str] = []
    ctv_mode = source.name == "CTV News"
    cbc_mode = source.name == "CBC News London"
    city_mode = source.name == "City of London Newsroom"

    selectors = (
        ["a[href*='/news/posts/']"]
        if is_police_source(source.name)
        else ["a[href*='/london/article/']", "main a[href*='/london/article/']"]
        if ctv_mode
        else ["a[href*='/news/canada/london/']", "main a[href*='/news/canada/london/']"]
        if cbc_mode
        else ["a[href*='/newsroom/']", "main a[href*='/newsroom/']"]
        if city_mode
        else [
            "main h2 a[href]", "main h3 a[href]", "article h2 a[href]", "article h3 a[href]",
            ".news-item a[href]", ".card a[href]", "a[href*='/news/']",
        ]
    )

    def add_url(url: str, anchor_text: str = "") -> bool:
        url = canonical_url(url)
        if not url or canonical_url(url) == canonical_url(source.url):
            return False
        parsed = urlparse(url)
        if parsed.netloc.lower().replace("www.", "") != host:
            return False
        path = parsed.path.lower()
        if is_police_source(source.name) and "/news/posts/" not in path:
            return False
        if ctv_mode and "/london/article/" not in path:
            return False
        if cbc_mode and "/news/canada/london/" not in path:
            return False
        if city_mode and "/newsroom/" not in path:
            return False
        # CTV/CBC often wrap the image and headline in separate anchors. Their
        # image anchor may contain no text, but the URL is still authoritative.
        if not (ctv_mode or cbc_mode) and len(clean_text(anchor_text)) < 8:
            return False
        if url not in links:
            links.append(url)
        return len(links) >= source.max_items

    for selector in selectors:
        for anchor in soup.select(selector):
            href = anchor.get("href")
            if not href:
                continue
            if add_url(urljoin(final_url, href), anchor.get_text(" ", strip=True)):
                return links

    # React hydration payloads can contain article URLs that are not rendered as
    # ordinary anchors in the server HTML. Recover only first-party local paths.
    if ctv_mode or cbc_mode:
        normalized_raw = html.unescape(raw).replace("\\/", "/")
        pattern = (
            r'(?:https?://(?:www\.)?ctvnews\.ca)?(/london/article/[A-Za-z0-9][^"\'<>\\\s?#]*)'
            if ctv_mode
            else r'(?:https?://(?:www\.)?cbc\.ca)?(/news/canada/london/[A-Za-z0-9][^"\'<>\\\s?#]*)'
        )
        for match in re.finditer(pattern, normalized_raw, flags=re.I):
            if add_url(urljoin(final_url, match.group(1))):
                return links

    return links

def page_items(source: Source, existing: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for url in page_links(source):
        old = existing.get(make_id(url)) or existing.get(canonical_url(url))
        if old and not stale(old):
            story = {**old, "source": source.name, "source_home": source.homepage, "source_accent": source.accent}
        else:
            basic = {
                "id": make_id(url), "title": old.get("title", "") if old else "", "source": source.name,
                "source_home": source.homepage, "source_accent": source.accent, "url": canonical_url(url),
                "published": old.get("published", datetime.now(timezone.utc).isoformat()) if old else datetime.now(timezone.utc).isoformat(),
                "summary": old.get("summary", "") if old else "", "image": old.get("image", "") if old else "",
                "author": old.get("author", "") if old else "", "category": old.get("category", "Local") if old else "Local",
            }
            try:
                story = enrich_article(basic, source)
            except Exception as exc:
                story = {**(old or {}), **basic}
                story["scrape_error"] = str(exc)[:240]
                story["scraped_at"] = datetime.now(timezone.utc).isoformat()
                story["content_status"] = "summary"
                story["extraction_schema"] = EXTRACTION_SCHEMA
                story["quality"] = extraction_quality(story, {}, "failed:story")
                print(f"Story skipped: {source.name} | {url[:90]} | {exc}", file=sys.stderr)
            time.sleep(0.14)
        if story.get("title"):
            items.append(story)
    return items


def sanitize_content_blocks(blocks: list[dict[str, Any]], source_name: str, title: str, lead_image: str = "") -> list[dict[str, Any]]:
    cleaned: list[dict[str, Any]] = []
    seen: list[str] = []
    seen_images: list[str] = []
    skipping_postmedia_trending = False
    heartfm_mode = is_heartfm_source(source_name)
    heartfm_content_started = False
    ctv_mode = source_name == "CTV News"
    for block in blocks:
        if not isinstance(block, dict):
            continue
        kind = block.get("type")
        if kind in ("paragraph", "heading", "quote"):
            text = clean_text(strip_title_echo(normalize_source_case(block.get("text", "")), title))
            key = boilerplate_key(text)
            if is_global_source(source_name) and global_stop_text(text):
                break
            if heartfm_mode and heartfm_stop_text(text):
                if heartfm_content_started:
                    break
                continue
            if is_postmedia_source(source_name) and kind == "heading" and (key.startswith("trending") or key.startswith("most read") or key.startswith("most popular")):
                skipping_postmedia_trending = True
                continue
            if skipping_postmedia_trending:
                if kind == "paragraph" and len(text) >= 70 and re.search(r"[.!?][\"'’)]?$", text):
                    skipping_postmedia_trending = False
                else:
                    continue
            min_length = 4 if kind == "heading" else 18
            if len(text) < min_length or is_boilerplate_block(text, source_name) or any(near_duplicate(text, prior) for prior in seen[-12:]):
                continue
            if is_police_source(source_name) and police_stop_text(text):
                break
            seen.append(text)
            cleaned.append({**block, "text": text})
            if heartfm_mode and kind in ("paragraph", "quote"):
                heartfm_content_started = True
        elif kind == "list":
            items = [clean_text(normalize_source_case(item)) for item in block.get("items", [])]
            items = [item for item in items if len(item) >= 5 and not is_boilerplate_block(item, source_name)]
            if items:
                cleaned.append({"type": "list", "ordered": bool(block.get("ordered")), "items": items})
        elif kind == "image" and valid_article_image(block.get("url", "")):
            url = normalize_image_url(block.get("url", ""))
            if same_image(url, lead_image) or any(same_image(url, prior) for prior in seen_images):
                continue
            seen_images.append(url)
            cleaned.append({
                "type": "image", "url": url,
                "alt": clean_text(block.get("alt", ""), 180), "caption": clean_text(block.get("caption", ""), 320),
            })
    return cleaned


def sanitize_cached_story(story: dict[str, Any]) -> dict[str, Any]:
    source_name = story.get("source", "")
    title = clean_story_title(story.get("title", ""), source_name)
    story["title"] = title

    existing_blocks = story.get("content_blocks") if isinstance(story.get("content_blocks"), list) else []
    if existing_blocks:
        blocks = sanitize_content_blocks(existing_blocks, source_name, title, story.get("image", ""))
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


def remove_repeated_source_images(stories: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_source: dict[str, list[dict[str, Any]]] = {}
    for story in stories:
        if story.get("source") and story.get("image"):
            by_source.setdefault(story["source"], []).append(story)

    for source_name, source_stories in by_source.items():
        recent = source_stories[:30]
        counts: dict[str, int] = {}
        sample_url: dict[str, str] = {}
        for story in recent:
            key = image_path_key(story.get("image", "")) or image_dedupe_key(story.get("image", ""))
            if key:
                counts[key] = counts.get(key, 0) + 1
                sample_url[key] = story.get("image", "")
        if not counts:
            continue
        key, count = max(counts.items(), key=lambda item: item[1])
        # Repeated on many stories means this is almost certainly a publisher default image or logo.
        if count < 3 or count / max(1, len(recent)) < 0.34:
            continue
        repeated_url = sample_url[key]
        for story in source_stories:
            if same_image(story.get("image", ""), repeated_url):
                story["image"] = ""
                story["source_default_image_removed"] = True
                story["content_blocks"] = [
                    block for block in (story.get("content_blocks") or [])
                    if block.get("type") != "image" or not same_image(block.get("url", ""), repeated_url)
                ]
                story["article_images"] = [
                    image for image in (story.get("article_images") or [])
                    if not same_image(image.get("url", ""), repeated_url)
                ]
    return stories


def add_image_focus(stories: list[dict[str, Any]], limit: int = 24) -> list[dict[str, Any]]:
    """Calculate focal points lazily for recent card images.

    Only a small number are analyzed per run so the GitHub Action remains light.
    Existing focal points are reused until the lead image changes.
    """
    analyzed = 0
    for story in stories[:90]:
        if analyzed >= limit:
            break
        image = story.get("image", "")
        if not image:
            continue
        if (
            story.get("image_focus_for") == image
            and story.get("image_focus_x") is not None
            and story.get("image_focus_y") is not None
        ):
            continue
        x, y = image_focus_point(image)
        story["image_focus_x"] = x
        story["image_focus_y"] = y
        story["image_focus_for"] = image
        analyzed += 1
    return stories


def backfill_missing(
    stories: list[dict[str, Any]],
    skip_sources: set[str] | None = None,
) -> list[dict[str, Any]]:
    source_by_name = {source.name: source for source in SOURCES}
    skip_sources = skip_sources or set()
    done = 0
    # Repair CBC/CTV first after extractor changes so stale degraded records do
    # not keep their source health orange for many scheduled refreshes.
    priority_sources = {"CBC News London": 0, "CTV News": 0}
    # Python's sort is stable, so sorting only by priority preserves the existing
    # newest-first order within CBC/CTV and repairs the records that affect health
    # and the visible feed first.
    candidates = sorted(
        stories,
        key=lambda item: priority_sources.get(item.get("source", ""), 1),
    )
    for story in candidates:
        if done >= BACKFILL_PER_RUN:
            break
        needs_upgrade = story.get("extraction_schema") != EXTRACTION_SCHEMA
        needs_content = story.get("content_status") not in ("full", "partial") or not story.get("content")
        if not needs_upgrade and not needs_content:
            continue
        source_name = story.get("source", "")
        if source_name in skip_sources:
            continue
        source = source_by_name.get(source_name)
        if not source and story.get("url"):
            source = Source(
                name=source_name or "Unknown source",
                url=story.get("url", ""),
                kind="page",
                homepage=story.get("source_home", ""),
                accent=story.get("source_accent", accent_for_source(source_name or "Unknown source")),
                max_items=1,
            )
        if not source or not story.get("url"):
            continue
        print(f"Backfill: {story.get('source')} | {story.get('title', '')[:70]}")
        try:
            enrich_article(story, source)
        except Exception as exc:
            # A single malformed legacy article must never abort the whole refresh.
            story["scrape_error"] = str(exc)[:240]
            story["scraped_at"] = datetime.now(timezone.utc).isoformat()
            print(f"Backfill skipped: {story.get('source')} | {exc}", file=sys.stderr)
        done += 1
        time.sleep(0.18)
    return stories


def build_source_health(stories: list[dict[str, Any]], run_counts: dict[str, int], run_errors: dict[str, str]) -> list[dict[str, Any]]:
    health: list[dict[str, Any]] = []
    now = datetime.now(timezone.utc).isoformat()
    for source in SOURCES:
        recent = [
            story for story in stories
            if story.get("source") == source.name or story.get("discovery_via") == source.name
        ][:30]
        scores = [int((story.get("quality") or {}).get("score") or 0) for story in recent]
        grades = [str((story.get("quality") or {}).get("grade") or "poor") for story in recent]
        full = sum(1 for story in recent if story.get("content_status") == "full")
        partial = sum(1 for story in recent if story.get("content_status") == "partial")
        summary = sum(1 for story in recent if story.get("content_status") == "summary")
        failed = sum(1 for story in recent if story.get("content_status") == "failed" or story.get("scrape_error"))
        avg = round(sum(scores) / len(scores)) if scores else 0
        last_scrape = max((story.get("scraped_at", "") for story in recent), default="")
        error = run_errors.get(source.name, "")
        tracked = max(1, len(recent))
        usable_ratio = (full + partial) / tracked
        failure_ratio = failed / tracked
        # Source health measures extractor reliability, not how long a publisher's
        # stories happen to be. A source with clean short briefs should not be orange.
        status = (
            "error" if error and not recent
            else "degraded" if error
            else "healthy" if recent and usable_ratio >= 0.70 and failure_ratio <= 0.10
            else "degraded" if recent
            else "waiting"
        )
        health.append({
            "source": source.name,
            "accent": source.accent,
            "logo": getattr(source, "logo", ""),
            "profile": profile_for(source.name).get("profile", "generic"),
            "status": status,
            "checked_at": now,
            "found_this_run": run_counts.get(source.name, 0),
            "tracked": len(recent),
            "full": full,
            "partial": partial,
            "summary": summary,
            "failed": failed,
            "excellent": grades.count("excellent"),
            "good": grades.count("good"),
            "poor": grades.count("poor"),
            "average_quality": avg,
            "last_scrape": last_scrape,
            "last_error": error,
        })
    return health



def title_dedupe_key(story: dict[str, Any]) -> str:
    title = clean_text(story.get("title", "")).lower()
    title = re.sub(r"[^a-z0-9]+", " ", title)
    return re.sub(r"\s+", " ", title).strip()


def dedupe_stories(stories: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge direct-feed and Google-discovered copies of the same story."""
    best_by_url: dict[str, dict[str, Any]] = {}
    for story in stories:
        key = canonical_url(story.get("url", "")) or story.get("id", "")
        current = best_by_url.get(key)
        if not current:
            best_by_url[key] = story
            continue
        current_score = int((current.get("quality") or {}).get("score") or 0)
        new_score = int((story.get("quality") or {}).get("score") or 0)
        if new_score > current_score or (current.get("discovery_via") and not story.get("discovery_via")):
            best_by_url[key] = story

    ordered = sorted(best_by_url.values(), key=lambda item: item.get("published", ""), reverse=True)
    final: list[dict[str, Any]] = []
    seen_titles: dict[str, dict[str, Any]] = {}
    for story in ordered:
        key = title_dedupe_key(story)
        if len(key) < 20:
            final.append(story)
            continue
        previous = seen_titles.get(key)
        if previous:
            try:
                a = date_parser.parse(previous.get("published", ""))
                b = date_parser.parse(story.get("published", ""))
                if a.tzinfo is None: a = a.replace(tzinfo=timezone.utc)
                if b.tzinfo is None: b = b.replace(tzinfo=timezone.utc)
                if abs((a - b).total_seconds()) <= 7 * 86400:
                    continue
            except Exception:
                continue
        seen_titles[key] = story
        final.append(story)
    return final

def cache_card_images(stories: list[dict[str, Any]], limit: int = 140) -> list[dict[str, Any]]:
    """Cache lightweight square card thumbnails locally for fast, stable feeds."""
    CARD_IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    wanted: set[str] = set()
    done = 0
    for story in sorted(stories, key=lambda item: item.get("published", ""), reverse=True):
        if done >= limit:
            break
        image_url = clean_text(story.get("image"))
        if not image_url or not image_url.startswith(("http://", "https://")):
            continue
        filename = hashlib.sha1(image_url.encode("utf-8", "ignore")).hexdigest()[:20] + ".webp"
        target = CARD_IMAGE_DIR / filename
        relative = f"cache/news/{filename}"
        wanted.add(filename)
        if not target.exists():
            try:
                response = SESSION.get(image_url, timeout=12)
                response.raise_for_status()
                image = Image.open(BytesIO(response.content)).convert("RGB")
                width, height = image.size
                if min(width, height) < 160:
                    continue
                focus_x = float(story.get("image_focus_x") or 50) / 100.0
                focus_y = float(story.get("image_focus_y") or 50) / 100.0
                side = min(width, height)
                center_x = max(side / 2, min(width - side / 2, width * focus_x))
                center_y = max(side / 2, min(height - side / 2, height * focus_y))
                left = int(center_x - side / 2)
                top = int(center_y - side / 2)
                image = image.crop((left, top, left + side, top + side))
                image.thumbnail((720, 720), Image.Resampling.LANCZOS)
                image.save(target, "WEBP", quality=82, method=6)
            except Exception:
                continue
        story["card_image"] = relative
        done += 1

    # Avoid unbounded repository growth. Keep cached files still referenced by the latest set.
    for path in CARD_IMAGE_DIR.glob("*.webp"):
        if path.name not in wanted:
            try:
                path.unlink()
            except OSError:
                pass
    return stories


def source_metadata_map() -> dict[str, dict[str, str]]:
    return {
        canonical_source_name(source.name): {
            "logo": getattr(source, "logo", ""),
            "homepage": source.homepage,
            "accent": source.accent,
        }
        for source in SOURCES
    }


def story_topics(story: dict[str, Any]) -> list[str]:
    """Small deterministic enrichment layer for browsing/search, never invented prose."""
    topics: list[str] = []
    category = clean_text(story.get("category"))
    if category:
        topics.append(category)
    for reason in story.get("local_reasons") or []:
        label = re.sub(r"\s+[+-]\d+$", "", clean_text(reason))
        label = re.sub(r"^local publisher\s*", "", label, flags=re.I).strip()
        if label and label.lower() not in {"london mention", "publisher"} and label not in topics:
            topics.append(label)
    if int(story.get("cluster_source_count") or 1) > 1:
        topics.append("Multiple sources")
    if story.get("content_status") == "full" and int((story.get("quality") or {}).get("score") or 0) >= 75:
        topics.append("Full article")
    return topics[:5]


def annotate_presentation(stories: list[dict[str, Any]], source_health: list[dict[str, Any]]) -> list[dict[str, Any]]:
    configured = source_metadata_map()
    health_map = {canonical_source_name(item.get("source")): item for item in source_health}
    for story in stories:
        source_name = canonical_source_name(story.get("source"))
        metadata = configured.get(source_name, {})
        story["source_logo"] = metadata.get("logo", story.get("source_logo", ""))
        health = health_map.get(source_name)
        if health:
            status = health.get("status", "waiting")
        else:
            q = int((story.get("quality") or {}).get("score") or 0)
            status = "healthy" if q >= 65 and not story.get("scrape_error") else "degraded"
        story["source_health_status"] = status
        quality = int((story.get("quality") or {}).get("score") or 0)
        local = int(story.get("cluster_local_score") or story.get("local_score") or 0)
        story["hero_eligible"] = bool(
            status == "healthy"
            and story.get("content_status") in {"full", "partial"}
            and quality >= 55
            and local >= 25
            and story.get("image")
        )
        story["story_topics"] = story_topics(story)
    return stories


def main() -> int:
    previous = [story for story in load_existing() if not is_unusable_google_story(story)]
    lookup = existing_lookup(previous)
    fresh: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    run_errors: dict[str, str] = {}
    run_counts: dict[str, int] = {}

    for source in SOURCES:
        try:
            if source.name == "CBC News London":
                items = cbc_items(source, lookup)
            elif source.kind in ("rss", "google_topic"):
                items = rss_items(source, lookup)
            else:
                items = page_items(source, lookup)
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

    stories = dedupe_stories(list(merged.values()))
    stories = [story for story in stories if not is_unusable_google_story(story)]
    stories = [sanitize_cached_story(story) for story in stories]
    # Do not immediately hammer a source again during backfill if it already failed
    # during this run. Cached stories stay available until that publisher recovers.
    stories = backfill_missing(stories, skip_sources=set(run_errors))
    stories = remove_repeated_source_images(stories)
    stories = add_image_focus(stories)
    stories = cache_card_images(stories)

    # Editorial intelligence is deterministic and free: local relevance,
    # cross-publisher event clustering, and homepage ranking are calculated on
    # every refresh and stored directly in news.json for inspection.
    stories, editorial = apply_editorial_intelligence(stories)

    # Google News is discovery only. Once the full article is available, remove
    # discoveries that do not clear the London-locality threshold, then recalculate
    # clusters so filtered stories cannot inflate coverage counts.
    before_discovery_filter = len(stories)
    stories = [
        story for story in stories
        if not (story.get("discovery_via") and int(story.get("local_score") or 0) < GOOGLE_DISCOVERY_MIN_LOCAL_SCORE)
    ]
    discovery_filtered = before_discovery_filter - len(stories)

    # Keep the canonical history chronological. Homepage ranking is represented by
    # top_story_ids rather than reordering the archive itself. Re-run the editorial
    # pass after the history cap so cluster member IDs can never reference records
    # that are not present in the published JSON.
    stories.sort(key=lambda item: item.get("published", ""), reverse=True)
    stories = stories[:HISTORY_LIMIT]
    stories, editorial = apply_editorial_intelligence(stories)

    source_health = build_source_health(stories, run_counts, run_errors)
    stories = annotate_presentation(stories, source_health)

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
        "source_count": len({story.get("source") for story in stories if story.get("source")}),
        "editorial_schema_version": 1,
        "cluster_count": editorial.get("cluster_count", 0),
        "multi_source_cluster_count": editorial.get("multi_source_cluster_count", 0),
        "top_story_ids": editorial.get("top_story_ids", []),
        "editorial_clusters": editorial.get("clusters", []),
        "google_discoveries_filtered": discovery_filtered,
        "errors": errors,
        "source_health": source_health,
        "stories": stories,
    }
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    DATA_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {len(stories)} stories ({full_count} full, {partial_count} partial) to {DATA_FILE}")
    return 0 if stories else 1


if __name__ == "__main__":
    raise SystemExit(main())
