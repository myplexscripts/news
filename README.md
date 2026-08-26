# London News cleanup update

Replace the matching files in your repository.

Changes in this pass:

- Restores white/black page canvas. Grey is reserved for cards.
- Removes the duplicate Sources button from the section controls.
- Makes the section controls normal page content instead of a second sticky header.
- Keeps the single desktop Sources icon in the main header and the Sources tab in the mobile bottom bar.
- First three visible stories are consistent full-width cards on desktop.
- Remaining stories use one consistent two-column card geometry.
- All card media uses flush 1:1 frames with focal-point cropping.
- Hover no longer moves cards. Only the image gently zooms inside its crop.
- Article body and source rail remain flat, not carded.
- CTV discovery now uses CTV's dedicated London RSS feed while linking to the current CTV London site.
- Adds a CTV embedded-JSON article-body fallback for pages whose visible HTML is only a hydration shell.
- Bumps extraction schema to 6 so cached stories are progressively re-extracted.
- Adds HTTP retries and raises the request timeout to reduce transient CBC/source failures.
