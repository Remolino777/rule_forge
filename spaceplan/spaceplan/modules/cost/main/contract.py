"""Contract of the cost module: `cost_report` (refactor tanda 4).

    cost_from_contracts(catalog, lot_capacity, site_plan, program, ...)
        reads the upstream contracts (no import of lotcap, site or household: only their JSON) -> lot reading of
        the relative cost index (quantity sheets, index per model, budget, tornado) -> cost_report, validated
    to_contract(cost, inputs, brief_id)   wraps a cost block (e.g. the reference-dwelling reading of a household)
    from_contract(contract)               validated blocks for the consumers (profiles, areas, pipeline)

The index is comparative, never a quote: no model knows money.
"""

from __future__ import annotations

from spaceplan.core.lib.catalog import Catalog
from spaceplan.core.lib.contracts import make_contract, plain_json, read_contract
from spaceplan.modules.cost.main.run_cost import package_cost

NAME = "cost_report"


def to_contract(cost: dict, inputs, brief_id: str | None = None) -> dict:
    """The cost block is carried as it is (the package does not round it)."""
    return make_contract(NAME, inputs, {"cost": plain_json(cost)}, brief_id)


def cost_from_contracts(catalog: Catalog, lot_capacity: dict, site_plan: dict, program: dict,
                        tier_programs: dict | None = None, model: str | None = None,
                        budget: dict | None = None) -> dict | None:
    """Lot reading of the program on every site option (and each household tier when given); None when the lot
    has no normative maximum (same rule as run_cost.package_cost)."""
    lot = read_contract(lot_capacity, "lot_capacity")
    site = read_contract(site_plan, "site_plan")
    prog = read_contract(program, "program")
    view = {"capacity": lot["capacity"], "site_partition": site["site_partition"],
            "meta": {"realization_strategy": lot["realization_strategy"]}}
    brief = {"program": prog["program"], "terrain": lot.get("terrain")}
    cost = package_cost(catalog, brief, view, tier_programs, model, budget)
    if cost is None:
        return None
    inputs = {"lot_capacity": lot_capacity["input_sha256"], "site_plan": site_plan["input_sha256"],
              "program": program["input_sha256"], "tiers": tier_programs, "model": model, "budget": budget}
    return to_contract(cost, inputs, lot_capacity.get("brief_id"))


def from_contract(contract: dict) -> dict:
    return read_contract(contract, NAME)


__all__ = ["NAME", "cost_from_contracts", "from_contract", "to_contract"]
