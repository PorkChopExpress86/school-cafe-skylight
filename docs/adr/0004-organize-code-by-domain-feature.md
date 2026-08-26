---
status: accepted
---

# Organize code by domain feature

The application will remain a single-family modular monolith and organize backend and frontend code primarily by the established domain features: Planner, Meal-plan Publication, Menu Catalog, and School Menu. Each feature keeps its workflow, models, adapters, and feature-owned persistence close together, while only application composition, SQLite connection and schema mechanics, and other genuinely shared infrastructure remain central; this preserves the existing deep modules without introducing speculative multi-tenant, database, or provider abstractions.

The Python runtime will use the explicit `lunch_planner` package, backend tests will mirror its feature structure, and frontend code will use matching `planner` and `menu-catalog` feature directories. The restructure is behavior-preserving: HTTP contracts, database schema, scheduling policy, UI behavior, and accepted domain invariants do not change as part of moving the files.
