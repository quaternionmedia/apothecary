"""A made piece's mesh, footprint and bounds say the same width x depth.

A round word found as an ellipse, or given two different sides by a person, is
built as that ellipse, not as a circle of its longer side; a piece turned as
its shape was seen has the upright box of it as turned for its footprint, so
the overlap check reads the box the piece fills.
"""

from __future__ import annotations

import math

import pytest

from apothecary.hierarchy import Assembly, check_no_overlaps
from apothecary.meshes import bounds, read_mesh
from apothecary.models.bounds import BoundingBox3D
from apothecary.models.vectors import Vector2D, Vector3D
from apothecary.projects.parts.stl_renderer import get_renderer
from apothecary.vision.compose import piece_from_shape
from apothecary.vision.models import FoundShape, ShapeKind
from apothecary.vocabulary import WordShape, starter_words


def _word_scad(word: str, width: float, depth: float, height: float) -> str:
    shape = WordShape(width=width, depth=depth, height=height)
    return starter_words().get(word).make("d", shape).to_scad_object().render()


# --- round words -----------------------------------------------------------------------


@pytest.mark.parametrize("word", ["disc", "post"])
def test_an_elliptical_round_word_names_a_scale_of_its_depth_over_its_width(word):
    text = _word_scad(word, 60.0, 30.0, 4.5)
    assert "scale([1.0, 0.5, 1.0])" in text
    assert "cylinder(h=4.5, r=30.0, center=false)" in text
    # Deeper than wide: the longer side keeps the radius, the width is squeezed.
    assert "scale([0.5, 1.0, 1.0])" in _word_scad(word, 30.0, 60.0, 4.5)


@pytest.mark.parametrize("word", ["disc", "post"])
def test_a_round_word_that_is_round_builds_the_same_circle_as_before(word):
    assert _word_scad(word, 54.0, 54.0, 8.1) == (
        "// Word: d\nunion() {\n  translate([27.0, 27.0, 0.0]) {\n"
        "  cylinder(h=8.1, r=27.0, center=false);\n}\n}"
    )


@pytest.mark.slow
@pytest.mark.skipif(not get_renderer().is_available, reason="OpenSCAD not installed")
def test_an_elliptical_disc_renders_as_wide_and_as_deep_as_its_sides(tmp_path):
    scad = tmp_path / "disc.scad"
    scad.write_text(_word_scad("disc", 60.0, 30.0, 4.5))
    result = get_renderer().render_stl(scad)
    assert result.success, result.error_message
    lo, hi = bounds(read_mesh(scad.with_suffix(".stl")))
    # OpenSCAD facets the circle, so a side may fall short by a facet's sag.
    assert hi[0] - lo[0] == pytest.approx(60.0, abs=0.5)
    assert hi[1] - lo[1] == pytest.approx(30.0, abs=0.5)
    assert hi[2] - lo[2] == pytest.approx(4.5, abs=1e-6)


# --- turned pieces ---------------------------------------------------------------------

BAR = (600.0, 150.0)  # at 1000 mm across a square picture


def _turned_bar(degrees: float) -> Assembly:
    """A 600 x 150 plate turned ``degrees``, standing on the picture's middle."""
    shape = FoundShape(
        kind=ShapeKind.RECT,
        min_point=Vector2D(x=0.2, y=0.2),
        max_point=Vector2D(x=0.8, y=0.8),
        turned_degrees=degrees,
        long_side=0.6,
        short_side=0.15,
        origin="stated",
    )
    piece, _about = piece_from_shape(
        shape,
        name="bar",
        word="plate",
        reason="a test",
        per_unit=1000.0,
        tallness=1.0,
        finder="stated",
    )
    assert (piece.position.x, piece.position.y) == pytest.approx((0.0, 0.0))
    return piece


def _block(name, x0, x1, y0, y1) -> Assembly:
    return Assembly(
        name=name,
        role="structure",
        footprint=BoundingBox3D(
            min_point=Vector3D(x=x0, y=y0, z=0.0), max_point=Vector3D(x=x1, y=y1, z=10.0)
        ),
    )


def test_a_turned_piece_has_the_box_of_it_as_turned_for_its_footprint():
    fp = _turned_bar(35).footprint
    turn = math.radians(35)
    width, depth = BAR
    assert fp.size.x == pytest.approx(width * math.cos(turn) + depth * math.sin(turn))
    assert fp.size.y == pytest.approx(width * math.sin(turn) + depth * math.cos(turn))
    assert fp.center.x == pytest.approx(0.0) and fp.center.y == pytest.approx(0.0)


def test_a_neighbour_on_the_turned_bar_is_an_overlap_its_unturned_box_would_miss():
    # The bar's middle line runs through (200, 140) at 35°; its unturned box
    # reaches only 75 back.
    on_the_bar = _block("on_the_bar", 150.0, 250.0, 100.0, 200.0)
    found = check_no_overlaps([_turned_bar(35), on_the_bar])
    assert [v.structures for v in found] == [["bar", "on_the_bar"]]


def test_a_neighbour_past_the_turned_bars_end_is_no_overlap_its_unturned_box_would_claim():
    # Turned 35°, the bar reaches about 289 across; unturned it reached 300.
    past_the_end = _block("past_the_end", 292.0, 320.0, -10.0, 10.0)
    assert check_no_overlaps([_turned_bar(35), past_the_end]) == []
