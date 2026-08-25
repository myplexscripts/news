# London News

A static local news reader for London, Ontario. The public site is built with Astro and deployed to GitHub Pages. A scheduled GitHub Action collects source feeds, fetches article pages, extracts readable article content and images, then rebuilds the site.

## How it works

1. `scripts/sources.py` defines local sources.
2. `scripts/fetch_news.py` reads RSS feeds or source pages.
3. New and stale articles are fetched and passed through Trafilatura plus a BeautifulSoup fallback.
4. Full readable text, metadata, hero imagery and inline article images are stored in `data/news.json`.
5. Astro turns the data into static homepage and story pages.
6. GitHub Pages serves only prebuilt files, so visitors never wait for scraping.

Previously captured full articles are reused for 12 hours. This keeps scheduled runs much lighter than re-downloading every article on every refresh. Older summary-only records are gradually backfilled on future runs.

## Add a source

Edit `scripts/sources.py` and add another `Source(...)` entry.

```python
Source(
    name="Example News",
    url="https://example.com/feed/",
    homepage="https://example.com/",
    accent="#0088FF",
)
```

For a source without RSS, use `kind="page"` and point `url` at the publication's news listing page.

## Local development

```bash
pip install -r requirements.txt
python scripts/fetch_news.py
npm install
npm run dev
```

## GitHub Pages

In the repository settings, set Pages to **GitHub Actions**. The included workflow refreshes and redeploys automatically.

## Publishing note

Full-text scraping and republishing can be subject to publisher terms, copyright and image licensing. For a public site, only enable full-content republication for sources where you have the appropriate permission or licence.
