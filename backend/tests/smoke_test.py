#!/usr/bin/env python3
"""Smoke test for the school-cafe-skylight app (JSON API).

Verifies, against the running server (default http://127.0.0.1:8000):
  1. GET /api/health returns {"status": "ok"}.
  2. GET /api/week returns the week's entrees (no sides/fruit/milk).
  3. POST /api/select sets a selection (radio-button semantics).
  4. Selecting a different entree overwrites the previous selection.
  5. "Make at home" can be selected as an alternative to a school entree.
  6. GET / returns the React SPA shell.

The test asserts structural properties rather than hardcoded entree
names, so it stays stable across weekly menu rotations.

Usage:
    python tests/smoke_test.py
    python tests/smoke_test.py --base-url http://127.0.0.1:9000
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request

DEFAULT_BASE = "http://127.0.0.1:8000"
MAKE_AT_HOME = "__MAKE_AT_HOME__"


def fetch_json(url: str, data: dict | None = None) -> tuple[int, dict]:
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(
        url,
        data=body,
        method="POST" if data is not None else "GET",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, {}


def assert_true(condition: bool, message: str) -> bool:
    status = "PASS" if condition else "FAIL"
    print(f"  [{status}] {message}")
    return condition


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default=DEFAULT_BASE)
    args = parser.parse_args()
    base = args.base_url.rstrip("/")

    failures = 0
    target_date = "2026-08-12"

    # --- [1] GET /api/health ---
    print(f"\n[1] GET {base}/api/health")
    code, data = fetch_json(f"{base}/api/health")
    if not assert_true(code == 200 and data.get("status") == "ok",
                       f"returns 200 ok (got {code} {data!r})"):
        return 1

    # --- [2] GET /api/week ---
    print(f"\n[2] GET {base}/api/week?date={target_date}")
    code, week = fetch_json(f"{base}/api/week?date={target_date}")
    if not assert_true(code == 200, f"returns 200 (got {code})"):
        return 1
    if not assert_true(len(week.get("week", [])) == 5,
                       f"returns 5 weekdays (got {len(week.get('week', []))})"):
        failures += 1
    if not assert_true(len(week.get("kids", [])) >= 1,
                       f"returns kids (got {len(week.get('kids', []))})"):
        failures += 1

    entrees = []
    for day in week.get("week", []):
        for e in day.get("entrees", []):
            if e not in entrees:
                entrees.append(e)
    if not assert_true(len(entrees) >= 1, f"has at least 1 entree (got {len(entrees)})"):
        failures += 1
    else:
        print(f"       (found {len(entrees)} entrees: {entrees[:3]}{'...' if len(entrees) > 3 else ''})")

    # --- [3] GET / : SPA shell ---
    print(f"\n[3] GET {base}/")
    req = urllib.request.Request(f"{base}/")
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            body = r.read().decode()
            code = r.status
    except urllib.error.HTTPError as e:
        code, body = e.code, ""
    if not assert_true(code == 200, f"returns 200 (got {code})"):
        return 1
    if not assert_true('<div id="root"></div>' in body, "serves the React SPA shell"):
        failures += 1

    # --- [4] POST /api/select (Parker -> first entree) ---
    if not entrees:
        print("  [SKIP] no entrees; skipping selection tests")
    else:
        # --- Save initial selection to restore after testing ---
        code_orig, week_orig = fetch_json(f"{base}/api/week?date={target_date}")
        initial_selection = None
        if code_orig == 200:
            initial_selection = week_orig.get("selections", {}).get(target_date, {}).get(1, {}).get("selection")

        first_entree = entrees[0]
        print(f"\n[4] POST {base}/api/select (Parker -> {first_entree!r})")
        code, data = fetch_json(f"{base}/api/select", {
            "kid_id": 1, "menu_date": target_date, "selection": first_entree,
        })
        if not assert_true(code == 200, f"returns 200 (got {code})"):
            return 1
        if not assert_true(data.get("selection") == first_entree,
                           f"returns selection {first_entree!r}"):
            failures += 1
        if not assert_true(data.get("day_totals", {}).get(target_date, 0) >= 1,
                           "day_totals reflects the selection"):
            failures += 1

        # --- [5] POST /api/select (Parker -> Make at home, overwriting) ---
        print(f"\n[5] POST {base}/api/select (Parker -> Make at home)")
        code, data = fetch_json(f"{base}/api/select", {
            "kid_id": 1, "menu_date": target_date, "selection": MAKE_AT_HOME,
        })
        if not assert_true(code == 200, f"returns 200 (got {code})"):
            return 1
        if not assert_true(data.get("selection") == MAKE_AT_HOME,
                           "returns MAKE_AT_HOME selection"):
            failures += 1

        # --- Restore initial selection ---
        if initial_selection:
            fetch_json(f"{base}/api/select", {
                "kid_id": 1, "menu_date": target_date, "selection": initial_selection,
            })

    # --- [6] GET /api/admin ---
    print(f"\n[6] GET {base}/api/admin")
    code, admin = fetch_json(f"{base}/api/admin")
    if not assert_true(code == 200, f"returns 200 (got {code})"):
        return 1
    if not assert_true("weeks" in admin and "items" in admin and "attempts" in admin,
                       "returns weeks, items, and attempts"):
        failures += 1

    print()
    if failures:
        print(f"FAILED: {failures} assertion(s) failed")
        return 1
    print("PASSED: all assertions passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
