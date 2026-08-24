---
status: accepted
---

# Deepen Meal-plan Publication behind one seam

Day and week publication will use one deep `MealPlanPublisher` module because they perform the same safety-critical replacement workflow and must not drift into separate implementations. A publication uses a frozen Selection snapshot, treats local Selections as authoritative, isolates failures by date, rejects overlapping dates, gates creation on successful discovery and removal, recognizes ownership through stored identifiers or exact Kid prefixes rather than loose name matching, and returns structured date and Kid outcomes while preserving existing route responses. The real and in-memory Skylight adapters share an explicit seam, while SQLite remains inside the implementation and is tested through temporary databases; this keeps the external interface small without introducing a hypothetical persistence seam.
