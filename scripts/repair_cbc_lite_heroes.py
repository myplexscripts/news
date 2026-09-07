from __future__ import annotations

"""Recover CBC story heroes from CBC's own article surfaces.

CBC discovery frequently enters Scoop through Google News. The feed image can be a
small reporter/avatar derivative even when the story has normal article photography.
CBC records already retain ``cbc_lite_url`` after body hydration, so use that URL as
the entry point, inspect CBC page metadata and article figures, follow the canonical
full CBC article when Lite points to one, and keep Jina reader extraction as a final
fallback.
"""

import argparse
import html
import json
import re
from typing import Any
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

import cache_cbc_images as cbc
import repair_card_image_refs as card_guard
import repair_cbc_images as cbc_repair

SCHEMA = 3
REQUEST_HEADERS = {
    "User-Agent": cbc.USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
}
CBC_NEWS_URL_RE = re.compile(
    r"https?://(?:www\.)?cbc\.ca/news/[^\s)\]>\"']+",
    re.I,
)
CBC_IMAGE_URL_RE = re.compile(
    r"https?://i\.cbc\.ca/[^\s)\]>\"']+",
    re.I,
)
AUTHOR_CONTAINER_RE = re.compile(
    r"author|byline|writer|reporter|contributor|profile|headshot|bio(?:graphy)?",
    re.I,
)


def clean(value: Any) -> str:
    return cbc.clean_text(value)


def is_cbc_reader_url(value: Any) -> bool:
    text = clean(value)
    if not text:
        return False
    try:
        parsed = urlparse(text)
    except Exception:
        return False
    host = parsed.netloc.lower().split(":", 1)[0]
    if parsed.scheme not in {"http", "https"}:
        return False
    if host not in {"cbc.ca", "www.cbc.ca"} and not host.endswith(".cbc.ca"):
        return False
    path = parsed.path.lower()
    return "/lite/story/" in path or "/news/" in path


def candidate_reader_urls(record: dict[str, Any]) -> list[str]:
    urls: list[str] = []
    for key in (
        "cbc_lite_url",
        "canonical_url",
        "resolved_url",
        "article_url",
        "original_url",
        "url",
    ):
        value = clean(record.get(key))
        if value and is_cbc_reader_url(value) and value not in urls:
            urls.append(value)
    return urls


def hero_needs_repair(record: dict[str, Any]) -> bool:
    hero = cbc.usable_hero(record)
    if not hero:
        return True
    if card_guard.is_tiny_remote_derivative(hero):
        return True
    if cbc_repair.current_hero_is_author(record):
        return True
    if cbc_repair.probable_small_square_profile(record):
        return True
    return False


def acceptable_candidate(
    record: dict[str, Any],
    candidate: Any,
    *,
    alt: str = "",
    caption: str = "",
) -> bool:
    value = clean(candidate)
    if not value:
        return False
    if card_guard.is_tiny_remote_derivative(value):
        return False
    if cbc_repair.looks_like_author_image(record, value, alt, caption):
        return False
    return cbc.is_remote_cbc_image(value) or not cbc.is_remote_url(value)


def json_image_values(value: Any) -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            if str(key).lower() in {"image", "imageurl", "thumbnailurl", "contenturl"}:
                if isinstance(child, str) and child.startswith(("http://", "https://")):
                    found.append(child)
                elif isinstance(child, dict):
                    for nested in ("url", "contentUrl", "thumbnailUrl"):
                        item = child.get(nested)
                        if isinstance(item, str) and item.startswith(("http://", "https://")):
                            found.append(item)
                elif isinstance(child, list):
                    for item in child:
                        if isinstance(item, str) and item.startswith(("http://", "https://")):
                            found.append(item)
                        elif isinstance(item, dict):
                            for nested in ("url", "contentUrl", "thumbnailUrl"):
                                nested_value = item.get(nested)
                                if isinstance(nested_value, str) and nested_value.startswith(("http://", "https://")):
                                    found.append(nested_value)
            found.extend(json_image_values(child))
    elif isinstance(value, list):
        for child in value:
            found.extend(json_image_values(child))
    return found


def srcset_urls(value: Any) -> list[str]:
    text = clean(value)
    if not text:
        return []
    urls: list[str] = []
    for part in text.split(","):
        candidate = clean(part.split()[0] if part.split() else "")
        if candidate:
            urls.append(candidate)
    return urls


def node_in_author_container(node: Any) -> bool:
    current = node
    depth = 0
    while current is not None and depth < 5:
        attrs = getattr(current, "attrs", {}) or {}
        values: list[str] = []
        for key in ("class", "id", "data-testid", "data-cy", "aria-label", "itemprop"):
            raw = attrs.get(key)
            if isinstance(raw, list):
                values.extend(str(item) for item in raw)
            elif raw:
                values.append(str(raw))
        if values and AUTHOR_CONTAINER_RE.search(" ".join(values)):
            return True
        current = getattr(current, "parent", None)
        depth += 1
    return False


def html_document_candidates(
    record: dict[str, Any],
    page_url: str,
    text: str,
) -> tuple[list[tuple[int, str]], list[str]]:
    """Return scored image candidates and CBC links discovered in an HTML page."""
    try:
        soup = BeautifulSoup(text, "html.parser")
    except Exception:
        return [], []

    images: list[tuple[int, str]] = []
    links: list[str] = []
    seen_images: set[str] = set()
    seen_links: set[str] = set()

    def add_image(raw: Any, score: int, alt: str = "", caption: str = "") -> None:
        candidate = clean(raw)
        if not candidate:
            return
        candidate = urljoin(page_url, html.unescape(candidate))
        if not acceptable_candidate(record, candidate, alt=alt, caption=caption):
            return
        key = cbc.normalize_local_image(candidate).split("?", 1)[0].lower()
        if not key or key in seen_images:
            return
        seen_images.add(key)
        images.append((score, candidate))

    def add_link(raw: Any) -> None:
        candidate = urljoin(page_url, clean(raw))
        if not is_cbc_reader_url(candidate):
            return
        key = candidate.split("#", 1)[0]
        if key not in seen_links:
            seen_links.add(key)
            links.append(key)

    for prop, bonus in (
        ("og:image", 180),
        ("og:image:secure_url", 175),
        ("twitter:image", 170),
        ("twitter:image:src", 165),
    ):
        for meta in soup.find_all("meta"):
            name = clean(meta.get("property") or meta.get("name")).lower()
            if name == prop:
                add_image(meta.get("content"), bonus)

    for meta in soup.find_all("meta"):
        name = clean(meta.get("property") or meta.get("name")).lower()
        if name in {"og:url", "twitter:url"}:
            add_link(meta.get("content"))

    for link in soup.find_all("link"):
        rel = " ".join(link.get("rel") or []).lower()
        if "canonical" in rel:
            add_link(link.get("href"))

    for script in soup.find_all("script", attrs={"type": re.compile("ld\\+json", re.I)}):
        raw = script.string or script.get_text(" ", strip=True)
        if not raw:
            continue
        try:
            payload = json.loads(raw)
        except Exception:
            continue
        for candidate in json_image_values(payload):
            add_image(candidate, 155)
        if isinstance(payload, dict):
            for key in ("url", "mainEntityOfPage"):
                value = payload.get(key)
                if isinstance(value, str):
                    add_link(value)
                elif isinstance(value, dict):
                    add_link(value.get("@id") or value.get("url"))

    article_roots = [
        *soup.select("article"),
        *soup.select("[itemprop='articleBody']"),
        *soup.select("[data-testid*='article' i]"),
        *soup.select("[class*='article-body' i]"),
        *soup.select("[class*='story-body' i]"),
    ]
    roots = article_roots or [soup]
    for root_index, root in enumerate(roots[:8]):
        for image_index, node in enumerate(root.find_all(["img", "source"], limit=80)):
            if node_in_author_container(node):
                continue
            alt = clean(node.get("alt"))
            caption = ""
            figure = node.find_parent("figure")
            if figure is not None:
                figcaption = figure.find("figcaption")
                if figcaption is not None:
                    caption = clean(figcaption.get_text(" ", strip=True))
            score = 140 - min(root_index * 5 + image_index, 70)
            for attr in ("src", "data-src", "data-original", "data-lazy-src", "data-image-src"):
                add_image(node.get(attr), score, alt, caption)
            for attr in ("srcset", "data-srcset"):
                entries = srcset_urls(node.get(attr))
                for offset, candidate in enumerate(reversed(entries)):
                    add_image(candidate, score + 8 - offset, alt, caption)

    for anchor in soup.find_all("a", href=True, limit=300):
        add_link(anchor.get("href"))

    images.sort(key=lambda item: item[0], reverse=True)
    return images, links


def text_document_candidates(
    record: dict[str, Any],
    page_url: str,
    text: str,
) -> tuple[list[tuple[int, str]], list[str]]:
    """Extract CBC images and full-article links from Jina/plain-text output."""
    images: list[tuple[int, str]] = []
    links: list[str] = []
    seen_images: set[str] = set()
    seen_links: set[str] = set()

    for index, (raw_alt, raw_url) in enumerate(cbc.MARKDOWN_IMAGE.findall(text)):
        candidate = html.unescape(clean(raw_url))
        alt = clean(raw_alt)
        if not acceptable_candidate(record, candidate, alt=alt):
            continue
        key = candidate.split("?", 1)[0].lower()
        if key in seen_images:
            continue
        seen_images.add(key)
        score = 130 + cbc_repair.title_overlap_score(record, alt) - min(index, 40)
        images.append((score, candidate))

    for index, raw_url in enumerate(CBC_IMAGE_URL_RE.findall(text)):
        candidate = html.unescape(clean(raw_url))
        if not acceptable_candidate(record, candidate):
            continue
        key = candidate.split("?", 1)[0].lower()
        if key in seen_images:
            continue
        seen_images.add(key)
        images.append((95 - min(index, 50), candidate))

    for raw_url in CBC_NEWS_URL_RE.findall(text):
        candidate = html.unescape(clean(raw_url)).rstrip(".,;:")
        if is_cbc_reader_url(candidate) and candidate not in seen_links:
            seen_links.add(candidate)
            links.append(candidate)

    images.sort(key=lambda item: item[0], reverse=True)
    return images, links


def fetch_documents(page_url: str) -> list[tuple[str, str, int]]:
    """Fetch CBC directly first, then Jina as a transport fallback."""
    documents: list[tuple[str, str, int]] = []
    try:
        response = requests.get(page_url, headers=REQUEST_HEADERS, timeout=(4, 15), allow_redirects=True)
        if response.status_code == 200 and len(response.content) >= 300:
            documents.append((response.url or page_url, response.text, response.status_code))
    except Exception:
        pass

    parsed = urlparse(page_url)
    if parsed.scheme in {"http", "https"}:
        target = f"{parsed.netloc}{parsed.path}"
        if parsed.query:
            target += f"?{parsed.query}"
        reader_url = f"https://r.jina.ai/http://{target}"
        try:
            response = requests.get(reader_url, headers=cbc.READER_HEADERS, timeout=(4, 22))
            if response.status_code == 200 and len(response.content) >= 300:
                documents.append((page_url, response.text, response.status_code))
        except Exception:
            pass
    return documents


def discover_from_cbc(record: dict[str, Any]) -> tuple[str, str]:
    queue = list(candidate_reader_urls(record))
    visited: set[str] = set()
    all_images: list[tuple[int, str, str]] = []

    while queue and len(visited) < 6:
        page_url = queue.pop(0)
        page_key = page_url.split("#", 1)[0]
        if page_key in visited:
            continue
        visited.add(page_key)

        for resolved_url, text, _status in fetch_documents(page_url):
            is_html = "<html" in text[:2000].lower() or "<meta" in text[:5000].lower()
            if is_html:
                images, links = html_document_candidates(record, resolved_url, text)
            else:
                images, links = text_document_candidates(record, page_url, text)
            for score, candidate in images:
                all_images.append((score, candidate, resolved_url))
            for link in links:
                if link not in visited and link not in queue:
                    queue.append(link)

        for index, candidate in enumerate(cbc_repair.reader_image_candidates(page_url, record)):
            if acceptable_candidate(record, candidate):
                all_images.append((90 - min(index, 30), clean(candidate), page_url))

    if not all_images:
        return "", ""

    best: dict[str, tuple[int, str, str]] = {}
    for score, candidate, source_url in all_images:
        parsed = urlparse(candidate)
        key = f"{parsed.netloc.lower()}{parsed.path.lower()}".rstrip("/")
        previous = best.get(key)
        if previous is None or score > previous[0]:
            best[key] = (score, candidate, source_url)
    selected = max(best.values(), key=lambda item: item[0])
    return selected[1], selected[2]


def clear_invalid_hero(record: dict[str, Any]) -> bool:
    if not hero_needs_repair(record):
        return False
    changed = False
    for key in ("image", "card_image", "card_image_small"):
        if clean(record.get(key)):
            record[key] = ""
            changed = True
    if changed:
        record["cbc_invalid_hero_cleared"] = True
    return changed


def repair_record(record: dict[str, Any]) -> bool:
    if not cbc_repair.is_cbc_record(record):
        return False
    if not hero_needs_repair(record):
        return False

    changed = clear_invalid_hero(record)
    discovered, source_url = discover_from_cbc(record)
    if not discovered:
        if changed:
            record["cbc_lite_hero_repair_schema"] = SCHEMA
            record["cbc_lite_hero_repair_status"] = "no-candidate"
        return changed

    cached = cbc.cache_image(discovered)
    selected = cached or discovered
    record["image"] = selected
    record["card_image"] = selected if cached else ""
    record["card_image_small"] = ""
    record["cbc_lite_hero_source"] = source_url
    record["cbc_lite_hero_repair_schema"] = SCHEMA
    record["cbc_lite_hero_repair_status"] = "recovered"
    record["cbc_invalid_hero_cleared"] = True
    if cached:
        record["cbc_images_cached"] = True
        record.pop("cbc_image_hotlink", None)
    else:
        record["cbc_image_hotlink"] = True
    return True


def repair_payload(payload: dict[str, Any], *, top_only: bool = False) -> int:
    stories = payload.get("stories")
    if not isinstance(stories, list):
        return 0
    top_ids = {
        clean(value)
        for value in payload.get("top_story_ids", [])
        if clean(value)
    } if top_only else set()
    corrected = 0
    for story in stories:
        if not isinstance(story, dict):
            continue
        if top_only and clean(story.get("id")) not in top_ids:
            continue
        if repair_record(story):
            corrected += 1
    payload["cbc_lite_hero_repair_schema"] = SCHEMA
    payload["cbc_lite_hero_repair_corrected"] = corrected
    return corrected


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--top-only",
        action="store_true",
        help="Only repair stories currently selected for the homepage top-story set.",
    )
    args = parser.parse_args()

    if not cbc.NEWS_PATH.exists():
        print("No data/news.json found")
        return 0
    payload = json.loads(cbc.NEWS_PATH.read_text(encoding="utf-8"))
    corrected = repair_payload(payload, top_only=args.top_only)
    if corrected:
        cbc.NEWS_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    scope = "top stories" if args.top_only else "all stories"
    print(f"CBC hero repair corrected {corrected} story/stories ({scope})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
