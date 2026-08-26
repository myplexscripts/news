# London News: mobile nav + CBC/CTV reliability repair

Replace the matching files in your project:

- `src/layouts/BaseLayout.astro`
- `src/styles/global.css`
- `src/pages/index.astro`
- `src/lib/sourceLogos.ts`
- `scripts/fetch_news.py`
- `scripts/sources.py`

## Fixes

### Mobile navigation
- Forces Home, Sections, Search and Sources into one four-column row.
- The final rule uses `!important` so the older three-column mobile override cannot win in the cascade.
- Preserves the 50px capsule/tab radii and back-to-top behaviour.

### CBC News London
- Keeps the configured CBC London RSS feed as the first path.
- If it times out, automatically tries alternate first-party CBC feed endpoints.
- If feeds are unavailable, falls back to the CBC London regional page and only accepts `/news/canada/london/` article URLs.
- A failed primary feed no longer makes the whole CBC source disappear when another CBC path works.

### CTV News
- More article-body DOM selectors and junk-module removal.
- Reads JSON-LD article bodies.
- Reads traditional embedded JSON state.
- Decodes newer Next.js `self.__next_f.push()` hydration payloads.
- Chooses the most complete cleaned first-party article-body candidate.
- Stops before CTV app/contact/newsletter/related-content furniture.
- Recovers London article links from hydration data when the landing page does not expose them as normal text anchors.

### Health and repair
- Extraction schema bumped to 11.
- Backfill increased to 36 stories/run and prioritizes recent CBC/CTV records.
- Source health now measures usable extraction rate and failure rate instead of penalizing publishers simply for publishing short articles.
