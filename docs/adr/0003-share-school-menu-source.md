---
status: accepted
---

# Share one School Menu Source seam

Week Menu and Menu Catalog Refresh remain separate deep modules because interactive cached Display Text and catalog persistence have different behavior. Both cross one School Menu Source seam with production and in-memory adapters, while cache, assembly, scheduling, persistence, and outcome projection stay inside their owning module implementations; this avoids both an all-purpose acquisition module and parallel SchoolCafe call paths.
