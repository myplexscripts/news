from __future__ import annotations

from datetime import datetime, timedelta, timezone

from ranking import GOOGLE_DISCOVERY_MIN_LOCAL_SCORE, apply_editorial_intelligence


def story(identifier: str, title: str, source: str, summary: str, *, hours: float = 1, category: str = "Local", quality: int = 80, discovery: bool = False) -> dict:
    now = datetime(2026, 8, 26, 2, 0, tzinfo=timezone.utc)
    item = {
        "id": identifier,
        "title": title,
        "source": source,
        "summary": summary,
        "published": (now - timedelta(hours=hours)).isoformat(),
        "category": category,
        "quality": {"score": quality},
        "content_status": "full",
        "paragraphs": [summary],
        "image": "https://images.example/story.jpg",
    }
    if discovery:
        item["discovery_via"] = "Google News London Discovery"
    return item


def main() -> None:
    now = datetime(2026, 8, 26, 2, 0, tzinfo=timezone.utc)
    stories = [
        story("fire-cbc", "Major fire closes Richmond Street in downtown London", "CBC News London", "Crews are battling a large fire on Richmond Street in London, Ont."),
        story("fire-ctv", "Richmond Street closed as crews battle downtown London fire", "CTV News", "London fire crews closed Richmond Street while battling a major downtown blaze.", hours=1.2),
        story("fire-global", "Fire shuts down Richmond Street in central London", "Global News London", "A fire in London, Ontario has closed Richmond Street while crews work at the scene.", hours=1.5),
        story("western", "Western University opens new student residence", "London Free Press", "Western University in London has opened a new residence for students.", hours=2, category="Education"),
        story("generic-on", "Ontario unveils provincial tax credit", "CTV News", "The Ontario government announced a tax credit available across the province.", hours=0.2, category="Business"),
        story("uk", "UK government announces rail plan in London", "Some UK Outlet", "The British government announced a new rail plan in London, England.", hours=0.1, discovery=True),
        story("provincial", "Ontario legislature resumes after summer break", "Some Provincial Outlet", "MPP debate resumes at Queen's Park in Toronto.", hours=0.1, discovery=True),
        story("breakin", "Police investigate break-in on Dundas Street", "London Police Service", "London Police are investigating a break-in on Dundas Street.", hours=2),
        story("collision", "Police investigate unrelated collision on Highbury Avenue", "London Police Service", "London Police are investigating a collision on Highbury Avenue.", hours=2.1),
    ]

    annotated, metadata = apply_editorial_intelligence(stories, now)
    lookup = {item["id"]: item for item in annotated}

    assert lookup["fire-cbc"]["cluster_id"] == lookup["fire-ctv"]["cluster_id"] == lookup["fire-global"]["cluster_id"]
    assert lookup["fire-cbc"]["cluster_source_count"] == 3
    assert lookup["breakin"]["cluster_id"] != lookup["collision"]["cluster_id"]
    assert lookup["uk"]["local_score"] < GOOGLE_DISCOVERY_MIN_LOCAL_SCORE
    assert lookup["provincial"]["local_score"] < GOOGLE_DISCOVERY_MIN_LOCAL_SCORE
    assert metadata["top_story_ids"][0] in {"fire-cbc", "fire-ctv", "fire-global"}
    assert "generic-on" not in metadata["top_story_ids"]
    assert metadata["multi_source_cluster_count"] == 1

    print("Editorial intelligence tests passed.")


if __name__ == "__main__":
    main()
