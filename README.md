# Forest City News

A SvelteKit news app for London, Ontario, with a static GitHub Pages deployment and the Scoop collection pipeline.

## Development

Install the Python dependencies from `requirements.txt`, then run:

```sh
npm ci
npm run dev
```

`npm run build` prepares the feed and article payloads, builds the app, verifies the generated pages and adds article social metadata. Use `BASE_PATH=/news npm run build` for the repository's Pages deployment. Generated files are not source files.

## App structure

- `src/routes/+layout.svelte` owns the persistent shell and the original four-icon mobile navigation: Home, Sections, Search and Settings.
- `public/mobile-nav-stable.css` preserves the navigation geometry and sliding indicator. It must be copied into the production build; `static` is not this project's asset directory.
- The early navigation animation in `src/app.html` provides immediate touch feedback. Do not add labelled tabs, additional destinations or whole-page transitions without an explicit request.
- `src/lib/newsData.js` shares feed and article requests. Cached feed data can render synchronously when returning to a screen.
- Home, Search and Sections expose SvelteKit snapshots for Back/Forward restoration. Article requests discard superseded results.
- `src/pages` and `src/layouts` contain the legacy Astro implementation. The deployed app uses `src/routes`.

## Validation

```sh
npm run check
python scripts/check_ui_contracts.py
python scripts/check_scope_contracts.py
python scripts/check_home_feed_contracts.py
npm run build
```

Also verify primary navigation, article Back, search/filter restoration, mobile safe areas and Reduce Motion in a browser. The production build checks are not a substitute for visual testing on iOS.
