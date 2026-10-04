"""The one mapping: a point of a picture to a point on the surface it shows.

A camera looking straight down at turn 0 takes exactly the flat picture, its
width ``2 * h * tan(fov / 2)``; a flat view's numbers come out of the mapping as
they always came out of their own formulas; a tilted camera's picture lands
where the hand-worked trigonometry says; and a camera's centre ray lands on the
first top it meets, the floor, or nowhere.
"""

from __future__ import annotations

import math

import pytest

from apothecary.models.vectors import Vector2D, Vector3D
from apothecary.vision.compose import built_sides
from apothecary.vision.models import FoundShape, ShapeKind
from apothecary.vision.projection import (
    Box,
    across,
    axes,
    corners,
    down_the_middle,
    first_surface,
    flat,
    lay,
    long_side_on,
    onto,
    pinhole,
    solve_fov,
)
from apothecary.vision.views import (
    View,
    mapping,
    mat_centre,
    shape_offset,
    width_of,
)

TALL = 0.75  # a 640 x 480 picture


def _close(a, b, tol=1e-9):
    return all(math.isclose(x, y, rel_tol=tol, abs_tol=tol) for x, y in zip(a, b, strict=True))


def _shape(lo, hi, *, turned=0.0, long_side=0.0, short_side=0.0):
    return FoundShape(
        kind=ShapeKind.RECT,
        min_point=Vector2D(x=lo[0], y=lo[1]),
        max_point=Vector2D(x=hi[0], y=hi[1]),
        turned_degrees=turned,
        long_side=long_side,
        short_side=short_side,
    )


SHAPES = [
    _shape((0.1, 0.2), (0.3, 0.35)),  # an upright box
    _shape((0.6, 0.6), (0.7, 0.9), turned=35.0, long_side=0.12, short_side=0.04),
    _shape((0.4, 0.1), (0.5, 0.2), turned=90.0, long_side=0.07, short_side=0.05),
    _shape((0.7, 0.3), (0.8, 0.4), turned=170.0),  # turned, its sides not measured
]


# --- the camera's conventions --------------------------------------------------------------


def test_straight_down_at_turn_zero_is_the_flat_picture():
    """At tilt 0 and turn 0 a camera's picture is today's flat mat: its right +x, its
    top +y, ``2 * h * tan(fov / 2)`` across and ``tallness`` times that deep."""
    for h, fov in ((600.0, 60.0), (1500.0, 40.0), (250.0, 112.0)):
        camera = pinhole((0.0, 0.0, h), 0.0, 0.0, fov, TALL)
        width = 2 * h * math.tan(math.radians(fov) / 2)
        laid_flat = flat(width, TALL)
        for row_c, row_f in zip(camera, laid_flat, strict=True):
            assert _close(row_c, row_f), (camera, laid_flat)
        assert across(camera) == pytest.approx(width)
        assert down_the_middle(camera) == pytest.approx(width * TALL)
        assert onto(camera, 1.0, 0.5) == pytest.approx((width / 2, 0.0))  # right is +x
        assert onto(camera, 0.5, 0.0) == pytest.approx((0.0, width * TALL / 2))  # top is +y


def test_the_camera_looks_down_and_turns_counterclockwise_from_above():
    right, down, forward = axes(0.0, 0.0)
    assert _close(right, (1, 0, 0)) and _close(down, (0, -1, 0)) and _close(forward, (0, 0, -1))
    # Tilted 30: it looks toward the picture's top, +y; its right stays level.
    right, _down, forward = axes(0.0, 30.0)
    assert _close(forward, (0.0, 0.5, -math.sqrt(3) / 2)) and right[2] == 0.0
    # Turned 90: the picture's top lies toward -x.
    _right, down, _forward = axes(90.0, 0.0)
    assert _close(down, (1.0, 0.0, 0.0), 1e-12)


def test_a_tilted_cameras_picture_lands_where_the_trigonometry_says():
    """A lens 1000 mm up, tilted 30 degrees, 60 across, a 4:3 picture: its centre ray
    lands ``h * tan(30)`` ahead; its centre line, ``h / cos(30)`` away, is
    ``2 * (h / cos(30)) * tan(30)`` across; its top and bottom edges run at the tilt
    plus and minus half its field of view down, ``atan(tan(30) * 3/4)``."""
    h, tilt, fov = 1000.0, 30.0, 60.0
    camera = pinhole((0.0, 0.0, h), 0.0, tilt, fov, TALL)
    t, half = math.radians(tilt), math.tan(math.radians(fov) / 2)
    assert onto(camera, 0.5, 0.5) == pytest.approx((0.0, h * math.tan(t)))
    assert across(camera) == pytest.approx(2 * (h / math.cos(t)) * half)
    down_half = math.atan(half * TALL)
    assert onto(camera, 0.5, 0.0)[1] == pytest.approx(h * math.tan(t + down_half))
    assert onto(camera, 0.5, 1.0)[1] == pytest.approx(h * math.tan(t - down_half))
    # The far corners are wider apart than the near ones: a trapezoid, not a rectangle.
    tl, tr, br, bl = corners(camera)
    assert tr[0] - tl[0] > br[0] - bl[0] > 0
    # Turned 90 as well, the same picture lies a quarter turn round: ahead is -x.
    turned = pinhole((0.0, 0.0, h), 90.0, tilt, fov, TALL)
    assert onto(turned, 0.5, 0.5) == pytest.approx((-h * math.tan(t), 0.0))
    # Moved, it lands as far again.
    moved = pinhole((100.0, -50.0, h), 0.0, tilt, fov, TALL)
    assert onto(moved, 0.5, 0.5) == pytest.approx((100.0, -50.0 + h * math.tan(t)))


def test_what_runs_past_the_horizon_lands_nowhere():
    camera = pinhole((0.0, 0.0, 1000.0), 0.0, 80.0, 60.0, TALL)
    assert onto(camera, 0.5, 0.5) is not None  # the centre still lands
    tl, tr, br, bl = corners(camera)
    assert tl is None and tr is None and br is not None and bl is not None
    assert down_the_middle(camera) is None
    assert across(camera) is not None  # a level centre line lands whenever its centre does
    # A shape up there lies nowhere; one down here lies somewhere.
    assert lay(camera, _shape((0.45, 0.0), (0.55, 0.05)), TALL) is None
    assert lay(camera, _shape((0.45, 0.9), (0.55, 0.95)), TALL) is not None
    # Looking up, nothing lands at all.
    assert onto(pinhole((0.0, 0.0, 1000.0), 0.0, 120.0, 60.0, TALL), 0.5, 0.5) is None


# --- a flat view's numbers, as they always were -------------------------------------------


def _flat_view(host: str, width, anchor=None) -> View:
    return View(
        id="view_1",
        site="garage",
        host=host,
        picture="p.png",
        taken_at="2026-10-04T00:00:00",
        mm_across=width,
        pixel_width=640,
        pixel_height=480,
        anchor=anchor,
        shapes=SHAPES,
    )


@pytest.mark.parametrize("host", ["workbench", ""], ids=["host", "floor"])
def test_a_flat_views_mapping_gives_what_its_own_formulas_gave(host):
    """``mm_across``, ``mat_centre``, ``shape_offset`` and the sides and turn a piece is
    built with come out of the one mapping as they came out of their own formulas."""
    from apothecary.example_hierarchy import create_example_site

    site = create_example_site()
    width = 1800.0
    anchor = Vector3D(x=5600.0, y=650.0, z=0.0) if host == "" else None
    view = _flat_view(host, width, anchor)
    assert width_of(view) == width
    centre = mat_centre(view, site)
    if host == "":
        assert (centre.x, centre.y, centre.z) == (anchor.x + width / 2, anchor.y, 0.0)
    else:
        assert (centre.x, centre.y, centre.z) == (900.0, 300.0, 780.0)
    matrix = mapping(view)
    for shape in SHAPES:
        cx, cy = shape.centre.x, shape.centre.y
        want = ((cx - 0.5) * width, (0.5 - cy) * TALL * width)
        assert shape_offset(view, shape) == pytest.approx(want, abs=1e-9)
        laid = lay(matrix, shape, TALL)
        sides = built_sides(shape, width, TALL)
        assert (laid.width, laid.depth) == pytest.approx(sides[:2], rel=1e-12)
        assert laid.turned_degrees == pytest.approx(shape.turned_degrees, abs=1e-9)
        shift = (anchor.x + width / 2, anchor.y) if anchor is not None else (0.0, 0.0)
        assert laid.centre == pytest.approx((shift[0] + want[0], shift[1] + want[1]), abs=1e-9)
    # Unsized, it has no mapping, and its mat stands where it always stood.
    unsized = _flat_view(host, None, anchor)
    assert mapping(unsized) is None
    middle = mat_centre(unsized, site)
    assert (middle.x, middle.y) == ((anchor.x, anchor.y) if anchor else (900.0, 300.0))


def test_a_shapes_long_side_reads_as_scale_reference_reads_it():
    """Sizing by a shape's long side reads the same length a flat picture's
    ``ScaleReference`` does: its own long side, or its upright box's longer side."""
    from apothecary.vision.models import Picture, long_side_across

    picture = Picture(name="p", pixel_width=640, pixel_height=480, shapes=SHAPES)
    laid_flat = flat(1000.0, TALL)
    for shape in SHAPES:
        assert long_side_on(laid_flat, shape, TALL) == pytest.approx(
            1000.0 * long_side_across(shape, picture)
        )


# --- the lens, taught ---------------------------------------------------------------------


def test_bisection_finds_the_field_of_view_that_gives_a_width():
    h = 600.0

    def measure(fov):
        return across(pinhole((0.0, 0.0, h), 0.0, 0.0, fov, TALL))

    fov = solve_fov(measure, 1800.0)
    assert fov == pytest.approx(math.degrees(2 * math.atan(900.0 / h)), abs=1e-9)
    assert solve_fov(measure, 1e12) is None and solve_fov(measure, 1e-9) is None


# --- where a centre ray lands -------------------------------------------------------------

BENCH = Box("workbench", (0.0, 0.0, 0.0), (1800.0, 600.0, 780.0))
PRINTER = Box("printer_2", (618.0, 109.0, 780.0), (1088.0, 563.0, 1350.0))


def test_a_ray_lands_on_the_first_top_the_floor_or_nowhere():
    down = (0.0, 0.0, -1.0)
    # Above a printer standing on a bench: the printer's top, not the bench's.
    hit = first_surface((900.0, 300.0, 2000.0), down, [BENCH, PRINTER])
    assert (hit.name, hit.side) == ("printer_2", False) and hit.point[2] == 1350.0
    # Above the bench's clear front strip: the bench.
    hit = first_surface((900.0, 50.0, 2000.0), down, [BENCH, PRINTER])
    assert (hit.name, hit.side, hit.point) == ("workbench", False, (900.0, 50.0, 780.0))
    # Past everything: the floor.
    hit = first_surface((3000.0, 50.0, 600.0), down, [BENCH, PRINTER])
    assert (hit.name, hit.point) == ("", (3000.0, 50.0, 0.0))
    # Level, at a printer's side: a wall, landed on nowhere.
    hit = first_surface((300.0, 336.0, 1000.0), (1.0, 0.0, 0.0), [BENCH, PRINTER])
    assert hit.side and hit.name == "printer_2"
    # Level past everything, or up: the sky.
    assert first_surface((300.0, 336.0, 3000.0), (1.0, 0.0, 0.0), [BENCH, PRINTER]) is None
    assert first_surface((300.0, 336.0, 1000.0), (0.0, 0.0, 1.0), [BENCH, PRINTER]) is None
    # A box a ray starts inside is passed through.
    hit = first_surface((900.0, 300.0, 1000.0), down, [BENCH, PRINTER])
    assert hit.name == "workbench"
