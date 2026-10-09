"""Facade of the figure files (refactor tanda 3): visualize.py was split by topic into

    lot_site_plots     capacity and site partition (plot_capacity, plot_site)
    zoning_plots       one-floor zoning (plot_zoning)
    review_sheets      review sheet of a zoned option (plot_review_sheet, space_label_fn)
    portfolio_sheet    portfolio of program profiles (plot_portfolio_sheet, move_label)
    area_matrix_plots  area analysis per lot (plot_decision_map, plot_area_budget, plot_ic_io, plot_scheme_matrix)

Code imports those files; this facade keeps the old names (spaceplan.lib.visualize) and is removed in tanda 4.
"""

from __future__ import annotations

from pathlib import Path  # noqa: F401  (kept for the bridge)

from spaceplan.core.lib_aux.geometry import polygon_parts  # noqa: F401  (kept for the bridge)
from spaceplan.modules.lotcap.lib.boundaries import (
    BoundaryModel,  # noqa: F401  (kept for the bridge)
)
from spaceplan.modules.lotcap.lib.lot import Lot  # noqa: F401  (kept for the bridge)
from spaceplan.modules.viz.lib.area_matrix_plots import (  # noqa: F401
    EMPTY_FILL,
    FOCUS_HOUSEHOLDS,
    GRID,
    INK,
    INK2,
    METRIC_ABBR,
    MUTED,
    SCHEME_COLORS,
    SCHEME_MARKERS,
    SCHEME_ORDER,
    STATUS_CODE,
    STATUS_FILL,
    SURFACE,
    _fig_text,
    _lot_line,
    plot_area_budget,
    plot_decision_map,
    plot_ic_io,
    plot_scheme_matrix,
)
from spaceplan.modules.viz.lib.lot_site_plots import (  # noqa: F401
    CLASS_COLORS,
    ZONE_STYLE,
    plot_capacity,
    plot_site,
)
from spaceplan.modules.viz.lib.portfolio_sheet import (  # noqa: F401
    move_label,
    plot_portfolio_sheet,
)
from spaceplan.modules.viz.lib.review_sheets import (  # noqa: F401
    REVIEW_DOOR_COLORS,
    REVIEW_YARD_COLORS,
    REVIEW_ZONE_COLORS,
    plot_review_sheet,
    space_label_fn,
)
from spaceplan.modules.viz.lib.zoning_plots import (  # noqa: F401
    BACKYARD_COLORS,
    ZONE_COLORS,
    plot_zoning,
)
