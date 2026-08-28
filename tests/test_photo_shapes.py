"""The picture path: finding shapes, choosing words, placing them."""

from __future__ import annotations

import json

import pytest
from click.testing import CliRunner

from apothecary.cli import cli
from apothecary.hierarchy import Assembly
from apothecary.models.vectors import Vector2D
from apothecary.vision import (
    MissingDescriptionError,
    PlainFinder,
    ScaleReference,
    ScaleUnknown,
    ShapeFinder,
    StatedFinder,
    get,
    names,
    picture_to_site,
)
from apothecary.vision.models import FoundShape, Picture, ShapeKind
from apothecary.vocabulary import UnknownWordError, WordShape, starter_words, word_for

# ---------------------------------------------------------------- pictures


def _draw(path, shapes, size=(400, 300)):
    """Paint a plain test picture: white ground, black shapes."""
    from PIL import Image, ImageDraw

    image = Image.new("L", size, 255)
    pen = ImageDraw.Draw(image)
    for kind, box in shapes:
        if kind == "rect":
            pen.rectangle(box, fill=0)
        elif kind == "disc":
            pen.ellipse(box, fill=0)
        elif kind == "tri":
            x0, y0, x1, y1 = box
            pen.polygon([(x0, y1), (x1, y1), ((x0 + x1) / 2, y0)], fill=0)
    image.save(path)
    return path


@pytest.fixture
def three_shapes(tmp_path):
    return _draw(
        tmp_path / "three.png",
        [("rect", (20, 20, 120, 90)), ("disc", (200, 40, 300, 140)), ("tri", (60, 170, 180, 270))],
    )


@pytest.fixture
def stated_picture(tmp_path):
    image = tmp_path / "stated.png"
    image.write_bytes(b"not really a picture, and never opened")
    (tmp_path / "stated.shapes.json").write_text(
        json.dumps(
            {
                "name": "stated",
                "pixel_width": 400,
                "pixel_height": 300,
                "shapes": [
                    {"kind": "rect", "min": [0.05, 0.05], "max": [0.30, 0.30], "label": "ruler"},
                    {"kind": "disc", "min": [0.50, 0.10], "max": [0.75, 0.45]},
                ],
            }
        )
    )
    return image


# ---------------------------------------------------------------- the connection


def test_both_finders_satisfy_the_connection():
    assert isinstance(StatedFinder(), ShapeFinder)
    assert isinstance(PlainFinder(), ShapeFinder)


def test_both_finders_are_registered():
    assert names() == ["plain", "stated"]
    assert get("plain").name() == "plain"
    assert get("stated").name() == "stated"


def test_asking_for_a_finder_nobody_registered_says_what_exists():
    with pytest.raises(KeyError, match="plain"):
        get("magic")


# ---------------------------------------------------------------- stated finder


def test_stated_finder_reads_what_was_written(stated_picture):
    picture = StatedFinder().look(stated_picture)
    assert picture.pixel_width == 400
    assert [s.kind for s in picture.shapes] == [ShapeKind.RECT, ShapeKind.DISC]
    assert all(s.origin == "stated" for s in picture.shapes)
    assert picture.guessed is False


def test_stated_finder_refuses_to_guess(tmp_path):
    lonely = tmp_path / "nothing-beside-it.png"
    lonely.write_bytes(b"")
    with pytest.raises(MissingDescriptionError):
        StatedFinder().look(lonely)


# ---------------------------------------------------------------- plain finder


def test_plain_finder_finds_three_shapes(three_shapes):
    picture = PlainFinder().look(three_shapes)
    assert picture.finder == "plain"
    assert len(picture.shapes) == 3
    assert picture.pixel_width == 400 and picture.pixel_height == 300


def test_plain_finder_recognises_the_families(three_shapes):
    found = {s.kind for s in PlainFinder().look(three_shapes).shapes}
    assert {ShapeKind.RECT, ShapeKind.DISC, ShapeKind.TRI} <= found


def test_plain_finder_never_claims_certainty(three_shapes):
    for shape in PlainFinder().look(three_shapes).shapes:
        assert shape.origin == "plain"
        assert shape.confidence <= 0.8


def test_plain_finder_reports_the_whole_picture_as_guessed(three_shapes):
    assert PlainFinder().look(three_shapes).guessed is True


def test_plain_finder_works_the_same_on_light_shapes(tmp_path):
    """Dark on light and light on dark are the same picture, inverted."""
    from PIL import Image, ImageOps

    dark_on_light = _draw(tmp_path / "dark.png", [("rect", (40, 40, 160, 120))])
    light_on_dark = tmp_path / "light.png"
    with Image.open(dark_on_light) as opened:
        ImageOps.invert(opened.convert("L")).save(light_on_dark)

    a = PlainFinder().look(dark_on_light)
    b = PlainFinder().look(light_on_dark)
    assert len(a.shapes) == len(b.shapes) == 1
    assert a.shapes[0].kind is b.shapes[0].kind


def test_plain_finder_ignores_speckle(tmp_path):
    picture = _draw(
        tmp_path / "speckle.png",
        [("rect", (40, 40, 200, 160)), ("rect", (300, 250, 302, 252))],
    )
    assert len(PlainFinder().look(picture).shapes) == 1


# ---------------------------------------------------------------- words


def test_the_starter_list_has_five_words():
    words = starter_words()
    assert words.names() == ["disc", "plate", "post", "slot", "wedge"]


def test_a_word_builds_an_ordinary_assembly_node():
    made = starter_words().get("plate").make("shelf", WordShape(width=100, depth=50, height=8))
    assert isinstance(made, Assembly)
    assert made.name == "shelf"
    assert made.role == "word"
    # A leaf's own shape is reached through to_scad_object; render() on a node
    # draws what is beneath it, and a word placed nowhere yet has nothing beneath.
    assert "cube" in made.to_scad_object().render()


def test_the_same_word_twice_gives_two_separate_things():
    words = starter_words()
    a = words.get("disc").make("one")
    b = words.get("disc").make("two")
    assert a is not b and a.name != b.name


def test_a_name_can_only_be_used_once():
    from apothecary.vocabulary.word import Word

    words = starter_words()
    with pytest.raises(ValueError, match="already registered"):
        words.add(
            Word(name="plate", describes="a second plate", build=lambda n, s: Assembly(name=n))
        )


def test_asking_for_an_unknown_word_says_what_exists():
    with pytest.raises(UnknownWordError, match="plate"):
        starter_words().get("flange")


# ---------------------------------------------------------------- matching


@pytest.mark.parametrize(
    "kind, box, expected",
    [
        (ShapeKind.RECT, (0.0, 0.0, 0.4, 0.4), "plate"),
        (ShapeKind.RECT, (0.0, 0.0, 0.9, 0.05), "slot"),
        (ShapeKind.DISC, (0.0, 0.0, 0.3, 0.3), "disc"),
        (ShapeKind.DISC, (0.0, 0.0, 0.05, 0.9), "post"),
        (ShapeKind.TRI, (0.0, 0.0, 0.3, 0.3), "wedge"),
        (ShapeKind.LINE, (0.0, 0.0, 0.9, 0.01), "slot"),
        (ShapeKind.POLY, (0.0, 0.0, 0.3, 0.3), "plate"),
    ],
)
def test_each_shape_reads_as_the_expected_word(kind, box, expected):
    shape = FoundShape(
        kind=kind,
        min_point=Vector2D(x=box[0], y=box[1]),
        max_point=Vector2D(x=box[2], y=box[3]),
    )
    choice = word_for(shape)
    assert choice.word == expected
    assert choice.reason


def test_every_word_the_table_names_actually_exists():
    from apothecary.vocabulary.match import TABLE

    words = starter_words()
    for rule in TABLE:
        assert rule.word in words, f"the table names {rule.word!r} and no such word exists"


# ---------------------------------------------------------------- placing


def _two_shape_picture():
    return Picture(
        name="bench",
        pixel_width=400,
        pixel_height=300,
        finder="stated",
        shapes=[
            FoundShape(
                kind=ShapeKind.RECT,
                min_point=Vector2D(x=0.0, y=0.0),
                max_point=Vector2D(x=0.4, y=0.4),
                origin="stated",
                label="ruler",
            ),
            FoundShape(
                kind=ShapeKind.DISC,
                min_point=Vector2D(x=0.6, y=0.6),
                max_point=Vector2D(x=0.9, y=0.9),
                origin="stated",
            ),
        ],
    )


def test_without_a_real_size_nothing_is_measured():
    site = picture_to_site(_two_shape_picture())
    assert len(site.children) == 2
    for piece in site.children:
        assert piece.footprint is None
        assert piece.status == "unsized"
        assert "no real-world size" in piece.comment


def test_without_a_real_size_the_overlap_check_stays_quiet():
    """Not 'no overlaps' — nothing to check. Being confidently wrong would be worse."""
    report = picture_to_site(_two_shape_picture()).validate()
    assert report.is_valid
    assert report.violations == []


def test_a_stated_width_gives_real_millimetres():
    site = picture_to_site(_two_shape_picture(), scale=ScaleReference(millimetres_across=1000))
    plate = site.children[0]
    assert plate.status is None
    assert plate.footprint is not None
    assert plate.footprint.width == pytest.approx(400.0)


def test_a_known_shape_can_supply_the_size():
    site = picture_to_site(
        _two_shape_picture(),
        scale=ScaleReference(known_shape="ruler", known_width_mm=200),
    )
    # The ruler covers 0.4 of the picture and is 200mm, so the whole width is 500mm.
    assert site.children[0].footprint.width == pytest.approx(200.0)


def test_a_reference_naming_a_shape_that_is_not_there_supplies_nothing():
    site = picture_to_site(
        _two_shape_picture(),
        scale=ScaleReference(known_shape="absent", known_width_mm=200),
    )
    assert all(p.status == "unsized" for p in site.children)


def test_you_can_insist_on_a_real_size():
    with pytest.raises(ScaleUnknown, match="real-world reference"):
        picture_to_site(_two_shape_picture(), require_scale=True)


def test_every_piece_records_where_it_came_from_and_what_was_guessed():
    site = picture_to_site(_two_shape_picture())
    for piece in site.children:
        assert "found by stated" in piece.comment
        assert "thickness is a guess" in piece.comment


def test_the_picture_is_flipped_so_the_top_of_the_picture_is_the_far_edge():
    site = picture_to_site(_two_shape_picture(), scale=ScaleReference(millimetres_across=1000))
    near_top_of_picture, near_bottom_of_picture = site.children
    assert near_top_of_picture.position.y > near_bottom_of_picture.position.y


def test_an_arrangement_renders_to_drawing_instructions():
    drawing = picture_to_site(_two_shape_picture()).render()
    assert "cube" in drawing and "cylinder" in drawing


# ---------------------------------------------------------------- commands


def test_look_reports_what_was_found(three_shapes):
    result = CliRunner().invoke(cli, ["photo", "look", str(three_shapes)])
    assert result.exit_code == 0, result.output
    assert "3 shape(s)" in result.output
    assert "Nothing above is a measurement" in result.output


def test_look_can_use_the_stated_finder(stated_picture):
    result = CliRunner().invoke(cli, ["photo", "look", str(stated_picture), "--finder", "stated"])
    assert result.exit_code == 0, result.output
    assert "2 shape(s)" in result.output


def test_look_explains_an_unknown_finder(three_shapes):
    result = CliRunner().invoke(cli, ["photo", "look", str(three_shapes), "--finder", "magic"])
    assert result.exit_code != 0
    assert "plain" in result.output and "stated" in result.output


def test_build_says_plainly_when_nothing_is_measured(three_shapes):
    result = CliRunner().invoke(cli, ["photo", "build", str(three_shapes)])
    assert result.exit_code == 0, result.output
    assert "(no real size)" in result.output
    assert "nothing to check" in result.output


def test_build_with_a_width_writes_drawing_instructions(three_shapes, tmp_path):
    out = tmp_path / "bench.scad"
    result = CliRunner().invoke(
        cli, ["photo", "build", str(three_shapes), "--width-mm", "500", "--out", str(out)]
    )
    assert result.exit_code == 0, result.output
    assert out.exists() and "cube" in out.read_text()
    assert "(no real size)" not in result.output


def test_words_lists_the_vocabulary():
    result = CliRunner().invoke(cli, ["photo", "words"])
    assert result.exit_code == 0
    assert "5 word(s)" in result.output
    assert "plate" in result.output


def test_finders_lists_both():
    result = CliRunner().invoke(cli, ["photo", "finders"])
    assert result.exit_code == 0
    assert result.output.split() == ["plain", "stated"]


# ---------------------------------------------------------------- turned pieces


def _turned_bar_picture(degrees: float):
    """One long bar, lying at an angle, with its true sides known."""
    from apothecary.vision.models import FoundShape, Picture

    return Picture(
        name="bar",
        pixel_width=400,
        pixel_height=400,
        finder="stated",
        shapes=[
            FoundShape(
                kind=ShapeKind.RECT,
                min_point=Vector2D(x=0.2, y=0.35),
                max_point=Vector2D(x=0.8, y=0.65),
                turned_degrees=degrees,
                long_side=0.60,
                short_side=0.15,
                origin="stated",
            )
        ],
    )


def test_a_piece_is_built_from_its_own_sides_not_its_upright_box():
    """The upright box round a tilted bar is far bigger than the bar."""
    site = picture_to_site(_turned_bar_picture(35), scale=ScaleReference(millimetres_across=1000))
    piece = site.children[0]
    # On a bounding box, width is across, height is back, depth is up.
    assert piece.footprint.width == pytest.approx(600.0)
    assert piece.footprint.height == pytest.approx(150.0)


def test_a_turned_shape_produces_a_turned_piece():
    drawing = picture_to_site(
        _turned_bar_picture(35), scale=ScaleReference(millimetres_across=1000)
    ).render()
    assert "rotate" in drawing


def test_an_upright_shape_produces_no_turn():
    drawing = picture_to_site(
        _turned_bar_picture(0), scale=ScaleReference(millimetres_across=1000)
    ).render()
    assert "rotate" not in drawing


def test_a_piece_sits_on_its_own_middle_so_turning_does_not_move_it():
    """Turned about a corner, a long bar swings right out of the picture."""
    site = picture_to_site(_turned_bar_picture(90), scale=ScaleReference(millimetres_across=1000))
    piece = site.children[0]
    assert piece.position.x == pytest.approx(500.0)
    assert piece.footprint.min_point.x == pytest.approx(-300.0)
    assert piece.footprint.max_point.x == pytest.approx(300.0)


def test_a_shape_whose_sides_were_never_measured_falls_back_to_its_box():
    site = picture_to_site(_two_shape_picture(), scale=ScaleReference(millimetres_across=1000))
    assert site.children[0].footprint.width == pytest.approx(400.0)


def test_both_finders_accept_a_plain_string(three_shapes, stated_picture):
    assert PlainFinder().look(str(three_shapes)).shapes
    assert StatedFinder().look(str(stated_picture)).shapes
