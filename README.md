# London News: Heart FM + mobile width repair

Replace these files in your repository:

- `src/styles/global.css`
- `scripts/fetch_news.py`

`source.py` is included only as a reference copy from the previous Scoop Action repair. You do not need to replace it if you already installed that repair.

Changes:
- Mobile feed uses a single flex column as the final layout authority, so hero cards, compact cards, and date headers share exactly the same content width.
- First 3 cards remain vertical image-on-top cards.
- Heart FM extraction now hard-stops at its post-article `More from Local News`, comments, weather, and recently-played regions once article prose has begun.
- Heart FM related-story link lists and images linked to other Heart FM articles are rejected.
- Extraction schema bumped to v9 so cached Heart FM stories are progressively cleaned/re-extracted.
