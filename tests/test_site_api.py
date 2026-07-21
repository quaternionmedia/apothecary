"""API tests for the Site/Structure hierarchy endpoints (prototype, unratified)."""

from fastapi.testclient import TestClient

from apothecary.api import app

client = TestClient(app)


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


def test_site_viewer_page_renders():
    response = client.get("/viewer/sites/garage")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "garage" in response.text.lower()


def test_site_viewer_page_unknown_site_is_404():
    response = client.get("/viewer/sites/nope")
    assert response.status_code == 404
