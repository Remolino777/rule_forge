"""Contract of the zoning module: `zoning_scheme` (refactor tanda 4).

    to_contract(brief, zoning, unit, corrections, strategy)  zoning options with their zone and space schemes,
                                                             circulation, the apartment unit and the minimal
                                                             correction -> zoning_scheme, validated
    from_contract(contract)                                  validated blocks for the consumers (viz, pipeline)
"""

from __future__ import annotations

from spaceplan.core.lib.contracts import make_contract, package_json, read_contract

NAME = "zoning_scheme"


def to_contract(brief: dict, zoning: dict | None, unit: dict | None = None, corrections: dict | None = None,
                strategy: str | None = None) -> dict:
    payload = {"zoning": package_json(zoning), "unit": package_json(unit), "corrections": package_json(corrections),
               "dwelling_type": brief["dwelling_type"], "realization_strategy": strategy}
    return make_contract(NAME, brief, payload, brief["meta"]["brief_id"])


def from_contract(contract: dict) -> dict:
    return read_contract(contract, NAME)


__all__ = ["NAME", "from_contract", "to_contract"]
