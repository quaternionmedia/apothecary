"""A view's marks and notes over HTTP, and a person's words on them
(apothecary/routes/marks.py): the marks of a pinned whiteboard, a word on one read
back by the view's shapes, a note typed, and what is refused."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw, ImageFont

from apothecary.api import app

BLUE, BLACK = (20, 30, 120), (10, 10, 10)


@pytest.fixture
def pinned(tmp_path, monkeypatch):
    """A drawn whiteboard in the picture folder, pinned at the garage's whiteboard and
    read by the outline finder: a plate, a ring alone, a line and its size."""
    image = Image.new("RGB", (1600, 1200), (238, 238, 236))
    pen = ImageDraw.Draw(image)
    pen.rectangle((250, 250, 700, 520), outline=BLUE, width=9)
    pen.ellipse((1290, 1000, 1370, 1080), outline=BLACK, width=6)
    pen.line((250, 590, 700, 590), fill=BLACK, width=5)
    pen.text((400, 605), "120 mm", fill=BLACK, font=ImageFont.load_default(size=44))
    image.save(tmp_path / "drawing.png")
    monkeypatch.setenv("APOTHECARY_PICTURE_ROOT", str(tmp_path))
    client = TestClient(app)
    made = client.post(
        "/sites/garage/views",
        json={"host": "workbench", "picture": "drawing.png", "mm_across": 1600},
    )
    assert made.status_code == 201, made.text
    view = made.json()["id"]
    found = client.post(f"/sites/garage/views/{view}/find", json={"finder": "outline"})
    assert found.status_code == 200, found.text
    assert len(found.json()["shapes"]) == 1
    yield client, view
    client.delete(f"/sites/garage/views/{view}")


def _by_kind(body, kind):
    return [mark for mark in body["marks"] if mark["kind"] == kind]


def test_a_views_marks_and_notes_are_listed(pinned):
    client, view = pinned
    body = client.get(f"/sites/garage/views/{view}/marks").json()
    assert body["finder"] == "outline" and body["view"] == view
    assert len(_by_kind(body, "diagram")) == 2 and len(_by_kind(body, "writing")) == 1
    (ring,) = _by_kind(body, "unsure")
    assert ring["by"] == "sorter" and "a letter, or a hole" in ring["why"]
    (note,) = body["notes"]
    assert note["lies"] == "beside" and note["words"] is None


def test_a_word_on_a_mark_is_read_back_by_the_views_shapes(pinned):
    """The ring said to be a diagram's is a second shape of the view; said to be
    nothing after, it is gone again. The last word wins."""
    client, view = pinned
    (ring,) = _by_kind(client.get(f"/sites/garage/views/{view}/marks").json(), "unsure")
    said = client.put(f"/sites/garage/views/{view}/marks/{ring['id']}", json={"kind": "diagram"})
    assert said.status_code == 200, said.text
    now = next(m for m in said.json()["marks"] if m["id"] == ring["id"])
    assert (now["kind"], now["by"], now["guess"]) == ("diagram", "you", "unsure")
    assert len(said.json()["seen"]["shapes"]) == 2
    again = client.put(f"/sites/garage/views/{view}/marks/{ring['id']}", json={"kind": "nothing"})
    assert len(again.json()["seen"]["shapes"]) == 1


def test_a_note_is_typed_and_its_size_offered(pinned):
    client, view = pinned
    (note,) = client.get(f"/sites/garage/views/{view}/marks").json()["notes"]
    typed = client.put(f"/sites/garage/views/{view}/notes/{note['id']}", json={"text": "120 mm"})
    assert typed.status_code == 200, typed.text
    (now,) = typed.json()["notes"]
    assert now["words"] == "120 mm" and now["by"] == "you"
    assert now["offer"]["millimetres"] == 120.0 and now["offer"]["picture_mm"] == pytest.approx(
        427, rel=0.04
    )
    retyped = client.put(f"/sites/garage/views/{view}/notes/{note['id']}", json={"text": "125 mm"})
    assert retyped.json()["notes"][0]["words"] == "125 mm"


def test_what_is_not_there_and_what_is_not_writing_are_refused(pinned):
    client, view = pinned
    body = client.get(f"/sites/garage/views/{view}/marks").json()
    plate = _by_kind(body, "diagram")[0]
    assert (
        client.put(f"/sites/garage/views/{view}/marks/m99", json={"kind": "writing"}).status_code
        == 404
    )
    assert (
        client.put(
            f"/sites/garage/views/{view}/marks/{plate['id']}", json={"kind": "shape"}
        ).status_code
        == 422
    )
    refused = client.put(
        f"/sites/garage/views/{view}/notes/{plate['id']}", json={"text": "a plate"}
    )
    assert refused.status_code == 400 and "not writing" in refused.json()["detail"]
    assert client.get("/sites/garage/views/view_none/marks").status_code == 404
