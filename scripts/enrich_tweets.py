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
from urllib.parse import parse_qs, urljoin, urlparse

import requests
from bs4 import BeautifulSoup, Tag

try:
    from fetch_news import fetch_html
except ImportError:
    fetch_html = None

ROOT = Path(__file__).resolve().parents[1]
NEWS_PATH = ROOT / "data" / "news.json"
TWEET_SCHEMA = 1
DEFAULT_LIMIT = max(12, int(os.getenv("TWEET_ENRICH_LIMIT", "60")))
WORKERS = max(2, min(8, int(os.getenv("TWEET_ENRICH_WORKERS", "6"))))
HEADERS = {"User-Agent": "ForestCityNews/1.0 (+https://myplexscripts.github.io/news/)"}
STATUS_RE = re.compile(r"https?://(?:www\.)?(?:twitter\.com|x\.com)/([A-Za-z0-9_]+)/status/(\d+)", re.I)
EMBED_RE = re.compile(r"platform\.twitter\.com/embed/Tweet\.html", re.I)


def clean(value: Any, limit: int | None = None) -> str:
    text = re.sub(r"\s+", " ", html.unescape(str(value or ""))).strip()
    return text[:limit].rstrip() if limit and len(text) > limit else text


def safe_url(value: Any, base: str = "") -> str:
    raw = html.unescape(str(value or "")).strip()
    if not raw or raw.startswith(("javascript:", "data:", "blob:")):
        return ""
    url = urljoin(base, raw)
    return url if urlparse(url).scheme in {"http", "https"} else ""


def identity(value: Any) -> tuple[str, str, str]:
    url = safe_url(value)
    match = STATUS_RE.search(url)
    if match:
        handle, tweet_id = match.group(1), match.group(2)
        return tweet_id, handle, f"https://x.com/{handle}/status/{tweet_id}"
    parsed = urlparse(url)
    if EMBED_RE.search(f"{parsed.netloc}{parsed.path}"):
        tweet_id = (parse_qs(parsed.query).get("id") or [""])[0]
        if tweet_id.isdigit():
            return tweet_id, "", f"https://x.com/i/web/status/{tweet_id}"
    return "", "", ""


def tweet_url(node: Tag, base: str = "") -> str:
    for attr in ("cite", "data-url", "data-href", "href", "src", "data-src"):
        candidate = safe_url(node.get(attr), base)
        if identity(candidate)[0]:
            return candidate
    for nested in node.find_all(["a", "iframe"]):
        candidate = safe_url(nested.get("href") or nested.get("src") or nested.get("data-src"), base)
        if identity(candidate)[0]:
            return candidate
    return ""


def base_block(url: str, node: Tag | None = None) -> dict[str, Any] | None:
    tweet_id, handle, canonical = identity(url)
    if not tweet_id:
        return None
    block: dict[str, Any] = {
        "type": "media",
        "media_type": "tweet",
        "provider": "x",
        "url": canonical,
        "source_url": canonical,
        "tweet_id": tweet_id,
        "handle": handle,
        "title": "Post on X",
    }
    if isinstance(node, Tag):
        paragraph = node.find("p")
        text = clean(paragraph.get_text(" ", strip=True), 10000) if isinstance(paragraph, Tag) else ""
        if text:
            block["text"] = text
    return block


def preceding_text(node: Tag) -> str:
    for prior in node.find_all_previous(["p", "h2", "h3", "h4"], limit=8):
        text = clean(prior.get_text(" ", strip=True), 260)
        if len(text) >= 12:
            return text
    return ""


def extract_from_html(raw: str, final_url: str) -> list[tuple[str, dict[str, Any]]]:
    soup = BeautifulSoup(raw, "html.parser")
    candidates = [*soup.find_all("blockquote"), *soup.find_all("iframe"), *soup.find_all("p")]
    output: list[tuple[str, dict[str, Any]]] = []
    seen: set[str] = set()
    for node in candidates:
        if not isinstance(node, Tag):
            continue
        block = base_block(tweet_url(node, final_url), node)
        if not block:
            continue
        tweet_id = str(block["tweet_id"])
        if tweet_id in seen:
            continue
        if node.name == "p" and len(clean(node.get_text(" ", strip=True))) > 320:
            continue
        seen.add(tweet_id)
        output.append((preceding_text(node), block))
    return output[:6]


def best_mp4(variants: list[dict[str, Any]]) -> str:
    found: list[tuple[int, str]] = []
    for item in variants or []:
        if not isinstance(item, dict):
            continue
        kind = str(item.get("content_type") or item.get("type") or "").lower()
        url = safe_url(item.get("url") or item.get("src"))
        if kind != "video/mp4" or not url:
            continue
        try:
            bitrate = int(item.get("bitrate") or 0)
        except (TypeError, ValueError):
            bitrate = 0
        found.append((bitrate, url))
    return max(found, default=(0, ""), key=lambda value: value[0])[1]


def apply_syndication(block: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    """Parse a syndication-shaped payload when one is already available.

    Forest City News does not call X's private syndication endpoint directly.
    This parser remains useful for fixtures and any publisher-provided payloads.
    """
    out = dict(block)
    text = clean(payload.get("text"), 10000)
    user = payload.get("user") if isinstance(payload.get("user"), dict) else {}
    handle = clean(user.get("screen_name"), 80).lstrip("@")
    if text:
        out["text"] = text
    if user.get("name"):
        out["author_name"] = clean(user["name"], 160)
    if handle:
        out["handle"] = handle
        out["url"] = out["source_url"] = f"https://x.com/{handle}/status/{out['tweet_id']}"
    avatar = safe_url(user.get("profile_image_url_https") or user.get("profile_image_url"))
    if avatar:
        out["avatar"] = avatar
    if payload.get("created_at"):
        out["published"] = clean(payload["created_at"], 120)

    photos: list[dict[str, Any]] = []
    poster = ""
    video_url = ""
    media = payload.get("mediaDetails") or payload.get("media_details") or []
    if isinstance(media, list):
        for item in media:
            if not isinstance(item, dict):
                continue
            kind = str(item.get("type") or "").lower()
            url = safe_url(item.get("media_url_https") or item.get("media_url") or item.get("url"))
            if kind == "photo" and url:
                photo: dict[str, Any] = {"url": url}
                info = item.get("original_info") if isinstance(item.get("original_info"), dict) else {}
                if info.get("width"):
                    photo["width"] = info["width"]
                if info.get("height"):
                    photo["height"] = info["height"]
                photos.append(photo)
            elif kind in {"video", "animated_gif"}:
                poster = poster or url
                info = item.get("video_info") if isinstance(item.get("video_info"), dict) else {}
                video_url = video_url or best_mp4(info.get("variants") or [])
    if photos:
        out["photos"] = photos[:4]
    if poster:
        out["poster"] = poster
    if video_url:
        out["video_url"] = video_url
    return out


def apply_oembed(block: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    out = dict(block)
    if payload.get("author_name") and not out.get("author_name"):
        out["author_name"] = clean(payload["author_name"], 160)
    author_url = safe_url(payload.get("author_url"))
    if author_url:
        handle = urlparse(author_url).path.strip("/").split("/")[0]
        if handle and handle not in {"i", "web"}:
            out["handle"] = handle
            out["url"] = out["source_url"] = f"https://x.com/{handle}/status/{out['tweet_id']}"
    if payload.get("html") and not out.get("text"):
        paragraph = BeautifulSoup(str(payload["html"]), "html.parser").find("p")
        if isinstance(paragraph, Tag):
            out["text"] = clean(paragraph.get_text(" ", strip=True), 10000)
    return out


def apply_fxtwitter(block: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    out = dict(block)
    tweet = payload.get("tweet") if isinstance(payload.get("tweet"), dict) else payload
    if not isinstance(tweet, dict):
        return out

    raw_text = tweet.get("raw_text") if isinstance(tweet.get("raw_text"), dict) else {}
    if not out.get("text") and (tweet.get("text") or raw_text.get("text")):
        out["text"] = clean(tweet.get("text") or raw_text.get("text"), 10000)

    author = tweet.get("author") if isinstance(tweet.get("author"), dict) else {}
    handle = clean(author.get("screen_name"), 80).lstrip("@")
    if author.get("name") and not out.get("author_name"):
        out["author_name"] = clean(author["name"], 160)
    if handle:
        out["handle"] = handle
        out["url"] = out["source_url"] = f"https://x.com/{handle}/status/{out['tweet_id']}"
    avatar = safe_url(author.get("avatar_url") or author.get("avatar"))
    if avatar and not out.get("avatar"):
        out["avatar"] = avatar

    photos = list(out.get("photos") or [])
    poster = safe_url(out.get("poster"))
    video_url = safe_url(out.get("video_url"))
    media = tweet.get("media_extended") or tweet.get("mediaExtended") or []
    if isinstance(media, list):
        for item in media:
            if not isinstance(item, dict):
                continue
            kind = str(item.get("type") or "").lower()
            url = safe_url(item.get("url") or item.get("media_url") or item.get("media_url_https"))
            thumb = safe_url(item.get("thumbnail_url") or item.get("thumbnail") or item.get("poster"))
            if kind in {"photo", "image"} and url:
                if not any(isinstance(photo, dict) and photo.get("url") == url for photo in photos):
                    photo: dict[str, Any] = {"url": url}
                    if item.get("width"):
                        photo["width"] = item["width"]
                    if item.get("height"):
                        photo["height"] = item["height"]
                    photos.append(photo)
            elif kind in {"video", "gif", "animated_gif"}:
                if url and (urlparse(url).path.lower().endswith(".mp4") or "video.twimg.com" in urlparse(url).netloc.lower()):
                    video_url = video_url or url
                poster = poster or thumb

    for value in tweet.get("mediaURLs") or tweet.get("media_urls") or []:
        url = safe_url(value)
        if not url:
            continue
        if urlparse(url).path.lower().endswith(".mp4") or "video.twimg.com" in urlparse(url).netloc.lower():
            video_url = video_url or url
        elif "pbs.twimg.com" in urlparse(url).netloc.lower() and not any(isinstance(photo, dict) and photo.get("url") == url for photo in photos):
            photos.append({"url": url})

    if photos:
        out["photos"] = photos[:4]
    if poster:
        out["poster"] = poster
    if video_url:
        out["video_url"] = video_url
    return out


def get_json(url: str, params: dict[str, str] | None = None) -> dict[str, Any]:
    try:
        response = requests.get(url, params=params or {}, headers=HEADERS, timeout=(4, 12))
        response.raise_for_status()
        payload = response.json()
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def enrich(block: dict[str, Any]) -> dict[str, Any]:
    tweet_id = str(block.get("tweet_id") or identity(block.get("source_url") or block.get("url"))[0])
    if not tweet_id:
        return block
    out = {**block, "tweet_id": tweet_id}

    # Official oEmbed supplies stable text/author metadata without requiring an API key.
    if not out.get("text") or not out.get("author_name"):
        oembed = get_json(
            "https://publish.twitter.com/oembed",
            {"url": str(out.get("source_url") or out.get("url")), "omit_script": "true", "dnt": "true"},
        )
        if oembed:
            out = apply_oembed(out, oembed)

    # X oEmbed does not expose direct photo/video assets. FxTwitter is a best-effort
    # server-side metadata fallback only. Forest City News never downloads the MP4.
    if not out.get("video_url") or not out.get("avatar"):
        handle = clean(out.get("handle"), 80).lstrip("@")
        path = f"{handle}/status/{tweet_id}" if handle else f"i/status/{tweet_id}"
        fallback = get_json(f"https://api.fxtwitter.com/{path}")
        if fallback:
            out = apply_fxtwitter(out, fallback)
    return out


def tweet_id_for(block: dict[str, Any]) -> str:
    if block.get("type") != "media":
        return ""
    explicit = str(block.get("tweet_id") or "")
    if explicit.isdigit():
        return explicit
    for field in ("source_url", "url"):
        tweet_id = identity(block.get(field))[0]
        if tweet_id:
            return tweet_id
    return ""


def is_x_block(block: dict[str, Any]) -> bool:
    return block.get("type") == "media" and (
        block.get("media_type") == "tweet"
        or str(block.get("provider") or "").lower() in {"x", "twitter"}
        or bool(tweet_id_for(block))
    )


def normalize(block: dict[str, Any]) -> dict[str, Any] | None:
    tweet_id = tweet_id_for(block)
    if not tweet_id:
        return None
    _, handle, canonical = identity(block.get("source_url") or block.get("url"))
    out: dict[str, Any] = {
        "type": "media",
        "media_type": "tweet",
        "provider": "x",
        "url": canonical or f"https://x.com/i/web/status/{tweet_id}",
        "source_url": canonical or f"https://x.com/i/web/status/{tweet_id}",
        "tweet_id": tweet_id,
        "handle": handle,
        "title": "Post on X",
    }
    for key in ("text", "author_name", "avatar", "published", "photos", "poster", "video_url"):
        if block.get(key):
            out[key] = block[key]
    title = clean(block.get("title"), 5000)
    if title and title.lower() not in {"embedded post", "embedded media", "post on x"}:
        out.setdefault("text", title)
    return out


def text_key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", clean(value).lower()).strip()


def match_anchor(blocks: list[dict[str, Any]], anchor: str) -> int | None:
    key = text_key(anchor)
    if not key:
        return None
    anchor_words = set(key.split())
    best: tuple[float, int | None] = (0.0, None)
    for index, block in enumerate(blocks):
        if block.get("type") not in {"paragraph", "heading", "quote"}:
            continue
        candidate = text_key(block.get("text"))
        if not candidate:
            continue
        if candidate == key or candidate in key or key in candidate:
            return index
        words = set(candidate.split())
        score = len(anchor_words & words) / max(1, min(len(anchor_words), len(words)))
        if score > best[0]:
            best = (score, index)
    return best[1] if best[0] >= 0.66 else None


def merge(
    blocks: list[dict[str, Any]],
    discovered: list[tuple[str, dict[str, Any]]],
) -> tuple[list[dict[str, Any]], int]:
    result = [dict(block) for block in blocks if isinstance(block, dict)]
    known_ids: set[str] = set()
    changed = 0

    for index, block in enumerate(result):
        if not is_x_block(block):
            continue
        normalized = normalize(block)
        if not normalized:
            continue
        result[index] = enrich(normalized)
        known_ids.add(str(normalized["tweet_id"]))
        changed += 1

    inserted_after_anchor: dict[str, int] = {}
    for anchor, block in discovered:
        tweet_id = str(block.get("tweet_id") or "")
        if not tweet_id or tweet_id in known_ids:
            continue
        target = match_anchor(result, anchor)
        if target is None:
            continue
        anchor_key = text_key(anchor)
        prior_count = inserted_after_anchor.get(anchor_key, 0)
        result.insert(target + 1 + prior_count, enrich(block))
        inserted_after_anchor[anchor_key] = prior_count + 1
        known_ids.add(tweet_id)
        changed += 1
    return result, changed


def process(story: dict[str, Any]) -> tuple[list[dict[str, Any]], int, str]:
    blocks = story.get("content_blocks") if isinstance(story.get("content_blocks"), list) else []
    discovered: list[tuple[str, dict[str, Any]]] = []
    method = "existing-x-embed" if any(is_x_block(block) for block in blocks if isinstance(block, dict)) else "none"
    if fetch_html is not None and story.get("url"):
        try:
            raw, final_url = fetch_html(str(story["url"]))
            discovered = extract_from_html(raw, final_url)
            if discovered:
                method = "dom+x-metadata"
        except Exception:
            pass
    merged, changed = merge(blocks, discovered)
    return merged, changed, method


def needs_work(story: dict[str, Any]) -> bool:
    if not (
        isinstance(story, dict)
        and story.get("url")
        and story.get("title")
        and story.get("content_status") in {"full", "partial"}
    ):
        return False
    blocks = story.get("content_blocks") if isinstance(story.get("content_blocks"), list) else []
    has_unstructured_x = any(
        is_x_block(block) and block.get("media_type") != "tweet"
        for block in blocks
        if isinstance(block, dict)
    )
    return has_unstructured_x or int(story.get("tweet_schema") or 0) < TWEET_SCHEMA


def timestamp(story: dict[str, Any]) -> float:
    try:
        return datetime.fromisoformat(str(story.get("published") or "").replace("Z", "+00:00")).timestamp()
    except Exception:
        return 0.0


def main() -> int:
    parser = argparse.ArgumentParser(description="Recover and enrich X/Twitter posts embedded in articles")
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    args = parser.parse_args()
    if not NEWS_PATH.exists():
        return 0

    payload = json.loads(NEWS_PATH.read_text(encoding="utf-8"))
    stories = payload.get("stories") if isinstance(payload.get("stories"), list) else []
    targets = sorted((story for story in stories if needs_work(story)), key=timestamp, reverse=True)[: max(1, args.limit)]
    if not targets:
        print("Tweet enrichment already current")
        return 0

    results: dict[str, tuple[list[dict[str, Any]], int, str]] = {}
    by_id = {str(story.get("id") or id(story)): story for story in targets}
    with ThreadPoolExecutor(max_workers=min(WORKERS, len(targets))) as pool:
        futures = {pool.submit(process, story): key for key, story in by_id.items()}
        for future in as_completed(futures):
            key = futures[future]
            try:
                results[key] = future.result()
            except Exception as exc:
                results[key] = ([], 0, f"error:{type(exc).__name__}")

    now = datetime.now(timezone.utc).isoformat()
    updated = tweets = videos = 0
    for key, story in by_id.items():
        blocks, changed, method = results.get(key, ([], 0, "none"))
        if blocks:
            story["content_blocks"] = blocks
        story.update({"tweet_schema": TWEET_SCHEMA, "tweet_enriched_at": now, "tweet_method": method})
        updated += int(bool(changed))
        tweet_blocks = [
            block
            for block in story.get("content_blocks", [])
            if isinstance(block, dict) and block.get("media_type") == "tweet"
        ]
        tweets += len(tweet_blocks)
        videos += sum(1 for block in tweet_blocks if block.get("video_url"))

    payload.update({"tweet_schema": TWEET_SCHEMA, "tweet_enriched_at": now})
    NEWS_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        f"Tweet enrichment: {updated}/{len(targets)} changed, "
        f"{tweets} tweet(s), {videos} remote video(s); no video files stored"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
