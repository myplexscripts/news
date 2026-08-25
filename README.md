# London News polish and scraper fixes

Replace the matching files in the repository with the files in this package.

This update adds:

- London, Ontario timezone handling using `America/Toronto` in the scraper and all displayed dates
- stronger London Free Press cleanup for Trending, Most Read, subscription and teaser modules
- London Police Service page discovery limited to real `/news/posts/` article pages
- London Police article boundaries that skip search, subscribe and category furniture and stop before media-contact boilerplate
- stronger hero and inline image deduplication
- automatic removal of publisher default images that repeat across many stories
- article media and publisher sidebar in separate grid columns so they cannot overlap
- publisher sidebar positioned beside the hero image on desktop
- inline article images use their natural aspect ratio
- search now expands inside the sticky header with an animated transition instead of opening a second search row
- extraction schema bumped to 4 so older captures are gradually refreshed with the improved rules

The collector still stores timestamps in UTC internally. Naive timestamps from local publishers are interpreted as London, Ontario local time before conversion to UTC. The frontend always formats times in `America/Toronto`, including daylight saving time automatically.
