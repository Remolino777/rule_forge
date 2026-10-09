"""Contract of the household module: `program` (refactor tanda 4).

    to_contract(brief, review, household)  program of the brief (given or derived from the household), its review
                                           against the catalog and the CRC, and the privacy-minimized household
                                           block -> program, validated
    from_contract(contract)                validated blocks for the consumers (profiles, zoning, cost, pipeline)
"""

from __future__ import annotations

from spaceplan.core.lib.contracts import make_contract, package_json, plain_json, read_contract

NAME = "program"


def to_contract(brief: dict, review: dict, household: dict | None = None) -> dict:
    """`brief` carries the program (resolved); the review is rounded as in the package, the household block is
    carried as it is (the package does not round it)."""
    payload = {"program": plain_json(brief["program"]), "household": plain_json(household),
               "program_review": package_json(review)}
    return make_contract(NAME, brief, payload, brief["meta"]["brief_id"])


def from_contract(contract: dict) -> dict:
    return read_contract(contract, NAME)


__all__ = ["NAME", "from_contract", "to_contract"]
