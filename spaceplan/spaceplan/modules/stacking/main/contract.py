"""Contract of the stacking module: `stack_plan` (step 6.7).

    to_contract(result, inputs)   run_stacking result -> stack_plan, validated
    from_contract(contract)       validated blocks for the consumers (viz, pipeline, step 6.8)
"""

from __future__ import annotations

from spaceplan.core.lib.contracts import make_contract, package_json, read_contract

NAME = "stack_plan"


def to_contract(result: dict, inputs=None) -> dict:
    """`inputs` defaults to the meta block (selection, ruleset and catalog versions and hashes)."""
    return make_contract(NAME, result["meta"] if inputs is None else inputs, package_json(result))


def from_contract(contract: dict) -> dict:
    return read_contract(contract, NAME)


__all__ = ["NAME", "from_contract", "to_contract"]
