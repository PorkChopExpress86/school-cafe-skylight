"""One rule for turning a stored menu description into the text a human sees.

SchoolCafé returns every description in ALL CAPS, and a parent can pin a
permanent replacement for any item. Resolving a stored description therefore
combines an override lookup with a casing pass — plus a consultation with a
language model for the items the simple rules get wrong.

That combination used to live in four places under three different rules:
`school_menu.extract_items` cased without overrides, `menu_service`'s two
override helpers applied overrides without casing, and `db.resolve_display_text`
did both. The entree a parent clicked and the Skylight recipe summary written
for it went through different ones, so they could disagree. The rule lives
here now, behind one interface.

The casing consultation sits behind its own seam (`CasingAdapter`) so the
offline test suite substitutes `NoCasing` rather than the production code
checking whether it is running under pytest.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from collections.abc import Iterable, Mapping
from typing import Protocol

# Acronyms and abbreviations to preserve in title case.
# SchoolCafé returns everything in ALL CAPS, so these are the tokens that
# should stay uppercase when the rest of the item is normalized to Title Case.
ACRONYMS: frozenset[str] = frozenset({
    "BBQ",   # Barbeque
    "PB",    # Peanut Butter
    "PBJ",   # Peanut Butter & Jelly
    "OG",    # Orange
    "USDA",  # U.S. Department of Agriculture
})

# Words that have unusual capitalization in food-service nomenclature and
# should NOT be lower-cased by Title Case (e.g. "Mac" in "Mac & Cheese").
# Applied as a sanity pass after the simple title-case conversion.
TITLE_CASE_EXCEPTIONS: dict[str, str] = {
    "mac": "Mac",   # Mac & Cheese
    "nugget": "Nugget",
    "chikn": "Chikn",
    "rotini": "Rotini",
    "pita": "Pita",
}

DEFAULT_CASING_MODEL = "gemini-3.6-flash-low"


# ---------------------------------------------------------------------------
# Casing seam
# ---------------------------------------------------------------------------


class CasingAdapter(Protocol):
    """Seam for consulting something smarter than the simple casing rules."""

    def suggest(self, text: str) -> str | None:
        """Return a better-cased form of `text`, or None to fall back."""
        ...


class NoCasing:
    """Casing adapter that never suggests anything.

    Used by the offline test suite and by any run that must not shell out.
    """

    def suggest(self, text: str) -> str | None:
        return None


class AgyCasingAdapter:
    """Consult the `agy` CLI for a complex item's display casing.

    Returns None — so the caller falls back to the simple rules — when agy is
    not installed, exits non-zero, times out, or answers implausibly.
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


_default_casing: CasingAdapter = AgyCasingAdapter()

# Cache of all-caps source -> properly-cased display string, shared by every
# instance that does not bring its own. Per-process and not persisted: the
# adapter is consulted once per unique item per server lifetime.
_default_cache: dict[str, str] = {}


def default_casing() -> CasingAdapter:
    """The casing adapter used when none is supplied."""
    return _default_casing


def set_default_casing(adapter: CasingAdapter) -> None:
    """Replace the process-wide casing adapter (tests, offline runs)."""
    global _default_casing
    _default_casing = adapter


def reset_cache() -> None:
    """Clear the shared casing cache."""
    _default_cache.clear()


# ---------------------------------------------------------------------------
# Casing rules
# ---------------------------------------------------------------------------


def _title_case_simple(text: str) -> str:
    """Convert ALL CAPS to Title Case, preserving acronyms and punctuation.

    Splits on whitespace, capitalizes each word unless it's a known acronym,
    then re-joins. Punctuation (commas, &, parentheses) is preserved as-is.
    """
    out: list[str] = []
    for word in text.split():
        # Strip punctuation for the acronym lookup, keep it for output.
        stripped = word.strip(".,;:!?'\"()[]/")
        if stripped.upper() in ACRONYMS:
            out.append(word.replace(stripped, stripped.upper()))
        else:
            # Lower-case then capitalize to handle things like "McDONALD'S"
            out.append(word.lower().capitalize())
    return " ".join(out)


def _apply_title_case_exceptions(text: str) -> str:
    """Apply per-word capitalization overrides for known food terms.

    Only touches words that appear as standalone tokens (not inside other
    words), so "Mac" overrides apply to "Mac & Cheese" but not to "Macaroni".
    """
    for word, replacement in TITLE_CASE_EXCEPTIONS.items():
        text = re.sub(rf"(?<![A-Za-z]){word}(?![A-Za-z])", replacement, text, flags=re.IGNORECASE)
    return text


def _needs_casing_adapter(text: str) -> bool:
    """True if the item is complex enough to warrant consulting the adapter.

    Heuristic: items with commas (multi-part descriptions), semicolons, or
    unusual compound words (three or more consecutive uppercase letters
    inside the string) are worth a second opinion.
    """
    if "," in text or ";" in text:
        return True
    return bool(re.search(r"[A-Z]{3,}", text[1:]))


# ---------------------------------------------------------------------------
# The module
# ---------------------------------------------------------------------------


class MenuItemDisplay:
    """Resolve stored menu descriptions to display text.

    `display` is the full rule and the one every caller should reach for.
    `cased` exposes the casing pass alone, for the override table, which
    stores a replacement under both the raw and the cased key.
    """

    def __init__(
        self,
        overrides: Mapping[str, str] | None = None,
        casing: CasingAdapter | None = None,
        cache: dict[str, str] | None = None,
        passthrough: Iterable[str] = (),
    ) -> None:
        self._overrides = dict(overrides or {})
        self._casing = casing
        self._cache = _default_cache if cache is None else cache
        self._passthrough = frozenset(passthrough)

    def cased(self, text: str) -> str:
        """Convert an ALL CAPS menu item description to proper Title Case.

        Rules:
          - Empty or already mixed-case text is returned as-is (idempotent).
          - ALL CAPS text is converted to Title Case.
          - Known acronyms (BBQ, PB, PBJ, OG, USDA) are preserved uppercase.
          - Known food terms (Mac, Rotini, etc.) get their canonical casing.
          - Complex items are put to the casing adapter on first appearance;
            the answer is cached.
        """
        if not text or not text.isupper():
            return text
        if text in self._cache:
            return self._cache[text]

        result = _apply_title_case_exceptions(_title_case_simple(text))
        if _needs_casing_adapter(text):
            casing = self._casing if self._casing is not None else _default_casing
            suggestion = casing.suggest(text)
            if suggestion:
                result = suggestion

        self._cache[text] = result
        return result

    def display(self, text: str) -> str:
        """Resolve `text` to its display form.

        An active override on the raw text wins; otherwise the text is cased
        and an override on the cased form is applied. Passthrough values (the
        Make at Home sentinel) and empty text are returned untouched.
        """
        if not text or text in self._passthrough:
            return text
        override = self._overrides.get(text)
        if override:
            return override
        cased = self.cased(text)
        return self._overrides.get(cased) or cased

    def suggest_casing(self, text: str) -> str | None:
        """Put `text` to the casing adapter directly, bypassing the heuristic.

        Used by the admin bulk re-casing pass, which wants an answer for every
        item rather than only the ones the heuristic flags.
        """
        casing = self._casing if self._casing is not None else _default_casing
        return casing.suggest(text)


def cased_menu_item(text: str) -> str:
    """Casing pass alone, against the shared cache and default adapter."""
    return MenuItemDisplay().cased(text)
