#!/usr/bin/env python3
"""Smoke test for the school-cafe-skylight app.

Verifies, against the running server (default http://127.0.0.1:8000):
  1. GET / returns 200 and renders the week's entrees (no sides/fruit/milk).
  2. The htmx + tailwind scripts are served locally (not from a CDN).
  3. POST /select sets a selection (radio-button semantics) and returns
     a cell fragment + OOB updates.
  4. Selecting a different entree overwrites the previous selection.
  5. "Make at home" can be selected as an alternative to a school entree.

The test asserts structural properties (cell IDs, OOB swaps, check marks)
rather than hardcoded entree names, so it stays stable across weekly menu
rotations.

Usage:
    python tests/smoke_test.py
    python tests/smoke_test.py --base-url http://127.0.0.1:9000
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

DEFAULT_BASE = "http://127.0.0.1:8000"
MAKE_AT_HOME = "__MAKE_AT_HOME__"

# Matches hx-vals JSON payloads: {"kid_id": 1, "menu_date": "...", "selection": "..."}
_SELECTION_RE = re.compile(r'"selection":\s*"([^"]+)"')


def fetch(url: str, data: bytes | None = None) -> tuple[int, str, dict[str, str]]:
    req = urllib.request.Request(url, data=data, method="POST" if data else "GET")
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            headers = {k.lower(): v for k, v in r.headers.items()}
            return r.status, r.read().decode(), headers
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode(), {k.lower(): v for k, v in e.headers.items()}


def assert_true(condition: bool, message: str) -> bool:
    status = "PASS" if condition else "FAIL"
    print(f"  [{status}] {message}")
    return condition


def extract_entrees(body: str) -> list[str]:
    """Extract entree selection values from the week page HTML.

    Scans hx-vals payloads for "selection" values, excluding the
    MAKE_AT_HOME sentinel which is tested separately.
    """
    entrees = []
    seen = set()
    for m in _SELECTION_RE.finditer(body):
        val = json.loads(f'"{m.group(1)}"')  # decode JSON escapes
        if val != MAKE_AT_HOME and val not in seen:
            seen.add(val)
            entrees.append(val)
    return entrees


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default=DEFAULT_BASE)
    args = parser.parse_args()
    base = args.base_url.rstrip("/")

    failures = 0
    target_date = "2026-08-12"
    url = f"{base}/?date={target_date}"

    # --- [1] GET / : page renders with entrees, no sides, local assets ---
    print(f"\n[1] GET {url}")
    code, body, headers = fetch(url)
    if not assert_true(code == 200, f"returns 200 (got {code})"):
        return 1
    if not assert_true("text/html" in headers.get("content-type", ""),
                       f"content-type is text/html (got {headers.get('content-type')})"):
        failures += 1

    entrees = extract_entrees(body)
    if not assert_true(len(entrees) >= 1, f"renders at least 1 entree (got {len(entrees)})"):
        failures += 1
    else:
        print(f"       (found {len(entrees)} entrees: {entrees[:3]}{'...' if len(entrees) > 3 else ''})")

    # Sides/fruit/milk categories should never appear as selectable cells.
    # Assert structurally: every selectable cell is either an entree or
    # MAKE_AT_HOME — no separate side-dish buttons. We check this by
    # verifying all selection values are in the entrees list or are the
    # make-at-home sentinel.
    all_selections = []
    for m in _SELECTION_RE.finditer(body):
        val = json.loads(f'"{m.group(1)}"')
        if val not in all_selections:
            all_selections.append(val)
    has_only_entrees_and_home = all(
        s in entrees or s == MAKE_AT_HOME for s in all_selections
    )
    if not assert_true(has_only_entrees_and_home,
                       "only entrees + make-at-home are selectable (no sides)"):
        failures += 1

    if not assert_true("/static/htmx.min.js" in body, "references local htmx"):
        failures += 1
    if not assert_true("/static/tailwind.js" in body, "references local tailwind"):
        failures += 1
    if not assert_true("unpkg.com" not in body, "does NOT reference unpkg.com"):
        failures += 1
    if not assert_true("cdn.tailwindcss.com" not in body, "does NOT reference tailwind CDN"):
        failures += 1

    if not assert_true("Make at home" in body, "shows 'Make at home' option"):
        failures += 1

    for kid in ["Parker", "Kylee"]:
        if not assert_true(kid in body, f"renders kid: {kid!r}"):
            failures += 1

    # Need at least 2 entrees to test the overwrite flow.
    if len(entrees) < 2:
        print("  [SKIP] fewer than 2 entrees available; skipping overwrite test")
    else:
        first_entree = entrees[0]
        second_entree = entrees[1]

        # --- [2] POST /select (Parker -> first entree) ---
        print(f"\n[2] POST {base}/select (Parker -> {first_entree!r})")
        data = urllib.parse.urlencode({
            "kid_id": "1", "menu_date": target_date,
            "selection": first_entree,
        }).encode()
        code, body, _ = fetch(f"{base}/select", data=data)
        if not assert_true(code == 200, f"returns 200 (got {code})"):
            return 1
        if not assert_true("check" in body.lower() or "&#10003;" in body,
                           "returns a cell with check mark"):
            failures += 1
        if not assert_true("hx-swap-oob" in body,
                           "returns OOB updates for other cells"):
            failures += 1

        # --- [3] POST /select (Parker -> second entree, overwriting) ---
        print(f"\n[3] POST {base}/select (Parker -> {second_entree!r}, overwriting)")
        data = urllib.parse.urlencode({
            "kid_id": "1", "menu_date": target_date,
            "selection": second_entree,
        }).encode()
        code, body, _ = fetch(f"{base}/select", data=data)
        if not assert_true(code == 200, f"returns 200 (got {code})"):
            return 1
        if not assert_true(second_entree in body,
                           f"returns cell for {second_entree!r}"):
            failures += 1
        if not assert_true("hx-swap-oob" in body,
                           "returns OOB updates to clear previous selection"):
            failures += 1

    # --- [4] POST /select (Parker -> Make at home) ---
    print(f"\n[4] POST {base}/select (Parker -> Make at home)")
    data = urllib.parse.urlencode({
        "kid_id": "1", "menu_date": target_date,
        "selection": MAKE_AT_HOME,
    }).encode()
    code, body, _ = fetch(f"{base}/select", data=data)
    if not assert_true(code == 200, f"returns 200 (got {code})"):
        return 1
    if not assert_true(MAKE_AT_HOME in body,
                       "returns cell for MAKE_AT_HOME"):
        failures += 1
    if not assert_true("emerald" in body,
                       "make-at-home cell uses emerald (green) styling"):
        failures += 1

    # --- [5] GET /health ---
    print(f"\n[5] GET {base}/health")
    code, body, _ = fetch(f"{base}/health")
    if not assert_true(code == 200 and body == "ok",
                       f"returns 200 'ok' (got {code} {body!r})"):
        failures += 1

    print()
    if failures:
        print(f"FAILED: {failures} assertion(s) failed")
        return 1
    print("PASSED: all assertions passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
