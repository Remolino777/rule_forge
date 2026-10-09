"""Contract of the lotcap module: `lot_capacity` (refactor tanda 4).

    to_contract(brief, scope, setup, strategy, flag)  LotSetup (layer 0) -> lot_capacity, validated
    from_contract(contract)                           validated blocks for the consumers (site, zoning, areas,
                                                      cost, viz, pipeline)

The blocks are serialized exactly as the package carries them (the package is assembled from this contract).
"""

from __future__ import annotations

from spaceplan.core.lib.contracts import make_contract, package_json, plain_json, read_contract
from spaceplan.modules.lotcap.lib.scope import ScopeResult

NAME = "lot_capacity"


def boundary_rows(lot, boundaries, evaluation, north_deg: float) -> list[dict]:
    """One row per lot edge: class, inference, street, length, setback and outward azimuth (package 'boundaries').
    Moved from the package assembly (pipeline) without changes."""
    rows = []
    for edge in lot.edges:
        a = boundaries.assignments[edge.edge_id]
        rows.append(
            {
                "edge_id": edge.edge_id,
                "boundary_class": a.boundary_class,
                "inferred": a.inferred,
                "status": a.status,
                "note": a.note,
                "street_id": edge.street_id,
                "length_ft": edge.length,
                "setback_ft": evaluation.edge_setbacks[edge.edge_id],
                "outward_azimuth_deg": (edge.outward_bearing_deg - north_deg) % 360.0,
            }
        )
    return rows


def lot_warnings(capacity, conformity: list[dict] | None) -> list[str]:
    """Capacity warnings, then one line per lot-conformity check that fails (package order)."""
    return list(capacity.warnings) + [
        f"lot does not meet {c['check_id']} ({c['value']:.1f} < {c['required']:.1f} {c['unit']})"
        for c in (conformity or []) if not c["passes"]]


def to_contract(brief: dict, scope: ScopeResult, setup, strategy: str, flag: dict | None = None) -> dict:
    """lot_capacity of a prepared house lot (`setup` is run_lotcap.LotSetup; `brief` is the planned brief, i.e.
    the body of a flag lot)."""
    ev, cap = setup.evaluation, setup.capacity
    payload = {
        "lot": {"polygon": package_json(setup.lot.polygon), "flag": package_json(flag),
                "lot_block": plain_json(brief["lot"])},
        "scope": package_json(scope.to_dict()),
        "lot_metrics": package_json(ev.metrics.to_dict(ev.width_method, ev.depth_method, setup.boundaries.frame)),
        "boundaries": package_json(boundary_rows(setup.lot, setup.boundaries, ev,
                                                 brief["orientation"]["north_azimuth_deg"])),
        "rule_variants": package_json(list(cap.decisions.values())),
        "lot_conformity": package_json(setup.conformity or []),
        "capacity": package_json(cap.capacity),
        "realizable_capacity": package_json(cap.realizable),
        "sensitivity": package_json(setup.sensitivity),
        "warnings": lot_warnings(cap, setup.conformity),
        "terrain": plain_json(brief.get("terrain")),
        "realization_strategy": strategy,
    }
    return make_contract(NAME, brief, payload, brief["meta"]["brief_id"])


def from_contract(contract: dict) -> dict:
    return read_contract(contract, NAME)


__all__ = ["NAME", "boundary_rows", "from_contract", "lot_warnings", "to_contract"]
