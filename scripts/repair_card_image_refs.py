from __future__ import annotations

"""Keep card-image caches aligned with the article hero selected by Scoop.

Card thumbnails are derived artifacts. If a hero is rejected or replaced later in
the pipeline, an older card_image must never survive and continue rendering the
rejected image on Home. This pass also promotes the first remaining article image
when the final article contract has removed a bad hero but left legitimate inline
photography behind.

The card contract is intentionally source-agnostic. Publisher avatar services often
attach perfectly plausible story alt text to a tiny author/profile derivative. A
remote image that explicitly asks for a very small rendition is therefore not
eligible to become a large article-card hero, regardless of its metadata.
"""

import hashlib
import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse, urlunparse

ROOT = Path(__file__).resolve().parents[1]
NEWS_PATH = ROOT / "data" / "news.json"
PUBLIC_DIR = ROOT / "public"
SCHEMA = 3
TINY_REMOTE_MAX = 192
REMOTE_SIZE_RE = re.compile(r"(?:resize|width|height|w|h)\s*=\s*(\d{1,4})", re.I)
INVALID_REMOTE_IMAGE_MARKERS = (
    "/akam/",
    "pixel_",
    "texttospeech",
    "nojsimg",
    "favicon",
    "tracking-pixel",
    "tracking_pixel",
)


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


def requested_remote_sizes(value: Any) -> list[int]:
    """Return explicit resize dimensions encoded in a remote image URL.

    Several publisher CDNs encode their transforms once or twice inside a query
    parameter, for example ``Resize%3D76``. Decode a few rounds before checking so
    those derivatives cannot bypass the card-quality guard.
    """
    text = clean(value)
    if not text.startswith(("http://", "https://")):
        return []
    decoded = text
    for _ in range(3):
        next_value = unquote(decoded)
        if next_value == decoded:
            break
        decoded = next_value
    sizes: list[int] = []
    for match in REMOTE_SIZE_RE.finditer(decoded):
        try:
            size = int(match.group(1))
        except (TypeError, ValueError):
            continue
        if size > 0:
            sizes.append(size)
    return sizes


def is_tiny_remote_derivative(value: Any, *, threshold: int = TINY_REMOTE_MAX) -> bool:
    sizes = requested_remote_sizes(value)
    return bool(sizes and min(sizes) <= threshold)


def is_invalid_remote_image(value: Any) -> bool:
    text = clean(value)
    if not text.startswith(("http://", "https://")):
        return False
    decoded = text.lower()
    for _ in range(3):
        next_value = unquote(decoded)
        if next_value == decoded:
            break
        decoded = next_value
    return any(marker in decoded for marker in INVALID_REMOTE_IMAGE_MARKERS)


def first_article_image(story: dict[str, Any]) -> tuple[str, str, str]:
    blocks = story.get("content_blocks")
    if not isinstance(blocks, list):
        return "", "", ""
    for block in blocks:
        if not isinstance(block, dict) or block.get("type") != "image":
            continue
        ref = clean(block.get("url") or block.get("src"))
        if ref and not is_tiny_remote_derivative(ref) and not is_invalid_remote_image(ref):
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


def is_cbc_story(story: dict[str, Any]) -> bool:
    source = clean(story.get("source")).lower()
    if source.startswith("cbc news"):
        return True
    return bool(clean(story.get("cbc_lite_url")))


def cbc_candidate_variants(value: str) -> list[str]:
    """Return safe CBC CDN URL variants, preferring the publisher URL as supplied.

    CBC reader output sometimes leaves a broken image-transform query attached to an
    otherwise valid ``i.cbc.ca`` asset. If the transformed request cannot be cached,
    retry the same image path without the transform before giving up.
    """
    value = clean(value)
    if not value:
        return []
    variants = [value]
    try:
        parsed = urlparse(value)
        host = parsed.netloc.lower().split(":", 1)[0]
        if host == "i.cbc.ca" and parsed.query:
            base = urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", ""))
            if base and base not in variants:
                variants.append(base)
    except Exception:
        pass
    return variants


def recover_cbc_hero(story: dict[str, Any]) -> str:
    """Recover a CBC hero using the stricter, image-score-aware reader path.

    This is a final safety net for a CBC hero that this pass has just rejected. It
    deliberately does not try to fill every image-less CBC record during a Pages
    build, keeping deployments bounded and leaving broad recovery to enrichment.
    """
    if not is_cbc_story(story):
        return ""
    try:
        import cache_cbc_images as cbc
        import repair_cbc_images as cbc_repair
    except Exception:
        return ""

    reader_urls: list[str] = []
    for key in ("cbc_lite_url", "canonical_url", "resolved_url", "article_url", "original_url"):
        value = clean(story.get(key))
        if value and value not in reader_urls:
            reader_urls.append(value)

    for page_url in reader_urls:
        try:
            candidates = cbc_repair.reader_image_candidates(page_url, story)
        except Exception:
            candidates = []
        for candidate in candidates:
            candidate = clean(candidate)
            if not candidate or is_tiny_remote_derivative(candidate) or is_invalid_remote_image(candidate):
                continue
            try:
                if cbc.image_score(candidate) <= 0:
                    continue
            except Exception:
                continue

            for variant in cbc_candidate_variants(candidate):
                if is_invalid_remote_image(variant) or is_tiny_remote_derivative(variant):
                    continue
                try:
                    cached = cbc.cache_image(variant)
                except Exception:
                    cached = ""
                if cached:
                    story["cbc_images_cached"] = True
                    story.pop("cbc_image_hotlink", None)
                    story["cbc_card_guard_recovered"] = True
                    return cached

            # A valid i.cbc.ca image is still preferable to a broken CBC tracking
            # pixel. Keep it as a browser fallback when GitHub's runner cannot copy
            # the asset. The next enrichment run will get another chance to cache it.
            story["cbc_image_hotlink"] = True
            story["cbc_card_guard_recovered"] = True
            return candidate
    return ""


def repair_story(story: dict[str, Any]) -> bool:
    changed = False
    hero = clean(story.get("image"))
    rejected_cbc_hero = False

    # Explicitly tiny CDN derivatives and known tracking/pixel endpoints are not
    # viable story heroes, even if publisher metadata labels them like the story.
    if hero and (is_tiny_remote_derivative(hero) or is_invalid_remote_image(hero)):
        reason = "tiny-remote-derivative" if is_tiny_remote_derivative(hero) else "invalid-remote-image"
        rejected_cbc_hero = is_cbc_story(story)
        story["image"] = ""
        story["card_image"] = ""
        story["card_image_small"] = ""
        story["card_image_rejected_reason"] = reason
        hero = ""
        changed = True

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

    # Only perform synchronous CBC network recovery when this pass rejected a bad
    # CBC hero. Normal image-less stories are handled later by the enrichment job.
    if not hero and rejected_cbc_hero:
        recovered = recover_cbc_hero(story)
        if recovered:
            story["image"] = recovered
            hero = recovered
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
