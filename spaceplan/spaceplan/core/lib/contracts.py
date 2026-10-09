"""Executable module contracts (refactor tanda 4).

A contract is a JSON object with a common envelope (contract, version, produced_by, input_sha256, optional
brief_id and consumers) plus the blocks of one module. The schemas live in spaceplan/contracts/schemas/ and
reference the package and brief schemas, so a contract and the package never diverge.

    make_contract(name, inputs, payload)   envelope + payload, validated (producer side: to_contract)
    read_contract(instance, name)          validated payload without the envelope (consumer side: from_contract)

Serialization follows the package: blocks the package rounds (lot, site, zoning, program review) go through
`package_json`; blocks the package carries as they are (household, cost) through `plain_json`.
"""

from __future__ import annotations

from functools import cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from shapely.geometry import mapping
from shapely.geometry.base import BaseGeometry

from spaceplan.core.lib.registry import CONSUMERS, PRODUCERS
from spaceplan.core.lib.schema_validation import CONTRACTS, contract_registry, load_contract_schema
from spaceplan.core.lib_aux.hashing import sha256_of
from spaceplan.core.lib_aux.json_io import dump_json, load_json, round_floats, to_json_compatible
from spaceplan.core.lib_aux.quantity import Quantity
from spaceplan.core.lib_aux.tolerances import ROUND_DECIMALS

CONTRACT_VERSION = "0.2.0"
ENVELOPE = ("contract", "version", "produced_by", "input_sha256", "brief_id", "consumers")
STRIPPED = ("contract", "version", "produced_by", "input_sha256", "consumers")  # brief_id stays in the payload
# PRODUCERS and CONSUMERS come from the single registry (spaceplan/core/lib/registry.py)


class ContractValidationError(ValueError):
    def __init__(self, name: str, errors: list[str]):
        self.name, self.errors = name, errors
        super().__init__(f"invalid {name} contract:\n  - " + "\n  - ".join(errors[:20]))


def serialize(obj: Any) -> Any:
    """Domain objects -> JSON values (Quantity, shapely geometry, objects with to_dict)."""
    if isinstance(obj, Quantity):
        return obj.to_dict()
    if isinstance(obj, BaseGeometry):
        return mapping(obj)
    if hasattr(obj, "to_dict"):
        return obj.to_dict()
    if isinstance(obj, dict):
        return {str(k): serialize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [serialize(v) for v in obj]
    if isinstance(obj, float):
        return float(obj)
    return obj


def package_json(obj: Any) -> Any:
    """Same treatment as the package assembly: serialize, JSON round trip, floats rounded."""
    return round_floats(to_json_compatible(serialize(obj)), ROUND_DECIMALS)


def plain_json(obj: Any) -> Any:
    """JSON round trip only (blocks the package carries without rounding)."""
    return to_json_compatible(obj)


@cache
def _validator(name: str) -> Draft202012Validator:
    if name not in CONTRACTS:
        raise KeyError(f"unknown contract {name!r}; expected one of {', '.join(CONTRACTS)}")
    return Draft202012Validator(load_contract_schema(name), registry=contract_registry())


def contract_problems(instance: Any, name: str) -> list[str]:
    errors = sorted(_validator(name).iter_errors(instance), key=lambda e: list(e.absolute_path))
    return [f"{'/'.join(map(str, e.absolute_path)) or '<root>'}: {e.message}" for e in errors]


def validate_contract(instance: Any, name: str) -> None:
    errors = contract_problems(instance, name)
    if errors:
        raise ContractValidationError(name, errors)


def make_contract(name: str, inputs: Any, payload: dict, brief_id: str | None = None) -> dict:
    """Envelope + payload of a module output, validated against its schema."""
    contract = {"contract": name, "version": CONTRACT_VERSION, "produced_by": PRODUCERS[name],
                "input_sha256": sha256_of(inputs), "brief_id": brief_id, "consumers": list(CONSUMERS[name]),
                **payload}
    validate_contract(contract, name)
    return contract


def read_contract(instance: dict, name: str) -> dict:
    """Validated payload of a contract (envelope removed, brief_id kept): what a consumer reads."""
    validate_contract(instance, name)
    return {k: v for k, v in instance.items() if k not in STRIPPED}


def write_contract(contract: dict, path: str | Path) -> None:
    validate_contract(contract, contract["contract"])
    dump_json(contract, path)


def load_contract(path: str | Path, name: str | None = None) -> dict:
    """Read a contract file; `name` (when given) must match its 'contract' field."""
    contract = load_json(path)
    actual = contract.get("contract") if isinstance(contract, dict) else None
    if actual not in CONTRACTS or (name is not None and actual != name):
        raise ContractValidationError(name or "module", [f"{path}: is a {actual!r} contract, expected {name or 'a module contract'!r}"])
    validate_contract(contract, actual)
    return contract


__all__ = ["CONSUMERS", "CONTRACT_VERSION", "ENVELOPE", "PRODUCERS", "ContractValidationError", "contract_problems",
           "load_contract", "make_contract", "package_json", "plain_json", "read_contract", "serialize",
           "validate_contract", "write_contract"]
