# Scoop audit hotfix

This repairs the GitHub Actions failure caused by `scripts/test_scraper_regressions.py` being referenced by the workflow but omitted from the previous audit ZIP.

Replace the matching files in your repository.

Included:
- `.github/workflows/site.yml`
- `scripts/fetch_news.py`
- `scripts/test_scraper_regressions.py`
- `scripts/audit_sources.py`
- `scripts/test_audit.py`
- `src/pages/admin/index.astro`

The regression test file and the Scoop version it tests are bundled together so they cannot get out of sync.
