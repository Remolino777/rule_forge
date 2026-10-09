"""Workflow of the site module: site partition per number of floors (layer 1) and backyard (layer 1d).

Refactor tanda 3: the calls the capacity pipeline made to the site library, moved here without changes so
the pipeline only composes module workflows.
"""

from __future__ import annotations

from spaceplan.modules.site.lib.backyard import backyard_for_site
from spaceplan.modules.site.lib.site_partition import build_site_partition


def plan_site(rs, catalog, brief: dict, setup, strategy_name: str) -> tuple[dict, list[str]]:
    """Site options per number of floors on a prepared lot (`setup` is lotcap's LotSetup)."""
    return build_site_partition(rs, catalog, brief, setup.lot, setup.boundaries, setup.evaluation, setup.capacity,
                                strategy_name)


def plan_site_backyard(catalog, rs, brief: dict, setup, site: dict, zoning: dict) -> None:
    """Backyard of every buildable site option (in place), using the best zoning scheme when there is one."""
    backyard_for_site(catalog, rs, brief, setup.lot, setup.boundaries, site, zoning)


__all__ = ["plan_site", "plan_site_backyard"]
