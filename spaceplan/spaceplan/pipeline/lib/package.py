"""Assembly of the schematic design package from the module contracts (refactor tanda 4).

    package_from_contracts(brief, ruleset, scope, program, strategy, lot_capacity, site_plan, zoning_scheme)
        meta from the brief, the ruleset and the program review; the lot, site and zoning blocks are read from
        the contracts (each validated); warnings in the historical order (lot, site, zoning, correction, review).
The in-memory assembly (`assemble_package(PackageInputs)`) was removed: the pipeline builds the contracts with
each module's to_contract and the package is always assembled from them.
"""

from __future__ import annotations

from typing import Any

from spaceplan import __version__
from spaceplan.core.lib.contracts import package_json, read_contract
from spaceplan.core.lib.enums import PACKAGE_SCHEMA_VERSION, Strategy
from spaceplan.core.lib.rules import RuleSet
from spaceplan.core.lib_aux.hashing import sha256_of, sha256_text

GENERATOR_NAME = "spaceplan"
RESERVED_BLOCKS = ("graphs", "sized_program", "geometric_scheme", "metrics")


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


def _zoning_warnings(zoning: dict | None, corrections: dict | None) -> list[str]:
    warnings = []
    for option in (zoning or {}).get("options", []):
        if option["status"] == "no_valid_scheme":
            hint = ""
            fits = [d for d in option.get("diagnostics", []) if not d["front_fits"]]
            if fits and len(fits) == len(option.get("diagnostics", [])):
                d = min(fits, key=lambda d: d["front_min_demand_ft"] - d["front_width_ft"])
                hint = (f" (access side needs {d['front_min_demand_ft']:.1f} ft for {', '.join(d['demand_by_cell'])}; "
                        f"footprint is {d['front_width_ft']:.1f} ft wide)")
            warnings.append(f"zoning {option['option_id']}: no topology satisfies the hard constraints{hint}")
    c = corrections
    if c is not None:
        if c["applied"]:
            warnings.append(
                f"minimal correction for n1 ({c['triggered_by']}): {', '.join(c['applied']['combo']['labels'])} "
                f"(cost {c['applied']['combo']['cost']:g}); see corrections.applied")
        else:
            warnings.append(f"no correction found for n1 ({c['triggered_by']}) within the evaluated combinations")
    return warnings


def package_from_contracts(
    brief: dict,
    rs: RuleSet,
    scope: dict,
    program: dict,
    strategy: str | None = None,
    lot_capacity: dict | None = None,
    site_plan: dict | None = None,
    zoning_scheme: dict | None = None,
) -> dict:
    """Package (schema 0.9) from the module contracts; `scope` is the scope block (lotcap's for a house in scope)."""
    review = read_contract(program, "program")["program_review"]
    lot = read_contract(lot_capacity, "lot_capacity") if lot_capacity is not None else None
    site = read_contract(site_plan, "site_plan") if site_plan is not None else {"site_partition": None, "warnings": []}
    zoning = (read_contract(zoning_scheme, "zoning_scheme") if zoning_scheme is not None
              else {"zoning": None, "unit": None, "corrections": None})
    package: dict[str, Any] = {
        "meta": _meta(brief, rs, review, strategy),
        "scope": scope,
        "lot_metrics": None,
        "boundaries": [],
        "rule_variants": [],
        "lot_conformity": [],
        "capacity": None,
        "realizable_capacity": [],
        "sensitivity": None,
        "site_partition": site["site_partition"],
        "zoning": zoning["zoning"],
        "unit": zoning["unit"],
        "corrections": zoning["corrections"],
        "program_review": review,
        "warnings": [],
    }
    if lot is not None:
        package.update({k: lot[k] for k in ("lot_metrics", "boundaries", "rule_variants", "lot_conformity",
                                            "capacity", "realizable_capacity", "sensitivity")})
        package["warnings"] = list(lot["warnings"])
    package["warnings"].extend(site.get("warnings", []))
    package["warnings"].extend(_zoning_warnings(zoning["zoning"], zoning["corrections"]))
    if not review["buildable_as_stated"]:
        package["warnings"].append(
            f"program review: {review['counts']['error']} error(s); see program_review.findings"
        )
    for block in RESERVED_BLOCKS:
        package[block] = None
    return package_json(package)
