# London News: Scoop extraction + mobile hero fix

Replace these two files in the repository:

- `src/styles/global.css`
- `scripts/fetch_news.py`

## Mobile layout

- The first three homepage stories are vertical hero cards on screens up to 760px.
- Hero image is on top, 1:1, flush to the card, with `20px 20px 0 0` radius.
- Hero copy sits below the image.
- Stories after the first three remain compact horizontal cards with a square image on the left.
- At 390px and below, only the compact card image shrinks. Hero cards stay vertical.

## Scoop extraction v8

- Extraction schema bumped to 8 so cached articles are reconsidered.
- Backfill increased to 24 cached articles per refresh while this migration settles.
- Global News now uses a strict extraction path:
  1. visible article DOM
  2. publisher JSON-LD `articleBody`
  3. partial trusted body if necessary
  4. never whole-page Trafilatura as a Global fallback
- Removes video/player/playlist blocks from Global articles.
- Removes Global newsletter, social, message-bar, related-story, read-more, sponsored and recirculation modules.
- Stops Global extraction at end-of-article markers such as `Stick to the Facts`, `Sponsored content`, and `Report an Error`.
- Filters Global's social-distribution banner and daily-news signup text.
- Hidden DOM nodes (`hidden`, `aria-hidden=true`, `display:none`, `visibility:hidden`) are ignored.
- London Free Press newsletter promotion text such as `Exclusive articles from...` is filtered while normal interview Q&A remains.

Scoop prefers a shorter trustworthy article over a longer extraction polluted by unrelated page furniture.
