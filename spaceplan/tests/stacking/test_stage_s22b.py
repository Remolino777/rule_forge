"""Step 6.7a S2.2b: the design registry inside stage S2.1 (shape per type, furniture, whole-wall small spaces,
carved closets, one piece per space, new score terms)."""

from types import SimpleNamespace

import numpy as np
import pytest

from spaceplan.core.lib.catalog import load_catalog
from spaceplan.modules.design.lib import design_profile as dp
from spaceplan.modules.design.lib.design_registry import load_registry
from spaceplan.modules.stacking.lib.space_rules import (
    design_view,
    load_crc_ruleset,
    load_openings_ruleset,
    space_rules,
)
from spaceplan.modules.stacking.lib.stacking_catalog import (
    S21_LOCAL_WEIGHTS,
    S21_WEIGHTS,
    load_stacking_catalog,
)
from spaceplan.modules.stacking.lib.stair_access import load_client_ruleset, relations
from spaceplan.modules.stacking.lib.stair_rules import load_stair_ruleset
from spaceplan.modules.stacking.lib.unit_frame import SpaceSpec, UnitFrame, spec_of
from spaceplan.modules.stacking.lib.unit_layout import Piece, UnitLayout
from spaceplan.modules.stacking.lib.zone_relations import build_matrix
from spaceplan.modules.stacking.lib_aux.space_grid import exposed_sides, fits_in_mask, shared_edge

RES = 0.5


@pytest.fixture(scope="module")
def catalog():
    return load_catalog()


@pytest.fixture(scope="module")
def scat():
    return load_stacking_catalog()


@pytest.fixture(scope="module")
def matrix(catalog, scat):
    return build_matrix(catalog, relations(load_client_ruleset()), scat.s2["pair_default_weights"])


def _rules(scat, catalog, profile=None):
    return space_rules(scat, catalog, load_crc_ruleset(), load_openings_ruleset(), load_stair_ruleset(),
                       load_client_ruleset(), design_view(profile))


@pytest.fixture(scope="module")
def rules(scat, catalog):
    return _rules(scat, catalog)


def _layout(rules, catalog, matrix, w_ft, h_ft, rows, level=1):
    """A floor of one unit w x h ft surrounded by outside, with the given space rows."""
    nx, ny = int(w_ft / RES) + 2, int(h_ft / RES) + 2
    base = np.full((ny, nx), -2, dtype=np.int32)
    base[0, :] = base[-1, :] = base[:, 0] = base[:, -1] = -1
    mask = base == -2
    specs = [spec_of(catalog, rules, matrix, r, "u") for r in rows]
    unit = UnitFrame(0, "u", "private", mask, (1, nx - 1, 1, ny - 1), specs)
    zero = np.zeros_like(mask)
    floor = SimpleNamespace(res=RES, outside=base == -1, landing=zero, links={}, units=[unit], base=base, fixed=[],
                            stair=zero, level=level, accessible=False)
    return UnitLayout(floor, unit, rules, catalog, matrix), unit


def _row(sid, st, area, host=None):
    return {"space_id": sid, "space_type": st, "zone": "private", "area_sqft": area, "host_space_id": host}


def _piece(ul, spec, i0, i1, j0, j1):
    m = np.zeros((ul.unit.box[3] - ul.unit.box[2], ul.unit.box[1] - ul.unit.box[0]), dtype=bool)
    m[j0:j1, i0:i1] = True
    return Piece(spec, m, (i0 + 1, i1 + 1, j0 + 1, j1 + 1))


# ------------------------------------------------------------------ data and rules


def test_catalog_weights_add_furniture_circulation_and_light(scat):
    assert scat.version == "0.14.0"
    assert set(scat.s21["weights"]) == set(S21_WEIGHTS) and "light" in S21_WEIGHTS and "furniture" in S21_WEIGHTS
    assert set(scat.s21["layout"]["local_weights"]) == set(S21_LOCAL_WEIGHTS)


def test_client_decisions_are_in_the_registry(rules):
    # intermediate profile (client 2026-10-11 23:54): hard for baths, strong preferences for the rest;
    # S2.2j (client 2026-10-13 23:21): the bed with its clearances is hard (the in-room path never crosses it)
    assert rules.std("bedroom", "furniture_w_ft") == 11.0 and rules.hard("bedroom", "furniture_w_ft")
    for st in ("bathroom", "primary_bath", "social_bath", "half_bath"):
        assert rules.hard(st, "aspect_max") and rules.furniture_hard(st), st
    for st in ("dining_room", "kitchen", "living_room"):
        assert not rules.hard(st, "aspect_max") and not rules.furniture_hard(st), st
    assert (7.5, 10.0) in rules.furniture_ft("kitchen") and len(rules.furniture_ft("kitchen")) == 4
    assert rules.policy("habitable_side_tolerance") == 0.0 and rules.policy("one_piece") is True
    assert "closet" in rules.policy("full_wall_types") and rules.design_kinds["space.policy.full_wall_types"] == "soft"
    assert rules.category("bathroom", 1) == "M" and rules.category("bedroom", 1) == "N"


def test_least_side_without_tolerance_and_from_hard_furniture(rules, catalog, matrix):
    bed = spec_of(catalog, rules, matrix, _row("b", "bedroom", 140), "u")
    assert bed.min_side_ft == pytest.approx(10.0)            # S2.2j: the bed with its clearances is hard (11 x 10)
    study = spec_of(catalog, rules, matrix, _row("s", "study", 130), "u")
    assert study.min_side_ft == pytest.approx(8.0)           # catalog least side, no tolerance (habitable)
    bath = spec_of(catalog, rules, matrix, _row("x", "bathroom", 55), "u")
    assert bath.min_side_ft == pytest.approx(5.0)            # 5 x 8 furniture (hard) over the toleranced 4.25


def test_a_profile_changes_the_rules(scat, catalog):
    reg = load_registry()
    prof = dp.apply(reg, dp.new_profile(reg, "t"), [{"id": "space.bedroom.furniture_w_ft", "kind": "soft"},
                                                     {"id": "space.policy.habitable_side_tolerance", "value": 0.15}],
                    "test", "2026-10-11")
    r = _rules(scat, catalog, prof)
    assert not r.furniture_hard("bedroom") and r.policy("habitable_side_tolerance") == 0.15


def test_grid_helpers():
    m = np.ones((20, 10), dtype=bool)
    assert fits_in_mask(m, 10, 16) and fits_in_mask(m, 11, 10) and not fits_in_mask(m, 11, 11)
    a, b = np.zeros((6, 8), bool), np.zeros((6, 8), bool)
    a[:2, :] = True
    b[2:, :] = True
    assert shared_edge(a, b) == (8, False)
    ext = (np.zeros_like(a),) * 2 + (np.ones_like(a), np.zeros_like(a))
    assert exposed_sides(a, ext) == 1


# ------------------------------------------------------------------ the layout


def test_long_bath_gets_a_bath_closet_across_its_short_wall(rules, catalog, matrix):
    ul, unit = _layout(rules, catalog, matrix, 5, 14, [_row("bath", "bathroom", 70)])
    spec = unit.specs[0]
    kept = np.ones((28, 10), dtype=bool)
    room, closet, _rect, role = ul._carve(spec, kept, (1, 11, 1, 29))
    assert role == "bath_closet"
    assert closet.sum() * RES * RES <= rules.closet_max_sqft + 1e-9
    h = room.any(1).sum() * RES
    assert h <= 1.6 * 5 + 1e-9                               # down to the preferred ratio (5 x 8)
    assert closet.any(0).sum() == 10                         # across the whole short wall


def test_hard_shape_of_baths_dining_and_kitchen(scat, catalog, matrix):
    reg = load_registry()
    strict = dp.apply(reg, dp.new_profile(reg, "strict"), [
        {"id": f"space.{t}.{n}", "kind": "hard"} for t in ("dining_room", "kitchen")
        for n in ("aspect_max", "furniture_w_ft")] + [{"id": "space.kitchen.templates_allowed", "kind": "hard"}],
        "test", "2026-10-11")
    rules = _rules(scat, catalog, strict)
    ul, unit = _layout(rules, catalog, matrix, 20, 20, [_row("k", "kitchen", 170), _row("d", "dining_room", 150),
                                                         _row("b", "bathroom", 55)])
    k, d, b = unit.specs

    def box(w, h):
        m = np.zeros((40, 40), dtype=bool)
        m[:int(h / RES), :int(w / RES)] = True
        return m

    assert ul._hard_shape(k, box(7.5, 11)) is None          # galley fits
    assert ul._hard_shape(k, box(6.5, 11)) == "furniture:kitchen"
    assert ul._hard_shape(d, box(8.5, 20)) == "aspect:dining_room"
    assert ul._hard_shape(d, box(12, 10)) is None
    assert ul._hard_shape(b, box(5, 10)) == "aspect:bathroom"
    assert ul._hard_shape(b, box(5, 8)) is None


def test_closet_covers_the_whole_wall_of_its_room(rules, catalog, matrix):
    ul, unit = _layout(rules, catalog, matrix, 12, 14, [_row("bed", "bedroom", 140), _row("cl", "closet", 12, "bed")])
    bed, cl = unit.specs
    room = _piece(ul, bed, 0, 24, 4, 28)
    whole = _piece(ul, cl, 0, 24, 0, 4)
    part = _piece(ul, cl, 0, 12, 0, 4)
    assert ul._wall_misses([room, whole]) == [] and ul._full_wall([room, part]) is None   # soft by default
    assert ul._wall_misses([room, part]) == ["closet"]
    assert ul._score([room, whole], {}, [])["furniture"] > ul._score([room, part], {}, [])["furniture"]


def test_small_spaces_are_capped_to_their_typical_size(rules, catalog, matrix):
    ul, unit = _layout(rules, catalog, matrix, 20, 20, [_row("bed", "bedroom", 140), _row("bath", "bathroom", 90)])
    specs = {s.space_id: s for s in unit.specs}
    cells = 1.0 / (RES * RES)
    out = ul._cap_small({"bed": 200 * cells, "bath": 100 * cells}, specs)
    assert out["bath"] == pytest.approx(5 * 8 * 1.25 * cells)
    assert out["bed"] + out["bath"] == pytest.approx(300 * cells)


def test_linen_closet_across_the_upper_hall(rules, catalog, matrix):
    ul, _ = _layout(rules, catalog, matrix, 4, 20, [_row("bed", "bedroom", 140)])
    hspec = SpaceSpec("hall_u", "hall", "circulation", "u", 70.0, 30.0, 3.0, False, True, True, frozenset())
    h = _piece(ul, hspec, 0, 7, 0, 40)
    out = ul._linen([h])
    assert out is not None
    linen = [p for p in out if p.spec.space_id.endswith("_linen")]
    assert len(linen) == 1 and linen[0].mask.any(0).sum() == 7      # the whole width of the hall
    ground, _ = _layout(rules, catalog, matrix, 4, 20, [_row("bed", "bedroom", 140)], level=0)
    assert ground._linen([h]) is None                                # upper floor only


def test_unit_score_has_the_new_terms(rules, catalog, matrix):
    ul, unit = _layout(rules, catalog, matrix, 12, 12, [_row("bed", "bedroom", 140)])
    p = _piece(ul, unit.specs[0], 0, 24, 0, 24)
    parts = ul._score([p], {"bed": 576}, [3.0])
    assert set(S21_LOCAL_WEIGHTS) <= set(parts)
    assert parts["furniture"] == 1.0 and parts["shape"] == 1.0
    strip = _piece(ul, unit.specs[0], 0, 18, 0, 24)              # 9 x 12: no room for the bed with 36 in clear
    assert ul._score([strip], {"bed": 432}, [3.0])["furniture"] == 0.0


# ------------------------------------------------------------------ step S2.2c (client 2026-10-12)


def test_bath_templates_lower_the_least_side(rules, catalog, matrix):
    assert rules.furniture_ft("primary_bath") == [(8.0, 9.0), (5.0, 8.0)]
    assert (5.0, 7.0) in rules.furniture_ft("bathroom") and (4.0, 4.0) in rules.furniture_ft("half_bath")
    pb = spec_of(catalog, rules, matrix, _row("pb", "primary_bath", 80, "suite"), "u")
    assert pb.min_side_ft == pytest.approx(5.0)               # the single-vanity template, not 8 ft


def test_walk_in_of_the_suite_is_a_walk_through(rules, catalog, matrix):
    wic = spec_of(catalog, rules, matrix, _row("w", "walk_in_closet", 50, "suite"), "u")
    assert wic.min_side_ft == pytest.approx(rules.policy("walk_through_min_side_ft"))
    from spaceplan.modules.stacking.lib.door_placement import door_choices

    suite = spec_of(catalog, rules, matrix, _row("suite", "primary_suite", 290), "u")
    bath = spec_of(catalog, rules, matrix, _row("pb", "primary_bath", 80, "suite"), "u")
    assert door_choices(rules, matrix, bath, wic) == 0          # through the walk-in first
    assert door_choices(rules, matrix, bath, suite) == 1        # the bedroom only as a fallback
    from spaceplan.modules.stacking.lib.unit_layout import suite_groups

    groups = suite_groups({s.space_id: s for s in (suite, wic, bath)}, rules, matrix)
    assert groups[0][0] == ["suite", "w", "pb"]                 # suite -> walk-in -> bath


def test_open_plan_by_culture_and_great_room_pairs(rules):
    assert rules.design["space.great_room.open_cultures"] == ["anglo", "none"]
    assert "living_room" in rules.design["space.great_room.zones"]
    assert rules.design["space.great_room.merge_units"] is False
    from spaceplan.modules.stacking.lib.door_placement import great_room_pair
    from spaceplan.modules.stacking.lib.unit_frame import SpaceSpec as S

    specs = [S("k", "kitchen", "kitchen", "k", 0, 0, 0, True, True, False, frozenset()),
             S("l", "living_room", "social", "s", 0, 0, 0, True, True, False, frozenset()),
             S("h", "half_bath", "circulation", "c", 0, 0, 0, False, False, False, frozenset())]
    open_lay = SimpleNamespace(floor=SimpleNamespace(open_plan=True), specs=specs)
    closed_lay = SimpleNamespace(floor=SimpleNamespace(open_plan=False), specs=specs)
    assert great_room_pair(open_lay, rules, 0, 1) and not great_room_pair(open_lay, rules, 0, 2)
    assert not great_room_pair(closed_lay, rules, 0, 1)


def test_maximum_profile_weighs_shape_more(rules):
    from spaceplan.modules.stacking.lib.unit_layout import shape_weighted

    w = {"shape": 0.25, "fit": 0.1}
    assert shape_weighted(rules, w, SimpleNamespace(profile="maximum"))["shape"] == pytest.approx(0.25 * 1.6)
    assert shape_weighted(rules, w, SimpleNamespace(profile="accessible")) == w


# ------------------------------------------------------------------ step S2.2d (client 2026-10-12)


def test_stair_band_between_the_quartiles():
    from shapely.geometry import box as sbox

    from spaceplan.modules.stacking.lib.access_stair import in_band

    ground = sbox(0, 0, 30, 40)                                  # street at y = 0, garden at y = 40
    band = {"band": [0.25, 0.75], "measure": "footprint", "garden_facade_free": True}
    assert in_band(sbox(0, 12, 4, 26), ground, band)
    assert not in_band(sbox(0, 2, 4, 14), ground, band)          # starts before the first quartile
    assert not in_band(sbox(0, 30, 4, 40), ground, band)         # on the garden facade
    centre = {**band, "measure": "centre"}
    assert in_band(sbox(0, 6, 4, 18), ground, centre) and not in_band(sbox(0, 28, 4, 40), ground, centre)
    assert in_band(sbox(0, 0, 4, 8), ground, None)


def test_upper_unit_leaves_its_slack_as_roof(rules, catalog, matrix):
    ul, unit = _layout(rules, catalog, matrix, 24, 14, [_row("bed", "bedroom", 140), _row("b", "bathroom", 55)])
    roof = ul._roof_spec({s.space_id: s for s in unit.specs})
    assert roof is not None and roof.space_type == "upper_roof"
    assert roof.target_sqft == pytest.approx(24 * 14 - 140 - 5 * 8 * 1.25)
    ground, gunit = _layout(rules, catalog, matrix, 24, 14, [_row("bed", "bedroom", 140)], level=0)
    assert ground._roof_spec({s.space_id: s for s in gunit.specs}) is None


def test_roof_on_the_facade_and_terrace_by_the_bedroom(rules, catalog, matrix):
    ul, unit = _layout(rules, catalog, matrix, 20, 14, [_row("bed", "bedroom", 140)])
    roof = ul._roof_spec({s.space_id: s for s in unit.specs}) or SpaceSpec(
        "roof_u", "upper_roof", "exterior", "u", 100.0, 0.0, RES, False, False, False, frozenset(), None, False, True)
    area = np.ones((28, 40), dtype=bool)
    edge = ul._roof_piece(area, roof, (31, 41, 1, 29))           # last 5 ft, on the +x facade
    assert edge is not None
    assert ul._roof_piece(area, roof, (11, 21, 1, 29)) is None    # in the middle of the unit: not a roof
    bed = _piece(ul, unit.specs[0], 0, 30, 0, 28)
    parts = ul._terraces([edge], [bed])
    terrace = [p for p in parts if p.spec.space_type == "terrace"]
    assert len(terrace) == 1 and terrace[0].spec.host == "bed"
    assert terrace[0].mask.any(0).sum() * RES <= rules.design["space.upper.terrace_max_depth_ft"] + 1e-9
    assert terrace[0].mask.any(1).sum() == 28                    # along the whole wall of the bedroom


def test_terrace_gets_a_slider_from_its_room(rules):
    from spaceplan.modules.stacking.lib.door_placement import (
        EXTERIOR,
        PATIO_SLIDER,
        DoorPlacer,
        place_terrace_doors,
    )
    from spaceplan.modules.stacking.lib.unit_frame import SpaceSpec as S

    labels = np.full((30, 40), -1, dtype=np.int32)
    labels[1:29, 1:31] = 0                                       # the bedroom, 15 x 14 ft
    terrace = np.zeros_like(labels, dtype=bool)
    terrace[1:29, 31:37] = True                                  # a 3 ft terrace along its +x wall
    bed = S("bed", "bedroom", "private", "u", 140, 0, 0, True, False, False, frozenset())
    tspec = S("terrace_u", "terrace", "exterior", "u", 40, 0, 0, False, False, False, frozenset(), "bed", False, True)
    floor = SimpleNamespace(res=RES, level=1, stair=np.zeros_like(terrace), landing=np.zeros_like(terrace))
    lay = SimpleNamespace(floor=floor, specs=[bed], labels=labels, open_air=[(tspec, terrace)], doors=[],
                          node=lambda sid: 0 if sid == "bed" else None)
    placer = DoorPlacer.__new__(DoorPlacer)
    placer.res, placer.corner = RES, rules.door_ft["corner_return"] / RES
    assert place_terrace_doors(lay, placer, rules) == 1
    d = lay.doors[0]
    assert (d.a, d.b, d.kind) == (0, EXTERIOR, PATIO_SLIDER) and d.run.vertical and d.run.k == 31
