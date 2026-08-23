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
exposes the casing pass alone because the override table stores a replacement
under both the raw and the cased key. The language-model consultation sits
behind its own `CasingAdapter` seam with two adapters — `AgyCasingAdapter` in
production and `NoCasing` offline — which replaces the previous
`PYTEST_CURRENT_TEST` check inside the production code.

`school_menu` keeps only the SchoolCafé fetch and parse, which removes `db`'s
mid-module import of it. Ingest-time casing is deliberately unchanged: menu
items are already stored cased, and re-deriving them would rewrite existing
rows for no gain.
