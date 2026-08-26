# London News local logo overlay update

Apply this on top of the latest product reliability/enrichment build.

## Changes
- Removes circular initials/avatar treatment from Sources cards, story source attribution, and admin source rows.
- Uses publisher logo assets from `images/logos/`.
- Moves publisher logos onto the top-left of news-card images.
- Logo overlay is a separate layer and does not zoom when the article image zooms on hover.
- Applies the same overlay treatment to Home, Latest, Search, and related-story cards.
- Source name remains visible as text in the card body.

## Expected existing logo files
- `images/logos/global.png`
- `images/logos/cbc.png`
- `images/logos/lfp.png`
- `images/logos/ctv.png`
- `images/logos/1069thex.png`
- `images/logos/CoL.png`
- `images/logos/lps.png`
- `images/logos/lfd.png`
- `images/logos/heartfm.png`
- `images/logos/google.png`

If your Heart FM or Google logo uses a different filename, change it once in `src/lib/sourceLogos.ts` and `scripts/sources.py`.
