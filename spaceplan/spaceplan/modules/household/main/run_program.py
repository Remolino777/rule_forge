"""Workflow for step 3: typology -> program block -> review.

Refactor tanda 3: the catalog parameter table (command `catalog`) moved to spaceplan.pipeline.main.run_catalog.
"""

from __future__ import annotations

from pathlib import Path

from spaceplan.core.lib.catalog import load_catalog
from spaceplan.core.lib.rules import CRC_RULESET, load_ruleset_resource
from spaceplan.modules.household.lib.program_builder import expand_typology
from spaceplan.modules.household.lib.program_review import review_program


def build_program(
    typology_id: str, garage_cars: int, profile: str = "balanced", catalog_path: str | Path | None = None
) -> dict:
    """Expanded program plus its review, ready to paste into brief.program."""
    catalog = load_catalog(catalog_path)
    program = expand_typology(catalog, typology_id, garage_cars, profile)
    review = review_program(catalog, load_ruleset_resource(*CRC_RULESET), program)
    return {"program": program, "review": review}


__all__ = ["build_program"]
