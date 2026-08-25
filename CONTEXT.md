# School Lunch Planning

This context describes how a family chooses school lunches and publishes those choices to its Skylight meal plan.

## Language

**Kid**:
A child whose school-lunch choice is managed by the planner.

**Selection**:
A Kid's chosen lunch outcome for one school date: a Menu entree or Make at Home.
_Avoid_: Pick, meal record

**Selection Change**:
The replacement of one Kid's Selection for one school date. A Selection Change
supersedes any previous Published Selection for that Kid and date.
_Avoid_: Selection update, choice save

**Published Selection**:
A Selection whose Owned Skylight Sitting is confirmed to exist. A removed sitting or failed creation leaves the Selection unpublished.
_Avoid_: Sent Selection

**Selection Publication State**:
The planner-visible condition of a Selection after Meal-plan Publication:
Pending, Published with an Owned Skylight Sitting, or Make at Home included
without an Owned Skylight Sitting.
_Avoid_: Sent flag, sitting status

**Planner Readback**:
The current, Display Text-resolved planner state for requested dates: stored
Selections, per-date totals and published counts, and recent activity history.
_Avoid_: Route response, refreshed page

**Week Planner Readback**:
The current weekly planning view: the displayed Menu, Kids, Planner Readback,
and the current availability of school-menu and Skylight configuration.
_Avoid_: Week payload, dashboard data

**Menu Catalog**:
The source-unique set of Menu items, their Display Text, and the recent
history of Menu refresh attempts used to administer the planner.
_Avoid_: Admin response, cache table

**Planner Interaction State**:
The current local planning interaction: an in-progress Selection Change or
Meal-plan Publication and its retained outcome for the displayed week.
_Avoid_: Page state, hook state

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
