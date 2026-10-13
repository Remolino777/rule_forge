"""Zoning on a structural frame (step 6.7a S2.2g): the band topologies of one floor whose band cuts lie on the
frame's lines, and the surplus of each band left open (roof upstairs, porch or a smaller footprint downstairs).

    band cuts    any subset of the frame's lines (most lines first; at most max_cuts); a frame line that is no band
                 cut runs inside a zone, where stage S2.1 puts a wall or a beam on it (a band cut is a zone wall
                 by construction: the share is scored as `structure`); `fixed`: every line is a band cut
    central hall with both hall lines as cuts, the band between them holds the circulation zone alone
    strip        (upper floor) the circulation may run as a strip along an interior cut (or, with no cut, along
                 either long side): that bay holds two bands, the strip cut by area
    free cut     (ground floor) with no frame line, one band cut placed by area along the same axis (the S2 rule)
    free         (ground floor) after the framed ones, the S2 topologies themselves: every frame line inside zones
    surplus      each band holds its units at their program area (never more than the floor-filling area of S2); what
                 is left at one end of the band, when at least surplus_min_cells, is open: roof (upper), porch on the
                 street or garden facade or a smaller footprint (ground, by the registry policy)

A framed topology is (axis, bands, cuts, split): `bands` the unit groups bay by bay (low to high), `cuts` the frame
lines used as band cuts (cells), `split` the bay holding two bands (None: none). No numbers live here.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from itertools import combinations, pairwise, permutations
from typing import Any

ROOF, PORCH, UNBUILT, EITHER = "roof", "porch", "unbuilt", "either"
SURPLUS_KINDS = (ROOF, PORCH, UNBUILT)
GROUND_POLICIES = (PORCH, UNBUILT, EITHER)
LOW, HIGH = 0, 1


@dataclass(frozen=True)
class FrameGuide:
    """The structural frame one floor is zoned on, in this floor's grid cells."""

    axis: str                          # 'x': bands are column ranges cut on lines x = c; 'y': row ranges
    lines: tuple[int, ...]             # frame lines inside the floor's bounding cells, ascending
    fixed: bool = False                # every line is a band cut (else any subset, at most max_cuts)
    spine: tuple[int, int] | None = None   # the two lines of a central hall (circulation alone between them)
    surplus: str = ROOF                # roof (upper) / porch / unbuilt / either (ground)
    surplus_min_cells: int = 0
    max_cuts: int = 2                  # most frame lines used as band cuts
    free_cut: bool = False             # with no frame line, one band cut placed by area along the axis
    strip: bool = False                # the circulation as a strip along an interior cut
    line_bonus: float = 0.0            # score bonus x the share of frame lines that are band cuts
    free: bool = False                 # also the S2 topologies (catalog axes, cuts by area): the frame's lines
                                       # then run inside zones, carried by walls or beams (ground floor)
    ref: Any = None                    # the structural_frame.Frame it comes from (output, pairing)


def _ordered_groups(items: tuple[int, ...], k: int) -> Iterator[tuple[tuple[int, ...], ...]]:
    """Every way to line the items up and cut the line into k non-empty consecutive groups."""
    n = len(items)
    if k < 1 or n < k:
        return
    for perm in permutations(items):
        for stops in combinations(range(1, n), k - 1):
            edges = (0, *stops, n)
            yield tuple(perm[a:b] for a, b in pairwise(edges))


def _strip_sides(bay: int, bays: int) -> tuple[int, ...]:
    """Sides of a bay where a circulation strip may run: along an interior cut (both sides in a single bay)."""
    if bays == 1:
        return (LOW, HIGH)
    return (HIGH,) if bay == 0 else (LOW,) if bay == bays - 1 else (LOW, HIGH)


def cut_sets(fg: FrameGuide) -> list[tuple[int, ...]]:
    """The band cuts to try, most frame lines first."""
    if fg.fixed:
        return [fg.lines]
    top = min(fg.max_cuts, len(fg.lines))
    return [c for k in range(top, -1, -1) for c in combinations(fg.lines, k)]


def framed_topologies(n: int, circ: int | None, fg: FrameGuide) -> Iterator[tuple]:
    """The framed topologies of a floor with n units (`circ`: the circulation unit, None: none), unbounded (the
    caller stops at the catalog's topology cap)."""
    units = tuple(range(n))
    others = tuple(u for u in units if u != circ)
    for cuts in cut_sets(fg):
        bays = len(cuts) + 1
        if fg.spine is not None and all(x in cuts for x in fg.spine):
            if circ is None:
                continue
            hall = cuts.index(fg.spine[0]) + 1                 # the bay between the two hall lines
            for groups in _ordered_groups(others, bays - 1):
                yield fg.axis, (*groups[:hall], (circ,), *groups[hall:]), cuts, None
            continue
        for groups in _ordered_groups(units, bays):
            yield fg.axis, groups, cuts, None
        if fg.strip and circ is not None:                  # the circulation strip along a cut
            for b in range(bays):
                for side in _strip_sides(b, bays):
                    for groups in _ordered_groups(others, bays):
                        pair = ((circ,), groups[b]) if side == LOW else (groups[b], (circ,))
                        yield fg.axis, (*groups[:b], *pair, *groups[b + 1:]), cuts, b
        if fg.free_cut and not cuts and n >= 2:            # the S2 band cut by area along the axis
            for groups in _ordered_groups(units, 2):
                yield fg.axis, groups, cuts, 0


def bay_ranges(lo: int, hi: int, cuts: tuple[int, ...]) -> list[tuple[int, int]] | None:
    """(lo, hi) of each bay; None when the cuts are not strictly inside lo..hi in order."""
    edges = (lo, *cuts, hi)
    if not all(a < b for a, b in pairwise(edges)):
        return None
    return list(pairwise(edges))


def surplus_kind(policy: str, axis: str, side: int, facade_of) -> str | None:
    """Kind of the open strip at one end of a band (`facade_of(side_name)` -> facade role); None when the policy
    does not allow it there. Columns run along y when the axis is 'x' (the ends are the front and the rear)."""
    if policy == ROOF:
        return ROOF
    end = ("low_y" if side == LOW else "high_y") if axis == "x" else ("low_x" if side == LOW else "high_x")
    role = facade_of(end)
    if policy == PORCH:
        return PORCH
    if policy == UNBUILT:
        return UNBUILT
    return PORCH if role in ("main_street", "garden") else UNBUILT


def side_order(policy: str, axis: str, facade_of, away: int | None) -> tuple[int, ...]:
    """Ends of a band to try for its surplus: upstairs the end away from the stair first; downstairs the garden
    porch, then the street porch, then the others."""
    if policy == ROOF or axis == "y":
        return (away, 1 - away) if away is not None else (HIGH, LOW)
    rank = {"garden": 0, "main_street": 1}
    ends = {LOW: facade_of("low_y"), HIGH: facade_of("high_y")}
    return tuple(sorted((LOW, HIGH), key=lambda s: rank.get(ends[s], 2)))


__all__ = ["EITHER", "GROUND_POLICIES", "HIGH", "LOW", "PORCH", "ROOF", "SURPLUS_KINDS", "UNBUILT", "FrameGuide",
           "bay_ranges", "cut_sets", "framed_topologies", "side_order", "surplus_kind"]
