from __future__ import annotations

import argparse
import html
import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup, Tag

import fetch_news
import repair_ctv_photos as legacy


ROOT = Path(__file__).resolve().parents[1]
NEWS_PATH = ROOT / "data" / "news.json"
CTV_PHOTO_SCHEMA = 3
MAX_PHOTOS = 40
WORKERS = 6

ARTICLE_TYPES = {"article", "newsarticle", "reportagenewsarticle"}
IMAGE_TYPES = {"image", "photo", "picture", "imageobject"}
IMAGE_URL_KEYS = (
    "url", "image_url", "imageUrl", "src", "source_url", "sourceUrl",
    "original_url", "originalUrl", "contentUrl", "thumbnailUrl",
    "fullSizeResizeUrl", "resizeUrl", "proxyUrl",
)
BODY_KEYS = {
    "contentelements", "bodyelements", "articlecontent", "storybody", "blocks",
}
MEDIA_KEYS = {
    "contentelements", "images", "image", "photos", "slides", "items",
    "media", "gallery", "galleries", "promoitems", "leadart", "primaryimage",
    "multimedia",
}
STATE_CONTAINER_KEYS = {
    "props", "pageprops", "data", "story", "article", "globalcontent",
    "content", "initialstate", "state", "payload", "result",
}
AUTHOR_RE = re.compile(r"(author|byline|avatar|headshot|profile|contributor|writer)", re.I)
CHROME_RE = re.compile(
    r"(related|recommended|newsletter|most[-_ ]?read|trending|recirculation|sidebar|"
    r"social|share|navigation|\bnav\b|advert|\bad\b|promo|logo|icon|footer|header)",
    re.I,
)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def clean_key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def canonical_page_url(value: Any) -> str:
    raw = fetch_news.clean_text(value or "")
    if not raw:
        return ""
    try:
        return fetch_news.canonical_url(raw)
    except Exception:
        return raw.split("#", 1)[0].split("?", 1)[0].rstrip("/")


def same_page(a: str, b: str) -> bool:
    left = canonical_page_url(a)
    right = canonical_page_url(b)
    return bool(left and right and left == right)


def is_ctv_story(story: dict[str, Any]) -> bool:
    if "ctv" not in fetch_news.clean_text(story.get("source", "")).lower():
        return False
    host = urlparse(fetch_news.clean_text(story.get("url", ""))).netloc.lower()
    return host.endswith("ctvnews.ca") or host.endswith("ctv.ca")


def story_needs_work(story: dict[str, Any]) -> bool:
    if not is_ctv_story(story):
        return False
    if int(story.get("ctv_photo_schema") or 0) < CTV_PHOTO_SCHEMA:
        return True
    scraped = str(story.get("scraped_at") or "").strip()
    checked = str(story.get("ctv_photo_checked_for_scrape") or "").strip()
    return bool(scraped and scraped != checked)


def normalize_url(value: Any, base_url: str) -> str:
    raw = html.unescape(str(value or "").strip())
    if not raw or raw.startswith(("data:", "blob:", "javascript:")):
        return ""
    try:
        return fetch_news.normalize_image_url(raw, base_url)
    except Exception:
        return ""


def valid_url(url: str, tag: Tag | None = None) -> bool:
    if not url:
        return False
    try:
        return bool(fetch_news.valid_article_image(url, tag))
    except Exception:
        return False


def same_image(a: str, b: str) -> bool:
    if not a or not b:
        return False
    try:
        return bool(fetch_news.same_image(a, b))
    except Exception:
        return a.split("?", 1)[0] == b.split("?", 1)[0]


def int_value(value: Any) -> int | None:
    try:
        number = int(float(value))
        return number if number > 0 else None
    except (TypeError, ValueError):
        return None


def add_photo(found: list[dict[str, Any]], seen: list[str], block: dict[str, Any] | None) -> None:
    if not block or len(found) >= MAX_PHOTOS:
        return
    url = str(block.get("url") or "")
    if not url or any(same_image(url, previous) for previous in seen):
        return
    seen.append(url)
    found.append(block)


def image_url_from_node(node: dict[str, Any], base_url: str) -> str:
    props = node.get("additional_properties")
    if not isinstance(props, dict):
        props = node.get("additionalProperties")
    props = props if isinstance(props, dict) else {}

    values: list[Any] = []
    for key in IMAGE_URL_KEYS:
        values.extend((node.get(key), props.get(key)))

    image = node.get("image")
    if isinstance(image, str):
        values.append(image)
    elif isinstance(image, dict):
        for key in IMAGE_URL_KEYS:
            values.append(image.get(key))

    for resized in (
        node.get("resized_urls"), node.get("resizedUrls"),
        props.get("resized_urls"), props.get("resizedUrls"),
    ):
        if isinstance(resized, dict):
            values.extend(resized.values())

    for value in values:
        if isinstance(value, str):
            url = normalize_url(value, base_url)
            if valid_url(url):
                return url
    return ""


def node_to_photo(node: dict[str, Any], base_url: str, context: str = "") -> dict[str, Any] | None:
    metadata = " ".join(
        str(node.get(key) or "")
        for key in ("type", "@type", "role", "subtype", "alt", "alt_text", "caption")
    )
    if AUTHOR_RE.search(context) or AUTHOR_RE.search(metadata) or CHROME_RE.search(context):
        return None

    url = image_url_from_node(node, base_url)
    if not url:
        return None

    block: dict[str, Any] = {
        "type": "image",
        "url": url,
        "alt": fetch_news.clean_text(
            node.get("alt_text") or node.get("alt") or node.get("subtitle") or "", 180
        ),
        "caption": fetch_news.clean_text(
            node.get("caption") or node.get("description") or "", 320
        ),
    }
    width = int_value(node.get("width"))
    height = int_value(node.get("height"))
    if width:
        block["width"] = width
    if height:
        block["height"] = height
    return block


def looks_like_image(node: dict[str, Any], base_url: str) -> bool:
    kind = clean_key(node.get("type") or node.get("@type"))
    if kind in IMAGE_TYPES:
        return True
    return bool(image_url_from_node(node, base_url)) and any(
        node.get(key)
        for key in ("width", "height", "caption", "description", "alt", "alt_text")
    )


def walk_article_media(
    value: Any,
    base_url: str,
    found: list[dict[str, Any]],
    seen: list[str],
    context: str = "",
    depth: int = 0,
) -> None:
    if depth > 12 or len(found) >= MAX_PHOTOS:
        return
    if isinstance(value, list):
        for item in value:
            walk_article_media(item, base_url, found, seen, context, depth + 1)
        return
    if not isinstance(value, dict):
        return
    if AUTHOR_RE.search(context) or CHROME_RE.search(context):
        return

    if looks_like_image(value, base_url):
        add_photo(found, seen, node_to_photo(value, base_url, context))
        return

    for key, child in value.items():
        normalized = clean_key(key)
        key_text = str(key)
        if AUTHOR_RE.search(key_text) or CHROME_RE.search(key_text):
            continue
        if normalized in MEDIA_KEYS or normalized in BODY_KEYS:
            walk_article_media(child, base_url, found, seen, f"{context} {key_text}", depth + 1)


def node_page_url(node: dict[str, Any], base_url: str) -> str:
    for key in ("canonical_url", "canonicalUrl", "website_url", "websiteUrl", "url"):
        value = node.get(key)
        if isinstance(value, str) and value.strip():
            return urljoin(base_url, value.strip())
    main_entity = node.get("mainEntityOfPage")
    if isinstance(main_entity, str):
        return urljoin(base_url, main_entity)
    if isinstance(main_entity, dict):
        value = main_entity.get("@id") or main_entity.get("url")
        if isinstance(value, str):
            return urljoin(base_url, value)
    return ""


def node_matches_current_article(node: dict[str, Any], base_url: str, context: str) -> bool:
    candidate_url = node_page_url(node, base_url)
    if candidate_url:
        return same_page(candidate_url, base_url)
    return "globalcontent" in clean_key(context)


def is_article_node(node: dict[str, Any], base_url: str, context: str) -> bool:
    kind = clean_key(node.get("@type") or node.get("type"))
    if kind in ARTICLE_TYPES:
        candidate_url = node_page_url(node, base_url)
        return not candidate_url or same_page(candidate_url, base_url)

    has_body = any(isinstance(node.get(key), list) for key in (
        "content_elements", "contentElements", "body_elements", "bodyElements", "blocks"
    ))
    has_headline = bool(node.get("headline") or node.get("headlines") or node.get("title"))
    return has_body and has_headline and node_matches_current_article(node, base_url, context)


def iter_article_nodes(value: Any, base_url: str, context: str = "", depth: int = 0) -> Iterable[dict[str, Any]]:
    if depth > 14:
        return
    if isinstance(value, list):
        for item in value:
            yield from iter_article_nodes(item, base_url, context, depth + 1)
        return
    if not isinstance(value, dict):
        return

    if is_article_node(value, base_url, context):
        yield value
        return

    for key, child in value.items():
        normalized = clean_key(key)
        if normalized in STATE_CONTAINER_KEYS or (depth < 3 and isinstance(child, (dict, list))):
            yield from iter_article_nodes(child, base_url, f"{context} {key}", depth + 1)


def extract_article_node_photos(
    node: dict[str, Any],
    base_url: str,
    found: list[dict[str, Any]],
    seen: list[str],
) -> None:
    for key in ("image", "primaryImage", "leadArt", "promo_items", "promoItems"):
        if key in node:
            walk_article_media(node[key], base_url, found, seen, f"article {key}")
    for key in (
        "content_elements", "contentElements", "body_elements", "bodyElements",
        "articleContent", "storyBody", "blocks",
    ):
        if key in node:
            walk_article_media(node[key], base_url, found, seen, f"article {key}")


def parse_script_values(text: str) -> list[Any]:
    text = html.unescape(text or "")
    values: list[Any] = []
    stripped = text.strip()
    if not stripped:
        return values

    try:
        values.append(json.loads(stripped))
    except Exception:
        pass

    decoder = json.JSONDecoder()
    for marker in ("Fusion.globalContent=", "window.Fusion.globalContent="):
        cursor = 0
        while True:
            index = text.find(marker, cursor)
            if index < 0:
                break
            tail = text[index + len(marker):].lstrip()
            try:
                value, consumed = decoder.raw_decode(tail)
            except Exception:
                cursor = index + len(marker)
                continue
            if isinstance(value, dict):
                values.append({"globalContent": value})
            cursor = index + len(marker) + max(consumed, 1)

    if "__next_f.push" in text:
        pattern = r'self\.__next_f\.push\(\s*\[\s*\d+\s*,\s*("(?:\\.|[^"\\])*")\s*\]\s*\)'
        for match in re.finditer(pattern, text, flags=re.S):
            try:
                payload = json.loads(match.group(1))
            except Exception:
                continue
            values.extend(parse_script_values(payload))

    return values


def metadata_photo(soup: BeautifulSoup, base_url: str) -> dict[str, Any] | None:
    for selector in (
        'meta[property="og:image:secure_url"]',
        'meta[property="og:image:url"]',
        'meta[property="og:image"]',
        'meta[name="twitter:image:src"]',
        'meta[name="twitter:image"]',
        'meta[itemprop="image"]',
    ):
        tag = soup.select_one(selector)
        if not isinstance(tag, Tag):
            continue
        url = normalize_url(tag.get("content"), base_url)
        if not valid_url(url):
            continue
        block: dict[str, Any] = {"type": "image", "url": url, "alt": "", "caption": ""}
        width_tag = soup.select_one('meta[property="og:image:width"]')
        height_tag = soup.select_one('meta[property="og:image:height"]')
        alt_tag = soup.select_one('meta[property="og:image:alt"]')
        width = int_value(width_tag.get("content") if isinstance(width_tag, Tag) else None)
        height = int_value(height_tag.get("content") if isinstance(height_tag, Tag) else None)
        block["alt"] = fetch_news.clean_text(
            alt_tag.get("content") if isinstance(alt_tag, Tag) else "", 180
        )
        if width:
            block["width"] = width
        if height:
            block["height"] = height
        return block
    return None


def linked_to_other_story(img: Tag, base_url: str) -> bool:
    anchor = img.find_parent("a", href=True)
    if not isinstance(anchor, Tag):
        return False
    href = urljoin(base_url, str(anchor.get("href") or ""))
    path = urlparse(href).path.lower()
    if "/article/" not in path and "/photos/" not in path:
        return False
    return not same_page(href, base_url)


def dom_photos(
    soup: BeautifulSoup,
    base_url: str,
    found: list[dict[str, Any]],
    seen: list[str],
) -> None:
    roots: list[Tag] = []
    for selector in (
        '[class*="article-body"]', '[class*="article__body"]',
        '[class*="story-body"]', '[class*="story__body"]',
        '[data-testid*="article-body"]', "main article", "article",
    ):
        for node in soup.select(selector):
            if isinstance(node, Tag) and node not in roots:
                roots.append(node)
    if not roots:
        return

    for root in roots:
        for img in root.find_all("img"):
            if not isinstance(img, Tag) or linked_to_other_story(img, base_url):
                continue
            ancestor = img.find_parent(["figure", "aside", "header", "footer", "nav"])
            context = " ".join((
                str(img.get("class") or ""), str(img.get("id") or ""),
                str(img.get("alt") or ""),
                str(ancestor.get("class") if isinstance(ancestor, Tag) else ""),
                str(ancestor.get("id") if isinstance(ancestor, Tag) else ""),
            ))
            if AUTHOR_RE.search(context) or CHROME_RE.search(context):
                continue

            width = int_value(img.get("width"))
            height = int_value(img.get("height"))
            if width and width < 300:
                continue
            if height and height < 180:
                continue

            try:
                url = fetch_news.best_img_url(img, base_url)
            except Exception:
                url = normalize_url(img.get("src") or img.get("data-src"), base_url)
            if not valid_url(url, img):
                continue

            caption = ""
            figure = img.find_parent("figure")
            if isinstance(figure, Tag):
                figcaption = figure.find("figcaption")
                if isinstance(figcaption, Tag):
                    caption = fetch_news.clean_text(figcaption.get_text(" ", strip=True), 320)

            block: dict[str, Any] = {
                "type": "image", "url": url,
                "alt": fetch_news.clean_text(img.get("alt") or "", 180),
                "caption": caption,
            }
            if width:
                block["width"] = width
            if height:
                block["height"] = height
            add_photo(found, seen, block)


def extract_ctv_photos(raw: str, base_url: str) -> list[dict[str, Any]]:
    soup = BeautifulSoup(raw, "html.parser")
    found: list[dict[str, Any]] = []
    seen: list[str] = []

    add_photo(found, seen, metadata_photo(soup, base_url))

    for script in soup.find_all("script"):
        if not isinstance(script, Tag):
            continue
        text = script.string or script.get_text("", strip=False)
        if not text or len(text) < 20:
            continue
        for value in parse_script_values(text):
            for article_node in iter_article_nodes(value, base_url):
                extract_article_node_photos(article_node, base_url, found, seen)
                if len(found) >= MAX_PHOTOS:
                    return found

    dom_photos(soup, base_url, found, seen)
    return found


def reset_polluted_v2_media(story: dict[str, Any]) -> None:
    if int(story.get("ctv_photo_schema") or 0) != 2:
        return
    blocks = story.get("content_blocks")
    if isinstance(blocks, list):
        story["content_blocks"] = [
            block for block in blocks
            if not (isinstance(block, dict) and block.get("type") == "image")
        ]
    story["article_images"] = []
    story["ctv_photo_count"] = 0


def process_story(story: dict[str, Any]) -> tuple[list[dict[str, Any]], str, str]:
    url = fetch_news.clean_text(story.get("url", ""))
    if not url:
        return [], "", "missing-url"
    try:
        raw, final_url = fetch_news.fetch_html(url)
    except Exception as exc:
        return [], "", f"{type(exc).__name__}: {exc}"[:240]
    return extract_ctv_photos(raw, final_url), final_url, ""


def main() -> int:
    parser = argparse.ArgumentParser(description="Recover current CTV article images without page-chrome media.")
    parser.add_argument("--limit", type=int, default=160)
    args = parser.parse_args()

    if not NEWS_PATH.exists():
        print("No data/news.json found")
        return 1

    payload = json.loads(NEWS_PATH.read_text(encoding="utf-8"))
    stories = payload.get("stories") if isinstance(payload.get("stories"), list) else []
    targets = [story for story in stories if isinstance(story, dict) and story_needs_work(story)]
    targets.sort(key=lambda story: str(story.get("published") or ""), reverse=True)
    targets = targets[: max(0, args.limit)]

    if not targets:
        print("CTV image recovery already current")
        return 0

    results: dict[str, tuple[list[dict[str, Any]], str, str]] = {}
    with ThreadPoolExecutor(max_workers=min(WORKERS, max(1, len(targets)))) as pool:
        futures = {
            pool.submit(process_story, dict(story)): str(story.get("id") or story.get("url") or index)
            for index, story in enumerate(targets)
        }
        for future in as_completed(futures):
            key = futures[future]
            try:
                results[key] = future.result()
            except Exception as exc:
                results[key] = ([], "", f"{type(exc).__name__}: {exc}"[:240])

    changed = 0
    recovered = 0
    missing = 0
    max_story_photos = 0
    for index, story in enumerate(targets):
        key = str(story.get("id") or story.get("url") or index)
        photos, final_url, error = results.get(key, ([], "", "missing-result"))
        before = json.dumps(story, sort_keys=True, ensure_ascii=False)

        reset_polluted_v2_media(story)
        if photos:
            legacy.merge_photos(story, photos)
            recovered += len(photos)
            max_story_photos = max(max_story_photos, len(photos))
        else:
            missing += 1

        story["ctv_photo_schema"] = CTV_PHOTO_SCHEMA
        story["ctv_photo_checked_at"] = now_iso()
        story["ctv_photo_checked_for_scrape"] = str(story.get("scraped_at") or "")
        if final_url:
            story["ctv_photo_source_url"] = fetch_news.canonical_url(final_url)
        if error:
            story["ctv_photo_error"] = error
        elif not photos:
            story["ctv_photo_error"] = "no-ctv-images-recovered"
        else:
            story.pop("ctv_photo_error", None)

        if json.dumps(story, sort_keys=True, ensure_ascii=False) != before:
            changed += 1

    if changed:
        NEWS_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(
        f"CTV image recovery v3: checked={len(targets)}, changed={changed}, "
        f"images={recovered}, missing={missing}, max_per_story={max_story_photos}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
