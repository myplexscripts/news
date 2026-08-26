# London News mobile width and count fix

Replace these files in the repository:

- `src/pages/index.astro`
- `src/pages/latest/index.astro`
- `src/styles/global.css`

Changes:
- mobile date section headers and story cards share one exact full-width feed gutter
- featured mobile cards stretch to the full feed width
- removes visible story totals from the home masthead
- removes story totals from Today / Yesterday / Two Days Ago / Earlier headers
- removes the visible total from Latest while retaining a screen-reader status message
