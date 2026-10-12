"""Lighter and faster (docs/plans/part-iteration-2026-10-12.md, item 6): binary STLs
in the variant cache, variant URLs answered immutable, responses compressed, the
cache keyed on what OpenSCAD compiles so a comment-only edit renders nothing, a
render's answer naming the editor version it was for, the edited draft served for
Download, the snowplow's generated SCAD for the parameters applied, and whether
this OpenSCAD can build the part said up front.

Every OpenSCAD here is scripted (tests/scripted_openscad.py) and every part is
the test's own, but for the library's parts the routes are asked about.
"""

from __future__ import annotations

import struct
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from scripted_openscad import calls, renders, scripted_openscad, stl_names

from apothecary import api
from apothecary.api import app
from apothecary.meshes import read_stl
from apothecary.projects.parts import stl_renderer, variants
from apothecary.projects.parts.base import BasePart
from apothecary.projects.parts.drafts import draft_digest
from apothecary.projects.parts.stl_renderer import binary_stl, is_binary_stl
from apothecary.projects.parts.variants import make_variant, variant_paths

SCAD = """// A block.
width = 34; // [10:100]
w = 1; WARN
cube([width, 20, 3]);
"""
# The same, said otherwise in its comments only.
RECOMMENTED = """// A block, which is a cube.
// Its width is a parameter.
width = 34; // [10:100] the width
w = 1; WARN
cube([width, 20, 3]); /* the body */
"""


@pytest.fixture
def openscad(tmp_path, monkeypatch):
    monkeypatch.setenv("APOTHECARY_CACHE_DIR", str(tmp_path / "cache"))

    def install(version: str = "2026.09.27", lists: bool = True) -> Path:
        exe = scripted_openscad(tmp_path / "bin" / version / "openscad", version, lists)
        monkeypatch.setenv("APOTHECARY_OPENSCAD", str(exe))
        monkeypatch.setattr(stl_renderer, "_renderer", None)
        return exe

    return install


@pytest.fixture
def block(tmp_path, monkeypatch):
    scad = tmp_path / "parts" / "block" / "block.scad"
    scad.parent.mkdir(parents=True)
    scad.write_text(SCAD)
    part = BasePart(name="block", source_file=scad)
    monkeypatch.setattr(BasePart, "get_stl_output_path", lambda self: tmp_path / "block.stl")
    real = api._load_part_wrapper
    monkeypatch.setattr(
        api, "_load_part_wrapper", lambda name: part if name == "block" else real(name)
    )
    return part


def _check(client, scad, params=None, **extra):
    return client.post(
        "/parts/block/draft/check", json={"scad": scad, "params": params or {}, **extra}
    )


def _render(client, scad, params=None, **extra):
    return client.post(
        "/parts/block/draft/render", json={"scad": scad, "params": params or {}, **extra}
    )


# --- binary STLs ---------------------------------------------------------------------


class TestBinarySTLs:
    def test_the_cache_keeps_a_binary_stl_whatever_openscad_wrote(self, openscad, block):
        openscad()
        made = make_variant(block, {"width": 50})
        stl = made.stl_path.read_bytes()
        assert is_binary_stl(made.stl_path) and len(read_stl(stl)) == 1
        assert stl_names(stl).startswith(draft_digest(SCAD)) and '"width=50"' in stl_names(stl)

    def test_an_openscad_that_writes_binary_is_asked_to(self, openscad, block, monkeypatch):
        exe = openscad()
        monkeypatch.setattr(stl_renderer, "writes_binary_stl", lambda path: True)
        make_variant(block, {"width": 50})
        (render,) = [c for c in calls(exe) if c["format"] == "binstl"]
        assert render["args"][:3] == ["-o", render["args"][1], "--export-format=binstl"]

    def test_ascii_is_made_binary_in_place_its_name_kept(self, tmp_path):
        stl = tmp_path / "a.stl"
        stl.write_text(
            "solid hello\nfacet normal 0 0 1\nouter loop\nvertex 0 0 0\nvertex 1 0 0\n"
            "vertex 0 1 0\nendloop\nendfacet\nendsolid hello\n"
        )
        assert binary_stl(stl) and is_binary_stl(stl)
        data = stl.read_bytes()
        assert data[:5] == b"hello" and struct.unpack_from("<I", data, 80)[0] == 1
        assert binary_stl(stl) is False  # already binary: left as it is


# --- what the browser keeps, and compression ------------------------------------------


class TestServedLighter:
    def test_a_variants_stl_and_draft_are_immutable(self, openscad, block):
        openscad()
        client = TestClient(app)
        body = _render(client, SCAD + "// edited\n", {"width": 50}).json()
        stl = client.get(body["stl_url"])
        assert stl.headers["cache-control"] == "public, max-age=31536000, immutable"
        scad = client.get(f"/parts/block/variants/{body['variant']}/scad")
        assert scad.headers["cache-control"] == "public, max-age=31536000, immutable"
        # The part's own STL changes under its URL, so it is not.
        assert "immutable" not in client.get("/parts/block/stl").headers.get("cache-control", "")

    def test_responses_are_compressed_for_a_client_that_takes_gzip(self):
        client = TestClient(app)
        js = client.get("/static/vendor/three/three.module.js", headers={"Accept-Encoding": "gzip"})
        assert js.status_code == 200 and js.headers["content-encoding"] == "gzip"
        listing = client.get("/parts", headers={"Accept-Encoding": "gzip"})
        assert listing.headers["content-encoding"] == "gzip" and listing.json()
        plain = client.get("/parts", headers={"Accept-Encoding": "identity"})
        assert "content-encoding" not in plain.headers

    def test_locality_stays_outermost(self):
        """GZip is inside LocalOnly: a request from elsewhere is still refused first."""
        from apothecary.stays_local import LocalOnly

        assert app.user_middleware[0].cls is LocalOnly


# --- keyed on what OpenSCAD compiles --------------------------------------------------


class TestACommentOnlyEdit:
    def test_after_its_check_it_draws_at_once_with_its_own_lines(self, openscad, block):
        exe = openscad()
        client = TestClient(app)
        assert _check(client, SCAD + "// first\n").json()["valid"]
        first = _render(client, SCAD + "// first\n").json()
        assert first["regenerated"] and len(renders(exe)) == 1
        checked = _check(client, RECOMMENTED).json()
        assert checked["valid"] and [m["line"] for m in checked["messages"]] == [4]
        again = _render(client, RECOMMENTED).json()
        assert again["regenerated"] is False and len(renders(exe)) == 1
        assert again["compiled_from"] == first["variant"] and again["variant"] != first["variant"]
        assert "nothing to render" in again["message"]
        # Its own key, its own text, its own lines; the same mesh.
        assert [m["line"] for m in again["messages"]] == [4]
        assert [m["line"] for m in first["messages"]] == [3]
        assert client.get(again["stl_url"]).content == client.get(first["stl_url"]).content
        assert client.get(f"/parts/block/variants/{again['variant']}/scad").text == RECOMMENTED
        record = client.get(f"/parts/block/variants/{again['variant']}").json()
        assert record["compiled_from"] == first["variant"]

    def test_other_values_compile_otherwise_and_render(self, openscad, block):
        exe = openscad()
        client = TestClient(app)
        _check(client, SCAD, {"width": 40})
        _render(client, SCAD, {"width": 40})
        _check(client, RECOMMENTED, {"width": 41})
        assert _render(client, RECOMMENTED, {"width": 41}).json()["regenerated"]
        assert len(renders(exe)) == 2

    def test_force_renders_it_whatever_it_compiles_to(self, openscad, block):
        exe = openscad()
        client = TestClient(app)
        _check(client, SCAD + "// a\n")
        _render(client, SCAD + "// a\n")
        _check(client, SCAD + "// b\n")
        r = client.post(
            "/parts/block/draft/render?force=true", json={"scad": SCAD + "// b\n", "params": {}}
        )
        assert r.json()["regenerated"] and len(renders(exe)) == 2

    def test_with_manifold_and_no_check_it_renders_rather_than_compile_first(self, openscad, block):
        """A snapshot's compile costs about what its render does: none is made here."""
        exe = openscad()
        client = TestClient(app)
        _render(client, SCAD + "// a\n")
        assert _render(client, SCAD + "// b\n").json()["regenerated"]
        assert [c for c in calls(exe) if c["format"] == "csg"] == []

    def test_with_cgal_it_compiles_first_for_it_costs_a_fraction_of_a_render(self, openscad, block):
        exe = openscad("2021.01", lists=False)
        client = TestClient(app)
        first = _render(client, SCAD + "// a\n").json()
        again = _render(client, SCAD + "// b\n").json()
        assert again["regenerated"] is False and again["compiled_from"] == first["variant"]
        assert len(renders(exe)) == 1
        assert len([c for c in calls(exe) if c["format"] == "csg"]) == 2

    def test_the_part_built_by_python_is_keyed_on_its_text_alone(self, openscad):
        from apothecary.projects.parts.rc_snowplow import DEFAULT as SNOWPLOW

        assert variants.compiled_for(SNOWPLOW, {}, stl_renderer.get_renderer(), None) is None

    def test_what_compiled_to_a_variant_the_cache_let_go_is_let_go(self, openscad, block):
        openscad("2021.01", lists=False)
        made = make_variant(block, draft=SCAD + "// a\n")
        folder = made.stl_path.parent
        assert len(list((folder / "compiled").iterdir())) == 1
        for suffix in (".stl", ".json", ".scad"):
            made.stl_path.with_suffix(suffix).unlink(missing_ok=True)
        variants.trim_variants(folder)
        assert list((folder / "compiled").iterdir()) == []
        again = make_variant(block, draft=SCAD + "// b\n")
        assert again.rendered and again.compiled_from is None


# --- the editor's version ---------------------------------------------------------------


class TestTheEditorVersion:
    def test_each_answer_hands_it_back_as_it_came(self, openscad, block):
        openscad()
        client = TestClient(app)
        assert _check(client, SCAD, editor_version=7).json()["editor_version"] == 7
        assert _render(client, SCAD + "// x\n", editor_version="v8").json()["editor_version"] == (
            "v8"
        )
        failed = _render(client, SCAD + "assert(false);\n", editor_version=9)
        assert failed.status_code == 422 and failed.json()["detail"]["editor_version"] == 9
        generated = client.post(
            "/parts/block/stl/generate", json={"params": {}, "editor_version": 10}
        ).json()
        assert generated["editor_version"] == 10
        assert _render(client, SCAD + "// y\n").json()["editor_version"] is None

    def test_a_token_too_long_is_refused(self, openscad, block):
        openscad()
        assert _check(TestClient(app), SCAD, editor_version="x" * 65).status_code == 422


# --- Download, and the generated SCAD ---------------------------------------------------


class TestDownload:
    def test_the_draft_is_handed_back_as_the_parts_scad_file(self, openscad, block):
        r = TestClient(app).post("/parts/block/draft/scad", json={"scad": RECOMMENTED})
        assert r.status_code == 200 and r.text == RECOMMENTED
        assert r.headers["content-disposition"] == 'attachment; filename="block.scad"'
        assert r.headers["x-part-draft"] == draft_digest(RECOMMENTED)
        assert block.source_file.read_text() == SCAD

    def test_a_rendered_drafts_text_downloads_from_its_variant(self, openscad, block):
        openscad()
        client = TestClient(app)
        key = _render(client, RECOMMENTED).json()["variant"]
        r = client.get(f"/parts/block/variants/{key}/scad?download=true")
        assert r.text == RECOMMENTED and "attachment" in r.headers["content-disposition"]

    def test_a_part_built_by_python_has_no_draft_to_download(self):
        r = TestClient(app).post("/parts/rc.snowplow/draft/scad", json={"scad": "cube(1);"})
        assert r.status_code == 403


class TestTheSCADOfAVariant:
    def test_the_snowplows_is_generated_for_the_parameters_applied(self, tmp_path, monkeypatch):
        from apothecary.projects.parts.rc_snowplow import DEFAULT as SNOWPLOW
        from apothecary.projects.parts.stl_renderer import geometry_scad

        monkeypatch.setenv("APOTHECARY_CACHE_DIR", str(tmp_path / "cache"))
        key = "0123456789abcdef01234567"
        stl, record = variant_paths(SNOWPLOW, key)
        stl.parent.mkdir(parents=True)
        stl.write_bytes(b"\0" * 84)
        record.write_text('{"params": {"blade_width": 80.0}}')
        r = TestClient(app).get(f"/parts/rc.snowplow/scad?variant={key}")
        assert r.status_code == 200 and r.headers["x-part-scad"] == "generated"
        wider = geometry_scad(SNOWPLOW, SNOWPLOW.validate_overrides({"blade_width": 80.0}))
        assert r.text == wider and r.text != geometry_scad(SNOWPLOW, {})
        assert r.headers["x-part-variant"] == key
        missing = TestClient(app).get("/parts/rc.snowplow/scad?variant=" + "f" * 24)
        assert missing.status_code == 404

    def test_an_editable_parts_is_its_draft_or_its_own(self, openscad, block):
        openscad()
        client = TestClient(app)
        drafted = _render(client, RECOMMENTED).json()["variant"]
        r = client.get(f"/parts/block/scad?variant={drafted}")
        assert (r.text, r.headers["x-part-scad"]) == (RECOMMENTED, "draft")
        # Apply's values are written into the part's text: that is the variant's SCAD.
        applied = client.post("/parts/block/stl/generate", json={"params": {"width": 50}}).json()
        r = client.get(f"/parts/block/scad?variant={applied['variant']}")
        written = SCAD.replace("width = 34;", "width = 50;")
        assert (r.text, r.headers["x-part-scad"]) == (written, "draft")
        own = client.post("/parts/block/stl/generate", json={"params": {}}).json()
        r = client.get(f"/parts/block/scad?variant={own['variant']}")
        assert (r.text, r.headers["x-part-scad"]) == (SCAD, "source")


# --- whether this OpenSCAD can build it ---------------------------------------------------


class TestCanItBeBuiltHere:
    def test_gridfinity_on_2021_01_says_no_up_front(self, openscad, monkeypatch):
        openscad("2021.01", lists=False)
        monkeypatch.setattr(
            stl_renderer, "_openscad_candidates", lambda: [stl_renderer.openscad_override()]
        )
        client = TestClient(app)
        params = client.get("/parts/gridfinity/params").json()
        assert params["can_build"] is False and "2021.08.24" in params["build_note"]
        state = client.get("/parts/gridfinity/state").json()
        assert state["can_build"] is False and state["build_note"] == params["build_note"]

    def test_a_snapshot_can(self, openscad):
        openscad()
        client = TestClient(app)
        params = client.get("/parts/gridfinity/params").json()
        assert params["can_build"] is True and params["build_note"] is None
        assert client.get("/parts/calibration_cube/state").json()["can_build"] is True
