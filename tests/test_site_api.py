"""API tests for the Site/Structure hierarchy endpoints (prototype, unratified)."""

import pytest
from fastapi.testclient import TestClient

from apothecary.api import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_garage_site():
    """The site store persists edits across requests (see site_store.py), so
    reset garage to its factory defaults before every test in this module --
    otherwise a test that moves a printer would leak state into the next one.
    """
    client.post("/sites/garage/reset")
    yield


def test_list_sites():
    response = client.get("/sites")
    assert response.status_code == 200
    assert response.json() == ["garage"]


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
    names = [s["name"] for s in data["structures"]]
    assert names == ["workbench", "printer_1", "printer_2", "printer_3"]


def test_get_garage_site_includes_substructures_and_features():
    data = client.get("/sites/garage").json()
    workbench = data["structures"][0]
    assert workbench["substructures"][0]["name"] == "frame_system"
    assert "cable_pass_through" in workbench["substructures"][0]["features"]

    printer_1 = data["structures"][1]
    substructure_names = {s["name"] for s in printer_1["substructures"]}
    assert substructure_names == {"frame_system", "gantry_system"}


def test_workbench_has_no_status_or_build_volume():
    data = client.get("/sites/garage").json()
    workbench = data["structures"][0]
    assert workbench["status"] is None
    assert workbench["build_volume"] is None


def test_printers_default_to_idle_with_a_build_volume():
    data = client.get("/sites/garage").json()
    for printer in data["structures"][1:]:
        assert printer["status"] == "idle"
        assert printer["build_volume"] == [220.0, 220.0, 250.0]


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
    response = client.post(
        "/sites/garage/layout",
        json={"positions": {"printer_1": {"x": 300, "y": 150, "z": 780}}},
    )
    data = response.json()
    assert data["is_valid"] is True
    printer_1 = next(s for s in data["structures"] if s["name"] == "printer_1")
    assert printer_1["world_bounds"]["min"] == [300.0, 150.0, 780.0]
    assert "translate([300.0, 150.0, 780.0])" in data["scad"]


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
