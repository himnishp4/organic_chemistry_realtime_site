# Liquid Glass Sliding Navigation Patch

This patch upgrades the desktop primary navigation into a sliding frosted-glass tab bar while retaining the existing mobile hamburger menu.

Files changed:
- `app/templates/base.html`
- `app/static/styles.css`
- `app/static/app.js`

The sliding capsule tracks the current route, glides to hovered/focused destinations, returns to the active page, supports light/dark themes, keyboard focus, reduced-motion preferences, and mobile fallbacks.
