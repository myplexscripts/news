# London News story/card interaction cleanup

Replace these files:

- `src/pages/index.astro`
- `src/pages/latest/index.astro`
- `src/pages/search/index.astro`
- `src/pages/story/[id].astro`
- `src/styles/global.css`

## Changes

- Home, Latest, Search, and Keep Reading story cards are now one full clickable link target.
- Keep Reading cards now show publisher, publish date/time, and estimated reading time.
- Removed the `← London News` link from story pages.
- Removed the coloured article category/read-time row above story headlines.
- Removed the duplicate topic pills from below the headline.
- Category + story-topic pills now live under the source card in the article sidebar.
- `Full story` is always excluded from the pill list, with case-insensitive tag deduplication.
- Reading time now lives in the article sidebar.
- Desktop article source/details stack is sticky at 24px from the viewport top and follows the reader while scrolling.
- Mobile article sidebar remains in normal document flow.
- Existing publisher logo image overlays remain outside the photo zoom transform.
