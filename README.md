# Scoop audit + admin review queue

Add/replace these files in the repository:

- `scripts/audit_sources.py`
- `scripts/test_audit.py`
- `src/pages/admin/index.astro`
- `.github/workflows/site.yml`

The refresh job now audits the newest 10 stories from every source after Scoop finishes and writes `data/audit.json`. Scheduled runs commit that report with `news.json`, and every run also uploads it as a 14-day GitHub Actions artifact.

The audit is non-blocking for newly detected story warnings. Known scraper regressions remain build-blocking through `test_scraper_regressions.py`. `test_audit.py` only verifies that the audit rules themselves continue working.

Open `/admin/` after deployment to see the review queue and per-source extraction details.
