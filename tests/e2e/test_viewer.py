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
    assert "26" in bg_color or "1a" in bg_color.lower() or "rgb(26" in bg_color, \
        f"Expected dark background, got {bg_color}"


@pytest.mark.e2e
def test_viewer_shows_contents_for_the_loaded_site(page: Page, base_url: str):
    """Test that the garage site's top-level structures appear in Contents."""
    page.goto(f"{base_url}/viewer/sites/garage")
    page.wait_for_timeout(600)

    items = page.locator("#contents-list .contents-item")
    assert items.count() == 4  # workbench + 3 printers
    expect(page.locator("#contents-list")).to_contain_text("workbench")


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
        assert jscad_response.ok, \
            f"Part {part_name}: JSCAD endpoint returned {jscad_response.status}"

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
        assert scad_response.ok, \
            f"Part {part_name}: SCAD endpoint returned {scad_response.status}"

        content = scad_response.text()
        assert len(content) > 0, f"Part {part_name}: Empty SCAD response"


@pytest.mark.e2e
def test_viewer_integrated_loads_without_critical_errors(page: Page, base_url: str):
    """Test that the fractal viewer loads without critical JavaScript errors."""
    console_errors = []
    page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)

    page.goto(f"{base_url}/viewer/sites/garage")

    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(2000)

    critical_errors = [e for e in console_errors if not any(ignore in e.lower() for ignore in [
        "extension",
        "favicon",
        "chrome-extension",
    ])]

    assert len(critical_errors) == 0, f"Console errors found: {critical_errors}"
