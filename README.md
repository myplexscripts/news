# London News card layout repair

Replace `src/pages/index.astro` with the included file.

Fixes:
- The first three visible chronological stories are always `card-featured`.
- Every visible story after the first three is always `card-standard`.
- Source health / `hero_eligible` metadata no longer changes card geometry.
- Filtering by section, search, hidden sources, or source preferences recalculates the first three visible cards deterministically.
- Existing publisher-logo overlays and image hover behaviour are unchanged.
