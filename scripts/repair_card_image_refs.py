from __future__ import annotations

"""Keep card-image caches aligned with the article hero selected by Scoop.

Card thumbnails are derived artifacts. If a hero is rejected or replaced later in
the pipeline, an older card_image must never survive and continue rendering the
rejected image on Home. This pass also promotes the first remaining article image
when the final article contract has removed a bad hero but left legitimate inline
photography behind.
"""

import hashlib
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
NEWS_PATH = ROOT / "data" / "news.json"
PUBLIC_DIR = ROOT / "public"
SCHEMA = 1


def clean(value: Any) -> str:
    return str(value or "").strip()


def normalize(value: Any) -> str:
    text = clean(value)
    if text.startswith("/news/"):
        return text[len("/news/"):]
    if text.startswith("/"):
        return text[1:]
    return text


def same_ref(left: Any, right: Any) -> bool:
    a = normalize(left)
    b = normalize(right)
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


def first_article_image(story: dict[str, Any]) -> tuple[str, str, str]:
    blocks = story.get("content_blocks")
    if not isinstance(blocks, list):
        return "", "", ""
    for block in blocks:
        if not isinstance(block, dict) or block.get("type") != "image":
            continue
        ref = clean(block.get("url") or block.get("src"))
        if ref:
            return ref, clean(block.get("alt")), clean(block.get("caption"))
    return "", "", ""


def expected_remote_cards(hero: str) -> tuple[str, str]:
    stem = hashlib.sha1(hero.encode("utf-8", "ignore")).hexdigest()[:20]
    return f"cache/news/{stem}.webp", f"cache/news/{stem}-sm.webp"


def local_exists(value: Any) -> bool:
    ref = normalize(value)
    if not ref or ref.startswith(("http://", "https://")):
        return False
    path = PUBLIC_DIR / ref
    return path.exists() and path.is_file()


def repair_story(story: dict[str, Any]) -> bool:
    changed = False
    hero = clean(story.get("image"))

    # The final article contract may reject a bad hero while preserving legitimate
    # article photography. Promote that surviving image rather than leaving Home
    # with either a stale headshot thumbnail or an unnecessary placeholder.
    if not hero:
        candidate, alt, caption = first_article_image(story)
        if candidate:
            story["image"] = candidate
            hero = candidate
            if alt and not clean(story.get("image_alt")):
                story["image_alt"] = alt
            if caption and not clean(story.get("image_caption")):
                story["image_caption"] = caption
            changed = True

    card = clean(story.get("card_image"))
    small = clean(story.get("card_image_small"))

    if not hero:
        if card:
            story["card_image"] = ""
            changed = True
        if small:
            story["card_image_small"] = ""
            changed = True
        if changed:
            story["card_image_contract_schema"] = SCHEMA
        return changed

    if hero.startswith(("http://", "https://")):
        expected, expected_small = expected_remote_cards(hero)

        # A cache generated from any previous hero is unsafe. If the current
        # hero's expected cache does not exist yet, clear the card reference and
        # let the card render the current remote hero until caching catches up.
        if card and normalize(card) != expected:
            story["card_image"] = ""
            card = ""
            changed = True
        if small and normalize(small) != expected_small:
            story["card_image_small"] = ""
            small = ""
            changed = True

        if card and not local_exists(card):
            story["card_image"] = ""
            changed = True
        if small and not local_exists(small):
            story["card_image_small"] = ""
            changed = True
    else:
        normalized_hero = normalize(hero)
        if card and not same_ref(card, hero):
            story["card_image"] = normalized_hero
            changed = True
        elif not card:
            story["card_image"] = normalized_hero
            changed = True

        # A differently named small thumbnail cannot be proven to belong to this
        # local hero, so discard it. The normal cache pass can regenerate one.
        if small and not same_ref(small, hero):
            story["card_image_small"] = ""
            changed = True

    if changed:
        story["card_image_contract_schema"] = SCHEMA
    return changed


def repair_payload(payload: dict[str, Any]) -> int:
    stories = payload.get("stories")
    if not isinstance(stories, list):
        return 0
    count = 0
    for story in stories:
        if isinstance(story, dict) and repair_story(story):
            count += 1
    payload["card_image_contract_schema"] = SCHEMA
    payload["card_image_contract_corrected"] = count
    return count


def main() -> int:
    if not NEWS_PATH.exists():
        print("No data/news.json found")
        return 0
    payload = json.loads(NEWS_PATH.read_text(encoding="utf-8"))
    count = repair_payload(payload)
    NEWS_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Card image contract corrected {count} stories")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
