from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from typing import Any

from dateutil import parser as date_parser
from rapidfuzz import fuzz

CLUSTER_WINDOW_HOURS = 36
GOOGLE_DISCOVERY_MIN_LOCAL_SCORE = 25
TOP_STORY_MIN_LOCAL_SCORE = 40

STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "been", "being", "but", "by", "can", "could",
    "did", "do", "does", "for", "from", "had", "has", "have", "he", "her", "hers", "him", "his",
    "how", "i", "if", "in", "into", "is", "it", "its", "may", "more", "new", "news", "not", "of",
    "on", "or", "our", "out", "over", "says", "say", "said", "she", "that", "the", "their", "them",
    "there", "they", "this", "to", "up", "was", "we", "were", "what", "when", "where", "which", "who",
    "why", "will", "with", "would", "you", "your", "after", "before", "amid", "about", "across", "near",
    "latest", "update", "updates", "story", "stories", "local", "ontario", "london",
    "government", "police", "city", "council", "mayor", "mayoral", "candidate", "announces", "announced",
    "investigate", "investigates", "investigating", "approves", "approved", "project", "plan", "plans",
    "report", "reports", "reported", "official", "officials", "former", "downtown", "area",
}

LOCAL_TERMS: tuple[tuple[int, str, tuple[str, ...]], ...] = (
    (35, "London, Ontario", ("london ontario", "london ont", "london on", "london-area", "london area", "londoner", "londoners")),
    (30, "City of London", ("city of london", "london city council", "london city hall", "london mayor")),
    (28, "London Police", ("london police", "london police service", "lps media")),
    (28, "London Fire", ("london fire department", "london fire", "ldnontfire")),
    (26, "Western University", ("western university", "western mustangs")),
    (26, "Fanshawe College", ("fanshawe college", "fanshawe")),
    (26, "London health", ("london health sciences centre", "lhsc", "middlesex-london health unit", "mlhu")),
    (24, "London schools", ("thames valley district school board", "tvdsb", "london district catholic school board", "ldcsb")),
    (24, "London Transit", ("london transit", "ltc", "ltc bus", "london transit commission")),
    (24, "London Knights", ("london knights", "budweiser gardens", "canada life place")),
    (22, "Middlesex", ("middlesex county", "middlesex centre", "middlesex-london", "middlesex county opp")),
    (18, "St. Thomas", ("st thomas", "st. thomas", "st-thomas")),
    (18, "Strathroy", ("strathroy", "strathroy-caradoc")),
    (16, "Thames Centre", ("thames centre", "dorchester", "thorndale")),
    (14, "Nearby community", ("lucan", "ilderton", "komoka", "mount brydges", "glencoe", "parkhill", "grand bend", "lambton shores", "ausable river")),
    (10, "London neighbourhood", (
        "old east village", "wortley village", "byron", "masonville", "white oaks", "hyde park",
        "lambeth", "westmount", "oakridge", "argyle", "soho", "pond mills", "river bend", "sunningdale",
    )),
    (10, "London street", (
        "richmond street", "dundas street", "oxford street", "wellington road", "commissioners road",
        "highbury avenue", "wonderland road", "adelaide street", "wharncliffe road", "fanshawe park road",
        "hamilton road", "springbank drive", "baseline road", "base line road",
    )),
    (8, "London landmark", ("covent garden market", "victoria park", "thames river", "springbank park", "storybook gardens")),
    (5, "Southwestern Ontario", ("southwestern ontario", "southwest ontario")),
)

NEGATIVE_TERMS: tuple[tuple[int, str, tuple[str, ...]], ...] = (
    (-90, "London, UK", ("london england", "london uk", "greater london", "westminster uk", "downing street", "british prime minister")),
    (-45, "United Kingdom", ("united kingdom", "uk government", "british government", "england")),
)

SOURCE_PRIORS = {
    "London Police Service": 55,
    "London Fire Department": 55,
    "City of London Newsroom": 55,
    "106.9 The X": 35,
    "London Free Press": 30,
    "CBC News London": 30,
    "Global News London": 20,
    "CTV News": 15,
    "104.7 Heart FM": 10,
}


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _key(value: Any) -> str:
    text = _clean(value).lower().replace("’", "'")
    text = re.sub(r"[^a-z0-9']+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _dt(value: Any) -> datetime:
    try:
        parsed = date_parser.parse(str(value or ""))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except Exception:
        return datetime(1970, 1, 1, tzinfo=timezone.utc)


def _tokens(value: str) -> set[str]:
    tokens = set()
    for token in re.findall(r"[a-z0-9]+(?:['-][a-z0-9]+)?", _key(value)):
        if len(token) < 4 or token in STOPWORDS or token.isdigit():
            continue
        tokens.add(token)
    return tokens


def _phrase_hits(text: str, phrases: tuple[str, ...]) -> list[str]:
    haystack = f" {_key(text)} "
    hits: list[str] = []
    for phrase in phrases:
        needle = f" {_key(phrase)} "
        if needle in haystack:
            hits.append(phrase)
    return hits


def local_relevance(story: dict[str, Any]) -> tuple[int, list[str]]:
    title = _clean(story.get("title"))
    summary = _clean(story.get("summary"))
    body = " ".join(_clean(p) for p in (story.get("paragraphs") or [])[:5])
    text = f"{title} {summary} {body}"

    score = int(SOURCE_PRIORS.get(_clean(story.get("source")), 0))
    reasons: list[tuple[int, str]] = []
    if score:
        reasons.append((score, f"local publisher +{score}"))

    positive_total = 0
    seen_labels: set[str] = set()
    for weight, label, phrases in LOCAL_TERMS:
        if label in seen_labels:
            continue
        if _phrase_hits(text, phrases):
            positive_total += weight
            seen_labels.add(label)
            reasons.append((weight, f"{label} +{weight}"))

    lowered = _key(text)
    if "london" in lowered.split() and not any(
        label in seen_labels for label in ("London, Ontario", "City of London", "London Police", "London Fire")
    ):
        positive_total += 12
        reasons.append((12, "London mention +12"))

    score = max(score, min(100, score + positive_total))

    for penalty, label, phrases in NEGATIVE_TERMS:
        if _phrase_hits(text, phrases):
            score += penalty
            reasons.append((penalty, f"{label} {penalty}"))

    score = max(0, min(100, score))
    reasons_sorted = [reason for _, reason in sorted(reasons, key=lambda item: abs(item[0]), reverse=True)[:6]]
    return score, reasons_sorted


def freshness_score(published: Any, now: datetime | None = None) -> int:
    now = now or datetime.now(timezone.utc)
    age_hours = max(0.0, (now - _dt(published)).total_seconds() / 3600)
    if age_hours <= 1:
        return 100
    if age_hours <= 3:
        return 92
    if age_hours <= 6:
        return 84
    if age_hours <= 12:
        return 72
    if age_hours <= 24:
        return 58
    if age_hours <= 36:
        return 44
    if age_hours <= 48:
        return 30
    if age_hours <= 72:
        return 14
    return 0


def image_quality_score(story: dict[str, Any]) -> int:
    if not story.get("image"):
        return 0
    score = 72
    if story.get("image_focus_x") is not None and story.get("image_focus_y") is not None:
        score += 14
    if _clean(story.get("image_alt")):
        score += 8
    return min(100, score)


def _story_entities(story: dict[str, Any]) -> set[str]:
    text = f"{_clean(story.get('title'))} {_clean(story.get('summary'))}"
    labels: set[str] = set()
    for _, label, phrases in LOCAL_TERMS:
        if _phrase_hits(text, phrases):
            labels.add(label)
    return labels


def story_similarity(left: dict[str, Any], right: dict[str, Any]) -> tuple[float, dict[str, float]]:
    left_title = _key(left.get("title"))
    right_title = _key(right.get("title"))
    if not left_title or not right_title:
        return 0.0, {}

    left_tokens = _tokens(f"{left.get('title', '')} {left.get('summary', '')}")
    right_tokens = _tokens(f"{right.get('title', '')} {right.get('summary', '')}")
    shared = left_tokens & right_tokens
    union = left_tokens | right_tokens
    jaccard = len(shared) / max(1, len(union))
    containment = len(shared) / max(1, min(len(left_tokens), len(right_tokens)))

    # Keep a headline-only overlap signal. Summaries often use very different
    # wording between publishers and must not erase an otherwise distinctive match.
    left_title_tokens = _tokens(str(left.get("title") or ""))
    right_title_tokens = _tokens(str(right.get("title") or ""))
    title_shared = left_title_tokens & right_title_tokens
    title_containment = len(title_shared) / max(1, min(len(left_title_tokens), len(right_title_tokens)))

    literal_title_ratio = fuzz.ratio(left_title, right_title) / 100.0
    token_title_ratio = fuzz.token_set_ratio(left_title, right_title) / 100.0
    title_ratio = max(literal_title_ratio, token_title_ratio * 0.96)
    entity_overlap = bool(_story_entities(left) & _story_entities(right))

    score = (title_ratio * 0.48) + (containment * 0.34) + (jaccard * 0.13) + (token_title_ratio * 0.05)
    if entity_overlap:
        score += 0.05
    score = min(1.0, score)
    return score, {
        "title": round(title_ratio, 3),
        "literal_title": round(literal_title_ratio, 3),
        "token_title": round(token_title_ratio, 3),
        "containment": round(containment, 3),
        "jaccard": round(jaccard, 3),
        "shared": float(len(shared)),
        "title_containment": round(title_containment, 3),
        "title_shared": float(len(title_shared)),
        "entity": 1.0 if entity_overlap else 0.0,
    }


def _should_cluster(left: dict[str, Any], right: dict[str, Any]) -> bool:
    delta_hours = abs((_dt(left.get("published")) - _dt(right.get("published"))).total_seconds()) / 3600
    if delta_hours > CLUSTER_WINDOW_HOURS:
        return False

    score, parts = story_similarity(left, right)
    shared = int(parts.get("shared", 0))
    title_shared = int(parts.get("title_shared", 0))
    same_source = _clean(left.get("source")) == _clean(right.get("source"))

    if same_source:
        return bool(
            parts.get("literal_title", 0) >= 0.88
            or (parts.get("title", 0) >= 0.90 and parts.get("containment", 0) >= 0.78 and shared >= 5)
        )

    if parts.get("literal_title", 0) >= 0.78 and shared >= 3:
        return True
    # Strong cross-publisher headline matches should survive unrelated summary prose.
    if (
        parts.get("token_title", 0) >= 0.84
        and parts.get("title_containment", 0) >= 0.72
        and title_shared >= 4
    ):
        return True
    if parts.get("token_title", 0) >= 0.86 and parts.get("containment", 0) >= 0.60 and shared >= 4:
        return True
    if parts.get("containment", 0) >= 0.64 and shared >= 4 and score >= 0.58:
        return True
    if parts.get("entity", 0) and shared >= 4 and score >= 0.60:
        return True
    return False


def _representative_score(story: dict[str, Any]) -> float:
    quality = float((story.get("quality") or {}).get("score") or 0)
    local = float(story.get("local_score") or 0)
    image = float(story.get("image_score") or 0)
    direct_bonus = 8 if not story.get("discovery_via") else 0
    content_bonus = 6 if story.get("content_status") == "full" else 2 if story.get("content_status") == "partial" else 0
    return (quality * 0.42) + (local * 0.28) + (image * 0.16) + direct_bonus + content_bonus


def _coverage_score(source_count: int) -> int:
    return {0: 0, 1: 20, 2: 52, 3: 76, 4: 90}.get(source_count, 100)


def _ranking(story: dict[str, Any], source_count: int, now: datetime) -> tuple[int, list[str]]:
    local = int(story.get("local_score") or 0)
    fresh = freshness_score(story.get("published"), now)
    coverage = _coverage_score(source_count)
    quality = int((story.get("quality") or {}).get("score") or 0)
    image = int(story.get("image_score") or 0)

    score = round((local * 0.35) + (fresh * 0.25) + (coverage * 0.20) + (quality * 0.10) + (image * 0.10))
    reasons = [
        f"local relevance {local}/100",
        f"freshness {fresh}/100",
        f"coverage {source_count} {'source' if source_count == 1 else 'sources'}",
        f"extraction quality {quality}/100",
        f"image quality {image}/100",
    ]
    return max(0, min(100, score)), reasons


def apply_editorial_intelligence(
    stories: list[dict[str, Any]], now: datetime | None = None
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Annotate stories with local relevance, event clusters and ranking metadata."""
    now = now or datetime.now(timezone.utc)
    if not stories:
        return stories, {"clusters": [], "top_story_ids": [], "cluster_count": 0, "multi_source_cluster_count": 0}

    for story in stories:
        local, local_reasons = local_relevance(story)
        story["local_score"] = local
        story["local_reasons"] = local_reasons
        story["image_score"] = image_quality_score(story)

    ordered_indices = sorted(range(len(stories)), key=lambda idx: _dt(stories[idx].get("published")), reverse=True)
    parent = list(range(len(stories)))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(left: int, right: int) -> None:
        a, b = find(left), find(right)
        if a != b:
            parent[b] = a

    for pos, left_idx in enumerate(ordered_indices):
        left = stories[left_idx]
        left_dt = _dt(left.get("published"))
        for right_idx in ordered_indices[pos + 1:]:
            right = stories[right_idx]
            age = (left_dt - _dt(right.get("published"))).total_seconds() / 3600
            if age > CLUSTER_WINDOW_HOURS:
                break
            if _should_cluster(left, right):
                union(left_idx, right_idx)

    grouped: dict[int, list[int]] = {}
    for idx in range(len(stories)):
        grouped.setdefault(find(idx), []).append(idx)

    cluster_summaries: list[dict[str, Any]] = []
    for members in grouped.values():
        member_stories = [stories[idx] for idx in members]
        representative = max(member_stories, key=_representative_score)
        representative_id = representative.get("id", "")
        oldest = min(member_stories, key=lambda item: (_dt(item.get("published")), str(item.get("id", ""))))
        cluster_seed = str(oldest.get("id") or _key(oldest.get("title")))
        cluster_id = "cluster-" + hashlib.sha1(cluster_seed.encode("utf-8", "ignore")).hexdigest()[:12]
        ordered_members = sorted(member_stories, key=lambda item: _dt(item.get("published")), reverse=True)
        sources = list(dict.fromkeys(_clean(item.get("source")) for item in ordered_members if _clean(item.get("source"))))
        source_count = len(sources)
        member_ids = [str(item.get("id")) for item in ordered_members if item.get("id")]

        cluster_local = max(int(item.get("local_score") or 0) for item in member_stories)
        cluster_published = max(
            (_dt(item.get("published")) for item in member_stories),
            default=datetime(1970, 1, 1, tzinfo=timezone.utc),
        )
        ranking_proxy = dict(representative)
        ranking_proxy["local_score"] = cluster_local
        ranking_proxy["published"] = cluster_published.isoformat()
        rank_score, ranking_reasons = _ranking(ranking_proxy, source_count, now)

        for item in member_stories:
            item["cluster_id"] = cluster_id
            item["cluster_size"] = len(member_stories)
            item["cluster_source_count"] = source_count
            item["cluster_sources"] = sources
            item["cluster_member_ids"] = member_ids
            item["cluster_representative_id"] = representative_id
            item["cluster_representative"] = item.get("id") == representative_id
            item["rank_score"] = rank_score
            item["ranking_reasons"] = ranking_reasons
            item["freshness_score"] = freshness_score(item.get("published"), now)
            item["cluster_local_score"] = cluster_local
            item["cluster_freshness_score"] = freshness_score(cluster_published.isoformat(), now)
            item["cluster_latest_published"] = cluster_published.isoformat()

        cluster_summaries.append({
            "id": cluster_id,
            "representative_id": representative_id,
            "title": representative.get("title", ""),
            "category": representative.get("category", "Local"),
            "sources": sources,
            "source_count": source_count,
            "member_ids": member_ids,
            "member_count": len(member_stories),
            "local_score": cluster_local,
            "rank_score": rank_score,
            "published": cluster_published.isoformat(),
            "ranking_reasons": ranking_reasons,
        })

    cluster_summaries.sort(key=lambda item: (item["rank_score"], _dt(item["published"])), reverse=True)

    representative_stories = [story for story in stories if story.get("cluster_representative")]
    eligible = [
        story for story in representative_stories
        if int(story.get("cluster_local_score") or story.get("local_score") or 0) >= TOP_STORY_MIN_LOCAL_SCORE
    ]
    eligible.sort(key=lambda item: (int(item.get("rank_score") or 0), _dt(item.get("published"))), reverse=True)
    top_story_ids = [str(story.get("id")) for story in eligible[:3] if story.get("id")]

    metadata = {
        "clusters": cluster_summaries,
        "top_story_ids": top_story_ids,
        "cluster_count": len(cluster_summaries),
        "multi_source_cluster_count": sum(1 for item in cluster_summaries if item["source_count"] > 1),
    }
    return stories, metadata
