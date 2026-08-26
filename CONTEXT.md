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

**Month Planner Readback**:
The current read-only monthly planning view: calendar dates, each Kid's Selection
state summarized without entree names, and known School Menu availability. A
Selection remains visible when menu availability is unknown. Choosing a date opens its Week
Planner Readback.
_Avoid_: Month payload, calendar data, monthly dashboard

**Monthly Selection Summary**:
The compact per-Kid Selection and day-completion information shown for a date in
a Month Planner Readback. Make at Home is a completed Selection; publication is
a separate status.
_Avoid_: Calendar badge, lunch icon, daily progress

**School Menu Availability**:
The planner's known status of whether a date has School Menu choices. Weekends
are non-school; a weekday without known choices is menu unavailable, not
necessarily a school holiday.
_Avoid_: Holiday status, no-school status

**School Date**:
A calendar date interpreted in the school's America/Chicago time zone.
_Avoid_: Browser date, device date

**Menu Catalog Freshness**:
The most recent successful Menu Catalog Refresh time shown with a Month Planner
Readback to qualify the current availability information.
_Avoid_: Calendar sync time, menu date

**Week Menu**:
The School Menu Source choices presented for one planning week after Display Text is resolved.
_Avoid_: Menu response, fetched week

**School Menu Source**:
The school-published lunch choices from which the planner obtains its Week Menu and Menu Catalog items.
_Avoid_: Remote menu, fetched menu

**Menu Catalog**:
The source-unique set of Menu items, their Display Text, and the recent
history of Menu refresh attempts used to administer the planner.
_Avoid_: Admin response, cache table

**Menu Catalog Refresh**:
One attempt to retrieve upcoming School Menu Source choices and record them in the Menu Catalog.
_Avoid_: Menu sync, background job

**Planner Interaction State**:
The current local planning interaction: an in-progress Selection Change or
Meal-plan Publication and its retained outcome for the displayed week.
_Avoid_: Page state, hook state

**Publication Outcome**:
The typed Status and Phase vocabulary produced by Meal-plan Publication and
projected once into the stable planner response vocabulary.
_Avoid_: Send result string, response normalization

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
