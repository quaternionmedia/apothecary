"""three.js is vendored under apothecary/static/vendor/three/ (its README says how
to update it) and served from this origin, so the viewer needs no network and no
install step. When the copy is missing, the page says so instead of rendering nothing.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from apothecary.api import THREE_IS_VENDORED, app

client = TestClient(app)

VIEWER_URL = "/viewer/sites/parts_library"


class TestVendoredLibraryIsServed:
    def test_three_module_is_reachable(self):
        if not THREE_IS_VENDORED:
            # The banner case is covered below; nothing to serve here.
            return
        response = client.get("/static/vendor/three/three.module.js")
        assert response.status_code == 200
        assert len(response.content) > 100_000

    def test_the_addons_the_viewer_imports_are_reachable(self):
        if not THREE_IS_VENDORED:
            return
        for addon in (
            "controls/OrbitControls.js",
            "controls/TransformControls.js",
            "loaders/STLLoader.js",
        ):
            response = client.get(f"/static/vendor/three/addons/{addon}")
            assert response.status_code == 200, addon

    def test_importmap_targets_what_is_actually_served(self):
        """The specifier and the route have to agree, or the page dies silently."""
        page = client.get(VIEWER_URL).text
        assert '"three": "/static/vendor/three/three.module.js"' in page
        assert '"three/addons/": "/static/vendor/three/addons/"' in page


class TestMissingLibraryIsAnnounced:
    def test_a_missing_install_renders_a_banner(self):
        """Silence was the original defect; absence has to be visible."""
        from apothecary.viewer import render_fractal_viewer_page

        page = render_fractal_viewer_page(
            ["parts_library"], "http://testserver", "parts_library", "", three_is_vendored=False
        )
        assert "The 3D library is missing" in page

    def test_a_present_install_renders_no_banner(self):
        from apothecary.viewer import render_fractal_viewer_page

        page = render_fractal_viewer_page(
            ["parts_library"], "http://testserver", "parts_library", "", three_is_vendored=True
        )
        assert "The 3D library is missing" not in page


class TestThePageEscapesWhatItIsGiven:
    def test_a_name_is_text_in_the_markup_and_a_string_in_the_script(self):
        from apothecary.viewer import render_fractal_viewer_page

        name = 'a"<b>&</script>'
        page = render_fractal_viewer_page([name], "http://testserver", name, name)
        assert name not in page
        assert '<option value="a&#34;&lt;b&gt;&amp;&lt;/script&gt;" selected>' in page
        assert r'const DEFAULT_SITE = "a\"\u003cb\u003e\u0026\u003c/script\u003e";' in page

    def test_no_sites_leaves_the_select_disabled(self):
        from apothecary.viewer import render_fractal_viewer_page

        page = render_fractal_viewer_page([], "http://testserver")
        assert '<select id="site-select" disabled>' in page
        assert "No sites found" in page


class TestTheLibraryIsCheckedIn:
    def test_a_fresh_clone_has_three_with_no_install(self):
        from apothecary.api import THREE_DIR

        assert (THREE_DIR / "three.module.js").is_file()
        assert (THREE_DIR / "LICENSE").is_file()


class TestCiCollectsTheWalkthrough:
    """pytest ignores `testpaths` once it is given a path, so CI names walkthrough/ itself."""

    def test_ci_names_it_too(self):
        from apothecary.projects.parts.skeleton import ROOT

        workflow = (ROOT / ".github" / "workflows" / "pytest.yml").read_text(encoding="utf-8")
        assert "pytest walkthrough" in workflow
