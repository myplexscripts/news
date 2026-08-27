from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

import requests

import ranking
import run_scoop


def make_story(identifier: str, title: str, source: str, summary: str, paragraphs=None, *, hours: float = 1) -> dict:
    now = datetime(2026, 8, 27, 12, 0, tzinfo=timezone.utc)
    return {
        "id": identifier,
        "title": title,
        "source": source,
        "summary": summary,
        "paragraphs": list(paragraphs or [summary]),
        "published": (now - timedelta(hours=hours)).isoformat(),
        "category": "Local",
        "quality": {"score": 80},
        "content_status": "full",
        "image": "https://images.example/story.jpg",
    }


def test_locality_gate() -> None:
    stories = [
        make_story("oshawa", "Priest charged in Oshawa", "Global News London", "Durham police laid charges in Oshawa."),
        make_story("bayfield", "Golf course clubhouse destroyed in fire near Bayfield", "CTV News", "Fire crews responded near Bayfield."),
        make_story("celebrity", "Actor dies at 80", "104.7 Heart FM", "The performer died at age 80."),
        make_story("airport", "Porter launches flights from London International Airport", "CTV News", "New routes will depart London International Airport."),
        make_story("ilderton", "Community event opens in Ilderton", "CTV News", "Residents gathered in Ilderton for the event."),
        make_story("national-lfp", "U.S. tariff policy changes again", "London Free Press", "The White House announced another tariff measure."),
        make_story("middlesex", "Driver dies after crash in Middlesex County", "London Free Press", "Police responded to a collision in Middlesex County."),
        make_story("bridge", "London Bridge child care expands in Huron County", "CTV News", "London Bridge Child Care Services opened a site near Bayfield."),
        make_story("retired-fire", "Fire crews respond", "London Fire Department", "A legacy Google-discovered fire post."),
    ]

    kept, dropped = run_scoop._publication_filter(stories)
    kept_ids = {story["id"] for story in kept}
    dropped_ids = {story["id"] for story in dropped}

    assert {"airport", "ilderton", "middlesex"} <= kept_ids
    assert {"oshawa", "bayfield", "celebrity", "national-lfp", "bridge", "retired-fire"} <= dropped_ids


def test_safe_classification() -> None:
    assert run_scoop._safe_classify(
        "Western Mustangs quarterback Rancourt ready for opener",
        "The Mustangs football team opens its OUA season this week.",
        "CTV News",
    ) == "Sports"
    assert run_scoop._safe_classify(
        "Former councillor appears in court",
        "The accused appeared in London court on Tuesday.",
        "CTV News",
    ) == "Public Safety"


def test_body_aware_cluster() -> None:
    ctv = make_story(
        "ctv-case",
        "More charges laid against man in child sexual abuse material investigation: LPS",
        "CTV News",
        "London Police laid more charges against a man in a child sexual abuse material investigation.",
        paragraphs=[],
        hours=1,
    )
    ctv["content_status"] = "summary"

    lps = make_story(
        "lps-case",
        "ICE unit investigation",
        "London Police Service",
        "The London Police Service Internet Child Exploitation Unit laid additional charges.",
        paragraphs=[
            "The London Police Service Internet Child Exploitation Unit continued an investigation into child sexual abuse and exploitation material.",
            "Investigators laid additional offences after reviewing child sexual abuse material seized during the investigation.",
        ],
        hours=1.4,
    )

    unrelated = make_story(
        "lps-unrelated",
        "Firearm and cocaine seized",
        "London Police Service",
        "Police seized a firearm and cocaine during an unrelated investigation.",
        paragraphs=["Officers executed a search warrant and seized a firearm and cocaine."],
        hours=1.2,
    )

    original_similarity = ranking.story_similarity
    original_should_cluster = ranking._should_cluster
    try:
        ranking.story_similarity = run_scoop._body_aware_story_similarity
        ranking._should_cluster = run_scoop._body_aware_should_cluster
        annotated, _ = ranking.apply_editorial_intelligence([ctv, lps, unrelated], datetime(2026, 8, 27, 12, 0, tzinfo=timezone.utc))
    finally:
        ranking.story_similarity = original_similarity
        ranking._should_cluster = original_should_cluster

    lookup = {story["id"]: story for story in annotated}
    assert lookup["ctv-case"]["cluster_id"] == lookup["lps-case"]["cluster_id"]
    assert lookup["ctv-case"]["cluster_source_count"] == 2
    assert lookup["lps-unrelated"]["cluster_id"] != lookup["ctv-case"]["cluster_id"]


def test_cbc_curl_fallback() -> None:
    timeout_error = requests.ConnectTimeout("CBC request timed out")

    def failing_get(url, *args, **kwargs):
        raise timeout_error

    completed = SimpleNamespace(returncode=0, stdout=b"<rss><channel></channel></rss>", stderr=b"")
    resilient = run_scoop._resilient_cbc_get(failing_get)

    with patch("run_scoop.subprocess.run", return_value=completed) as mocked:
        response = resilient("https://www.cbc.ca/webfeed/rss/rss-canada-london", timeout=5)

    assert response.status_code == 200
    assert response.content.startswith(b"<rss>")
    assert response.headers.get("X-London-News-Transport") == "curl-fallback"
    command = mocked.call_args.args[0]
    assert "--http1.1" in command
    assert "--max-time" in command


def main() -> None:
    test_locality_gate()
    print("PASS test_locality_gate")
    test_safe_classification()
    print("PASS test_safe_classification")
    test_body_aware_cluster()
    print("PASS test_body_aware_cluster")
    test_cbc_curl_fallback()
    print("PASS test_cbc_curl_fallback")


if __name__ == "__main__":
    main()
