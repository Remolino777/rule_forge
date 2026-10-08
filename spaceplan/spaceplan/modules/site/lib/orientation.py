"""Orientation (spaceplan v1.1 section 7): north is a reference vector, not a graph node.

Each lot line and each footprint facade receives an exposure profile (sun, morning light,
afternoon shade, street exposure). Zones score facades by preference x exposure; the
score per unit length feeds the zoning layer (step 5).
"""

from __future__ import annotations

import math

from spaceplan.modules.lotcap.lib.boundaries import BoundaryModel
from spaceplan.core.lib.catalog import Catalog
from spaceplan.core.lib.enums import BoundaryClass
from spaceplan.modules.lotcap.lib.lot import Lot
from spaceplan.core.lib_aux.geometry import Frame

STREET_CLASSES = (BoundaryClass.FRONT.value, BoundaryClass.STREET_SIDE.value)
ZONE_WEIGHT_KEYS = ("sun", "morning_light", "street_privacy")


def compass_azimuth(bearing_deg: float, north_azimuth_deg: float) -> float:
    """Drawing bearing (clockwise from +y) -> compass azimuth (clockwise from north)."""
    return (bearing_deg - north_azimuth_deg) % 360.0


def exposure(azimuth_deg: float, latitude_deg: float, model: dict) -> dict[str, float]:
    az = math.radians(azimuth_deg)
    equator_az = math.radians(180.0 if latitude_deg >= 0 else 0.0)
    w = min(1.0, abs(latitude_deg) / model["equator_weight_full_at_lat_deg"])
    sun = w * max(0.0, math.cos(az - equator_az)) + (1.0 - w) * abs(math.sin(az))
    morning = max(0.0, math.cos(az - math.radians(model["morning_azimuth_deg"])))
    afternoon = max(0.0, math.cos(az - math.radians(model["afternoon_azimuth_deg"])))
    return {"sun": sun, "morning_light": morning, "afternoon_shade": 1.0 - afternoon}


def local_normal_azimuth(frame: Frame, nx: float, ny: float, north_azimuth_deg: float) -> float:
    """Compass azimuth of a direction given in the lot's local frame."""
    c, s = math.cos(frame.angle), math.sin(frame.angle)
    wx, wy = c * nx - s * ny, s * nx + c * ny
    return compass_azimuth(math.degrees(math.atan2(wx, wy)) % 360.0, north_azimuth_deg)


def boundary_exposures(lot: Lot, boundaries: BoundaryModel, brief: dict, model: dict) -> list[dict]:
    north, lat = brief["orientation"]["north_azimuth_deg"], brief["orientation"]["latitude_deg"]
    rows = []
    for edge in lot.edges:
        cls = boundaries.assignments[edge.edge_id].boundary_class
        az = compass_azimuth(edge.outward_bearing_deg, north)
        rows.append(
            {
                "edge_id": edge.edge_id,
                "boundary_class": cls,
                "outward_azimuth_deg": az,
                **exposure(az, lat, model),
                "street_exposure": 1.0 if cls in STREET_CLASSES else 0.0,
            }
        )
    return rows


def facade_affinity(catalog: Catalog, facades: list[dict]) -> dict[str, dict[str, float]]:
    """affinity[zone][facade] = sum(pref_k * exposure_k) / sum(pref_k); 0 for indifferent zones."""
    out: dict[str, dict[str, float]] = {}
    for zone in catalog.data["zones"]:
        prefs = zone["orientation"]
        total = sum(prefs[k] for k in ZONE_WEIGHT_KEYS)
        row = {}
        for f in facades:
            exposures = {"sun": f["sun"], "morning_light": f["morning_light"],
                         "street_privacy": 1.0 - f["street_exposure"]}
            row[f["facade_id"]] = 0.0 if total == 0 else sum(prefs[k] * exposures[k] for k in ZONE_WEIGHT_KEYS) / total
        out[zone["zone"]] = row
    return out
