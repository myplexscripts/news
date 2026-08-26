# Scoop GitHub Action repair

Replace these two files in the repo:

- `scripts/fetch_news.py`
- `scripts/sources.py`

## Fixes

- Removes the Python 3.12 variable-width look-behind that crashed Heart FM/backfill.
- A malformed story can no longer abort a source refresh.
- A malformed backfill story can no longer abort the GitHub Action.
- Sources that already failed in a run are skipped during backfill instead of being hammered again.
- CBC uses a short, no-retry request path on GitHub runners. If CBC stalls, Scoop preserves cached CBC stories and continues the build.
- CTV no longer uses its dead legacy RSS redirect. Discovery comes from `https://www.ctvnews.ca/london/` and first-party `/london/article/` pages.
