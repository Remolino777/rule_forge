"""Contract of the profiles module: `program_portfolio` (refactor tanda 4).

    to_contract(portfolio, inputs)  expansion curve, the five profiles (minimum, optimum, maximum, accessible,
                                    staged) and the ceilings -> program_portfolio, validated
    from_contract(contract)         validated blocks for the consumers (areas, viz)
"""

from __future__ import annotations

from spaceplan.core.lib.contracts import make_contract, plain_json, read_contract

NAME = "program_portfolio"


def to_contract(portfolio: dict, inputs) -> dict:
    """`inputs`: what the portfolio was computed from (brief or household, budget, model)."""
    return make_contract(NAME, inputs, plain_json(portfolio), portfolio.get("brief_id"))


def from_contract(contract: dict) -> dict:
    return read_contract(contract, NAME)


__all__ = ["NAME", "from_contract", "to_contract"]
