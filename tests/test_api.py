from fastapi.testclient import TestClient

from apothecary.api import app
from apothecary.example import create_example_scene
from apothecary.projects.registry import scan_projects
from apothecary.projects.parts.skeleton import ROOT


def test_health_endpoint():
    client = TestClient(app)
    r = client.get("/health")
    assert r.status_code == 200
    data = r.json()
    assert data.get("status") == "healthy"


def test_render_endpoint_with_example_scene():
    client = TestClient(app)
    scene = create_example_scene()
    r = client.post("/render", json=scene.model_dump())
    assert r.status_code == 200
    data = r.json()
    assert data.get("success") is True
    assert "code" in data and isinstance(data["code"], str)
    assert data.get("object_count", 0) >= 1


def _expected_part_names():
    return {p.name for p in scan_projects(ROOT) if p.kind == "part"}


def test_parts_listing_contains_known_part():
    client = TestClient(app)
    r = client.get("/parts")
    assert r.status_code == 200
    data = r.json()
    names = {item["name"] for item in data}
    # Ensure at least one known part is in the response
    assert any(name in names for name in _expected_part_names())


def test_parts_detail_and_scad_download():
    client = TestClient(app)
    # Parametric star is always present in the repo
    r = client.get("/parts/parametric_star")
    assert r.status_code == 200
    data = r.json()
    assert data["name"] == "parametric_star"
    assert "include" in data
    scad = client.get("/parts/parametric_star/scad")
    assert scad.status_code == 200
    assert "module parametric_star" in scad.text


def test_parts_random_endpoint_returns_metadata():
    client = TestClient(app)
    r = client.get("/parts/random")
    assert r.status_code == 200
    data = r.json()
    assert data.get("random_source") in _expected_part_names()
    assert "include" in data and "download_url" in data


def test_parts_random_scad_endpoint():
    client = TestClient(app)
    r = client.get("/parts/random/scad")
    assert r.status_code == 200
    header_name = r.headers.get("x-part-name")
    assert header_name is not None and header_name.strip()
    assert len(r.text) > 10


def test_viewer_random_redirects():
    """Test that /viewer/random redirects to viewer with a random part."""
    client = TestClient(app)
    r = client.get("/viewer/random", follow_redirects=False)
    assert r.status_code == 307
    location = r.headers.get("location", "")
    # Now redirects to main viewer with part query param
    assert location.startswith("/viewer?part=")


def test_viewer_specific_part_redirect():
    """Test that /viewer/parts/{name} redirects to viewer with part selected."""
    client = TestClient(app)
    part_name = next(iter(_expected_part_names()))
    r = client.get(f"/viewer/parts/{part_name}", follow_redirects=False)
    assert r.status_code == 307
    location = r.headers.get("location", "")
    # Redirects to main viewer with part query param
    assert location.startswith("/viewer?part=")
