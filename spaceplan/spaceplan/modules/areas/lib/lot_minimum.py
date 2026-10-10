"""Lot minimum (client rule D04, 2026-10-09): the basic one-bedroom house as a reference for a lot.

The same for every household: its gross area is the sum of the minimum areas of the reference typology times its
gross factor; the report says whether it fits one floor within the design footprint and the effective FOT.
The household minimum (its required program) stays the `minimum` profile of each household.
"""

from __future__ import annotations

from typing import Any

from spaceplan.core.lib.catalog import Catalog
from spaceplan.modules.household.lib.program_builder import expand_typology


def lot_minimum(catalog: Catalog, spec: dict[str, Any], budget) -> dict[str, Any]:
    program = expand_typology(catalog, spec["typology_id"], int(spec.get("garage_cars", 0)),
                              spec.get("size_profile", "compact"))
    net = sum(s["min_area_sqft"] for s in program["spaces"])
    gross = net * program["gross_factor"]
    footprint = budget.footprint_design_sqft
    fot_area = budget.limits.gross_area_max_sqft
    return {
        "typology_id": spec["typology_id"],
        "garage_cars": int(spec.get("garage_cars", 0)),
        "spaces": [s["space_type"] for s in program["spaces"]],
        "net_sqft": round(net, 1),
        "gross_sqft": round(gross, 1),
        "IC": round(gross / budget.lot_area_sqft, 4),
        "fits_one_floor": footprint is None or gross <= footprint + 1e-6,
        "within_fot": gross <= fot_area + 1e-6,
    }


__all__ = ["lot_minimum"]
