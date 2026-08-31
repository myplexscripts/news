from __future__ import annotations

"""Reader-mode article extraction for every publisher.

Use established article extractors as the authority instead of growing a pile of
publisher-specific DOM heuristics:

* Trafilatura produces cleaned HTML with formatting, links and images preserved.
* readability-lxml independently applies the Readability reader-mode algorithm.

The script chooses the best complete candidate, keeps existing content when both
reader engines look truncated, and enforces strict CTV section attribution so a
landing-page link can never silently become a CTV London/Canada story.
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

from bs4 import BeautifulSoup, NavigableString, Tag
from readability import Document
from trafilatura import extract as trafilatura_extract

from fetch_news import fetch_html, same_image, valid_article_image

ROOT = Path(__file__).resolve().parents[1]
NEWS_PATH = ROOT / "data" / "news.json"
READER_SCHEMA = 2
MAX_FETCH = max(40, int(os.getenv("READER_MAX_FETCH", "180")))
WORKERS = max(2, min(12, int(os.getenv("READER_WORKERS", "10"))))
RETRY_HOURS = max(3, int(os.getenv("READER_RETRY_HOURS", "8")))
MIN_WORDS = 55

OBVIOUS_CHROME = re.compile(
    r"^(?:advertisement|advertising|sponsored content|promoted|related stories?|"
    r"recommended(?: for you)?|you may also like|read more|read next|more from(?: .+)?|"
    r"more stories|more news|trending(?: now)?|most read|most popular|top stories|"
    r"newsletter|newsletters|subscribe|sign up|follow related authors and topics|"
    r"interact with .+|report an? editorial error|report a technical issue|"
    r"editorial code of conduct|comments?)$",
    re.I,
)

TRACKER_IMAGE_TOKENS = (
    "doubleclick", "adservice", "tracking", "pixel", "spacer", "sprite", "favicon", "logo",
)

LOCATION_SELECTOR_PREFIX_RE = re.compile(r"^(?:state|country|province|region|territory)\b", re.I)
LOCATION_SELECTOR_MARKERS = (
    "alabama",
    "alaska",
    "arizona",
    "california",
    "florida",
    "new york",
    "north carolina",
    "texas",
    "washington",
    "wisconsin",
    "wyoming",
    "canada",
    "mexico",
    "afghanistan",
    "albania",
    "algeria",
)


def compact(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def text_key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", compact(value).lower()).strip()


def word_count(value: Any) -> int:
    return len(re.findall(r"\b\w+[’'-]?\w*\b", compact(value)))


def looks_like_location_selector_dump(value: Any) -> bool:
    key = compact(value).lower()
    if len(key) < 260 or word_count(key) < 40:
        return False
    if not LOCATION_SELECTOR_PREFIX_RE.search(key):
        return False
    marker_count = sum(1 for marker in LOCATION_SELECTOR_MARKERS if marker in key)
    return marker_count >= 6


def parse_datetime(value: Any) -> datetime | None:
    raw = compact(value).replace("Z", "+00:00")
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except Exception:
        return None


def source_is_ctv(source: Any) -> bool:
    return compact(source).lower() in {"ctv news", "ctv news canada"}


def ctv_section_for_url(url: Any) -> str:
    path = urlparse(compact(url)).path.lower()
    if "/london/article/" in path:
        return "london"
    if "/canada/article/" in path:
        return "canada"
    return ""


def normalize_ctv_attribution(story: dict[str, Any]) -> str:
    """Return keep/reassign/drop and make the source agree with the URL section."""
    if not source_is_ctv(story.get("source")):
        return "keep"
    section = ctv_section_for_url(story.get("url"))
    if not section:
        return "drop"
    if section == "london":
        changed = compact(story.get("source")) != "CTV News" or compact(story.get("scope")) != "local"
        story["source"] = "CTV News"
        story["source_home"] = "https://www.ctvnews.ca/london/"
        story["scope"] = "local"
        return "reassign" if changed else "keep"
    changed = compact(story.get("source")) != "CTV News Canada" or compact(story.get("scope")) != "canada"
    story["source"] = "CTV News Canada"
    story["source_home"] = "https://www.ctvnews.ca/canada/"
    story["scope"] = "canada"
    return "reassign" if changed else "keep"


def clean_editorial_metadata(payload: dict[str, Any], removed_ids: set[str]) -> None:
    if not removed_ids:
        return
    payload["top_story_ids"] = [
        story_id for story_id in payload.get("top_story_ids", [])
        if str(story_id) not in removed_ids
    ]
    clusters: list[dict[str, Any]] = []
    for raw in payload.get("editorial_clusters", []) or []:
        if not isinstance(raw, dict):
            continue
        member_ids = [
            str(story_id) for story_id in raw.get("member_ids", [])
            if str(story_id) not in removed_ids
        ]
        if not member_ids:
            continue
        cluster = dict(raw)
        cluster["member_ids"] = member_ids
        cluster["member_count"] = len(member_ids)
        if str(cluster.get("representative_id") or "") in removed_ids:
            cluster["representative_id"] = member_ids[0]
        clusters.append(cluster)
    payload["editorial_clusters"] = clusters
    payload["cluster_count"] = len(clusters)
    payload["multi_source_cluster_count"] = sum(
        1 for cluster in clusters if int(cluster.get("source_count") or 0) > 1
    )


def safe_url(value: Any, base_url: str) -> str:
    raw = compact(value)
    if not raw or raw.startswith(("javascript:", "data:", "blob:")):
        return ""
    resolved = urljoin(base_url, raw)
    parsed = urlparse(resolved)
    return resolved if parsed.scheme in {"http", "https"} and parsed.netloc else ""


def render_inline(node: Any, base_url: str) -> str:
    if isinstance(node, NavigableString):
        return html.escape(str(node), quote=False)
    if not isinstance(node, Tag):
        return ""
    name = str(node.name or "").lower()
    children = "".join(render_inline(child, base_url) for child in node.children)
    if name == "br":
        return "<br>"
    if name in {"strong", "b"}:
        return f"<strong>{children}</strong>"
    if name in {"em", "i"}:
        return f"<em>{children}</em>"
    if name in {"sup", "sub", "code"}:
        return f"<{name}>{children}</{name}>"
    if name == "a":
        href = safe_url(node.get("href"), base_url)
        if not href:
            return children
        return (
            f'<a href="{html.escape(href, quote=True)}" target="_blank" '
            f'rel="noopener noreferrer">{children}</a>'
        )
    return children


def inline_html(node: Tag, base_url: str) -> str:
    return "".join(render_inline(child, base_url) for child in node.children).strip()


def srcset_candidates(value: Any) -> list[tuple[int, str]]:
    candidates: list[tuple[int, str]] = []
    for part in str(value or "").split(","):
        bits = part.strip().split()
        if not bits:
            continue
        weight = 1
        if len(bits) > 1:
            raw = re.sub(r"[^0-9.]", "", bits[1])
            try:
                weight = int(float(raw) * (1000 if bits[1].endswith("x") else 1))
            except Exception:
                pass
        candidates.append((weight, bits[0]))
    return candidates


def best_img_url(img: Tag, base_url: str) -> str:
    candidates: list[tuple[int, str]] = []
    picture = img.find_parent("picture")
    if isinstance(picture, Tag):
        for source in picture.find_all("source"):
            if not isinstance(source, Tag):
                continue
            candidates.extend(srcset_candidates(source.get("srcset") or source.get("data-srcset")))
            for attr in ("data-src", "data-lazy-src", "data-original", "src"):
                value = source.get(attr)
                if value:
                    candidates.append((1, str(value)))
    for attr in ("data-src", "data-lazy-src", "data-original", "data-full-src", "data-zoom-src", "data-image", "data-image-src", "data-img-url", "src"):
        value = img.get(attr)
        if value:
            candidates.append((1, str(value)))
    candidates.extend(srcset_candidates(img.get("srcset") or img.get("data-srcset")))
    for _, candidate in sorted(candidates, reverse=True):
        url = safe_url(candidate, base_url)
        if url:
            return url
    return ""


def image_block(img: Tag, base_url: str, hero: str = "") -> dict[str, Any] | None:
    url = best_img_url(img, base_url)
    if not url or same_image(url, hero) or not valid_article_image(url, img):
        return None
    lower = url.lower()
    if any(token in lower for token in TRACKER_IMAGE_TOKENS):
        return None
    figure = img.find_parent("figure")
    caption = ""
    if isinstance(figure, Tag):
        cap = figure.find("figcaption")
        if isinstance(cap, Tag):
            caption = compact(cap.get_text(" ", strip=True))[:320]
    return {
        "type": "image",
        "url": url,
        "alt": compact(img.get("alt"))[:180],
        "caption": caption,
        **({"width": int(str(img.get("width") or "0"))} if str(img.get("width") or "").isdigit() else {}),
        **({"height": int(str(img.get("height") or "0"))} if str(img.get("height") or "").isdigit() else {}),
    }


def html_to_blocks(fragment: str, base_url: str, title: str = "", hero: str = "") -> list[dict[str, Any]]:
    soup = BeautifulSoup(fragment or "", "html.parser")
    for node in soup.find_all(["script", "style", "noscript", "form", "button", "iframe", "nav", "footer"]):
        node.decompose()

    root = soup.body or soup
    blocks: list[dict[str, Any]] = []
    seen_text: set[str] = set()
    seen_images: list[str] = []
    title_key = text_key(title)

    for node in root.find_all(["h1", "h2", "h3", "h4", "h5", "h6", "p", "blockquote", "ul", "ol", "figure", "img"]):
        if not isinstance(node, Tag):
            continue
        if node.name == "p" and node.find_parent(["blockquote", "li", "figcaption"]):
            continue
        if node.name in {"ul", "ol"} and node.find_parent(["ul", "ol"]):
            continue
        if node.name == "img" and node.find_parent("figure"):
            continue

        if node.name in {"h1", "h2", "h3", "h4", "h5", "h6", "p", "blockquote"}:
            text = compact(node.get_text(" ", strip=True))
            key = text_key(text)
            minimum = 3 if node.name.startswith("h") else 12
            if len(text) < minimum or not key or key in seen_text:
                continue
            if node.name.startswith("h") and title_key and key == title_key:
                continue
            seen_text.add(key)
            rendered = inline_html(node, base_url)
            block: dict[str, Any] = {"text": text}
            if rendered:
                block["html"] = rendered
            if node.name.startswith("h"):
                level = int(node.name[1])
                block.update({"type": "heading", "level": 2 if level <= 2 else 3})
            elif node.name == "blockquote":
                block["type"] = "quote"
            else:
                block["type"] = "paragraph"
            blocks.append(block)
            continue

        if node.name in {"ul", "ol"}:
            items: list[dict[str, str]] = []
            for li in node.find_all("li", recursive=False):
                text = compact(li.get_text(" ", strip=True))
                if not text:
                    continue
                rendered = inline_html(li, base_url)
                items.append({"text": text, "html": rendered or html.escape(text, quote=False)})
            if items:
                joined = text_key(" ".join(item["text"] for item in items))
                if joined and joined not in seen_text:
                    seen_text.add(joined)
                    blocks.append({"type": "list", "ordered": node.name == "ol", "items": items})
            continue

        img = node.find("img") if node.name == "figure" else node
        if not isinstance(img, Tag):
            continue
        block = image_block(img, base_url, hero)
        if not block:
            continue
        if any(same_image(block["url"], prior) for prior in seen_images):
            continue
        seen_images.append(block["url"])
        blocks.append(block)

    return blocks


def text_from_blocks(blocks: list[dict[str, Any]]) -> tuple[list[str], str]:
    paragraphs: list[str] = []
    for block in blocks:
        kind = block.get("type")
        if kind in {"paragraph", "quote"} and block.get("text"):
            paragraphs.append(compact(block.get("text")))
        elif kind == "list":
            for item in block.get("items", []) or []:
                text = compact(item.get("text") if isinstance(item, dict) else item)
                if text:
                    paragraphs.append(text)
    return paragraphs, "\n\n".join(paragraphs)


def blocks_word_count(blocks: list[dict[str, Any]]) -> int:
    paragraphs, _ = text_from_blocks(blocks)
    return sum(word_count(paragraph) for paragraph in paragraphs)


def obvious_chrome_count(blocks: list[dict[str, Any]]) -> int:
    count = 0
    for block in blocks:
        kind = block.get("type")
        if kind in {"paragraph", "heading", "quote"}:
            text = compact(block.get("text"))
            if OBVIOUS_CHROME.match(text) or looks_like_location_selector_dump(text):
                count += 1
        elif kind == "list":
            items = block.get("items", []) or []
            if len(items) >= 2:
                linked = 0
                headlineish = 0
                for item in items:
                    text = compact(item.get("text") if isinstance(item, dict) else item)
                    markup = compact(item.get("html") if isinstance(item, dict) else "")
                    if re.fullmatch(r"<a\b[^>]*>.*</a>", markup, flags=re.I | re.S):
                        linked += 1
                    if 4 <= word_count(text) <= 24 and not re.search(r"[.!?][\"'’”)]?$", text):
                        headlineish += 1
                if linked >= 2 and linked / len(items) >= 0.67 and headlineish / len(items) >= 0.67:
                    count += 1
    return count


def formatting_strength(blocks: list[dict[str, Any]]) -> tuple[int, int, int, int]:
    headings = sum(1 for block in blocks if block.get("type") == "heading")
    lists = sum(1 for block in blocks if block.get("type") == "list")
    images = sum(1 for block in blocks if block.get("type") == "image")
    rich_inline = sum(
        1 for block in blocks
        if block.get("type") in {"paragraph", "heading", "quote"}
        and re.search(r"<(?:a|strong|em|sup|sub|code)\b", compact(block.get("html")), re.I)
    )
    return headings, lists, images, rich_inline


def reader_candidate(raw: str, final_url: str, title: str, hero: str) -> tuple[list[dict[str, Any]], str]:
    try:
        doc = Document(raw, url=final_url, min_text_length=25, retry_length=150)
        summary = doc.summary(html_partial=True, keep_all_images=True)
    except Exception:
        return [], "readability:error"
    return html_to_blocks(summary, final_url, title, hero), "readability-lxml"


def trafilatura_candidate(raw: str, final_url: str, title: str, hero: str) -> tuple[list[dict[str, Any]], str]:
    try:
        cleaned = trafilatura_extract(
            raw,
            url=final_url,
            output_format="html",
            include_comments=False,
            include_tables=True,
            include_links=True,
            include_images=True,
            include_formatting=True,
            favor_precision=True,
            deduplicate=True,
        )
    except Exception:
        return [], "trafilatura:error"
    if not cleaned:
        return [], "trafilatura:empty"
    return html_to_blocks(cleaned, final_url, title, hero), "trafilatura-html"


def candidate_score(blocks: list[dict[str, Any]], method: str) -> tuple[float, dict[str, Any]]:
    words = blocks_word_count(blocks)
    paragraphs = sum(1 for block in blocks if block.get("type") in {"paragraph", "quote"})
    headings, lists, images, rich_inline = formatting_strength(blocks)
    chrome = obvious_chrome_count(blocks)
    score = (
        words
        + paragraphs * 18
        + headings * 26
        + lists * 30
        + images * 10
        + rich_inline * 8
        - chrome * 700
    )
    if method == "readability-lxml":
        score += 80
    elif method == "trafilatura-html":
        score += 65
    if words > 4500:
        score -= (words - 4500) * 0.4
    return score, {
        "words": words,
        "paragraphs": paragraphs,
        "headings": headings,
        "lists": lists,
        "images": images,
        "rich_inline": rich_inline,
        "chrome": chrome,
    }


def acceptable_candidate(story: dict[str, Any], blocks: list[dict[str, Any]], metrics: dict[str, Any]) -> bool:
    words = int(metrics.get("words") or 0)
    paragraphs = int(metrics.get("paragraphs") or 0)
    if words < MIN_WORDS or paragraphs < 1 or int(metrics.get("chrome") or 0) > 0:
        return False
    existing_words = int(story.get("word_count") or 0)
    contaminated = bool(story.get("article_hygiene_flags")) or existing_words > 4500
    if existing_words >= 120 and not contaminated and words < int(existing_words * 0.55):
        return False
    return True


def choose_reader_result(
    story: dict[str, Any],
    candidates: list[tuple[list[dict[str, Any]], str]],
) -> tuple[list[dict[str, Any]], str, dict[str, Any]]:
    accepted: list[tuple[float, list[dict[str, Any]], str, dict[str, Any]]] = []
    by_method: dict[str, tuple[list[dict[str, Any]], dict[str, Any]]] = {}
    for blocks, method in candidates:
        if not blocks:
            continue
        score, metrics = candidate_score(blocks, method)
        if not acceptable_candidate(story, blocks, metrics):
            continue
        accepted.append((score, blocks, method, metrics))
        by_method[method] = (blocks, metrics)
    if not accepted:
        return [], "", {}

    # Readability is the precision-first default. If Trafilatura found substantially
    # more clean article text, prefer it instead of accepting an obviously truncated
    # Reader result.
    readable = by_method.get("readability-lxml")
    traf = by_method.get("trafilatura-html")
    if readable and traf:
        r_blocks, r_metrics = readable
        t_blocks, t_metrics = traf
        r_words = int(r_metrics["words"])
        t_words = int(t_metrics["words"])
        if r_words >= int(t_words * 0.68):
            return r_blocks, "readability-lxml", r_metrics
        if t_words >= r_words and int(t_metrics.get("chrome") or 0) == 0:
            return t_blocks, "trafilatura-html", t_metrics

    accepted.sort(key=lambda row: row[0], reverse=True)
    _, blocks, method, metrics = accepted[0]
    return blocks, method, metrics


def remaining_hygiene_flags(blocks: list[dict[str, Any]]) -> list[str]:
    flags: list[str] = []
    chrome = obvious_chrome_count(blocks)
    if chrome:
        flags.append("reader-chrome")
    if blocks_word_count(blocks) > 4500:
        flags.append("reader-oversized")
    return flags


def article_format_state(blocks: list[dict[str, Any]]) -> str:
    words = blocks_word_count(blocks)
    paragraphs = sum(1 for block in blocks if block.get("type") in {"paragraph", "quote"})
    headings, lists, images, rich = formatting_strength(blocks)
    if words >= 70 and paragraphs >= 2 and headings + lists + images + rich == 0:
        return "flat"
    return "structured"


def should_fetch(story: dict[str, Any], now: datetime) -> bool:
    if not story.get("url") or not story.get("title"):
        return False
    attempted = parse_datetime(story.get("reader_attempted_at"))
    retry_due = not attempted or now - attempted >= timedelta(hours=RETRY_HOURS)
    if not retry_due:
        return False
    if int(story.get("reader_schema") or 0) < READER_SCHEMA:
        return True
    if compact(story.get("content_status")).lower() in {"partial", "summary", "failed", "unknown", ""}:
        return True
    if story.get("article_hygiene_flags") or compact(story.get("article_format_state")) == "flat":
        return True
    return False


def priority(story: dict[str, Any], now: datetime) -> tuple[int, int, int, float]:
    status = compact(story.get("content_status")).lower()
    weak = 2 if status in {"failed", "summary"} else 1 if status == "partial" else 0
    ctv = 1 if source_is_ctv(story.get("source")) else 0
    flagged = 1 if story.get("article_hygiene_flags") or compact(story.get("article_format_state")) == "flat" else 0
    published = parse_datetime(story.get("published"))
    age_hours = (now - published).total_seconds() / 3600 if published else 99999
    recent = 1 if age_hours <= 168 else 0
    return weak, ctv + flagged, recent, -age_hours


def process_story(story: dict[str, Any]) -> tuple[list[dict[str, Any]], str, dict[str, Any], str]:
    try:
        raw, final_url = fetch_html(compact(story.get("url")))
    except Exception as exc:
        return [], "", {}, f"fetch:{type(exc).__name__}"

    # Do not allow a redirect to silently move a CTV story into another section.
    if source_is_ctv(story.get("source")):
        expected = ctv_section_for_url(story.get("url"))
        actual = ctv_section_for_url(final_url)
        if expected and actual and expected != actual:
            return [], "", {}, "ctv:section-redirect"

    title = compact(story.get("title"))
    hero = compact(story.get("image"))
    candidates = [
        reader_candidate(raw, final_url, title, hero),
        trafilatura_candidate(raw, final_url, title, hero),
    ]
    blocks, method, metrics = choose_reader_result(story, candidates)
    return blocks, method, metrics, "" if blocks else "reader:no-complete-candidate"


def rebuild_story(story: dict[str, Any], blocks: list[dict[str, Any]], method: str, metrics: dict[str, Any]) -> None:
    paragraphs, text = text_from_blocks(blocks)
    story["content_blocks"] = blocks
    story["paragraphs"] = paragraphs
    story["content"] = text
    story["word_count"] = int(metrics.get("words") or blocks_word_count(blocks))
    story["reader_method"] = method
    story["reader_schema"] = READER_SCHEMA
    story["reader_extracted_at"] = datetime.now(timezone.utc).isoformat()
    flags = remaining_hygiene_flags(blocks)
    if flags:
        story["article_hygiene_flags"] = flags
    else:
        story.pop("article_hygiene_flags", None)
    story["article_format_state"] = article_format_state(blocks)

    words = int(story.get("word_count") or 0)
    paragraphs_count = sum(1 for block in blocks if block.get("type") in {"paragraph", "quote"})
    old_status = compact(story.get("content_status")).lower()
    if words >= 120 and paragraphs_count >= 2:
        story["content_status"] = "full"
        story.pop("scrape_error", None)
    elif words >= MIN_WORDS and old_status in {"summary", "failed", "unknown", ""}:
        story["content_status"] = "partial"
        story.pop("scrape_error", None)


def refresh_payload_counts(payload: dict[str, Any]) -> None:
    stories = [story for story in payload.get("stories", []) if isinstance(story, dict)]
    payload["story_count"] = len(stories)
    payload["full_story_count"] = sum(1 for story in stories if story.get("content_status") == "full")
    payload["partial_story_count"] = sum(1 for story in stories if story.get("content_status") == "partial")
    payload["source_count"] = len({story.get("source") for story in stories if story.get("source")})


def main() -> int:
    if not NEWS_PATH.exists():
        print("Reader-mode extraction: data/news.json not found", file=sys.stderr)
        return 1

    payload = json.loads(NEWS_PATH.read_text(encoding="utf-8"))
    stories = [story for story in payload.get("stories", []) if isinstance(story, dict)]

    # First fix CTV source attribution without making any network requests. The old
    # generic CTV Canada page crawler can discover links from unrelated CTV sections;
    # these must not survive as Canada or London stories.
    removed_ids: set[str] = set()
    ctv_reassigned = 0
    kept: list[dict[str, Any]] = []
    for story in stories:
        result = normalize_ctv_attribution(story)
        if result == "drop":
            if story.get("id"):
                removed_ids.add(str(story.get("id")))
            continue
        if result == "reassign":
            ctv_reassigned += 1
        kept.append(story)
    stories = kept
    payload["stories"] = stories
    clean_editorial_metadata(payload, removed_ids)

    now = datetime.now(timezone.utc)
    targets = [story for story in stories if should_fetch(story, now)]
    targets.sort(key=lambda story: priority(story, now), reverse=True)
    targets = targets[:MAX_FETCH]

    updated = 0
    failed = 0
    methods: dict[str, int] = {}
    by_identity = {str(story.get("id") or story.get("url") or index): story for index, story in enumerate(targets)}

    with ThreadPoolExecutor(max_workers=WORKERS) as executor:
        futures = {
            executor.submit(process_story, story): identity
            for identity, story in by_identity.items()
        }
        for future in as_completed(futures):
            story = by_identity[futures[future]]
            story["reader_attempted_at"] = now.isoformat()
            try:
                blocks, method, metrics, error = future.result()
            except Exception as exc:
                blocks, method, metrics, error = [], "", {}, f"reader:{type(exc).__name__}"
            if not blocks:
                story["reader_error"] = error or "reader:no-result"
                failed += 1
                continue
            rebuild_story(story, blocks, method, metrics)
            story.pop("reader_error", None)
            methods[method] = methods.get(method, 0) + 1
            updated += 1

    # Compatibility fields used by the existing admin audit. They now describe the
    # reader-mode output rather than the retired custom universal sweep.
    for story in stories:
        blocks = list(story.get("content_blocks") or [])
        if int(story.get("reader_schema") or 0) >= READER_SCHEMA:
            flags = remaining_hygiene_flags(blocks)
            if flags:
                story["article_hygiene_flags"] = flags
            else:
                story.pop("article_hygiene_flags", None)
            story["article_format_state"] = article_format_state(blocks)

    refresh_payload_counts(payload)
    payload["reader_schema"] = READER_SCHEMA
    payload["reader_extracted_at"] = datetime.now(timezone.utc).isoformat()
    payload["reader_stats"] = {
        "ctv_unrelated_removed": len(removed_ids),
        "ctv_reassigned": ctv_reassigned,
        "attempted": len(targets),
        "updated": updated,
        "failed_or_kept_existing": failed,
        "methods": methods,
        "pending": sum(1 for story in stories if int(story.get("reader_schema") or 0) < READER_SCHEMA),
        "hygiene_flagged": sum(1 for story in stories if story.get("article_hygiene_flags")),
        "flat_remaining": sum(1 for story in stories if story.get("article_format_state") == "flat"),
    }

    NEWS_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        "Reader-mode extraction: "
        f"{len(removed_ids)} unrelated CTV removed, {ctv_reassigned} CTV reassigned, "
        f"{len(targets)} attempted, {updated} updated, {failed} kept existing; methods={methods}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
