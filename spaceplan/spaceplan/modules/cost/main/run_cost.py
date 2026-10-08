"""Workflow for step 6.5b: options -> quantity sheets -> relative index -> budget -> tornado.

Two readings of the same index:
    lot                 1 = the lot's normative maximum gross area (capacity.gross_area_max) built
                        with the reference mix and form; used inside run_capacity.
    reference_dwelling  1 = the catalog reference dwelling; used without a lot (household command)
                        and to compare lots.
The index is comparative, never a quote: no model knows money.
"""

from __future__ import annotations

from spaceplan.core.lib.catalog import Catalog
from spaceplan.core.lib.enums import HOUSEHOLD_TIERS as TIERS
from spaceplan.modules.cost.lib.budget import assess_budget, resolve_budget
from spaceplan.modules.cost.lib.cost_models import evaluate_all, get_cost_model
from spaceplan.modules.cost.lib.cost_sensitivity import tornado
from spaceplan.modules.cost.lib.quantities import build_sheet, reference_sheet

LOT, REFERENCE_DWELLING = "lot", "reference_dwelling"
SENSITIVITY_MODEL = "shape"


def _sources(catalog: Catalog) -> dict:
    ci = catalog.data["cost_index"]
    return {"catalog_id": catalog.catalog_id, "catalog_version": catalog.version,
            "status": ci["source"]["status"], "citation": ci["source"]["citation"]}


def _option_entry(catalog, sheet, reference, model_name: str, kind: str) -> dict:
    by_model = evaluate_all(catalog, sheet, reference)
    return {"label": sheet.label, "kind": kind, "index": round(by_model[model_name]["index"], 4),
            "by_model": {k: round(v["index"], 4) for k, v in by_model.items()},
            "breakdown": by_model[model_name]["detail"], "quantities": sheet.to_dict()}


def _block(catalog, reading, reference, model_name, entries, sheets, budget_raw, minimum_label) -> dict:
    ci = catalog.data["cost_index"]
    resolved = resolve_budget(ci, budget_raw)
    indices = {e["label"]: e["index"] for e in entries}
    sens_model = get_cost_model(SENSITIVITY_MODEL)
    measured = [s for s in sheets if s.footprint.basis == "measured"]
    pair = measured[:2] if len(measured) >= 2 else sheets[:1]
    sens = tornado(sens_model, ci, reference, *pair) if pair else None
    return {
        "legend": ci["legend"],
        "model": model_name,
        "reading": reading,
        "reference": {"label": reference.label, "gross_area_sqft": round(reference.gross_area, 3),
                      "mix": ci["reference_mix"], "form": "one floor, rectangle, flat, no exterior works"},
        "budget": assess_budget(resolved, indices, reading, minimum_label),
        "options": entries,
        "tornado": sens,
        "sources": _sources(catalog),
    }


def household_cost(catalog: Catalog, stage: dict, model: str | None = None) -> dict:
    """Reference-dwelling reading of the tier programs of a household stage (no lot: one floor, estimated)."""
    ci = catalog.data["cost_index"]
    model_name = model or ci["default_model"]
    reference = reference_sheet(catalog, ci["reference_dwelling_gross_sqft"], "reference_dwelling")
    sheets = [build_sheet(catalog, stage["programs"][t], t) for t in TIERS]
    entries = [_option_entry(catalog, s, reference, model_name, "tier") for s in sheets]
    return _block(catalog, REFERENCE_DWELLING, reference, model_name, entries, sheets, None, None)


def package_cost(catalog: Catalog, brief: dict, package: dict, tier_programs: dict | None = None,
                 model: str | None = None, budget: dict | None = None) -> dict | None:
    """Lot reading for the brief program on every site option, and for each household tier when given."""
    capacity = package.get("capacity")
    if not capacity or not capacity.get("gross_area_max") or capacity["gross_area_max"].get("value") is None:
        return None
    ci = catalog.data["cost_index"]
    model_name = model or (budget or {}).get("cost_model") or ci["default_model"]
    reference = reference_sheet(catalog, capacity["gross_area_max"]["value"], "lot_normative_max")
    strategy = package["meta"].get("realization_strategy")
    slope = (brief.get("terrain") or {}).get("mean_slope")
    sheets, entries = [], []
    for option in (package.get("site_partition") or {}).get("options", []):
        if "zones" not in option:
            continue
        sheet = build_sheet(catalog, brief["program"], option["option_id"], site_option=option, strategy=strategy,
                            mean_slope=slope)
        sheets.append(sheet)
        entry = _option_entry(catalog, sheet, reference, model_name, "site_option")
        entry["site_feasible"] = option["feasible"]
        entries.append(entry)
    site_options = (package.get("site_partition") or {}).get("options", [])
    floors = sorted({o["floors"] for o in site_options}) or [1]
    minimum_label = None
    for tier in TIERS if tier_programs else ():
        for n in floors:
            label = f"{tier}@{n}f"
            sheet = build_sheet(catalog, tier_programs[tier], label, floors=n, strategy=strategy, mean_slope=slope)
            sheets.append(sheet)
            entries.append(_option_entry(catalog, sheet, reference, model_name, "household_tier"))
            if tier == TIERS[0] and minimum_label is None:
                minimum_label = label
    return _block(catalog, LOT, reference, model_name, entries, sheets, budget, minimum_label)
