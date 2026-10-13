"""Structural frame of a two-floor house (step 6.7a S2.2g): the axes both floors are zoned on (support first, after
Habraken's support and infill; positions refined by the optimization of lib/frame_positions).

    joists      span the upper floor's short side S; the axes run along its long side
    outline     the upper floor's two lines across the joists are axes (over the ground floor they are the joint)
    pattern     S <= joist span                      -> single bay, no interior axis
                joist span < S < spine_from_ft       -> two bays, one interior axis
                spine_from_ft <= S <= 2 joist + hall -> central hall: two axes a hall width apart
                (S larger: no frame; the stage falls back to the free zoning)
    candidates  the stair core's lines and the garage's walls along the axes (one more candidate each, no
                priority: client 2026-10-12), and the balanced position; a free axis moves onto a fixed element
                within fixed_pull_ft
    variants    the best few by balance of the bays and fixed elements used; a free axis keeps a window of
                axis_window_ft for the optimization

Bays are measured in feet in the local frame of the lot plan; every value comes from the design registry and the
catalog (no numbers here).
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from itertools import pairwise
from typing import Any

from spaceplan.modules.stacking.lib.floor_frame import CellFloors
from spaceplan.modules.stacking.lib_aux.frame_geometry import (
    EPS,
    axis_window,
    edge_lines,
    extent,
    inside,
    length_along,
    snap,
)

SINGLE, TWO_BAY, SPINE = "single", "two_bay", "spine"
CORE, GARAGE, FREE, OUTLINE = "core", "garage", "free", "outline"


@dataclass(frozen=True)
class Axis:
    pos: float                             # ft, local frame
    tag: str                               # core / garage / free / outline
    window: tuple[float, float]            # where the optimization may move it (pos, pos when fixed)


@dataclass(frozen=True)
class Frame:
    axis: str                              # 'x': axes are lines x = c (bands are column ranges); 'y': y = c
    lo: float                              # the upper floor's outline across the joists
    hi: float
    pattern: str
    axes: tuple[Axis, ...]                 # interior axes, low to high
    hall_ft: float = 0.0
    joints: tuple[float, ...] = ()         # outline lines standing over the ground interior
    score: float = 0.0
    notes: tuple[str, ...] = field(default_factory=tuple)
    variant: int = 0                       # rank among the cell's frame variants (kept when an axis moves)

    @property
    def lines(self) -> tuple[float, ...]:
        return (self.lo, *(a.pos for a in self.axes), self.hi)

    def bays(self) -> list[tuple[float, float]]:
        ls = self.lines
        return list(pairwise(ls))

    @property
    def spine_bay(self) -> int | None:
        return 1 if self.pattern == SPINE else None

    def ground_lines(self) -> tuple[float, ...]:
        """Lines the ground floor carries: the joints and the interior axes."""
        return tuple(sorted({*self.joints, *(a.pos for a in self.axes)}))

    def to_dict(self) -> dict[str, Any]:
        return {"axis": self.axis, "pattern": self.pattern, "lo": round(self.lo, 3), "hi": round(self.hi, 3),
                "axes": [{"pos": round(a.pos, 3), "tag": a.tag, "window": [round(a.window[0], 3),
                                                                            round(a.window[1], 3)]} for a in self.axes],
                "joints": [round(j, 3) for j in self.joints], "hall_ft": round(self.hall_ft, 3),
                "bays_ft": [round(b - a, 2) for a, b in self.bays()], "score": round(self.score, 4),
                "variant": self.variant,
                "notes": list(self.notes)}


def frame_settings(values: dict[str, Any], hall_ft: float, grid_ft: float) -> dict[str, Any] | None:
    """Settings of the frame from the design registry values (None when the frame is off)."""
    if not values.get("structure.frame.enabled") or not values.get("structure.enabled"):
        return None
    return {"joist": float(values["structure.joist_span_max_ft"]),
            "bay_min": float(values["structure.frame.bay_min_ft"]),
            "spine_from": float(values["structure.frame.spine_from_ft"]),
            "variants": max(1, int(values["structure.frame.variants"])),
            "window": float(values["structure.frame.axis_window_ft"]),
            "pull": float(values["structure.frame.fixed_pull_ft"]),
            "hall": float(hall_ft), "grid": float(grid_ft)}


def frame_axis(upper) -> str:
    """'x' when the upper floor is narrower along x (the joists span x and the axes are lines x = c)."""
    x0, y0, x1, y1 = upper.bounds
    return "x" if (x1 - x0) <= (y1 - y0) else "y"


def _fixed_lines(floors: CellFloors, axis: str, lo: float, hi: float) -> list[tuple[float, str]]:
    out = [(c, CORE) for c in edge_lines(floors.stair, axis)]
    if floors.garage is not None and not floors.garage.is_empty:
        out += [(c, GARAGE) for c in edge_lines(floors.garage, axis)]
    return [(c, t) for c, t in out if lo + EPS < c < hi - EPS]


def _joints(floors: CellFloors, axis: str, lo: float, hi: float) -> tuple[float, ...]:
    g_lo, g_hi = extent(floors.ground, axis)
    return tuple(c for c in (lo, hi) if g_lo + EPS < c < g_hi - EPS)


def _balance(lines: tuple[float, ...]) -> float:
    bays = [b - a for a, b in pairwise(lines)]
    return min(bays) / max(bays) if bays and max(bays) > 0 else 1.0


def build_frames(floors: CellFloors, st: dict[str, Any]) -> list[Frame]:
    """The frame variants of a drawn cell, best first; [] when the upper floor is too deep for two axes."""
    axis = frame_axis(floors.upper)
    lo, hi = extent(floors.upper, axis)
    span = hi - lo
    joist, bmin, hall, grid = st["joist"], st["bay_min"], st["hall"], st["grid"]
    joints = _joints(floors, axis, lo, hi)
    notes = (f"long side {length_along(floors.upper, axis):.1f} ft",)
    if span <= joist + EPS:
        return [Frame(axis, lo, hi, SINGLE, (), 0.0, joints, 1.0, notes)]
    pattern = TWO_BAY if span < st["spine_from"] - EPS else SPINE
    width = 0.0 if pattern == TWO_BAY else hall
    if pattern == SPINE and span > 2 * joist + hall + EPS:
        return []
    win = axis_window(lo, hi, bmin, joist, width)
    if win is None:
        return []
    fixed = _fixed_lines(floors, axis, lo, hi)
    cands: dict[float, str] = {}
    for c, tag in fixed:                          # fixed elements as the first axis or (spine) the second one
        for p in (c, c - width) if width else (c,):
            if inside(p, win):
                cands.setdefault(round(p, 3), tag)
    centre = snap(lo + (span - width) / 2.0, grid, lo)
    for p in (centre, snap(win[0], grid, lo), snap(win[1], grid, lo)):
        if inside(p, win):
            q = round(p, 3)
            near = [c for c in cands if abs(c - q) <= st["pull"] + EPS]
            if not near:
                cands.setdefault(q, FREE)
    frames = []
    for p, tag in cands.items():
        w = (p, p) if tag != FREE else (max(win[0], p - st["window"]), min(win[1], p + st["window"]))
        axes = (Axis(p, tag, w),) if pattern == TWO_BAY else (Axis(p, tag, w), Axis(p + width, tag, (w[0] + width,
                                                                                                    w[1] + width)))
        outer = (lo, axes[0].pos, hi) if pattern == TWO_BAY else (lo, axes[0].pos, axes[0].pos + (hi - axes[1].pos))
        score = _balance(outer) + (0.25 if tag != FREE else 0.0)          # balanced bays; a fixed element helps
        frames.append(Frame(axis, lo, hi, pattern, axes, width, joints, score, notes))
    frames.sort(key=lambda f: (-f.score, f.axes[0].pos))
    return [replace(f, variant=k) for k, f in enumerate(frames[: st["variants"]])]


__all__ = ["CORE", "FREE", "GARAGE", "OUTLINE", "SINGLE", "SPINE", "TWO_BAY", "Axis", "Frame", "build_frames",
           "frame_axis", "frame_settings"]
