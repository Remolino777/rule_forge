"""Workflow of the `household` command: household needs and programs (6.5a) priced by the cost module (6.5b).

Refactor tanda 3: the household module no longer imports the cost module; this pipeline workflow composes
both with the same signature and output as the former spaceplan.main.run_household.derive_household.
"""

from __future__ import annotations

from pathlib import Path

from spaceplan.modules.cost.main.run_cost import household_cost
from spaceplan.modules.household.main import run_household


def derive_household(
    raw: dict,
    catalog_path: str | Path | None = None,
    household_catalog_path: str | Path | None = None,
    dwelling_type: str = "house",
    next_stage: bool = True,
    cost_model: str | None = None,
) -> dict:
    """Needs and programs for the current stage and (optionally) the next one, with growth delta and
    the relative cost index of every tier (reference-dwelling reading, step 6.5b)."""
    return run_household.derive_household(
        raw, catalog_path, household_catalog_path, dwelling_type, next_stage,
        stage_cost=lambda catalog, stage: household_cost(catalog, stage, cost_model))


__all__ = ["derive_household"]
