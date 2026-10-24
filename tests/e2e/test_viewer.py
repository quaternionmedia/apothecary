"""Browser tests for the fractal zoom viewer (templates/fractal_viewer.html.j2),
which is also the parts browser: the parts library is a site like any other."""

import pytest
from playwright.sync_api import Page, expect
from viewer_ready import WAVE_DONE


def _open(page: Page, url: str) -> None:
    """Go to a viewer page and wait until its site is on screen."""
    page.goto(url)
    expect(page.locator("#status")).to_contain_text("Loaded", timeout=20000)


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
    assert "26" in bg_color or "1a" in bg_color.lower() or "rgb(26" in bg_color, (
        f"Expected dark background, got {bg_color}"
    )


@pytest.mark.e2e
def test_viewer_shows_contents_for_the_loaded_site(page: Page, base_url: str):
    """Test that the garage site's top-level structures appear in Contents:
    the workbench and its printer fleet, plus the building shell, utility
    fixture stubs, storage, the CNC router stub, and the boards on the bench
    the firmware seam binds to (a devkit, the footpedal, an Uno, a Pi, a Teensy).
    """
    _open(page, f"{base_url}/viewer/sites/garage")

    expect(page.locator("#contents-list .contents-item")).to_have_count(16)
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
    _open(page, f"{base_url}/viewer/sites/garage")

    page.locator("#contents-list .contents-item", has_text="printer_1").dblclick()

    # Zoomed into printer_1: its substructures now populate Contents, and the
    # breadcrumb reflects the new depth.
    expect(page.locator("#breadcrumb")).to_contain_text("printer_1")
    expect(page.locator("#contents-list")).to_contain_text("gantry_system")
    expect(page.locator("#zoom-out-btn")).to_be_enabled()

    page.locator("#zoom-out-btn").click()

    expect(page.locator("#contents-list")).to_contain_text("workbench")
    expect(page.locator("#zoom-out-btn")).to_be_disabled()


def _depth(node: dict) -> int:
    return 1 + max(map(_depth, node["children"])) if node["children"] else 0


@pytest.mark.e2e
def test_minimap_advances_with_zoom_depth(page: Page, base_url: str):
    """One tick per level of the site's tree, filled down to the focus."""
    tree = page.request.get(f"{base_url}/sites/garage").json()["tree"]
    _open(page, f"{base_url}/viewer/sites/garage")

    expect(page.locator("#minimap .minimap-tick")).to_have_count(_depth(tree) + 1)
    filled = page.locator("#minimap .minimap-tick.filled")
    expect(filled).to_have_count(1)

    page.locator("#contents-list .contents-item", has_text="printer_1").dblclick()

    expect(filled).to_have_count(2)


@pytest.mark.e2e
def test_selecting_a_parts_library_leaf_shows_the_absorbed_part_view(page: Page, base_url: str):
    """Selecting a part in the parts library shows its SCAD source and a link to
    download it."""
    _open(page, f"{base_url}/viewer/sites/parts_library")

    page.locator("#contents-list .contents-item").first.click()

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
def test_viewer_integrated_loads_without_critical_errors(page: Page, base_url: str):
    """No console errors from loading the garage: its tree, its geometry and its
    device bindings."""
    console_errors = []
    page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
    page.add_init_script(WAVE_DONE)

    # The viewer's own "Loaded" status, not networkidle: the device panel
    # rescans ports on a schedule, so the page is never idle for long.
    _open(page, f"{base_url}/viewer/sites/garage")
    page.evaluate("() => window.fractalViewer.waveDone")
    page.wait_for_function("() => window.fractalViewer.bindingsLoaded")

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
    """A focused leaf is its own render node: listed in Contents and drawn from
    its STL, not an empty scene."""
    with page.expect_request(lambda r: "/parts/datum_core/stl" in r.url, timeout=20000):
        page.goto(f"{base_url}/viewer/sites/parts_library?focus=datum_core")

    expect(page.locator("#contents-list")).to_contain_text("datum_core")


@pytest.mark.e2e
def test_code_panel_populates_without_an_edit(page: Page, base_url: str):
    """Loading a site fills the generated OpenSCAD panel; no layout edit needed."""
    _open(page, f"{base_url}/viewer/sites/parts_library")

    code = page.locator("#code-content")
    expect(code).to_contain_text("Generated by OpenSCAD Framework")
    expect(code).not_to_contain_text("Load a site to see")


@pytest.mark.e2e
def test_double_click_navigates_into_a_leaf(page: Page, base_url: str):
    """A leaf (every entry in the parts library) can be zoomed into like any node."""
    _open(page, f"{base_url}/viewer/sites/parts_library")
    expect(page.locator("#breadcrumb")).not_to_contain_text("datum_core")

    page.dblclick("text=datum_core (part)")

    expect(page.locator("#breadcrumb")).to_contain_text("datum_core")
    expect(page.locator("#contents-list")).to_contain_text("datum_core")


@pytest.mark.e2e
def test_viewer_runs_with_no_access_to_any_cdn(page: Page, base_url: str):
    """The page works for a browser that cannot reach the public internet (an ad
    blocker, a proxy, an offline machine): every off-origin request is aborted."""
    page.route("**cdn.jsdelivr.net/**", lambda route, request: route.abort())
    page.route("**unpkg.com/**", lambda route, request: route.abort())

    _open(page, f"{base_url}/viewer/sites/parts_library")

    expect(page.locator("#contents-list")).to_contain_text("datum_core")
    expect(page.locator("#code-content")).to_contain_text("Generated by OpenSCAD Framework")


@pytest.mark.e2e
def test_a_part_deep_link_arrives_with_its_panel_open(page: Page, base_url: str):
    """`/viewer/parts/<name>` focuses the part and selects it, so its parameter
    controls are on screen without another click."""
    page.goto(f"{base_url}/viewer/parts/datum_core")

    expect(page.locator("#breadcrumb")).to_contain_text("datum_core", timeout=20000)
    expect(page.locator("#part-params input[type=range]").first).to_be_attached()
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
# the world away" from "the world is behind you".
# ---------------------------------------------------------------------------

STATE = """() => {
    const v = window.fractalViewer;
    return {
        far: v.camera.far,
        maxDolly: v.orbitControls.maxDistance,
        meshes: Object.keys(v.meshByName).length,
        overlays: Object.keys(v.compoundOverlayByKey).length,
        dots: Object.values(v.meshByName).filter((m) => m.userData.isDot).length,
    };
}"""


def _viewer_state(page: Page) -> dict:
    """Read camera/scene counters straight out of the running viewer."""
    return page.evaluate(STATE)


def _state_once(page: Page, holds: str) -> dict:
    """Wait until `holds` (JS over the counters, as `s`) is true; return the counters."""
    page.wait_for_function(f"() => {{ const s = ({STATE})(); return {holds}; }}")
    return _viewer_state(page)


def _load_garage(page: Page, base_url: str) -> dict:
    _open(page, f"{base_url}/viewer/sites/garage")
    return _viewer_state(page)


@pytest.mark.e2e
def test_far_plane_clears_the_furthest_the_camera_can_dolly(page: Page, base_url: str):
    """Pulled back as far as the dolly clamp allows (about 54000 on the garage),
    the world is still inside the far plane."""
    state = _load_garage(page, base_url)

    assert state["far"] > state["maxDolly"], (
        f"far plane {state['far']} is inside the dolly clamp {state['maxDolly']}; "
        "the scene clips when zoomed out"
    )
    assert state["far"] > 20000, "far plane is no further than 20000"


@pytest.mark.e2e
def test_assembly_outlines_toggle_off_and_on(page: Page, base_url: str):
    """Each compound node gets one outline, and the toolbar toggle removes them."""
    state = _load_garage(page, base_url)
    assert state["overlays"] > 0, "expected an outline per compound node"

    page.locator("#overlay-toggle").uncheck()
    _state_once(page, "s.overlays === 0")

    page.locator("#overlay-toggle").check()
    _state_once(page, f"s.overlays === {state['overlays']}")


@pytest.mark.e2e
def test_detail_mode_collapses_compound_nodes_to_dots(page: Page, base_url: str):
    """`Dot` replaces every compound node's box with a marker; `box` restores it."""
    state = _load_garage(page, base_url)
    assert state["dots"] == 0

    page.locator("#detail-mode").select_option("dot")
    dotted = _state_once(page, "s.dots > 0")
    assert dotted["meshes"] == state["meshes"], "detail level changed how many nodes render"

    page.locator("#detail-mode").select_option("box")
    _state_once(page, "s.dots === 0")


@pytest.mark.e2e
def test_detail_can_be_overridden_for_one_node(page: Page, base_url: str):
    """A per-node override applies to that node alone, not the whole level."""
    _load_garage(page, base_url)

    page.locator("#contents-list .contents-item[data-path='workbench']").click()
    page.locator("#selected-body .detail-select").select_option("dot")

    dotted = _state_once(page, "s.dots > 0")
    assert dotted["dots"] == 1, "override should affect exactly the selected node"
