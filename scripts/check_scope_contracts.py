#!/usr/bin/env python3
"""Fail CI if the strict Local/Canada source contract regresses."""
from __future__ import annotations

from annotate_scopes import scope_for_story


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"Scope contract failed: {message}")


def main() -> None:
    require(
        scope_for_story({
            "source": "London Free Press",
            "url": "https://lfpress.com/news/local-news/example",
        }) == "local",
        "London Free Press must be Local",
    )

    require(
        scope_for_story({
            "source": "CTV News London",
            "url": "https://www.ctvnews.ca/london/article/example/",
        }) == "local",
        "CTV News London must be Local",
    )

    require(
        scope_for_story({
            "source": "CTV News",
            "url": "https://www.ctvnews.ca/london/article/example/",
        }) == "local",
        "legacy CTV name is Local only for a ctvnews.ca/london URL",
    )

    require(
        scope_for_story({
            "source": "CTV News",
            "url": "https://www.ctvnews.ca/canada/article/example/",
            "local_score": 100,
            "local_reasons": ["London, Ontario +35"],
        }) == "canada",
        "non-London CTV must never be Local",
    )

    require(
        scope_for_story({
            "source": "CTV News Canada",
            "url": "https://www.ctvnews.ca/canada/article/example/",
        }) == "canada",
        "CTV News Canada must remain Canada",
    )

    require(
        scope_for_story({
            "source": "The Globe and Mail",
            "url": "https://www.theglobeandmail.com/canada/article-example/",
            "local_score": 100,
            "local_reasons": ["London, Ontario +35"],
        }) == "canada",
        "The Globe and Mail must never appear in Local",
    )

    require(
        scope_for_story({
            "source": "Toronto Star",
            "local_score": 100,
            "local_reasons": ["London, Ontario +35"],
        }) == "canada",
        "national publishers cannot be promoted into Local by story text",
    )

    print("Scope contracts passed: Local is the explicit London-source whitelist only.")


if __name__ == "__main__":
    main()
