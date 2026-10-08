"""Assembly and serialization of the schematic design package."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from shapely.geometry import mapping
from shapely.geometry.base import BaseGeometry

from spaceplan import __version__
from spaceplan.modules.lotcap.lib.boundaries import BoundaryModel
from spaceplan.modules.lotcap.lib.capacity import CapacityResult, SetbackEvaluation
from spaceplan.core.lib.enums import PACKAGE_SCHEMA_VERSION, Strategy
from spaceplan.modules.lotcap.lib.lot import Lot
from spaceplan.core.lib.rules import RuleSet
from spaceplan.modules.lotcap.lib.scope import ScopeResult
from spaceplan.core.lib_aux.hashing import sha256_of, sha256_text
from spaceplan.core.lib_aux.json_io import round_floats, to_json_compatible
from spaceplan.core.lib_aux.quantity import Quantity
from spaceplan.core.lib_aux.tolerances import ROUND_DECIMALS

GENERATOR_NAME = "spaceplan"
RESERVED_BLOCKS = ("graphs", "sized_program", "geometric_scheme", "metrics")


def serialize(obj: Any) -> Any:
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


def package_id(brief_sha: str, *input_shas: str) -> str:
    """Deterministic id from the brief and every versioned input (rulesets, catalog)."""
    joined = ":".join((brief_sha, *input_shas, f"{GENERATOR_NAME}-{__version__}"))
    return "pkg-" + sha256_text(joined)[:16]


def _meta(brief: dict, rs: RuleSet, review: dict, strategy: str | None = None) -> dict:
    brief_sha = sha256_of(brief)
    return {
        "package_id": package_id(brief_sha, rs.sha256, review["catalog_sha256"], review["crc_ruleset_sha256"]),
        "schema_version": PACKAGE_SCHEMA_VERSION,
        "brief_id": brief["meta"]["brief_id"],
        "dwelling_type": brief["dwelling_type"],
        "brief_sha256": brief_sha,
        "ruleset_id": rs.ruleset_id,
        "ruleset_version": rs.version,
        "ruleset_sha256": rs.sha256,
        "code_edition": rs.code_edition,
        "seed": brief["meta"]["seed"],
        "generator": {"name": GENERATOR_NAME, "version": __version__},
        "realization_strategy": strategy or Strategy.A_INSCRIBED_RECTANGLE.value,
    }


def _boundaries(lot: Lot, boundaries: BoundaryModel, ev: SetbackEvaluation, north_deg: float) -> list[dict]:
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
                "setback_ft": ev.edge_setbacks[edge.edge_id],
                "outward_azimuth_deg": (edge.outward_bearing_deg - north_deg) % 360.0,
            }
        )
    return rows


@dataclass(frozen=True)
class PackageInputs:
    brief: dict
    ruleset: RuleSet
    scope: ScopeResult
    program_review: dict
    lot: Lot | None = None
    boundaries: BoundaryModel | None = None
    evaluation: SetbackEvaluation | None = None
    capacity: CapacityResult | None = None
    sensitivity: dict | None = None
    conformity: list[dict] | None = None
    site_partition: dict | None = None
    site_warnings: tuple[str, ...] = ()
    zoning: dict | None = None
    unit: dict | None = None
    corrections: dict | None = None
    strategy: str | None = None


def assemble_package(inputs: PackageInputs) -> dict:
    brief, rs = inputs.brief, inputs.ruleset
    package: dict[str, Any] = {
        "meta": _meta(brief, rs, inputs.program_review, inputs.strategy),
        "scope": inputs.scope.to_dict(),
        "lot_metrics": None,
        "boundaries": [],
        "rule_variants": [],
        "lot_conformity": [],
        "capacity": None,
        "realizable_capacity": [],
        "sensitivity": None,
        "site_partition": inputs.site_partition,
        "zoning": inputs.zoning,
        "unit": inputs.unit,
        "corrections": inputs.corrections,
        "program_review": inputs.program_review,
        "warnings": [],
    }
    if inputs.capacity is not None:
        ev, cap = inputs.evaluation, inputs.capacity
        package.update(
            lot_metrics=ev.metrics.to_dict(ev.width_method, ev.depth_method, inputs.boundaries.frame),
            boundaries=_boundaries(
                inputs.lot, inputs.boundaries, ev, brief["orientation"]["north_azimuth_deg"]
            ),
            rule_variants=list(cap.decisions.values()),
            lot_conformity=inputs.conformity or [],
            capacity=cap.capacity,
            realizable_capacity=cap.realizable,
            sensitivity=inputs.sensitivity,
            warnings=list(cap.warnings)
            + [f"lot does not meet {c['check_id']} ({c['value']:.1f} < {c['required']:.1f} {c['unit']})"
               for c in (inputs.conformity or []) if not c["passes"]],
        )
    package["warnings"].extend(inputs.site_warnings)
    for option in (inputs.zoning or {}).get("options", []):
        if option["status"] == "no_valid_scheme":
            hint = ""
            fits = [d for d in option.get("diagnostics", []) if not d["front_fits"]]
            if fits and len(fits) == len(option.get("diagnostics", [])):
                d = min(fits, key=lambda d: d["front_min_demand_ft"] - d["front_width_ft"])
                hint = (f" (access side needs {d['front_min_demand_ft']:.1f} ft for {', '.join(d['demand_by_cell'])}; "
                        f"footprint is {d['front_width_ft']:.1f} ft wide)")
            package["warnings"].append(f"zoning {option['option_id']}: no topology satisfies the hard constraints{hint}")
    c = inputs.corrections
    if c is not None:
        if c["applied"]:
            package["warnings"].append(
                f"minimal correction for n1 ({c['triggered_by']}): {', '.join(c['applied']['combo']['labels'])} "
                f"(cost {c['applied']['combo']['cost']:g}); see corrections.applied")
        else:
            package["warnings"].append(f"no correction found for n1 ({c['triggered_by']}) within the evaluated combinations")
    if not inputs.program_review["buildable_as_stated"]:
        package["warnings"].append(
            f"program review: {inputs.program_review['counts']['error']} error(s); see program_review.findings"
        )
    for block in RESERVED_BLOCKS:
        package[block] = None
    return round_floats(to_json_compatible(serialize(package)), ROUND_DECIMALS)
