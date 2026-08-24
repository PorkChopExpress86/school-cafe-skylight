---
status: accepted
---

# One seam for Display Text

Resolving a stored menu description to its Display Text lives in one deep
`MenuItemDisplay` module. The rule previously existed in four call paths under
three variants — SchoolCafé ingest cased without consulting overrides, the two
`menu_service` helpers applied overrides without casing, and
`db.resolve_display_text` did both — so the entree a Kid picked and the Skylight
recipe summary written for it could resolve differently. That mismatch caused
the case-sensitive recipe lookup bug fixed in ad97f2d.

`display()` is the whole rule and the interface every caller crosses; `cased()`
exposes the casing pass alone because the Display Override table stores a
replacement under both the raw and the cased key.

`MenuItemDisplay` is pure: no adapter, no cache, no subprocess. Measured
against the real menu (24 items), the previous per-item heuristic for
consulting a language model fired for every single one — its "three
consecutive uppercase letters" test matches any word of three or more letters
in text that is entirely ALL CAPS, so it was never the exception path its
docstring claimed. Consulting a model on `HOT DOG` to improve on
`str.capitalize()` was pure cost: a blocking subprocess with a 10-second
timeout, once per item per sync.

The language-model consultation now lives in `menu_casing.py`, whose one
caller is the admin bulk re-casing pass (`POST /api/admin/llm-case-all`). It
asks for every item, not a heuristic subset, and pins results as Display
Overrides for a parent to review or correct. The Display Override table is the
intended correction mechanism — pinning in two clicks is cheaper than a
smarter per-item guess — so the simple rules alone are expected to be good
enough for ingest, and the override table is the signal for what to add to
`ACRONYMS` or `TITLE_CASE_EXCEPTIONS` if that stops being true.

`school_menu` keeps only the SchoolCafé fetch and parse, which removes `db`'s
mid-module import of it. Ingest-time casing rules are unchanged; only the
model consultation moved.
