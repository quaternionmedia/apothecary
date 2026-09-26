"""A catalog leaf refers to a part instead of describing its own shape.

`to_scad_object()` knew only how to build geometry from `base`, `additions`
and `children`, so every node in the parts library raised. One missing case
emptied three surfaces of the viewer at once: the canvas got 422 from the
node-STL route, the contents list had no meshes to show, and the generated
OpenSCAD panel kept its placeholder because the layout route 500'd before it
could return any.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from apothecary.api import app
from apothecary.example_parts_library import create_parts_library_site
from apothecary.hierarchy import Assembly, part_stl_path
from apothecary.primitives import Import
from apothecary.projects.parts.stl_renderer import get_renderer

client = TestClient(app)


@pytest.fixture(scope="module", autouse=True)
def datum_core_is_built():
    """These tests read a part's STL, and an STL is a build artifact.

    A fresh checkout has none -- they are gitignored -- so assuming a populated
    working tree is what made this module pass on a developer machine and fail
    in CI. Build the one part it needs, once.
    """
    from apothecary.projects.parts.skeleton import ROOT

    stl = ROOT / "parts" / "datum_core" / "datum_core.stl"
    if stl.exists():
        return
    renderer = get_renderer()
    if not renderer.is_available:
        pytest.skip("OpenSCAD not installed; cannot build the STL these tests read")
    result = renderer.render_stl(stl.with_suffix(".scad"), stl, timeout=300)
    assert result.success, result.error_message


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
    def test_registered_part_resolves_repository_relative(self):
        # Never absolute: generated SCAD is shown to people and an absolute
        # path there leaks the local layout of whoever generated it.
        assert part_stl_path("datum_core") == "parts/datum_core/datum_core.stl"

    def test_unregistered_part_is_none(self):
        assert part_stl_path("no-such-part") is None


class TestCatalogLeafCompiles:
    def test_part_ref_leaf_imports_its_geometry(self):
        leaf = Assembly(name="datum_core", role="part", part_ref="datum_core")
        rendered = leaf.to_scad_object().render()
        assert 'import("parts/datum_core/datum_core.stl"' in rendered

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

    def test_the_whole_catalog_renders(self):
        # This is the one that was failing: a site made entirely of part_ref
        # leaves could not render at all.
        scad = create_parts_library_site().render()
        assert "parts/datum_core/datum_core.stl" in scad

    def test_the_catalog_survives_a_part_nobody_has_built(self):
        from apothecary.hierarchy import Site

        site = Site("catalog", structures=[Assembly(name="ghost", part_ref="no-such-part")])
        assert "generate-stl no-such-part" in site.render()


class TestViewerSurfaces:
    def test_layout_returns_generated_scad(self):
        """The panel says 'Load a site to see generated OpenSCAD' until this
        response carries a `scad` key, so an error here reads as a blank panel.
        """
        site = client.get("/sites/parts_library").json()
        positions = {s["name"]: s["position"] for s in site["structures"]}
        response = client.post("/sites/parts_library/layout", json={"positions": positions})
        assert response.status_code == 200, response.text

        body = response.json()
        assert body["is_valid"] is True
        assert "parts/datum_core/datum_core.stl" in body["scad"]

    @pytest.mark.slow
    def test_node_stl_renders_a_catalog_leaf(self):
        if not get_renderer().is_available:
            pytest.skip("OpenSCAD not installed")
        response = client.get("/sites/parts_library/nodes/datum_core/stl")
        assert response.status_code == 200, response.text
        assert len(response.content) > 1000

    @pytest.mark.slow
    def test_node_render_leaves_no_scratch_behind(self):
        if not get_renderer().is_available:
            pytest.skip("OpenSCAD not installed")
        from apothecary.projects.parts.skeleton import ROOT

        client.get("/sites/parts_library/nodes/calibration_cube/stl")
        assert list(ROOT.glob(".node-stl-*.scad")) == []


class TestSitePayloadCarriesScad:
    """The viewer's code panel reads `scad` off an ordinary site read."""

    def test_get_site_includes_generated_scad(self):
        body = client.get("/sites/parts_library").json()
        assert "parts/datum_core/datum_core.stl" in body["scad"]

    def test_layout_still_includes_it(self):
        site = client.get("/sites/parts_library").json()
        positions = {s["name"]: s["position"] for s in site["structures"]}
        body = client.post("/sites/parts_library/layout", json={"positions": positions}).json()
        assert "parts/datum_core/datum_core.stl" in body["scad"]

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
