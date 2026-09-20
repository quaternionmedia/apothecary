"""The photo workflow from the browser: pictures on this machine, captures, gathering, cameras."""

from __future__ import annotations

import io
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

from apothecary.api import _site_store, app


def _drawn(shapes: str, size=(640, 480)) -> bytes:
    """A picture with a few plain shapes; ``shapes`` says which, so two can differ."""
    img = Image.new("L", size, 245)
    pen = ImageDraw.Draw(img)
    if "r" in shapes:
        pen.rectangle((40, 40, 260, 160), fill=30)
    if "e" in shapes:
        pen.ellipse((360, 60, 520, 220), fill=20)
    if "t" in shapes:
        pen.polygon([(80, 420), (300, 420), (190, 280)], fill=25)
    out = io.BytesIO()
    img.save(out, format="PNG")
    return out.getvalue()


@pytest.fixture
def pictures(tmp_path, monkeypatch):
    monkeypatch.setenv("APOTHECARY_PICTURE_ROOT", str(tmp_path))
    monkeypatch.setenv("APOTHECARY_STATE_DIR", str(tmp_path / "state"))
    (tmp_path / "bench.png").write_bytes(_drawn("ret"))
    (tmp_path / "bench_again.png").write_bytes(_drawn("ret"))
    (tmp_path / "lamp.png").write_bytes(_drawn("et", (500, 500)))
    (tmp_path / "notes.txt").write_text("not a picture")
    from apothecary.vision import shelf as shelf_module
    from apothecary.vision.shelf import Shelf

    stock = Shelf()
    with patch.object(shelf_module, "_shelf", stock):
        yield tmp_path
    for name in list(stock.names()):
        if name in _site_store.names():
            _site_store.remove(name)


def test_the_pictures_in_the_folder_are_listed_and_a_capture_is_kept(pictures):
    c = TestClient(app)
    listed = c.get("/photos/pictures").json()
    assert sorted(p["name"] for p in listed) == ["bench.png", "bench_again.png", "lamp.png"]
    assert all(not p["captured"] for p in listed)
    # A capture: a PNG by its bytes, kept under captures/, listed as captured, newest first.
    r = c.post("/photos/pictures", params={"name": "webcam frame.png"}, content=_drawn("r"))
    assert r.status_code == 201
    kept = r.json()
    assert (
        kept["captured"]
        and kept["path"].startswith("captures/")
        and kept["name"].endswith("-webcam_frame.png")
    )
    assert (pictures / kept["path"]).is_file()
    assert c.get("/photos/pictures").json()[0]["name"] == kept["name"]
    # Not a picture by its bytes, whatever its name says; and nothing empty.
    assert c.post("/photos/pictures", params={"name": "x.png"}, content=b"hello").status_code == 415
    assert c.post("/photos/pictures", params={"name": "x.png"}, content=b"").status_code == 422
    # A JPEG is a JPEG.
    jpg = io.BytesIO()
    Image.new("RGB", (32, 32), (200, 100, 50)).save(jpg, format="JPEG")
    r = c.post("/photos/pictures", params={"name": "shot"}, content=jpg.getvalue())
    assert r.status_code == 201 and r.json()["name"].endswith("-shot.jpg")
    # The kept capture can be looked at like any picture, and forgotten.
    r = c.post(
        "/photos", json={"picture": kept["path"], "name": "from_the_camera", "width_mm": 400}
    )
    assert r.status_code == 200 and r.json()["name"] == "from_the_camera"
    assert c.delete(f"/photos/pictures/{kept['name']}").json()["forgotten"] == kept["name"]
    assert c.delete(f"/photos/pictures/{kept['name']}").status_code == 404
    assert c.delete("/photos/pictures/../bench.png").status_code == 404
    assert (pictures / "bench.png").is_file()


def test_gathering_from_the_browser_reports_asks_and_takes_the_answers(pictures):
    c = TestClient(app)
    r = c.post("/photos/gather", json={"pictures": ["bench.png", "bench_again.png", "lamp.png"]})
    assert r.status_code == 200, r.text
    got = r.json()
    assert "bench" in got["report"] and got["map_html"].startswith("<")
    assert len(got["readings"]) == 3 and all(r["readable"] for r in got["readings"])
    names = {n for cl in got["clusters"] for n in cl["pictures"]}
    assert names == {"bench", "bench_again", "lamp"}
    # Two identical drawings are of one thing; the lamp stands alone or is asked about.
    together = next(
        (cl for cl in got["clusters"] if {"bench", "bench_again"} <= set(cl["pictures"])), None
    )
    assert together is not None and together["kind"] != "alone"
    for q in got["questions"]:
        assert q["sentence"].startswith("Are ") and len(q["answers"]) == 3
    # A person's word, in the answers' own sentences, wins and is carried.
    r = c.post(
        "/photos/gather",
        json={
            "pictures": ["bench.png", "bench_again.png", "lamp.png"],
            "answers": "bench and lamp are not related\n",
        },
    )
    assert r.status_code == 200
    assert not any({"bench", "lamp"} <= set(cl["pictures"]) for cl in r.json()["clusters"])
    # A name that is not here is refused, not ignored.
    r = c.post(
        "/photos/gather",
        json={
            "pictures": ["bench.png", "lamp.png"],
            "answers": "bench and sofa are the same thing\n",
        },
    )
    assert r.status_code == 422 and "sofa" in r.json()["detail"]
    # Fewer than two pictures is not a gathering.
    assert c.post("/photos/gather", json={"pictures": ["bench.png"]}).status_code == 422
    # Built as one arrangement, it is a site the world can open.
    r = c.post(
        "/photos/gather",
        json={
            "pictures": ["bench.png", "bench_again.png", "lamp.png"],
            "build": True,
            "name": "from_pictures",
        },
    )
    assert r.status_code == 200 and r.json()["site"] == "from_pictures"
    assert "from_pictures" in _site_store.names()
    assert c.get("/sites/from_pictures").status_code == 200


def test_cameras_are_placed_in_the_world_and_kept(pictures):
    c = TestClient(app)
    assert c.get("/cameras").json() == []
    r = c.put(
        "/cameras/abc123", json={"label": "Bench webcam", "site": "garage", "path": "workbench"}
    )
    assert r.status_code == 200 and r.json()["path"] == "workbench"
    assert (
        c.put(
            "/cameras/abc123", json={"label": "x", "site": "garage", "path": "nowhere"}
        ).status_code
        == 404
    )
    assert (
        c.put(
            "/cameras/bad id!", json={"label": "x", "site": "garage", "path": "workbench"}
        ).status_code
        == 422
    )
    listed = c.get("/cameras", params={"site": "garage"}).json()
    assert [cam["id"] for cam in listed] == ["abc123"] and listed[0]["label"] == "Bench webcam"
    assert c.get("/cameras", params={"site": "parts_library"}).json() == []
    assert (pictures / "state" / "cameras.json").is_file()
    assert c.delete("/cameras/abc123").json()["unplaced"] == "abc123"
    assert c.delete("/cameras/abc123").status_code == 404
