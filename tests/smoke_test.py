#!/usr/bin/env python3
"""Smoke test for the school-cafe-skylight app.

Verifies, against the running server (default http://127.0.0.1:8000):
  1. GET / returns 200 and renders the week's entrees (no sides/fruit/milk).
  2. The htmx + tailwind scripts are served locally (not from a CDN).
  3. POST /select sets a selection (radio-button semantics) and returns
     a cell fragment + OOB updates.
  4. Selecting a different entree overwrites the previous selection.
  5. "Make at home" can be selected as an alternative to a school entree.

Usage:
    python tests/smoke_test.py
    python tests/smoke_test.py --base-url http://127.0.0.1:9000
"""

from __future__ import annotations

import argparse
import sys
import urllib.error
import urllib.parse
import urllib.request

DEFAULT_BASE = "http://127.0.0.1:8000"
MAKE_AT_HOME = "__MAKE_AT_HOME__"


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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default=DEFAULT_BASE)
    args = parser.parse_args()
    base = args.base_url.rstrip("/")

    failures = 0
    target_date = "2026-08-12"
    url = f"{base}/?date={target_date}"

    print(f"\n[1] GET {url}")
    code, body, headers = fetch(url)
    if not assert_true(code == 200, f"returns 200 (got {code})"):
        return 1
    if not assert_true("text/html" in headers.get("content-type", ""),
                       f"content-type is text/html (got {headers.get('content-type')})"):
        failures += 1

    expected_entrees = ["Cheese Pizza", "Pepperoni Pizza", "Yogurt Box Entree",
                        "Chicken Caesar Salad", "Hot Dog", "Steak Fingers"]
    for entree in expected_entrees:
        if not assert_true(entree in body, f"contains entree: {entree!r}"):
            failures += 1

    unexpected = ["Baby Carrots", "1% Milk - 8 oz", "Soy Milk", "Parmesan", "Ranch Dressing"]
    for item in unexpected:
        if not assert_true(item not in body, f"does NOT contain side: {item!r}"):
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

    print(f"\n[2] POST {base}/select (Parker -> Cheese Pizza)")
    data = urllib.parse.urlencode({
        "kid_id": "1", "menu_date": target_date,
        "selection": "Cheese Pizza",
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

    print(f"\n[3] POST {base}/select (Parker -> Pepperoni Pizza, overwriting)")
    data = urllib.parse.urlencode({
        "kid_id": "1", "menu_date": target_date,
        "selection": "Pepperoni Pizza",
    }).encode()
    code, body, _ = fetch(f"{base}/select", data=data)
    if not assert_true(code == 200, f"returns 200 (got {code})"):
        failures += 1
    if not assert_true("Pepperoni Pizza" in body,
                       "returns cell for Pepperoni Pizza"):
        failures += 1
    if not assert_true("hx-swap-oob" in body,
                       "returns OOB updates to clear Cheese Pizza"):
        failures += 1

    print(f"\n[4] POST {base}/select (Parker -> Make at home)")
    data = urllib.parse.urlencode({
        "kid_id": "1", "menu_date": target_date,
        "selection": MAKE_AT_HOME,
    }).encode()
    code, body, _ = fetch(f"{base}/select", data=data)
    if not assert_true(code == 200, f"returns 200 (got {code})"):
        failures += 1
    if not assert_true(MAKE_AT_HOME in body,
                       "returns cell for MAKE_AT_HOME"):
        failures += 1
    if not assert_true("emerald" in body,
                       "make-at-home cell uses emerald (green) styling"):
        failures += 1

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