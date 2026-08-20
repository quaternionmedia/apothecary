from fastapi.testclient import TestClient

from apothecary.api import app
from apothecary.example import create_example_scene
from apothecary.projects.parts.skeleton import ROOT
from apothecary.projects.registry import scan_projects


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


def test_parts_metadata_uses_repo_relative_paths():
    client = TestClient(app)
    r = client.get("/parts/parametric_star")
    assert r.status_code == 200
    data = r.json()
    assert data["source_file"].startswith("parts/")
    assert ":/" not in data["source_file"]
    if data.get("readme"):
        assert not data["readme"].startswith("/")
        assert ":/" not in data["readme"]


def test_parts_include_uses_repo_relative_include_path():
    client = TestClient(app)
    r = client.get("/parts/parametric_star")
    assert r.status_code == 200
    include = r.json()["include"]
    assert "include <parts/" in include
    assert "C:/" not in include
    assert "\\\\" not in include


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


def test_viewer_home_redirects_to_the_named_default_site():
    """/viewer no longer serves a standalone parts browser -- it redirects to
    the fractal viewer for api.py's DEFAULT_VIEWER_SITE. It used to redirect to
    whichever site sorted first, which meant registering one could move the
    front door without anyone deciding to (parts are reached by navigating into
    "parts_library"; datum-core is its own site).
    """
    client = TestClient(app)
    r = client.get("/viewer", follow_redirects=False)
    assert r.status_code == 307
    assert r.headers.get("location", "") == "/viewer/sites/garage"
