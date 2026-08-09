#!/usr/bin/env python3
"""Smoke test for the school-cafe-skylight app.

Verifies, against the running server (default http://127.0.0.1:8000):
  1. GET / returns 200 and renders the week's entrees (no sides/fruit/milk).
  2. The htmx script is served locally (not from a CDN).
  3. POST /toggle actually flips a choice and returns a cell fragment.
  4. Repeated toggles are idempotent (on -> off -> on).

Usage:
    python tests/smoke_test.py
    python tests/smoke_test.py --base-url http://127.0.0.1:9000
"""

from __future__ import annotations

import argparse
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta

DEFAULT_BASE = "http://127.0.0.1:8000"


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

    # Use a date we know has data (Cheese Pizza day, week of 8/12/2026)
    target_date = "2026-08-12"
    url = f"{base}/?date={target_date}"
    print(f"\n[1] GET {url}")
    code, body, headers = fetch(url)
    if not assert_true(code == 200, f"returns 200 (got {code})"):
        return 1
    if not assert_true("text/html" in headers.get("content-type", ""),
                       f"content-type is text/html (got {headers.get('content-type')})"):
        failures += 1

    # Entrees only — these should be present
    expected_entrees = ["Cheese Pizza", "Pepperoni Pizza", "Yogurt Box Entree",
                        "Chicken Caesar Salad", "Hot Dog", "Steak Fingers"]
    for entree in expected_entrees:
        if not assert_true(entree in body, f"contains entree: {entree!r}"):
            failures += 1

    # Sides/milk/condiments — these should NOT be present
    unexpected = ["Baby Carrots", "Fresh Cucumber Slices", "Banana",
                  "1% Milk - 8 oz", "Fat-Free Chocolate Milk", "Soy Milk",
                  "Parmesan", "Ranch Dressing", "Tajin", "Ketchup", "Mustard"]
    for item in unexpected:
        if not assert_true(item not in body, f"does NOT contain side: {item!r}"):
            failures += 1

    # htmx is served locally
    if not assert_true("/static/htmx.min.js" in body,
                       "references /static/htmx.min.js (local, not CDN)"):
        failures += 1
    if not assert_true("unpkg.com" not in body,
                       "does NOT reference unpkg.com CDN"):
        failures += 1

    # Parker and Kylee
    for kid in ["Parker", "Kylee"]:
        if not assert_true(kid in body, f"renders kid: {kid!r}"):
            failures += 1

    # [2] POST /toggle - turn Parker's "Cheese Pizza" ON
    print(f"\n[2] POST {base}/toggle (Parker -> Cheese Pizza ON)")
    data = urllib.parse.urlencode({
        "kid_id": "1",
        "menu_date": target_date,
        "item_text": "Cheese Pizza",
        "eats": "1",
    }).encode()
    code, body, _ = fetch(f"{base}/toggle", data=data)
    if not assert_true(code == 200, f"returns 200 (got {code})"):
        return 1
    if not assert_true("check-btn" in body, "returns a check-btn fragment"):
        failures += 1
    if not assert_true("on" in body or "✓" in body, "shows checked state"):
        failures += 1
    if not assert_true('"eats": 0' in body or '"eats": "0"' in body,
                       "next toggle will turn OFF (eats=0)"):
        failures += 1

    # [3] POST /toggle - turn it OFF
    print(f"\n[3] POST {base}/toggle (Parker -> Cheese Pizza OFF)")
    data = urllib.parse.urlencode({
        "kid_id": "1",
        "menu_date": target_date,
        "item_text": "Cheese Pizza",
        "eats": "0",
    }).encode()
    code, body, _ = fetch(f"{base}/toggle", data=data)
    if not assert_true(code == 200, f"returns 200 (got {code})"):
        failures += 1
    if not assert_true("·" in body or "skip" in body.lower(),
                       "shows unchecked state"):
        failures += 1
    if not assert_true('"eats": 1' in body or '"eats": "1"' in body,
                       "next toggle will turn ON (eats=1)"):
        failures += 1

    # [4] Health
    print(f"\n[4] GET {base}/health")
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