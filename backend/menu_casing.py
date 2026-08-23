"""Bulk Display Override generation via a language model.

The per-item read and ingest paths never shell out — see menu_item_display.py.
This module is the one place that talks to `agy`: the admin bulk re-casing
pass, which asks for every unique menu item and pins the result as a Display
Override so a parent can review, correct, or clear any of them afterward.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Protocol

DEFAULT_CASING_MODEL = "gemini-3.6-flash-low"


class CasingAdapter(Protocol):
    """Seam for consulting something smarter than the simple casing rules."""

    def suggest(self, text: str) -> str | None:
        """Return a better-cased form of `text`, or None to fall back."""
        ...


class AgyCasingAdapter:
    """Consult the `agy` CLI for an item's display casing.

    Returns None — so the caller keeps the existing text — when agy is not
    installed, exits non-zero, times out, or answers implausibly.
    """

    def __init__(self, model: str = DEFAULT_CASING_MODEL, timeout: int = 10) -> None:
        self._model = model
        self._timeout = timeout

    def _binary(self) -> str | None:
        found = shutil.which("agy")
        if found:
            return found
        fallback = os.path.expanduser("~/.local/bin/agy")
        return fallback if os.path.exists(fallback) else None

    def suggest(self, text: str) -> str | None:
        agy_bin = self._binary()
        if agy_bin is None:
            return None
        prompt = (
            "Convert this ALL-CAPS school menu item description to Title Case "
            "food-service display format (return ONLY the converted string, "
            "no extra punctuation or quotes):\n"
            f"{text}"
        )
        cmd = [agy_bin, "-p", prompt, "--model", self._model, "--disable-slash-commands"]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=self._timeout)
        except Exception:  # noqa: BLE001
            return None
        if res.returncode != 0:
            return None
        cleaned = res.stdout.strip().strip('"\'')
        # An answer far longer than the source is a refusal or a preamble.
        if cleaned and len(cleaned) < len(text) * 2:
            return cleaned
        return None


def pin_display_overrides_for_all_items(
    db_path: Path | None = None, casing: CasingAdapter | None = None
) -> dict:
    """Put every unique menu item to the casing adapter and pin the answers.

    Unlike the per-item rule, this asks for every item rather than only the
    ones the heuristic flags, so a parent can re-case the whole library at
    once and correct anything wrong via the Display Override table.
    """
    from db import fetch_unique_menu_items, set_menu_override

    adapter = casing if casing is not None else AgyCasingAdapter()
    unique_items = fetch_unique_menu_items(db_path)
    updated = 0
    for item in unique_items:
        orig = item["description"]
        cased = adapter.suggest(orig)
        if cased and cased != orig:
            set_menu_override(orig, cased, db_path)
            updated += 1

    return {
        "ok": True,
        "count": len(unique_items),
        "updated": updated,
        "message": (
            f"Processed {len(unique_items)} unique items with Gemini 3.6 Flash. "
            f"Updated {updated} display overrides."
        ),
    }
