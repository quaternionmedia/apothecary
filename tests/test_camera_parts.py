"""A camera is a part standing in a site, aimed where it looks.

The fixture is tests/test_views_api.py's world: the garage, its bench's top at
z 780, printer_1 standing at the bench's left end with its top at z 1350, the
bench's middle clear, and a stated picture 1000 by 500 pixels. A camera added
above the bench stands 600 mm above its middle; one added at the floor stands
600 mm above the floor just past the garage's roots.
"""

from __future__ import annotations

import json
import math
import re

import pytest
from fastapi.testclient import TestClient
from test_views_api import _pin, _roots, forget_cameras, world  # noqa: F401 - the fixture

from apothecary.api import _site_store, app
from apothecary.vision import cameras
from apothecary.vision import views as viewing

pytestmark = pytest.mark.usefixtures("world")

START_WIDTH = 2 * 600 * math.tan(math.radians(30))


def _add(c, host="workbench", site="garage"):
    r = c.post(f"/sites/{site}/cameras", json={"host": host})
    assert r.status_code == 201, r.text
    return r.json()["camera"]


def _pose(c, name, **body):
    r = c.put(f"/sites/garage/cameras/{name}/pose", json=body)
    assert r.status_code == 200, r.text
    return r.json()["camera"]


def _attached(c):
    return c.get("/sites/garage/attached").json()


# --- the part ----------------------------------------------------------------------------


def test_the_webcam_part_and_the_camera_node_are_the_same_shape():
    """The node's Python geometry and the part's SCAD say the same body and lens,
    and the part's declared bounds are the node's box looking straight down."""
    from apothecary.projects.parts.skeleton import ROOT

    folder = ROOT / "parts" / "cameras" / "webcam"
    scad = (folder / "webcam.scad").read_text(encoding="utf-8")
    body = [float(v) for v in re.search(r"^body = \[([^\]]+)\]", scad, re.M).group(1).split(",")]
    assert tuple(body) == cameras.BODY
    assert float(re.search(r"^lens_d = ([\d.]+)", scad, re.M).group(1)) == cameras.LENS_D
    assert float(re.search(r"^lens_h = ([\d.]+)", scad, re.M).group(1)) == cameras.LENS_H
    bounds = json.loads((folder / "part.json").read_text())["bounds"]
    box = cameras.footprint(cameras.Pose(position=cameras.Vector3D()))
    assert [box.min_point.x, box.min_point.y, box.min_point.z] == pytest.approx(bounds["min"])
    assert [box.max_point.x, box.max_point.y, box.max_point.z] == pytest.approx(bounds["max"])


def test_the_three_mounts_are_stubs_that_draw_the_webcam():
    from apothecary.projects.parts.skeleton import ROOT

    for stub in ("webcam_desk_stand", "webcam_clamp_arm", "webcam_ceiling_mount"):
        folder = ROOT / "parts" / "cameras" / stub
        described = json.loads((folder / "part.json").read_text())
        assert "stub" in described["tags"] and "stub" in described["description"]
        assert "include <../webcam/webcam.scad>" in (folder / f"{stub}.scad").read_text()
    webcam = json.loads((ROOT / "parts" / "cameras" / "webcam" / "part.json").read_text())
    assert "stub" not in webcam["tags"]


# --- Add here ------------------------------------------------------------------------------


def test_add_here_stands_a_camera_above_the_place_looking_straight_down():
    c = TestClient(app)
    added = c.post("/sites/garage/cameras", json={"host": "workbench"})
    assert added.status_code == 201, added.text
    camera = added.json()["camera"]
    assert camera["name"] == "camera_1"
    assert camera["position"] == [900.0, 300.0, 1380.0]  # 600 above the bench's middle
    assert (camera["turn"], camera["tilt"], camera["fov"]) == (0.0, 0.0, 60.0)
    assert camera["fov_taught"] is False and camera["device"] is None
    assert camera["added"] == {"position": [900.0, 300.0, 1380.0], "turn": 0.0, "tilt": 0.0}
    # Its picture lands on the bench's own top, where it was added.
    assert camera["lands"] == {"host": "workbench", "point": [900.0, 300.0, 780.0]}
    # A root structure of the site, drawn as the webcam, standing in the air.
    root = _roots(c)["camera_1"]
    tree = next(
        n for n in c.get("/sites/garage").json()["tree"]["children"] if n["name"] == "camera_1"
    )
    assert tree["part_ref"] == "webcam" and tree["category"] == "camera"
    assert root["world_bounds"]["min"] == pytest.approx([855.0, 285.0, 1380.0])
    assert root["world_bounds"]["max"] == pytest.approx([945.0, 315.0, 1414.0])
    assert added.json()["site"]["is_valid"], added.json()["site"]["violations"]
    # At the floor: just past the roots, 600 up; its picture lands on the floor.
    floor = _add(c, host="")
    anchor = viewing.floor_anchor(_site_store.get("garage"), viewing.added_roots("garage"))
    assert floor["name"] == "camera_2"
    assert floor["position"] == pytest.approx([anchor.x + START_WIDTH / 2, anchor.y, 600.0])
    assert floor["lands"]["host"] == ""
    # The site's SCAD draws it, aimed.
    assert "rotate([0.0, 0.0, 0.0])" in c.get("/sites/garage").json()["scad"]


def test_a_camera_is_named_afresh_while_a_view_remembers_a_removed_one():
    c = TestClient(app)
    _add(c)
    _pin(c, host=None, camera="camera_1")
    assert c.delete("/sites/garage/cameras/camera_1").status_code == 200
    assert _add(c)["name"] == "camera_2"  # camera_1's picture still names camera_1


# --- pose, device, remove --------------------------------------------------------------------


def test_a_camera_is_moved_turned_and_tilted_and_its_pictures_stay_where_they_landed():
    c = TestClient(app)
    _add(c)
    first = _pin(c, host=None, camera="camera_1")
    moved = _pose(c, "camera_1", position=[900.0, 50.0, 1380.0], turn=-90, tilt=20)
    assert moved["position"] == [900.0, 50.0, 1380.0]
    assert (moved["turn"], moved["tilt"]) == (270.0, 20.0)  # a turn is one of 0..360
    # Tilted 20 toward the picture's top, turned 270: it looks toward +x, onto the bench.
    lands = moved["lands"]
    assert lands["host"] == "workbench"
    assert lands["point"] == pytest.approx(
        [900.0 + 600.0 * math.tan(math.radians(20)), 50.0, 780.0]
    )
    # Its node is aimed too, and its box grew.
    box = _roots(c)["camera_1"]["world_bounds"]
    assert box["max"][2] - box["min"][2] > 34.0
    # The picture it took before still lies on the bench's middle, as it was.
    still = next(v for v in _attached(c)["views"] if v["id"] == first["id"])
    assert still["mat"]["centre"] == pytest.approx([900.0, 300.0, 780.0])
    assert still["host"] == "workbench" and still["mat"]["centre"] == pytest.approx(
        first["mat"]["centre"]
    )
    # Only what is given changes; nonsense is refused.
    assert _pose(c, "camera_1", tilt=0)["position"] == [900.0, 50.0, 1380.0]
    for bad in ({}, {"tilt": 190}, {"tilt": -5}, {"position": [1, 2]}, {"turn": "x"}):
        assert c.put("/sites/garage/cameras/camera_1/pose", json=bad).status_code == 422, bad
    assert c.put("/sites/garage/cameras/camera_9/pose", json={"tilt": 5}).status_code == 404


def test_a_cameras_device_is_set_and_cleared_and_never_enters_the_site():
    c = TestClient(app)
    _add(c)
    told = c.put(
        "/sites/garage/cameras/camera_1/device", json={"id": "ab12cd", "label": "My Cam (Built-in)"}
    )
    assert told.status_code == 200 and told.json()["device"] == {
        "id": "ab12cd",
        "label": "My Cam (Built-in)",
    }
    assert _attached(c)["cameras"][0]["device"]["id"] == "ab12cd"
    assert "My Cam" not in json.dumps(c.get("/sites/garage").json())
    cleared = c.delete("/sites/garage/cameras/camera_1/device")
    assert cleared.status_code == 200 and cleared.json()["device"] is None
    assert c.put("/sites/garage/cameras/camera_9/device", json={"id": "x"}).status_code == 404


def test_one_device_is_one_camera_in_any_site():
    """Choosing a device for a camera takes it off any other camera it was, in any
    site (the owner's decision of 2026-10-04); another device stays where it is."""
    c = TestClient(app)
    _add(c)
    _add(c)
    _add(c, site="datum_core", host="tray")
    c.put("/sites/garage/cameras/camera_1/device", json={"id": "desk", "label": "desk cam"})
    c.put("/sites/garage/cameras/camera_2/device", json={"id": "door", "label": "door cam"})
    moved = c.put("/sites/datum_core/cameras/camera_1/device", json={"id": "desk", "label": "d"})
    assert moved.status_code == 200, moved.text
    assert moved.json()["device"]["id"] == "desk"
    assert moved.json()["taken_from"] == [{"site": "garage", "name": "camera_1"}]
    devices = {
        (row["site"], row["name"]): row["device"] for row in c.get("/placed").json()["cameras"]
    }
    assert devices[("garage", "camera_1")] is None
    assert devices[("garage", "camera_2")]["id"] == "door"
    assert devices[("datum_core", "camera_1")]["id"] == "desk"
    # Choosing it again for the camera that has it takes it from nothing.
    again = c.put("/sites/datum_core/cameras/camera_1/device", json={"id": "desk", "label": "d"})
    assert again.json()["taken_from"] == []


# --- Part › Edit: a camera's numbers are its parameters ----------------------------------------


def test_a_cameras_numbers_are_parameters_as_a_parts_are():
    """Part › Edit on a camera's ring opens the one editor, on the camera's numbers:
    its lens's position, its turn, tilt and field of view, in the shape a part's
    parameters are answered in; a staged set is checked as a part's is."""
    from apothecary.projects.parts.params import ParamsSpec, Validation

    c = TestClient(app)
    _add(c)
    spec = c.get("/sites/garage/cameras/camera_1/params")
    assert spec.status_code == 200, spec.text
    reference = c.get("/parts/datum_core/params").json()
    assert list(spec.json()) == list(reference)
    assert list(spec.json()["fields"][0]) == list(reference["fields"][0])
    fields = {f["name"]: f for f in ParamsSpec(**spec.json()).model_dump()["fields"]}
    assert list(fields) == ["x", "y", "z", "turn", "tilt", "fov"]
    assert [fields[n]["default"] for n in fields] == [900.0, 300.0, 1380.0, 0.0, 0.0, 60.0]
    assert all(fields[n]["type"] == "number" for n in fields)
    # A position's slider spans the garage and past it; the aim's are its own bounds.
    assert fields["x"]["min"] < -400 and fields["x"]["max"] > 5400
    assert (fields["tilt"]["min"], fields["tilt"]["max"]) == (0.0, 180.0)
    assert (fields["turn"]["min"], fields["turn"]["max"]) == (0.0, 360.0)
    assert 0 < fields["fov"]["min"] < 1 and 179 < fields["fov"]["max"] < 180
    assert all(not fields[n]["contested"] for n in fields)  # nothing moved yet
    checked = c.post("/sites/garage/cameras/camera_1/validate", json={"params": {"tilt": 30}})
    assert checked.status_code == 200 and Validation(**checked.json()).valid
    # Tilted, its body swings forward over its lens.
    assert checked.json()["bounds"]["min_point"]["y"] < -15.0
    for bad in ({"tilt": 190}, {"fov": 0}, {"fov": 180}, {"turn": -1}, {"nozzle": 1}):
        refused = c.post("/sites/garage/cameras/camera_1/validate", json={"params": bad})
        assert refused.json()["valid"] is False, bad
    # A position outside the slider's span is a position all the same.
    assert c.post(
        "/sites/garage/cameras/camera_1/validate", json={"params": {"x": 50000.0}}
    ).json()["valid"]
    assert c.get("/sites/garage/cameras/camera_9/params").status_code == 404


def test_applying_a_cameras_numbers_moves_it_and_a_field_of_view_is_its_lens():
    """The editor's Apply: the camera moved, turned and tilted as it says; a field of
    view given is the camera's lens from then on, a person's, and its pictures no
    person sized follow, their pieces re-sized. Where each number started is a
    candidate to turn back to."""
    c = TestClient(app)
    _add(c)
    view = _pin(c, host=None, camera="camera_1")
    piece = c.post(f"/sites/garage/views/{view['id']}/make", json={"shape": 1}).json()["made"][0]
    before = _roots(c)[piece]["footprint"]
    r = c.put(
        "/sites/garage/cameras/camera_1",
        json={"params": {"z": 1500.0, "tilt": 10.0, "fov": 90.0, "x": 900.0}},
    )
    assert r.status_code == 200, r.text
    camera = r.json()["camera"]
    assert camera["position"] == [900.0, 300.0, 1500.0] and camera["tilt"] == 10.0
    assert camera["fov"] == 90.0 and camera["fov_taught"] is True
    assert r.json()["rebuilt"] == [piece]
    followed = next(v for v in _attached(c)["views"] if v["id"] == view["id"])
    assert followed["taken"]["fov"] == 90.0 and followed["scale"] is None
    # Its picture stays where it landed: only its lens changed, as the camera's did.
    assert followed["mm_across"] == pytest.approx(2 * 600 * math.tan(math.radians(45)))
    after = _roots(c)[piece]["footprint"]
    grown = (after["max"][0] - after["min"][0]) / (before["max"][0] - before["min"][0])
    assert grown == pytest.approx(math.tan(math.radians(45)) / math.tan(math.radians(30)))
    # The node stands where the numbers say.
    assert _roots(c)["camera_1"]["position"] == {"x": 900.0, "y": 300.0, "z": 1500.0}
    # Each number that moved offers where it started.
    fields = {f["name"]: f for f in c.get("/sites/garage/cameras/camera_1/params").json()["fields"]}
    assert [v["value"] for v in fields["z"]["contested"]] == [1380.0]
    assert [v["value"] for v in fields["tilt"]["contested"]] == [0.0]
    assert [v["value"] for v in fields["fov"]["contested"]] == [60.0]
    assert fields["x"]["contested"] == []
    # Nonsense is refused, and nothing changes.
    for bad in ({"params": {}}, {"params": {"tilt": 200}}, {"params": {"wheels": 4}}, {}):
        assert c.put("/sites/garage/cameras/camera_1", json=bad).status_code == 422, bad
    assert _attached(c)["cameras"][0]["tilt"] == 10.0


def test_remove_takes_the_camera_away_and_leaves_its_pictures():
    c = TestClient(app)
    _add(c)
    view = _pin(c, host=None, camera="camera_1")
    r = c.delete("/sites/garage/cameras/camera_1")
    assert r.status_code == 200 and r.json()["removed"] == "camera_1"
    assert "camera_1" not in _roots(c) and _attached(c)["cameras"] == []
    assert [v["id"] for v in _attached(c)["views"]] == [view["id"]]
    assert c.delete("/sites/garage/cameras/camera_1").status_code == 404


def test_a_camera_whose_site_is_gone_is_listed_and_removed_all_the_same():
    c = TestClient(app)
    pose = cameras.Pose(position=cameras.Vector3D(z=600.0))
    gone = cameras.Camera(
        site="forgotten_photo", name="camera_1", pose=pose, added=pose, added_at="2026-10-04"
    )
    cameras._save([*cameras.records(), gone])
    rows = c.get("/placed").json()["cameras"]
    assert {(r["site"], r["site_known"], r["node_found"]) for r in rows} == {
        ("forgotten_photo", False, False)
    }
    r = c.delete("/sites/forgotten_photo/cameras/camera_1")
    assert r.status_code == 200 and r.json() == {"removed": "camera_1", "site": None}
    assert cameras.records() == []


# --- kept across a restart, and Reset ----------------------------------------------------------


def _restart():
    """The server started again: every site built afresh from its factory."""
    for name in list(_site_store.loaded()):
        _site_store._sites.pop(name, None)


def test_a_camera_stands_where_it_stood_after_a_restart(world):  # noqa: F811 - the fixture
    c = TestClient(app)
    _add(c)
    c.put("/sites/garage/cameras/camera_1/device", json={"id": "ab12cd", "label": "desk"})
    # Moved with the handles, as the layout route moves any part.
    r = c.post(
        "/sites/garage/layout", json={"positions": {"camera_1": {"x": 100, "y": 50, "z": 1500}}}
    )
    assert r.status_code == 200, r.text
    _pose(c, "camera_1", tilt=15)
    _restart()
    root = _roots(c)["camera_1"]
    assert root["position"] == {"x": 100.0, "y": 50.0, "z": 1500.0}
    camera = _attached(c)["cameras"][0]
    assert camera["tilt"] == 15.0 and camera["device"]["label"] == "desk" and camera["in_site"]
    records = json.loads((world.parent / "state" / cameras.RECORDS).read_text())
    assert [r["name"] for r in records["cameras"]] == ["camera_1"]


def test_reset_stands_a_camera_back_where_it_was_added_and_keeps_its_device_lens_and_views():
    c = TestClient(app)
    _add(c)
    c.put("/sites/garage/cameras/camera_1/device", json={"id": "ab12cd", "label": "desk"})
    view = _pin(c, host=None, camera="camera_1")
    c.put(f"/sites/garage/views/{view['id']}/scale", json={"mm_across": 900})
    made = c.post(f"/sites/garage/views/{view['id']}/make", json={"all": True}).json()["made"]
    assert made
    _pose(c, "camera_1", position=[100.0, 50.0, 1500.0], turn=45, tilt=30)
    r = c.post("/sites/garage/reset")
    assert r.status_code == 200, r.text
    camera = _attached(c)["cameras"][0]
    assert camera["position"] == [900.0, 300.0, 1380.0] and (camera["turn"], camera["tilt"]) == (
        0,
        0,
    )
    assert camera["device"]["label"] == "desk" and camera["fov_taught"] is True
    assert camera["in_site"] and "camera_1" in _roots(c)
    assert [v["id"] for v in _attached(c)["views"]] == [view["id"]]
    assert not set(made) & set(_roots(c)) and _attached(c)["made"] == {}


# --- where a picture lands -------------------------------------------------------------------


def test_a_picture_lands_on_a_top_on_the_floor_or_nowhere_and_nowhere_makes_nothing():
    c = TestClient(app)
    _add(c)
    # Added at the bench, over its clear middle: the bench's top.
    assert _pin(c, host=None, camera="camera_1")["host"] == "workbench"
    # Over printer_1, standing on the bench: the printer's top, the first it meets.
    _pose(c, "camera_1", position=[333.0, 336.0, 1950.0])
    on_top = _pin(c, host=None, camera="camera_1")
    assert on_top["host"] == "printer_1"
    assert on_top["mat"]["centre"] == pytest.approx([333.0, 336.0, 1350.0])
    # Past the garage: the floor, the picture's anchor where its centre ray lands.
    _pose(c, "camera_1", position=[7000.0, 300.0, 600.0])
    floor = _pin(c, host=None, camera="camera_1")
    assert floor["host"] == "" and floor["anchor"] == [7000.0, 300.0, 0.0]
    assert floor["mat"]["centre"] == pytest.approx([7000.0, 300.0, 0.0])
    # Level, at printer_1's side: a wall. Kept, lying nowhere, and nothing is made from it.
    _pose(c, "camera_1", position=[0.0, 336.0, 1000.0], turn=-90, tilt=90)
    assert _attached(c)["cameras"][0]["lands"] is None
    wall = _pin(c, host=None, camera="camera_1")
    assert wall["host"] is None and wall["mat"] is None and wall["mm_across"] is None
    r = c.post(f"/sites/garage/views/{wall['id']}/make", json={"all": True})
    assert r.status_code == 409 and "Aim the camera down" in r.json()["detail"]
    r = c.put(f"/sites/garage/views/{wall['id']}/scale", json={"mm_across": 500})
    assert r.status_code == 409 and "Aim the camera down" in r.json()["detail"]
    row = next(v for v in c.get("/placed").json()["views"] if v["id"] == wall["id"])
    assert row["placed"] is False and row["host_found"] is False
    # Up at the sky: nowhere.
    _pose(c, "camera_1", tilt=180)
    assert _pin(c, host=None, camera="camera_1")["host"] is None


def test_a_tilted_cameras_pieces_stand_where_their_shapes_land():
    """A camera 600 mm over the bench's middle, tilted 20 degrees toward the back:
    each piece stands where its shape's middle lands through the pinhole. In front
    of printer_1, the same tilt meets the printer's front first: a wall."""
    c = TestClient(app)
    _add(c)
    _pose(c, "camera_1", position=[333.0, 50.0, 1380.0], tilt=20)
    assert _pin(c, host=None, camera="camera_1")["host"] is None
    _pose(c, "camera_1", position=[900.0, 300.0, 1380.0], tilt=20)
    view = _pin(c, host=None, camera="camera_1")
    assert view["host"] == "workbench" and view["mat"]["homography"] is not None
    made = c.post(f"/sites/garage/views/{view['id']}/make", json={"shape": 1}).json()
    piece = made["made"][0]
    # The coin's middle, by hand: the picture point's ray from the lens to the bench's top.
    shape = view["shapes"][1]
    u, v = (shape["min"][0] + shape["max"][0]) / 2, (shape["min"][1] + shape["max"][1]) / 2
    half = math.tan(math.radians(30))
    t = math.radians(20)
    right, down, forward = (
        (1, 0, 0),
        (0, -math.cos(t), -math.sin(t)),
        (0, math.sin(t), -math.cos(t)),
    )
    ray = [
        f + (2 * u - 1) * half * r + (2 * v - 1) * half * 0.5 * d
        for f, r, d in zip(forward, right, down, strict=True)
    ]
    s = 600.0 / -ray[2]
    expected = (900.0 + s * ray[0], 300.0 + s * ray[1], 780.0)
    root = _roots(c)[piece]
    assert (root["position"]["x"], root["position"]["y"], root["position"]["z"]) == pytest.approx(
        expected
    )
    record = _attached(c)["made"][piece]
    assert record["camera"] == "camera_1" and len(record["homography"]) == 3
    assert record["mm_across"] == pytest.approx(view["mm_across"])


# --- the learned lens ---------------------------------------------------------------------------


def test_the_first_width_teaches_the_lens_and_the_pictures_no_person_sized_follow():
    """Until taught, a camera's pictures are sized at its starting field of view. The
    first width a person types teaches it: its pictures no person sized follow, and
    the pieces made from them re-size. A width typed after sizes its own view alone."""
    c = TestClient(app)
    _add(c)
    first = _pin(c, host=None, camera="camera_1")
    second = _pin(c, host=None, camera="camera_1")
    assert second["mm_across"] == pytest.approx(START_WIDTH)
    piece = c.post(f"/sites/garage/views/{second['id']}/make", json={"shape": 1}).json()["made"][0]
    before = _roots(c)[piece]["footprint"]
    r = c.put(f"/sites/garage/views/{first['id']}/scale", json={"mm_across": 1800})
    assert r.status_code == 200, r.text
    assert r.json()["taught"] == "camera_1" and r.json()["rebuilt"] == [piece]
    learned = math.degrees(2 * math.atan(900 / 600))
    assert cameras.record("garage", "camera_1").fov == pytest.approx(learned)
    views = {v["id"]: v for v in _attached(c)["views"]}
    assert views[second["id"]]["mm_across"] == pytest.approx(1800)  # followed the lens
    assert views[second["id"]]["taken"]["fov"] == pytest.approx(learned)
    assert views[second["id"]]["scale"] is None
    # The piece made from the follower re-sized with it, as a re-size re-sizes it.
    after = _roots(c)[piece]["footprint"]
    grown = (after["max"][0] - after["min"][0]) / (before["max"][0] - before["min"][0])
    assert grown == pytest.approx(1800 / START_WIDTH)
    # A camera's next picture is sized by what it learned; a person's width after
    # that sizes its own view, keeps it, and teaches nothing.
    third = _pin(c, host=None, camera="camera_1")
    assert third["mm_across"] == pytest.approx(1800)
    r = c.put(f"/sites/garage/views/{third['id']}/scale", json={"mm_across": 500})
    assert r.json()["taught"] is None and r.json()["mm_across"] == pytest.approx(500)
    assert cameras.record("garage", "camera_1").fov == pytest.approx(learned)
    views = {v["id"]: v for v in _attached(c)["views"]}
    assert views[second["id"]]["mm_across"] == pytest.approx(1800)
    assert views[third["id"]]["mm_across"] == pytest.approx(500)
    assert views[third["id"]]["scale"] == {"mm_across": 500}


# --- the ring, through the routes ---------------------------------------------------------------


def _intent(action, targets, pointing="node"):
    return {
        "intent": {
            "action": action,
            "option_id": action,
            "context": {"pointing": pointing, "targets": targets},
        },
        "site": "garage",
    }


def test_add_here_and_remove_are_carried_by_the_server_and_the_ring_knows_a_camera():
    c = TestClient(app)
    r = c.post("/menu/intent", json=_intent("camera:add-here", ["workbench"]))
    assert r.status_code == 200, r.text
    assert "camera_1" in r.json()["did"] and r.json()["carried_by"] == "the server carries it out"
    assert "camera_1" in {s["name"] for s in r.json()["site"]["structures"]}
    r = c.post("/menu/intent", json=_intent("camera:add-here:@floor", [], "canvas"))
    assert r.status_code == 200 and "camera_2" in r.json()["did"]
    assert c.post("/menu/intent", json=_intent("camera:add-here", ["nowhere"])).status_code == 404
    # The camera's own ring: its device is the server's to say, from its record.
    c.put("/sites/garage/cameras/camera_1/device", json={"id": "mine", "label": "desk"})
    told = {
        "context": {"pointing": "node", "targets": ["camera_1"]},
        "site": "garage",
        "picture": {
            "cameras": [{"id": "mine", "label": "desk"}],
            "asked": True,
            "here": {"camera": {"id": "someone_elses", "label": "x"}},
        },
    }
    ring = c.post("/menu/resolve", json=told).json()
    labels = [o["label"] for o in ring["options"]]
    assert labels == [
        "Zoom in",
        "Move",
        "Why this",
        "Device",
        "Live",
        "Take picture",
        "Remove",
        "Part",
    ]
    part = next(o for o in ring["options"] if o["label"] == "Part")
    assert [(o["label"], o["action"]) for o in part["children"]] == [("Edit", "part:edit")]
    device = next(o for o in ring["options"] if o["label"] == "Device")
    assert [(o["action"], o["marked"]) for o in device["children"]] == [
        ("camera:device:mine", True)
    ]
    # A host no longer offers Pin here; it offers Add here.
    bench = c.post(
        "/menu/resolve",
        json={"context": {"pointing": "node", "targets": ["workbench"]}, "site": "garage"},
    ).json()
    camera_cell = next(o for o in bench["options"] if o["label"] == "Camera")
    assert [o["action"] for o in camera_cell["children"]] == ["camera:add-here"]
    # Remove, carried by the server.
    r = c.post("/menu/intent", json=_intent("camera:remove", ["camera_1"]))
    assert r.status_code == 200 and "camera_1" not in {
        s["name"] for s in r.json()["site"]["structures"]
    }
    assert c.post("/menu/intent", json=_intent("camera:remove", ["camera_1"])).status_code == 404
    # The page's verbs are the page's.
    for action in (
        "camera:live",
        "camera:take-picture",
        "camera:device:mine",
        "camera:allow",
        "part:edit",
    ):
        r = c.post("/menu/intent", json=_intent(action, ["camera_2"]))
        assert r.status_code == 200 and r.json()["carried_by"] == "the viewer carries it out"


def test_a_camera_in_the_air_overlaps_nothing_and_one_moved_into_a_printer_does_in_any_site():
    c = TestClient(app)
    _add(c)
    _add(c, site="datum_core", host="tray")
    assert c.get("/sites/datum_core").json()["is_valid"]
    r = c.post(
        "/sites/datum_core/layout", json={"positions": {"camera_1": {"x": 0, "y": 0, "z": 5}}}
    )
    pairs = [sorted(v["structures"]) for v in r.json()["violations"] if v["kind"] == "overlap"]
    assert any("camera_1" in pair for pair in pairs), r.json()["violations"]
    forget_cameras()
