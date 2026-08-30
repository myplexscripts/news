from __future__ import annotations

import json
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup, Tag

from fetch_news import canonical_url, fetch_html, same_image, valid_article_image

ROOT = Path(__file__).resolve().parents[1]
NEWS_PATH = ROOT / "data" / "news.json"
INLINE_MEDIA_SCHEMA = 1
INLINE_MEDIA_MAX_FETCH = max(20, int(os.getenv("INLINE_MEDIA_MAX_FETCH", "60")))
INLINE_MEDIA_WORKERS = max(2, min(12, int(os.getenv("INLINE_MEDIA_WORKERS", "10"))))

RECIRCULATION_RE = re.compile(
    r"^(?:read more|read next|keep reading|related(?: stories?| videos?| coverage)?|"
    r"recommended(?: for you)?|you may also like|also read|more from(?: .+)?|more stories|"
    r"more to read|more on this topic|more news|trending(?: now)?|most read|most popular|"
    r"top stories)(?:\b|$)",
    re.I,
)

UTILITY_RE = re.compile(
    r"^(?:advertisement|advertising|story continues below advertisement|sponsored(?: content)?|"
    r"promoted|newsletter|newsletters|sign up|subscribe|download (?:our |the )?app|get the app|"
    r"follow us|follow related authors and topics|interact with .+|report an? editorial error|"
    r"report a technical issue|editorial code of conduct|comments?)(?:\b|$)",
    re.I,
)

UTILITY_SENTENCE_RE = re.compile(
    r"(?:delivered to your inbox|never miss (?:the|a) day|join the conversation|"
    r"share this (?:story|article)|download our app|subscribe for|register /? sign in|"
    r"create an account or sign in|unlimited online access|support local journalism|"
    r"daily puzzles|email updates from your favourite authors|exclusive articles by)",
    re.I,
)

PAYWALL_RE = re.compile(
    r"^(?:this content is reserved for subscribers|subscriber(?:s| only)?|subscriber exclusive|"
    r"subscribe for more articles|register /? sign in to unlock more articles|"
    r"create an account or sign in to continue|this article is free to read register to unlock|"
    r"you(?:'|’)ve reached your article limit|sign in to continue reading|"
    r"subscribe to continue reading)(?:\b|$)",
    re.I,
)

PROMO_METADATA_MARKERS = (
    "recirc", "recirculation", "related", "recommend", "promotion", "promo", "newsletter",
    "advert", "sponsor", "more-from", "read-more", "outbrain", "taboola", "paywall",
    "subscription", "signup", "sign-up", "related-video", "related_story", "related-story",
)

DOM_PROMO_MARKERS = (
    "advert", "ad-slot", "adunit", "ad-unit", "sponsor", "promo", "promoted", "related",
    "recommend", "recirc", "newsletter", "subscribe", "subscription", "signup", "sign-up",
    "outbrain", "taboola", "paywall", "more-from", "read-more", "trending", "most-read",
    "related-video", "related_story", "related-story",
)

TITLE_TOKEN_STOPWORDS = {
    "about", "after", "amid", "from", "have", "into", "london", "more", "news", "over",
    "that", "their", "this", "with", "will", "your",
}


def item_text(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("text") or "").strip()
    return str(value or "").strip()


def block_text(block: dict[str, Any]) -> str:
    if block.get("type") == "list":
        return " ".join(item_text(item) for item in block.get("items", []) if item_text(item))
    return str(block.get("text") or block.get("caption") or block.get("alt") or "").strip()


def text_key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", item_text(value).lower()).strip()


def word_count(value: Any) -> int:
    return len(re.findall(r"\b\w+[’'-]?\w*\b", item_text(value)))


def sentence_like(value: Any) -> bool:
    text = item_text(value)
    return word_count(text) >= 8 and bool(re.search(r"[.!?][\"'’”)]?$", text))


def substantive_prose(block: dict[str, Any]) -> bool:
    if block.get("type") not in {"paragraph", "quote"}:
        return False
    text = item_text(block.get("text"))
    if word_count(text) < 10 or len(text) < 65:
        return False
    if is_utility_text(text) or is_recirculation_label(text) or is_paywall_text(text):
        return False
    return sentence_like(text) or word_count(text) >= 18


def headline_like(value: Any) -> bool:
    text = item_text(value)
    count = word_count(text)
    if count < 4 or count > 24 or len(text) < 18 or len(text) > 240:
        return False
    if sentence_like(text) and count >= 14:
        return False
    return True


def is_recirculation_label(value: Any) -> bool:
    return bool(RECIRCULATION_RE.search(item_text(value).strip()))


def is_utility_text(value: Any) -> bool:
    text = item_text(value).strip()
    return bool(text) and (bool(UTILITY_RE.search(text)) or bool(UTILITY_SENTENCE_RE.search(text)))


def is_paywall_text(value: Any) -> bool:
    return bool(PAYWALL_RE.search(item_text(value).strip()))


def metadata_marks_promo(block: dict[str, Any]) -> bool:
    values = " ".join(
        str(block.get(key) or "")
        for key in ("role", "kind", "module", "module_type", "source_type", "class_name", "component")
    ).lower()
    return bool(values) and any(marker in values for marker in PROMO_METADATA_MARKERS)


def title_tokens(key: str) -> set[str]:
    return {token for token in key.split() if len(token) >= 4 and token not in TITLE_TOKEN_STOPWORDS}


def build_title_index(stories: list[dict[str, Any]]) -> tuple[set[str], dict[str, set[str]]]:
    titles = {key for story in stories if (key := text_key(story.get("title")))}
    by_token: dict[str, set[str]] = {}
    for title in titles:
        for token in title_tokens(title):
            by_token.setdefault(token, set()).add(title)
    return titles, by_token


def title_match(item: Any, titles: set[str], title_index: dict[str, set[str]], current_title: str = "") -> bool:
    key = text_key(item)
    if len(key) < 18:
        return False
    if key in titles and key != current_title:
        return True
    candidates: set[str] = set()
    for token in title_tokens(key):
        candidates.update(title_index.get(token, ()))
    for title in candidates:
        if title == current_title or len(title) < 18:
            continue
        shorter, longer = (key, title) if len(key) <= len(title) else (title, key)
        if len(shorter) >= 24 and shorter in longer and len(shorter) / max(1, len(longer)) >= 0.72:
            return True
        if SequenceMatcher(None, key, title).ratio() >= 0.88:
            return True
    return False


def shared_headline_prefix(items: list[str]) -> bool:
    prefixes: list[str] = []
    for item in items:
        if ":" not in item:
            return False
        prefix = text_key(item.split(":", 1)[0])
        if len(prefix) < 4 or len(prefix.split()) > 5:
            return False
        prefixes.append(prefix)
    return len(prefixes) >= 2 and len(set(prefixes)) == 1


def html_is_single_link(block: dict[str, Any]) -> bool:
    markup = str(block.get("html") or "").strip()
    return bool(re.fullmatch(r"<a\b[^>]*>.*</a>", markup, flags=re.I | re.S))


def linked_headline_block(block: dict[str, Any]) -> bool:
    return (
        block.get("type") in {"heading", "paragraph"}
        and html_is_single_link(block)
        and headline_like(block.get("text"))
    )


def list_is_story_promo(
    block: dict[str, Any],
    titles: set[str],
    title_index: dict[str, set[str]],
    current_title: str,
    source: str = "",
) -> bool:
    if block.get("type") != "list":
        return False
    raw_items = block.get("items", []) or []
    items = [item_text(item) for item in raw_items if item_text(item)]
    if len(items) < 2:
        return False

    matches = sum(1 for item in items if title_match(item, titles, title_index, current_title))
    if matches >= 2 and matches / len(items) >= 0.6:
        return True

    linked = sum(
        1 for item in raw_items
        if isinstance(item, dict)
        and re.fullmatch(r"<a\b[^>]*>.*</a>", str(item.get("html") or "").strip(), flags=re.I | re.S)
    )
    headline_count = sum(1 for item in items if headline_like(item))
    if linked >= 2 and linked / len(items) >= 0.6 and headline_count / len(items) >= 0.6:
        return True

    if shared_headline_prefix(items) and all(headline_like(item) for item in items):
        return True

    source_lower = source.lower()
    if block.get("ordered") and any(name in source_lower for name in ("post", "free press", "ctv", "global", "star")):
        if all(headline_like(item) for item in items) and not any(sentence_like(item) for item in items):
            return True

    return False


def standalone_linked_story(
    block: dict[str, Any],
    titles: set[str],
    title_index: dict[str, set[str]],
    current_title: str,
    source: str,
) -> bool:
    if not linked_headline_block(block):
        return False
    if title_match(block.get("text"), titles, title_index, current_title):
        return True
    return any(name in source.lower() for name in ("globe", "national post", "toronto star", "global news", "ctv"))


def module_start(block: dict[str, Any]) -> bool:
    text = block_text(block)
    return metadata_marks_promo(block) or is_recirculation_label(text) or is_utility_text(text)


def terminal_marker(story: dict[str, Any], block: dict[str, Any]) -> bool:
    text = block_text(block)
    key = text_key(text)
    source = str(story.get("source") or "").lower()
    if is_paywall_text(text):
        return True
    if "globe and mail" in source and key in {
        "report an editorial error", "report a technical issue",
        "follow related authors and topics", "interact with the globe",
    }:
        return True
    if "national post" in source and (
        key.startswith("postmedia is committed to maintaining a lively but civil forum")
        or key.startswith("this content is reserved for subscribers")
    ):
        return True
    return False


def skip_linked_card_run(blocks: list[dict[str, Any]], start: int) -> int | None:
    if start >= len(blocks) or not linked_headline_block(blocks[start]):
        return None
    cursor = start
    headlines = 0
    images = 0
    consumed = 0
    while cursor < len(blocks) and consumed < 18:
        block = blocks[cursor]
        if linked_headline_block(block):
            headlines += 1
            cursor += 1
            consumed += 1
            continue
        if block.get("type") == "image" and headlines:
            images += 1
            cursor += 1
            consumed += 1
            continue
        if block.get("type") == "list" and headlines:
            items = [item_text(item) for item in block.get("items", []) if item_text(item)]
            if items and all(word_count(item) <= 10 for item in items):
                cursor += 1
                consumed += 1
                continue
        break
    return cursor if headlines >= 2 and (images >= 1 or headlines >= 3) else None


def strip_contextual_modules(
    story: dict[str, Any],
    blocks: list[dict[str, Any]],
    titles: set[str],
    title_index: dict[str, set[str]],
) -> tuple[list[dict[str, Any]], bool, str]:
    current_title = text_key(story.get("title"))
    source = str(story.get("source") or "")
    changed = False
    terminal_reason = ""

    prelim: list[dict[str, Any]] = []
    for block in blocks:
        if not isinstance(block, dict):
            changed = True
            continue
        if metadata_marks_promo(block):
            changed = True
            continue
        if block.get("type") == "list" and list_is_story_promo(block, titles, title_index, current_title, source):
            changed = True
            continue
        prelim.append(dict(block))

    out: list[dict[str, Any]] = []
    index = 0
    real_words = 0
    while index < len(prelim):
        block = prelim[index]

        if terminal_marker(story, block) and real_words >= 20:
            changed = True
            terminal_reason = "publisher-paywall" if is_paywall_text(block_text(block)) else "publisher-chrome"
            break

        card_end = skip_linked_card_run(prelim, index)
        if card_end is not None:
            changed = True
            index = card_end
            continue

        if standalone_linked_story(block, titles, title_index, current_title, source):
            changed = True
            index += 1
            if index < len(prelim) and prelim[index].get("type") == "image":
                index += 1
            continue

        if module_start(block):
            changed = True
            index += 1
            consumed = 0
            while index < len(prelim) and consumed < 16:
                candidate = prelim[index]
                if terminal_marker(story, candidate):
                    terminal_reason = "publisher-paywall" if is_paywall_text(block_text(candidate)) else "publisher-chrome"
                    index = len(prelim)
                    break
                if substantive_prose(candidate):
                    break
                if candidate.get("type") == "list" and not list_is_story_promo(
                    candidate, titles, title_index, current_title, source
                ):
                    item_texts = [item_text(item) for item in candidate.get("items", []) if item_text(item)]
                    if item_texts and any(sentence_like(item) for item in item_texts):
                        break
                index += 1
                consumed += 1
            continue

        text = block_text(block)
        if block.get("type") in {"paragraph", "heading", "quote"} and is_utility_text(text):
            changed = True
            index += 1
            continue

        out.append(block)
        if block.get("type") in {"paragraph", "quote"}:
            real_words += word_count(block.get("text"))
        elif block.get("type") == "list":
            real_words += sum(word_count(item_text(item)) for item in block.get("items", []))
        index += 1

    return out, changed, terminal_reason


def rebuild_story_text(story: dict[str, Any], blocks: list[dict[str, Any]], terminal_reason: str = "") -> None:
    paragraphs: list[str] = []
    for block in blocks:
        kind = block.get("type")
        if kind in {"paragraph", "quote"} and block.get("text"):
            paragraphs.append(str(block["text"]).strip())
        elif kind == "list":
            paragraphs.extend(item_text(item) for item in block.get("items", []) if item_text(item))
    story["content_blocks"] = blocks
    story["paragraphs"] = paragraphs
    story["content"] = "\n\n".join(paragraphs)
    story["word_count"] = sum(word_count(paragraph) for paragraph in paragraphs)
    story["recirculation_cleaned"] = True

    if terminal_reason:
        story["content_truncated_reason"] = terminal_reason
        if story["word_count"] >= 30:
            story["content_status"] = "partial"
        else:
            story["content_status"] = "summary"
    elif story.get("content_truncated_reason") in {"publisher-paywall", "publisher-chrome"}:
        story.pop("content_truncated_reason", None)


def prune_story(story: dict[str, Any], titles: set[str], title_index: dict[str, set[str]]) -> bool:
    blocks = story.get("content_blocks") if isinstance(story.get("content_blocks"), list) else []
    if not blocks:
        return False
    cleaned, changed, terminal_reason = strip_contextual_modules(story, blocks, titles, title_index)
    if not changed:
        return False
    rebuild_story_text(story, cleaned, terminal_reason)
    return True


def clean_payload(payload: dict[str, Any]) -> int:
    stories = payload.get("stories") if isinstance(payload.get("stories"), list) else []
    dict_stories = [story for story in stories if isinstance(story, dict)]
    titles, title_index = build_title_index(dict_stories)
    changed = sum(1 for story in dict_stories if prune_story(story, titles, title_index))
    payload["article_module_cleanup_at"] = datetime.now(timezone.utc).isoformat()
    payload["article_module_cleanup_corrected"] = changed
    return changed


def dom_signature(node: Tag) -> str:
    values: list[str] = []
    for key in ("id", "class", "role", "aria-label", "data-testid", "data-component", "data-module"):
        value = node.get(key)
        if isinstance(value, list):
            values.extend(str(item) for item in value)
        elif value:
            values.append(str(value))
    return re.sub(r"[^a-z0-9]+", "-", " ".join(values).lower())


def dom_is_promo(node: Tag, stop: Tag | None = None) -> bool:
    cursor: Tag | None = node
    depth = 0
    while isinstance(cursor, Tag) and cursor is not stop and depth < 8:
        signature = dom_signature(cursor)
        if signature and any(marker in signature for marker in DOM_PROMO_MARKERS):
            return True
        role = str(cursor.get("role") or "").lower()
        if role in {"navigation", "complementary"}:
            return True
        cursor = cursor.parent if isinstance(cursor.parent, Tag) else None
        depth += 1
    return False


def best_img_url(img: Tag, base_url: str) -> str:
    candidates: list[tuple[int, str]] = []
    for attr in ("data-src", "data-lazy-src", "data-original", "src"):
        value = img.get(attr)
        if value:
            candidates.append((1, str(value)))
    srcset = img.get("srcset") or img.get("data-srcset")
    if srcset:
        for part in str(srcset).split(","):
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
    for _, candidate in sorted(candidates, reverse=True):
        resolved = urljoin(base_url, candidate)
        parsed = urlparse(resolved)
        if parsed.scheme in {"http", "https"} and parsed.netloc:
            return resolved
    return ""


def paragraph_match_index(text: str, paragraph_keys: list[str]) -> int | None:
    key = text_key(text)
    if len(key) < 35:
        return None
    probe = key[:90]
    for index, candidate in enumerate(paragraph_keys):
        if len(candidate) < 35:
            continue
        if probe in candidate or candidate[:90] in key:
            return index
        shorter, longer = (key, candidate) if len(key) <= len(candidate) else (candidate, key)
        if len(shorter) >= 70 and shorter[:70] in longer:
            return index
    return None


def find_article_container(soup: BeautifulSoup, paragraphs: list[str]) -> tuple[Tag | None, dict[int, int]]:
    paragraph_keys = [text_key(text) for text in paragraphs]
    match_by_node: dict[int, int] = {}
    scores: dict[int, set[int]] = {}
    nodes: dict[int, Tag] = {}

    for p in soup.find_all("p"):
        text = p.get_text(" ", strip=True)
        match = paragraph_match_index(text, paragraph_keys)
        if match is None:
            continue
        match_by_node[id(p)] = match
        cursor: Tag | None = p
        depth = 0
        while isinstance(cursor, Tag) and cursor.name not in {"html", "body"} and depth < 8:
            if not dom_is_promo(cursor):
                ident = id(cursor)
                nodes[ident] = cursor
                scores.setdefault(ident, set()).add(match)
            cursor = cursor.parent if isinstance(cursor.parent, Tag) else None
            depth += 1

    if not scores:
        return None, match_by_node

    best: Tag | None = None
    best_rank: tuple[int, int, int] | None = None
    for ident, matched in scores.items():
        node = nodes[ident]
        tag_bonus = 2 if node.name == "article" else 1 if node.get("itemprop") == "articleBody" else 0
        text_size = len(node.get_text(" ", strip=True))
        rank = (len(matched), tag_bonus, -text_size)
        if best_rank is None or rank > best_rank:
            best = node
            best_rank = rank

    if best_rank and best_rank[0] < min(2, max(1, len(paragraphs))):
        return None, match_by_node
    return best, match_by_node


def linked_to_other_story(img: Tag, final_url: str, container: Tag) -> bool:
    link = img.find_parent("a", href=True)
    if not isinstance(link, Tag) or link is container:
        return False
    href = urljoin(final_url, str(link.get("href") or ""))
    if not href:
        return False
    parsed = urlparse(href)
    current = urlparse(final_url)
    if parsed.netloc.lower() != current.netloc.lower():
        return False
    path = parsed.path.lower()
    if re.search(r"\.(?:jpe?g|png|webp|avif)(?:$|\?)", path):
        return False
    return canonical_url(href) != canonical_url(final_url)


def figure_caption(img: Tag) -> str:
    figure = img.find_parent("figure")
    if not isinstance(figure, Tag):
        return ""
    cap = figure.find("figcaption")
    return str(cap.get_text(" ", strip=True)).strip()[:320] if isinstance(cap, Tag) else ""


def extract_contextual_images(
    raw: str,
    final_url: str,
    story: dict[str, Any],
    blocks: list[dict[str, Any]],
) -> list[tuple[int, dict[str, Any]]]:
    paragraphs: list[str] = [
        str(block.get("text") or "").strip()
        for block in blocks
        if block.get("type") in {"paragraph", "quote"} and word_count(block.get("text")) >= 6
    ]
    if not paragraphs:
        return []

    soup = BeautifulSoup(raw, "html.parser")
    container, _ = find_article_container(soup, paragraphs)
    if not isinstance(container, Tag):
        return []

    paragraph_keys = [text_key(text) for text in paragraphs]
    paragraph_block_indices: list[int] = [
        index for index, block in enumerate(blocks)
        if block.get("type") in {"paragraph", "quote"} and word_count(block.get("text")) >= 6
    ]
    hero = str(story.get("image") or "")
    existing_images = [
        str(block.get("url") or "") for block in blocks if block.get("type") == "image" and block.get("url")
    ]

    sequence: list[tuple[str, Tag, int | None]] = []
    for node in container.find_all(["p", "img"]):
        if not isinstance(node, Tag):
            continue
        if node.name == "p":
            match = paragraph_match_index(node.get_text(" ", strip=True), paragraph_keys)
            sequence.append(("p", node, match))
        else:
            if node.find_parent("figure") and node is not node.find_parent("figure").find("img"):
                continue
            sequence.append(("img", node, None))

    recovered: list[tuple[int, dict[str, Any]]] = []
    seen: list[str] = list(existing_images)

    for pos, (kind, node, _) in enumerate(sequence):
        if kind != "img":
            continue
        img = node
        if dom_is_promo(img, container):
            continue
        if linked_to_other_story(img, final_url, container):
            continue

        url = best_img_url(img, final_url)
        if not url or same_image(url, hero) or any(same_image(url, prior) for prior in seen):
            continue
        if not valid_article_image(url, img):
            continue

        alt = str(img.get("alt") or "").strip()[:180]
        caption = figure_caption(img)
        surrounding = " ".join(value for value in (alt, caption) if value)
        if is_utility_text(surrounding) or is_recirculation_label(surrounding) or is_paywall_text(surrounding):
            continue

        previous_match: int | None = None
        next_match: int | None = None
        for back in range(pos - 1, max(-1, pos - 9), -1):
            if sequence[back][0] == "p" and sequence[back][2] is not None:
                previous_match = sequence[back][2]
                break
        for forward in range(pos + 1, min(len(sequence), pos + 9)):
            if sequence[forward][0] == "p" and sequence[forward][2] is not None:
                next_match = sequence[forward][2]
                break
        if previous_match is None and next_match is None:
            continue

        anchor_para = previous_match if previous_match is not None else max(0, int(next_match or 0) - 1)
        if anchor_para >= len(paragraph_block_indices):
            continue
        anchor_block = paragraph_block_indices[anchor_para]

        seen.append(url)
        recovered.append((
            anchor_block,
            {
                "type": "image",
                "url": url,
                "alt": alt,
                "caption": caption,
                "recovered_from_source": True,
            },
        ))

    return recovered


def merge_contextual_images(blocks: list[dict[str, Any]], recovered: list[tuple[int, dict[str, Any]]]) -> tuple[list[dict[str, Any]], int]:
    if not recovered:
        return blocks, 0
    by_anchor: dict[int, list[dict[str, Any]]] = {}
    for anchor, block in recovered:
        by_anchor.setdefault(anchor, []).append(block)
    merged: list[dict[str, Any]] = []
    added = 0
    for index, block in enumerate(blocks):
        merged.append(block)
        for image in by_anchor.get(index, []):
            merged.append(image)
            added += 1
    return merged, added


def parse_published(value: Any) -> datetime | None:
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


def image_recovery_priority(story: dict[str, Any], now: datetime) -> tuple[int, float]:
    published = parse_published(story.get("published"))
    age_hours = (now - published).total_seconds() / 3600 if published else 99999
    recent = 1 if age_hours <= 168 else 0
    return recent, -age_hours


def needs_image_recovery(story: dict[str, Any]) -> bool:
    if not story.get("url") or not isinstance(story.get("content_blocks"), list):
        return False
    if sum(1 for block in story["content_blocks"] if block.get("type") in {"paragraph", "quote"}) < 1:
        return False
    stamp = str(story.get("reader_extracted_at") or story.get("scraped_at") or "")
    return (
        int(story.get("inline_media_schema") or 0) < INLINE_MEDIA_SCHEMA
        or str(story.get("inline_media_source_stamp") or "") != stamp
    )


def recover_story_images(story: dict[str, Any]) -> tuple[int, str]:
    try:
        raw, final_url = fetch_html(str(story.get("url") or ""))
    except Exception as exc:
        return 0, f"fetch:{type(exc).__name__}"

    blocks = list(story.get("content_blocks") or [])
    recovered = extract_contextual_images(raw, final_url, story, blocks)
    merged, added = merge_contextual_images(blocks, recovered)
    if added:
        story["content_blocks"] = merged
    stamp = str(story.get("reader_extracted_at") or story.get("scraped_at") or "")
    story["inline_media_schema"] = INLINE_MEDIA_SCHEMA
    story["inline_media_source_stamp"] = stamp
    story["inline_media_attempted_at"] = datetime.now(timezone.utc).isoformat()
    story["inline_media_recovered"] = added
    story.pop("inline_media_error", None)
    return added, ""


def recover_inline_media(payload: dict[str, Any]) -> tuple[int, int, int]:
    stories = [story for story in payload.get("stories", []) if isinstance(story, dict)]
    now = datetime.now(timezone.utc)
    targets = [story for story in stories if needs_image_recovery(story)]
    targets.sort(key=lambda story: image_recovery_priority(story, now), reverse=True)
    targets = targets[:INLINE_MEDIA_MAX_FETCH]

    added = 0
    failed = 0
    with ThreadPoolExecutor(max_workers=INLINE_MEDIA_WORKERS) as executor:
        futures = {executor.submit(recover_story_images, story): story for story in targets}
        for future in as_completed(futures):
            story = futures[future]
            try:
                count, error = future.result()
            except Exception as exc:
                count, error = 0, f"error:{type(exc).__name__}"
            added += count
            if error:
                failed += 1
                story["inline_media_error"] = error

    payload["inline_media_schema"] = INLINE_MEDIA_SCHEMA
    payload["inline_media_recovery_at"] = datetime.now(timezone.utc).isoformat()
    payload["inline_media_recovery_stats"] = {
        "attempted": len(targets),
        "images_added": added,
        "failed": failed,
        "pending": sum(1 for story in stories if needs_image_recovery(story)),
    }
    return len(targets), added, failed


def main() -> int:
    if not NEWS_PATH.exists():
        print("No data/news.json found")
        return 0

    payload = json.loads(NEWS_PATH.read_text(encoding="utf-8"))
    corrected = clean_payload(payload)
    attempted, images_added, failed = recover_inline_media(payload)

    NEWS_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        "Article contextual cleanup: "
        f"{corrected} stories corrected; {attempted} image recovery fetches; "
        f"{images_added} editorial image(s) restored; {failed} image fetch failure(s)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
