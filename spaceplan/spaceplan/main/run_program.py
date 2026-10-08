"""Workflow for step 3: typology -> program block -> review; catalog -> parameter table."""

from __future__ import annotations

from pathlib import Path

from spaceplan.lib.catalog import load_catalog
from spaceplan.lib.catalog_table import render_cost_table, render_parameter_table
from spaceplan.lib.program_builder import expand_typology
from spaceplan.lib.program_review import review_program
from spaceplan.lib.rules import CRC_RULESET, load_ruleset_resource


def build_program(
    typology_id: str, garage_cars: int, profile: str = "balanced", catalog_path: str | Path | None = None
) -> dict:
    """Expanded program plus its review, ready to paste into brief.program."""
    catalog = load_catalog(catalog_path)
    program = expand_typology(catalog, typology_id, garage_cars, profile)
    review = review_program(catalog, load_ruleset_resource(*CRC_RULESET), program)
    return {"program": program, "review": review}


def parameter_table(catalog_path: str | Path | None = None, garage_cars: int = 2) -> str:
    catalog = load_catalog(catalog_path)
    return (render_parameter_table(catalog, load_ruleset_resource(*CRC_RULESET), garage_cars) + "\n"
            + render_cost_table(catalog))
