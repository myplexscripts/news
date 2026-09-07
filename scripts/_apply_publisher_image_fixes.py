from __future__ import annotations

from pathlib import Path


FETCH_NEWS = Path("scripts/fetch_news.py")
MEDIA = Path("scripts/enrich_article_media.py")


def patch_fetch_news() -> None:
    text = FETCH_NEWS.read_text(encoding="utf-8")
    text = text.replace("EXTRACTION_SCHEMA = 15", "EXTRACTION_SCHEMA = 16", 1)

    start = text.index("def srcset_candidates(value: Any) -> list[tuple[int, str]]:")
    end = text.index("\ndef best_img_url(", start)
    replacement = '''def srcset_candidates(value: Any) -> list[tuple[int, str]]:
    """Parse responsive image candidates without splitting commas inside URLs.

    CBC image asset paths contain a literal comma before the numeric asset id.
    A plain ``str.split(",")`` therefore corrupts otherwise valid srcset URLs.
    Candidate descriptors are the reliable boundary, so parse complete
    ``URL + width/density descriptor`` pairs first and fall back only when a
    publisher supplies a non-standard descriptor-free srcset.
    """
    raw = html.unescape(str(value or "")).strip()
    if not raw:
        return []

    candidates: list[tuple[int, str]] = []
    pattern = re.compile(r'(?:^|,\\s*)(\\S+?)\\s+([0-9.]+[wx])(?=\\s*(?:,|$))', re.I)
    for match in pattern.finditer(raw):
        url, descriptor = match.group(1), match.group(2).lower()
        try:
            number = float(descriptor[:-1])
            score = int(number * (1000 if descriptor.endswith("x") else 1))
        except Exception:
            score = 1
        candidates.append((max(1, score), url))

    if candidates:
        return candidates

    # Descriptor-free srcsets are uncommon but legal enough in the wild to
    # preserve the old permissive behaviour. Do not use this path for normal
    # CBC responsive markup because its URL itself contains commas.
    for part in raw.split(','):
        candidate = part.strip().split()[0] if part.strip() else ''
        if candidate:
            candidates.append((1, candidate))
    return candidates

'''
    text = text[:start] + replacement + text[end + 1 :]

    valid_start = text.index("def valid_article_image(")
    valid_end = text.index("\ndef figure_caption(", valid_start)
    valid_slice = text[valid_start:valid_end]
    old = '    if any(token in lower for token in IMAGE_JUNK):\n        return False'
    new = '''    # CBC uses /default.jpg for real editorial photos, so "default" is only
    # a junk signal in element metadata, not in an otherwise valid image URL.
    if any(token in lower for token in IMAGE_JUNK if token != "default"):
        return False'''
    assert old in valid_slice, "valid_article_image URL junk check changed unexpectedly"
    valid_slice = valid_slice.replace(old, new, 1)
    text = text[:valid_start] + valid_slice + text[valid_end:]

    old_cbc = '''        "remove": ["[data-cy*='related']", ".related", ".newsletter", ".share", ".ad"],'''
    new_cbc = '''        "remove": [
            "[data-cy*='related']", ".related", ".newsletter", ".share", ".ad",
            "[data-cy*='player']", "[class*='player-placeholder']", ".mediaEmbed",
        ],'''
    assert old_cbc in text, "CBC profile changed unexpectedly"
    text = text.replace(old_cbc, new_cbc, 1)

    old_globe = '''        "roots": [
            "[data-testid='article-body']", "[itemprop='articleBody']",
            ".article-body", ".c-article-body", "main article", "article", "main",
        ],'''
    new_globe = '''        "roots": [
            "article#content-gate", "#content-gate",
            "[data-testid='article-body']", "[itemprop='articleBody']",
            ".article-body", ".c-article-body", "main article", "article",
        ],'''
    assert old_globe in text, "Globe profile changed unexpectedly"
    text = text.replace(old_globe, new_globe, 1)

    selection_needle = '''    else:
        blocks = dom_blocks
        paragraphs, text = text_from_blocks(blocks)

    raw_summary = ('''
    structured = '''    else:
        blocks = dom_blocks
        paragraphs, text = text_from_blocks(blocks)

    # For publishers with noisy whole-page markup, the images that survived the
    # chosen article body are more trustworthy than generic page-wide candidates.
    # This is especially important for CTV, whose server HTML contains dozens of
    # recommendation cards, and for Globe pages with large recirculation rails.
    if source.name == "CBC News London" or is_ctv_source(source.name) or "globe and mail" in source.name.lower():
        structured_inline: list[dict[str, Any]] = []
        for block in blocks:
            if block.get("type") != "image" or not block.get("url"):
                continue
            image_url = normalize_image_url(str(block.get("url") or ""), final_url)
            if not valid_article_image(image_url) or same_image(image_url, lead_image):
                continue
            if any(same_image(image_url, prior["url"]) for prior in structured_inline):
                continue
            structured_inline.append({
                "url": image_url,
                "alt": clean_text(block.get("alt", ""), 180),
                "caption": clean_text(block.get("caption", ""), 320),
                "width": int_attr(block.get("width")) or None,
                "height": int_attr(block.get("height")) or None,
                "score": 1000 - len(structured_inline),
            })
            if len(structured_inline) >= MAX_ARTICLE_IMAGES:
                break
        if structured_inline:
            inline_candidates = structured_inline
        elif is_ctv_source(source.name):
            # Never publish recommendation-card images as CTV article media just
            # because the visible article DOM is client-rendered.
            inline_candidates = []

    raw_summary = ('''
    assert selection_needle in text, "article selection insertion point changed unexpectedly"
    text = text.replace(selection_needle, structured, 1)
    FETCH_NEWS.write_text(text, encoding="utf-8")


def patch_media() -> None:
    text = MEDIA.read_text(encoding="utf-8")
    text = text.replace("MEDIA_SCHEMA = 3", "MEDIA_SCHEMA = 4", 1)

    old_import = '''    extract_dom_blocks as extract_article_dom_blocks,
    image_dedupe_key,
    same_image,
    valid_article_image,
)'''
    new_import = '''    extract_dom_blocks as extract_article_dom_blocks,
    extract_ctv_embedded_blocks,
    image_dedupe_key,
    is_ctv_source,
    same_image,
    valid_article_image,
)'''
    assert old_import in text, "media import block changed unexpectedly"
    text = text.replace(old_import, new_import, 1)

    start = text.index("def process_story(story: dict[str, Any]) -> tuple[list[tuple[str, dict[str, Any]]], str]:")
    end = text.index("\ndef story_needs_work(", start)
    replacement = '''def process_story(story: dict[str, Any]) -> tuple[list[tuple[str, dict[str, Any]]], str]:
    source = clean_text(story.get("source", ""))
    cbc_media: list[tuple[str, dict[str, Any]]] = []
    if source == "CBC News London":
        # CBC's Jina/Lite route is useful for playable audio/video, but returning
        # here used to prevent the normal DOM pass from ever recovering photos.
        cbc_media = extract_cbc_media(story)

    url = clean_text(story.get("url", ""))
    if not url:
        return cbc_media, "cbc:jina-media-v4" if cbc_media else "dom:no-url"
    try:
        raw, final_url = fetch_html(url)
    except Exception as exc:
        if cbc_media:
            return cbc_media, "cbc:jina-media-v4"
        return [], f"dom:{type(exc).__name__}"

    dom_media = extract_dom_media(raw, final_url)
    hero_url = clean_text(story.get("image", ""))
    images = extract_dom_images(
        raw,
        final_url,
        source,
        clean_text(story.get("title", "")),
        hero_url,
    )

    if is_ctv_source(source):
        # CTV's actual article body lives in Arc/Fusion state on pages where the
        # visible server DOM has no usable article root. Reuse that first-party
        # structure so recommendation-card photos never stand in for story media.
        soup = BeautifulSoup(raw, "html.parser")
        embedded_blocks, _stats = extract_ctv_embedded_blocks(
            soup,
            clean_text(story.get("title", "")),
            final_url,
        )
        embedded_images: list[tuple[str, dict[str, Any]]] = []
        anchor = ""
        for block in embedded_blocks:
            kind = block.get("type")
            if kind in {"paragraph", "heading", "quote"} and block.get("text"):
                anchor = clean_text(block.get("text"), 240)
                continue
            if kind != "image" or not block.get("url"):
                continue
            image_url = str(block.get("url") or "")
            if same_image(image_url, hero_url) or not valid_article_image(image_url):
                continue
            embedded_images.append((anchor, block))
        if embedded_images:
            images = [*embedded_images, *images]

    combined = [*cbc_media, *dom_media, *images]
    deduped: list[tuple[str, dict[str, Any]]] = []
    seen: set[str] = set()
    for anchor, block in combined:
        key = block_key(block)
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append((anchor, block))

    if source == "CBC News London":
        return deduped, "cbc:jina-dom-media-images-v4"
    if is_ctv_source(source):
        return deduped, "ctv:embedded-dom-media-images-v4"
    return deduped, "dom:media-images-v4"

'''
    text = text[:start] + replacement + text[end + 1 :]
    MEDIA.write_text(text, encoding="utf-8")


def patch_workflows() -> None:
    changes = [
        (
            Path(".github/workflows/refresh.yml"),
            "          python scripts/test_scoop_runtime.py\n",
            "          python scripts/test_scoop_runtime.py\n          python scripts/test_publisher_image_structures.py\n",
        ),
        (
            Path(".github/workflows/enrich.yml"),
            "          python scripts/test_article_media.py\n",
            "          python scripts/test_article_media.py\n          python scripts/test_publisher_image_structures.py\n",
        ),
    ]
    for path, needle, insertion in changes:
        body = path.read_text(encoding="utf-8")
        assert needle in body, f"{path} test insertion point changed unexpectedly"
        body = body.replace(needle, insertion, 1)
        path.write_text(body, encoding="utf-8")


def main() -> int:
    patch_fetch_news()
    patch_media()
    patch_workflows()
    print("Applied publisher article image fixes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
