"""Workflow of the `catalog` command: parameter table of the residential catalog (plus the cost table).

Moved from spaceplan.modules.household.main.run_program in refactor tanda 3 without changes (the table
documents the whole catalog, so it is composed by the pipeline).
"""

from __future__ import annotations

from pathlib import Path

from spaceplan.core.lib.catalog import load_catalog
from spaceplan.core.lib.rules import CRC_RULESET, load_ruleset_resource
from spaceplan.pipeline.lib.catalog_table import render_cost_table, render_parameter_table


def parameter_table(catalog_path: str | Path | None = None, garage_cars: int = 2) -> str:
    catalog = load_catalog(catalog_path)
    return (render_parameter_table(catalog, load_ruleset_resource(*CRC_RULESET), garage_cars) + "\n"
            + render_cost_table(catalog))


__all__ = ["parameter_table"]
