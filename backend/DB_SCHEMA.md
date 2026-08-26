# SQLite Database Schema — school-cafe-skylight

Reference for reviewing the `app.db` setup. The schema is created by
`init_db()` in `fastapi_app.py` (core tables) and `_init_menu_tables()`
in `menu_sync.py` (menu cache + sync log + overrides). Both are
idempotent (`CREATE TABLE IF NOT EXISTS`), so the DB self-migrates on
startup.

- **File:** `app.db` (SQLite, WAL mode — set once in `init_db`)
- **Location:** project root, bind-mounted into the container
- **Not committed:** `app.db`, `app.db-shm`, `app.db-wal` are gitignored
- **Concurrency:** single-user app; the three-phase send pattern never
  holds a write lock across a network call

## Tables

### kids

One row per child. Prefixes are backfilled in `init_db` so every kid
has one (e.g. `"P-"`, `"K-"`).

| Column | Type | Notes |
|--------|------|-------|
| `id` | INTEGER PK AUTOINCREMENT | |
| `name` | TEXT NOT NULL UNIQUE | e.g. `"Parker"` |
| `color` | TEXT NOT NULL | hex color for the dashboard cells |
| `prefix` | TEXT NOT NULL DEFAULT `''` | e.g. `"P-"`; used in Skylight recipe titles |

Seeded from `DEFAULT_KIDS` in `fastapi_app.py` via `INSERT OR IGNORE`.

### selections

One row per (kid, day). `selection` is either an entree description
(proper-cased) or the `MAKE_AT_HOME` sentinel (`"__MAKE_AT_HOME__"`).

| Column | Type | Notes |
|--------|------|-------|
| `kid_id` | INTEGER NOT NULL | FK → `kids.id` ON DELETE CASCADE |
| `menu_date` | TEXT NOT NULL | ISO `YYYY-MM-DD` |
| `selection` | TEXT NOT NULL | entree text or `MAKE_AT_HOME` |
| `sent_at` | TEXT NULL | ISO timestamp; set on every send, even make-at-home |
| `sent_sitting_id` | TEXT NULL | Skylight sitting ID; NULL for make-at-home |

**Semantics (important):**
- `sent_at` set = "this kid was included in a send" (even make-at-home)
- `sent_sitting_id` set = "a real Skylight sitting was created"
- A new selection clears both (`/select` route)

**Index:** `idx_selections_menu_date` on `menu_date` (the week view
filters by date alone; the composite PK can't serve that).

### selection_history

Append-only activity log shown on the dashboard. Pruned to
`HISTORY_RETENTION` (500) rows on every insert.

| Column | Type | Notes |
|--------|------|-------|
| `id` | INTEGER PK AUTOINCREMENT | |
| `kid_name` | TEXT NOT NULL | denormalized kid name (not FK — survives kid deletion) |
| `menu_date` | TEXT NOT NULL | ISO `YYYY-MM-DD` |
| `selection` | TEXT NOT NULL | entree text or `MAKE_AT_HOME` |
| `action` | TEXT NOT NULL | `"Selected"` or `"Sent to Skylight"` |
| `created_at` | TEXT NOT NULL | ISO timestamp |

### menu_items

Cached entrees from the automated Sunday SchoolCafé sync. Only entrees are
stored — the admin page lists exactly what's pickable.

| Column | Type | Notes |
|--------|------|-------|
| `menu_date` | TEXT NOT NULL | ISO `YYYY-MM-DD` |
| `description` | TEXT NOT NULL | proper-cased entree text |
| `category` | TEXT NOT NULL DEFAULT `''` | e.g. `"LUNCH ENTREE"` |
| `week_start` | TEXT NOT NULL | ISO date of the Monday of the week |
| `fetched_at` | TEXT NOT NULL | ISO timestamp of the sync |

**PK:** `(menu_date, description)` — one row per (day, entree).
**Index:** `idx_menu_items_week_start` on `week_start` (admin page
groups by week).

### menu_sync_log

One row per sync attempt (success or failure). Backs the admin page's
sync history and the automated scheduler's duplicate-attempt guard.

| Column | Type | Notes |
|--------|------|-------|
| `id` | INTEGER PK AUTOINCREMENT | |
| `attempted_at` | TEXT NOT NULL | ISO timestamp |
| `succeeded` | INTEGER NOT NULL | 1 = success, 0 = failure |
| `weeks_fetched` | INTEGER NOT NULL DEFAULT 0 | 4 on success |
| `items_stored` | INTEGER NOT NULL DEFAULT 0 | total entrees stored |
| `weeks_covered` | TEXT NOT NULL DEFAULT `'[]'` | JSON array of week-start ISO dates |
| `error` | TEXT NULL | error message on failure |

**Index:** `idx_menu_sync_log_attempted_at` on `attempted_at`.

### menu_item_overrides

Persistent display-text lookup table. Maps an original description to
the user's chosen display string. **No date column** — an override
applies to every occurrence of the item, past and future, until
cleared.

| Column | Type | Notes |
|--------|------|-------|
| `original_description` | TEXT PK | the item as stored in `menu_items` |
| `replacement_description` | TEXT NOT NULL | what the user wants displayed |
| `created_at` | TEXT NOT NULL | ISO timestamp |
| `updated_at` | TEXT NOT NULL | ISO timestamp |

**Application points:**
- Menu Catalog: `MenuCatalogReadback` adds `display_description`.
- Week Menu: `WeekMenu.read` resolves current Display Text on both cache-hit
  and fresh-source paths.

## Relationships

```
kids 1 ──── * selections (kid_id, ON DELETE CASCADE)
selections * ──── 1 kids

menu_items (menu_date, description)  ←  menu_item_overrides.original_description
                                        (loose reference, no FK)

selection_history.kid_name  ←  kids.name (denormalized, no FK)
```

## Conventions

- **Dates:** stored as ISO `YYYY-MM-DD` strings; timestamps as
  `datetime.now().isoformat(timespec="seconds")`.
- **Sentinel:** `MAKE_AT_HOME = "__MAKE_AT_HOME__"` (module constant in
  `fastapi_app.py`, exposed to templates).
- **WAL mode:** set once in `init_db` (`PRAGMA journal_mode = WAL`).
- **Migrations:** additive only — `CREATE TABLE IF NOT EXISTS` plus
  `PRAGMA table_info` checks (see the `kids.prefix` migration). No
  destructive ALTERs.
- **Corruption recovery:** if `app.db` is ever malformed (e.g. from
  concurrent host+container access), the schema above is the source of
  truth for rebuilding. Readable tables can be dumped with
  `PRAGMA writable_schema = ON` and re-inserted into a fresh DB.

## Verification

```bash
# Integrity check
python3 -c "import sqlite3; c=sqlite3.connect('app.db'); print(c.execute('PRAGMA integrity_check').fetchone())"

# Dump full schema
python3 -c "
import sqlite3
c = sqlite3.connect('app.db')
for r in c.execute(\"SELECT name, sql FROM sqlite_master WHERE type='table'\"):
    print(r[1])
"

# Row counts per table
python3 -c "
import sqlite3
c = sqlite3.connect('app.db')
for t in ['kids','selections','selection_history','menu_items','menu_sync_log','menu_item_overrides']:
    print(t, c.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0])
"
```
