from __future__ import annotations

from pathlib import Path

import enrich_tweets as module

ROOT = Path(__file__).resolve().parents[1]


def test_blockquote_is_detected() -> None:
    raw = '''
    <article>
      <p>Officials responded to the announcement online.</p>
      <blockquote class="twitter-tweet">
        <p lang="en">Transit service is returning to normal this evening.</p>
        &mdash; London Transit (@LTCLdnOnt) <a href="https://twitter.com/LTCLdnOnt/status/1891234567890123456">March 1, 2026</a>
      </blockquote>
    </article>
    '''
    tweets = module.extract_from_html(raw, 'https://example.test/story')
    assert len(tweets) == 1
    anchor, block = tweets[0]
    assert 'Officials responded' in anchor
    assert block['media_type'] == 'tweet'
    assert block['tweet_id'] == '1891234567890123456'
    assert block['handle'] == 'LTCLdnOnt'
    assert block['text'] == 'Transit service is returning to normal this evening.'


def test_syndication_extracts_photos_and_best_remote_video() -> None:
    block = module.base_block('https://x.com/example/status/1891234567890123456')
    assert block
    payload = {
        'text': 'Video from the scene.',
        'created_at': 'Sun Sep 07 22:00:00 +0000 2026',
        'user': {
            'name': 'Example News',
            'screen_name': 'example',
            'profile_image_url_https': 'https://pbs.twimg.com/profile_images/example.jpg',
        },
        'mediaDetails': [
            {
                'type': 'photo',
                'media_url_https': 'https://pbs.twimg.com/media/photo.jpg',
                'original_info': {'width': 1600, 'height': 900},
            },
            {
                'type': 'video',
                'media_url_https': 'https://pbs.twimg.com/ext_tw_video_thumb/poster.jpg',
                'video_info': {
                    'variants': [
                        {'content_type': 'application/x-mpegURL', 'url': 'https://video.twimg.com/movie.m3u8'},
                        {'content_type': 'video/mp4', 'bitrate': 256000, 'url': 'https://video.twimg.com/low.mp4'},
                        {'content_type': 'video/mp4', 'bitrate': 2176000, 'url': 'https://video.twimg.com/high.mp4'},
                    ]
                },
            },
        ],
    }
    enriched = module.apply_syndication(block, payload)
    assert enriched['author_name'] == 'Example News'
    assert enriched['avatar'].startswith('https://pbs.twimg.com/')
    assert enriched['photos'][0]['width'] == 1600
    assert enriched['poster'].endswith('poster.jpg')
    assert enriched['video_url'] == 'https://video.twimg.com/high.mp4'


def test_generic_x_embed_is_upgraded_in_place() -> None:
    original_enrich = module.enrich
    module.enrich = lambda block: {**block, 'text': 'Recovered post text'}
    try:
        blocks = [
            {'type': 'paragraph', 'text': 'The mayor posted an update.'},
            {
                'type': 'media',
                'media_type': 'embed',
                'provider': 'x',
                'url': 'https://platform.twitter.com/embed/Tweet.html?id=1891234567890123456&dnt=true',
                'source_url': 'https://twitter.com/example/status/1891234567890123456',
                'title': 'Embedded post',
            },
            {'type': 'paragraph', 'text': 'The announcement followed council debate.'},
        ]
        merged, changed = module.merge(blocks, [])
        assert changed == 1
        assert merged[1]['media_type'] == 'tweet'
        assert merged[1]['tweet_id'] == '1891234567890123456'
        assert merged[1]['text'] == 'Recovered post text'
    finally:
        module.enrich = original_enrich


def test_missing_tweet_is_inserted_after_matching_article_anchor() -> None:
    original_enrich = module.enrich
    module.enrich = lambda block: block
    try:
        blocks = [
            {'type': 'paragraph', 'text': 'The agency shared the following update on social media.'},
            {'type': 'paragraph', 'text': 'Crews remained at the scene for several hours.'},
        ]
        tweet = module.base_block('https://x.com/example/status/1891234567890123456')
        assert tweet
        merged, changed = module.merge(
            blocks,
            [('The agency shared the following update on social media.', tweet)],
        )
        assert changed == 1
        assert merged[1]['media_type'] == 'tweet'
    finally:
        module.enrich = original_enrich


def test_oembed_fills_text_and_author_without_media_download() -> None:
    block = module.base_block('https://x.com/example/status/1891234567890123456')
    assert block
    enriched = module.apply_oembed(block, {
        'author_name': 'Example Reporter',
        'author_url': 'https://twitter.com/example',
        'html': '<blockquote class="twitter-tweet"><p lang="en">A short update from London.</p></blockquote>',
    })
    assert enriched['author_name'] == 'Example Reporter'
    assert enriched['text'] == 'A short update from London.'
    assert enriched['handle'] == 'example'
    assert 'video_bytes' not in enriched


def test_fxtwitter_fallback_recovers_remote_mp4() -> None:
    block = module.base_block('https://x.com/example/status/1891234567890123456')
    assert block
    enriched = module.apply_fxtwitter(block, {
        'tweet': {
            'text': 'Fallback media post.',
            'author': {
                'name': 'Example News',
                'screen_name': 'example',
                'avatar_url': 'https://pbs.twimg.com/profile_images/example.jpg',
            },
            'media_extended': [
                {
                    'type': 'video',
                    'url': 'https://video.twimg.com/ext_tw_video/example.mp4',
                    'thumbnail_url': 'https://pbs.twimg.com/ext_tw_video_thumb/example.jpg',
                }
            ],
        }
    })
    assert enriched['video_url'].endswith('example.mp4')
    assert enriched['poster'].endswith('example.jpg')
    assert enriched['avatar'].startswith('https://pbs.twimg.com/')


def test_tweet_renderer_is_native_and_video_is_on_demand() -> None:
    component = (ROOT / 'src' / 'lib' / 'components' / 'TweetCard.svelte').read_text(encoding='utf-8')
    reader = (ROOT / 'src' / 'routes' / 'story' / '[id]' / '+page.svelte').read_text(encoding='utf-8')
    assert 'class="tweet-card"' in component
    assert "media_type === 'tweet'" in reader
    assert '<TweetCard {block} />' in reader
    assert 'videoActive' in component
    assert 'preload="none"' in component
    assert 'src={videoUrl}' in component
    assert 'font-size: 12px' not in component


def main() -> int:
    tests = [
        test_blockquote_is_detected,
        test_syndication_extracts_photos_and_best_remote_video,
        test_generic_x_embed_is_upgraded_in_place,
        test_missing_tweet_is_inserted_after_matching_article_anchor,
        test_oembed_fills_text_and_author_without_media_download,
        test_fxtwitter_fallback_recovers_remote_mp4,
        test_tweet_renderer_is_native_and_video_is_on_demand,
    ]
    for test in tests:
        test()
        print(f'PASS {test.__name__}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
