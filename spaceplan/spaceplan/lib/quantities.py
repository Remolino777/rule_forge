"""Quantity sheet (step 6.5b): what any cost, carbon or energy model needs to read from an option.

The sheet is the contract with future cost modules: they read it, never the program or the
geometry. Every item records its basis:

    measured   taken from the site geometry of the option
    derived    computed from the program (areas, counts) with catalog parameters
    estimated  heuristic stand-in when the geometry is not available yet
    reference  synthetic sheet used to normalize the index
    not_available

Area classes come from the catalog (`cost_index.area_classes`); wet spaces form their own class.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from spaceplan.lib.catalog import Catalog
from spaceplan.lib.enums import Strategy

MEASURED, DERIVED, ESTIMATED, REFERENCE, NOT_AVAILABLE = "measured", "derived", "estimated", "reference", "not_available"
BASIS_RANK = {REFERENCE: 0, MEASURED: 0, DERIVED: 1, ESTIMATED: 2, NOT_AVAILABLE: 3}
STRATEGY_FORM = {
    Strategy.A_INSCRIBED_RECTANGLE.value: "rectangle",
    Strategy.B_STEPPED_FOOTPRINT.value: "stepped",
    Strategy.B_POLYGONAL_FOOTPRINT.value: "polygonal",
}


@dataclass(frozen=True)
class Item:
    value: float
    unit: str
    basis: str
    note: str | None = None

    def to_dict(self) -> dict:
        out = {"value": round(self.value, 3), "unit": self.unit, "basis": self.basis}
        if self.note:
            out["note"] = self.note
        return out


@dataclass(frozen=True)
class QuantitySheet:
    label: str
    area_by_class: dict[str, Item]
    exterior_by_class: dict[str, Item]
    floors: int
    area_by_floor: tuple[Item, ...]
    footprint: Item
    roof: Item
    facade_perimeter: Item
    stairs: int
    wet_spaces: int
    wet_cores: Item
    footprint_form: str
    mean_slope: float | None
    notes: tuple[str, ...] = field(default_factory=tuple)

    @property
    def gross_area(self) -> float:
        return math.fsum(i.value for i in self.area_by_class.values())

    def interior_amounts(self) -> dict[str, float]:
        return {k: i.value for k, i in self.area_by_class.items()}

    def exterior_amounts(self) -> dict[str, float]:
        return {k: i.value for k, i in self.exterior_by_class.items()}

    @property
    def confidence(self) -> str:
        """Worst basis among the items that enter a cost model."""
        items = [*self.area_by_class.values(), self.footprint, self.facade_perimeter, *self.exterior_by_class.values()]
        relevant = [i.basis for i in items if i.basis != NOT_AVAILABLE] or [NOT_AVAILABLE]
        return max(relevant, key=BASIS_RANK.__getitem__)

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "gross_area_sqft": round(self.gross_area, 3),
            "area_by_class": {k: v.to_dict() for k, v in sorted(self.area_by_class.items())},
            "exterior_by_class": {k: v.to_dict() for k, v in sorted(self.exterior_by_class.items())},
            "floors": self.floors,
            "area_by_floor": [i.to_dict() for i in self.area_by_floor],
            "footprint": self.footprint.to_dict(),
            "roof": self.roof.to_dict(),
            "facade_perimeter": self.facade_perimeter.to_dict(),
            "stairs": self.stairs,
            "wet_spaces": self.wet_spaces,
            "wet_cores": self.wet_cores.to_dict(),
            "footprint_form": self.footprint_form,
            "mean_slope": self.mean_slope,
            "confidence": self.confidence,
            "notes": list(self.notes),
        }


def area_class(cost_index: dict, space: dict) -> str:
    classes = cost_index["area_classes"]
    if space["wet"] and space["zone"] != "garage":
        return classes["wet_class"]
    return classes["zone_class"][space["zone"]]


def rectangle_perimeter(area: float, aspect: float) -> float:
    if area <= 0:
        return 0.0
    return 2 * (math.sqrt(area * aspect) + math.sqrt(area / aspect))


def _zone_area(zones: dict, name: str) -> float:
    zone = zones.get(name)
    if zone is None:
        return 0.0
    return float(zone["area_sqft"] if isinstance(zone, dict) else zone)


def build_sheet(
    catalog: Catalog,
    program: dict,
    label: str,
    floors: int = 1,
    site_option: dict | None = None,
    strategy: str | None = None,
    mean_slope: float | None = None,
    floor_shares: list[float] | None = None,
) -> QuantitySheet:
    """Sheet for a program built on `floors` floors, measured from a site option when one is given.

    floor_shares (step 6.6): share of the gross area on each floor when a vertical scheme splits the
    program unevenly; the ground floor then sets the footprint (derived, not measured)."""
    ci = catalog.data["cost_index"]
    gross_factor = program.get("gross_factor", 1.0)
    floors = site_option["floors"] if site_option else floors
    net: dict[str, float] = {}
    wet_spaces = 0
    for s in program["spaces"]:
        cls = area_class(ci, s)
        net[cls] = net.get(cls, 0.0) + s["target_area_sqft"]
        wet_spaces += cls == ci["area_classes"]["wet_class"]
    declared = program.get("required_gross_area_sqft")
    scale = gross_factor
    notes = []
    if declared:
        scale = declared / math.fsum(net.values())
        notes.append(f"class areas scaled to the declared gross {declared:g} sq ft")
    areas = {cls: Item(a * scale, "sq_ft", DERIVED) for cls, a in net.items()}
    has_stair = any(s.get("space_type") == ci["estimates"]["stair_space_type"] for s in program["spaces"])
    stairs = 1 if floors > 1 else 0
    if floors > 1 and not has_stair:
        stair = catalog.space_type(ci["estimates"]["stair_space_type"])["area"]["target"] * floors
        circ = ci["area_classes"]["zone_class"]["circulation"]
        prev = areas.get(circ, Item(0.0, "sq_ft", DERIVED)).value
        areas[circ] = Item(prev + stair, "sq_ft", DERIVED, f"includes the stair repeated on {floors} floors")
        notes.append(f"stair added: {stair:g} sq ft over {floors} floors")
    gross = math.fsum(i.value for i in areas.values())
    aspect = ci["estimates"]["footprint_aspect_ratio"]
    if site_option and site_option.get("footprint_area_sqft"):
        footprint = Item(site_option["footprint_area_sqft"], "sq_ft", MEASURED)
        w, d = site_option.get("footprint_width_ft"), site_option.get("footprint_depth_ft")
        perimeter = (Item(2 * (w + d), "ft", MEASURED, "bounding dimensions of the footprint") if w and d else
                     Item(rectangle_perimeter(footprint.value, aspect), "ft", ESTIMATED))
        zones = site_option.get("zones") or {}
        paving = Item(_zone_area(zones, "driveway") + _zone_area(zones, "walkway"), "sq_ft", MEASURED)
        deck = Item(_zone_area(zones, "entry_deck"), "sq_ft", MEASURED)
        green = {e["element"] for e in catalog.data["backyard_elements"] if e["counts_as_green"]}
        placed = [e for e in (site_option.get("backyard") or {}).get("elements", [])
                  if e["status"] == "placed" and e["element"] not in green]
        backyard = Item(math.fsum(e["area_sqft"] for e in placed), "sq_ft",
                        MEASURED if site_option.get("backyard") else NOT_AVAILABLE,
                        "placed non-green backyard elements" if placed else None)
    elif floor_shares:
        footprint = Item(gross * floor_shares[0], "sq_ft", DERIVED, "ground floor of the vertical scheme")
        perimeter = Item(rectangle_perimeter(footprint.value, aspect), "ft", ESTIMATED,
                         f"rectangle with aspect ratio {aspect:g}")
        paving = Item(0.0, "sq_ft", NOT_AVAILABLE)
        deck = Item(0.0, "sq_ft", NOT_AVAILABLE)
        backyard = Item(0.0, "sq_ft", NOT_AVAILABLE)
    else:
        footprint = Item(gross / floors, "sq_ft", ESTIMATED, "gross area split evenly by floor")
        perimeter = Item(rectangle_perimeter(footprint.value, aspect), "ft", ESTIMATED,
                         f"rectangle with aspect ratio {aspect:g}")
        paving = Item(0.0, "sq_ft", NOT_AVAILABLE)
        deck = Item(0.0, "sq_ft", NOT_AVAILABLE)
        backyard = Item(0.0, "sq_ft", NOT_AVAILABLE)
    if floor_shares:
        if len(floor_shares) != floors or abs(sum(floor_shares) - 1) > 1e-6:
            raise ValueError("floor_shares must have one share per floor and sum to 1")
        by_floor = tuple(Item(gross * f, "sq_ft", DERIVED) for f in floor_shares)
    else:
        by_floor = tuple(Item(gross / floors, "sq_ft", ESTIMATED) for _ in range(floors))
    form = STRATEGY_FORM.get(strategy or "", "rectangle")
    return QuantitySheet(
        label=label, area_by_class=areas, exterior_by_class={"paving": paving, "deck": deck, "backyard": backyard}, floors=floors,
        area_by_floor=by_floor, footprint=footprint,
        roof=Item(footprint.value, "sq_ft", footprint.basis, "flat-plate assumption: roof = footprint"),
        facade_perimeter=perimeter, stairs=stairs, wet_spaces=wet_spaces,
        wet_cores=Item(float(min(floors, wet_spaces)), "count", ESTIMATED, "one wet core per floor with wet spaces"),
        footprint_form=form, mean_slope=mean_slope, notes=tuple(notes),
    )


def reference_sheet(catalog: Catalog, gross_sqft: float, label: str) -> QuantitySheet:
    """Synthetic normalizer: reference mix, one floor, rectangle, flat, no exterior works."""
    ci = catalog.data["cost_index"]
    areas = {cls: Item(gross_sqft * f, "sq_ft", REFERENCE) for cls, f in ci["reference_mix"].items()}
    aspect = ci["estimates"]["footprint_aspect_ratio"]
    footprint = Item(gross_sqft, "sq_ft", REFERENCE)
    return QuantitySheet(
        label=label, area_by_class=areas,
        exterior_by_class={c: Item(0.0, "sq_ft", REFERENCE) for c in ci["area_classes"]["exterior_classes"]},
        floors=1, area_by_floor=(Item(gross_sqft, "sq_ft", REFERENCE),), footprint=footprint, roof=footprint,
        facade_perimeter=Item(rectangle_perimeter(gross_sqft, aspect), "ft", REFERENCE), stairs=0, wet_spaces=0,
        wet_cores=Item(1.0, "count", REFERENCE), footprint_form="rectangle", mean_slope=0.0,
    )
