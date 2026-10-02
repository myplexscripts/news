"""Keep the current repository feed and media within a seven-day publication window."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import unquote, urlparse
from dateutil import parser

ROOT = Path(__file__).resolve().parents[1]
RETENTION_DAYS = 7


def retained_stories(stories, now=None):
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=RETENTION_DAYS)
    kept = []
    for story in stories:
        try:
            published = parser.parse(str(story.get('published') or ''))
            if published.tzinfo is None:
                published = published.replace(tzinfo=timezone.utc)
            # A later source in the cluster must not extend this report's lifetime.
            if published > cutoff:
                kept.append(story)
        except (ValueError, TypeError, OverflowError):
            continue
    return kept


def prune_payload(payload, now=None, *, recluster=True):
    from ranking import apply_recent_editorial_intelligence
    previous_count = len(payload.get('stories') or [])
    stories = retained_stories(payload.get('stories') or [], now)
    editorial = None
    if recluster or len(stories) != previous_count:
        stories, editorial = apply_recent_editorial_intelligence(stories, now)
    payload['stories'] = stories
    payload['retention_days'] = RETENTION_DAYS
    payload['story_count'] = len(stories)
    payload['full_story_count'] = sum(s.get('content_status') == 'full' for s in stories)
    payload['partial_story_count'] = sum(s.get('content_status') == 'partial' for s in stories)
    scores = [int((s.get('quality') or {}).get('score') or 0) for s in stories]
    payload['average_quality'] = round(sum(scores) / len(scores)) if scores else 0
    if editorial is not None:
        payload['editorial_clusters'] = editorial['clusters']
        for key in ('cluster_count', 'multi_source_cluster_count', 'top_story_ids'):
            payload[key] = editorial[key]
    return previous_count - len(stories)


def referenced_cache_paths(value):
    found = set()
    def visit(item):
        if isinstance(item, dict):
            for child in item.values(): visit(child)
        elif isinstance(item, list):
            for child in item: visit(child)
        elif isinstance(item, str):
            parsed = urlparse(item)
            if parsed.scheme or parsed.netloc:
                return
            path = unquote(parsed.path).lstrip('/')
            if path.startswith('news/cache/'):
                path = path[5:]
            if path.startswith('cache/') and '..' not in Path(path).parts:
                found.add(path)
    visit(value)
    return found


def prune_unused_cache(stories, public=ROOT / 'public'):
    referenced = referenced_cache_paths(stories)
    removed = 0
    for path in (public / 'cache').rglob('*'):
        if path.is_file() and path.relative_to(public).as_posix() not in referenced:
            path.unlink()
            removed += 1
    return removed


def main():
    path = ROOT / 'data/news.json'
    payload = json.loads(path.read_text())
    removed = prune_payload(payload)
    from image_assets import attach_cached_images
    attach_cached_images(payload['stories'])
    media = prune_unused_cache(payload['stories'])
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n')
    print(f'Seven-day retention: removed {removed} expired articles and {media} unreferenced media files; kept {len(payload["stories"])} articles')


if __name__ == '__main__':
    main()
