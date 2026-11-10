"""The outline finder: a drawing's strokes read as the shapes they enclose
(apothecary/vision/outline.py).

Each picture is drawn here, so its answer is known: marker outlines on a
whiteboard, bare or framed by a darker wall, with what a whiteboard carries
beside a drawing. The floors at the foot were read off a run of the bench
(`apothecary photo check --finder outline`) and set a little under it.
"""

from __future__ import annotations

import pytest
from PIL import Image, ImageChops, ImageDraw

from apothecary.vision import OutlineFinder, PlainFinder, get, names
from apothecary.vision.bench import run
from apothecary.vision.models import ShapeKind

WHITEBOARD, WALL, MARKER = 238, 60, 30
WIDE, HIGH = 1600, 1200
PLATE = (250, 250, 700, 520)
DISC = (900, 250, 1200, 550)
WEDGE = ((350, 950), (650, 950), (500, 700))
LINE = 9


def _drawing(tmp_path, name="drawing", *, framed=False, also=None, over=None):
    """A plate, a disc and a wedge in outline, saved; ``also`` draws more on it,
    and ``over`` changes the finished picture."""
    image = Image.new("L", (WIDE, HIGH), WALL if framed else WHITEBOARD)
    pen = ImageDraw.Draw(image)
    if framed:
        pen.rectangle((80, 80, WIDE - 80, HIGH - 80), fill=WHITEBOARD, outline=150, width=14)
    pen.rectangle(PLATE, outline=MARKER, width=LINE)
    pen.ellipse(DISC, outline=MARKER, width=LINE)
    pen.polygon(WEDGE, outline=MARKER, width=LINE)
    if also is not None:
        also(pen)
    if over is not None:
        image = over(image)
    path = tmp_path / f"{name}.png"
    image.save(path)
    return path


def _kinds(picture):
    """What was found, read left to right and top to bottom as the three were drawn."""
    return [
        shape.kind for shape in sorted(picture.shapes, key=lambda s: (s.centre.y > 0.5, s.centre.x))
    ]


THE_THREE = [ShapeKind.RECT, ShapeKind.DISC, ShapeKind.TRI]


def test_it_is_registered_beside_the_other_two():
    assert "outline" in names()
    assert isinstance(get("outline"), OutlineFinder)


def test_a_closed_stroke_is_the_shape_of_what_it_encloses(tmp_path):
    picture = OutlineFinder().look(_drawing(tmp_path))
    assert picture.finder == "outline"
    assert _kinds(picture) == THE_THREE
    assert {shape.origin for shape in picture.shapes} == {"outline"}
    # No surer than the plain finder is of a filled shape.
    assert all(0.45 <= shape.confidence <= 0.8 for shape in picture.shapes)


def test_the_plain_finder_names_none_of_the_same_drawing(tmp_path):
    """What the outline finder is for: the same picture, read as blobs, is three
    strokes, each filling little of its box."""
    picture = PlainFinder().look(_drawing(tmp_path))
    assert [shape.kind for shape in picture.shapes] == [ShapeKind.POLY] * 3


def test_a_shape_is_as_wide_as_the_middle_of_its_stroke(tmp_path):
    picture = OutlineFinder().look(_drawing(tmp_path))
    plate = next(shape for shape in picture.shapes if shape.kind is ShapeKind.RECT)
    # Pillow draws a rectangle's outline inward from its box, so the stroke's
    # middle is half a line inside it.
    left, top, right, bottom = (
        PLATE[0] + LINE / 2,
        PLATE[1] + LINE / 2,
        PLATE[2] - LINE / 2,
        PLATE[3] - LINE / 2,
    )
    # The working picture is 512 across, so a pixel of it is this much.
    near = 1.5 / 512
    assert plate.min_point.x == pytest.approx(left / WIDE, abs=near)
    assert plate.max_point.x == pytest.approx(right / WIDE, abs=near)
    assert plate.min_point.y == pytest.approx(top / HIGH, abs=near * WIDE / HIGH)
    assert plate.max_point.y == pytest.approx(bottom / HIGH, abs=near * WIDE / HIGH)
    assert plate.long_side == pytest.approx((right - left) / WIDE, abs=2 * near)
    assert plate.short_side == pytest.approx((bottom - top) / WIDE, abs=2 * near)


def test_the_whiteboard_is_the_ground_whatever_runs_round_it(tmp_path):
    """Framed by a darker wall the whiteboard is still not a shape, and neither is
    the wall or the frame."""
    picture = OutlineFinder().look(_drawing(tmp_path, framed=True))
    assert _kinds(picture) == THE_THREE
    assert all(shape.long_side < 0.4 for shape in picture.shapes)


def test_a_stroke_inside_a_shape_is_not_a_shape_of_its_own(tmp_path):
    def a_hole(pen):
        pen.ellipse((400, 340, 470, 410), outline=MARKER, width=7)

    picture = OutlineFinder().look(_drawing(tmp_path, also=a_hole))
    assert _kinds(picture) == THE_THREE
    plate = next(shape for shape in picture.shapes if shape.kind is ShapeKind.RECT)
    assert plate.confidence >= 0.45, "the stroke inside it took nothing from the plate"


def test_a_dimension_line_an_arrow_and_writing_are_not_shapes(tmp_path):
    def notes(pen):
        pen.line((250, 590, 700, 590), fill=MARKER, width=5)
        pen.line((250, 590, 275, 575), fill=MARKER, width=5)
        pen.line((250, 590, 275, 605), fill=MARKER, width=5)
        for letter in range(6):
            x = 400 + letter * 30
            pen.line((x, 610, x + 12, 650), fill=MARKER, width=5)
            pen.line((x + 12, 650, x + 22, 615), fill=MARKER, width=5)

    assert _kinds(OutlineFinder().look(_drawing(tmp_path, also=notes))) == THE_THREE


def test_a_stroke_left_open_is_not_a_shape(tmp_path):
    def rub_out(pen):
        pen.rectangle((440, 500, 520, 540), fill=WHITEBOARD)

    picture = OutlineFinder().look(_drawing(tmp_path, also=rub_out))
    assert _kinds(picture) == [ShapeKind.DISC, ShapeKind.TRI]


def test_a_shadow_across_the_whiteboard_loses_no_shape(tmp_path):
    def shadow(image):
        ramp = Image.linear_gradient("L").rotate(90).resize(image.size)
        return ImageChops.multiply(image, ramp.point(lambda v: round(255 - 0.45 * v)))

    assert _kinds(OutlineFinder().look(_drawing(tmp_path, over=shadow))) == THE_THREE


def test_a_smear_is_not_a_stroke(tmp_path):
    def smear(image):
        from PIL import ImageFilter

        smudges = Image.new("L", image.size, 255)
        ImageDraw.Draw(smudges).ellipse((700, 500, 1100, 800), fill=205)
        return ImageChops.multiply(image, smudges.filter(ImageFilter.GaussianBlur(20)))

    assert _kinds(OutlineFinder().look(_drawing(tmp_path, over=smear))) == THE_THREE


def test_a_mark_filled_in_is_the_shape_it_covers(tmp_path):
    def filled(pen):
        pen.ellipse((1000, 750, 1300, 1050), fill=MARKER)
        pen.rectangle((760, 930, 880, 1050), fill=MARKER)

    picture = OutlineFinder().look(_drawing(tmp_path, also=filled))
    kinds = [shape.kind for shape in picture.shapes]
    assert kinds.count(ShapeKind.DISC) == 2 and kinds.count(ShapeKind.RECT) == 2
    assert len(kinds) == 5


def test_a_whiteboard_with_nothing_drawn_on_it_holds_nothing(tmp_path):
    for name, shade in (("clean", WHITEBOARD), ("dark", WALL)):
        path = tmp_path / f"{name}.png"
        Image.new("L", (640, 480), shade).save(path)
        assert OutlineFinder().look(path).shapes == []


def test_find_shapes_offers_it_for_a_drawing_and_for_nothing_else(tmp_path, monkeypatch):
    """A picture with a closed stroke in it has two finders; a picture of filled
    shapes, a clean whiteboard and a file that is no picture keep the one, so
    Find shapes stays one press for them."""
    from apothecary.routes.views import finders_for

    _drawing(tmp_path, "sketched")
    filled = Image.new("L", (640, 480), WHITEBOARD)
    pen = ImageDraw.Draw(filled)
    pen.rectangle((80, 80, 260, 200), fill=MARKER)
    pen.ellipse((360, 220, 540, 400), fill=MARKER)
    filled.save(tmp_path / "filled.png")
    Image.new("L", (640, 480), WHITEBOARD).save(tmp_path / "clean.png")
    (tmp_path / "broken.png").write_bytes(b"not a picture")
    monkeypatch.setenv("APOTHECARY_PICTURE_ROOT", str(tmp_path))
    assert finders_for("sketched.png") == ["outline", "plain"]
    assert finders_for("filled.png") == ["plain"]
    assert finders_for("clean.png") == ["plain"]
    assert finders_for("broken.png") == ["plain"]
    assert OutlineFinder().reads(tmp_path / "sketched.png")
    assert not OutlineFinder().reads(tmp_path / "filled.png")


# condition, drawing settings, least acceptable found rate, least acceptable naming
OUTLINED = [
    ("in outline", dict(stroke=0.012), 1.00, 1.00),
    ("outline, turned", dict(stroke=0.012, turn=True), 1.00, 1.00),
    ("outline, faint", dict(stroke=0.012, faintness=0.6), 1.00, 1.00),
    ("outline, shadowed", dict(stroke=0.012, shadow=0.4), 0.95, 0.95),
    ("outline, glare", dict(stroke=0.012, glare=True), 0.85, 0.95),
    ("outline, smeared", dict(stroke=0.012, smear=True), 1.00, 1.00),
    ("outline, with notes", dict(stroke=0.012, notes=True), 1.00, 1.00),
    ("outline, framed", dict(stroke=0.012, framed=True), 1.00, 1.00),
]


@pytest.mark.slow
@pytest.mark.parametrize("label, drawing, least_found, least_named", OUTLINED)
def test_it_holds_its_measured_floor_and_makes_nothing_up(label, drawing, least_found, least_named):
    result, _ = run(OutlineFinder(), count=20, **drawing)
    assert result.found_rate >= least_found, f"{label}: {result.summary()}"
    assert result.kind_rate >= least_named, f"{label}: {result.summary()}"
    assert result.spurious == 0, f"{label}: {result.summary()}"


@pytest.mark.slow
def test_a_filled_shape_is_never_made_up_either():
    """Its own subject is a drawing in outline; on shapes filled in it may miss
    one, and reports none that was not drawn."""
    for drawing in ({}, dict(faintness=0.85), dict(blur=5.0), dict(smallest=0.03, largest=0.06)):
        result, _ = run(OutlineFinder(), count=20, **drawing)
        assert result.spurious == 0, f"{drawing}: {result.summary()}"
