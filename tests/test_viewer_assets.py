"""The viewer's 3D library is served from this origin, not a CDN.

Loading three.js from jsdelivr meant the page worked only for a browser that
could reach jsdelivr. When it could not -- offline, an ad blocker, a corporate
proxy -- the module script never executed, so the canvas, the contents list and
the code panel came up empty *together*, while the status line still read
"Loading site..." and the validity chip still read "Layout valid" because both
are static markup. An inert page was indistinguishable from a working one.

The house-stack record requires frontend dependencies to be vendored and never
CDN-loaded, and this is the failure it exists to prevent.
"""

from __future__ import annotations

import re

from fastapi.testclient import TestClient

from apothecary.api import THREE_IS_VENDORED, app

client = TestClient(app)

VIEWER_URL = "/viewer/sites/parts_library"


class TestNoExternalOrigins:
    def test_the_page_names_no_cdn(self):
        page = client.get(VIEWER_URL).text
        assert "jsdelivr" not in page
        assert "unpkg" not in page

    def test_every_module_specifier_is_same_origin(self):
        page = client.get(VIEWER_URL).text
        importmap = re.search(r'<script type="importmap">(.*?)</script>', page, re.S)
        assert importmap, "no importmap in the viewer page"
        for url in re.findall(r'"(https?://[^"]+)"', importmap.group(1)):
            raise AssertionError(f"importmap reaches off-origin: {url}")

    def test_no_script_tag_points_off_origin(self):
        page = client.get(VIEWER_URL).text
        assert not re.search(r'<script[^>]+src="https?://', page)


class TestVendoredLibraryIsServed:
    def test_three_module_is_reachable(self):
        if not THREE_IS_VENDORED:
            # The banner case is covered below; nothing to serve here.
            return
        response = client.get("/vendor/three/build/three.module.js")
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
            response = client.get(f"/vendor/three/examples/jsm/{addon}")
            assert response.status_code == 200, addon

    def test_importmap_targets_what_is_actually_served(self):
        """The specifier and the route have to agree, or the page dies silently."""
        page = client.get(VIEWER_URL).text
        assert '"three": "/vendor/three/build/three.module.js"' in page
        assert '"three/addons/": "/vendor/three/examples/jsm/"' in page


class TestMissingLibraryIsAnnounced:
    def test_a_missing_install_renders_a_banner(self):
        """Silence was the original defect; absence has to be visible."""
        from apothecary.viewer import render_fractal_viewer_page

        page = render_fractal_viewer_page(
            ["parts_library"], "http://testserver", "parts_library", "", three_is_vendored=False
        )
        assert "The 3D library is not installed" in page

    def test_a_present_install_renders_no_banner(self):
        from apothecary.viewer import render_fractal_viewer_page

        page = render_fractal_viewer_page(
            ["parts_library"], "http://testserver", "parts_library", "", three_is_vendored=True
        )
        assert "The 3D library is not installed" not in page
