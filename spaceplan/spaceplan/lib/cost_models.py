"""Interchangeable relative cost models (step 6.5b).

A cost model reads only a QuantitySheet and a point of parameters (`coef:<class>`,
`form:<factor>`) and returns a dimensionless amount. The index normalizes that amount by the
same model evaluated on a reference sheet, so the reference is 1 in every model:

    base      gross interior area                         (no parameters)
    weighted  sum(area x coef) over interior and exterior classes
    shape     weighted x product of the form factors that apply (floors, stepped or
              polygonal footprint, hillside)

A future real cost module implements the same protocol and reads the same sheet. No model
knows money: parameters are relative, dimensionless and come from the catalog with status.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from spaceplan.lib.catalog import Catalog
from spaceplan.lib.quantities import QuantitySheet
from spaceplan.lib_aux.weighted import product, weighted_sum

COEF, FORM = "coef:", "form:"
FLOOR_FACTORS = {2: "two_floors", 3: "three_floors"}
FORM_FACTORS = {"stepped": "stepped_footprint", "polygonal": "polygonal_footprint"}


class CostModel(Protocol):
    name: str

    def parameters(self, cost_index: dict) -> dict[str, tuple[float, float, float]]: ...

    def evaluate(self, sheet: QuantitySheet, point: dict[str, float], cost_index: dict) -> tuple[float, dict]: ...


def _ranges(group: dict, prefix: str) -> dict[str, tuple[float, float, float]]:
    return {prefix + k: (v["min"], v["mode"], v["max"]) for k, v in group.items()}


def applicable_form_factors(sheet: QuantitySheet, cost_index: dict) -> list[str]:
    names = []
    if sheet.floors in FLOOR_FACTORS:
        names.append(FLOOR_FACTORS[sheet.floors])
    if sheet.footprint_form in FORM_FACTORS:
        names.append(FORM_FACTORS[sheet.footprint_form])
    if sheet.mean_slope is not None and sheet.mean_slope >= cost_index["hillside_mean_slope_threshold"]:
        names.append("hillside")
    return names


@dataclass(frozen=True)
class BaseAreaModel:
    name: str = "base"

    def parameters(self, cost_index: dict) -> dict[str, tuple[float, float, float]]:
        return {}

    def evaluate(self, sheet, point, cost_index):
        return sheet.gross_area, {"gross_area_sqft": sheet.gross_area}


@dataclass(frozen=True)
class WeightedAreaModel:
    name: str = "weighted"

    def parameters(self, cost_index):
        return _ranges(cost_index["coefficients"], COEF)

    def evaluate(self, sheet, point, cost_index):
        amounts = {**sheet.interior_amounts(), **sheet.exterior_amounts()}
        weights = {k[len(COEF):]: v for k, v in point.items() if k.startswith(COEF)}
        total, parts = weighted_sum(amounts, weights)
        return total, {"by_class": parts}


@dataclass(frozen=True)
class ShapeAdjustedModel:
    name: str = "shape"

    def parameters(self, cost_index):
        return {**_ranges(cost_index["coefficients"], COEF), **_ranges(cost_index["form_factors"], FORM)}

    def evaluate(self, sheet, point, cost_index):
        weighted, detail = WeightedAreaModel().evaluate(sheet, point, cost_index)
        factors = {f: point[FORM + f] for f in applicable_form_factors(sheet, cost_index)}
        return weighted * product(factors), {**detail, "form_factors": factors}


MODELS: dict[str, CostModel] = {m.name: m for m in (BaseAreaModel(), WeightedAreaModel(), ShapeAdjustedModel())}


def get_cost_model(name: str) -> CostModel:
    try:
        return MODELS[name]
    except KeyError as exc:
        raise ValueError(f"unknown cost model {name!r}; known: {', '.join(MODELS)}") from exc


def mode_point(model: CostModel, cost_index: dict) -> dict[str, float]:
    return {k: v[1] for k, v in model.parameters(cost_index).items()}


def relative_index(model: CostModel, sheet: QuantitySheet, reference: QuantitySheet, cost_index: dict,
                   point: dict[str, float] | None = None) -> float:
    point = mode_point(model, cost_index) if point is None else point
    return model.evaluate(sheet, point, cost_index)[0] / model.evaluate(reference, point, cost_index)[0]


def evaluate_all(catalog: Catalog, sheet: QuantitySheet, reference: QuantitySheet,
                 models: tuple[str, ...] | None = None) -> dict[str, dict]:
    """Index of the sheet under every model at the most likely parameters, with its breakdown."""
    ci = catalog.data["cost_index"]
    out = {}
    for name in models or tuple(ci["models"]):
        model = get_cost_model(name)
        point = mode_point(model, ci)
        amount, detail = model.evaluate(sheet, point, ci)
        ref_amount, _ = model.evaluate(reference, point, ci)
        out[name] = {"index": amount / ref_amount, "detail": detail}
    return out
