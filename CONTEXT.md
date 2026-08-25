# School Lunch Planning

This context describes how a family chooses school lunches and publishes those choices to its Skylight meal plan.

## Language

**Kid**:
A child whose school-lunch choice is managed by the planner.

**Selection**:
A Kid's chosen lunch outcome for one school date: a Menu entree or Make at Home.
_Avoid_: Pick, meal record

**Published Selection**:
A Selection whose Owned Skylight Sitting is confirmed to exist. A removed sitting or failed creation leaves the Selection unpublished.
_Avoid_: Sent Selection

**Planner Readback**:
The current, Display Text-resolved planner state for requested dates: stored
Selections, per-date totals and published counts, and recent activity history.
_Avoid_: Route response, refreshed page

**Owned Skylight Sitting**:
A Skylight Lunch entry managed by this planner for a Kid and date. Other family meal-plan entries are not owned by the planner.
_Avoid_: Existing sitting, calendar item

**Display Text**:
The text a human sees for a stored menu description: an active Display Override on the raw text, else the cased text, else an Override on the cased text. One rule, resolved in one place, so the entree a Kid picked and the Skylight recipe summary written for it cannot disagree.
_Avoid_: Formatted name, pretty text, title case

**Display Override**:
A permanent replacement a parent pins for one menu description. Stored under both the raw and the cased form of the description, so either spelling resolves.
_Avoid_: Alias, rename

**Meal-plan Publication**:
The one-way replacement of Owned Skylight Sittings for requested dates from a frozen snapshot of current Selections. Local Selections are authoritative, and each date is isolated from failures on other dates.
_Avoid_: Synchronization, send
