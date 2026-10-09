"""Contract of the site module: `site_plan` (refactor tanda 4).

    to_contract(brief, site, warnings)  site partition (options per number of floors, access, paving, garden,
                                        facades, backyard) -> site_plan, validated
    from_contract(contract)             validated blocks for the consumers (zoning, areas, cost, viz, pipeline)
"""

from __future__ import annotations

from spaceplan.core.lib.contracts import make_contract, package_json, read_contract

NAME = "site_plan"


def to_contract(brief: dict, site: dict, warnings=()) -> dict:
    """site_plan of a house lot once the backyard is placed (run_site.plan_site + plan_site_backyard)."""
    payload = {"site_partition": package_json(site), "warnings": list(warnings)}
    return make_contract(NAME, brief, payload, brief["meta"]["brief_id"])


def from_contract(contract: dict) -> dict:
    return read_contract(contract, NAME)


__all__ = ["NAME", "from_contract", "to_contract"]
