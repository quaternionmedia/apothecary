"""
End-to-end tests for the Apothecary fractal zoom viewer.

Covers the unified viewer that absorbed the former standalone parts browser
and the former Site/Structure hierarchy viewer -- see
apothecary/api.py's site_viewer handler and templates/fractal_viewer.html.j2.
"""

import pytest
from playwright.sync_api import Page, expect


@pytest.mark.e2e
def test_viewer_page_loads(page: Page, base_url: str):
    """Test that the fractal viewer page loads successfully."""
    page.goto(f"{base_url}/viewer/sites/garage")

    expect(page).to_have_title("Apothecary Fractal Viewer")
    heading = page.locator(".toolbar h1")
    expect(heading).to_contain_text("Apothecary")


@pytest.mark.e2e
def test_viewer_has_site_dropdown(page: Page, base_url: str):
    """Test that the site dropdown lists both registered sites."""
    page.goto(f"{base_url}/viewer/sites/garage")

    select = page.locator("#site-select")
    expect(select).to_be_visible()
    options = select.locator("option")
    assert options.count() >= 2, "Expected at least garage and parts_library"


@pytest.mark.e2e
def test_viewer_has_canvas(page: Page, base_url: str):
    """Test that the 3D viewer canvas exists and renders with real dimensions."""
    page.goto(f"{base_url}/viewer/sites/garage")

    canvas = page.locator("#viewer-canvas")
    expect(canvas).to_be_visible()
    box = canvas.bounding_box()
    assert box is not None
    assert box["width"] > 100
    assert box["height"] > 100


@pytest.mark.e2e
def test_viewer_has_code_panel(page: Page, base_url: str):
    """Test that the Generated OpenSCAD code panel exists."""
    page.goto(f"{base_url}/viewer/sites/garage")

    code_content = page.locator("#code-content")
    expect(code_content).to_be_visible()


@pytest.mark.e2e
def test_viewer_dark_theme(page: Page, base_url: str):
    """Test that the viewer uses dark theme."""
    page.goto(f"{base_url}/viewer/sites/garage")

    body = page.locator("body")
    bg_color = body.evaluate("el => getComputedStyle(el).backgroundColor")
    assert (
        "26" in bg_color or "1a" in bg_color.lower() or "rgb(26" in bg_color
    ), f"Expected dark background, got {bg_color}"


@pytest.mark.e2e
def test_viewer_shows_contents_for_the_loaded_site(page: Page, base_url: str):
    """Test that the garage site's top-level structures appear in Contents:
    the workbench and its printer fleet, plus the building shell, utility
    fixture stubs, storage, the CNC router stub, and the boards on the bench
    the firmware seam binds to (a devkit, the footpedal, an Uno, a Pi, a Teensy).
    """
    page.goto(f"{base_url}/viewer/sites/garage")
    page.wait_for_timeout(600)

    items = page.locator("#contents-list .contents-item")
    assert items.count() == 16
    contents = page.locator("#contents-list")
    for name in (
        "workbench",
        "printer_1",
        "printer_2",
        "printer_3",
        "garage_building",
        "lighting",
        "hvac",
        "electrical",
        "fluids",
        "storage_shelving",
        "cnc_router",
        "esp32_blink",
        "footpedal",
        "arduino_uno",
        "raspberry_pi_4",
        "teensy_40",
    ):
        expect(contents).to_contain_text(name)


@pytest.mark.e2e
def test_double_click_zooms_in_and_zoom_out_returns(page: Page, base_url: str):
    """Test the standardized zoom-in/zoom-out navigation controls."""
    page.goto(f"{base_url}/viewer/sites/garage")
    page.wait_for_timeout(600)

    printer_1 = page.locator("#contents-list .contents-item", has_text="printer_1")
    printer_1.dblclick()
    page.wait_for_timeout(300)

    # Zoomed into printer_1: its substructures now populate Contents, and the
    # breadcrumb reflects the new depth.
    expect(page.locator("#breadcrumb")).to_contain_text("printer_1")
    expect(page.locator("#contents-list")).to_contain_text("gantry_system")
    expect(page.locator("#zoom-out-btn")).to_be_enabled()

    page.locator("#zoom-out-btn").click()
    page.wait_for_timeout(300)

    expect(page.locator("#contents-list")).to_contain_text("workbench")
    expect(page.locator("#zoom-out-btn")).to_be_disabled()


@pytest.mark.e2e
def test_minimap_advances_with_zoom_depth(page: Page, base_url: str):
    """Test that the abstract minimap reflects the current zoom depth."""
    page.goto(f"{base_url}/viewer/sites/garage")
    page.wait_for_timeout(600)

    ticks = page.locator("#minimap .minimap-tick")
    assert ticks.count() >= 2  # at least root + one deeper level exists
    assert page.locator("#minimap .minimap-tick.filled").count() == 1

    page.locator("#contents-list .contents-item", has_text="printer_1").dblclick()
    page.wait_for_timeout(300)

    assert page.locator("#minimap .minimap-tick.filled").count() == 2


@pytest.mark.e2e
def test_selecting_a_parts_library_leaf_shows_the_absorbed_part_view(page: Page, base_url: str):
    """Test that zooming into the parts library shows real SCAD source --
    the old standalone part-viewer experience, now reached by navigation.
    """
    page.goto(f"{base_url}/viewer/sites/parts_library")
    page.wait_for_timeout(600)

    first_part = page.locator("#contents-list .contents-item").first
    first_part.click()
    page.wait_for_timeout(800)

    scad_content = page.locator("#part-scad-content")
    expect(scad_content).to_be_visible()
    expect(scad_content).not_to_have_text("Loading…")
    text = scad_content.text_content()
    assert len(text) > 0

    download_link = page.locator(".part-actions a")
    expect(download_link).to_be_visible()
    href = download_link.get_attribute("href")
    assert href is not None and "/scad" in href


@pytest.mark.e2e
def test_parts_api_returns_list(page: Page, base_url: str):
    """Test that the parts API endpoint returns a valid list."""
    response = page.request.get(f"{base_url}/parts")

    assert response.ok
    data = response.json()

    assert isinstance(data, list)
    assert len(data) > 0

    first_part = data[0]
    assert "name" in first_part
    assert "description" in first_part
    assert "source_file" in first_part


@pytest.mark.e2e
def test_parts_jscad_endpoint(page: Page, base_url: str):
    """Test that the JSCAD endpoint returns valid JavaScript."""
    response = page.request.get(f"{base_url}/parts")
    parts = response.json()

    if len(parts) > 0:
        part_name = parts[0]["name"]

        jscad_response = page.request.get(f"{base_url}/parts/{part_name}/jscad")

        assert jscad_response.ok
        content = jscad_response.text()

        assert "const jscad = require('@jscad/modeling')" in content
        assert "module.exports = { main }" in content
        assert "OpenSCAD source:" in content


@pytest.mark.e2e
def test_health_endpoint(page: Page, base_url: str):
    """Test the health check endpoint."""
    response = page.request.get(f"{base_url}/health")

    assert response.ok
    data = response.json()

    assert data["status"] == "healthy"
    assert "version" in data


@pytest.mark.e2e
def test_viewer_loads_each_part_jscad(page: Page, base_url: str):
    """Test that JSCAD endpoint works for every available part."""
    response = page.request.get(f"{base_url}/parts")
    parts = response.json()

    assert len(parts) > 0, "No parts available"

    for part in parts:
        part_name = part["name"]

        jscad_response = page.request.get(f"{base_url}/parts/{part_name}/jscad")
        assert (
            jscad_response.ok
        ), f"Part {part_name}: JSCAD endpoint returned {jscad_response.status}"

        content = jscad_response.text()
        assert len(content) > 0, f"Part {part_name}: Empty JSCAD response"
        assert "const main" in content, f"Part {part_name}: Missing main function"
        assert "module.exports" in content, f"Part {part_name}: Missing module.exports"


@pytest.mark.e2e
def test_viewer_loads_each_part_scad(page: Page, base_url: str):
    """Test that SCAD download works for every available part."""
    response = page.request.get(f"{base_url}/parts")
    parts = response.json()

    assert len(parts) > 0, "No parts available"

    for part in parts:
        part_name = part["name"]

        scad_response = page.request.get(f"{base_url}/parts/{part_name}/scad")
        assert scad_response.ok, f"Part {part_name}: SCAD endpoint returned {scad_response.status}"

        content = scad_response.text()
        assert len(content) > 0, f"Part {part_name}: Empty SCAD response"


@pytest.mark.e2e
def test_viewer_integrated_loads_without_critical_errors(page: Page, base_url: str):
    """Test that the fractal viewer loads without critical JavaScript errors."""
    console_errors = []
    page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)

    page.goto(f"{base_url}/viewer/sites/garage")

    # The viewer's own "Loaded" status, not networkidle: the device panel
    # rescans ports on a schedule, so the page is never idle for long.
    expect(page.locator("#status")).to_contain_text("Loaded", timeout=30000)
    page.wait_for_timeout(2000)

    critical_errors = [
        e
        for e in console_errors
        if not any(
            ignore in e.lower()
            for ignore in [
                "extension",
                "favicon",
                "chrome-extension",
            ]
        )
    ]

    assert len(critical_errors) == 0, f"Console errors found: {critical_errors}"


@pytest.mark.e2e
def test_focusing_a_leaf_renders_that_leaf(page: Page, base_url: str):
    """Zooming into a part shows the part.

    The viewer renders "the focus node's children", and a part is a leaf, so
    focusing one rendered an empty scene: no mesh, nothing in Contents, and no
    geometry request at all. The page still said "Loaded" and the static
    "Layout valid" chip still showed, which is what made it read as three
    separate faults instead of one.
    """
    requests = []
    page.on("request", lambda r: requests.append(r.url))

    page.goto(f"{base_url}/viewer/sites/parts_library?focus=datum_core")
    page.wait_for_timeout(3000)

    expect(page.locator("#contents-list")).to_contain_text("datum_core")
    assert any("/parts/datum_core/stl" in url for url in requests), (
        "focusing a part fetched no geometry for it"
    )


@pytest.mark.e2e
def test_code_panel_populates_without_an_edit(page: Page, base_url: str):
    """The generated OpenSCAD panel used to fill in only after a layout drag.

    `scad` rode on the layout response alone, so a site that had merely been
    loaded kept the "Load a site to see generated OpenSCAD" placeholder --
    indistinguishable from a viewer that had failed to load anything.
    """
    page.goto(f"{base_url}/viewer/sites/parts_library")
    page.wait_for_timeout(3000)

    code = page.locator("#code-content")
    expect(code).to_contain_text("Generated by OpenSCAD Framework")
    expect(code).not_to_contain_text("Load a site to see")


@pytest.mark.e2e
def test_double_click_navigates_into_a_leaf(page: Page, base_url: str):
    """Every entry in the parts library is a leaf, and zoomIn refused any node
    without children -- so nothing in the catalog could be navigated into at
    all, by double-click or by scroll. Selecting worked, which is what made it
    look like the click had registered and the view had simply not changed.
    """
    page.goto(f"{base_url}/viewer/sites/parts_library")
    page.wait_for_timeout(3000)
    expect(page.locator("#breadcrumb")).not_to_contain_text("datum_core")

    page.dblclick("text=datum_core (part)")
    page.wait_for_timeout(3000)

    expect(page.locator("#breadcrumb")).to_contain_text("datum_core")
    expect(page.locator("#contents-list")).to_contain_text("datum_core")


@pytest.mark.e2e
def test_viewer_runs_with_no_access_to_any_cdn(page: Page, base_url: str):
    """The page has to work for a browser that cannot reach the public internet.

    Aborting every off-origin request reproduces an ad blocker, a proxy, or an
    offline machine. Before the library was vendored this left the page inert
    but plausible-looking: static "Layout valid" chip, empty everything else.
    """
    page.route("**cdn.jsdelivr.net/**", lambda route, request: route.abort())
    page.route("**unpkg.com/**", lambda route, request: route.abort())

    page.goto(f"{base_url}/viewer/sites/parts_library")
    page.wait_for_timeout(4000)

    expect(page.locator("#status")).to_contain_text("Loaded")
    expect(page.locator("#contents-list")).to_contain_text("datum_core")
    expect(page.locator("#code-content")).to_contain_text("Generated by OpenSCAD Framework")



@pytest.mark.e2e
def test_a_part_deep_link_arrives_with_its_panel_open(page: Page, base_url: str):
    """`/viewer/parts/<name>` promises the parameter controls, and the panel is
    only built once a node is selected -- focusing alone left the reader one
    click short of what the link said it would show.
    """
    page.goto(f"{base_url}/viewer/parts/datum_core")
    page.wait_for_selector("#part-params", timeout=20000)
    page.wait_for_timeout(1500)

    expect(page.locator("#breadcrumb")).to_contain_text("datum_core")
    assert page.locator("#part-params input[type=range]").count() > 0, "no sliders to stage with"
    expect(page.locator("#stage-summary")).to_be_visible()


@pytest.mark.e2e
def test_a_link_written_before_the_rename_still_lands_on_the_part(page: Page, base_url: str):
    """The library was consolidated to underscore case after links to
    `datum-core` had been handed out. The wrapper lookup tolerates the old
    spelling; the redirect canonicalises so the focus string matches a real
    node instead of nothing.
    """
    page.goto(f"{base_url}/viewer/parts/datum-core")
    page.wait_for_selector("#part-params", timeout=20000)
    assert "focus=datum_core" in page.url, page.url
    expect(page.locator("#breadcrumb")).to_contain_text("datum_core")


# ---------------------------------------------------------------------------
# Viewing range, assembly outlines, and per-node detail
#
# These assert against the live scene through window.fractalViewer rather than
# against a screenshot: a screenshot cannot distinguish "the far plane clipped
# the world away" from "the world is behind you", which is the exact bug the
# clipping change fixes.
# ---------------------------------------------------------------------------


def _viewer_state(page: Page) -> dict:
    """Read camera/scene counters straight out of the running viewer."""
    return page.evaluate(
        """() => {
            const v = window.fractalViewer;
            return {
                far: v.camera.far,
                maxDolly: v.orbitControls.maxDistance,
                meshes: Object.keys(v.meshByName).length,
                overlays: Object.keys(v.compoundOverlayByKey).length,
                dots: Object.values(v.meshByName).filter((m) => m.userData.isDot).length,
            };
        }"""
    )


def _load_garage(page: Page, base_url: str) -> dict:
    page.goto(f"{base_url}/viewer/sites/garage")
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(1500)
    return _viewer_state(page)


@pytest.mark.e2e
def test_far_plane_clears_the_furthest_the_camera_can_dolly(page: Page, base_url: str):
    """The whole point of the render-distance change.

    The far plane used to be a fixed 20000 while the dolly clamp was derived
    per level and reached ~54000 on the garage, so pulling back to look at the
    largest scale clipped the world away instead of showing more of it.
    """
    state = _load_garage(page, base_url)

    assert state["far"] > state["maxDolly"], (
        f"far plane {state['far']} is inside the dolly clamp {state['maxDolly']}; "
        "the scene clips when zoomed out"
    )
    assert state["far"] > 20000, "far plane is still the old fixed 20000"


@pytest.mark.e2e
def test_assembly_outlines_toggle_off_and_on(page: Page, base_url: str):
    """Each compound node gets one outline, and the toolbar toggle removes them."""
    state = _load_garage(page, base_url)
    assert state["overlays"] > 0, "expected an outline per compound node"

    page.locator("#overlay-toggle").uncheck()
    page.wait_for_timeout(800)
    assert _viewer_state(page)["overlays"] == 0

    page.locator("#overlay-toggle").check()
    page.wait_for_timeout(800)
    assert _viewer_state(page)["overlays"] == state["overlays"]


@pytest.mark.e2e
def test_detail_mode_collapses_compound_nodes_to_dots(page: Page, base_url: str):
    """`Dot` replaces every compound node's box with a marker; `box` restores it."""
    state = _load_garage(page, base_url)
    assert state["dots"] == 0

    page.locator("#detail-mode").select_option("dot")
    page.wait_for_timeout(1200)
    dotted = _viewer_state(page)
    assert dotted["dots"] > 0, "no node collapsed to a dot"
    assert dotted["meshes"] == state["meshes"], "detail level changed how many nodes render"

    page.locator("#detail-mode").select_option("box")
    page.wait_for_timeout(1200)
    assert _viewer_state(page)["dots"] == 0


@pytest.mark.e2e
def test_detail_can_be_overridden_for_one_node(page: Page, base_url: str):
    """A per-node override applies to that node alone, not the whole level."""
    _load_garage(page, base_url)

    page.locator("#contents-list .contents-item").first.click()
    page.wait_for_timeout(500)

    detail_select = page.locator(".detail-select")
    if detail_select.count() == 0:
        pytest.skip("first contents row is a leaf; it has no subassembly to collapse")

    detail_select.first.select_option("dot")
    page.wait_for_timeout(1000)

    assert _viewer_state(page)["dots"] == 1, "override should affect exactly the selected node"
