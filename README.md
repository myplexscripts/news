# London News HIG Editorial UI Update

Upload the contents of this folder into the matching paths in your existing London News GitHub repository and replace the existing files.

Updated files:

- `src/layouts/BaseLayout.astro`
- `src/pages/index.astro`
- `src/styles/global.css`

## What changed

- Editorial homepage hierarchy instead of a dashboard/card-heavy layout
- Sticky translucent material header
- Search expands directly inside the header
- Search supports Escape, clear/close, live filtering, and live results status
- Top-level section navigation with a compact More menu
- Publisher filtering uses a native select control
- Lead story plus three-story editorial feature row
- Cleaner Latest feed with quieter metadata and fewer containers
- Publisher directory simplified into a restrained sidebar
- Article reader restyled for a more publication-like reading experience
- Article hero and publisher sidebar retain separate grid columns
- All visible UI text remains 16px or larger
- 44px minimum interactive targets
- Focus indicators and skip navigation
- Reduced motion support
- Light, dark, and increased contrast system palettes retained
- London, Ontario timezone display retained

The scraper, source configuration, cached news data, and GitHub workflow are not replaced by this update.
