"""The flat geometry the finder leans on.

These are properties rather than snapshots: things that must hold for any input,
checked against many. A property that survives a few hundred generated cases is
worth more than one hand-picked example that happens to pass.
"""

from __future__ import annotations

import math
import random

import pytest

from apothecary.vision.geometry import edge_points, outline, smallest_box


def _turn(points, degrees, about=(0.0, 0.0)):
    radians = math.radians(degrees)
    cos, sin = math.cos(radians), math.sin(radians)
    cx, cy = about
    return [
        (cx + (x - cx) * cos - (y - cy) * sin, cy + (x - cx) * sin + (y - cy) * cos)
        for x, y in points
    ]


# ---------------------------------------------------------------- outline


def test_the_outline_of_a_square_is_its_four_corners():
    filled = [(x, y) for x in range(11) for y in range(11)]
    assert sorted(outline(filled)) == [(0, 0), (0, 10), (10, 0), (10, 10)]


def test_points_inside_never_reach_the_outline():
    dice = random.Random(11)
    edge = [(0, 0), (100, 0), (100, 100), (0, 100)]
    inside = [(dice.uniform(5, 95), dice.uniform(5, 95)) for _ in range(200)]
    assert sorted(outline(edge + inside)) == sorted(edge)


def test_the_outline_never_bends_inwards():
    """Walk it and check every turn goes the same way."""
    dice = random.Random(12)
    cloud = [(dice.uniform(0, 200), dice.uniform(0, 200)) for _ in range(150)]
    hull = outline(cloud)
    assert len(hull) >= 3
    for i in range(len(hull)):
        a, b, c = hull[i], hull[(i + 1) % len(hull)], hull[(i + 2) % len(hull)]
        cross = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
        assert cross >= -1e-9, "the outline bends inwards"


def test_two_points_or_fewer_come_back_unchanged():
    assert outline([]) == []
    assert outline([(1.0, 1.0)]) == [(1.0, 1.0)]
    assert sorted(outline([(1.0, 1.0), (2.0, 2.0)])) == [(1.0, 1.0), (2.0, 2.0)]


def test_repeated_points_do_not_confuse_it():
    assert sorted(outline([(0, 0)] * 5 + [(4, 0), (4, 4), (0, 4)])) == [
        (0, 0),
        (0, 4),
        (4, 0),
        (4, 4),
    ]


# ---------------------------------------------------------------- smallest box


def test_the_smallest_box_round_an_upright_rectangle_is_that_rectangle():
    box = smallest_box([(0, 0), (60, 0), (60, 20), (0, 20)])
    assert sorted((round(box.width), round(box.height))) == [20, 60]


@pytest.mark.parametrize("degrees", [0, 7, 15, 30, 45, 60, 73, 90, 128, 179])
def test_turning_a_shape_does_not_change_its_smallest_box(degrees):
    """The whole reason this exists. Judge by the upright box and this fails."""
    square = [(0, 0), (40, 0), (40, 40), (0, 40)]
    turned = _turn(square, degrees, about=(20, 20))
    assert smallest_box(turned).area == pytest.approx(smallest_box(square).area, rel=1e-6)


@pytest.mark.parametrize("degrees", [0, 23, 45, 67, 90])
def test_a_turned_square_still_fills_its_smallest_box(degrees):
    """Against the upright box a square at 45° fills half, and reads as a triangle."""
    solid = [(x, y) for x in range(41) for y in range(41)]
    turned = _turn(solid, degrees, about=(20, 20))
    fullness = len(turned) / smallest_box(turned).area
    assert fullness > 0.9, f"a square turned {degrees}° filled only {fullness:.2f}"


def test_a_circle_fills_about_four_fifths_of_its_smallest_box():
    solid = [(x, y) for x in range(-30, 31) for y in range(-30, 31) if x * x + y * y <= 30 * 30]
    fullness = len(solid) / smallest_box(solid).area
    assert 0.74 < fullness < 0.82, fullness


def test_a_triangle_fills_about_half_its_smallest_box():
    solid = [(x, y) for y in range(0, 61) for x in range(-y // 2, y // 2 + 1)]
    fullness = len(solid) / smallest_box(solid).area
    assert 0.44 < fullness < 0.58, fullness


def test_the_smallest_box_is_never_bigger_than_the_upright_one():
    dice = random.Random(13)
    for _ in range(60):
        cloud = [(dice.uniform(0, 100), dice.uniform(0, 100)) for _ in range(25)]
        xs = [p[0] for p in cloud]
        ys = [p[1] for p in cloud]
        upright = (max(xs) - min(xs)) * (max(ys) - min(ys))
        assert smallest_box(cloud).area <= upright + 1e-6


def test_the_angle_comes_back_pointing_the_right_way():
    bar = [(x, y) for x in range(0, 80) for y in range(0, 8)]
    turned = _turn(bar, 30, about=(40, 4))
    reported = smallest_box(turned).degrees
    assert min(abs(reported - 30), abs(reported - 210), abs(reported - 150)) < 2.0


def test_a_flat_line_of_points_does_not_crash():
    box = smallest_box([(float(x), 5.0) for x in range(20)])
    assert box.area == 0.0


# ---------------------------------------------------------------- edge points


def test_only_the_pixels_touching_the_outside_are_kept():
    width = 10
    solid = {y * width + x for x in range(2, 8) for y in range(2, 8)}
    edge = edge_points(sorted(solid), width, solid)
    assert len(edge) == 6 * 6 - 4 * 4  # the ring, not the middle
    assert (2.0, 2.0) in edge and (4.0, 4.0) not in edge


def test_keeping_only_the_edge_gives_the_same_answer_as_keeping_everything():
    width = 40
    solid = {y * width + x for x in range(5, 35) for y in range(5, 25)}
    everything = [(float(i % width), float(i // width)) for i in sorted(solid)]
    just_edge = edge_points(sorted(solid), width, solid)
    assert smallest_box(just_edge).area == pytest.approx(smallest_box(everything).area, rel=1e-9)
