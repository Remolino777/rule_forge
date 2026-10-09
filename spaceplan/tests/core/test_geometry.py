import math

import pytest
from shapely.geometry import LineString, Point, Polygon

from spaceplan.core.lib_aux.geometry import (
    Frame,
    discretize_arc,
    halfplane_envelope,
    max_inscribed_rect,
    setback_envelope,
)


def _items(points, distances):
    ring = list(points) + [points[0]]
    return [([ring[i], ring[i + 1]], d) for i, d in enumerate(distances)]


def test_inward_arc_area():
    arc = discretize_arc((0, 0), (50, 0), 50, "inward", 0.05)
    lot = Polygon(arc[:-1] + [(50, 0), (50, 100), (0, 100)])
    expected = 5000 - 0.5 * 50**2 * (math.pi / 3 - math.sin(math.pi / 3))
    # chords of a 0.05 ft sagitta tolerance shave ~2/3 * tol * arc length (~1.7 sq ft)
    assert lot.area == pytest.approx(expected, abs=2.0)


def test_outward_arc_bulges_outside():
    arc = discretize_arc((0, 0), (50, 0), 50, "outward", 0.05)
    assert min(y for _, y in arc) < -6.5


def test_rectangle_envelope_and_inscribed_rect():
    pts = [(0, 0), (50, 0), (50, 100), (0, 100)]
    env = setback_envelope(Polygon(pts), _items(pts, [15, 4, 13, 4]))
    assert env.area == pytest.approx(3024)
    assert max_inscribed_rect(env, Frame((0, 0), 0.0)).area == pytest.approx(3024, abs=0.01)


def test_fan_inscribed_rect_matches_reference():
    pts = [(-17.5, 0), (17.5, 0), (40, 100), (-40, 100)]
    env = setback_envelope(Polygon(pts), _items(pts, [15, 4, 13, 4]))
    assert env.area == pytest.approx(3582, abs=0.5)
    rect = max_inscribed_rect(env, Frame((-17.5, 0), 0.0))
    assert rect.area == pytest.approx(2415.6, abs=1.0)


def test_rotated_frame_gives_same_rect():
    pts = [(0, 0), (50, 0), (50, 100), (0, 100)]
    angle = math.radians(30)
    frame = Frame((10.0, 5.0), angle)
    world = frame.to_world(Polygon(pts))
    ring = list(world.exterior.coords)[:-1]
    env = setback_envelope(world, _items(ring, [15, 4, 13, 4]))
    assert max_inscribed_rect(env, frame).area == pytest.approx(3024, abs=0.05)


def test_concave_lot_respects_distances_at_reflex_corner():
    pts = [(0, 0), (60, 0), (60, 40), (30, 40), (30, 100), (0, 100)]
    distances = [10, 5, 5, 5, 10, 5]
    items = _items(pts, distances)
    env = setback_envelope(Polygon(pts), items)
    for x, y in env.exterior.coords:
        for line, d in items:
            assert LineString(line).distance(Point(x, y)) >= d - 0.01
    # the reflex corner (30, 40) keeps a rounded clearance, unlike half-planes
    assert env.distance(Point(30, 40)) == pytest.approx(5, abs=0.01)  # polygonal buffer arcs
    assert halfplane_envelope(Polygon(pts), items).area < env.area


def test_frame_round_trip():
    frame = Frame((3.0, -2.0), 0.7)
    p = Point(10, 4)
    back = frame.to_world(frame.to_local(p))
    assert back.distance(p) < 1e-9
    assert frame.point_to_local((10, 4)) == pytest.approx(tuple(frame.to_local(p).coords[0]))
