# London News mobile navigation + Sections update

Replace/add these files in the repository:

- `src/layouts/BaseLayout.astro`
- `src/pages/index.astro`
- `src/pages/sections/index.astro` (new)
- `src/styles/global.css`

What changed:

- Mobile navigation is now icon-only: Home, Sections, Sources.
- Mobile nav bar and active tabs use a 50px radius.
- The Home icon becomes a Back to Top arrow after scrolling on every page. Tapping it scrolls the current page to the top, then it returns to Home state.
- Added `/sections/`, generated from categories already present in `news.json`.
- Section links return to Home with that category filtered.
- The old horizontal category bar is hidden on mobile but remains on desktop.
- Decorative horizontal dividers are removed across the public UI. Story source-rail dividers are intentionally preserved.
