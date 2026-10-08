"""Multivariable minimal correction (step 6).

When the one-floor option does not zone (or its site is not compliant), the design can usually be
rescued by changing a few things at once. The variables and their costs live in the catalog
(`corrections`): the realization strategy (geometry, cheap), a front recess behind the setback (costs
front yard, per foot) and the garage layout (program change, expensive). This module holds the pure
parts: the candidate combinations ordered by cost, the frontage test that prunes them before any
expensive run, and the program edits. The search loop that re-runs site partition and zoning lives in
main/run_corrections.py.
"""

from __future__ import annotations

import copy
import itertools
import math
from dataclasses import dataclass, field

from spaceplan.core.lib.catalog import Catalog, site_parameters
from spaceplan.core.lib.enums import Strategy, Zone
from spaceplan.core.lib_aux.section import SectionProfile

GARAGE_AS_BRIEF = "as_brief"
GARAGE_TANDEM = "tandem"
GARAGE_ONE_CAR = "one_car"
TANDEM_TYPE = "garage_2car_tandem"
ONE_CAR_TYPE = "garage_1car"


@dataclass(frozen=True)
class Combo:
    strategy: str
    garage: str
    recess_ft: float
    cost: float
    changes: int
    labels: tuple[str, ...] = field(default_factory=tuple)

    @property
    def key(self) -> str:
        return f"{self.strategy}|{self.garage}|recess_{self.recess_ft:g}"

    def as_dict(self) -> dict:
        return {"strategy": self.strategy, "garage_layout": self.garage, "front_recess_ft": self.recess_ft,
                "cost": round(self.cost, 4), "changes": self.changes, "labels": list(self.labels)}


# --------------------------------------------------------------------------- program edits


def _garage_space(program: dict) -> dict | None:
    return next((s for s in program["spaces"] if s["zone"] == Zone.GARAGE.value), None)


def garage_program(catalog: Catalog, program: dict, layout: str) -> dict | None:
    """Program with the garage changed to layout, or None when the change does not apply."""
    if layout == GARAGE_AS_BRIEF:
        return program
    garage = _garage_space(program)
    if garage is None or program["garage_cars"] < 1:
        return None
    if layout == GARAGE_TANDEM:
        if program["garage_cars"] != 2 or garage.get("space_type") == TANDEM_TYPE:
            return None
        new_type, cars = TANDEM_TYPE, 2
    elif layout == GARAGE_ONE_CAR:
        if program["garage_cars"] < 2:
            return None
        new_type, cars = ONE_CAR_TYPE, 1
    else:
        raise ValueError(f"unknown garage layout {layout!r}")
    t = catalog.space_type(new_type)
    out = copy.deepcopy(program)
    out["garage_cars"] = cars
    g = _garage_space(out)
    g.update(space_type=new_type, min_area_sqft=t["area"]["min"], target_area_sqft=t["area"]["target"])
    return out


def driveway_width(catalog: Catalog, program: dict) -> float:
    """Driveway width the program's garage needs on the front face (lanes x width per car)."""
    per_car = site_parameters(catalog, "driveway")["width_per_car_ft"]
    garage = _garage_space(program)
    cars = program["garage_cars"]
    if garage is None or cars == 0:
        return 0.0
    lanes = cars
    if catalog.has_space_type(garage.get("space_type")):
        lanes = min(cars, catalog.space_type(garage["space_type"]).get("lanes") or cars)
    return lanes * per_car


# --------------------------------------------------------------------------- frontage


def frontage_demand(diagnostics: list[dict], garage_width: float | None, garage_min_width: float = 0.0
                    ) -> float | None:
    """Least frontage any zoning variant needs (cells forced onto the access side), with the garage term
    replaced by the width the new garage needs. None when there is nothing to estimate from."""
    best = None
    for d in diagnostics:
        demand = dict(d["demand_by_cell"])
        if garage_width is not None:
            for cell in demand:
                if cell == Zone.GARAGE.value or cell.startswith(Zone.GARAGE.value + "_"):
                    demand[cell] = max(garage_width, garage_min_width)
        total = sum(demand.values())
        best = total if best is None else min(best, total)
    return best


def minimal_recess(profile: SectionProfile, demand: float, step: float, max_recess: float) -> float | None:
    """Smallest recess (rounded up to step) where the envelope section is at least demand wide."""
    y0 = profile.ymin
    if profile.width(y0) >= demand - 1e-9:
        return 0.0
    y = profile.y_for_width(demand, y0, min(profile.ymax, y0 + max_recess))
    if y is None:
        return None
    r = math.ceil((y - y0) / step - 1e-9) * step
    return r if r <= max_recess + 1e-9 else None


def garage_zone_min_width(catalog: Catalog) -> float:
    return next(z["min_width_ft"] for z in catalog.data["zones"] if z["zone"] == Zone.GARAGE.value)


def frontage_supply(strategy: str, recess: float, profile: SectionProfile, rect_width: float | None) -> float:
    if strategy == Strategy.A_INSCRIBED_RECTANGLE.value:
        return rect_width or 0.0
    return profile.width(profile.ymin + recess)


# --------------------------------------------------------------------------- combinations


def candidate_combos(catalog: Catalog, program: dict, profile: SectionProfile, diagnostics: dict[str, list[dict]],
                     baseline: tuple[str, str, float], extra_recesses: tuple[float, ...] = ()) -> list[Combo]:
    """Every (strategy, garage, recess) combination ordered by cost, then by number of changes.

    The recess is never arbitrary. For each garage variant and B strategy the candidates are: none; the
    smallest recess giving the frontage the variant needs, with the living room on the front line
    ("strict") or allowed on a shoulder ("relaxed"); and each extra recess the site asks for (e.g. moving
    the entry deck out of the front yard), alone or combined with the frontage recesses.
    """
    cfg = catalog.data["corrections"]
    variables = cfg["variables"]
    per_ft = variables["front_recess"]["cost_per_ft"]
    out = []
    for s_opt, g_opt in itertools.product(variables["strategy"], variables["garage_layout"]):
        prog = garage_program(catalog, program, g_opt["value"])
        if prog is None:
            continue
        recesses = {0.0}
        if s_opt["value"] != Strategy.A_INSCRIBED_RECTANGLE.value:
            frontage = []
            for kind in ("strict", "relaxed"):
                demand = frontage_demand(diagnostics.get(kind, []), driveway_width(catalog, prog),
                                         garage_zone_min_width(catalog))
                if demand is not None:
                    r = minimal_recess(profile, demand, cfg["recess_step_ft"], cfg["recess_max_ft"])
                    if r is not None:
                        frontage.append(r)
            step = cfg["recess_step_ft"]
            for r in frontage + [math.ceil(e / step - 1e-9) * step for e in extra_recesses]:
                recesses.add(r)
            for f in frontage:
                for e in extra_recesses:
                    recesses.add(max(f, math.ceil(e / step - 1e-9) * step))
            recesses = {r for r in recesses if r <= cfg["recess_max_ft"] + 1e-9}
        for r in sorted(recesses):
            labels = []
            if s_opt["value"] != baseline[0]:
                labels.append(f"strategy {s_opt['value']}")
            if g_opt["value"] != GARAGE_AS_BRIEF:
                labels.append(f"garage {g_opt['value']}")
            if r > 0:
                labels.append(f"front recess {r:g} ft")
            combo = Combo(s_opt["value"], g_opt["value"], r, s_opt["cost"] + g_opt["cost"] + per_ft * r,
                          len(labels), tuple(labels))
            if (combo.strategy, combo.garage, combo.recess_ft) == baseline:
                continue
            out.append(combo)
    out.sort(key=lambda c: (round(c.cost, 9), c.changes, c.key))
    return out


__all__ = ["Combo", "GARAGE_AS_BRIEF", "GARAGE_ONE_CAR", "GARAGE_TANDEM", "candidate_combos", "driveway_width",
           "frontage_demand", "frontage_supply", "garage_program", "garage_zone_min_width", "minimal_recess"]
