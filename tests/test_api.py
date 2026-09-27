import pytest
from fastapi.testclient import TestClient

import apothecary.api as api
from apothecary import meshes
from apothecary.api import app
from apothecary.example import create_example_scene
from apothecary.projects.parts.calibration_cube import DEFAULT as CUBE
from apothecary.projects.parts.skeleton import ROOT
from apothecary.projects.registry import scan_projects


def test_health_endpoint():
    client = TestClient(app)
    r = client.get("/health")
    assert r.status_code == 200
    data = r.json()
    assert data.get("status") == "healthy"


def test_render_endpoint_with_example_scene():
    """What the library renders in-process is what the endpoint renders from JSON."""
    client = TestClient(app)
    scene = create_example_scene()
    r = client.post("/render", json=scene.model_dump(mode="json"))
    assert r.status_code == 200
    data = r.json()
    assert data["code"] == scene.render()
    assert data["object_count"] == len(scene.objects)


def test_render_endpoint_builds_what_the_document_describes():
    client = TestClient(app)
    doc = {
        "objects": [
            {"type": "cube", "size": {"x": 1, "y": 2, "z": 3}},
            {
                "type": "difference",
                "children": [
                    {"type": "sphere", "r": 4},
                    {
                        "type": "translate",
                        "v": {"x": 1, "y": 0, "z": 0},
                        "children": [{"type": "cylinder", "h": 2, "r1": 1, "r2": 0.5}],
                    },
                ],
            },
        ]
    }
    code = client.post("/render", json=doc).json()["code"]
    assert "cube([1.0, 2.0, 3.0], center=false);" in code
    assert "sphere(r=4.0);" in code
    assert "cylinder(h=2.0, r1=1.0, r2=0.5, center=false);" in code


@pytest.mark.parametrize(
    "bad",
    [{"r": 5}, {"type": "wat"}, {"type": "cube", "size": {"x": "?"}}],
    ids=["no type", "unknown type", "bad field"],
)
def test_render_endpoint_refuses_what_it_cannot_build(bad):
    """No guessing: an object that does not say what it is, or says something
    it cannot be, is a 422 -- not a 200 with an empty union in it."""
    client = TestClient(app)
    assert client.post("/render", json={"objects": [bad]}).status_code == 422


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


def test_every_listed_part_serves_its_scad():
    client = TestClient(app)
    listed = [part["name"] for part in client.get("/parts").json()]
    assert listed
    for name in listed:
        r = client.get(f"/parts/{name}/scad")
        assert r.status_code == 200, name
        assert r.text.strip(), name


def test_viewer_home_redirects_to_the_named_default_site():
    """/viewer no longer serves a standalone parts browser -- it redirects to
    the fractal viewer for api.py's DEFAULT_VIEWER_SITE. It used to redirect to
    whichever site sorted first, which meant registering one could move the
    front door without anyone deciding to (parts are reached by navigating into
    "parts_library"; datum_core is its own site).
    """
    client = TestClient(app)
    r = client.get("/viewer", follow_redirects=False)
    assert r.status_code == 307
    assert r.headers.get("location", "") == "/viewer/sites/garage"


@pytest.mark.parametrize("name", ["base", "stl_renderer", "readiness", "nope"])
def test_a_part_name_from_a_url_is_never_an_import_path(name):
    """GET /parts/stl_renderer imported that module and answered 500."""
    assert TestClient(app).get(f"/parts/{name}").status_code == 404


def test_a_nested_part_is_found_by_the_name_the_listing_gives_it():
    client = TestClient(app)
    listed = {part["name"] for part in client.get("/parts").json()}
    assert "rc.snowplow" in listed
    assert client.get("/parts/rc.snowplow/scad").status_code == 200


# POST /parts/{name}/stl/generate goes through build_stl. calibration_cube's STL
# is pointed at a temp file, so nothing here writes into parts/.

UNIT_CUBE = (
    "v 0 0 0\nv 1 0 0\nv 1 1 0\nv 0 1 0\nv 0 0 1\nv 1 0 1\nv 1 1 1\nv 0 1 1\n"
    "f 1 2 3 4\nf 5 6 7 8\nf 1 2 6 5\nf 2 3 7 6\nf 3 4 8 7\nf 4 1 5 8\n"
)


class _OpenSCADIsHere:
    is_available = True


@pytest.fixture
def cube_stl(tmp_path, monkeypatch):
    """Where calibration_cube builds to in these tests; OpenSCAD reported present."""
    stl = tmp_path / "calibration_cube.stl"
    monkeypatch.setattr(type(CUBE), "get_stl_output_path", lambda self: stl)
    monkeypatch.setattr(api, "get_stl_renderer", lambda: _OpenSCADIsHere())
    return stl


@pytest.mark.parametrize("params", [{"sise": 12}, {"size": 1}], ids=["unknown", "out of range"])
def test_generate_refuses_parameters_the_part_does_not_take(params):
    r = TestClient(app).post("/parts/calibration_cube/stl/generate", json={"params": params})
    assert r.status_code == 422
    assert next(iter(params)) in r.json()["detail"]


def test_generate_keeps_a_fresh_stl(cube_stl):
    meshes.write_stl(meshes.read_obj(UNIT_CUBE), cube_stl)
    r = TestClient(app).post("/parts/calibration_cube/stl/generate")
    assert r.status_code == 200, r.text
    assert r.json()["regenerated"] is False
    assert r.json()["bounds"] is not None


def test_generate_is_503_for_a_part_that_cannot_be_built_here(cube_stl, monkeypatch):
    monkeypatch.setattr(
        type(CUBE), "can_generate_stl", lambda self, openscad=None: (False, "needs 2024.x")
    )
    r = TestClient(app).post("/parts/calibration_cube/stl/generate?force=true")
    assert r.status_code == 503
    assert "needs 2024.x" in r.json()["detail"]
    assert not cube_stl.exists()
