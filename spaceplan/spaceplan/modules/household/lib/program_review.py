"""Program review: brief program vs catalog ranges and CRC habitability minima.

Produces a summary (net/gross areas per zone, habitable spaces that need an exterior edge,
placement order) and findings with severity, status and source. Findings never block the
capacity layer; errors tell the client the program is not buildable as stated.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass

from spaceplan.core.lib.catalog import Catalog
from spaceplan.core.lib.enums import DEFAULT_GROSS_FACTOR, Zone
from spaceplan.core.lib.rules import RuleSet
from spaceplan.core.lib_aux.quantity import PROVISIONAL, VERIFIED

HABITABLE_AREA = "C01-HABITABLE-AREA"
HABITABLE_DIMENSION = "C01-HABITABLE-DIMENSION"
GLAZING = "C03-GLAZING"
VENTILATION = "C03-VENTILATION"
EXEMPT_VARIANT = "kitchen_exempt"

ERROR, WARNING, INFO = "error", "warning", "info"


@dataclass(frozen=True)
class Finding:
    check_id: str
    severity: str
    subject: str
    message: str
    status: str
    source: str

    def to_dict(self) -> dict:
        return asdict(self)


def _catalog_tag(catalog: Catalog, entry: dict) -> tuple[str, str]:
    src = catalog.source_of(entry)
    return f"catalog:{catalog.catalog_id}@{catalog.version} ({src['citation']})", src["status"]


def _is_habitable(catalog: Catalog, space: dict) -> bool:
    if catalog.has_space_type(space.get("space_type")):
        return catalog.space_type(space["space_type"])["habitable"]
    return space["zone"] in (Zone.SOCIAL, Zone.PRIVATE, Zone.KITCHEN) and not space["wet"] and space["scale"] in (
        "large",
        "normal",
    )


def _exempt(crc: RuleSet, rule_id: str, space: dict) -> bool:
    return space.get("space_type") in crc.params(rule_id, EXEMPT_VARIANT)["exempt_space_types"]


def review_program(catalog: Catalog, crc: RuleSet, program: dict) -> dict:
    findings: list[Finding] = []
    spaces = program["spaces"]
    ids = {s["space_id"] for s in spaces}
    crc_area = float(crc.rule(HABITABLE_AREA)["value"])
    crc_side = float(crc.rule(HABITABLE_DIMENSION)["value"])

    for s in spaces:
        sid, stype = s["space_id"], s.get("space_type")
        typed = catalog.has_space_type(stype)
        if stype is None:
            findings.append(Finding("space_type_missing", INFO, sid, "no space_type: only scale checks apply",
                                    VERIFIED, "brief"))
        elif not typed:
            findings.append(Finding("space_type_unknown", ERROR, sid, f"space_type {stype!r} is not in the catalog",
                                    VERIFIED, f"catalog:{catalog.catalog_id}"))
        scale = catalog.scale(s["scale"])
        if typed:
            t = catalog.space_type(stype)
            tag, status = _catalog_tag(catalog, t)
            if t["zone"] != s["zone"]:
                findings.append(Finding("zone_mismatch", ERROR, sid,
                                        f"{stype} belongs to zone {t['zone']!r}, brief says {s['zone']!r}", status, tag))
            if t["scale"] != s["scale"]:
                findings.append(Finding("scale_mismatch", WARNING, sid,
                                        f"{stype} is {t['scale']!r} in the catalog, brief says {s['scale']!r}", status, tag))
            a = t["area"]
            if not a["min"] <= s["target_area_sqft"] <= a["max"]:
                findings.append(Finding("type_range", WARNING, sid,
                                        f"target {s['target_area_sqft']:g} outside {stype} range {a['min']:g}-{a['max']:g} sq ft",
                                        status, tag))
            exception = t.get("scale_range_exception")
        else:
            exception, tag, status = None, f"catalog:{catalog.catalog_id}", PROVISIONAL
        lo, hi = scale["area_min"], scale["area_max"]
        if lo is not None and not exception and not lo <= s["target_area_sqft"] <= hi:
            findings.append(Finding("scale_range", WARNING, sid,
                                    f"target {s['target_area_sqft']:g} outside {s['scale']} range {lo:g}-{hi:g} sq ft",
                                    *_catalog_tag(catalog, scale)))

        if _is_habitable(catalog, s) and not _exempt(crc, HABITABLE_AREA, s):
            smallest = min(s["min_area_sqft"], s["target_area_sqft"])
            if smallest < crc_area:
                findings.append(Finding("crc_habitable_area", ERROR, sid,
                                        f"habitable space allows {smallest:g} sq ft < {crc_area:g} sq ft",
                                        crc.status(HABITABLE_AREA), crc.source_tag(HABITABLE_AREA)))

        host = s.get("host_space_id")
        if host is not None and (host not in ids or host == sid):
            findings.append(Finding("host_unknown", ERROR, sid, f"host {host!r} is not another space of the program",
                                    VERIFIED, "brief"))
        if scale["topology"] == "satellite" and host is None:
            findings.append(Finding("satellite_without_host", WARNING, sid,
                                    "support-scale space without host_space_id; it would enter the topology",
                                    *_catalog_tag(catalog, scale)))

    zones = defaultdict(float)
    for s in spaces:
        zones[s["zone"]] += s["target_area_sqft"]
    garage_spaces = [s["space_id"] for s in spaces if s["zone"] == Zone.GARAGE]
    if program["garage_cars"] > 0 and not garage_spaces:
        findings.append(Finding("garage_missing", ERROR, "program",
                                f"garage_cars={program['garage_cars']} but no garage space", VERIFIED, "brief"))
    if program["garage_cars"] == 0 and garage_spaces:
        findings.append(Finding("garage_unexpected", WARNING, "program", "garage space with garage_cars=0",
                                VERIFIED, "brief"))
    if Zone.KITCHEN not in zones:
        findings.append(Finding("kitchen_missing", ERROR, "program", "no kitchen-zone space", VERIFIED, "brief"))
    bathrooms = [s for s in spaces if s["wet"] and s["zone"] in (Zone.PRIVATE, Zone.CIRCULATION)]
    if not bathrooms:
        findings.append(Finding("bathroom_missing", ERROR, "program", "no bathroom", VERIFIED, "brief"))

    by_zone = {}
    for zone, budget in program["zone_budgets"].items():
        net = zones.get(zone, 0.0)
        inside = budget["min_sqft"] <= net <= budget["max_sqft"]
        by_zone[zone] = {"net_target_sqft": net, "budget_min_sqft": budget["min_sqft"],
                         "budget_max_sqft": budget["max_sqft"], "within_budget": inside}
        if not inside:
            findings.append(Finding("zone_budget", WARNING, zone,
                                    f"targets sum {net:g} sq ft outside budget {budget['min_sqft']:g}-{budget['max_sqft']:g}",
                                    VERIFIED, "brief"))
    for zone, net in zones.items():
        by_zone.setdefault(zone, {"net_target_sqft": net, "budget_min_sqft": None,
                                  "budget_max_sqft": None, "within_budget": None})

    net_total = sum(zones.values())
    factor = program.get("gross_factor", DEFAULT_GROSS_FACTOR)
    declared = program.get("required_gross_area_sqft")
    if declared is not None and declared < net_total:
        findings.append(Finding("gross_below_net", ERROR, "program",
                                f"declared gross {declared:g} sq ft is below the net program {net_total:g} sq ft",
                                VERIFIED, "brief"))

    habitable = [s["space_id"] for s in spaces if _is_habitable(catalog, s)]
    order = sorted(
        (s for s in spaces if catalog.scale(s["scale"])["placement_order"] is not None
         and catalog.scale(s["scale"])["topology"] == "node"),
        key=lambda s: (catalog.scale(s["scale"])["placement_order"], -s["target_area_sqft"], s["space_id"]),
    )
    counts = {sev: sum(f.severity == sev for f in findings) for sev in (ERROR, WARNING, INFO)}
    return {
        "catalog_id": catalog.catalog_id,
        "catalog_version": catalog.version,
        "catalog_sha256": catalog.sha256,
        "crc_ruleset_id": crc.ruleset_id,
        "crc_ruleset_sha256": crc.sha256,
        "summary": {
            "net_area_sqft": net_total,
            "gross_factor": factor,
            "gross_estimate_sqft": net_total * factor,
            "declared_gross_sqft": declared,
            "by_zone": by_zone,
            "habitable_spaces": habitable,
            "exterior_edge_required": [
                {"space_id": sid, "reason": f"{crc.source_tag(GLAZING)}; {crc.source_tag(VENTILATION)}",
                 "status": crc.status(GLAZING)}
                for sid in habitable
            ],
            "min_side_ft": {
                s["space_id"]: (None if _exempt(crc, HABITABLE_DIMENSION, s) else crc_side)
                for s in spaces if s["space_id"] in habitable
            },
            "satellites": {s["space_id"]: s.get("host_space_id") for s in spaces
                           if catalog.scale(s["scale"])["topology"] == "satellite"},
            "placement_order": [s["space_id"] for s in order],
        },
        "counts": counts,
        "buildable_as_stated": counts[ERROR] == 0,
        "findings": [f.to_dict() for f in findings],
    }
