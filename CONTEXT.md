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

**Owned Skylight Sitting**:
A Skylight Lunch entry managed by this planner for a Kid and date. Other family meal-plan entries are not owned by the planner.
_Avoid_: Existing sitting, calendar item

**Meal-plan Publication**:
The one-way replacement of Owned Skylight Sittings for requested dates from a frozen snapshot of current Selections. Local Selections are authoritative, and each date is isolated from failures on other dates.
_Avoid_: Synchronization, send
