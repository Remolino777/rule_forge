"""Walls on a cell grid and how the upper floor stands on the ground floor (step 6.7a S2.2f). Domain-free: labels,
edges, offsets and lengths; the rules (spans, shares) come from the caller.

A label grid (ny, nx) has a wall on every cell edge between two different labels. Walls are kept as two boolean
arrays:

    V (ny, nx + 1)   V[j, i]: wall on the vertical line x = i between cells (j, i - 1) and (j, i)
    H (ny + 1, nx)   H[j, i]: wall on the horizontal line y = j between cells (j - 1, i) and (j, i)

Both floors use grids anchored on the same origin (zone_grid.rasterize `anchor`), so a line of one floor is a line of
the other: an upper index plus the integer offset (di, dj) is the ground index.

A wall run of the upper floor (maximal straight stretch on one line) stands on the ground walls of the same line;
the stretches without a ground wall below are beams, measured between supports: a ground wall on the line, or a
ground wall crossing or ending on the line (a bearing point). A beam end with no support is a post; on an outer wall
of the upper floor standing over the ground interior, posts also split a beam longer than the limit (interior runs
are not split: their beams bear on walls).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import pairwise

import numpy as np

EDGE_TOL = 1e-6


def edge_walls(labels: np.ndarray, outside: int) -> tuple[np.ndarray, np.ndarray]:
    """(V, H) walls of a label grid; cells beyond the grid count as `outside`."""
    pad = np.pad(labels, 1, constant_values=outside)
    v = pad[1:-1, :-1] != pad[1:-1, 1:]
    h = pad[:-1, 1:-1] != pad[1:, 1:-1]
    return v, h


def inside_edges(inside: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """(V, H): edges with the floor on at least one side."""
    pad = np.pad(inside, 1, constant_values=False)
    return pad[1:-1, :-1] | pad[1:-1, 1:], pad[:-1, 1:-1] | pad[1:, 1:-1]


def grid_offset(a_x0: float, a_y0: float, b_x0: float, b_y0: float, res: float) -> tuple[int, int]:
    """(di, dj) with index_in_b = index_in_a + d; the grids must share their lines."""
    di, dj = (a_x0 - b_x0) / res, (a_y0 - b_y0) / res
    ri, rj = round(di), round(dj)
    if abs(di - ri) > 1e-6 or abs(dj - rj) > 1e-6:
        raise ValueError("grids are not on the same lines (rasterize both floors on one anchor)")
    return int(ri), int(rj)


def window(arr: np.ndarray, shape: tuple[int, int], di: int, dj: int) -> np.ndarray:
    """`arr` (in grid b) seen from grid a: out[j, i] = arr[j + dj, i + di], False outside `arr`."""
    out = np.zeros(shape, dtype=bool)
    ny, nx = shape
    j0, i0 = max(0, -dj), max(0, -di)
    j1, i1 = min(ny, arr.shape[0] - dj), min(nx, arr.shape[1] - di)
    if j1 > j0 and i1 > i0:
        out[j0:j1, i0:i1] = arr[j0 + dj:j1 + dj, i0 + di:i1 + di]
    return out


def _runs(line: np.ndarray) -> list[tuple[int, int]]:
    d = np.diff(np.concatenate(([0], line.astype(np.int8), [0])))
    return list(zip(np.nonzero(d == 1)[0].tolist(), np.nonzero(d == -1)[0].tolist(), strict=True))


@dataclass
class SupportReport:
    """How the checked walls stand on the walls below (lengths in feet)."""

    length_ft: float = 0.0
    supported_ft: float = 0.0
    interior_ft: float = 0.0
    interior_supported_ft: float = 0.0
    beams_ft: list[float] = field(default_factory=list)
    posts: int = 0
    runs: list[dict] = field(default_factory=list)

    @property
    def fraction(self) -> float:
        return self.supported_ft / self.length_ft if self.length_ft > EDGE_TOL else 1.0

    @property
    def interior_fraction(self) -> float:
        return self.interior_supported_ft / self.interior_ft if self.interior_ft > EDGE_TOL else 1.0

    def to_dict(self) -> dict:
        return {"length_ft": round(self.length_ft, 2), "supported_ft": round(self.supported_ft, 2),
                "fraction": round(self.fraction, 3), "interior_ft": round(self.interior_ft, 2),
                "interior_fraction": round(self.interior_fraction, 3),
                "beams_ft": [round(b, 2) for b in sorted(self.beams_ft, reverse=True)], "posts": self.posts}


def _line_runs(check: np.ndarray, below: np.ndarray, cross_lo: np.ndarray, cross_hi: np.ndarray,
               interior: np.ndarray, res: float, vertical: bool, rep: SupportReport,
               min_fraction: float, beam_max_ft: float, violations: list[str]) -> None:
    """Runs along the second axis of the edge arrays (one line per index of the first axis after transposing).

    For vertical lines (V, shape ny x (nx+1)) the line index is i and the run goes along j; `cross_lo/hi` are the
    perpendicular ground walls that meet the line at each node (len ny + 1)."""
    lines = check.T if vertical else check
    sup = below.T if vertical else below
    inn = interior.T if vertical else interior
    for k in range(lines.shape[0]):
        if not lines[k].any():
            continue
        for a, b in _runs(lines[k]):
            seg = sup[k, a:b]
            n = b - a
            got = int(seg.sum())
            inside_n = int(inn[k, a:b].sum())
            rep.length_ft += n * res
            rep.supported_ft += got * res
            run_interior = inside_n == n
            if run_interior:
                rep.interior_ft += n * res
                rep.interior_supported_ft += got * res
            # supports along the run: nodes t in a..b where a ground wall lies on the line on either side, or a
            # perpendicular ground wall meets the line
            node = np.zeros(n + 1, dtype=bool)
            node[:-1] |= seg
            node[1:] |= seg
            cl = cross_lo[k] if cross_lo.ndim == 2 else cross_lo
            ch = cross_hi[k] if cross_hi.ndim == 2 else cross_hi
            node |= cl[a:b + 1] | ch[a:b + 1]
            beams = []
            t = 0
            while t < n:
                if seg[t]:
                    t += 1
                    continue
                s = t
                while t < n and not seg[t]:
                    t += 1
                pts = [s + x for x in range(t - s + 1) if node[s + x]]
                ends_ok = (pts[:1] == [s], pts[-1:] == [t])
                cuts = sorted({s, t, *pts})
                spans = [(q - p) * res for p, q in pairwise(cuts)]
                beams += [x for x in spans if x > EDGE_TOL]
                rep.posts += int(not ends_ok[0]) + int(not ends_ok[1])
            if not run_interior:                     # an outer wall over the ground interior: posts split long beams
                split = []
                for x in beams:
                    parts = int(np.ceil(x / beam_max_ft - EDGE_TOL)) if beam_max_ft > 0 and np.isfinite(beam_max_ft) else 1
                    rep.posts += max(0, parts - 1)
                    split += [x / max(parts, 1)] * max(parts, 1)
                beams = split
            rep.beams_ft += beams
            frac = got / n if n else 1.0
            info = {"vertical": vertical, "line": k, "from": a, "to": b, "length_ft": n * res,
                    "supported_ft": got * res, "interior": run_interior, "beams_ft": beams}
            rep.runs.append(info)
            if run_interior and frac + EDGE_TOL < min_fraction:
                violations.append(f"structure:support:{'x' if vertical else 'y'}{k}")
            if any(x > beam_max_ft + EDGE_TOL for x in beams):
                violations.append(f"structure:beam:{'x' if vertical else 'y'}{k}")


def support_report(upper_labels: np.ndarray, upper_outside: int, ground_labels: np.ndarray, ground_outside: int,
                   di: int, dj: int, res: float, min_fraction: float, beam_max_ft: float
                   ) -> tuple[SupportReport, list[str]]:
    """How the walls of the upper label grid stand on the ground label grid (offset d: upper + d = ground).

    Checked: every upper wall with the ground floor below at least on one side (walls over the cantilever, with
    open air below on both sides, are left out). Interior runs (floor on both sides upstairs) must have
    `min_fraction` of their length on ground walls; every beam (unsupported stretch between supports) at most
    `beam_max_ft`."""
    uv, uh = edge_walls(upper_labels, upper_outside)
    gv, gh = edge_walls(ground_labels, ground_outside)
    g_in = ground_labels != ground_outside
    u_in = upper_labels != upper_outside
    ny, nx = upper_labels.shape
    gv_w, gh_w = window(gv, (ny, nx + 1), di, dj), window(gh, (ny + 1, nx), di, dj)
    giv, gih = inside_edges(g_in)
    giv_w, gih_w = window(giv, (ny, nx + 1), di, dj), window(gih, (ny + 1, nx), di, dj)
    uiv = np.pad(u_in, 1)[1:-1, :-1] & np.pad(u_in, 1)[1:-1, 1:]
    uih = np.pad(u_in, 1)[:-1, 1:-1] & np.pad(u_in, 1)[1:, 1:-1]
    check_v, check_h = uv & giv_w, uh & gih_w
    # bearing points on vertical line i at node j: ground horizontal walls at y = j touching x = i from either side
    gh_big = window(gh, (ny + 1, nx + 2), di - 1, dj)          # columns i - 1 .. i + nx
    cross_v_lo = gh_big[:, :-1].T                               # (nx + 1, ny + 1): wall in cell column i - 1
    cross_v_hi = gh_big[:, 1:].T                                # wall in cell column i
    gv_big = window(gv, (ny + 2, nx + 1), di, dj - 1)          # rows j - 1 .. j + ny
    cross_h_lo = gv_big[:-1, :]                                 # (ny + 1, nx + 1)
    cross_h_hi = gv_big[1:, :]
    rep = SupportReport()
    violations: list[str] = []
    _line_runs(check_v, gv_w, cross_v_lo, cross_v_hi, uiv, res, True, rep, min_fraction, beam_max_ft, violations)
    _line_runs(check_h, gh_w, cross_h_lo, cross_h_hi, uih, res, False, rep, min_fraction, beam_max_ft, violations)
    return rep, violations


def bearing_spans(upper_labels: np.ndarray, outside: int, rep: SupportReport, res: float, span_max_ft: float,
                  min_fraction: float, beam_max_ft: float) -> dict:
    """Whether the floor joists of the upper floor (and its ceiling) can span between bearing lines in one of the two
    directions: bearing lines are the outline of the upper floor and the interior runs that stand on the ground
    floor (at least `min_fraction` supported, every beam at most `beam_max_ft`). Returns {direction: largest span
    (ft)} for 'x' (joists along x, bearing on vertical lines) and 'y', and the best direction."""
    inside = upper_labels != outside
    ov, oh = edge_walls(inside.astype(np.int8), 0)          # the outline
    bv, bh = ov.copy(), oh.copy()
    for r in rep.runs:
        if not r["interior"]:
            continue
        ok = r["supported_ft"] + EDGE_TOL >= min_fraction * r["length_ft"] and all(
            b <= beam_max_ft + EDGE_TOL for b in r["beams_ft"])
        if not ok:
            continue
        if r["vertical"]:
            bv[r["from"]:r["to"], r["line"]] = True
        else:
            bh[r["line"], r["from"]:r["to"]] = True
    out = {}
    for name, b, axis_inside in (("y", bh, inside), ("x", bv.T, inside.T)):
        worst = 0
        for col in range(axis_inside.shape[1]):
            run = 0
            for row in range(axis_inside.shape[0]):
                if b[row, col]:
                    run = 0
                if axis_inside[row, col]:
                    run += 1
                    worst = max(worst, run)
                else:
                    run = 0
        out[name] = worst * res
    best = min(out, key=lambda k: out[k])
    return {"span_x_ft": round(out["x"], 2), "span_y_ft": round(out["y"], 2), "joists": best,
            "ok": out[best] <= span_max_ft + EDGE_TOL}


def box_lines(walls: tuple[np.ndarray, np.ndarray], box: tuple[int, int, int, int], share: float) -> tuple:
    """(x lines, y lines) inside a box (i0, i1, j0, j1) where the walls (V, H) run along at least `share` of it."""
    v, h = walls
    i0, i1, j0, j1 = box
    nx_need = max(1, int(np.ceil(share * (j1 - j0))))
    ny_need = max(1, int(np.ceil(share * (i1 - i0))))
    xs = tuple(i for i in range(i0, i1 + 1) if i < v.shape[1] and v[j0:j1, i].sum() >= nx_need)
    ys = tuple(j for j in range(j0, j1 + 1) if j < h.shape[0] and h[j, i0:i1].sum() >= ny_need)
    return xs, ys


def line_density(walls: np.ndarray, vertical: bool, k: int, lo: int, hi: int) -> float:
    """Share of the stretch lo..hi of line k covered by walls (V: vertical line x = k over rows lo..hi; H: line
    y = k over columns lo..hi)."""
    if hi <= lo:
        return 0.0
    if vertical:
        if not 0 <= k < walls.shape[1]:
            return 0.0
        seg = walls[max(lo, 0):min(hi, walls.shape[0]), k]
    else:
        if not 0 <= k < walls.shape[0]:
            return 0.0
        seg = walls[k, max(lo, 0):min(hi, walls.shape[1])]
    return float(seg.sum()) / (hi - lo)


def snap_line(walls: np.ndarray, vertical: bool, k: int, lo: int, hi: int, reach: int, min_density: float,
              low: int, high: int) -> int:
    """The line nearest k (within `reach` cells, strictly between `low` and `high`) where the walls cover at least
    `min_density` of lo..hi; k itself when none does."""
    best, best_key = k, None
    for d in range(reach + 1):
        for c in ((k,) if d == 0 else (k - d, k + d)):
            if not low < c < high:
                continue
            dens = line_density(walls, vertical, c, lo, hi)
            if dens + EDGE_TOL >= min_density and dens > 0:
                key = (d, -dens)
                if best_key is None or key < best_key:
                    best, best_key = c, key
        if best_key is not None:
            return best
    return best


__all__ = ["SupportReport", "bearing_spans", "box_lines", "edge_walls", "grid_offset", "inside_edges", "line_density", "snap_line",
           "support_report", "window"]
