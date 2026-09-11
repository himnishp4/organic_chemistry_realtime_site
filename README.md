# Dark icon contrast polish

Fixes chapter-number tiles such as `01` / `02` becoming nearly white in dark mode.

Changes:
- premium dark emerald chapter number badges
- champagne-gold numbering
- improved type-icon contrast
- safe dark treatment for related compact icon tiles
- no backend, database, storage, or API changes

The patch adds a small stylesheet loaded after the main site CSS so it does not overwrite the rest of the current premium UI work.
