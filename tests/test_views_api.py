"""Views: a picture pinned at a place in a site, its shapes, and the pieces made from them.

The fixture is a stated description of a picture 1000 by 500 pixels (so not
square), pinned at node ``workbench`` in site ``garage``. The bench's top is
x 0..1800, y 0..600 at z 780, so its top-centre is (900, 300, 780); at a
width of 1800 mm the mat covers the bench's width exactly and is 900 mm deep.
Its three shapes, read in the world at that width:

- 0, ``block``: centre (333, 336), under ``printer_1`` (x 98..568, y 109..563);
- 1, ``coin``: centre (1080, 50), in front of every printer, touching nothing;
- 2, ``bar``: centre (590, 590), just past ``printer_1``'s right side, behind it.
"""

from __future__ import annotations

import io
import json
import threading
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

from apothecary.api import _site_store, app

WIDE, HIGH = 1000, 500
TALLNESS = HIGH / WIDE
BENCH_TOP = (900.0, 300.0, 780.0)
SHAPES = [
    {
        "kind": "rect",
        "min": [0.135, 0.41],
        "max": [0.235, 0.51],
        "label": "block",
        "points": [[0.135, 0.41], [0.235, 0.41], [0.235, 0.51], [0.135, 0.51]],
    },
    {
        "kind": "disc",
        "min": [0.585, 0.7478],
        "max": [0.615, 0.8078],
        "label": "coin",
        "confidence": 0.9,
    },
    {
        "kind": "rect",
        "min": [0.3178, 0.1578],
        "max": [0.3378, 0.1978],
        "label": "bar",
        "confidence": 0.8,
    },
]


def _png(size=(WIDE, HIGH), shapes="rt") -> bytes:
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
def world(tmp_path, monkeypatch):
    """A picture root with the stated fixture, a state folder, and a fresh view store."""
    root = tmp_path / "pictures"
    root.mkdir()
    monkeypatch.setenv("APOTHECARY_PICTURE_ROOT", str(root))
    monkeypatch.setenv("APOTHECARY_STATE_DIR", str(tmp_path / "state"))
    (root / "bench_top.png").write_bytes(_png())
    (root / "bench_top.shapes.json").write_text(
        json.dumps(
            {"name": "bench_top", "pixel_width": WIDE, "pixel_height": HIGH, "shapes": SHAPES}
        ),
        encoding="utf-8",
    )
    (root / "drawn.png").write_bytes(_png(shapes="ret"))
    from apothecary.firmware import devices
    from apothecary.vision import cache as cache_module
    from apothecary.vision import views as views_module

    monkeypatch.setattr(devices, "_STATE", None)  # the boards pinned in this state folder
    monkeypatch.setattr(views_module, "_store", views_module.Views())
    monkeypatch.setattr(cache_module, "_cache", cache_module.FinderCache())
    for name in _site_store.names():
        _site_store.reset(name)
    yield root
    forget_cameras()


def forget_cameras():
    """Every camera a test added taken away, and every site built fresh: a Reset alone
    stands a site's cameras back in it, and the next test's state folder has none."""
    from apothecary.vision import cameras

    for camera in cameras.records():
        cameras.remove(camera.site, None, camera.name)
    for name in _site_store.loaded():
        _site_store.reset(name)


def _pin(c, *, site="garage", host="workbench", picture="bench_top.png", finder="stated", **more):
    """Pin a picture as a view and Find shapes in it: the two steps a person takes,
    as most tests here want them taken."""
    r = c.post(f"/sites/{site}/views", json={"host": host, "picture": picture, **more})
    assert r.status_code == 201, r.text
    r = c.post(f"/sites/{site}/views/{r.json()['id']}/find", json={"finder": finder})
    assert r.status_code == 200, r.text
    return r.json()


def _roots(c, site="garage"):
    return {s["name"]: s for s in c.get(f"/sites/{site}").json()["structures"]}


def _centre(structure):
    b = structure["world_bounds"]
    return ((b["min"][0] + b["max"][0]) / 2, (b["min"][1] + b["max"][1]) / 2, b["min"][2])


def _outline_centre(mat_centre, width, shape):
    cx = (shape["min"][0] + shape["max"][0]) / 2
    cy = (shape["min"][1] + shape["max"][1]) / 2
    return (
        mat_centre[0] + (cx - 0.5) * width,
        mat_centre[1] + (0.5 - cy) * width * TALLNESS,
    )


# --- taking and finding: two steps -----------------------------------------------------


def test_a_pinned_view_has_no_shapes_until_find_shapes_finds_them(world):
    """Pinning finds nothing; Find shapes is the step that does, as its own request.
    A view not yet searched (no finder, no time found) reads apart from one searched
    with nothing in it (a finder and a time, no shapes)."""
    c = TestClient(app)
    r = c.post("/sites/garage/views", json={"host": "workbench", "picture": "bench_top.png"})
    assert r.status_code == 201, r.text
    pinned = r.json()
    assert pinned["shapes"] == [] and pinned["finder"] is None and pinned["found_at"] is None
    # Its mat is laid all the same, at the picture's own proportions.
    assert (pinned["pixel_width"], pinned["pixel_height"]) == (WIDE, HIGH)
    assert pinned["mat"]["centre"] == list(BENCH_TOP)
    found = c.post(f"/sites/garage/views/{pinned['id']}/find", json={"finder": "stated"})
    assert found.status_code == 200, found.text
    view = found.json()
    assert view["id"] == pinned["id"] and view["finder"] == "stated" and view["found_at"]
    assert [s["index"] for s in view["shapes"]] == [0, 1, 2]
    attached = c.get("/sites/garage/attached").json()["views"]
    assert [(v["id"], len(v["shapes"])) for v in attached] == [(pinned["id"], 3)]
    # A picture with nothing in it, searched: a finder and a time, and no shapes.
    (world / "blank.png").write_bytes(_png(shapes=""))
    blank = c.post("/sites/garage/views", json={"host": "printer_1", "picture": "blank.png"})
    none = c.post(f"/sites/garage/views/{blank.json()['id']}/find", json={}).json()
    assert none["finder"] == "plain" and none["found_at"] and none["shapes"] == []
    # Nothing to find in a view that is not there, or with a finder that is not.
    assert c.post("/sites/garage/views/view_nowhere/find", json={}).status_code == 404
    r = c.post(f"/sites/garage/views/{pinned['id']}/find", json={"finder": "nope"})
    assert r.status_code == 400


def test_a_taken_picture_is_kept_and_pinned_with_no_shapes(world):
    """What a camera's Take picture sends: a frame kept under captures/ with its
    camera, lying where the camera looks, sized by how the camera stands, and no
    finder run. A camera added above the bench stands 600 mm above its clear
    middle, and its picture lies on the bench's own top: the first top its centre
    ray meets."""
    import math

    c = TestClient(app)
    added = c.post("/sites/garage/cameras", json={"host": "workbench"})
    assert added.status_code == 201, added.text
    assert added.json()["camera"]["position"] == [900.0, 300.0, 780.0 + 600.0]
    r = c.post(
        "/photos/pictures",
        params={"name": "camera_1", "site": "garage", "camera": "camera_1"},
        content=_png(shapes="ret"),
    )
    assert r.status_code == 201, r.text
    view = r.json()["view"]
    assert r.json()["path"].startswith("captures/") and view["picture"] == r.json()["path"]
    assert view["camera"] == "camera_1" and view["host"] == "workbench"
    assert view["mm_across"] == pytest.approx(2 * 600 * math.tan(math.radians(30)))
    assert view["mat"]["centre"] == pytest.approx(list(BENCH_TOP))
    assert view["shapes"] == [] and view["finder"] is None and view["found_at"] is None
    # A host and a camera together are refused, and a camera that is not there.
    both = {"name": "x", "site": "garage", "camera": "camera_1", "host": "workbench"}
    assert c.post("/photos/pictures", params=both, content=_png()).status_code == 422
    nowhere = {"name": "x", "site": "garage", "camera": "camera_9"}
    assert c.post("/photos/pictures", params=nowhere, content=_png()).status_code == 404
    found = c.post(f"/sites/garage/views/{view['id']}/find", json={"finder": "plain"}).json()
    assert found["finder"] == "plain" and len(found["shapes"]) == 3


def test_make_before_find_shapes_is_refused_and_names_find_shapes(world):
    """Make and Make all need shapes found and a width; each refusal names the step."""
    c = TestClient(app)
    pinned = c.post(
        "/sites/garage/views",
        json={"host": "workbench", "picture": "bench_top.png", "mm_across": 1800},
    ).json()
    for body in ({"shape": 0}, {"all": True}):
        r = c.post(f"/sites/garage/views/{pinned['id']}/make", json=body)
        assert r.status_code == 409, r.text
        assert "Find shapes" in r.json()["detail"], r.json()
    # And through the ring's intent, as a person would press it.
    intent = {
        "action": f"picture:make-all:{pinned['id']}",
        "option_id": "picture:make-all",
        "context": {"pointing": "node", "targets": ["workbench"]},
    }
    r = c.post("/menu/intent", json={"intent": intent, "site": "garage"})
    assert r.status_code == 409 and "Find shapes" in r.json()["detail"], r.text
    # Found, and unsized: the refusal names the width and where it is typed.
    unsized = c.post(
        "/sites/garage/views", json={"host": "printer_1", "picture": "bench_top.png"}
    ).json()
    c.post(f"/sites/garage/views/{unsized['id']}/find", json={"finder": "stated"})
    r = c.post(f"/sites/garage/views/{unsized['id']}/make", json={"all": True})
    assert r.status_code == 409 and "width" in r.json()["detail"]
    assert "Size" in r.json()["detail"], r.json()
    assert c.get("/sites/garage/attached").json()["made"] == {}


def test_find_shapes_with_another_finder_pins_a_second_view_and_keeps_the_first(world):
    """A view's shapes are its finder's: another finder's shapes are a new view of the
    same picture at the same host, sized as the first, and the first keeps its own."""
    c = TestClient(app)
    first = _pin(c, mm_across=1800)
    c.post(f"/sites/garage/views/{first['id']}/make", json={"shape": 1})
    again = c.post(f"/sites/garage/views/{first['id']}/find", json={"finder": "stated"})
    assert again.status_code == 200 and again.json()["id"] == first["id"]  # unchanged
    r = c.post(f"/sites/garage/views/{first['id']}/find", json={"finder": "plain"})
    assert r.status_code == 200, r.text
    second = r.json()
    assert second["id"] != first["id"] and second["finder"] == "plain"
    assert (second["host"], second["picture"]) == (first["host"], first["picture"])
    assert second["mm_across"] == 1800 and second["made"] == {}
    views = {v["id"]: v for v in c.get("/sites/garage/attached").json()["views"]}
    assert set(views[first["id"]]["made"]) == {"1"} and views[first["id"]]["finder"] == "stated"
    assert list(views)[-1] == second["id"]  # the newest, so the one drawn


# --- pinning ------------------------------------------------------------------------


def test_a_view_keeps_the_boxes_and_points_it_found(world):
    c = TestClient(app)
    view = _pin(c)
    assert view["id"].startswith("view_") and view["host"] == "workbench"
    assert view["picture"] == "bench_top.png" and view["finder"] == "stated"
    assert (view["pixel_width"], view["pixel_height"]) == (WIDE, HIGH)
    assert view["left_out"] == 0 and view["scale"] is None and view["mm_across"] is None
    shapes = view["shapes"]
    assert [s["index"] for s in shapes] == [0, 1, 2]
    assert shapes[0]["min"] == SHAPES[0]["min"] and shapes[0]["max"] == SHAPES[0]["max"]
    assert shapes[0]["points"] == SHAPES[0]["points"]
    assert shapes[1]["confidence"] == 0.9 and shapes[1]["word"] == "disc"
    assert all(s["status"] == "found" for s in shapes)
    # The mat lies on the bench's top, centred, unsized until a width is given.
    assert view["mat"]["centre"] == list(BENCH_TOP) and view["mat"]["width"] is None
    # Listed with the site's camera parts in one request; GET /sites does not change.
    attached = c.get("/sites/garage/attached").json()
    assert [vw["id"] for vw in attached["views"]] == [view["id"]]
    assert attached["cameras"] == [] and attached["made"] == {}
    assert "views" not in c.get("/sites/garage").json()


def test_a_pin_may_carry_a_typed_width(world):
    c = TestClient(app)
    view = _pin(c, mm_across=1800)
    assert view["mm_across"] == 1800 and view["scale"] == {"mm_across": 1800}
    assert view["mat"]["width"] == 1800 and view["mat"]["depth"] == 900


def test_views_and_cameras_are_refused_where_they_cannot_be_pinned(world):
    c = TestClient(app)
    for host, says in (
        ("storage_shelving.shelf_unit", "root"),
        ("garage_building", "footprint"),
        ("nowhere", "not found"),
    ):
        r = c.post(
            "/sites/garage/views",
            json={"host": host, "picture": "bench_top.png"},
        )
        assert r.status_code in (404, 422), (host, r.text)
        assert says in r.json()["detail"], (host, r.json())
        r = c.post("/sites/garage/cameras", json={"host": host})
        assert r.status_code in (404, 422) and says in r.json()["detail"], (host, r.json())
    # A made piece is not a host: its pins would go stale when it is dropped or reset.
    view = _pin(c, mm_across=1800)
    made = c.post(f"/sites/garage/views/{view['id']}/make", json={"shape": 1}).json()
    piece = made["made"][0]
    r = c.post("/sites/garage/views", json={"host": piece, "picture": "bench_top.png"})
    assert r.status_code == 422 and "made piece" in r.json()["detail"]
    r = c.post("/sites/garage/cameras", json={"host": piece})
    assert r.status_code == 422 and "made piece" in r.json()["detail"]
    # Nor is a camera: its pictures land where it looks.
    camera = c.post("/sites/garage/cameras", json={"host": "workbench"}).json()["camera"]
    for refused in (
        c.post("/sites/garage/views", json={"host": camera["name"], "picture": "bench_top.png"}),
        c.post("/sites/garage/cameras", json={"host": camera["name"]}),
    ):
        assert refused.status_code == 422 and "is a camera" in refused.json()["detail"]


def test_a_path_outside_the_root_is_refused(world):
    c = TestClient(app)
    outside = world.parent / "elsewhere.png"
    outside.write_bytes(_png())
    for picture in ("../elsewhere.png", str(outside)):
        r = c.post("/sites/garage/views", json={"host": "workbench", "picture": picture})
        assert r.status_code == 403, r.text


def test_cameras_added_at_a_host_and_at_the_floor_are_listed_where_they_look(world):
    c = TestClient(app)
    bench = c.post("/sites/garage/cameras", json={"host": "workbench"}).json()["camera"]
    floor = c.post("/sites/garage/cameras", json={"host": ""}).json()["camera"]
    listed = c.get("/sites/garage/attached").json()["cameras"]
    assert [(cam["name"], cam["lands"]["host"]) for cam in listed] == [
        (bench["name"], "workbench"),
        (floor["name"], ""),
    ]
    assert all(cam["device"] is None and cam["fov"] == 60 for cam in listed)


def test_a_new_view_from_a_camera_is_sized_by_how_it_stands(world):
    import math

    c = TestClient(app)
    c.post("/sites/garage/cameras", json={"host": "workbench"})
    view = _pin(c, host=None, camera="camera_1")
    assert view["camera"] == "camera_1" and view["host"] == "workbench"
    assert view["mm_across"] == pytest.approx(1200 * math.tan(math.radians(30)))
    assert view["scale"] is None  # no person sized it: it follows its camera's lens


# --- making pieces ------------------------------------------------------------------


def test_an_unsized_make_is_refused_with_its_reason(world):
    c = TestClient(app)
    view = _pin(c)
    r = c.post(f"/sites/garage/views/{view['id']}/make", json={"shape": 0})
    assert r.status_code == 409 and "width" in r.json()["detail"]
    assert c.post(f"/sites/garage/views/{view['id']}/make", json={"all": True}).status_code == 409
    assert set(_roots(c)) == set(_roots(c)) and not c.get("/sites/garage/attached").json()["made"]


def test_a_piece_stands_on_its_outline_at_a_host(world):
    c = TestClient(app)
    view = _pin(c, mm_across=1800)
    for index in (0, 2):  # one off-centre either way, on a picture that is not square
        r = c.post(f"/sites/garage/views/{view['id']}/make", json={"shape": index})
        assert r.status_code == 200, r.text
        piece = r.json()["made"][0]
        x, y, z = _centre(_roots(c)[piece])
        ex, ey = _outline_centre(BENCH_TOP, 1800, SHAPES[index])
        assert (x, y) == pytest.approx((ex, ey), abs=1e-6)
        assert z == pytest.approx(780.0)  # resting on the bench's top
    assert _outline_centre(BENCH_TOP, 1800, SHAPES[0]) == pytest.approx((333.0, 336.0))


def test_a_piece_stands_on_its_outline_at_the_floor(world):
    c = TestClient(app)
    view = _pin(c, host="", mm_across=1000)
    anchor = view["anchor"]
    # The floor's anchor: z 0, y at the centre of the code's roots, x past their +x edge.
    assert anchor[2] == 0 and anchor[0] > 5400
    mat = view["mat"]
    assert mat["centre"] == pytest.approx([anchor[0] + 500, anchor[1], 0])
    r = c.post(f"/sites/garage/views/{view['id']}/make", json={"shape": 0})
    piece = r.json()["made"][0]
    x, y, z = _centre(_roots(c)[piece])
    assert (x, y) == pytest.approx(_outline_centre(mat["centre"], 1000, SHAPES[0]))
    assert z == 0


def test_a_floor_mat_and_a_piece_at_its_centre_touch_nothing_in_any_site(world):
    from apothecary.hierarchy import _penetrates
    from apothecary.models.bounds import BoundingBox3D
    from apothecary.models.vectors import Vector3D

    c = TestClient(app)
    centred = {"kind": "rect", "min": [0.45, 0.45], "max": [0.55, 0.55]}
    (world / "centred.png").write_bytes(_png())
    (world / "centred.shapes.json").write_text(
        json.dumps({"pixel_width": WIDE, "pixel_height": HIGH, "shapes": [centred]})
    )
    for site in _site_store.names():
        before = [s for s in _roots(c, site).values() if s["world_bounds"]]
        view = _pin(c, site=site, host="", picture="centred.png", mm_across=1800)
        mat = view["mat"]
        mx, my, _ = mat["centre"]
        mat_box = BoundingBox3D(
            min_point=Vector3D(x=mx - 900, y=my - 450, z=0.0),
            max_point=Vector3D(x=mx + 900, y=my + 450, z=1.0),
        )
        made = c.post(f"/sites/{site}/views/{view['id']}/make", json={"shape": 0}).json()
        piece = _roots(c, site)[made["made"][0]]
        pb = piece["world_bounds"]
        piece_box = BoundingBox3D(
            min_point=Vector3D(x=pb["min"][0], y=pb["min"][1], z=pb["min"][2]),
            max_point=Vector3D(x=pb["max"][0], y=pb["max"][1], z=pb["max"][2]),
        )
        for other in before:
            b = other["world_bounds"]
            box = BoundingBox3D(
                min_point=Vector3D(x=b["min"][0], y=b["min"][1], z=b["min"][2]),
                max_point=Vector3D(x=b["max"][0], y=b["max"][1], z=b["max"][2]),
            )
            assert not _penetrates(mat_box, box), (site, other["name"])
            assert not _penetrates(piece_box, box), (site, other["name"])
        assert made["site"]["is_valid"], (site, made["site"]["violations"])


def test_an_overlap_with_a_made_piece_is_reported_once_everywhere(world):
    from apothecary.spaces import problems

    c = TestClient(app)
    view = _pin(c, mm_across=1800)
    made = c.post(f"/sites/garage/views/{view['id']}/make", json={"shape": 1}).json()
    coin = made["made"][0]
    assert made["site"]["is_valid"], made["site"]["violations"]
    # Moved under printer_1 with the gizmo's route: one violation, not two.
    r = c.post("/sites/garage/layout", json={"positions": {coin: {"x": 333, "y": 336, "z": 780}}})
    pairs = [sorted(v["structures"]) for v in r.json()["violations"] if v["kind"] == "overlap"]
    assert pairs == [sorted([coin, "printer_1"])]
    found = [p for p in problems() if p.subject == "garage" and coin in p.sources]
    assert len(found) == 1 and "printer_1" in found[0].sources
    # datum_core's validator checks only tray against lid; a made piece is checked all the same.
    tray_view = _pin(c, site="datum_core", host="tray", mm_across=40)
    made = c.post(f"/sites/datum_core/views/{tray_view['id']}/make", json={"shape": 1}).json()
    piece = made["made"][0]
    r = c.post("/sites/datum_core/layout", json={"positions": {piece: {"x": 0, "y": 0, "z": 28}}})
    pairs = [sorted(v["structures"]) for v in r.json()["violations"] if v["kind"] == "overlap"]
    assert pairs == [sorted([piece, "lid"])]


def test_make_all_skips_what_is_made_and_a_second_view_does_not_remake_it(world):
    c = TestClient(app)
    first = _pin(c, mm_across=1800)
    one = c.post(f"/sites/garage/views/{first['id']}/make", json={"shape": 1}).json()
    everything = c.post(f"/sites/garage/views/{first['id']}/make", json={"all": True}).json()
    assert len(everything["made"]) == 2 and everything["skipped"] == 1
    second = _pin(c, mm_across=1800)
    statuses = [s["status"] for s in c.get("/sites/garage/attached").json()["views"][1]["shapes"]]
    assert statuses == ["already_made"] * 3
    again = c.post(f"/sites/garage/views/{second['id']}/make", json={"all": True})
    assert again.status_code == 200 and again.json()["made"] == [] and again.json()["skipped"] == 3
    r = c.post(f"/sites/garage/views/{second['id']}/make", json={"shape": 1})
    assert r.status_code == 409 and one["made"][0] in r.json()["detail"]
    assert len(c.get("/sites/garage/attached").json()["made"]) == 3


def test_a_moved_piece_is_neither_made_twice_nor_hides_the_outline_it_stands_over(world):
    c = TestClient(app)
    first = _pin(c, mm_across=1800)
    coin = c.post(f"/sites/garage/views/{first['id']}/make", json={"shape": 1}).json()["made"][0]
    x, y, z = _centre(_roots(c)[coin])
    # Moved 500 mm onto where the bar was seen.
    bar_x, bar_y = _outline_centre(BENCH_TOP, 1800, SHAPES[2])
    c.post("/sites/garage/layout", json={"positions": {coin: {"x": bar_x, "y": bar_y, "z": z}}})
    second = _pin(c, mm_across=1800)
    shapes = next(
        vw for vw in c.get("/sites/garage/attached").json()["views"] if vw["id"] == second["id"]
    )["shapes"]
    assert shapes[1]["status"] == "already_made" and shapes[1]["piece"] == coin
    assert shapes[2]["status"] == "found"  # the coin stands over it now, and was not made from it
    r = c.post(f"/sites/garage/views/{second['id']}/make", json={"all": True}).json()
    assert r["skipped"] == 1 and len(r["made"]) == 2


def test_moving_the_host_moves_its_mat_and_not_its_pieces(world):
    c = TestClient(app)
    view = _pin(c, mm_across=1800)
    coin = c.post(f"/sites/garage/views/{view['id']}/make", json={"shape": 1}).json()["made"][0]
    before = _centre(_roots(c)[coin])
    c.post("/sites/garage/layout", json={"positions": {"workbench": {"x": 100, "y": 50, "z": 0}}})
    moved = c.get("/sites/garage/attached").json()["views"][0]
    assert moved["mat"]["centre"] == [1000.0, 350.0, 780.0]
    assert _centre(_roots(c)[coin]) == before


def test_make_all_past_the_made_cells_room_is_refused(world):
    from apothecary.vision import views as views_module

    c = TestClient(app)
    per_view = views_module.VIEW_SHAPES_MOST
    views = []
    for row in range(views_module.MADE_MOST // per_view + 1):
        many = [
            {
                "kind": "rect",
                "min": [0.02 * i, 0.1 + 0.3 * row],
                "max": [0.02 * i + 0.01, 0.12 + 0.3 * row],
            }
            for i in range(per_view)
        ]
        (world / f"many_{row}.png").write_bytes(_png())
        (world / f"many_{row}.shapes.json").write_text(
            json.dumps({"pixel_width": WIDE, "pixel_height": HIGH, "shapes": many})
        )
        views.append(_pin(c, host="", picture=f"many_{row}.png", mm_across=5000))
    for view in views[:-1]:
        r = c.post(f"/sites/garage/views/{view['id']}/make", json={"all": True})
        assert r.status_code == 200 and len(r.json()["made"]) == per_view, r.text
    made = c.get("/sites/garage/attached").json()["made"]
    assert len(made) == views_module.MADE_MOST
    r = c.post(f"/sites/garage/views/{views[-1]['id']}/make", json={"all": True})
    assert r.status_code == 409 and str(views_module.MADE_MOST) in r.json()["detail"]
    r = c.post(f"/sites/garage/views/{views[-1]['id']}/make", json={"shape": 0})
    assert r.status_code == 409
    assert c.get("/sites/garage/attached").json()["made"] == made


def test_a_view_keeps_at_most_its_budget_of_shapes_by_confidence(world):
    from apothecary.vision import views as views_module

    c = TestClient(app)
    most = views_module.VIEW_SHAPES_MOST
    lots = [
        {
            "kind": "rect",
            "min": [0.005 * i, 0.5],
            "max": [0.005 * i + 0.004, 0.51],
            "confidence": 0.5 if i else 0.99,
        }
        for i in range(most + 3)
    ]
    lots[-1]["confidence"] = 0.98
    (world / "lots.png").write_bytes(_png())
    (world / "lots.shapes.json").write_text(
        json.dumps({"pixel_width": WIDE, "pixel_height": HIGH, "shapes": lots})
    )
    view = _pin(c, picture="lots.png")
    assert len(view["shapes"]) == most and view["left_out"] == 3
    confidences = [s["confidence"] for s in view["shapes"]]
    assert 0.99 in confidences and 0.98 in confidences


def test_a_view_is_found_once_per_picture_and_finder(world):
    from apothecary.vision import finder as finder_module
    from apothecary.vision.stated import StatedFinder

    calls = []

    class Counting(StatedFinder):
        def name(self):
            return "counting"

        def look(self, image):
            calls.append(Path(image).name)
            return super().look(image)

    finder_module.register("counting", Counting)
    try:
        c = TestClient(app)
        _pin(c, finder="counting")
        _pin(c, finder="counting", host="printer_1")
        assert calls == ["bench_top.png"]
        # A picture changed on disk is a different picture.
        (world / "bench_top.png").write_bytes(_png(shapes="e"))
        _pin(c, finder="counting")
        assert calls == ["bench_top.png", "bench_top.png"]
    finally:
        finder_module._finders.pop("counting", None)


# --- scale --------------------------------------------------------------------------


def test_a_width_typed_for_a_shape_sizes_the_view_and_teaches_its_camera(world):
    """The first width typed for a camera's picture teaches the camera its field of
    view: its next picture is sized by it. A later width sizes its own view alone."""
    import math

    c = TestClient(app)
    c.post("/sites/garage/cameras", json={"host": "workbench"})
    first = _pin(c, host=None, camera="camera_1")
    # The coin's long side is 0.03 of the picture's width; say it is 54 mm. Seen
    # from 600 mm above, 1800 mm across is a field of view of 2 * atan(900 / 600).
    r = c.put(f"/sites/garage/views/{first['id']}/scale", json={"known_index": 1, "mm": 54})
    assert r.status_code == 200, r.text
    sized = r.json()
    assert sized["scale"] == {"known_index": 1, "mm": 54} and sized["taught"] == "camera_1"
    assert sized["mm_across"] == pytest.approx(1800)
    learned = math.degrees(2 * math.atan(900 / 600))
    camera = c.get("/sites/garage/cameras/camera_1").json()
    assert camera["fov"] == pytest.approx(learned) and camera["fov_taught"] is True
    second = _pin(c, host=None, camera="camera_1")
    per_pixel = [vw["mm_across"] / vw["pixel_width"] for vw in (sized, second)]
    assert per_pixel[0] == pytest.approx(per_pixel[1])
    # A later view can still be rescaled alone; the camera keeps what it learned.
    r = c.put(f"/sites/garage/views/{second['id']}/scale", json={"mm_across": 900})
    assert r.json()["mm_across"] == pytest.approx(900) and r.json()["taught"] is None
    assert c.get("/sites/garage/cameras/camera_1").json()["fov"] == pytest.approx(learned)
    views = {vw["id"]: vw for vw in c.get("/sites/garage/attached").json()["views"]}
    assert views[first["id"]]["mm_across"] == pytest.approx(1800)
    # Nonsense is refused, and a width no field of view reaches.
    for bad in ({}, {"mm_across": -1}, {"known_index": 9, "mm": 10}, {"known_index": 1}):
        assert c.put(f"/sites/garage/views/{first['id']}/scale", json=bad).status_code == 422, bad
    r = c.put(f"/sites/garage/views/{first['id']}/scale", json={"mm_across": 1e9})
    assert r.status_code == 422 and "field of view" in r.json()["detail"]


# --- words, parameters, drop ---------------------------------------------------------


def test_a_word_on_a_made_shape_rebuilds_its_piece_in_place(world):
    c = TestClient(app)
    view = _pin(c, mm_across=1800)
    piece = c.post(f"/sites/garage/views/{view['id']}/make", json={"shape": 0}).json()["made"][0]
    before = _roots(c)[piece]
    r = c.put(f"/sites/garage/views/{view['id']}/shapes/0", json={"word": "disc"})
    assert r.status_code == 200 and r.json()["rebuilt"] == piece
    after = _roots(c)[piece]
    assert after["position"] == before["position"]
    made = c.get("/sites/garage/attached").json()["made"][piece]
    assert made["word"] == "disc" and made["word_stated"] is True
    # An unmade shape takes the word too, and the piece made later uses it.
    r = c.put(f"/sites/garage/views/{view['id']}/shapes/1", json={"word": "post"})
    assert r.json()["rebuilt"] is None
    coin = c.post(f"/sites/garage/views/{view['id']}/make", json={"shape": 1}).json()["made"][0]
    assert coin.startswith("post_")
    assert (
        c.put(f"/sites/garage/views/{view['id']}/shapes/1", json={"word": "nope"}).status_code
        == 422
    )
    assert (
        c.put(f"/sites/garage/views/{view['id']}/shapes/7", json={"word": "disc"}).status_code
        == 404
    )


def test_a_made_piece_is_rebuilt_by_its_word_or_parameters_after_its_view_is_gone(world):
    c = TestClient(app)
    view = _pin(c, mm_across=1800)
    piece = c.post(f"/sites/garage/views/{view['id']}/make", json={"shape": 0}).json()["made"][0]
    position = _roots(c)[piece]["position"]
    assert c.delete(f"/sites/garage/views/{view['id']}").status_code == 200
    r = c.put(
        f"/sites/garage/made/{piece}", json={"parameters": {"width": 40, "depth": 30, "height": 5}}
    )
    assert r.status_code == 200, r.text
    after = _roots(c)[piece]
    assert after["position"] == position
    fp = after["footprint"]
    assert [fp["max"][i] - fp["min"][i] for i in range(3)] == pytest.approx([40, 30, 5])
    r = c.put(f"/sites/garage/made/{piece}", json={"word": "wedge"})
    assert r.status_code == 200 and r.json()["provenance"]["word"] == "wedge"
    assert _roots(c)[piece]["position"] == position
    assert c.put("/sites/garage/made/workbench", json={"word": "disc"}).status_code == 404
    assert c.put(f"/sites/garage/made/{piece}", json={}).status_code == 422


def test_drop_removes_the_piece_and_its_shape_reads_found_again(world):
    c = TestClient(app)
    view = _pin(c, mm_across=1800)
    piece = c.post(f"/sites/garage/views/{view['id']}/make", json={"shape": 1}).json()["made"][0]
    r = c.delete(f"/sites/garage/made/{piece}")
    assert r.status_code == 200 and piece not in {s["name"] for s in r.json()["site"]["structures"]}
    shapes = c.get("/sites/garage/attached").json()["views"][0]["shapes"]
    assert shapes[1]["status"] == "found" and shapes[1].get("piece") is None
    assert c.delete(f"/sites/garage/made/{piece}").status_code == 404


def test_names_stay_unique(world):
    c = TestClient(app)
    view = _pin(c, mm_across=1800)
    made = c.post(f"/sites/garage/views/{view['id']}/make", json={"all": True}).json()["made"]
    c.delete(f"/sites/garage/made/{made[0]}")
    again = c.post(f"/sites/garage/views/{view['id']}/make", json={"shape": 0}).json()["made"]
    second = _pin(c, host="printer_1", mm_across=1800)
    more = c.post(f"/sites/garage/views/{second['id']}/make", json={"all": True}).json()["made"]
    names = [s["name"] for s in c.get("/sites/garage").json()["structures"]]
    assert len(names) == len(set(names))
    assert set(made[1:] + again + more) <= set(names)


# --- the store under load -----------------------------------------------------------


def test_a_make_during_a_slow_find_loses_nothing_and_a_get_answers(world):
    from apothecary.vision import finder as finder_module
    from apothecary.vision.stated import StatedFinder

    started, release = threading.Event(), threading.Event()

    class Slow(StatedFinder):
        def name(self):
            return "slow"

        def look(self, image):
            started.set()
            assert release.wait(10)
            return super().look(image)

    finder_module.register("slow", Slow)
    try:
        c = TestClient(app)
        view = _pin(c, mm_across=1800)
        waiting = c.post(
            "/sites/garage/views", json={"host": "printer_1", "picture": "bench_top.png"}
        ).json()
        answers = {}

        def slow_find():
            answers["slow"] = TestClient(app).post(
                f"/sites/garage/views/{waiting['id']}/find", json={"finder": "slow"}
            )

        worker = threading.Thread(target=slow_find)
        worker.start()
        assert started.wait(10)
        t0 = time.monotonic()
        assert c.get("/sites/garage/attached").status_code == 200
        made = c.post(f"/sites/garage/views/{view['id']}/make", json={"all": True}).json()
        assert time.monotonic() - t0 < 5
        release.set()
        worker.join(10)
        assert answers["slow"].status_code == 200
        attached = c.get("/sites/garage/attached").json()
        assert len(attached["views"]) == 2
        assert len(attached["views"][1]["shapes"]) == 3
        assert sorted(attached["made"]) == sorted(made["made"]) and len(made["made"]) == 3
    finally:
        release.set()
        finder_module._finders.pop("slow", None)


def test_a_forget_during_a_make_loses_neither_the_mark_nor_the_piece(world, monkeypatch):
    from apothecary.vision import views as views_module
    from apothecary.vision.views import store

    c = TestClient(app)
    kept = c.post(
        "/photos/pictures",
        params={"name": "table", "kept": "upload"},
        content=(world / "bench_top.png").read_bytes(),
    ).json()
    (world / "uploads" / "table.shapes.json").write_text(
        (world / "bench_top.shapes.json").read_text()
    )
    view = _pin(c, picture=kept["path"], mm_across=1800)
    real = views_module.piece_from_shape

    def forgetting(*args, **kwargs):
        # The picture is forgotten from the threadpool while the make is under way.
        (world / kept["path"]).unlink()
        store().forget_picture(kept["path"])
        return real(*args, **kwargs)

    monkeypatch.setattr(views_module, "piece_from_shape", forgetting)
    r = c.post(f"/sites/garage/views/{view['id']}/make", json={"shape": 1})
    assert r.status_code == 200, r.text
    piece = r.json()["made"][0]
    assert piece in _roots(c)
    made = c.get("/sites/garage/attached").json()["made"]
    assert made[piece]["picture_forgotten"] is True


# --- cascades -----------------------------------------------------------------------


def test_unpinning_a_view_leaves_its_file_and_its_pieces(world):
    c = TestClient(app)
    view = _pin(c, mm_across=1800)
    piece = c.post(f"/sites/garage/views/{view['id']}/make", json={"shape": 1}).json()["made"][0]
    r = c.delete(f"/sites/garage/views/{view['id']}")
    assert r.status_code == 200 and r.json()["unpinned"] == view["id"]
    assert (world / "bench_top.png").is_file()
    attached = c.get("/sites/garage/attached").json()
    assert attached["views"] == [] and piece in attached["made"]
    # The piece keeps a copy of its shape, so its outline can be drawn without the view.
    assert attached["made"][piece]["shape"]["min"] == SHAPES[1]["min"]
    assert c.delete(f"/sites/garage/views/{view['id']}").status_code == 404


def test_forgetting_a_kept_picture_unpins_its_views_and_marks_its_pieces(world):
    c = TestClient(app)
    kept = c.post(
        "/photos/pictures",
        params={"name": "desk", "kept": "upload", "site": "garage", "host": "workbench"},
        content=_png(shapes="ret"),
    )
    assert kept.status_code == 201, kept.text
    view = kept.json()["view"]
    assert view["picture"] == "uploads/desk.png" and view["host"] == "workbench"
    view = c.post(f"/sites/garage/views/{view['id']}/find", json={}).json()
    assert view["finder"] == "plain" and view["shapes"]
    other = _pin(c, site="datum_core", host="tray", picture="uploads/desk.png", finder="plain")
    c.put(f"/sites/garage/views/{view['id']}/scale", json={"mm_across": 1800})
    piece = c.post(f"/sites/garage/views/{view['id']}/make", json={"shape": 0}).json()["made"][0]
    r = c.delete("/photos/pictures/uploads/desk.png")
    assert r.status_code == 200 and sorted(r.json()["unpinned"]) == sorted(
        [view["id"], other["id"]]
    )
    attached = c.get("/sites/garage/attached").json()
    assert attached["views"] == [] and attached["made"][piece]["picture_forgotten"] is True
    assert piece in _roots(c)
    assert c.get("/sites/datum_core/attached").json()["views"] == []


def test_purge_cascades_and_leaves_the_folders_own(world):
    c = TestClient(app)
    own = _pin(c)
    kept = c.post(
        "/photos/pictures",
        params={"name": "frame", "site": "garage", "host": ""},
        content=_png(shapes="r"),
    ).json()
    assert kept["view"]["host"] == ""
    r = c.delete("/photos/pictures")
    assert r.status_code == 200 and r.json()["unpinned"] == [kept["view"]["id"]]
    assert [vw["id"] for vw in c.get("/sites/garage/attached").json()["views"]] == [own["id"]]
    assert (world / "bench_top.png").is_file()


def test_a_refused_pin_keeps_nothing(world):
    c = TestClient(app)
    r = c.post(
        "/photos/pictures",
        params={"name": "x", "kept": "upload", "site": "garage", "host": "garage_building"},
        content=_png(),
    )
    assert r.status_code == 422
    assert not (world / "uploads").exists() or not list((world / "uploads").iterdir())


def test_reset_takes_made_pieces_back_and_leaves_the_views(world):
    c = TestClient(app)
    view = _pin(c, mm_across=1800)
    first = c.post(f"/sites/garage/views/{view['id']}/make", json={"shape": 1}).json()["made"][0]
    c.post("/sites/garage/reset")
    attached = c.get("/sites/garage/attached").json()
    assert first not in _roots(c) and attached["made"] == {}
    assert [vw["id"] for vw in attached["views"]] == [view["id"]]
    assert attached["views"][0]["made"] == {}
    assert all(s["status"] == "found" for s in attached["views"][0]["shapes"])
    # And by the ring's intent.
    second = c.post(f"/sites/garage/views/{view['id']}/make", json={"shape": 1}).json()["made"][0]
    intent = {
        "action": "reset",
        "option_id": "reset",
        "context": {"pointing": "canvas", "targets": []},
    }
    r = c.post("/menu/intent", json={"intent": intent, "site": "garage"})
    assert r.status_code == 200, r.text
    assert second not in _roots(c) and c.get("/sites/garage/attached").json()["made"] == {}


# --- every site's pins --------------------------------------------------------------


def test_placed_lists_every_sites_cameras_and_views(world):
    c = TestClient(app)
    c.post("/sites/garage/cameras", json={"host": "workbench"})
    a = _pin(c)
    b = _pin(c, site="datum_core", host="tray")
    placed = c.get("/placed").json()
    assert [(cam["site"], cam["name"]) for cam in placed["cameras"]] == [("garage", "camera_1")]
    assert placed["cameras"][0]["node_found"] is True
    views = {vw["id"]: vw for vw in placed["views"]}
    assert set(views) == {a["id"], b["id"]} and views[b["id"]]["site"] == "datum_core"
    assert all(vw["host_found"] for vw in placed["views"])
    assert "shapes" not in views[a["id"]]  # a row, not the view
    assert placed["boards"] == []


# --- the picture route --------------------------------------------------------------


def test_a_picture_is_served_at_a_few_sizes_and_never_cached(world):
    c = TestClient(app)
    whole = c.get("/photos/pictures/file", params={"path": "bench_top.png"})
    assert whole.status_code == 200 and whole.headers["cache-control"] == "no-store"
    small = c.get("/photos/pictures/file", params={"path": "bench_top.png", "px": 300})
    assert small.status_code == 200 and small.headers["cache-control"] == "no-store"
    with Image.open(io.BytesIO(small.content)) as img:
        assert max(img.size) in (256, 512) and img.size[0] == 2 * img.size[1]
    jpg = io.BytesIO()
    Image.new("RGB", (2000, 1000), (200, 100, 50)).save(jpg, format="JPEG")
    (world / "big.jpg").write_bytes(jpg.getvalue())
    thumb = c.get("/photos/pictures/file", params={"path": "big.jpg", "px": 5000})
    assert thumb.headers["content-type"] == "image/jpeg"
    with Image.open(io.BytesIO(thumb.content)) as img:
        assert max(img.size) <= 2048
    assert (
        c.get("/photos/pictures/file", params={"path": "bench_top.png", "px": 0}).status_code == 422
    )
