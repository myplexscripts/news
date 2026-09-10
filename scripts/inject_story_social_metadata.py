from __future__ import annotations

"""Create crawlable per-story HTML shells with story-specific share metadata."""

import html
import json
import os
import re
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlparse

ROOT = Path(__file__).resolve().parents[1]
NEWS_PATH = ROOT / "data" / "news.json"
DIST_DIR = ROOT / "dist"
FALLBACK_PATH = DIST_DIR / "404.html"
SITE_TITLE = "Forest City News"
SITE_DESCRIPTION = "Local reporting from across London, Ontario."
MAX_DESCRIPTION = 240
URL_SAFE = "-_.!~*'()"


def clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def trim_preview(value: Any, limit: int = MAX_DESCRIPTION) -> str:
    text = clean(value)
    if len(text) <= limit:
        return text
    clipped = text[: limit + 1].rsplit(" ", 1)[0].rstrip(" ,;:")
    return f"{clipped}…" if clipped else f"{text[:limit].rstrip()}…"


def repository_context() -> tuple[str, str]:
    repository = os.environ.get("GITHUB_REPOSITORY", "myplexscripts/news")
    owner, _, repo = repository.partition("/")
    owner = owner or "myplexscripts"
    repo = repo or "news"
    configured = os.environ.get("BASE_PATH")
    if configured is None:
        base = "" if repo == f"{owner}.github.io" else f"/{repo}"
    else:
        base = "" if configured == "/" else configured.rstrip("/")
    return f"https://{owner}.github.io", base


def absolute_url(value: Any, origin: str, base: str) -> str:
    raw = clean(value)
    if not raw:
        return ""
    parsed = urlparse(raw)
    if parsed.scheme in {"http", "https"} and parsed.netloc:
        return raw
    if raw.startswith("//"):
        return f"https:{raw}"
    path = raw.replace("\\", "/")
    if path.startswith("/"):
        if base and (path == base or path.startswith(f"{base}/")):
            return f"{origin}{path}"
        return f"{origin}{base}{path}"
    return f"{origin}{base}/{path.lstrip('/')}"


def image_mime(value: str) -> str:
    path = urlparse(value).path.lower()
    if path.endswith(".webp"):
        return "image/webp"
    if path.endswith((".jpg", ".jpeg")):
        return "image/jpeg"
    if path.endswith(".png"):
        return "image/png"
    if path.endswith(".gif"):
        return "image/gif"
    return ""


def first_prose(story: dict[str, Any]) -> str:
    for paragraph in story.get("paragraphs") or []:
        text = clean(paragraph)
        if text:
            return text
    for block in story.get("content_blocks") or []:
        if isinstance(block, dict) and block.get("type") in {"paragraph", "quote"}:
            text = clean(block.get("text"))
            if text:
                return text
    return ""


def story_description(story: dict[str, Any]) -> str:
    return trim_preview(story.get("summary") or first_prose(story) or SITE_DESCRIPTION)


def story_image(story: dict[str, Any], origin: str, base: str) -> tuple[str, int | None, int | None]:
    hero = clean(story.get("image"))
    optimized = clean(story.get("editorial_image"))
    optimized_source = clean(story.get("editorial_image_source"))
    if optimized and (not optimized_source or not hero or optimized_source == hero):
        return (
            absolute_url(optimized, origin, base),
            int(story.get("editorial_image_width") or 0) or None,
            int(story.get("editorial_image_height") or 0) or None,
        )
    if hero:
        return absolute_url(hero, origin, base), None, None

    for block in story.get("content_blocks") or []:
        if not isinstance(block, dict) or block.get("type") != "image":
            continue
        source = clean(block.get("url"))
        optimized_block = clean(block.get("optimized_url"))
        optimized_source = clean(block.get("optimized_url_source"))
        chosen = optimized_block if optimized_block and (not optimized_source or optimized_source == source) else source
        if chosen:
            return (
                absolute_url(chosen, origin, base),
                int(block.get("optimized_url_width") or block.get("width") or 0) or None,
                int(block.get("optimized_url_height") or block.get("height") or 0) or None,
            )

    card = clean(story.get("card_image") or story.get("card_image_small"))
    if card:
        return absolute_url(card, origin, base), None, None
    return absolute_url("social.png", origin, base), 1536, 1024


def prop(name: str, value: Any) -> str:
    return f'<meta property="{html.escape(name, quote=True)}" content="{html.escape(clean(value), quote=True)}">'


def named(name: str, value: Any) -> str:
    return f'<meta name="{html.escape(name, quote=True)}" content="{html.escape(clean(value), quote=True)}">'


def strip_existing(document: str) -> str:
    document = re.sub(
        r"\s*<meta\b[^>]*(?:property|name)=[\"'](?:og:[^\"']+|twitter:[^\"']+|article:[^\"']+)[\"'][^>]*>\s*",
        "\n",
        document,
        flags=re.I,
    )
    document = re.sub(r"\s*<meta\b[^>]*name=[\"']description[\"'][^>]*>\s*", "\n", document, flags=re.I)
    document = re.sub(r"\s*<link\b[^>]*rel=[\"']canonical[\"'][^>]*>\s*", "\n", document, flags=re.I)
    return document


def set_title(document: str, title: str) -> str:
    tag = f"<title>{html.escape(title)}</title>"
    if re.search(r"<title\b[^>]*>.*?</title>", document, flags=re.I | re.S):
        return re.sub(r"<title\b[^>]*>.*?</title>", tag, document, count=1, flags=re.I | re.S)
    return document.replace("</head>", f"{tag}</head>", 1)


def metadata(story: dict[str, Any], page_url: str, origin: str, base: str) -> str:
    title = clean(story.get("title")) or SITE_TITLE
    description = story_description(story)
    image, width, height = story_image(story, origin, base)
    image_type = image_mime(image)
    image_alt = clean(story.get("image_alt")) or title

    tags = [
        named("description", description),
        f'<link rel="canonical" href="{html.escape(page_url, quote=True)}">',
        prop("og:site_name", SITE_TITLE),
        prop("og:type", "article"),
        prop("og:locale", "en_CA"),
        prop("og:title", title),
        prop("og:description", description),
        prop("og:url", page_url),
        prop("og:image", image),
        prop("og:image:secure_url", image),
        prop("og:image:alt", image_alt),
    ]
    if image_type:
        tags.append(prop("og:image:type", image_type))
    if width:
        tags.append(prop("og:image:width", width))
    if height:
        tags.append(prop("og:image:height", height))

    tags.extend(
        [
            named("twitter:card", "summary_large_image"),
            named("twitter:title", title),
            named("twitter:description", description),
            named("twitter:image", image),
            named("twitter:image:alt", image_alt),
        ]
    )

    published = clean(story.get("cluster_latest_published") or story.get("published"))
    if published:
        tags.append(prop("article:published_time", published))
    section = clean(story.get("category"))
    if section:
        tags.append(prop("article:section", section))
    return "\n".join(tags)


def story_segment(story_id: str) -> str:
    if re.fullmatch(r"[A-Za-z0-9._~-]+", story_id) and story_id not in {".", ".."}:
        return story_id
    return quote(story_id, safe=URL_SAFE)


def build_shell(fallback: str, story: dict[str, Any], origin: str, base: str) -> tuple[Path, str] | None:
    story_id = clean(story.get("id"))
    title = clean(story.get("title"))
    if not story_id or not title:
        return None

    encoded_id = quote(story_id, safe=URL_SAFE)
    page_url = f"{origin}{base}/story/{encoded_id}/"
    document = set_title(strip_existing(fallback), f"{title} | {SITE_TITLE}")
    if "</head>" not in document:
        raise RuntimeError("Svelte fallback is missing </head>")
    document = document.replace("</head>", f"\n{metadata(story, page_url, origin, base)}\n</head>", 1)
    return DIST_DIR / "story" / story_segment(story_id) / "index.html", document


def main() -> int:
    if not NEWS_PATH.exists():
        raise SystemExit("data/news.json is missing")
    if not FALLBACK_PATH.exists():
        raise SystemExit("dist/404.html is missing; run this after the Svelte build")

    payload = json.loads(NEWS_PATH.read_text(encoding="utf-8"))
    stories = [story for story in payload.get("stories") or [] if isinstance(story, dict)]
    fallback = FALLBACK_PATH.read_text(encoding="utf-8")
    origin, base = repository_context()

    generated = 0
    with_images = 0
    with_summaries = 0
    for story in stories:
        built = build_shell(fallback, story, origin, base)
        if built is None:
            continue
        target, document = built
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(document, encoding="utf-8")
        generated += 1
        with_images += int(bool(clean(story.get("editorial_image") or story.get("image"))))
        with_summaries += int(bool(clean(story.get("summary"))))

    if stories and generated == 0:
        raise SystemExit("No story social shells were generated")
    print(f"Story social metadata: {generated} shells, {with_images} with story images, {with_summaries} with story summaries")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
