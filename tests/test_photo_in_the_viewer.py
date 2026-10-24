"""An arrangement built from a picture, in the viewer the tool already has.

The point of these is that almost nothing new had to be drawn. The viewer
already picks an arrangement by name, walks into it, and filters it by the group
each piece belongs to. Naming each piece's word as its group is what makes that
last one a filter by word.
"""

from __future__ import annotations

import os
import sys
from unittest.mock import patch

import pytest
from click.testing import CliRunner
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

from apothecary.api import _site_store, app
from apothecary.cli import cli
from apothecary.vision import PlainFinder, ScaleReference, build
from apothecary.vision.shelf import Shelf

client = TestClient(app)


@pytest.fixture
def picture(tmp_path, monkeypatch):
    # The server reads pictures from one folder and refuses everywhere else, and
    # checks again every time it serves one. Say which folder.
    monkeypatch.setenv("APOTHECARY_PICTURE_ROOT", str(tmp_path))
    drawn = Image.new("L", (640, 480), 245)
    pen = ImageDraw.Draw(drawn)
    pen.rectangle((40, 40, 260, 160), fill=30)
    pen.ellipse((360, 60, 520, 220), fill=20)
    pen.polygon([(80, 420), (300, 420), (190, 280)], fill=25)
    path = tmp_path / "bench.png"
    drawn.save(path)
    return path


@pytest.fixture
def shelved(picture):
    """One arrangement built from a picture, put where the viewer looks."""
    made = build(
        PlainFinder().look(picture),
        name="test_bench",
        scale=ScaleReference(millimetres_across=800),
        picture_path=picture,
    )
    stock = Shelf()
    stock.put(made)
    _site_store.add("test_bench", stock.factory("test_bench"), stock.checker("test_bench"))

    from apothecary.vision import shelf as shelf_module

    with patch.object(shelf_module, "_shelf", stock):
        yield made

    # The register belongs to the whole program, so anything put on it here has
    # to come back off. A test that leaves something behind is a test that
    # breaks a different one.
    _site_store.remove("test_bench")


# ---------------------------------------------------------------- grouping


def test_each_piece_carries_the_word_it_came_from_as_its_group(shelved):
    groups = {piece.category for piece in shelved.site.children}
    assert groups <= {"plate", "disc", "post", "slot", "wedge"}
    assert None not in groups


def test_the_viewer_sees_those_groups_without_any_new_drawing_code(shelved):
    """The filter the viewer already has becomes a filter by word."""
    tree = client.get("/sites/test_bench").json()["tree"]
    assert {child["category"] for child in tree["children"]} == {
        piece.category for piece in shelved.site.children
    }


def test_pieces_are_gathered_by_word_with_the_biggest_group_first(shelved):
    sizes = [len(paths) for paths in shelved.album.groups().values()]
    assert sizes == sorted(sizes, reverse=True)


# ---------------------------------------------------------------- what is known


def test_what_is_known_sits_beside_the_arrangement_not_inside_it(shelved):
    """A node gained no new fields, so the tree is the shape it always was.

    The reasoning does appear in each piece's note, in words, on purpose — that
    is what makes it readable in the viewer today. What has not happened is a
    node growing fields to carry it.
    """
    piece = shelved.site.children[0]
    for invented in ("confidence", "finder", "origin", "word", "provenance"):
        assert invented not in type(piece).model_fields

    assert set(shelved.album.provenance) == {p.name for p in shelved.site.children}


def test_every_piece_can_say_where_it_came_from(shelved):
    for path, about in shelved.album.provenance.items():
        assert about.word and about.reason and about.finder
        assert 0.0 <= about.confidence <= 1.0
        assert about.summary().startswith(about.word)
        assert path in shelved.album.groups()[about.word]


def test_the_least_sure_pieces_are_the_ones_worth_checking(shelved):
    doubtful = shelved.album.unsure(below=0.9)
    ordered = [shelved.album.provenance[path].confidence for path in doubtful]
    assert ordered == sorted(ordered), "the least sure should come first"


def test_a_machine_guessing_the_shape_is_counted_apart_from_having_a_real_size(shelved):
    """A piece can be correctly sized and still be a guess about what it is."""
    assert shelved.album.sized is True
    assert shelved.album.guessed_share() == 1.0


# ---------------------------------------------------------------- over the API


def test_an_arrangement_built_from_a_picture_appears_beside_the_others(shelved):
    assert "test_bench" in client.get("/sites").json()


def test_what_is_known_is_available_over_the_api(shelved):
    known = client.get("/photos/test_bench").json()
    assert known["finder"] == "plain"
    assert known["sized"] is True
    assert known["groups"]
    assert all("summary" in piece for piece in known["pieces"].values())


def test_the_picture_itself_is_served_beside_the_arrangement(shelved):
    answer = client.get("/photos/test_bench/picture")
    assert answer.status_code == 200
    assert answer.headers["content-type"] == "image/png"
    assert answer.content[:4] == b"\x89PNG"


def test_asking_about_an_arrangement_that_is_not_there_says_so(shelved):
    assert client.get("/photos/nothing_here").status_code == 404
    assert client.get("/photos/nothing_here/picture").status_code == 404


def test_a_picture_that_has_moved_since_is_reported_rather_than_guessed_at(shelved, tmp_path):
    (tmp_path / "bench.png").unlink()
    answer = client.get("/photos/test_bench/picture")
    assert answer.status_code == 404
    assert "no longer where it was" in answer.json()["detail"]


# ---------------------------------------------------------------- the shelf


def test_the_shelf_replaces_an_arrangement_of_the_same_name(picture):
    stock = Shelf()
    first = build(PlainFinder().look(picture), name="same", picture_path=picture)
    stock.put(first)
    stock.put(build(PlainFinder().look(picture), name="same", picture_path=picture))
    assert stock.names() == ["same"]
    assert len(stock) == 1


def test_the_register_takes_an_arrangement_it_did_not_start_with(picture):
    """The register held only what was decided in advance. A picture is not."""
    stock = Shelf()
    stock.put(build(PlainFinder().look(picture), name="added_later", picture_path=picture))
    _site_store.add("added_later", stock.factory("added_later"), stock.checker("added_later"))
    try:
        assert "added_later" in _site_store.names()
        assert _site_store.get("added_later").name == "added_later"
    finally:
        _site_store.remove("added_later")


# ---------------------------------------------------------------- one command


def test_one_command_builds_it_and_opens_the_viewer_on_it(picture):
    """Held in memory, so building and showing have to be the same program."""
    with patch("uvicorn.run") as started:
        result = CliRunner().invoke(
            cli, ["photo", "view", str(picture), "--name", "one_go", "--width-mm", "800"]
        )
    try:
        assert result.exit_code == 0, result.output
        assert started.call_count == 1
        assert "/viewer/sites/one_go" in result.output
        assert "one_go" in _site_store.names()
    finally:
        _site_store.remove("one_go")


def test_the_command_says_plainly_when_nothing_is_measured(picture):
    with patch("uvicorn.run"):
        result = CliRunner().invoke(cli, ["photo", "view", str(picture), "--name", "unsized_go"])
    _site_store.remove("unsized_go")
    assert "Nothing is measured" in result.output


def test_the_command_listens_only_to_this_machine_unless_told_otherwise(picture):
    with patch("uvicorn.run") as started:
        CliRunner().invoke(cli, ["photo", "view", str(picture), "--name", "local_go"])
    _site_store.remove("local_go")
    assert started.call_args.kwargs["host"] == "127.0.0.1"


def test_an_arrangement_can_be_taken_back_off_the_register(picture):
    """Otherwise every test that adds one quietly breaks the next."""
    stock = Shelf()
    stock.put(build(PlainFinder().look(picture), name="temporary", picture_path=picture))
    before = set(_site_store.names())
    _site_store.add("temporary", stock.factory("temporary"), stock.checker("temporary"))
    assert _site_store.remove("temporary") is True
    assert set(_site_store.names()) == before
    assert _site_store.remove("temporary") is False


# ---------------------------------------------------------------- refusals


def test_an_arrangement_from_a_picture_cannot_cover_a_built_in_one(picture, tmp_path):
    """Naming it 'garage' used to replace the built-in garage, permanently."""
    answer = client.post("/photos", json={"picture": str(picture), "name": "garage"})
    assert answer.status_code == 409
    assert len(client.get("/sites/garage").json()["tree"]["children"]) > 3


def test_a_built_in_arrangement_cannot_be_forgotten(picture):
    """Deleting it used to remove it from the register for the whole run."""
    assert client.delete("/photos/garage").status_code == 404
    assert "garage" in client.get("/sites").json()


@pytest.mark.parametrize("bad", ["a/b", "../../etc/x", "x" * 100, "a\nb", "a b"])
def test_a_name_that_is_not_a_name_is_refused(picture, bad):
    """These were stored and then could never be fetched or deleted again."""
    assert client.post("/photos", json={"picture": str(picture), "name": bad}).status_code in (
        400,
        422,
    )


def test_an_empty_name_falls_back_to_the_file_name(picture):
    answer = client.post("/photos", json={"picture": str(picture), "name": ""})
    assert answer.status_code == 200
    assert answer.json()["name"] == "bench"
    client.delete("/photos/bench")


def test_a_picture_outside_the_one_folder_is_refused(picture, tmp_path):
    outside = tmp_path.parent / "outside.png"
    Image.new("L", (10, 10), 255).save(outside)
    assert client.post("/photos", json={"picture": str(outside)}).status_code == 403


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="named pipes are a POSIX thing")
def test_something_that_is_not_an_ordinary_file_is_refused(picture, tmp_path):
    """A pipe exists, and opening one waits for a writer that never comes."""

    pipe = tmp_path / "pipe.png"
    os.mkfifo(pipe)
    assert client.post("/photos", json={"picture": str(pipe)}).status_code == 404


def test_the_type_is_chosen_from_a_list_not_built_from_the_file_name(picture, tmp_path):
    """A file name can contain the characters that end a header."""
    import shutil

    odd = tmp_path / "odd.weird"
    shutil.copy(picture, odd)
    client.post("/photos", json={"picture": str(odd), "name": "oddtype"})
    answer = client.get("/photos/oddtype/picture")
    assert answer.headers["content-type"].startswith("application/octet-stream")
    assert answer.headers["x-content-type-options"] == "nosniff"
    client.delete("/photos/oddtype")


@pytest.mark.skipif(sys.platform == "win32", reason="an unprivileged Windows user cannot symlink")
def test_a_picture_swapped_for_a_link_out_of_the_folder_is_refused_when_served(picture, tmp_path):
    """The front door refused this. The serving door has to refuse it too."""
    client.post("/photos", json={"picture": str(picture), "name": "swaptest"})
    try:
        picture.unlink()
        os.symlink("/etc/hostname", picture)
        assert client.get("/photos/swaptest/picture").status_code == 403
    finally:
        # Whatever happened above, the register must not keep this name: a
        # leaked site is what every later test of /sites trips over.
        picture.unlink(missing_ok=True)
        client.delete("/photos/swaptest")


def test_resetting_an_arrangement_built_from_a_picture_really_resets_it(shelved):
    """It used to hand back the same object it had just been asked to discard."""
    moved = client.post(
        "/sites/test_bench/layout",
        json={"positions": {"plate_1": {"x": 999, "y": 888, "z": 777}}},
    )
    assert moved.status_code == 200
    client.post("/sites/test_bench/reset")
    after = client.get("/sites/test_bench").json()["tree"]["children"]
    plate = next(c for c in after if c["name"] == "plate_1")
    assert plate["position"] != {"x": 999.0, "y": 888.0, "z": 777.0}


def test_a_piece_whose_name_could_never_be_found_again_is_refused(picture):
    """Names are joined with dots to address a node, so one cannot contain a dot."""
    from apothecary.hierarchy import Assembly
    from apothecary.primitives import Cube

    made = build(PlainFinder().look(picture), name="dotty", picture_path=picture)
    made.site.children.append(Assembly(name="has.a.dot", role="word", base=Cube(size=1.0)))
    with pytest.raises(ValueError, match="could never be found again"):
        Shelf().put(made)
