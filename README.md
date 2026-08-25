# London News card + sources update

Replace/add these files in the existing repository:

- `src/layouts/BaseLayout.astro`
- `src/pages/index.astro`
- `src/pages/sources/index.astro` (new)
- `src/styles/global.css`

## What changed

- New `/sources/` page with persistent show/hide switches for every source currently present in `data/news.json`.
- Source preferences are stored in `localStorage` under `london-news-hidden-sources` and automatically applied to the homepage.
- New mobile bottom tab bar for Home, Latest, and Sources.
- Desktop keeps the compact header and adds only an icon shortcut to Sources.
- Homepage converted to a responsive card publication layout.
- First visible story becomes the feature card automatically. The next two become secondary cards. Remaining stories reflow into compact cards.
- Filtering, search, and hidden-source preferences all trigger a live layout reflow.
- Article reader and related stories receive matching card surfaces for visual consistency.
- All controls remain at least 44px touch targets and all UI text remains at least 16px.
- London, Ontario timezone formatting remains `America/Toronto`.

No scraper, workflow, source configuration, or `data/news.json` files are replaced by this update.
