"""Geometric realization as an interchangeable piece (spaceplan v1.1 section 10; step 6).

Everything above this layer (zones, relations, areas, orientation) is shape independent. A strategy
turns a zone topology plus zone areas into cells inside a footprint domain. All strategies share the
same interface, so zoning and scoring never know which one ran.

  A  inscribed rectangle: one rectangle, two bands of columns, optional through column and spine.
  B  stepped footprint: the front band starts at the front line; every band is a rectangular step as
     wide as the envelope allows over its own depth, so the footprint widens (or narrows) with the lot.
     Where a step is wider than its neighbour a "shoulder" facade appears. The slivers between each
     step and the oblique lot lines are kept as a polygonal reserve (wedges), not discarded.
     Joint articulation: instead of a full spine, a corridor of the circulation width can be carved at
     the junction of the two steps, starting at the circulation column of the front band and running to
     one end over whole rear columns. It reaches the rooms behind without separating the open pair
     (dining, kitchen) on the other side; its area is taken from the rear cells it runs under.
  BP polygonal footprint: the bands are slabs of the envelope itself; columns are cut by area, so the
     edge cells follow the oblique lines (trapezoids). Every cell also carries its largest axis-aligned
     core rectangle: adjacency, minimum dimensions and the space level use the core (conservative);
     the rest of the cell polygon is handed to the spaces that touch it (polygonal extension).

Areas are exact by construction in all three.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from spaceplan.lib.enums import Strategy
from spaceplan.lib_aux.allocation import fit_lengths
from spaceplan.lib_aux.section import INF, SectionProfile

Rect = tuple[float, float, float, float]  # local frame: x0, y0, x1, y1 (front at y0)
Column = tuple[str, ...]  # zones stacked front-to-back inside one column of a band

SHOULDER_FACADES = ("front_shoulder", "rear_shoulder")
_TOL = 1e-6


@dataclass(frozen=True)
class ZoneTopology:
    """Columns of each band, left to right in the local frame; the front band faces the street."""

    front: tuple[Column, ...]
    rear: tuple[Column, ...]
    through: Column = ()          # full-depth column (front to rear) at one end
    through_side: str = "left"

    @property
    def key(self) -> str:
        def band(cols):
            return "|".join("+".join(c) for c in cols)

        prefix = f"T{self.through_side[0].upper()}:{'+'.join(self.through)}/" if self.through else ""
        return f"{prefix}F:{band(self.front)}/R:{band(self.rear)}"

    def zones(self) -> tuple[str, ...]:
        return tuple(self.through) + tuple(z for col in self.front + self.rear for z in col)


@dataclass(frozen=True)
class FootprintDomain:
    """Where a strategy may build.

    rect      nominal rectangle (strategy A builds exactly here; B uses it only as a bounding frame)
    profile   section profile of the setback envelope in the local frame (strategy B)
    y_front   front line of the footprint (envelope front plus any recess)
    """

    rect: Rect
    profile: SectionProfile | None = None
    y_front: float | None = None

    @property
    def y_max(self) -> float:
        return self.profile.ymax if self.profile else self.rect[3]


@dataclass(frozen=True)
class RealizedZones:
    cells: dict[str, Rect]          # A and B: the cell; BP: the cell's core rectangle
    front_depth: float
    rear_depth: float
    footprint: Rect                 # bounding rectangle of the realized footprint
    spine: Rect | None = None       # circulation corridor between the bands (its area was taken from every zone)
    facades: dict[str, dict[str, float]] | None = None   # exterior length per facade id (B / BP)
    front_spans: dict[str, tuple[float, float]] | None = None  # x-span of each cell on the front line (B / BP)
    extents: dict[str, Rect] | None = None   # BP: column x-range (may be infinite) and y-range of each cell
    steps: tuple[Rect, ...] = ()     # B: band rectangles; BP: band slabs (x-range of the core)
    wedges: tuple[dict, ...] = ()    # B: polygonal reserve between steps and lot lines
    areas: dict[str, float] = field(default_factory=dict)  # true cell areas (BP: polygon area)
    spine_area: float = 0.0
    mode: str = "rectangle"          # rectangle | polygonal
    joint: str | None = None         # B stepped: side the joint corridor runs to (spine holds its rectangle)

    @property
    def footprint_area(self) -> float:
        if self.areas:
            return sum(self.areas.values()) + self.spine_area
        x0, y0, x1, y1 = self.footprint
        return (x1 - x0) * (y1 - y0)

    def spine_contact(self, cell: str) -> float:
        if self.spine is None:
            return 0.0
        x0, y0, x1, y1 = self.cells[cell]
        sx0, sy0, sx1, sy1 = self.spine
        if abs(y1 - sy0) < 1e-9 or abs(y0 - sy1) < 1e-9:
            return max(0.0, min(x1, sx1) - max(x0, sx0))
        return 0.0

    def contact(self, a: str, b: str) -> float:
        """Length of the shared edge between two cells (0 if they only touch at a corner)."""
        ax0, ay0, ax1, ay1 = self.cells[a]
        bx0, by0, bx1, by1 = self.cells[b]
        tol = 1e-9
        if abs(ax1 - bx0) < tol or abs(bx1 - ax0) < tol:
            return max(0.0, min(ay1, by1) - max(ay0, by0))
        if abs(ay1 - by0) < tol or abs(by1 - ay0) < tol:
            return max(0.0, min(ax1, bx1) - max(ax0, bx0))
        return 0.0

    def facade_contacts(self, zone: str) -> dict[str, float]:
        if self.facades is not None:
            return self.facades.get(zone, {})
        x0, y0, x1, y1 = self.cells[zone]
        fx0, fy0, fx1, fy1 = self.footprint
        tol = 1e-9
        out = {}
        if abs(y0 - fy0) < tol:
            out["front"] = x1 - x0
        if abs(y1 - fy1) < tol:
            out["rear"] = x1 - x0
        if abs(x0 - fx0) < tol:
            out["left"] = y1 - y0
        if abs(x1 - fx1) < tol:
            out["right"] = y1 - y0
        return out

    def front_span(self, cell: str) -> tuple[float, float] | None:
        """x-span of the cell on the front line, or None if it does not reach it."""
        if self.front_spans is not None:
            return self.front_spans.get(cell)
        if "front" not in self.facade_contacts(cell):
            return None
        x0, _, x1, _ = self.cells[cell]
        return x0, x1


class RealizationStrategy(Protocol):
    name: str

    def realize(self, footprint, topology: ZoneTopology, areas: dict[str, float], spine_width: float = 0.0,
                min_widths: dict[str, float] | None = None, max_shift: float | None = None) -> RealizedZones | None:
        """Cells with the requested areas inside the footprint, or None if the topology cannot be drawn.

        min_widths / max_shift (optional, strategy B stepped): column widths are raised to their minimum
        inside each band, moving area between the zones of that band by at most max_shift (fraction)."""


def _rect_of(footprint) -> Rect:
    return footprint.rect if isinstance(footprint, FootprintDomain) else tuple(footprint)


def _band_area(band, areas) -> float:
    return sum(areas[z] for col in band for z in col)


def _columns_in_rect(cells: dict[str, Rect], band, areas, x0: float, x1: float, top: float, bottom: float,
                     min_widths: dict[str, float] | None = None, max_shift: float | None = None) -> bool:
    """A row of columns filling [x0, x1] x [top, bottom]; widths and stacked depths proportional to area.

    With min_widths, widths below a column's minimum are raised, taking the deficit from the other
    columns' slack (the band keeps its total area; the zones of the band trade area). False when the
    minimums do not fit or a column's area would move by more than max_shift.
    """
    area_b = _band_area(band, areas)
    widths = [(x1 - x0) * sum(areas[z] for z in col) / area_b for col in band]
    if min_widths:
        fitted = fit_lengths(widths, [max(min_widths.get(z, 0.0) for z in col) for col in band])
        if fitted is None:
            return False
        if max_shift is not None and any(abs(f - w) > max_shift * w + 1e-9 for f, w in zip(fitted, widths)):
            return False
        widths = fitted
    cursor = x0
    for i, column in enumerate(band):
        col_area = sum(areas[z] for z in column)
        end = x1 if i == len(band) - 1 else cursor + widths[i]
        y = top
        for j, zone in enumerate(column):
            y_end = bottom if j == len(column) - 1 else y + (bottom - top) * areas[zone] / col_area
            cells[zone] = (cursor, y, end, y_end)
            y = y_end
        cursor = end
    return True


class StrategyA:
    """Inscribed rectangle + two-band slicing.

    The footprint rectangle is cut into a front band and a rear band whose depths follow the
    area assigned to each. A band is a row of columns; a column takes the band depth and a width
    equal to its area / depth, and its zones split that depth in proportion to their areas.
    Areas are exact by construction (a slicing floorplan of depth 3).
    """

    name = Strategy.A_INSCRIBED_RECTANGLE.value

    def realize(self, footprint, topology: ZoneTopology, areas: dict[str, float], spine_width: float = 0.0,
                min_widths: dict[str, float] | None = None, max_shift: float | None = None) -> RealizedZones | None:
        footprint = _rect_of(footprint)
        x0, y0, x1, y1 = footprint
        if x1 - x0 <= 0 or not (topology.front or topology.rear or topology.through):
            return None
        cells: dict[str, Rect] = {}
        if topology.through:
            all_area = sum(areas[z] for z in topology.zones())
            t_area = sum(areas[z] for z in topology.through)
            t_width = (x1 - x0) * t_area / all_area
            tx0, tx1 = (x0, x0 + t_width) if topology.through_side == "left" else (x1 - t_width, x1)
            cursor = y0
            for j, zone in enumerate(topology.through):
                end = y1 if j == len(topology.through) - 1 else cursor + (y1 - y0) * areas[zone] / t_area
                cells[zone] = (tx0, cursor, tx1, end)
                cursor = end
            x0, x1 = (tx1, x1) if topology.through_side == "left" else (x0, tx0)
            if not topology.front and not topology.rear:
                return RealizedZones(cells, y1 - y0, 0.0, footprint, None)
        front_area, rear_area = _band_area(topology.front, areas), _band_area(topology.rear, areas)
        total = front_area + rear_area
        spine = spine_width if (spine_width > 0 and topology.front and topology.rear) else 0.0
        depth = y1 - y0 - spine
        front_depth = depth * front_area / total
        for band, top, bottom in ((topology.front, y0, y0 + front_depth),
                                  (topology.rear, y0 + front_depth + spine, y1)):
            if band:
                _columns_in_rect(cells, band, areas, x0, x1, top, bottom)
        spine_rect = (x0, y0 + front_depth, x1, y0 + front_depth + spine) if spine else None
        return RealizedZones(cells, front_depth, depth - front_depth, footprint, spine_rect)


# --------------------------------------------------------------------------- strategy B helpers


def _merge(intervals: list[tuple[float, float]]) -> float:
    total, end = 0.0, -INF
    for lo, hi in sorted(intervals):
        if hi <= end:
            continue
        total += hi - max(lo, end)
        end = hi
    return total


def exterior_facades(cells: dict[str, Rect], others: list[Rect], y_front: float, y_top: float
                     ) -> tuple[dict[str, dict[str, float]], dict[str, tuple[float, float]]]:
    """Exterior length of every cell side not shared with another cell or the spine, by facade id.

    A side facing the street is "front" on the front line and "front_shoulder" behind it; a side facing
    the rear is "rear" on the last line and "rear_shoulder" before it.
    """
    rects = list(cells.items())
    blockers = [r for _, r in rects] + list(others)
    facades: dict[str, dict[str, float]] = {}
    spans: dict[str, tuple[float, float]] = {}
    for cid, (x0, y0, x1, y1) in rects:
        out: dict[str, float] = {}
        for side in ("bottom", "top", "left", "right"):
            covered = []
            for (bx0, by0, bx1, by1) in blockers:
                if (bx0, by0, bx1, by1) == (x0, y0, x1, y1):
                    continue
                if side == "bottom" and abs(by1 - y0) < _TOL:
                    covered.append((max(x0, bx0), min(x1, bx1)))
                elif side == "top" and abs(by0 - y1) < _TOL:
                    covered.append((max(x0, bx0), min(x1, bx1)))
                elif side == "left" and abs(bx1 - x0) < _TOL:
                    covered.append((max(y0, by0), min(y1, by1)))
                elif side == "right" and abs(bx0 - x1) < _TOL:
                    covered.append((max(y0, by0), min(y1, by1)))
            covered = [(lo, hi) for lo, hi in covered if hi - lo > _TOL]
            length = (x1 - x0) if side in ("bottom", "top") else (y1 - y0)
            free = length - _merge(covered)
            if free <= 1e-6:
                continue
            if side == "bottom":
                fid = "front" if abs(y0 - y_front) < _TOL else "front_shoulder"
                if fid == "front":
                    spans[cid] = (x0, x1)
            elif side == "top":
                fid = "rear" if abs(y1 - y_top) < _TOL else "rear_shoulder"
            else:
                fid = side
            out[fid] = out.get(fid, 0.0) + free
        facades[cid] = out
    return facades, spans


class StrategyB:
    """Stepped footprint (mode "rectangle") or polygonal footprint (mode "polygonal").

    Bands are laid from the front line backwards: band depth follows its area and the envelope width
    over that depth. Through columns are not used (a full-depth column cannot follow two widths).
    """

    def __init__(self, mode: str = "rectangle"):
        if mode not in ("rectangle", "polygonal"):
            raise ValueError(f"unknown strategy B mode {mode!r}")
        self.mode = mode
        self.name = (Strategy.B_STEPPED_FOOTPRINT if mode == "rectangle" else Strategy.B_POLYGONAL_FOOTPRINT).value

    # ------------------------------------------------------------------ band geometry (also used by filters)

    def band_layout(self, domain: FootprintDomain, front_area: float, rear_area: float, spine_width: float
                    ) -> list[tuple[float, float, float, float]] | None:
        """(y0, y1, x0, x1) of the front and rear bands (empty bands omitted), or None if they do not fit."""
        prof = domain.profile
        y = domain.y_front
        spine = spine_width if (spine_width > 0 and front_area > 0 and rear_area > 0) else 0.0
        out = []
        for i, area in enumerate((front_area, rear_area)):
            if area <= 0:
                continue
            d = prof.depth_for_area(y, area, self.mode)
            if d is None or y + d > prof.ymax + 1e-6:
                return None
            lo, hi = prof.slab_interval(y, y + d)
            if hi - lo <= _TOL:
                return None
            out.append((y, y + d, lo, hi))
            y += d
            if i == 0:
                y += spine
                if spine and y > prof.ymax + 1e-6:
                    return None
        return out

    def realize(self, footprint, topology: ZoneTopology, areas: dict[str, float], spine_width: float = 0.0,
                min_widths: dict[str, float] | None = None, max_shift: float | None = None,
                joint: tuple[str, float, tuple[str, ...], float] | None = None) -> RealizedZones | None:
        """joint = (side, width, anchor cells, minimum contact with the anchor) carves a joint corridor
        (stepped mode, no spine)."""
        if not isinstance(footprint, FootprintDomain) or footprint.profile is None:
            raise TypeError("strategy B needs a FootprintDomain with an envelope profile")
        if topology.through or not (topology.front or topology.rear):
            return None
        prof = footprint.profile
        front_area, rear_area = _band_area(topology.front, areas), _band_area(topology.rear, areas)
        bands = self.band_layout(footprint, front_area, rear_area, spine_width)
        if bands is None:
            return None
        spine_w = spine_width if (spine_width > 0 and topology.front and topology.rear) else 0.0
        band_defs = [b for b in (topology.front, topology.rear) if b]
        y_top = bands[-1][1]
        if self.mode == "rectangle":
            return self._steps(footprint, prof, band_defs, bands, areas, spine_w, y_top, topology, min_widths,
                               max_shift, joint if not spine_w else None)
        return self._polygonal(footprint, prof, band_defs, bands, areas, spine_w, y_top, topology, min_widths,
                               max_shift)

    def _steps(self, dom, prof, band_defs, bands, areas, spine_w, y_top, topology, min_widths=None,
               max_shift=None, joint=None) -> RealizedZones | None:
        cells: dict[str, Rect] = {}
        steps = []
        for band, (y0, y1, x0, x1) in zip(band_defs, bands):
            if not _columns_in_rect(cells, band, areas, x0, x1, y0, y1, min_widths, max_shift):
                return None
            steps.append((x0, y0, x1, y1))
        spine = None
        if spine_w and len(steps) == 2:
            (fx0, _, fx1, fy1), (rx0, ry0, rx1, _) = steps
            spine = (max(fx0, rx0), fy1, min(fx1, rx1), ry0)
            if spine[2] - spine[0] <= _TOL:
                return None
        joint_side = None
        if joint is not None:
            if len(steps) != 2 or not topology.front or not topology.rear:
                return None
            spine = carve_joint(cells, topology.rear, steps, joint)
            if spine is None:
                return None
            joint_side = joint[0]
        facades, spans = exterior_facades(cells, [spine] if spine else [], dom.y_front, y_top)
        wedges = []
        for i, (x0, y0, x1, y1) in enumerate(steps):
            band = band_defs[i]
            for side, c0, c1, col in (("left", -INF, x0, band[0]), ("right", x1, INF, band[-1])):
                area = prof.strip_area(y0, y1, c0, c1)
                if area > 0.5:
                    wedges.append({"band": "front" if (band is topology.front) else "rear", "side": side,
                                   "y_range": (y0, y1), "x_limit": x0 if side == "left" else x1,
                                   "area": area, "adjacent_cells": tuple(col)})
        xs = [s[0] for s in steps] + [s[2] for s in steps]
        bbox = (min(xs), steps[0][1], max(xs), steps[-1][3])
        cell_areas = {c: (r[2] - r[0]) * (r[3] - r[1]) for c, r in cells.items()}
        spine_area = (spine[2] - spine[0]) * (spine[3] - spine[1]) if spine else 0.0
        front_depth = bands[0][1] - bands[0][0] if topology.front else 0.0
        rear_depth = bands[-1][1] - bands[-1][0] if topology.rear else 0.0
        return RealizedZones(cells, front_depth, rear_depth, bbox, spine, facades, spans, None, tuple(steps),
                             tuple(wedges), cell_areas, spine_area, "rectangle", joint_side)

    def _polygonal(self, dom, prof, band_defs, bands, areas, spine_w, y_top, topology, min_widths=None,
                   max_shift=None) -> RealizedZones | None:
        cells: dict[str, Rect] = {}
        extents: dict[str, Rect] = {}
        true_areas: dict[str, float] = {}
        steps = []
        for band, (y0, y1, sx0, sx1) in zip(band_defs, bands):
            steps.append((sx0, y0, sx1, y1))
            fit = polygonal_cuts(prof, y0, y1, band, areas, min_widths, max_shift)
            if fit is None:
                return None
            cuts, col_areas = fit
            for i, column in enumerate(band):
                c0, c1 = cuts[i], cuts[i + 1]
                scale = col_areas[i] / sum(areas[z] for z in column)
                ya = y0
                for j, zone in enumerate(column):
                    yb = y1 if j == len(column) - 1 else prof.y_for_area(ya, y1, areas[zone] * scale, c0, c1)
                    lo, hi = prof.slab_interval(ya, yb)
                    core = (max(c0, lo), ya, min(c1, hi), yb)
                    if core[2] < core[0]:
                        core = (core[0], ya, core[0], yb)  # degenerate: fails the minimum width check
                    cells[zone] = core
                    extents[zone] = (c0, ya, c1, yb)
                    true_areas[zone] = prof.strip_area(ya, yb, c0, c1)
                    ya = yb
        spine, spine_area = None, 0.0
        if spine_w and len(bands) == 2:
            sy0, sy1 = bands[0][1], bands[1][0]
            lo, hi = prof.slab_interval(sy0, sy1)
            spine = (lo, sy0, hi, sy1)
            spine_area = prof.strip_area(sy0, sy1)
        facades: dict[str, dict[str, float]] = {}
        spans: dict[str, tuple[float, float]] = {}
        for cid, (c0, ya, c1, yb) in extents.items():
            out: dict[str, float] = {}
            if abs(ya - dom.y_front) < _TOL:
                lo, hi = prof.interval(ya)
                span = (max(c0, lo), min(c1, hi))
                if span[1] - span[0] > _TOL:
                    out["front"] = span[1] - span[0]
                    spans[cid] = span
            if abs(yb - y_top) < _TOL:
                lo, hi = prof.interval(yb)
                length = min(c1, hi) - max(c0, lo)
                if length > _TOL:
                    out["rear"] = length
            if c0 == -INF:
                length = prof.boundary_length("left", ya, yb, None if c1 == INF else c1)
                if length > _TOL:
                    out["left"] = length
            if c1 == INF:
                length = prof.boundary_length("right", ya, yb, None if c0 == -INF else c0)
                if length > _TOL:
                    out["right"] = length
            facades[cid] = out
        bbox = (min(s[0] for s in steps), steps[0][1], max(s[2] for s in steps), steps[-1][3])
        front_depth = bands[0][1] - bands[0][0] if topology.front else 0.0
        rear_depth = bands[-1][1] - bands[-1][0] if topology.rear else 0.0
        return RealizedZones(cells, front_depth, rear_depth, bbox, spine, facades, spans, extents, tuple(steps), (),
                             true_areas, spine_area, "polygonal")


def polygonal_cuts(prof: SectionProfile, y0: float, y1: float, band, areas: dict[str, float],
                   min_widths: dict[str, float] | None = None, max_shift: float | None = None
                   ) -> tuple[list[float], list[float]] | None:
    """Column cuts of a polygonal band (first = -inf, last = +inf) and the area each column gets.

    Cuts follow the areas. With min_widths, a column whose core span (inside the slab interval) is below
    its minimum is widened by moving the cuts, the other columns giving up slack; the column areas then
    follow the cuts (the band keeps its total), and no column may change by more than max_shift.
    """
    targets = [sum(areas[z] for z in col) for col in band]
    cuts, c0 = [-INF], -INF
    for t in targets[:-1]:
        c0 = prof.x_for_area(y0, y1, t, c0)
        cuts.append(c0)
    cuts.append(INF)
    if not min_widths:
        return cuts, targets
    lo, hi = prof.slab_interval(y0, y1)
    if hi - lo <= _TOL:
        return None
    spans = [max(0.0, min(cuts[i + 1], hi) - max(cuts[i], lo)) for i in range(len(band))]
    mins = [max(min_widths.get(z, 0.0) for z in col) for col in band]
    if all(sp >= m - 1e-9 for sp, m in zip(spans, mins)):
        return cuts, targets
    fitted = fit_lengths(spans, mins)
    if fitted is None:
        return None
    cuts, x = [-INF], lo
    for f in fitted[:-1]:
        x += f
        cuts.append(x)
    cuts.append(INF)
    got = [prof.strip_area(y0, y1, cuts[i], cuts[i + 1]) for i in range(len(band))]
    if max_shift is not None and any(abs(g - t) > max_shift * t + 1e-9 for g, t in zip(got, targets)):
        return None
    return cuts, got


def carve_joint(cells: dict[str, Rect], rear_band, steps, joint) -> Rect | None:
    """Carve the joint corridor into the front cells of the rear columns between the anchor and one end.

    Returns the corridor rectangle, or None when the anchor does not reach the junction, the corridor
    would not touch it over the minimum contact, or a carved cell would vanish.
    """
    side, width, anchors, min_contact = joint
    (_, _, _, yj), (rx0, _, rx1, _) = steps
    anchor = [cells[a] for a in anchors if a in cells and abs(cells[a][3] - yj) < _TOL]
    if not anchor:
        return None
    ax0, ax1 = min(a[0] for a in anchor), max(a[2] for a in anchor)
    columns = [(cells[col[0]][0], cells[col[0]][2], col[0]) for col in rear_band]
    if side == "left":
        chosen = [c for c in columns if c[0] < ax1 - _TOL]
    else:
        chosen = [c for c in columns if c[1] > ax0 + _TOL]
    if not chosen:
        return None
    jx0, jx1 = min(c[0] for c in chosen), max(c[1] for c in chosen)
    if min(jx1, ax1) - max(jx0, ax0) < min_contact - 1e-9:
        return None
    for _, _, cid in chosen:
        x0, y0, x1, y1 = cells[cid]
        if y1 - (y0 + width) <= _TOL:
            return None
        cells[cid] = (x0, y0 + width, x1, y1)
    return (jx0, yj, jx1, yj + width)


STRATEGIES: dict[str, RealizationStrategy] = {
    StrategyA.name: StrategyA(),
    Strategy.B_STEPPED_FOOTPRINT.value: StrategyB("rectangle"),
    Strategy.B_POLYGONAL_FOOTPRINT.value: StrategyB("polygonal"),
}


def get_strategy(name: str) -> RealizationStrategy:
    try:
        return STRATEGIES[name]
    except KeyError as exc:
        raise KeyError(f"unknown realization strategy {name!r}; available: {sorted(STRATEGIES)}") from exc


def is_strategy_b(strategy) -> bool:
    return isinstance(strategy, StrategyB)


__all__ = ["FootprintDomain", "Rect", "RealizationStrategy", "RealizedZones", "SHOULDER_FACADES", "STRATEGIES",
           "StrategyA", "StrategyB", "ZoneTopology", "carve_joint", "polygonal_cuts", "exterior_facades", "get_strategy", "is_strategy_b"]
