# London News extraction upgrade

Upload these files into the matching paths in your existing repository and replace the old versions.

This phase adds:

- source-specific extraction profiles for Global, CBC, London Free Press, CTV, 106.9 The X, City of London, London Police and London Fire
- structured article blocks for paragraphs, headings, quotes, lists and inline images
- stronger hero and inline image selection with duplicate and junk-image filtering
- extraction quality scoring from 0 to 100
- full, partial, summary and failed content states
- a hidden `/admin/` collector health page
- a per-source health report showing current extraction quality and failures
- a review queue for weak extractions
- automatic schema upgrades for cached stories
- quality-aware homepage lead selection

The collector uses extraction schema 3. Stories from the current feeds upgrade immediately. Older cached stories are upgraded in batches of 12 per scheduled run so the collector does not hit every publisher at once.

The `/admin/` page is intentionally not linked from the public navigation and includes a `noindex` robots tag. It is hidden from normal visitors, but it is not password protected.
