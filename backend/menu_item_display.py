"""One rule for turning a stored menu description into the text a human sees.

SchoolCafé returns every description in ALL CAPS, and a parent can pin a
permanent replacement for any item. Resolving a stored description therefore
combines an override lookup with a casing pass.

That combination used to live in four places under three different rules:
`school_menu.extract_items` cased without overrides, `menu_service`'s two
override helpers applied overrides without casing, and `db.resolve_display_text`
did both. The entree a parent clicked and the Skylight recipe summary written
for it went through different ones, so they could disagree. The rule lives
here now, behind one interface.

This module is deliberately pure: no I/O, no subprocess, no cache. Consulting
a language model for a better casing is a separate concern — see
`menu_casing.py`, whose one caller is the admin bulk re-casing pass. Nothing
in the read or ingest path needs to shell out.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping

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


class MenuItemDisplay:
    """Resolve stored menu descriptions to display text.

    `display` is the full rule and the one every caller should reach for.
    `cased` exposes the casing pass alone, for the override table, which
    stores a replacement under both the raw and the cased key.
    """

    def __init__(
        self,
        overrides: Mapping[str, str] | None = None,
        passthrough: Iterable[str] = (),
    ) -> None:
        self._overrides = dict(overrides or {})
        self._passthrough = frozenset(passthrough)

    def cased(self, text: str) -> str:
        """Convert an ALL CAPS menu item description to proper Title Case.

        Rules:
          - Empty or already mixed-case text is returned as-is (idempotent).
          - ALL CAPS text is converted to Title Case.
          - Known acronyms (BBQ, PB, PBJ, OG, USDA) are preserved uppercase.
          - Known food terms (Mac, Rotini, etc.) get their canonical casing.
        """
        if not text or not text.isupper():
            return text
        return _apply_title_case_exceptions(_title_case_simple(text))

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


def cased_menu_item(text: str) -> str:
    """Casing pass alone, with no overrides applied."""
    return MenuItemDisplay().cased(text)
