from fetch_news import is_boilerplate_block, clean_article_blocks

assert is_boilerplate_block('Get daily National news', 'Global News London')
assert is_boilerplate_block('Sponsored content', 'Global News London')
assert is_boilerplate_block('Exclusive articles from Ryan Pyette, Dale Carruthers and others. Plus, the Noon News Roundup newsletter on weekdays.', 'London Free Press')
assert is_boilerplate_block('More from Local News', '104.7 Heart FM')
blocks = clean_article_blocks([
    'London police say the investigation remains ongoing.',
    'Related stories',
    'Another unrelated story headline',
], 'Global News London', 'Test headline')
assert blocks and blocks[0].startswith('London police')
print('Scoop quality tests passed.')
