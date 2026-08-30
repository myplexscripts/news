from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

DEFAULT_PROFILE: dict[str, Any] = {
    "name": "generic",
    "roots": [
        "[itemprop='articleBody']",
        "[data-testid='article-body']",
        "article .article-body",
        "article .article-content",
        "article .story-body",
        "article .entry-content",
        "article .post-content",
        "article",
        "main",
    ],
    "remove": [
        "script", "style", "noscript", "nav", "footer", "form", "button", "aside",
        "[role='complementary']", "[aria-hidden='true']",
        "[class*='advert']", "[class*='newsletter']", "[class*='subscribe']",
        "[class*='related']", "[class*='recommend']", "[class*='recirc']",
        "[class*='read-more']", "[class*='readmore']", "[class*='outbrain']",
        "[class*='taboola']", "[class*='trending']", "[class*='most-read']",
        "[class*='most-popular']", "[class*='more-news']", "[class*='more-stories']",
        "[class*='follow-author']", "[class*='author-follow']", "[class*='feedback']",
        "[class*='comment-module']", "[class*='comments-module']",
        "[data-testid*='related']", "[data-testid*='recommend']", "[data-testid*='recirc']",
        "[id*='related']", "[id*='recirc']", "[id*='advert']",
    ],
}

PROFILES: dict[str, dict[str, Any]] = {
    "cbc": {
        "name": "cbc",
        "roots": [
            "[data-cy='storyWrapper']", ".story-content", ".story-body",
            "[itemprop='articleBody']", "article",
        ],
        "remove": [
            "[data-cy*='related']", "[data-cy*='recommend']", ".related", ".newsletter",
            ".share", ".ad", "[class*='recirc']", "[class*='recommend']",
            "[class*='more-from']", "[class*='preferred-source']",
        ],
    },
    "postmedia": {
        "name": "postmedia",
        "roots": [
            "[data-testid='article-body']", ".article-content", ".article-body",
            "[itemprop='articleBody']", "article",
        ],
        "remove": [
            ".subscription", ".subscribe", ".paywall", ".registration", ".account",
            ".newsletter", ".related", ".share", ".social", ".ad", ".advertisement",
            "[class*='subscription']", "[class*='paywall']", "[class*='registration']",
            "[class*='epaper']", "[class*='puzzle']", "[class*='comment']",
            "[class*='trending']", "[id*='trending']", "[data-testid*='trending']",
            "[class*='most-read']", "[class*='most-popular']", "[class*='popular']",
            "[class*='read-more']", "[class*='readmore']", "[class*='recirc']",
            "[class*='recommend']", "[class*='more-from']", "[class*='morefrom']",
            "[data-testid*='related']", "[data-testid*='recommend']",
            "[id*='read-more']", "[id*='related']",
        ],
    },
    "ctv": {
        "name": "ctv",
        "roots": [
            "[data-testid='article-body']", "[data-testid*='article-body']",
            "[data-testid*='articleBody']", "[class*='articleBody']", "[class*='ArticleBody']",
            ".articleBody", ".article-body", ".article__body", ".article-content",
            ".story-body", "[class*='storyBody']", "[class*='StoryBody']",
            "[itemprop='articleBody']", "main article", "article", "main",
        ],
        "remove": [
            ".related", ".newsletter", ".share", ".social", ".ad", ".advertisement",
            "[class*='related']", "[class*='recommend']", "[class*='advert']",
            "[class*='newsletter']", "[class*='recirc']", "[class*='popular']",
            "[class*='read-more']", "[class*='readmore']", "[class*='more-from']",
            "[class*='morefrom']", "[data-testid*='related']", "[data-testid*='recommend']",
            "[aria-label*='related' i]", "[aria-label*='recommended' i]",
        ],
    },
    "global": {
        "name": "global",
        "roots": [
            ".l-article__body", ".l-article__content", ".article-content",
            "[data-testid='article-body']", "[itemprop='articleBody']", "article",
        ],
        "remove": [
            ".l-article__related", ".l-relatedStories", ".l-inlineStories", ".c-posts",
            ".c-readmore", "[data-shortcode='readmore']", ".c-ad", ".ad",
            "[class*='advert']", "[class*='sponsor']", ".newsletter",
            "[class*='newsletter']", "[class*='email-signup']", ".share",
            "[class*='share']", "[class*='social']", "[class*='message-bar']",
            "[class*='recirc']", "[class*='recommended']", "[class*='preferred-source']",
        ],
    },
    "globe": {
        "name": "globe",
        "roots": [
            "[data-testid='article-body']", "[itemprop='articleBody']",
            ".article-body", ".c-article-body", "main article", "article", "main",
        ],
        "remove": [
            "[class*='advert']", "[class*='related']", "[class*='recirc']",
            "[class*='recommend']", "[class*='follow']", "[class*='feedback']",
            "[class*='error-report']", "[class*='editorial-code']", "[class*='interact']",
            "[class*='comment']", "[data-testid*='follow']", "[data-testid*='related']",
        ],
    },
    "star": {
        "name": "star",
        "roots": [
            "[data-testid='article-body']", "[itemprop='articleBody']",
            ".article-body", ".asset-content", ".story-body", "main article", "article", "main",
        ],
        "remove": [
            "[class*='trending']", "[id*='trending']", "[class*='more-news']",
            "[class*='related']", "[class*='recommend']", "[class*='recirc']",
            "[class*='share']", "[class*='social']", "[class*='comment']",
            "[class*='advert']", "[data-testid*='related']", "[data-testid*='trending']",
        ],
    },
    "western": {
        "name": "western",
        "roots": [
            ".entry-content", ".post-content", ".article-content", ".story-content",
            "[itemprop='articleBody']", "main article", "article", "main",
        ],
        "remove": [
            ".related", ".related-posts", ".share", ".social", ".newsletter", ".subscribe",
            "[class*='related']", "[class*='recommend']", "[class*='recirc']",
            "[class*='more-stories']", "[class*='more-from']", ".faculty-card", ".author-card",
        ],
    },
    "police": {
        "name": "police",
        "roots": [
            ".news-article-content", ".news-post-content", ".news-post__content",
            ".field--name-body", ".article-content", "[itemprop='articleBody']", "article", "main",
        ],
        "remove": [
            ".related", ".share", ".social", ".newsletter", ".news-search", ".subscribe",
            "[class*='back-to']", "[class*='related']", "[class*='recommend']",
            "[class*='recirc']", "[class*='print']", "[class*='feedback']",
        ],
    },
    "municipal": {
        "name": "municipal",
        "roots": [
            ".field--name-body", ".node__content", ".article-content",
            "[itemprop='articleBody']", "article", "main",
        ],
        "remove": [
            ".related", ".share", ".social", ".feedback", ".webform",
            "[class*='related']", "[class*='recommend']", "[class*='recirc']",
        ],
    },
}


def profile_for(source: str = "", url: str = "") -> dict[str, Any]:
    source_key = str(source or "").lower()
    host = urlparse(str(url or "")).netloc.lower().split(":", 1)[0]

    if "cbc" in source_key or host.endswith("cbc.ca"):
        selected = PROFILES["cbc"]
    elif "free press" in source_key or "postmedia" in source_key or "national post" in source_key or host.endswith("lfpress.com") or host.endswith("postmedia.com") or host.endswith("nationalpost.com"):
        selected = PROFILES["postmedia"]
    elif "ctv" in source_key or host.endswith("ctvnews.ca"):
        selected = PROFILES["ctv"]
    elif "global news" in source_key or host.endswith("globalnews.ca"):
        selected = PROFILES["global"]
    elif "globe and mail" in source_key or host.endswith("theglobeandmail.com"):
        selected = PROFILES["globe"]
    elif "toronto star" in source_key or host.endswith("thestar.com"):
        selected = PROFILES["star"]
    elif "western" in source_key or host.endswith("uwo.ca") or "westernu.ca" in host or host.endswith("westernnews.ca") or host.endswith("westerngazette.ca"):
        selected = PROFILES["western"]
    elif "london police" in source_key or host.endswith("londonpolice.ca"):
        selected = PROFILES["police"]
    elif "city of london" in source_key or host.endswith("london.ca"):
        selected = PROFILES["municipal"]
    else:
        selected = DEFAULT_PROFILE

    roots = list(dict.fromkeys([*selected.get("roots", []), *DEFAULT_PROFILE["roots"]]))
    remove = list(dict.fromkeys([*DEFAULT_PROFILE["remove"], *selected.get("remove", [])]))
    return {"name": selected.get("name", "generic"), "roots": roots, "remove": remove}
