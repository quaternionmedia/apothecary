"""A whiteboard photographed again: what changed is proposed, and only the rows a
person takes are applied (apothecary/vision/again.py). Both photographs are
drawn here, the second the first with its drawing changed."""

from __future__ import annotations

import json

import pytest
from click.testing import CliRunner
from PIL import Image, ImageDraw

from apothecary.cli.main import cli
from apothecary.vision import OutlineFinder, again
from apothecary.vision.again import Change
from apothecary.vision.models import ShapeKind

INK = (20, 30, 120)


def _whiteboard(
    path, *, plate=(250, 250, 700, 520), disc=(900, 250, 1200, 550), wedge=True, extra=False
):
    image = Image.new("RGB", (1600, 1200), (238, 238, 236))
    pen = ImageDraw.Draw(image)
    pen.rectangle(plate, outline=INK, width=9)
    if disc:
        pen.ellipse(disc, outline=INK, width=9)
    if wedge:
        pen.polygon(((350, 950), (650, 950), (500, 700)), outline=INK, width=9)
    if extra:
        pen.rectangle((1000, 750, 1300, 1000), outline=INK, width=9)
    image.save(path)
    return path


@pytest.fixture
def first(tmp_path):
    return OutlineFinder().look(_whiteboard(tmp_path / "first.png"))


def _second(tmp_path, **changed):
    return OutlineFinder().look(_whiteboard(tmp_path / "second.png", **changed))


def test_the_same_drawing_photographed_again_proposes_nothing(first, tmp_path):
    assert again.compare(first, _second(tmp_path)) == []


def test_each_kind_of_change_is_one_row_that_says_by_how_much(first, tmp_path):
    """The plate drawn wider, the disc moved, the wedge rubbed out, a plate added."""
    second = _second(
        tmp_path, plate=(250, 250, 800, 520), disc=(960, 250, 1260, 550), wedge=False, extra=True
    )
    rows = again.compare(first, second)
    assert sorted(row.change.value for row in rows) == ["gone", "moved", "new", "resized"]
    by = {row.change: row for row in rows}
    assert by[Change.RESIZED].kind == "rect" and "1.2" in by[Change.RESIZED].says
    assert by[Change.MOVED].kind == "disc" and "of the picture's width" in by[Change.MOVED].says
    assert by[Change.GONE].kind == "tri" and by[Change.GONE].after is None
    assert by[Change.NEW].kind == "rect" and by[Change.NEW].before is None
    assert [row.number for row in rows] == [1, 2, 3, 4] and all(row.takeable for row in rows)


def test_nothing_changes_until_a_row_is_taken_and_then_only_that_row(first, tmp_path):
    second = _second(
        tmp_path, plate=(250, 250, 800, 520), disc=(960, 250, 1260, 550), wedge=False, extra=True
    )
    rows = again.compare(first, second)
    by = {row.change: row.number for row in rows}
    left = again.taken_from(first, second, rows, [])
    assert left.shapes == first.shapes

    moved = again.taken_from(first, second, rows, [by[Change.MOVED]])
    disc = next(s for s in moved.shapes if s.kind is ShapeKind.DISC)
    assert disc.centre.x == pytest.approx(1110 / 1600, abs=0.01)
    plate = next(s for s in moved.shapes if s.kind is ShapeKind.RECT)
    assert plate.long_side == pytest.approx(441 / 1600, abs=0.01), "the plate's row was left"
    assert len(moved.shapes) == 3

    everything = again.taken_from(first, second, rows, list(by.values()))
    assert sorted(s.kind.value for s in everything.shapes) == ["disc", "rect", "rect"]
    with pytest.raises(KeyError, match="no row 9"):
        again.taken_from(first, second, rows, [9])


def test_a_shape_a_person_sized_is_not_proposed_over(first, tmp_path):
    """The plate's sides are a person's: drawn wider, its row says the two
    disagree and by how much, and cannot be taken."""
    second = _second(tmp_path, plate=(250, 250, 800, 520))
    plate_at = next(i for i, s in enumerate(first.shapes) if s.kind is ShapeKind.RECT)
    (row,) = again.compare(first, second, stated=[plate_at])
    assert row.change is Change.DISAGREES and not row.takeable
    assert "disagree" in row.says and "1.2" in row.says
    with pytest.raises(ValueError, match="A person's sides stand"):
        again.taken_from(first, second, [row], [row.number])
    # Moved and not resized, a stated shape's row is an ordinary one.
    moved = OutlineFinder().look(_whiteboard(tmp_path / "third.png", plate=(350, 250, 800, 520)))
    (row,) = again.compare(first, moved, stated=[plate_at])
    assert row.change is Change.MOVED and row.takeable


def test_a_cut_drawn_in_a_shape_since_is_a_change_to_it(first, tmp_path):
    path = _whiteboard(tmp_path / "cut.png")
    with Image.open(path) as image:
        ImageDraw.Draw(image).ellipse((300, 420, 370, 490), outline=INK, width=7)
        image.save(path)
    (row,) = again.compare(first, OutlineFinder().look(path))
    assert row.change is Change.RESIZED and "1 cut(s) more" in row.says


def test_photo_again_lists_rows_takes_some_and_keeps_what_was_done(tmp_path):
    before = _whiteboard(tmp_path / "before.png")
    after = _whiteboard(tmp_path / "after.png", disc=(960, 250, 1260, 550), wedge=False)
    listed = CliRunner().invoke(cli, ["photo", "again", str(before), str(after)])
    assert listed.exit_code == 0, listed.output
    assert (
        "2 change(s) proposed" in listed.output
        and "nothing taken, so nothing changed" in listed.output
    )
    gone = next(line.split()[0] for line in listed.output.splitlines() if " gone " in line)
    kept, out = tmp_path / "rows.json", tmp_path / "after.scad"
    taken = CliRunner().invoke(
        cli,
        [
            "photo",
            "again",
            str(before),
            str(after),
            "--take",
            gone,
            "--width-mm",
            "1600",
            "--answers",
            str(kept),
            "--out",
            str(out),
        ],
    )
    assert taken.exit_code == 0, taken.output
    assert "2 piece(s) after 1 row(s) taken" in taken.output
    held = json.loads(kept.read_text(encoding="utf-8"))
    assert (
        held["format"] == again.FORMAT and held["taken"] == [int(gone)] and len(held["rows"]) == 2
    )
    assert "cylinder(" in out.read_text(encoding="utf-8")
    refused = CliRunner().invoke(cli, ["photo", "again", str(before), str(after), "--take", "9"])
    assert refused.exit_code != 0 and "no row 9" in refused.output
