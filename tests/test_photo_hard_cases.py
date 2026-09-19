"""The awkward inputs, and the faults they exposed.

Every test here came from an independent review that set out to break the
picture path rather than confirm it. Each one failed before it passed. They are
kept together because they share a theme: the easy case was working and the
ordinary case was not, and nothing in the friendly tests could tell the
difference.
"""

from __future__ import annotations

import math

import pytest
from PIL import Image, ImageDraw

from apothecary.models.vectors import Vector2D
from apothecary.vision import PlainFinder, ScaleReference, picture_to_site
from apothecary.vision.models import AmbiguousReference, FoundShape, Picture, ShapeKind
from apothecary.vocabulary.word import WordList


def _stated(**overrides) -> Picture:
    shape = dict(
        kind=ShapeKind.RECT,
        min_point=Vector2D(x=0.1, y=0.4),
        max_point=Vector2D(x=0.9, y=0.6),
        origin="stated",
    )
    shape.update(overrides)
    return Picture(
        name="stated",
        pixel_width=512,
        pixel_height=512,
        finder="stated",
        shapes=[FoundShape(**shape)],
    )


# ------------------------------------------------- pictures that are not square


def test_a_wide_picture_is_not_stretched(tmp_path):
    """Across is a fraction of the width and down is a fraction of the height.

    Treating both as the width stretched every ordinary photograph by a third,
    and put pieces off the top of the picture they came from.
    """
    picture = Image.new("L", (4000, 3000), 255)
    pen = ImageDraw.Draw(picture)
    pen.rectangle((100, 100, 500, 500), fill=0)
    pen.rectangle((100, 2500, 500, 2900), fill=0)
    path = tmp_path / "wide.png"
    picture.save(path)

    site = picture_to_site(PlainFinder().look(path), scale=ScaleReference(millimetres_across=400))
    tops = sorted(piece.position.y for piece in site.children)
    assert tops[1] - tops[0] == pytest.approx(240, abs=6)
    # The picture is 400mm across and therefore 300mm down. Nothing may sit past it.
    assert tops[1] <= 300


def test_a_tall_shape_is_not_measured_against_the_width():
    site = picture_to_site(
        Picture(
            name="tall",
            pixel_width=400,
            pixel_height=200,
            finder="stated",
            shapes=[
                FoundShape(
                    kind=ShapeKind.RECT,
                    min_point=Vector2D(x=0.0, y=0.0),
                    max_point=Vector2D(x=0.25, y=0.25),
                    origin="stated",
                )
            ],
        ),
        scale=ScaleReference(millimetres_across=400),
    )
    box = site.children[0].footprint
    # The picture is 400mm across and 200mm down. A quarter of each is not the
    # same length, which is the whole point: 100mm across, 50mm down.
    assert box.width == pytest.approx(100.0)
    assert box.height == pytest.approx(50.0)


# ------------------------------------------------- the subject fills the frame


@pytest.mark.parametrize("edge", [280, 310, 369])
def test_one_object_filling_the_frame_is_the_object_not_the_background(tmp_path, edge):
    """Calling the rarer colour the subject fails the moment you fill the frame.

    Which is how anyone photographs one thing on purpose. It came back as a
    single shape covering the whole picture, at higher confidence than the
    correct answer got.
    """
    picture = Image.new("L", (400, 400), 255)
    ImageDraw.Draw(picture).rectangle((5, 5, edge, edge), fill=0)
    path = tmp_path / f"fills_{edge}.png"
    picture.save(path)

    found = PlainFinder().look(path).shapes
    assert len(found) == 1
    assert found[0].kind is ShapeKind.RECT
    assert found[0].width < 0.99, "the whole picture came back as one shape"


# ------------------------------------------------- how pictures are really saved


def test_a_see_through_background_does_not_hide_everything(tmp_path):
    """Anything exported with transparency stores black underneath it."""
    picture = Image.new("RGBA", (300, 300), (0, 0, 0, 0))
    ImageDraw.Draw(picture).rectangle((50, 50, 200, 200), fill=(0, 0, 0, 255))
    path = tmp_path / "seethrough.png"
    picture.save(path)
    assert len(PlainFinder().look(path).shapes) == 1


def test_a_photograph_is_read_the_way_up_it_is_meant_to_be_seen(tmp_path):
    """A phone stores the sensor's idea of up and a note saying the real one."""
    picture = Image.new("L", (400, 200), 255)
    ImageDraw.Draw(picture).rectangle((20, 20, 180, 80), fill=0)
    note = Image.Exif()
    note[274] = 6  # a quarter turn
    path = tmp_path / "sideways.jpg"
    picture.save(path, exif=note)
    seen = PlainFinder().look(path)
    assert (seen.pixel_width, seen.pixel_height) == (200, 400)


@pytest.mark.parametrize("edge", [64, 128, 256, 512, 1024])
def test_the_same_content_is_found_at_every_picture_size(tmp_path, edge):
    """Three dots at 4% of the edge. A speckle floor tied to the picture size
    threw all three away in a thumbnail and kept all three in a photograph."""
    picture = Image.new("L", (edge, edge), 255)
    pen = ImageDraw.Draw(picture)
    radius = edge * 0.04
    for cx, cy in ((0.25, 0.25), (0.5, 0.6), (0.75, 0.3)):
        pen.ellipse(
            (cx * edge - radius, cy * edge - radius, cx * edge + radius, cy * edge + radius),
            fill=0,
        )
    path = tmp_path / f"dots_{edge}.png"
    picture.save(path)
    assert len(PlainFinder().look(path).shapes) == 3


# ------------------------------------------------- references and angles


def test_a_tilted_reference_measures_its_own_length(tmp_path):
    """Measuring a tilted ruler by its upright box scaled the build a third too big."""
    straight = ScaleReference(known_shape="ruler", known_width_mm=300).millimetres_per_unit(
        _stated(label="ruler", long_side=0.6, short_side=0.05, turned_degrees=0)
    )
    tilted = ScaleReference(known_shape="ruler", known_width_mm=300).millimetres_per_unit(
        _stated(label="ruler", long_side=0.6, short_side=0.05, turned_degrees=45)
    )
    assert straight == pytest.approx(tilted)


def test_a_reference_naming_two_shapes_is_refused_not_guessed():
    two = Picture(
        name="two",
        pixel_width=100,
        pixel_height=100,
        finder="stated",
        shapes=[
            FoundShape(
                kind=ShapeKind.RECT,
                min_point=Vector2D(x=0.0, y=0.0),
                max_point=Vector2D(x=0.2, y=0.2),
                label="ref",
                origin="stated",
            ),
            FoundShape(
                kind=ShapeKind.RECT,
                min_point=Vector2D(x=0.5, y=0.5),
                max_point=Vector2D(x=0.9, y=0.9),
                label="ref",
                origin="stated",
            ),
        ],
    )
    with pytest.raises(AmbiguousReference):
        ScaleReference(known_shape="ref", known_width_mm=50).millimetres_per_unit(two)


def test_a_panel_barely_off_square_keeps_its_angle(tmp_path):
    """Five pixels off square is not noise, and its direction is unambiguous.

    Throwing it away built the panel a quarter turn out.
    """
    picture = Image.new("L", (600, 600), 255)
    middle, angle = 300, 45
    corners = [
        (
            middle + x * math.cos(math.radians(angle)) - y * math.sin(math.radians(angle)),
            middle + x * math.sin(math.radians(angle)) + y * math.cos(math.radians(angle)),
        )
        for x, y in [(-100, -97), (100, -97), (100, 97), (-100, 97)]
    ]
    ImageDraw.Draw(picture).polygon(corners, fill=20)
    path = tmp_path / "panel.png"
    picture.save(path)
    assert PlainFinder().look(path).shapes[0].turned_degrees == pytest.approx(45, abs=4)


def test_a_stated_angle_is_not_thrown_away():
    turned = picture_to_site(
        _stated(turned_degrees=45, long_side=0.7, short_side=0.1),
        scale=ScaleReference(millimetres_across=100),
    )
    assert "rotate" in turned.render()


# ------------------------------------------------- refusing nonsense


def test_a_box_that_runs_backwards_is_refused():
    with pytest.raises(ValueError, match="backwards"):
        FoundShape(
            kind=ShapeKind.RECT,
            min_point=Vector2D(x=0.9, y=0.9),
            max_point=Vector2D(x=0.1, y=0.1),
        )


def test_a_box_outside_the_picture_is_refused():
    with pytest.raises(ValueError, match="fractions of the"):
        FoundShape(
            kind=ShapeKind.RECT,
            min_point=Vector2D(x=-5.0, y=-5.0),
            max_point=Vector2D(x=9.0, y=9.0),
        )


@pytest.mark.parametrize("silly", [0, -5, float("inf"), float("nan")])
def test_a_width_that_is_not_a_width_is_refused(silly):
    with pytest.raises(ValueError):
        ScaleReference(millimetres_across=silly)


def test_an_empty_word_list_is_used_rather_than_quietly_replaced():
    """Passing a curated list and getting the starters back is worse than an error."""
    with pytest.raises(KeyError):
        picture_to_site(_stated(), words=WordList())


# ------------------------------------------------- the label fix broke nothing


def test_a_bad_child_does_not_break_a_shape_that_never_looks_at_children():
    from apothecary.api import _rehydrate

    built = _rehydrate(
        {"type": "sphere", "r": 3, "children": [{"type": "cube", "size": {"x": "?"}}]}
    )
    assert "sphere" in built.render()


def test_a_turn_described_in_a_way_we_do_not_handle_still_renders_something():
    from apothecary.api import _rehydrate

    assert _rehydrate({"type": "rotate", "a": [0, 0, 45], "children": []}) is not None
