"""Contract of the areas module: `area_matrix` (refactor tanda 4).

    to_contract(result, inputs)  lot budgets, cells (profile x vertical scheme x strategy, E0/E1), ranking,
                                 Pareto and E2 -> area_matrix, validated
    from_contract(contract)      validated blocks for the consumers (viz)
"""

from __future__ import annotations

from spaceplan.core.lib.contracts import make_contract, plain_json, read_contract

NAME = "area_matrix"


def to_contract(result: dict, inputs=None) -> dict:
    """`inputs` defaults to the matrix meta (lots, households, model, ruleset and catalog versions)."""
    return make_contract(NAME, result["meta"] if inputs is None else inputs, plain_json(result))


def from_contract(contract: dict) -> dict:
    return read_contract(contract, NAME)


__all__ = ["NAME", "from_contract", "to_contract"]
