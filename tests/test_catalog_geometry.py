"""A catalog leaf refers to a part instead of describing its own shape.

Its geometry is the part's STL, imported. The viewer's canvas (the node-STL
route), its contents list and its generated-OpenSCAD panel all depend on it.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from rendered_parts import built_stl_fixture  # noqa: F401

from apothecary import meshes
from apothecary.api import app
from apothecary.example_parts_library import create_parts_library_site
from apothecary.hierarchy import Assembly, part_stl_path
from apothecary.primitives import Import
from apothecary.projects.parts.base import BasePart
from apothecary.projects.parts.calibration_cube import DEFAULT as CUBE
from apothecary.projects.parts.datum_core import DEFAULT as CORE

client = TestClient(app)

UNIT_CUBE = (
    "v 0 0 0\nv 1 0 0\nv 1 1 0\nv 0 1 0\nv 0 0 1\nv 1 0 1\nv 1 1 1\nv 0 1 1\n"
    "f 1 2 3 4\nf 5 6 7 8\nf 1 2 6 5\nf 2 3 7 6\nf 3 4 8 7\nf 4 1 5 8\n"
)


def _build_to(mp: pytest.MonkeyPatch, part: BasePart, stl) -> None:
    """Make ``stl`` the part's output path, for this part's class alone."""
    assert type(part) is not BasePart, "patching BasePart would move every part"
    mp.setattr(type(part), "get_stl_output_path", lambda self: stl)


@pytest.fixture(scope="module", autouse=True)
def datum_core_stl(tmp_path_factory):
    """These tests read datum_core's STL, a build artifact a fresh checkout does
    not have. A cube in a temp directory stands in for it; nothing is built into
    the repository. Yields the path a render imports."""
    stl = tmp_path_factory.mktemp("catalog") / "datum_core.stl"
    meshes.write_stl(meshes.read_obj(UNIT_CUBE), stl)
    with pytest.MonkeyPatch.context() as mp:
        _build_to(mp, CORE, stl)
        yield stl.as_posix()


class TestImportPrimitive:
    def test_renders_an_openscad_import(self):
        assert Import(file="parts/datum_core/datum_core.stl").render() == (
            'import("parts/datum_core/datum_core.stl", convexity=10);'
        )

    def test_windows_separators_become_posix(self):
        # The same scene has to render identically on either platform.
        assert '"a/b/c.stl"' in Import(file=r"a\b\c.stl").render()

    def test_comment_precedes_the_call(self):
        rendered = Import(file="x.stl", comment="Part: x").render()
        assert rendered.splitlines()[0] == "// Part: x"


class TestPartStlPath:
    def test_the_part_says_where_its_stl_is(self, datum_core_stl):
        # Not the SCAD's own name with .stl: gridfinity's source is in a submodule
        # and its STL is not.
        assert part_stl_path("datum_core") == datum_core_stl

    def test_inside_the_repository_the_path_is_relative(self, monkeypatch):
        # Never absolute: generated SCAD is shown to people and an absolute
        # path there leaks the local layout of whoever generated it. Any file
        # under the root that exists stands in for a built STL.
        _build_to(monkeypatch, CORE, CORE.source_file)
        assert part_stl_path("datum_core") == "parts/datum_core/datum_core.scad"

    def test_unregistered_part_is_none(self):
        assert part_stl_path("no-such-part") is None


class TestCatalogLeafCompiles:
    def test_part_ref_leaf_imports_its_geometry(self, datum_core_stl):
        leaf = Assembly(name="datum_core", role="part", part_ref="datum_core")
        rendered = leaf.to_scad_object().render()
        assert f'import("{datum_core_stl}"' in rendered

    def test_missing_stl_names_the_command_that_fixes_it(self):
        """Asking for one node's geometry is a direct request, so it fails."""
        leaf = Assembly(name="ghost", role="part", part_ref="no-such-part")
        with pytest.raises(ValueError, match="apothecary parts generate-stl no-such-part"):
            leaf.to_scad_object(strict=True)

    def test_an_unbuilt_part_says_so_instead_of_failing(self):
        """STLs are build artifacts, so a catalog routinely holds a part nobody
        has built yet. One of those must not take every other part down with it.
        """
        leaf = Assembly(name="ghost", role="part", part_ref="no-such-part")
        rendered = leaf.to_scad_object().render()
        assert "apothecary parts generate-stl no-such-part" in rendered

    def test_a_leaf_with_neither_still_reports_the_original_error(self):
        bare = Assembly(name="bare", role="part")
        with pytest.raises(ValueError, match="has no base, additions, or children"):
            bare.to_scad_object()

    def test_the_whole_catalog_renders(self, datum_core_stl):
        # A site made entirely of part_ref leaves.
        scad = create_parts_library_site().render()
        assert datum_core_stl in scad

    def test_the_catalog_survives_a_part_nobody_has_built(self):
        from apothecary.hierarchy import Site

        site = Site("catalog", structures=[Assembly(name="ghost", part_ref="no-such-part")])
        assert "generate-stl no-such-part" in site.render()


class TestViewerSurfaces:
    def test_layout_returns_generated_scad(self, datum_core_stl):
        """The panel says 'Load a site to see generated OpenSCAD' until this
        response carries a `scad` key, so an error here reads as a blank panel.
        """
        site = client.get("/sites/parts_library").json()
        positions = {s["name"]: s["position"] for s in site["structures"]}
        response = client.post("/sites/parts_library/layout", json={"positions": positions})
        assert response.status_code == 200, response.text

        body = response.json()
        assert body["is_valid"] is True
        assert datum_core_stl in body["scad"]

    @pytest.mark.slow
    def test_node_stl_renders_a_catalog_leaf(self, built_stl, monkeypatch):
        _build_to(monkeypatch, CORE, built_stl(CORE))
        response = client.get("/sites/parts_library/nodes/datum_core/stl")
        assert response.status_code == 200, response.text
        assert len(response.content) > 1000

    @pytest.mark.slow
    def test_node_render_leaves_no_scratch_behind(self, built_stl, monkeypatch, tmp_path):
        """The scratch SCAD lives in the cache beside its STL, and goes once rendered."""
        monkeypatch.setenv("APOTHECARY_CACHE_DIR", str(tmp_path))
        _build_to(monkeypatch, CUBE, built_stl(CUBE))
        assert client.get("/sites/parts_library/nodes/calibration_cube/stl").status_code == 200
        assert list((tmp_path / "node_stl").glob("*.stl"))
        assert list((tmp_path / "node_stl").glob("*.scad")) == []


class TestSitePayloadCarriesScad:
    """The viewer's code panel reads `scad` off an ordinary site read."""

    def test_get_site_includes_generated_scad(self, datum_core_stl):
        body = client.get("/sites/parts_library").json()
        assert datum_core_stl in body["scad"]

    def test_layout_still_includes_it(self, datum_core_stl):
        site = client.get("/sites/parts_library").json()
        positions = {s["name"]: s["position"] for s in site["structures"]}
        body = client.post("/sites/parts_library/layout", json={"positions": positions}).json()
        assert datum_core_stl in body["scad"]

    def test_a_site_that_cannot_compile_reports_it_rather_than_500ing(self, monkeypatch):
        """One uncompilable node must not take the whole page down with it."""
        import apothecary.api as api

        class Boom:
            name = "boom"
            children: list = []

            def render(self):
                raise ValueError("nope")

        class Report:
            violations: list = []
            is_valid = True

        monkeypatch.setattr(api, "_assembly_tree", lambda site: {})
        payload = api._site_payload(Boom(), Report())
        assert payload["scad"].startswith("// This site has no generated OpenSCAD")


class TestHull:
    """A rounded rectangular prism is what an enclosure shell actually is, and
    a cube would misreport the corner radius everything is fitted around.
    """

    def test_renders_an_openscad_hull(self):
        from apothecary import Hull
        from apothecary.primitives import Cylinder

        rendered = Hull(children=[Cylinder(h=2, r=3), Cylinder(h=2, r=3)]).render()
        assert rendered.startswith("hull() {")
        assert rendered.count("cylinder(") == 2

    def test_carries_its_comment(self):
        from apothecary import Hull

        assert Hull(children=[], comment="Shell").render().splitlines()[0] == "// Shell"

    def test_is_part_of_the_public_surface(self):
        """Its siblings are exported; a boolean nobody can import is a private
        one wearing a public name.
        """
        import apothecary

        assert "Hull" in apothecary.__all__
        assert "Import" in apothecary.__all__
