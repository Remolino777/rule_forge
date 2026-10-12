"""Contract of the design module: `design_profile` (step 6.7a S2.2a).

    to_contract(profile)        design profile -> design_profile contract, validated
    from_contract(contract)     validated profile for the consumers (stacking, pipeline)
"""

from __future__ import annotations

from spaceplan.core.lib.contracts import make_contract, plain_json, read_contract

NAME = "design_profile"


def to_contract(profile: dict) -> dict:
    inputs = {k: profile[k] for k in ("registry_id", "registry_version", "base_stores_sha256")}
    return make_contract(NAME, inputs, {"design_profile": plain_json(profile)})


def from_contract(contract: dict) -> dict:
    return read_contract(contract, NAME)["design_profile"]


__all__ = ["NAME", "from_contract", "to_contract"]
