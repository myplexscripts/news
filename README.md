# London News product reliability + enrichment pass

This package builds on the latest UI consistency and Scoop fixes.

## UI/navigation
- Header is no longer sticky.
- Mobile header no longer contains Search.
- Mobile bottom navigation is now Home, Sections, Search, Sources, icon-only.
- Home still becomes Back to top after scrolling on every page.
- Desktop keeps header search; non-home pages open the dedicated Search screen.
- Added `/search/` with live archive search across headline, publisher, summary, category, article text and enriched topics.

## Publisher identity and health
- Configured sources now include first-party favicon/logo URLs.
- Source cards, article source cards, admin health rows and feed cards can show publisher identity instead of initials.
- Source health is copied onto each story as `source_health_status`.
- A story is `hero_eligible` only when the source is healthy, extraction is usable, locality is adequate and a real image is available.
- Poor/degraded stories remain chronological but cannot take a large hero position.

## Scoop v10
- Extraction schema bumped to 10 so cached stories progressively refresh.
- Expanded generic junk rejection for related/recommended/video/popular modules.
- Keeps all existing strict Global, Postmedia, Heart FM and CTV rules.
- Story topics are enriched deterministically from category, local relevance reasons, cluster coverage and extraction completeness.

## Clustering and locality
- Cross-publisher clustering thresholds are stricter to reduce accidental merges.
- Same-publisher follow-ups remain separate unless effectively duplicates.
- Global, CTV and Heart FM publisher priors were lowered so generic Ontario/Oxford coverage cannot appear strongly local just because of publisher identity.

## Performance
- Scoop caches up to 140 recent card images as 720px square WebP files in `public/cache/news/` using the existing focal-point crop.
- Cards use cached images when available; article hero images remain original resolution.
- The workflow now commits both `data/news.json` and `public/cache/` during scheduled refreshes.

## PWA
- Added manifest, app icons and a lightweight service worker.
- The app shell can be installed to an iPhone/desktop and previously loaded shell pages can be opened when the network is unavailable.

## Files
Replace/add the matching files from this package, including `.github/workflows/site.yml`, `public/`, `scripts/`, and `src/`.

The package does not contain `data/news.json`, so it will not overwrite your existing archive.
