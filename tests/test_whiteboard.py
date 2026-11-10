"""A whiteboard found in a photograph taken from one side, and the photograph
squared to it (apothecary/vision/whiteboard.py).

The photograph is drawn here: a whiteboard on a wall, leaning as it does seen
from the left, its drawing carried through the same lean. Squared, each shape is
where it was drawn on the whiteboard, and as wide.
"""

from __future__ import annotations

import json
import math

import pytest
from click.testing import CliRunner
from PIL import Image, ImageDraw

from apothecary.cli.main import cli
from apothecary.vision import OutlineFinder, ScaleReference, build, whiteboard
from apothecary.vision.models import ShapeKind

WIDE, HIGH = 1600, 1200
# The whiteboard's corners in the photograph: top-left, top-right, bottom-right,
# bottom-left. Its right side is further away, so shorter.
LEANING = [(180, 150), (1380, 300), (1400, 900), (160, 1050)]
# A whiteboard 1200 mm by 900 mm.
BOARD_MM = (1200.0, 900.0)


def _onto(corners):
    """The mapping from a place on the whiteboard, each way 0 to 1, to the
    photograph: the projective one that takes the unit square to four corners."""
    (x0, y0), (x1, y1), (x2, y2), (x3, y3) = corners
    dx1, dx2, sx = x1 - x2, x3 - x2, x0 - x1 + x2 - x3
    dy1, dy2, sy = y1 - y2, y3 - y2, y0 - y1 + y2 - y3
    below = dx1 * dy2 - dx2 * dy1
    g = (sx * dy2 - dx2 * sy) / below
    h = (dx1 * sy - sx * dy1) / below
    a, b, c = x1 - x0 + g * x1, x3 - x0 + h * x3, x0
    d, e, f = y1 - y0 + g * y1, y3 - y0 + h * y3, y0

    def place(u, v):
        w = g * u + h * v + 1
        return ((a * u + b * v + c) / w, (d * u + e * v + f) / w)

    return place


def _photograph(path, corners=LEANING):
    """A plate, a disc and a wedge drawn on a whiteboard seen from one side."""
    place = _onto(corners)
    image = Image.new("RGB", (WIDE, HIGH), (60, 60, 64))
    pen = ImageDraw.Draw(image)
    pen.polygon([place(u, v) for u, v in ((0, 0), (1, 0), (1, 1), (0, 1))], fill=(238, 238, 236))
    ink = (20, 30, 120)
    plate = [(0.15, 0.2), (0.45, 0.2), (0.45, 0.45), (0.15, 0.45)]
    pen.polygon([place(u, v) for u, v in plate], outline=ink, width=8)
    # A disc 240 mm across on a whiteboard 1200 by 900: 0.2 of its width, 0.2667 of its height.
    ring = [
        (0.7 + 0.1 * math.cos(t / 60 * math.tau), 0.35 + 0.1333 * math.sin(t / 60 * math.tau))
        for t in range(60)
    ]
    pen.polygon([place(u, v) for u, v in ring], outline=ink, width=8)
    wedge = [(0.25, 0.9), (0.45, 0.9), (0.35, 0.6)]
    pen.polygon([place(u, v) for u, v in wedge], outline=ink, width=8)
    image.save(path)
    return path


def test_the_corners_are_found_where_the_whiteboard_leans(tmp_path):
    found = whiteboard.find(_photograph(tmp_path / "leaning.png"))
    assert found.by == "finder" and not found.fills
    for (x, y), (want_x, want_y) in zip(found.corners, LEANING, strict=True):
        assert x == pytest.approx(want_x / WIDE, abs=0.012)
        assert y == pytest.approx(want_y / HIGH, abs=0.012)


def test_squared_each_shape_is_where_it_was_drawn_and_as_wide(tmp_path):
    photograph = _photograph(tmp_path / "leaning.png")
    out = tmp_path / "squared.png"
    used, size = whiteboard.square(photograph, out, wide_over_tall=BOARD_MM[0] / BOARD_MM[1])
    assert size == (whiteboard.SQUARED_EDGE, 1200)
    picture = OutlineFinder().look(out)
    kinds = {shape.kind: shape for shape in picture.shapes}
    assert set(kinds) == {ShapeKind.RECT, ShapeKind.DISC, ShapeKind.TRI}
    plate, disc = kinds[ShapeKind.RECT], kinds[ShapeKind.DISC]
    assert (plate.min_point.x, plate.max_point.x) == pytest.approx((0.15, 0.45), abs=0.012)
    assert (plate.min_point.y, plate.max_point.y) == pytest.approx((0.2, 0.45), abs=0.015)
    assert disc.centre.x == pytest.approx(0.7, abs=0.012)
    # Sized by the whiteboard's own width, which is the squared picture's.
    built = build(picture, scale=ScaleReference(millimetres_across=BOARD_MM[0]))
    assert built.album.sized
    assert plate.long_side * BOARD_MM[0] == pytest.approx(360.0, abs=12)
    assert disc.long_side * BOARD_MM[0] == pytest.approx(240.0, abs=10)


def test_unsquared_the_same_photograph_reads_the_plate_out_of_true(tmp_path):
    """What squaring is for: read as it leans, the plate is not where it was drawn."""
    picture = OutlineFinder().look(_photograph(tmp_path / "leaning.png"))
    plate = next(shape for shape in picture.shapes if shape.kind is not ShapeKind.DISC)
    assert abs(plate.min_point.x - 0.15) > 0.03


def test_its_proportions_are_read_from_its_sides_when_nobody_says(tmp_path):
    photograph = _photograph(tmp_path / "leaning.png")
    read = whiteboard.proportions(photograph, whiteboard.find(photograph))
    # Its far side is shorter in the photograph, so it reads wider than its
    # four to three; a whiteboard's own size, given, is what squares it true.
    assert 1.5 < read < 1.8


def test_a_persons_word_on_a_corner_wins_and_is_kept_beside_the_photograph(tmp_path):
    photograph = _photograph(tmp_path / "leaning.png")
    found = whiteboard.find(photograph)
    said = whiteboard.say(photograph, found, [("top-right", (0.9, 0.2))])
    assert said.by == "you" and said.corners[1] == (0.9, 0.2) and said.guess == found.corners
    assert said.corners[0] == found.corners[0]
    kept = json.loads(whiteboard.corners_path(photograph).read_text(encoding="utf-8"))
    assert kept["format"] == whiteboard.FORMAT and kept["picture"]
    again = whiteboard.with_word(photograph, whiteboard.find(photograph))
    assert again.by == "you" and again.corners[1] == (0.9, 0.2)
    with pytest.raises(KeyError, match="no corner 'middle'"):
        whiteboard.say(photograph, found, [("middle", (0.5, 0.5))])
    with pytest.raises(ValueError, match="a fraction of the photograph"):
        whiteboard.say(photograph, found, [("top-left", (1.4, 0.5))])


def test_a_whiteboard_that_fills_the_photograph_says_so_and_a_dark_one_is_refused(tmp_path):
    full = tmp_path / "full.png"
    image = Image.new("RGB", (800, 600), (238, 238, 236))
    ImageDraw.Draw(image).rectangle((200, 200, 500, 400), outline=(20, 30, 120), width=6)
    image.save(full)
    assert whiteboard.find(full).fills
    small = tmp_path / "small.png"
    image = Image.new("RGB", (800, 600), (40, 40, 40))
    ImageDraw.Draw(image).rectangle((350, 250, 450, 330), fill=(238, 238, 236))
    image.save(small)
    with pytest.raises(whiteboard.NoWhiteboard, match="too small to square"):
        whiteboard.find(small)


def test_photo_square_writes_the_picture_and_says_what_it_used(tmp_path):
    photograph = _photograph(tmp_path / "leaning.png")
    out = tmp_path / "squared.png"
    done = CliRunner().invoke(
        cli, ["photo", "square", str(photograph), "--out", str(out), "--size-mm", "1200x900"]
    )
    assert done.exit_code == 0, done.output
    assert "corners by finder; squared to 1600 by 1200 pixels" in done.output
    with Image.open(out) as squared:
        assert squared.size == (1600, 1200)
    moved = CliRunner().invoke(
        cli,
        ["photo", "square", str(photograph), "--out", str(out), "--corner", "top-left=0.11,0.12"],
    )
    assert moved.exit_code == 0 and "corners by you" in moved.output
    for wrong, means in (
        (["--corner", "top-left=here"], "a corner is NAME=X,Y"),
        (["--corner", "middle=0.5,0.5"], "no corner 'middle'"),
        (["--size-mm", "wide"], "a size is WIDExHIGH"),
    ):
        refused = CliRunner().invoke(
            cli, ["photo", "square", str(photograph), "--out", str(out), *wrong]
        )
        assert refused.exit_code != 0 and means in refused.output, refused.output
