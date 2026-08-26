#!/usr/bin/env python3
"""Command-line adapter for one Menu Catalog Refresh."""

from __future__ import annotations

import argparse
import sys

from lunch_planner.menu_catalog.refresh import default_menu_catalog_refresh
from lunch_planner.persistence import database as db


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Refresh the next four weeks of school lunch choices in the Menu Catalog."
    )
    parser.parse_args(argv)

    outcome = default_menu_catalog_refresh(db.DEFAULT_DB_PATH).refresh()
    stream = sys.stdout if outcome.succeeded else sys.stderr
    print(outcome.message, file=stream)
    if outcome.status == "not_configured":
        return 2
    return 0 if outcome.succeeded else 1


if __name__ == "__main__":
    sys.exit(main())
