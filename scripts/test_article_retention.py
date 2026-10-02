from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from article_retention import retained_stories, prune_payload, prune_unused_cache


def main():
    now = datetime(2026, 10, 2, 16, tzinfo=timezone.utc)
    rows = [
        {'id':'new', 'published':(now-timedelta(days=7, microseconds=-1)).isoformat(), 'cluster_id':'shared', 'source':'A'},
        {'id':'boundary', 'published':(now-timedelta(days=7)).isoformat(), 'cluster_latest_published':now.isoformat(), 'cluster_id':'shared', 'source':'B'},
        {'id':'old', 'published':(now-timedelta(days=8)).isoformat()},
        {'id':'invalid', 'published':'invalid'},
    ]
    assert [s['id'] for s in retained_stories(rows, now)] == ['new']
    payload = {'stories':rows}
    assert prune_payload(payload, now) == 3
    assert payload['story_count'] == 1
    assert payload['stories'][0]['cluster_member_ids'] == ['new']
    assert payload['stories'][0]['cluster_source_count'] == 1
    with TemporaryDirectory() as directory:
        public = Path(directory); (public/'cache').mkdir()
        for name in ['shared.webp','expired.webp']:(public/'cache'/name).write_bytes(b'image')
        (public/'logo.svg').write_text('logo')
        assert prune_unused_cache([{'content_blocks':[{'url':'/news/cache/shared.webp'}]}], public) == 1
        assert (public/'cache/shared.webp').exists()
        assert (public/'logo.svg').exists()
    print('PASS seven-day retention boundary, cluster metadata and shared media cleanup')


if __name__ == '__main__':main()
