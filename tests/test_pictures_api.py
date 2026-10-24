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
    assert c.delete(f"/photos/pictures/{kept['name']}").json()["forgotten"] == kept["path"]
    assert c.delete(f"/photos/pictures/{kept['name']}").status_code == 404
    assert c.delete("/photos/pictures/../bench.png").status_code == 404
    assert (pictures / "bench.png").is_file()


def test_a_picture_a_person_adds_from_the_browser_keeps_its_name(pictures):
    """An upload is kept under uploads/ as the person named it (made safe), judged a
    picture by its bytes and not its name; a second of the same name is numbered."""
    c = TestClient(app)
    r = c.post(
        "/photos/pictures", params={"name": "my bench.jpeg", "kept": "upload"}, content=_drawn("r")
    )
    assert r.status_code == 201
    kept = r.json()
    # The bytes are a PNG, so the suffix is .png whatever the name said.
    assert kept["path"] == "uploads/my_bench.png" and kept["kept"] == "upload"
    assert not kept["captured"]
    again = c.post(
        "/photos/pictures", params={"name": "my bench.jpeg", "kept": "upload"}, content=_drawn("e")
    ).json()
    assert again["path"] == "uploads/my_bench-2.png"
    # A GIF is a picture too, by its first bytes.
    gif = io.BytesIO()
    Image.new("P", (8, 8)).save(gif, format="GIF")
    r = c.post(
        "/photos/pictures", params={"name": "wave", "kept": "upload"}, content=gif.getvalue()
    )
    assert r.status_code == 201 and r.json()["path"] == "uploads/wave.gif"
    # A name that is only punctuation still gets a name; a text file does not get in.
    r = c.post("/photos/pictures", params={"name": "...", "kept": "upload"}, content=_drawn("t"))
    assert r.status_code == 201 and r.json()["path"] == "uploads/picture.png"
    assert c.post("/photos/pictures", params={"kept": "upload"}, content=b"text").status_code == 415
    assert (
        c.post("/photos/pictures", params={"kept": "elsewhere"}, content=_drawn("r")).status_code
        == 422
    )
    # Listed with the folder's own, each saying how it got here.
    listed = {p["path"]: p["kept"] for p in c.get("/photos/pictures").json()}
    assert listed["bench.png"] is None and listed["uploads/my_bench.png"] == "upload"
    assert (pictures / "uploads").stat().st_mode & 0o777 == 0o700
    # Forgotten by its path; a bare name is a capture, and this is not one.
    assert c.delete("/photos/pictures/my_bench.png").status_code == 404
    assert c.delete("/photos/pictures/uploads/my_bench.png").json()["forgotten"] == (
        "uploads/my_bench.png"
    )
    assert not (pictures / "uploads" / "my_bench.png").exists()


def test_forgetting_every_kept_picture_leaves_the_folders_own(pictures):
    """Purge takes back what the browser put here -- captures and uploads -- and only
    that: the pictures a person named stay, and so does a link left in the folder."""
    c = TestClient(app)
    c.post("/photos/pictures", params={"name": "frame"}, content=_drawn("r"))
    c.post("/photos/pictures", params={"name": "frame"}, content=_drawn("e"))
    c.post("/photos/pictures", params={"name": "chosen", "kept": "upload"}, content=_drawn("t"))
    (pictures / "uploads" / "elsewhere.png").symlink_to(pictures / "bench.png")
    (pictures / "captures" / "note.txt").write_text("not a picture")
    before = c.get("/photos/pictures").json()
    assert sum(1 for p in before if p["kept"]) == 3
    # One kind at a time, or both.
    gone = c.delete("/photos/pictures", params={"kept": "upload"}).json()
    assert gone["forgotten"] == ["uploads/chosen.png"] and gone["left"] == 3
    gone = c.delete("/photos/pictures").json()
    assert len(gone["forgotten"]) == 2 and all(f.startswith("captures/") for f in gone["forgotten"])
    assert gone["left"] == 3
    after = c.get("/photos/pictures").json()
    assert sorted(p["name"] for p in after) == ["bench.png", "bench_again.png", "lamp.png"]
    assert (pictures / "bench.png").is_file()
    assert (pictures / "uploads" / "elsewhere.png").is_symlink()
    assert (pictures / "captures" / "note.txt").is_file()
    # A link is not forgotten one at a time either, and nothing above the folders is.
    assert c.delete("/photos/pictures/uploads/elsewhere.png").status_code == 404
    assert c.delete("/photos/pictures/uploads/../bench.png").status_code == 404
    assert c.delete("/photos/pictures/captures/.hidden").status_code == 404
    assert c.delete("/photos/pictures/state/x.png").status_code == 404
    assert (pictures / "bench.png").is_file()
    # Refused by name, not by whether the file exists: a path with a folder the
    # browser does not fill is 404 whatever is there.
    (pictures / "other").mkdir()
    (pictures / "other" / "x.png").write_bytes(_drawn("r"))
    assert c.delete("/photos/pictures/other/x.png").status_code == 404
    assert (pictures / "other" / "x.png").is_file()


def test_an_arrangement_is_never_named_after_a_route_under_photos(pictures):
    """``DELETE /photos/pictures`` forgets the kept pictures. An arrangement called
    ``pictures`` would be addressed by that route and never by itself, so the name
    is refused where an arrangement is built rather than shadowed here."""
    c = TestClient(app)
    (pictures / "pictures.png").write_bytes(_drawn("ret"))
    refused = c.post("/photos", json={"picture": "pictures.png", "width_mm": 400})
    assert refused.status_code == 400 and "route under /photos/" in refused.json()["detail"]
    assert c.post("/photos", json={"picture": "bench.png", "name": "gather"}).status_code == 400
    # Named something else, the same picture builds and is forgotten by its own name.
    built = c.post("/photos", json={"picture": "pictures.png", "name": "the_shelf"})
    assert built.status_code == 200
    assert c.delete("/photos/the_shelf").status_code == 200
    # And the gathering route refuses it too, before anything is built.
    pair = ["bench.png", "bench_again.png"]
    assert c.post("/photos/gather", json={"pictures": pair, "name": "pictures"}).status_code == 422


def test_a_picture_larger_than_the_limit_is_refused_before_it_is_read(pictures):
    """The limit is a limit on what the server reads, not on what it has read: a
    body that says it is too large is refused on its headers, and one that lies
    is refused as it streams, either way without a picture's worth of memory."""
    c = TestClient(app)
    from apothecary.routes import pictures as routes

    big = b"\x89PNG\r\n\x1a\n" + b"\0" * (routes.CAPTURE_MAX + 1)
    r = c.post("/photos/pictures", params={"name": "huge", "kept": "upload"}, content=big)
    assert r.status_code == 413

    # A body that understates its length is refused while it is read.
    def understated():
        yield b"\x89PNG\r\n\x1a\n"
        yield b"\0" * routes.CAPTURE_MAX

    r = c.post(
        "/photos/pictures",
        params={"name": "huge", "kept": "upload"},
        content=understated(),
        headers={"Content-Length": "8"},
    )
    assert r.status_code == 413
    assert not list((pictures / "uploads").glob("*")) if (pictures / "uploads").is_dir() else True


def test_a_kept_folder_that_is_a_link_elsewhere_is_neither_filled_nor_emptied(pictures):
    """uploads/ pointing at a folder of the person's own: nothing is written there,
    nothing listed from it, and a purge or a forget reaches nothing through it.
    A plain file standing where the folder would be is refused the same way."""
    c = TestClient(app)
    theirs = pictures.parent / "theirs"
    theirs.mkdir()
    (theirs / "holiday.png").write_bytes(_drawn("r"))
    (pictures / "uploads").symlink_to(theirs)
    r = c.post("/photos/pictures", params={"name": "x", "kept": "upload"}, content=_drawn("e"))
    assert r.status_code == 409
    assert sorted(p.name for p in theirs.iterdir()) == ["holiday.png"]
    assert "uploads/holiday.png" not in {p["path"] for p in c.get("/photos/pictures").json()}
    assert c.delete("/photos/pictures/uploads/holiday.png").status_code == 404
    assert c.delete("/photos/pictures").json()["forgotten"] == []
    assert (theirs / "holiday.png").is_file()
    # A file where the folder would be: said so, not a server error.
    (pictures / "captures").write_text("not a folder")
    r = c.post("/photos/pictures", params={"name": "x"}, content=_drawn("r"))
    assert r.status_code == 409 and "not a folder" in r.json()["detail"]


def test_only_a_picture_is_forgotten_from_a_kept_folder(pictures):
    """What the browser keeps in those folders is pictures; anything else a person
    left there is theirs, and the same rule holds one at a time as in a purge."""
    c = TestClient(app)
    kept = c.post("/photos/pictures", params={"name": "frame"}, content=_drawn("r")).json()
    (pictures / "captures" / "notes.txt").write_text("mine")
    (pictures / "captures" / "state.json").write_text("{}")
    assert c.delete("/photos/pictures/notes.txt").status_code == 404
    assert c.delete("/photos/pictures/captures/state.json").status_code == 404
    assert c.delete(f"/photos/pictures/{kept['name']}").status_code == 200
    assert c.delete("/photos/pictures").json()["forgotten"] == []
    assert (pictures / "captures" / "notes.txt").is_file()
    assert (pictures / "captures" / "state.json").is_file()


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
