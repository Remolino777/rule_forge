"""Level 2 - spaces inside each zone cell, circulation network and the D/I/N relation matrix.

Circulation is not a zone: the foyer takes the entry; a hall is carved (design width) along one long
side of a cell that holds two or more terminal rooms, taking its area from that cell; and every path
through a passable room (living, dining, kitchen) takes a strip of the same width from that room.
Each cell offers a few subdivision options (with or without a hall); combinations are checked
globally: reachability from the entry through passable spaces only, net areas after circulation,
and the hard D pairs of the matrix. Soft pairs, circulation efficiency and shape rank the rest.
"""

from __future__ import annotations

import itertools
from collections import Counter
from dataclasses import dataclass

from shapely.geometry import LineString, box

from spaceplan.core.lib.catalog import Catalog
from spaceplan.core.lib.rules import RuleSet
from spaceplan.core.lib_aux.allocation import (  # noqa: F401  (fit_lengths re-exported)
    fit_lengths,
    ranked_product,
)
from spaceplan.core.lib_aux.quantity import worst_status
from spaceplan.modules.zoning.lib.band_enumeration import band_arrangements
from spaceplan.modules.zoning.lib.circulation import (
    DoorRules,
    Node,
    build_graph,
    evaluate_matrix,
    reachability,
    shared_edge,
    through_strips,
)
from spaceplan.modules.zoning.lib.realization import RealizedZones, Rect
from spaceplan.modules.zoning.lib.relation_matrix import ENTRY, PATIO, RelationMatrix

CIRCULATION_TYPES = ("foyer", "hall")
MAX_STACK = 3  # spaces stacked in one column inside a cell (guillotine depth 3)


@dataclass(frozen=True)
class SpaceSpec:
    space_id: str
    space_type: str
    zone: str
    cell: str
    target: float
    min_area: float
    min_side: float
    passable: bool
    circulation: bool
    roles: frozenset[str]
    wet: bool


@dataclass(frozen=True)
class LayoutParams:
    width: float                   # design circulation width
    normative_width: float
    normative_status: str
    normative_source: str
    door_contact: float
    hall_min_terminals: int
    per_hall_side: int
    without_hall: int
    target_fraction: float
    warn_fraction: float
    max_aspect: float
    weights: dict[str, float]
    level_weights: dict[str, float]
    zone_schemes: int
    max_combinations: int


def layout_params(catalog: Catalog, crc: RuleSet) -> LayoutParams:
    c = catalog.data["circulation"]
    z = catalog.data["zoning"]
    rule = c["normative_width"]["rule_id"]
    return LayoutParams(
        width=c["design_width_ft"], normative_width=float(crc.rule(rule)["value"]),
        normative_status=crc.status(rule), normative_source=crc.source_tag(rule),
        door_contact=c["door_contact_ft"], hall_min_terminals=c["hall_min_terminals"],
        per_hall_side=c["search"]["options_per_hall_side"], without_hall=c["search"]["options_without_hall"],
        target_fraction=c["target_fraction"], warn_fraction=c["warn_fraction"], max_aspect=z["max_aspect_ratio"],
        weights=z["space_weights"], level_weights=z["level_weights"], zone_schemes=c["search"]["zone_schemes"],
        max_combinations=c["search"]["max_combinations_per_scheme"],
    )


def space_specs(catalog: Catalog, crc: RuleSet, program: dict, cells, matrix: RelationMatrix
                ) -> tuple[dict[str, list[SpaceSpec]], dict[str, str]]:
    """Real spaces per cell (satellites folded into their host; derived halls removed)."""
    habit_min = float(crc.rule("C01-HABITABLE-DIMENSION")["value"])
    exempt = set(crc.params("C01-HABITABLE-DIMENSION", "kitchen_exempt")["exempt_space_types"])
    spaces = {s["space_id"]: s for s in program["spaces"]}
    targets = Counter()
    for sid, cell in cells.space_cell.items():
        targets[sid] += spaces[sid]["target_area_sqft"]
    hosts = {}
    for sat, cell in cells.satellite_cell.items():
        host = spaces[sat].get("host_space_id")
        if host not in cells.space_cell:
            in_cell = [s for s, c in cells.space_cell.items() if c == cell]
            in_cell.sort(key=lambda s: (spaces[s].get("space_type") not in CIRCULATION_TYPES, -spaces[s]["target_area_sqft"]))
            host = in_cell[0]
        hosts[sat] = host
        targets[host] += spaces[sat]["target_area_sqft"]
    out: dict[str, list[SpaceSpec]] = {}
    for sid, cell in cells.space_cell.items():
        s = spaces[sid]
        t = catalog.space_type(s["space_type"]) if catalog.has_space_type(s.get("space_type")) else None
        stype = s.get("space_type") or s["zone"]
        min_side = t["min_side_ft"] if t else 3.0
        if t and t["habitable"] and stype not in exempt:
            min_side = max(min_side, habit_min)
        roles = set(matrix.roles_of(stype))
        for sat, host in hosts.items():
            if host == sid:
                roles |= matrix.roles_of(spaces[sat].get("space_type") or "")
        out.setdefault(cell, []).append(SpaceSpec(
            sid, stype, s["zone"], cell, targets[sid], s["min_area_sqft"], min_side,
            bool(t and t["passable"]), stype in CIRCULATION_TYPES, frozenset(roles), bool(s["wet"])))
    return out, hosts


# --------------------------------------------------------------------------- cell options


@dataclass(frozen=True)
class CellOption:
    cell: str
    hall: Rect | None
    hall_side: str
    rects: dict[str, Rect]
    shape: float


def _shape(rect: Rect, max_aspect: float) -> float:
    w, d = rect[2] - rect[0], rect[3] - rect[1]
    return min(1.0, max_aspect / (max(w, d) / min(w, d)))


def _realize_columns(rect: Rect, along_x: bool, columns, areas: dict[str, float],
                     min_side: dict[str, float] | None = None) -> dict[str, Rect] | None:
    """Guillotine slicing: columns along one axis, spaces stacked inside each column.

    Spans start proportional to area; with min_side given, they are adjusted so every space meets its
    minimum dimension in both directions when the cell allows it (None otherwise).
    """
    x0, y0, x1, y1 = rect
    main = (x1 - x0) if along_x else (y1 - y0)
    cross = (y1 - y0) if along_x else (x1 - x0)
    total = sum(areas[s] for col in columns for s in col)
    spans = [main * sum(areas[s] for s in col) / total for col in columns]
    if min_side:
        spans = fit_lengths(spans, [max(min_side[s] for s in col) for col in columns])
        if spans is None:
            return None
    out, cursor = {}, x0 if along_x else y0
    for col, span in zip(columns, spans):
        col_area = sum(areas[s] for s in col)
        stack = [cross * areas[s] / col_area for s in col]
        if min_side:
            stack = fit_lengths(stack, [min_side[s] for s in col])
            if stack is None:
                return None
        cur = y0 if along_x else x0
        for s_id, length in zip(col, stack):
            out[s_id] = (cursor, cur, cursor + span, cur + length) if along_x else (cur, cursor, cur + length, cursor + span)
            cur += length
        cursor += span
    return out


def _arrangements(ids: list[str], max_stack: int):
    yield from band_arrangements(ids, max_stack, set(), set())


def _local_ok(specs: dict[str, SpaceSpec], rects: dict[str, Rect], hall: Rect | None, matrix: RelationMatrix,
              door_contact: float) -> bool:
    for sid, r in rects.items():
        s = specs[sid]
        if min(r[2] - r[0], r[3] - r[1]) < s.min_side - 1e-9 or (r[2] - r[0]) * (r[3] - r[1]) < s.min_area - 1e-6:
            return False
    hard_d = [p for p in matrix.pairs if p.kind == "hard" and p.type == "D"]
    in_cell = list(specs.values())
    for a in in_cell:
        if a.passable:
            continue
        for p in hard_d:
            for mine, other in ((p.a, p.b),):  # rows of the matrix: every A needs some B
                if mine not in a.roles:
                    continue
                partners = [b for b in in_cell if b.space_id != a.space_id and other in b.roles and not b.passable]
                if not partners or len(partners) < sum(other in s.roles for s in in_cell if s.space_id != a.space_id):
                    continue  # partner may sit in another cell or be reachable through a passable space
                ok = any(shared_edge(rects[a.space_id], rects[b.space_id])[0] >= door_contact - 1e-9
                         or (hall is not None and shared_edge(rects[a.space_id], hall)[0] >= door_contact - 1e-9
                             and shared_edge(rects[b.space_id], hall)[0] >= door_contact - 1e-9)
                         for b in partners)
                if not ok:
                    return False
    return True


def cell_options(cell: str, rect: Rect, specs: list[SpaceSpec], p: LayoutParams, matrix: RelationMatrix) -> list[CellOption]:
    by_id = {s.space_id: s for s in specs}
    if len(specs) == 1:
        s = specs[0]
        ok = _local_ok(by_id, {s.space_id: rect}, None, matrix, p.door_contact)
        return [CellOption(cell, None, "none", {s.space_id: rect}, _shape(rect, p.max_aspect))] if ok else []
    x0, y0, x1, y1 = rect
    along_x = (x1 - x0) >= (y1 - y0)
    total = sum(s.target for s in specs)
    ids = [s.space_id for s in specs]
    options: dict[str, list[CellOption]] = {}

    mins = {s.space_id: s.min_side for s in specs}

    def keep(side, hall, rects):
        if rects is None or not _local_ok(by_id, rects, hall, matrix, p.door_contact):
            return
        shape = sum(_shape(r, p.max_aspect) for r in rects.values()) / len(rects)
        options.setdefault(side, []).append(CellOption(cell, hall, side, rects, shape))

    area = (x1 - x0) * (y1 - y0)
    areas = {s.space_id: area * s.target / total for s in specs}
    arrangements = list(_arrangements(ids, MAX_STACK))
    for axis in (True, False):
        for columns in arrangements:
            keep("none", None, _realize_columns(rect, axis, columns, areas, mins))
    if sum(not s.passable for s in specs) >= p.hall_min_terminals:
        w = p.width
        halls = {
            "front": ((x0, y0, x1, y0 + w), (x0, y0 + w, x1, y1), True),
            "rear": ((x0, y1 - w, x1, y1), (x0, y0, x1, y1 - w), True),
            "left": ((x0, y0, x0 + w, y1), (x0 + w, y0, x1, y1), False),
            "right": ((x1 - w, y0, x1, y1), (x0, y0, x1 - w, y1), False),
        }
        for side, (hall, rest, axis) in halls.items():
            if min(rest[2] - rest[0], rest[3] - rest[1]) <= 0:
                continue
            rest_area = (rest[2] - rest[0]) * (rest[3] - rest[1])
            rest_areas = {s.space_id: rest_area * s.target / total for s in specs}
            for columns in _arrangements(ids, 2):
                keep(side, hall, _realize_columns(rest, axis, columns, rest_areas, mins))
    out = []
    for side, opts in options.items():
        opts.sort(key=lambda o: (-o.shape, sorted(o.rects.items())))
        out.extend(opts[: (p.without_hall if side == "none" else p.per_hall_side)])
    return out


# --------------------------------------------------------------------------- global evaluation


@dataclass(frozen=True)
class LayoutContext:
    params: LayoutParams
    matrix: RelationMatrix
    rules: DoorRules
    specs: dict[str, list[SpaceSpec]]
    hosts: dict[str, str]
    footprint_area: float
    spine: Rect | None = None
    forbidden_zones: tuple[tuple[str, str], ...] = ()


def _nodes(lc: LayoutContext, combo: tuple[CellOption, ...]) -> dict[str, Node]:
    nodes = {}
    if lc.spine is not None:
        nodes["spine"] = Node("spine", "hall", "circulation", "spine", lc.spine, True, True, lc.params.width, 0.0,
                              frozenset(), False)
    for opt in combo:
        for s in lc.specs[opt.cell]:
            nodes[s.space_id] = Node(s.space_id, s.space_type, s.zone, s.cell, opt.rects[s.space_id], s.passable,
                                     s.circulation, s.min_side, s.min_area, s.roles, s.wet)
        if opt.hall is not None:
            hid = f"hall_{opt.cell}"
            nodes[hid] = Node(hid, "hall", lc.specs[opt.cell][0].zone, opt.cell, opt.hall, True, True,
                              lc.params.width, 0.0, frozenset(), False)
    return nodes


def evaluate_combo(lc: LayoutContext, combo: tuple[CellOption, ...]) -> tuple[list[str], dict | None]:
    nodes = _nodes(lc, combo)
    g = build_graph(nodes, lc.rules)
    depth, parent = reachability(g)
    missing = sorted(n for n in nodes if n not in depth)
    if ENTRY not in g.adj:
        return ["entry:no_space_on_entry"], None
    if missing:
        return [f"reachability:{missing[0]}"], None
    for za, zb in lc.forbidden_zones:
        for a in nodes.values():
            if a.zone != za:
                continue
            for b in nodes.values():
                if b.zone == zb and shared_edge(a.rect, b.rect)[0] > 1e-6:
                    return [f"forbidden:{za}-{zb}"], None
    strips = through_strips(g, parent, lc.params.width)
    for nid, strip in strips.items():
        n = nodes[nid]
        x0, y0, x1, y1 = n.rect
        if (x1 - x0) * (y1 - y0) - strip < n.min_area - 1e-6:
            return [f"net_area:{nid}"], None
    matrix = evaluate_matrix(lc.matrix, g)
    hard = [m for m in matrix if m["kind"] == "hard" and m["applicable"] and not m["satisfied"]]
    if hard:
        return [f"matrix:{hard[0]['pair']}"], None
    soft = [m for m in matrix if m["kind"] == "soft" and m["applicable"]]
    total_w = sum(m["weight"] for m in soft)
    matrix_score = sum(m["weight"] for m in soft if m["satisfied"]) / total_w if total_w else 1.0
    carved = {"spine"} | {f"hall_{o.cell}" for o in combo if o.hall is not None}
    foyer = sum((n.rect[2] - n.rect[0]) * (n.rect[3] - n.rect[1]) for nid, n in nodes.items()
                if n.circulation and nid not in carved)
    halls = sum((n.rect[2] - n.rect[0]) * (n.rect[3] - n.rect[1]) for nid, n in nodes.items() if nid in carved)
    circ = foyer + halls + sum(strips.values())
    fraction = circ / lc.footprint_area
    efficiency = 1.0 if fraction <= lc.params.target_fraction else max(0.0, 1.0 - (fraction - lc.params.target_fraction) / 0.15)
    shape = sum(o.shape for o in combo) / len(combo)
    w = lc.params.weights
    space_total = (w["matrix"] * matrix_score + w["circulation"] * efficiency + w["shape"] * shape) / sum(w.values())
    return [], {"nodes": nodes, "graph": g, "depth": depth, "strips": strips, "matrix": matrix,
                "circulation": {"foyer_sqft": foyer, "halls_sqft": halls, "strips_sqft": sum(strips.values()),
                                "total_sqft": circ, "fraction": fraction},
                "scores": {"total": space_total, "matrix": matrix_score, "circulation": efficiency, "shape": shape}}


def _segment(seg) -> list[list[float]] | None:
    return [list(seg[0]), list(seg[1])] if seg else None


def space_scheme(lc: LayoutContext, combo, result: dict, frame) -> dict:
    nodes, g, depth = result["nodes"], result["graph"], result["depth"]
    spaces, halls = {}, []
    carved = {"spine"} | {f"hall_{o.cell}" for o in combo if o.hall is not None}
    for nid, n in sorted(nodes.items()):
        area = (n.rect[2] - n.rect[0]) * (n.rect[3] - n.rect[1])
        if nid in carved:
            side = "spine" if nid == "spine" else next(o.hall_side for o in combo if o.cell == n.cell)
            halls.append({"hall_id": nid, "cell": n.cell, "side": side,
                          "rect_local": list(n.rect), "area_sqft": area, "width_ft": lc.params.width,
                          "depth_from_entry": depth.get(nid), "polygon": frame.to_world(box(*n.rect))})
            continue
        strip = result["strips"].get(nid, 0.0)
        spaces[nid] = {"space_type": n.space_type, "zone": n.zone, "cell": n.cell, "rect_local": list(n.rect),
                       "area_sqft": area, "through_strip_sqft": strip, "net_area_sqft": area - strip,
                       "passable": n.passable, "depth_from_entry": depth.get(nid), "roles": sorted(n.roles),
                       "polygon": frame.to_world(box(*n.rect))}
    doors = []
    for d in g.doors:
        seg = d["segment"]
        world = [list(frame.to_world(LineString(seg)).coords[0]), list(frame.to_world(LineString(seg)).coords[-1])] if seg else None
        doors.append({"a": d["a"], "b": d["b"], "kind": d["kind"], "segment_local": _segment(seg), "segment": world})
    c = result["circulation"]
    p = lc.params
    return {
        "spaces": spaces,
        "halls": halls,
        "satellites": dict(sorted(lc.hosts.items())),
        "doors": doors,
        "matrix": result["matrix"],
        "circulation": {**c, "design_width_ft": p.width, "normative_min_ft": p.normative_width,
                        "width_ok": p.width >= p.normative_width - 1e-9,
                        "normative_status": worst_status(p.normative_status), "normative_source": p.normative_source,
                        "target_fraction": p.target_fraction, "warn": c["fraction"] > p.warn_fraction},
        "space_scores": result["scores"],
    }


def layout_candidates(zone_valid: list, build_lc, frame, top_k: int, p: LayoutParams) -> dict:
    """Run level 2 over the best zone candidates; return space-level schemes and statistics."""
    failures: Counter = Counter()
    evaluated, found = 0, []
    for zone_scores, topology, realized, zctx in zone_valid[: p.zone_schemes]:
        lc = build_lc(zctx, realized)
        per_cell = []
        for cell, rect in realized.cells.items():
            opts = cell_options(cell, rect, lc.specs.get(cell, []), p, lc.matrix) if lc.specs.get(cell) else []
            if not opts:
                failures["cell_dimensions"] += 1
                per_cell = None
                break
            per_cell.append(opts)
        if per_cell is None:
            continue
        for idx in ranked_product([len(o) for o in per_cell], p.max_combinations):
            combo = tuple(opts[i] for opts, i in zip(per_cell, idx))
            evaluated += 1
            violations, result = evaluate_combo(lc, combo)
            if violations:
                failures[violations[0].split(":")[0] + (":" + violations[0].split(":")[1]
                                                        if violations[0].startswith("matrix") else "")] += 1
                continue
            lw = p.level_weights
            total = (lw["zone"] * zone_scores["total"] + lw["space"] * result["scores"]["total"]) / sum(lw.values())
            found.append((total, zone_scores, topology, realized, zctx, lc, combo, result))
    found.sort(key=lambda f: (-f[0], f[2].key, tuple(o.hall_side for o in f[6])))
    chosen, seen = [], set()
    for item in found:
        key = item[2].key
        if key in seen:
            continue
        seen.add(key)
        chosen.append(item)
        if len(chosen) == top_k:
            break
    if len(chosen) < top_k:
        for item in found:
            if item not in chosen and len(chosen) < top_k:
                concept = (item[2].key, tuple(o.hall_side for o in item[6]))
                if concept not in {(c[2].key, tuple(o.hall_side for o in c[6])) for c in chosen}:
                    chosen.append(item)
    return {"zone_schemes_considered": min(len(zone_valid), p.zone_schemes), "combinations_evaluated": evaluated,
            "valid": len(found), "failures_by_first_violation": dict(sorted(failures.items())), "chosen": chosen}


__all__ = ["CellOption", "LayoutContext", "LayoutParams", "SpaceSpec", "cell_options", "evaluate_combo",
           "layout_candidates", "layout_params", "space_scheme", "space_specs", "PATIO"]
