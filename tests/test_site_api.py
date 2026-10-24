"""API tests for the Site/Structure hierarchy endpoints (prototype, unratified)."""

import os
import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

import apothecary.api as api
from apothecary.api import _find_node_by_path, _job_store, _site_store, app
from apothecary.example_hierarchy import create_example_site
from apothecary.firmware import devices as firmware_devices
from apothecary.firmware import gcode as firmware_gcode
from apothecary.firmware.models import DeviceInfo, PrinterInfo
from apothecary.hierarchy import Assembly, Site
from apothecary.primitives import Import
from apothecary.projects.parts.skeleton import ROOT
from apothecary.projects.parts.stl_renderer import RenderResult, get_renderer

client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_garage_site():
    """The site store keeps edits between requests: each test starts from the
    factory garage. test_reset_endpoint_discards_edits covers the route."""
    _site_store.reset("garage")
    _job_store.reset("garage")
    yield


def test_list_sites():
    response = client.get("/sites")
    assert response.status_code == 200
    assert response.json() == ["datum_core", "garage", "parts_library"]


def test_get_unknown_site_is_404():
    response = client.get("/sites/nope")
    assert response.status_code == 404


def test_get_garage_site_default_layout_is_valid():
    response = client.get("/sites/garage")
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Garage"
    assert data["is_valid"] is True
    assert data["violations"] == []
    names = {s["name"] for s in data["structures"]}
    assert {"workbench", "printer_1", "printer_2", "printer_3"} <= names
    assert {
        "garage_building",
        "lighting",
        "hvac",
        "electrical",
        "fluids",
        "storage_shelving",
        "cnc_router",
    } <= names


def test_get_garage_site_includes_substructures_and_features():
    data = client.get("/sites/garage").json()
    workbench = data["structures"][0]
    assert workbench["substructures"][0]["name"] == "frame_system"
    assert "cable_pass_through" in workbench["substructures"][0]["features"]

    printer_1 = data["structures"][1]
    substructure_names = {s["name"] for s in printer_1["substructures"]}
    assert substructure_names == {"frame_system", "gantry_system"}


def test_get_garage_site_tree_recurses_past_one_level():
    """``tree`` (unlike the flattened ``structures``) walks the whole fractal
    depth -- the belt_tensioner_boss -> belt_tensioner_relief_chamfer nesting
    is four levels below printer_1, well past what ``structures`` flattens.
    """
    data = client.get("/sites/garage").json()
    printer_1 = next(s for s in data["tree"]["children"] if s["name"] == "printer_1")
    gantry_system = next(s for s in printer_1["children"] if s["name"] == "gantry_system")
    belt_tensioner_system = next(
        s for s in gantry_system["children"] if s["name"] == "belt_tensioner_system"
    )
    belt_tensioner_boss = next(
        s for s in belt_tensioner_system["children"] if s["name"] == "belt_tensioner_boss"
    )
    assert belt_tensioner_boss["composition"] == "addition"
    chamfer = next(
        s for s in belt_tensioner_boss["children"] if s["name"] == "belt_tensioner_relief_chamfer"
    )
    assert chamfer["role"] == "feature"


def test_tree_category_is_set_on_top_level_structures_and_inherited_below():
    """category is only ever set on the top-level Structure in this example
    (see example_hierarchy.py) -- everything beneath it must inherit that
    same value from the nearest tagged ancestor, however deep.
    """
    data = client.get("/sites/garage").json()
    tree = data["tree"]

    by_name = {s["name"]: s for s in tree["children"]}
    assert by_name["workbench"]["category"] == "furniture"
    assert by_name["printer_1"]["category"] == "mechanical"
    assert by_name["garage_building"]["category"] == "wall"
    assert by_name["lighting"]["category"] == "electrical"
    assert by_name["hvac"]["category"] == "mechanical"
    assert by_name["electrical"]["category"] == "electrical"
    assert by_name["fluids"]["category"] == "fluid"
    assert by_name["storage_shelving"]["category"] == "furniture"
    assert by_name["cnc_router"]["category"] == "mechanical"

    garage_building = by_name["garage_building"]
    north_wall = next(s for s in garage_building["children"] if s["name"] == "north_wall")
    assert north_wall["category"] == "wall"

    printer_1 = by_name["printer_1"]
    gantry_system = next(s for s in printer_1["children"] if s["name"] == "gantry_system")
    belt_tensioner_system = next(
        s for s in gantry_system["children"] if s["name"] == "belt_tensioner_system"
    )
    assert belt_tensioner_system["category"] == "mechanical"


def test_get_parts_library_site():
    response = client.get("/sites/parts_library")
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Parts Library"
    assert data["is_valid"] is True
    assert len(data["tree"]["children"]) > 0
    assert all(child["part_ref"] for child in data["tree"]["children"])


def test_workbench_has_no_status_or_build_volume():
    data = client.get("/sites/garage").json()
    workbench = data["structures"][0]
    assert workbench["status"] is None
    assert workbench["build_volume"] is None


def test_printers_default_to_idle_with_a_build_volume():
    data = client.get("/sites/garage").json()
    printers = [s for s in data["structures"] if s["name"].startswith("printer_")]
    assert len(printers) == 3
    for printer in printers:
        assert printer["status"] == "idle"
        assert printer["build_volume"] == [220.0, 220.0, 250.0]


def test_cnc_router_has_no_build_volume():
    """Unlike the printers, the CNC router stub isn't wired into the job
    queue yet (see example_hierarchy.py's BENCH_MOUNTED_STRUCTURES comment).
    """
    data = client.get("/sites/garage").json()
    router = next(s for s in data["structures"] if s["name"] == "cnc_router")
    assert router["status"] == "idle"
    assert router["build_volume"] is None


def test_update_structure_status():
    response = client.post("/sites/garage/structures/printer_1/status", json={"status": "printing"})
    assert response.status_code == 200
    printer_1 = next(s for s in response.json()["structures"] if s["name"] == "printer_1")
    assert printer_1["status"] == "printing"

    # persists across a plain GET, same as position edits
    data = client.get("/sites/garage").json()
    printer_1 = next(s for s in data["structures"] if s["name"] == "printer_1")
    assert printer_1["status"] == "printing"


def test_update_structure_status_rejects_unknown_value():
    response = client.post(
        "/sites/garage/structures/printer_1/status", json={"status": "on_fire"}
    )
    assert response.status_code == 400


def test_update_structure_status_unknown_structure_is_404():
    response = client.post(
        "/sites/garage/structures/not_a_real_structure/status", json={"status": "idle"}
    )
    assert response.status_code == 404


def test_update_structure_status_unknown_site_is_404():
    response = client.post("/sites/nope/structures/printer_1/status", json={"status": "idle"})
    assert response.status_code == 404


def test_layout_endpoint_with_no_overrides_matches_default():
    response = client.post("/sites/garage/layout", json={"positions": {}})
    assert response.status_code == 200
    data = response.json()
    assert data["is_valid"] is True
    assert "scad" in data and "Structure: workbench" in data["scad"]


def test_layout_endpoint_detects_overlap():
    response = client.post(
        "/sites/garage/layout",
        json={"positions": {"printer_1": {"x": 650, "y": 150, "z": 780}}},
    )
    data = response.json()
    assert data["is_valid"] is False
    kinds = {v["kind"] for v in data["violations"]}
    assert "overlap" in kinds


def test_layout_endpoint_detects_overhang():
    response = client.post(
        "/sites/garage/layout",
        json={"positions": {"printer_1": {"x": 1750, "y": 150, "z": 780}}},
    )
    data = response.json()
    assert data["is_valid"] is False
    kinds = {v["kind"] for v in data["violations"]}
    assert "out_of_bounds" in kinds


def test_layout_endpoint_detects_wrong_height():
    response = client.post(
        "/sites/garage/layout",
        json={"positions": {"printer_1": {"x": 100, "y": 150, "z": 0}}},
    )
    data = response.json()
    assert data["is_valid"] is False
    kinds = {v["kind"] for v in data["violations"]}
    assert "not_on_bench" in kinds


def test_layout_endpoint_valid_move_updates_world_bounds_and_scad():
    # A 470 mm Ender 3 nudged 20 mm right still clears printer_2; its world
    # bounds start where its LCD hangs off the front (y -41) and its frame
    # begins (x -2), which is what the footprint says.
    response = client.post(
        "/sites/garage/layout",
        json={"positions": {"printer_1": {"x": 120, "y": 150, "z": 780}}},
    )
    data = response.json()
    assert data["is_valid"] is True, data.get("violations")
    printer_1 = next(s for s in data["structures"] if s["name"] == "printer_1")
    assert printer_1["world_bounds"]["min"] == [118.0, 109.0, 780.0]
    assert "translate([120.0, 150.0, 780.0])" in data["scad"]


def test_layout_endpoint_unknown_site_is_404():
    response = client.post("/sites/nope/layout", json={"positions": {}})
    assert response.status_code == 404


def test_layout_edits_persist_across_get_requests():
    client.post(
        "/sites/garage/layout",
        json={"positions": {"printer_1": {"x": 300, "y": 150, "z": 780}}},
    )
    data = client.get("/sites/garage").json()
    printer_1 = next(s for s in data["structures"] if s["name"] == "printer_1")
    assert printer_1["position"]["x"] == 300.0


def test_reset_endpoint_discards_edits():
    client.post(
        "/sites/garage/layout",
        json={"positions": {"printer_1": {"x": 300, "y": 150, "z": 780}}},
    )
    response = client.post("/sites/garage/reset")
    assert response.status_code == 200
    data = response.json()
    assert data["is_valid"] is True
    printer_1 = next(s for s in data["structures"] if s["name"] == "printer_1")
    assert printer_1["position"]["x"] == 100.0  # PRINTER_X_POSITIONS[0] default

    # confirm it actually persisted the reset, not just returned a fresh copy
    data_after = client.get("/sites/garage").json()
    printer_1_after = next(s for s in data_after["structures"] if s["name"] == "printer_1")
    assert printer_1_after["position"]["x"] == 100.0


def test_reset_endpoint_unknown_site_is_404():
    response = client.post("/sites/nope/reset")
    assert response.status_code == 404


def test_site_viewer_page_renders():
    response = client.get("/viewer/sites/garage")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "garage" in response.text.lower()


def test_site_viewer_page_unknown_site_is_404():
    response = client.get("/viewer/sites/nope")
    assert response.status_code == 404


# =============================================================================
# _find_node_by_path -- dotted-path resolution for the node-STL endpoint
# =============================================================================


def test_find_node_by_path_resolves_a_direct_child():
    site = create_example_site()
    node = _find_node_by_path(site, "garage_building")
    assert node is not None
    assert node.name == "garage_building"


def test_find_node_by_path_resolves_through_additions_and_children():
    """belt_tensioner_boss is an addition of belt_tensioner_system, which is
    a child of gantry_system -- resolution must walk children, additions,
    and subtractions uniformly, not just children.
    """
    site = create_example_site()
    node = _find_node_by_path(
        site, "printer_1.gantry_system.belt_tensioner_system.belt_tensioner_boss"
    )
    assert node is not None
    assert node.name == "belt_tensioner_boss"


def test_find_node_by_path_unknown_segment_returns_none():
    site = create_example_site()
    assert _find_node_by_path(site, "printer_1.no_such_child") is None
    assert _find_node_by_path(site, "no_such_top_level") is None


# =============================================================================
# GET /sites/{name}/nodes/{path}/stl -- render any addressable node's own
# subtree through the OpenSCAD CLI, cached by content hash (edge 2: real
# geometry for composite nodes, not just leaves).
# =============================================================================


def test_node_stl_endpoint_unknown_site_is_404():
    response = client.get("/sites/nope/nodes/garage_building/stl")
    assert response.status_code == 404


def test_node_stl_endpoint_unknown_node_is_404():
    response = client.get("/sites/garage/nodes/no_such_node/stl")
    assert response.status_code == 404


@pytest.mark.skipif(not get_renderer().is_available, reason="OpenSCAD not installed")
def test_node_stl_endpoint_renders_a_composite_node():
    """garage_building has no part_ref and more than one wall union'd
    together (plus a differenced-out door/window) -- exactly the shape a
    single primitive descriptor can't represent, so this is real CSG output
    from the OpenSCAD CLI, not a bounding box.
    """
    response = client.get("/sites/garage/nodes/garage_building/stl")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/sla"
    assert len(response.content) > 0
    assert response.content.startswith(b"solid") or len(response.content) > 84  # ASCII or binary STL


@pytest.mark.skipif(not get_renderer().is_available, reason="OpenSCAD not installed")
def test_node_stl_endpoint_caches_by_content_hash():
    first = client.get("/sites/garage/nodes/printer_1.frame_system/stl")
    second = client.get("/sites/garage/nodes/printer_1.frame_system/stl")
    assert first.status_code == second.status_code == 200
    assert first.content == second.content


class _SlowOpenSCAD:
    """Keeps each SCAD it is handed and where it sat, and writes a stub STL after a pause."""

    is_available = True

    def __init__(self):
        self.scad, self.folders = [], []

    def render_stl(self, scad_path, stl_path, timeout=120.0, params=None):
        self.scad.append(scad_path.read_text(encoding="utf-8"))
        self.folders.append(scad_path.parent)
        time.sleep(0.2)
        stl_path.write_bytes(b"solid stub\nendsolid stub\n")
        return RenderResult(success=True, stl_path=stl_path)


@pytest.fixture
def slow_openscad(tmp_path, monkeypatch):
    monkeypatch.setenv("APOTHECARY_CACHE_DIR", str(tmp_path))
    fake = _SlowOpenSCAD()
    monkeypatch.setattr(api, "get_stl_renderer", lambda: fake)
    return fake


def test_node_stl_scratch_sits_in_the_cache_and_imports_by_absolute_path(slow_openscad, tmp_path):
    mesh = Assembly(name="mesh", role="part", base=Import(file="parts/somewhere/thing.stl"))
    _site_store.add(
        "import_probe", lambda: Site("import_probe", structures=[mesh]), Assembly.validate
    )
    try:
        response = client.get("/sites/import_probe/nodes/mesh/stl")
    finally:
        _site_store.remove("import_probe")
    assert response.status_code == 200, response.text
    assert f'import("{ROOT.as_posix()}/parts/somewhere/thing.stl"' in slow_openscad.scad[0]
    assert slow_openscad.folders == [tmp_path / "node_stl"]
    assert [p.suffix for p in (tmp_path / "node_stl").iterdir()] == [".stl"]


def test_one_render_per_node_however_many_ask_at_once(slow_openscad):
    with ThreadPoolExecutor(4) as pool:
        answers = list(pool.map(lambda _: api.get_node_stl("garage", "garage_building"), range(4)))
    assert len(slow_openscad.scad) == 1
    assert {a.body for a in answers} == {b"solid stub\nendsolid stub\n"}


@pytest.fixture
def a_held_printer(fake_arduino_cli, monkeypatch):
    """A printer on /dev/ttyFAKE1 with its link open; polling it fails the test."""
    board = DeviceInfo(
        port="/dev/ttyFAKE1",
        serial_number="FAKESERIAL1",
        printer=PrinterInfo(firmware_name="Marlin"),
    )

    def polled(port, *_, **__):
        raise AssertionError(f"polled the printer on {port}")

    monkeypatch.setattr(firmware_devices, "detected_devices", lambda *_, **__: [board])
    monkeypatch.setattr(firmware_gcode, "get_printer_links", lambda: {board.port: object()})
    monkeypatch.setattr(firmware_devices, "printer_status", polled)
    return board


def test_a_pin_change_polls_no_printer(a_held_printer):
    pinned = client.put("/sites/garage/nodes/printer_1/device", json={"identity": "/dev/ttyFAKE1"})
    assert pinned.status_code == 200, pinned.text
    assert pinned.json()["binding_source"] == "manual"
    assert pinned.json()["device"]["port"] == "/dev/ttyFAKE1"

    unpinned = client.delete("/sites/garage/nodes/printer_1/device")
    assert unpinned.status_code == 200, unpinned.text
    assert unpinned.json()["path"] == "printer_1"
    assert unpinned.json()["binding_source"] is None


def test_the_node_cache_keeps_the_most_recently_served(tmp_path):
    for i in range(5):
        (tmp_path / f"{i}.stl").write_bytes(b"x")
        os.utime(tmp_path / f"{i}.stl", ns=(i * 10**9, 0))
    (tmp_path / ".0.inflight.stl").write_bytes(b"x")  # a render being written
    api._trim_node_stl_cache(tmp_path, keep=3)
    kept = sorted(p.name for p in tmp_path.iterdir())
    assert kept == [".0.inflight.stl", "2.stl", "3.stl", "4.stl"]
