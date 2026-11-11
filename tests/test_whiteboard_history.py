"""A whiteboard's history: its photographs, words and pieces on one timeline, the
whiteboard as it stood at a moment, what changed between two photographs taken or
left, and a moment placed elsewhere (apothecary/routes/whiteboards.py)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw, ImageFont

from apothecary.api import app

INK, BLACK = (20, 30, 120), (10, 10, 10)


def _drawing(
    path, *, plate=(250, 250, 700, 520), disc=(900, 250, 1200, 550), wedge=True, words=True
):
    """A whiteboard on a wall, square on: a plate, a disc, a wedge, and writing."""
    image = Image.new("RGB", (1800, 1400), (60, 60, 64))
    pen = ImageDraw.Draw(image)
    pen.rectangle((100, 100, 1700, 1300), fill=(238, 238, 236))
    shift = (100, 100)
    move = lambda box: tuple(v + shift[i % 2] for i, v in enumerate(box))  # noqa: E731
    pen.rectangle(move(plate), outline=INK, width=9)
    if disc:
        pen.ellipse(move(disc), outline=INK, width=9)
    if wedge:
        pen.polygon(((450, 1050), (750, 1050), (600, 800)), outline=INK, width=9)
    if words:
        pen.text((1000, 900), "lid, 3 off", fill=BLACK, font=ImageFont.load_default(size=44))
    image.save(path)


@pytest.fixture
def board(tmp_path, monkeypatch):
    _drawing(tmp_path / "monday.png")
    _drawing(
        tmp_path / "tuesday.png",
        plate=(250, 250, 800, 520),
        disc=(960, 250, 1260, 550),
        wedge=False,
    )
    monkeypatch.setenv("APOTHECARY_PICTURE_ROOT", str(tmp_path))
    client = TestClient(app)
    yield client
    for view in client.get("/sites/garage/attached").json()["views"]:
        client.delete(f"/sites/garage/views/{view['id']}")
    client.post("/sites/garage/reset")


def _photographed(client, picture):
    view = client.post(
        "/sites/garage/views", json={"host": "whiteboard", "picture": picture}
    ).json()
    client.post(
        f"/sites/garage/views/{view['id']}/find", json={"finder": "outline"}
    ).raise_for_status()
    return view["id"]


def _writing(client, view):
    marks = client.get(f"/sites/garage/views/{view}/marks").json()
    (note,) = marks["notes"]
    return note["id"]


def _monday(client):
    """Monday's photograph, its note typed and every shape made."""
    first = _photographed(client, "monday.png")
    client.put(
        f"/sites/garage/views/{first}/notes/{_writing(client, first)}", json={"text": "lid, 3 off"}
    )
    client.post(f"/sites/garage/views/{first}/make", json={"all": True}).raise_for_status()
    return first


def test_the_whiteboards_are_listed_and_a_structure_that_is_none_is_refused(board):
    assert board.get("/sites/garage/whiteboards").json() == [
        {"name": "whiteboard", "photographs": 0}
    ]
    assert board.get("/sites/garage/whiteboards/workbench/timeline").status_code == 404


def test_every_photograph_word_and_piece_is_an_event_in_order(board):
    first = _monday(board)
    second = _photographed(board, "tuesday.png")
    line = board.get("/sites/garage/whiteboards/whiteboard/timeline").json()
    kinds = [(e["kind"], e["view"]) for e in line["events"]]
    assert kinds[:2] == [("photograph", first), ("note", first)]
    assert kinds.count(("made", first)) == 3 and kinds[-1] == ("photograph", second)
    assert [p["id"] for p in line["photographs"]] == [first, second]
    assert line["layer"] == second and line["since"] == line["events"][0]["at"]
    moments = [e["at"] for e in line["events"]]
    assert moments == sorted(moments)


def test_a_moment_is_the_newest_photograph_by_then_with_the_words_given_by_then(board):
    first = _photographed(board, "monday.png")
    pinned = board.get("/sites/garage/whiteboards/whiteboard/timeline").json()["events"][0]["at"]
    board.put(
        f"/sites/garage/views/{first}/notes/{_writing(board, first)}", json={"text": "lid, 3 off"}
    )
    second = _photographed(board, "tuesday.png")
    line = board.get("/sites/garage/whiteboards/whiteboard/timeline", params={"at": pinned}).json()
    assert line["layer"] == first
    # As of the photograph's pinning, its note has no words; now it has.
    then = board.get(f"/sites/garage/views/{first}/marks", params={"as_of": pinned}).json()
    now = board.get(f"/sites/garage/views/{first}/marks").json()
    assert then["notes"][0]["words"] is None and now["notes"][0]["words"] == "lid, 3 off"
    assert board.get("/sites/garage/whiteboards/whiteboard/timeline").json()["layer"] == second
    bad = board.get("/sites/garage/whiteboards/whiteboard/timeline", params={"at": "tuesday"})
    assert bad.status_code == 422


def _rows(client, later, earlier):
    return client.get(f"/sites/garage/views/{later}/again", params={"since": earlier}).json()[
        "rows"
    ]


def test_what_changed_is_proposed_and_says_whether_taking_it_changes_a_piece(board):
    first = _monday(board)
    second = _photographed(board, "tuesday.png")
    rows = {r["change"]: r for r in _rows(board, second, first)}
    assert {"resized", "moved", "gone", "note same"} <= set(rows)
    assert all(rows[c]["takeable"] for c in ("resized", "moved", "gone", "note same"))
    assert rows["note same"]["words"] == "lid, 3 off"
    # Nothing has changed: the three pieces made from Monday stand as they were.
    made = board.get("/sites/garage/attached").json()["made"]
    assert sorted(r["view"] for r in made.values()) == [first] * 3


def test_only_the_rows_taken_change_anything(board):
    first = _monday(board)
    second = _photographed(board, "tuesday.png")
    rows = {r["change"]: r for r in _rows(board, second, first)}
    taken = board.post(
        f"/sites/garage/views/{second}/again",
        json={
            "since": first,
            "take": [rows["moved"]["number"], rows["gone"]["number"], rows["note same"]["number"]],
        },
    )
    assert taken.status_code == 200, taken.text
    body = taken.json()
    assert len(body["dropped"]) == 2 and len(body["made"]) == 1
    made = board.get("/sites/garage/attached").json()["made"]
    by_view = sorted(r["view"] for r in made.values())
    # The disc is Tuesday's now; the plate, its row left, is still Monday's; the wedge is gone.
    assert by_view == [first, second]
    assert next(r for r in made.values() if r["view"] == first)["word"] == "plate"
    # The same writing carries its words to Tuesday's photograph.
    assert (
        board.get(f"/sites/garage/views/{second}/marks").json()["notes"][0]["words"] == "lid, 3 off"
    )
    # The history keeps the pieces dropped: made from Monday, and dropped since.
    events = board.get("/sites/garage/whiteboards/whiteboard/timeline").json()["events"]
    assert sum(1 for e in events if e["kind"] == "made" and e["view"] == first) == 3
    assert sum(1 for e in events if e["kind"] == "dropped") == 2
    refused = board.post(f"/sites/garage/views/{second}/again", json={"since": first, "take": [99]})
    assert refused.status_code == 404


def test_a_row_with_no_piece_to_change_cannot_be_taken(board):
    first = _photographed(board, "monday.png")
    second = _photographed(board, "tuesday.png")
    rows = _rows(board, second, first)
    moved = next(r for r in rows if r["change"] == "moved")
    assert not moved["takeable"] and "nothing is made from it" in moved["says"]
    refused = board.post(
        f"/sites/garage/views/{second}/again", json={"since": first, "take": [moved["number"]]}
    )
    assert refused.status_code == 409


def test_a_moment_placed_elsewhere_keeps_its_size_finder_and_words_by_then(board):
    first = _photographed(board, "monday.png")
    pinned = board.get("/sites/garage/whiteboards/whiteboard/timeline").json()["events"][0]["at"]
    board.put(
        f"/sites/garage/views/{first}/notes/{_writing(board, first)}", json={"text": "lid, 3 off"}
    )
    now = board.post(f"/sites/garage/views/{first}/place", json={"host": "workbench"})
    assert now.status_code == 201, now.text
    placed = now.json()
    assert placed["host"] == "workbench" and placed["placed_from"] == first
    assert (
        placed["mm_across"] == 1200 and placed["finder"] == "outline" and len(placed["shapes"]) == 3
    )
    assert not placed["in_front"]
    words = board.get(f"/sites/garage/views/{placed['id']}/marks").json()["notes"][0]["words"]
    assert words == "lid, 3 off"
    then = board.post(
        f"/sites/garage/views/{first}/place", json={"host": "", "as_of": pinned}
    ).json()
    assert then["host"] == "" and then["as_of"] == pinned
    assert board.get(f"/sites/garage/views/{then['id']}/marks").json()["notes"][0]["words"] is None
    for host, means in (("whiteboard", 409), ("nowhere", 404)):
        assert (
            board.post(f"/sites/garage/views/{first}/place", json={"host": host}).status_code
            == means
        )
