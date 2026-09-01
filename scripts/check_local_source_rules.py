#!/usr/bin/env python3
"""Fail CI if the explicit London source whitelist regresses."""
from __future__ import annotations

from apply_local_source_rules import LOCAL_SOURCES, apply_rules


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"Local-source contract failed: {message}")


def main() -> None:
    required = {
        "104.7 Heart FM",
        "106.9 The X",
        "CBC News London",
        "CTV News London",
        "City of London Newsroom",
        "Environment Canada London Alerts",
        "Fanshawe College Newsroom",
        "Global News London",
        "London District Catholic School Board",
        "London Free Press",
        "London Health Sciences Centre",
        "London Police Service",
        "London Transit Commission",
        "Middlesex County",
        "Middlesex-London Health Unit",
        "St. Joseph's Health Care London",
        "Thames Valley District School Board",
        "Western News",
    }
    require(required <= LOCAL_SOURCES, "confirmed London source list must remain Local")

    payload = {
        "stories": [
            {
                "source": "CTV News",
                "url": "https://www.ctvnews.ca/london/article/example/",
                "scope": "canada",
                "category": "Canada",
            },
            {
                "source": "CTV News",
                "url": "https://www.ctvnews.ca/canada/article/example/",
                "scope": "local",
                "category": "Local",
            },
            {"source": "London Free Press", "scope": "canada", "category": "Canada"},
            {
                "source": "The Globe and Mail",
                "scope": "local",
                "category": "Local",
                "local_score": 100,
                "local_reasons": ["London, Ontario +35"],
            },
            {
                "source": "Toronto Star",
                "scope": "local",
                "category": "Local",
                "local_score": 100,
                "local_reasons": ["London, Ontario +35"],
            },
        ],
        "source_health": [
            {"source": "CTV News", "scope": "local"},
            {"source": "CTV News Canada", "scope": "canada"},
            {"source": "The Globe and Mail", "scope": "local"},
        ],
    }

    result = apply_rules(payload)
    stories = result["stories"]

    require(stories[0]["source"] == "CTV News London", "legacy London CTV URL must become CTV News London")
    require(stories[0]["scope"] == "local", "CTV News London must be Local")
    require(stories[1]["source"] == "CTV News", "non-London CTV must not be renamed to CTV News London")
    require(stories[1]["scope"] == "canada", "non-London CTV must be Canada")
    require(stories[2]["scope"] == "local", "London Free Press must be Local")
    require(stories[3]["scope"] == "canada", "The Globe and Mail must not be Local")
    require(stories[4]["scope"] == "canada", "Toronto Star must not be Local")
    require(result["source_health"][0]["source"] == "CTV News London", "legacy local CTV health record must become CTV News London")
    require(result["source_health"][1]["source"] == "CTV News Canada", "CTV News Canada name must remain distinct")
    require(result["source_health"][2]["scope"] == "canada", "The Globe and Mail health record must be Canada")

    print("Local-source contracts passed: only the confirmed London source whitelist is Local.")


if __name__ == "__main__":
    main()
