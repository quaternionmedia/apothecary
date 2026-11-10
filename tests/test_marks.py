"""A whiteboard's marks sorted into a diagram's, writing and unsure, a person's
word on any of them kept as an example, and the sorter's thresholds fitted to
examples (apothecary/vision/marks.py).

The whiteboard is drawn here, so what each mark is, is known. The floors at the
foot were read off `apothecary photo check --finder outline` and set a little
under it.
"""

from __future__ import annotations

import json

import pytest
from click.testing import CliRunner
from PIL import Image, ImageDraw, ImageFont

from apothecary.cli.main import cli
from apothecary.vision import OutlineFinder, marks
from apothecary.vision.bench import run_sorting
from apothecary.vision.marks import Kind
from apothecary.vision.models import ShapeKind

WHITEBOARD = (238, 238, 236)
BLUE, RED, BLACK, GREEN = (20, 30, 120), (160, 20, 20), (10, 10, 10), (10, 120, 40)


@pytest.fixture
def whiteboard(tmp_path):
    """A plate with a hole and a label in it, a disc, a wedge, a dimension line
    with its size written under it, a remark, and one small ring alone."""
    image = Image.new("RGB", (1600, 1200), WHITEBOARD)
    pen = ImageDraw.Draw(image)
    pen.rectangle((250, 250, 700, 520), outline=BLUE, width=9)
    pen.ellipse((300, 420, 370, 490), outline=BLUE, width=7)
    pen.text((470, 300), "top plate", fill=BLACK, font=ImageFont.load_default(size=40))
    pen.ellipse((900, 250, 1200, 550), outline=BLUE, width=9)
    pen.polygon(((350, 950), (650, 950), (500, 700)), outline=RED, width=9)
    pen.line((250, 590, 700, 590), fill=BLACK, width=5)
    pen.text((400, 605), "120 mm", fill=BLACK, font=ImageFont.load_default(size=44))
    pen.text(
        (800, 800), "check the fit before cutting", fill=GREEN, font=ImageFont.load_default(size=40)
    )
    pen.ellipse((1290, 1000, 1370, 1080), outline=BLACK, width=6)
    path = tmp_path / "whiteboard.png"
    image.save(path)
    return path


def _at(found, x, y):
    """The smallest mark over a point of the picture, in its own pixels."""
    over = [
        m
        for m in found
        if m.min_point.x <= x / 1600 <= m.max_point.x and m.min_point.y <= y / 1200 <= m.max_point.y
    ]
    assert over, f"no mark at {x}, {y}"
    return min(over, key=lambda m: m.max_point.x - m.min_point.x)


def test_a_closed_stroke_a_line_and_writing_are_sorted_apart(whiteboard):
    found = marks.marks_in(whiteboard)
    assert _at(found, 252, 400).kind is Kind.DIAGRAM  # the plate's own stroke
    assert _at(found, 1050, 252).kind is Kind.DIAGRAM  # the disc's
    assert _at(found, 500, 948).kind is Kind.DIAGRAM  # the wedge's
    assert _at(found, 475, 590).kind is Kind.DIAGRAM  # the dimension line
    assert _at(found, 470, 630).kind is Kind.WRITING  # 120 mm
    assert _at(found, 1000, 825).kind is Kind.WRITING  # the remark, its letters run together
    assert all(0 < m.sure <= 0.85 and m.by == "sorter" and m.why for m in found)


def test_what_it_cannot_place_is_unsure_and_says_why(whiteboard):
    found = marks.marks_in(whiteboard)
    alone = _at(found, 1330, 1003)
    assert alone.kind is Kind.UNSURE and "a letter, or a hole" in alone.why


def test_a_closed_stroke_alone_inside_a_shape_is_a_cut_through_it(whiteboard):
    """The ring drawn in the plate is a diagram's, and the plate is read with it
    as a cut: where it was drawn, as wide as its stroke's middle, and round."""
    found = marks.marks_in(whiteboard)
    hole = _at(found, 335, 423)
    assert hole.kind is Kind.DIAGRAM and "is a cut" in hole.why and hole.sure < 0.8
    picture = OutlineFinder().look(whiteboard)
    plate = next(shape for shape in picture.shapes if shape.kind is ShapeKind.RECT)
    (cut,) = plate.cuts
    assert cut.kind is ShapeKind.DISC and cut.origin == "outline"
    assert (cut.centre.x, cut.centre.y) == pytest.approx((335 / 1600, 455 / 1200), abs=0.004)
    assert cut.long_side == pytest.approx(63 / 1600, abs=0.004)
    assert [shape.cuts for shape in picture.shapes if shape is not plate] == [[], []]


def test_a_cut_is_taken_out_of_the_piece_where_it_was_drawn(whiteboard):
    from apothecary.booleans import Difference
    from apothecary.vision import ScaleReference, build

    picture = OutlineFinder().look(whiteboard)
    built = build(picture, scale=ScaleReference(millimetres_across=1600))
    plate = next(p for p in built.site.children if p.category == "plate")
    assert isinstance(plate.base, Difference) and len(plate.base.children) == 2
    assert "1 cut(s) through it" in plate.comment
    scad = built.site.render()
    # The ring's stroke runs from 300 to 370 and is 7 wide, so its middle is 63
    # across; a millimetre a pixel here.
    assert "difference()" in scad and "cylinder(" in scad
    moved = plate.base.children[1]
    # From the plate's middle (475, 385) to the ring's (335, 455): left, and
    # towards the front of the build, which is down the picture.
    assert moved.v.x == pytest.approx(-140.0, abs=4) and moved.v.y == pytest.approx(-70.0, abs=4)
    assert type(moved.children[0]).__name__ == "Cylinder"
    assert moved.children[0].r == pytest.approx(31.5, abs=2.5)
    others = [p for p in built.site.children if p is not plate]
    assert not any(isinstance(p.base, Difference) for p in others if p.category != "slot")


def test_a_person_says_a_ring_inside_a_shape_is_no_cut(whiteboard):
    found = marks.marks_in(whiteboard)
    hole = _at(found, 335, 423)
    answers = marks.Answers(examples=[marks.say(found, hole.id, Kind.WRITING, picture="abc")])
    marks.save(marks.answers_path(whiteboard), answers)
    plate = next(s for s in OutlineFinder().look(whiteboard).shapes if s.kind is ShapeKind.RECT)
    assert plate.cuts == []


def test_a_mark_inside_a_closed_stroke_says_which(whiteboard):
    found = marks.marks_in(whiteboard)
    plate = _at(found, 252, 400)
    assert _at(found, 560, 325).inside == plate.id  # top plate, written in it
    assert _at(found, 335, 423).inside == plate.id  # the ring drawn in it
    assert plate.inside is None


def test_a_marks_colour_is_read_and_decides_nothing(whiteboard):
    found = marks.marks_in(whiteboard)
    assert _at(found, 500, 948).colour == "red"
    assert _at(found, 1000, 825).colour == "green"
    recoloured = Image.open(whiteboard).convert("L").convert("RGB")
    grey = whiteboard.with_name("grey.png")
    recoloured.save(grey)
    assert [m.kind for m in marks.marks_in(grey)] == [m.kind for m in found]


def test_only_a_diagrams_marks_are_read_as_shapes(whiteboard):
    """The ring alone and the hole are closed strokes, and neither is a shape
    until somebody says it is a diagram's."""
    picture = OutlineFinder().look(whiteboard)
    assert sorted(shape.kind.value for shape in picture.shapes) == ["disc", "rect", "tri"]


def test_a_persons_word_wins_says_who_and_is_kept_as_an_example(whiteboard):
    found = marks.marks_in(whiteboard)
    alone = _at(found, 1330, 1003)
    example = marks.say(found, alone.id, Kind.DIAGRAM, picture="abc")
    said = marks.apply(found, marks.Answers(examples=[example]))
    now = next(m for m in said if m.id == alone.id)
    assert (now.kind, now.by, now.sure, now.guess) == (Kind.DIAGRAM, "you", 1.0, Kind.UNSURE)
    assert example.guess is Kind.UNSURE and example.word is Kind.DIAGRAM
    assert example.features["closed"] == 1.0 and example.colour
    # Every other mark is as the sorter left it.
    assert [m.kind for m in said if m.id != alone.id] == [m.kind for m in found if m.id != alone.id]


def test_words_kept_beside_a_picture_change_what_is_read_from_it(whiteboard):
    """`photo marks --say` keeps the words beside the picture, and the finder
    reads the picture with them: the ring said to be a diagram's is a shape,
    the wedge said to be nothing is not."""
    found = marks.marks_in(whiteboard)
    alone, wedge = _at(found, 1330, 1003), _at(found, 500, 948)
    before = OutlineFinder().model_digest(whiteboard)
    done = CliRunner().invoke(
        cli,
        [
            "photo",
            "marks",
            str(whiteboard),
            "--say",
            f"{alone.id}=diagram",
            "--say",
            f"{wedge.id}=nothing",
        ],
    )
    assert done.exit_code == 0, done.output
    kept = json.loads(marks.answers_path(whiteboard).read_text(encoding="utf-8"))
    assert kept["format"] == marks.FORMAT and len(kept["examples"]) == 2
    assert {e["word"] for e in kept["examples"]} == {"diagram", "nothing"}
    assert "you" in done.output
    kinds = [shape.kind for shape in OutlineFinder().look(whiteboard).shapes]
    assert ShapeKind.TRI not in kinds and len(kinds) == 3
    assert OutlineFinder().model_digest(whiteboard) != before, (
        "the cache would hold the old reading"
    )


def test_a_word_that_is_no_kind_and_a_mark_that_is_not_there_are_refused(whiteboard):
    for said, means in (("m1=shape", "a word is one of"), ("m99=writing", "no mark 'm99'")):
        done = CliRunner().invoke(cli, ["photo", "marks", str(whiteboard), "--say", said])
        assert done.exit_code != 0 and means in done.output
    assert not marks.answers_path(whiteboard).exists()


def test_photo_marks_lists_each_mark_and_as_json(whiteboard):
    done = CliRunner().invoke(cli, ["photo", "marks", str(whiteboard)])
    assert done.exit_code == 0, done.output
    assert "diagram" in done.output and "writing" in done.output and "unsure" in done.output
    as_json = CliRunner().invoke(cli, ["photo", "marks", str(whiteboard), "--json"])
    assert {m["kind"] for m in json.loads(as_json.output)} == {"diagram", "writing", "unsure"}


def test_the_table_is_the_defaults_until_a_file_is_named(tmp_path, monkeypatch):
    assert marks.table() == marks.DEFAULTS
    named = tmp_path / "table.json"
    named.write_text(json.dumps({"small": 0.05, "nonsense": 1}), encoding="utf-8")
    monkeypatch.setenv(marks.TABLE_ENV, str(named))
    assert marks.table() == {**marks.DEFAULTS, "small": 0.05}


def _example(word: Kind, **features) -> marks.Example:
    return marks.Example(
        picture="abc",
        min=(0.1, 0.1),
        max=(0.2, 0.2),
        guess=Kind.UNSURE,
        sure=0.4,
        word=word,
        features=features,
    )


def test_a_fit_moves_a_threshold_to_what_people_said():
    """Two-stroke words a person called writing: the default run of three leaves
    them unsure, and the fit takes the run to two."""
    words = [
        _example(Kind.WRITING, tall=0.04, wide=0.07, strokes=2.0, thin=0.6, long=0.07)
        for _ in range(6)
    ]
    assert marks.score(words, marks.DEFAULTS) == 0.0
    fitted, before, after = marks.fit(words)
    assert (before, after) == (0.0, 1.0) and fitted["run"] == 2.0
    same, start, end = marks.fit([_example(Kind.DIAGRAM, tall=0.3, wide=0.3, closed=1.0)])
    assert same == marks.table() and start == end == 1.0


def _two_stroke_words(count: int) -> list:
    return [
        _example(Kind.WRITING, tall=0.04, wide=0.07, strokes=2.0, thin=0.6, long=0.07)
        for _ in range(count)
    ]


def _short_words(count: int) -> list:
    """One-stroke words under twice as wide as tall, which a person called writing."""
    return [
        _example(Kind.WRITING, tall=0.04, wide=0.07, strokes=1.0, thin=0.6, long=0.07)
        for _ in range(count)
    ]


def test_photo_fit_prints_a_fit_and_writes_it_where_named(tmp_path):
    kept = tmp_path / "words.marks.json"
    marks.save(kept, marks.Answers(examples=_short_words(4)))
    out = tmp_path / "table.json"
    done = CliRunner().invoke(cli, ["photo", "fit", str(kept), "--out", str(out), "--count", "6"])
    assert done.exit_code == 0, done.output
    assert "4 example(s): 0% sorted as their person did, 100% fitted" in done.output
    assert json.loads(out.read_text(encoding="utf-8"))["wide"] == 1.5
    printed = CliRunner().invoke(cli, ["photo", "fit", str(kept), "--count", "6"])
    assert printed.exit_code == 0 and '"wide": 1.5' in printed.output
    empty = tmp_path / "none.marks.json"
    marks.save(empty, marks.Answers())
    refused = CliRunner().invoke(cli, ["photo", "fit", str(empty)])
    assert refused.exit_code != 0 and "no examples" in refused.output


def test_a_fit_that_sorts_the_drawn_whiteboards_worse_is_refused(tmp_path):
    """Marks two and a half times as wide as tall that somebody called unsure fit a
    reach of three, which leaves the drawn whiteboards' short words unsure too; the
    fit is refused and nothing is written."""
    doubted = [
        _example(Kind.UNSURE, tall=0.04, wide=0.1, strokes=1.0, thin=0.4, long=0.1)
        for _ in range(6)
    ]
    kept = tmp_path / "words.marks.json"
    marks.save(kept, marks.Answers(examples=doubted))
    out = tmp_path / "table.json"
    done = CliRunner().invoke(cli, ["photo", "fit", str(kept), "--out", str(out), "--count", "20"])
    assert done.exit_code != 0 and "worse" in done.output, done.output
    assert not out.exists()


SORTED = [
    ("writing beside", {}, 0.95),
    ("turned", dict(turn=True), 0.95),
    ("shadowed", dict(shadow=0.4), 0.95),
    ("smeared", dict(smear=True), 0.95),
    ("framed", dict(framed=True), 0.95),
]


@pytest.mark.slow
@pytest.mark.parametrize("label, drawing, least_right", SORTED)
def test_the_sorter_holds_its_measured_floor(label, drawing, least_right):
    result = run_sorting(count=20, **drawing)
    assert result.right_rate >= least_right, f"{label}: {result}"
    assert result.diagram_as_writing == 0 and result.missed == 0, f"{label}: {result}"
    assert result.writing_as_diagram <= 1, f"{label}: {result}"
