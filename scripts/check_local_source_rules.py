#!/usr/bin/env python3
"""Fail CI if explicit London source handling regresses."""
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
            {"source": "CTV News", "scope": "canada", "category": "Canada"},
            {"source": "London Free Press", "scope": "canada", "category": "Canada"},
            {"source": "Toronto Star", "scope": "local", "category": "Local"},
            {"source": "Toronto Star", "scope": "canada", "category": "Canada"},
        ],
        "source_health": [
            {"source": "CTV News", "scope": "local"},
            {"source": "CTV News Canada", "scope": "canada"},
        ],
    }
    result = apply_rules(payload)
    stories = result["stories"]

    require(stories[0]["source"] == "CTV News London", "legacy CTV local name must become CTV News London")
    require(stories[0]["scope"] == "local", "CTV News London must always be Local")
    require(stories[1]["scope"] == "local", "London Free Press must always be Local")
    require(stories[2]["scope"] == "local", "story-level London matches from broader publishers must stay Local")
    require(stories[3]["scope"] == "canada", "non-London broader stories must stay Canada")
    require(result["source_health"][0]["source"] == "CTV News London", "Sources screen must show CTV News London")
    require(result["source_health"][1]["source"] == "CTV News Canada", "CTV News Canada name must remain distinct")

    print("Local-source contracts passed: confirmed London sources are always Local and CTV editions stay distinct.")


if __name__ == "__main__":
    main()
