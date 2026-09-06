from __future__ import annotations

"""Final cross-publisher article contract.

Every extractor may be permissive, but published article bodies may contain only
editorial prose, headings, lists, quotes and legitimate article images. This
guard removes author portraits, ads, social/share UI, newsletters, preferred-
source promos and recirculation regardless of publisher.
"""

import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
NEWS_PATH = ROOT / "data" / "news.json"
PUBLIC_DIR = ROOT / "public"
CONTRACT_SCHEMA = 1

AUTHOR_STOPWORDS = {
    "by", "cbc", "ctv", "global", "news", "reporter", "journalist", "staff",
    "senior", "producer", "editor", "correspondent", "writer", "digital",
    "video", "photo", "photos",
}
AUTHOR_URL_MARKERS = (
    "/author/", "/authors/", "/staff/", "author-", "byline", "headshot",
    "avatar", "profile-photo", "profile_image", "profile-image", "staff-photo",
)
AUTHOR_TEXT_RE = re.compile(
    r"\b(?:author|byline|columnist|correspondent|headshot|journalist|"
    r"reporter|staff portrait|staff photo|profile photo|profile image)\b",
    re.I,
)

UTILITY_EXACT = {
    "advertisement", "advertising", "sponsored content", "promoted",
    "share", "share this story", "share this article", "share close",
    "newsletter", "newsletters", "sign up", "subscribe", "follow us",
    "recommended video", "previous video", "next video", "hide message bar",
    "stick to the facts",
}
UTILITY_PREFIXES = (
    "story continues below advertisement",
    "if you get global news from instagram or facebook",
    "find out how you can still connect with us",
    "leave a comment",
    "share this item on",
    "send this page to someone via email",
    "see more sharing options",
    "copy article link",
    "get daily ",
    "get breaking ",
    "get the latest ",
    "sign up for ",
    "subscribe to ",
    "download our app",
    "download the app",
    "get the app",
    "follow us on ",
    "add global news as a preferred source on google",
    "add global news as a preferred source",
    "add as a preferred source on google",
    "add citynews as a preferred source on google",
    "add ctv news as a preferred source on google",
    "by providing your email address",
    "read more:",
    "read more :",
)
UTILITY_CONTAINS = (
    "delivered to your inbox",
    "preferred source on google",
    "join the conversation in the comments",
    "share this item via whatsapp",
    "share this item on facebook",
    "send this page to someone via email",
    "see more sharing options",
    "this advertisement has not loaded yet",
)
TERMINAL_PREFIXES = (
    "keep reading",
    "more from ",
    "more stories",
    "related stories",
    "related coverage",
    "recommended for you",
    "you may also like",
    "most read",
    "most popular",
    "trending now",
    "top stories",
)
PROMO_METADATA_MARKERS = (
    "advert", "ad-slot", "adunit", "sponsor", "promo", "promotion",
    "newsletter", "subscribe", "signup", "sign-up", "related", "recommend",
    "recirc", "more-from", "read-more", "preferred-source", "outbrain", "taboola",
)
IMAGE_PROMO_URL_MARKERS = (
    "preferred-source", "preferred_source", "google-preferred", "newsletter",
    "signup", "subscribe",
)


def clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def key(value: Any) -> str:
    return clean(value).lower().replace("’", "'")


def words(value: Any) -> int:
    return len(re.findall(r"\b[\w’'-]+\b", clean(value)))


def item_text(value: Any) -> str:
    if isinstance(value, dict):
        return clean(value.get("text") or value.get("title") or value.get("label"))
    return clean(value)


def block_text(block: dict[str, Any]) -> str:
    if block.get("type") == "list":
        return " ".join(item_text(item) for item in block.get("items", []) if item_text(item))
    for field in ("text", "title", "label", "caption", "alt", "credit", "name"):
        value = clean(block.get(field))
        if value:
            return value
    return ""


def block_metadata(block: dict[str, Any]) -> str:
    return " ".join(
        clean(block.get(field))
        for field in ("role", "kind", "module", "module_type", "source_type", "class_name", "component")
        if clean(block.get(field))
    ).lower()


def source_name(story: dict[str, Any]) -> str:
    return key(story.get("source"))


def author_tokens(story: dict[str, Any]) -> list[str]:
    names: list[str] = []
    for field in ("author", "byline"):
        value = clean(story.get(field))
        if value:
            names.append(value)
    authors = story.get("authors")
    if isinstance(authors, list):
        for author in authors:
            value = clean(author.get("name") if isinstance(author, dict) else author)
            if value:
                names.append(value)

    output: list[str] = []
    for name in names:
        name = re.sub(r"^by\s+", "", name, flags=re.I)
        name = re.split(r"\s*[|·•]\s*|,\s*(?:cbc|ctv|global)\b", name, maxsplit=1, flags=re.I)[0]
        for token in re.findall(r"[a-z0-9]+", name.lower()):
            if len(token) >= 2 and token not in AUTHOR_STOPWORDS and token not in output:
                output.append(token)
    return output[:6]


def author_mentioned(story: dict[str, Any], value: Any) -> bool:
    tokens = author_tokens(story)
    if len(tokens) < 2:
        return False
    haystack = set(re.findall(r"[a-z0-9]+", key(value)))
    matches = sum(1 for token in tokens if token in haystack)
    return matches >= min(2, len(tokens))


def utility_reason(value: Any) -> str:
    normalized = key(value)
    if not normalized:
        return ""
    if normalized in UTILITY_EXACT:
        return "publisher-ui"
    if any(normalized.startswith(prefix) for prefix in UTILITY_PREFIXES):
        return "publisher-promo"
    if any(marker in normalized for marker in UTILITY_CONTAINS):
        return "publisher-promo"
    return ""


def terminal_reason(value: Any) -> str:
    normalized = key(value)
    if not normalized:
        return ""
    if any(normalized == prefix or normalized.startswith(prefix) for prefix in TERMINAL_PREFIXES):
        return "recirculation-tail"
    return ""


def metadata_is_promo(block: dict[str, Any]) -> bool:
    metadata = block_metadata(block)
    return bool(metadata) and any(marker in metadata for marker in PROMO_METADATA_MARKERS)


def is_substantive(block: dict[str, Any]) -> bool:
    if block.get("type") not in {"paragraph", "quote", "list"}:
        return False
    text = block_text(block)
    return words(text) >= 10 and len(text) >= 55 and not utility_reason(text)


def normalize_image_ref(value: Any) -> str:
    ref = clean(value)
    if ref.startswith("/news/"):
        return ref[len("/news/"):]
    if ref.startswith("/"):
        return ref[1:]
    return ref


def image_local_path(value: Any) -> Path | None:
    ref = normalize_image_ref(value)
    if not ref or ref.startswith(("http://", "https://")) or not ref.startswith("cache/"):
        return None
    path = PUBLIC_DIR / ref
    return path if path.exists() and path.is_file() else None


def image_dimensions(value: Any) -> tuple[int, int]:
    path = image_local_path(value)
    if path is None:
        return 0, 0
    try:
        with Image.open(path) as image:
            return int(image.width), int(image.height)
    except Exception:
        return 0, 0


def image_url(block: dict[str, Any]) -> str:
    return clean(block.get("url") or block.get("src"))


def image_descriptor(block: dict[str, Any]) -> str:
    return " ".join(
        clean(block.get(field))
        for field in ("alt", "caption", "title", "credit", "description")
        if clean(block.get(field))
    )


def image_is_explicit_promo(block: dict[str, Any]) -> bool:
    descriptor = key(image_descriptor(block))
    url = key(image_url(block))
    return (
        bool(utility_reason(descriptor))
        or any(marker in url for marker in IMAGE_PROMO_URL_MARKERS)
        or ("preferred source" in descriptor and "google" in descriptor)
    )


def image_is_author(
    story: dict[str, Any],
    block: dict[str, Any],
    index: int,
    first_prose_index: int | None,
    other_image_exists: bool,
) -> bool:
    url = key(image_url(block))
    descriptor = image_descriptor(block)
    descriptor_key = key(descriptor)

    if any(marker in url for marker in AUTHOR_URL_MARKERS):
        return True
    if AUTHOR_TEXT_RE.search(descriptor_key):
        return True
    if author_mentioned(story, url):
        return True
    if descriptor and len(descriptor) <= 160 and author_mentioned(story, descriptor):
        return True

    # CBC and Global frequently serialize a small square byline portrait before
    # the article prose. This guarded shape heuristic catches unlabelled versions
    # while leaving square editorial photos later in the story untouched.
    source = source_name(story)
    if "cbc" in source or "global news" in source:
        before_prose = first_prose_index is None or index < first_prose_index
        width, height = image_dimensions(image_url(block))
        if before_prose and width and height:
            ratio = width / max(1, height)
            short_descriptor = not descriptor or words(descriptor) <= 5
            if (
                0.72 <= ratio <= 1.38
                and max(width, height) <= 900
                and short_descriptor
                and (other_image_exists or len(author_tokens(story)) >= 2)
            ):
                return True
    return False


def same_ref(left: Any, right: Any) -> bool:
    a = normalize_image_ref(left)
    b = normalize_image_ref(right)
    if not a or not b:
        return False
    if a == b:
        return True
    try:
        pa = urlparse(a)
        pb = urlparse(b)
        if pa.scheme and pb.scheme:
            return pa.netloc.lower() == pb.netloc.lower() and pa.path == pb.path
    except Exception:
        pass
    return False


def paragraphs_from_blocks(blocks: list[dict[str, Any]]) -> list[str]:
    output: list[str] = []
    for block in blocks:
        if block.get("type") in {"paragraph", "quote"}:
            text = clean(block.get("text"))
            if text:
                output.append(text)
        elif block.get("type") == "list":
            output.extend(item_text(item) for item in block.get("items", []) if item_text(item))
    return output


def safe_image_refs(blocks: list[dict[str, Any]]) -> list[str]:
    output: list[str] = []
    for block in blocks:
        if block.get("type") == "image":
            ref = image_url(block)
            if ref and ref not in output:
                output.append(ref)
    return output


def hero_is_probable_author(story: dict[str, Any], rejected_refs: set[str]) -> bool:
    hero = clean(story.get("image") or story.get("card_image"))
    if not hero:
        return False
    if any(same_ref(hero, ref) for ref in rejected_refs):
        return True

    descriptor = clean(story.get("image_alt") or story.get("image_caption"))
    if AUTHOR_TEXT_RE.search(descriptor) or author_mentioned(story, descriptor):
        return True
    if any(marker in key(hero) for marker in AUTHOR_URL_MARKERS):
        return True

    source = source_name(story)
    width, height = image_dimensions(hero)
    if ("cbc" in source or "global news" in source) and width and height:
        ratio = width / max(1, height)
        if 0.72 <= ratio <= 1.38 and max(width, height) <= 900 and len(author_tokens(story)) >= 2:
            return True
    return False


def repair_hero(story: dict[str, Any], blocks: list[dict[str, Any]], rejected_refs: set[str]) -> bool:
    if not hero_is_probable_author(story, rejected_refs):
        return False

    candidates = safe_image_refs(blocks)
    replacement = candidates[0] if candidates else ""
    changed = False
    if replacement:
        if clean(story.get("image")) != replacement:
            story["image"] = replacement
            changed = True
        desired_card = "" if replacement.startswith(("http://", "https://")) else normalize_image_ref(replacement)
        if clean(story.get("card_image")) != desired_card:
            story["card_image"] = desired_card
            changed = True
    else:
        for field in ("image", "card_image", "card_image_small"):
            if clean(story.get(field)):
                story[field] = ""
                changed = True

    if clean(story.get("card_image_small")):
        story["card_image_small"] = ""
        changed = True
    if author_mentioned(story, story.get("image_alt")):
        story["image_alt"] = ""
        changed = True
    return changed


def enforce_story(story: dict[str, Any]) -> bool:
    raw_blocks = story.get("content_blocks")
    if not isinstance(raw_blocks, list) or not raw_blocks:
        return False

    blocks = [dict(block) for block in raw_blocks if isinstance(block, dict)]
    first_prose_index = next((i for i, block in enumerate(blocks) if is_substantive(block)), None)
    image_indexes = [i for i, block in enumerate(blocks) if block.get("type") == "image"]

    cleaned: list[dict[str, Any]] = []
    removed: list[str] = []
    rejected_refs: set[str] = set()
    prose_words = 0
    prose_blocks = 0

    for index, block in enumerate(blocks):
        kind = block.get("type")
        text = block_text(block)

        terminal = terminal_reason(text)
        if terminal and (prose_words >= 45 or prose_blocks >= 2):
            removed.append(terminal)
            break
        if terminal:
            removed.append(terminal)
            continue

        if metadata_is_promo(block):
            removed.append("promo-metadata")
            continue

        reason = utility_reason(text)
        if reason:
            removed.append(reason)
            continue

        if kind == "media":
            removed.append("embedded-media")
            continue

        if kind == "image":
            ref = image_url(block)
            if image_is_explicit_promo(block):
                if ref:
                    rejected_refs.add(ref)
                removed.append("promo-image")
                continue
            if image_is_author(
                story,
                block,
                index,
                first_prose_index,
                any(other != index for other in image_indexes),
            ):
                if ref:
                    rejected_refs.add(ref)
                removed.append("author-image")
                continue
            cleaned.append(block)
            continue

        if kind == "list":
            raw_items = block.get("items", []) or []
            items = []
            for item in raw_items:
                text_item = item_text(item)
                if not text_item:
                    continue
                if utility_reason(text_item) or terminal_reason(text_item):
                    removed.append("list-publisher-ui")
                    continue
                items.append(item)
            if not items and raw_items:
                continue
            if len(items) != len(raw_items):
                block = {**block, "items": items}

        cleaned.append(block)
        if kind in {"paragraph", "quote"}:
            count = words(text)
            if count:
                prose_words += count
                prose_blocks += 1
        elif kind == "list":
            prose_words += sum(words(item_text(item)) for item in block.get("items", []) or [])

    changed = cleaned != blocks
    if repair_hero(story, cleaned, rejected_refs):
        changed = True

    paragraphs = paragraphs_from_blocks(cleaned)
    if story.get("paragraphs") != paragraphs:
        story["paragraphs"] = paragraphs
        changed = True
    content = "\n\n".join(paragraphs)
    if clean(story.get("content")) != clean(content):
        story["content"] = content
        changed = True
    word_count = sum(words(paragraph) for paragraph in paragraphs)
    if int(story.get("word_count") or 0) != word_count:
        story["word_count"] = word_count
        changed = True
    if story.get("content_blocks") != cleaned:
        story["content_blocks"] = cleaned
        changed = True

    if int(story.get("article_contract_schema") or 0) != CONTRACT_SCHEMA:
        story["article_contract_schema"] = CONTRACT_SCHEMA
        changed = True
    reasons = sorted(set(removed))
    if reasons:
        if story.get("article_contract_removed") != reasons:
            story["article_contract_removed"] = reasons
            changed = True
    elif story.get("article_contract_removed"):
        story.pop("article_contract_removed", None)
        changed = True
    return changed


def enforce_payload(payload: dict[str, Any]) -> int:
    stories = payload.get("stories") if isinstance(payload.get("stories"), list) else []
    corrected = sum(1 for story in stories if isinstance(story, dict) and enforce_story(story))
    payload["article_contract_schema"] = CONTRACT_SCHEMA
    payload["article_contract_corrected"] = corrected
    return corrected


def main() -> int:
    if not NEWS_PATH.exists():
        print("No data/news.json found")
        return 0
    payload = json.loads(NEWS_PATH.read_text(encoding="utf-8"))
    corrected = enforce_payload(payload)
    NEWS_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Article contract enforced: {corrected} story/stories corrected")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
