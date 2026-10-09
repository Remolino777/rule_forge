"""Workflow of the zoning module: one-floor zoning of a house (plus the minimal correction) or of an apartment.

    house:     site options + frame + envelope profile -> zones and spaces per option (strategy A/B)
               -> [corrections] multivariable minimal correction when the one-floor option does not zone
    apartment: unit polygon -> zoning with the apartment profile (strategy A)

Refactor tanda 3: the calls the capacity pipeline made to the zoning library, moved here without changes so
the pipeline only composes module workflows.
"""

from __future__ import annotations

from spaceplan.core.lib.enums import Strategy
from spaceplan.modules.zoning.lib.realization import get_strategy
from spaceplan.modules.zoning.lib.unit import build_unit
from spaceplan.modules.zoning.lib.zoning import zone_site_options, zone_unit
from spaceplan.modules.zoning.main.run_corrections import search_corrections


def zone_house(brief: dict, rs, catalog, setup, site: dict, strategy_name: str, selection: dict,
               corrections: bool = True) -> tuple[dict, dict | None]:
    """(zoning of the site options, correction or None); `setup` is lotcap's LotSetup."""
    zoning = zone_site_options(catalog, brief, setup.frame, site, get_strategy(strategy_name), setup.profile)
    zoning["selection"] = selection
    correction = None
    if corrections and setup.profile is not None:
        rect = setup.capacity.realizable[0]
        correction = search_corrections(brief, rs, catalog, setup.lot, setup.boundaries, setup.evaluation,
                                        setup.capacity, setup.profile, rect["width_ft"], strategy_name, site, zoning)
    return zoning, correction


def zone_apartment(brief: dict, catalog) -> tuple[object, dict]:
    """(unit, zoning) of an apartment brief."""
    unit = build_unit(brief["unit"])
    zoning = zone_unit(catalog, brief, unit, get_strategy(Strategy.A_INSCRIBED_RECTANGLE))
    return unit, zoning


__all__ = ["zone_apartment", "zone_house"]
