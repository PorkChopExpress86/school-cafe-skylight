"""Planner-ready presentation of one Selection's publication facts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import db

SelectionPublicationState = Literal["pending", "published", "make_at_home"]


@dataclass(frozen=True)
class SelectionPresentation:
    """One Selection expressed in the planner's publication vocabulary."""

    publication_state: SelectionPublicationState

    @classmethod
    def from_storage(
        cls, selection: str, sent_at: str | None, sent_sitting_id: str | None
    ) -> SelectionPresentation:
        """Translate stored publication facts without exposing them to callers."""
        if sent_sitting_id:
            return cls("published")
        if sent_at and selection == db.MAKE_AT_HOME:
            return cls("make_at_home")
        return cls("pending")
