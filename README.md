# Premium Light/Dark Theme Patch

Adds a persistent light/dark theme toggle to the Organic Chemistry site without changing FastAPI routes, database code, or Supabase configuration.

Files changed:
- `app/templates/base.html`
- `app/static/styles.css`
- `app/static/app.js`

The visitor's preference is stored in browser localStorage under `oc-theme` and applies across pages.
