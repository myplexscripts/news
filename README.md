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

- `src/routes/+layout.svelte` owns the persistent shell, route lifecycle, appearance and article chrome.
- `src/lib/components/AppNavigation.svelte` is the single primary navigation implementation, shared across phone and desktop layouts. Use SvelteKit navigation APIs; do not patch browser history or add a second tab animation script.
- `src/styles/app-system.css` owns shared interface sizing, motion and accessibility rules. Editorial content keeps its existing layout and image proportions.
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
