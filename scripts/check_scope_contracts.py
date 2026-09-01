#!/usr/bin/env python3
"""Fail CI if the Local/Canada story contract regresses."""
from __future__ import annotations

from annotate_scopes import scope_for_story


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"Scope contract failed: {message}")


def main() -> None:
    require(
        scope_for_story({
            "source": "National Publisher",
            "local_score": 35,
            "local_reasons": ["London, Ontario +35"],
        }) == "local",
        "London, Ontario story from a national publisher must be Local",
    )

    require(
        scope_for_story({
            "source": "National Publisher",
            "local_score": 12,
            "local_reasons": ["London mention +12"],
        }) == "local",
        "unambiguous London story from any publisher must be Local",
    )

    require(
        scope_for_story({
            "source": "National Publisher",
            "local_score": 0,
            "local_reasons": [],
        }) == "canada",
        "non-London national story must remain Canada",
    )

    require(
        scope_for_story({
            "source": "CTV News",
            "local_score": 15,
            "local_reasons": ["local publisher +15"],
        }) == "canada",
        "publisher identity alone must not make a broad story Local",
    )

    require(
        scope_for_story({
            "source": "National Publisher",
            "local_score": 0,
            "local_reasons": ["London mention +12", "London, UK -90"],
        }) == "canada",
        "London, UK must never qualify for the London, Ontario feed",
    )

    require(
        scope_for_story({
            "source": "London Police Service",
            "local_score": 0,
            "local_reasons": [],
        }) == "local",
        "London civic institutions must remain inherently Local",
    )

    print("Scope contracts passed: Local is story-level London, Ontario relevance from any publisher.")


if __name__ == "__main__":
    main()
