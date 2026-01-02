"""
End-to-end tests for the Apothecary 3D parts viewer.
"""
import pytest
from playwright.sync_api import Page, expect


@pytest.mark.e2e
def test_viewer_page_loads(page: Page, base_url: str):
    """Test that the 3D viewer page loads successfully."""
    page.goto(f"{base_url}/viewer")
    
    # Check page title
    expect(page).to_have_title("Apothecary Parts Viewer")
    
    # Check main heading in toolbar
    heading = page.locator(".toolbar h1")
    expect(heading).to_contain_text("Apothecary")


@pytest.mark.e2e
def test_viewer_has_parts_dropdown(page: Page, base_url: str):
    """Test that the parts dropdown is present and functional."""
    page.goto(f"{base_url}/viewer")
    
    # Check dropdown exists
    select = page.locator("#part-select")
    expect(select).to_be_visible()
    
    # Check that it has options (placeholder + at least a few parts)
    options = select.locator("option")
    count = options.count()
    assert count >= 4, f"Expected at least 4 options (including placeholder), got {count}"


@pytest.mark.e2e
def test_viewer_has_download_buttons(page: Page, base_url: str):
    """Test that download buttons are present in dropdowns."""
    page.goto(f"{base_url}/viewer")
    
    # Check load button
    load_btn = page.locator("#load-btn")
    expect(load_btn).to_be_visible()
    
    # Check dropdown buttons exist (use get_by_role for exact match)
    scad_dropdown = page.get_by_role("button", name="📥 SCAD ▼")
    expect(scad_dropdown).to_be_visible()
    
    jscad_dropdown = page.get_by_role("button", name="📥 JSCAD ▼")
    expect(jscad_dropdown).to_be_visible()


@pytest.mark.e2e
def test_viewer_has_canvas(page: Page, base_url: str):
    """Test that the 3D viewer canvas exists."""
    page.goto(f"{base_url}/viewer")
    
    canvas = page.locator("#viewer-canvas")
    expect(canvas).to_be_visible()


@pytest.mark.e2e
def test_viewer_has_code_panel(page: Page, base_url: str):
    """Test that the code panel exists."""
    page.goto(f"{base_url}/viewer")
    
    code_panel = page.locator(".code-panel")
    expect(code_panel).to_be_visible()
    
    code_content = page.locator("#code-content")
    expect(code_content).to_be_visible()


@pytest.mark.e2e
def test_viewer_dark_theme(page: Page, base_url: str):
    """Test that the viewer uses dark theme."""
    page.goto(f"{base_url}/viewer")
    
    # Check body has dark background
    body = page.locator("body")
    bg_color = body.evaluate("el => getComputedStyle(el).backgroundColor")
    # Should be a dark color (rgb values close to 0)
    assert "26" in bg_color or "1a" in bg_color.lower() or "rgb(26" in bg_color, \
        f"Expected dark background, got {bg_color}"


@pytest.mark.e2e
def test_viewer_shows_preview_on_select(page: Page, base_url: str):
    """Test that selecting a part shows code in the code panel."""
    page.goto(f"{base_url}/viewer")
    
    # Select a part
    select = page.locator("#part-select")
    select.select_option(index=1)  # First actual part (index 0 is placeholder)
    
    # Click load button
    load_btn = page.locator("#load-btn")
    load_btn.click()
    
    # Wait for code to load
    page.wait_for_timeout(1000)
    
    # Code content should have actual code
    code_content = page.locator("#code-content")
    text = code_content.text_content()
    # Should have some OpenSCAD code, not the placeholder message
    assert len(text) > 50 or "module" in text.lower() or "//" in text


@pytest.mark.e2e
def test_parts_api_returns_list(page: Page, base_url: str):
    """Test that the parts API endpoint returns a valid list."""
    response = page.request.get(f"{base_url}/parts")
    
    assert response.ok
    data = response.json()
    
    assert isinstance(data, list)
    assert len(data) > 0
    
    # Check first part has expected structure
    first_part = data[0]
    assert "name" in first_part
    assert "description" in first_part
    assert "source_file" in first_part


@pytest.mark.e2e
def test_parts_jscad_endpoint(page: Page, base_url: str):
    """Test that the JSCAD endpoint returns valid JavaScript."""
    # Get list of parts first
    response = page.request.get(f"{base_url}/parts")
    parts = response.json()
    
    if len(parts) > 0:
        part_name = parts[0]["name"]
        
        # Request JSCAD version
        jscad_response = page.request.get(f"{base_url}/parts/{part_name}/jscad")
        
        assert jscad_response.ok
        content = jscad_response.text()
        
        # Check it's valid JSCAD (CommonJS format for jscad-web)
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
def test_viewer_canvas_renders(page: Page, base_url: str):
    """Test that viewer canvas renders correctly."""
    page.goto(f"{base_url}/viewer")
    
    # Canvas should exist and have dimensions
    canvas = page.locator("#viewer-canvas")
    expect(canvas).to_be_visible()
    
    # Canvas should have proper dimensions
    box = canvas.bounding_box()
    assert box is not None
    assert box["width"] > 100
    assert box["height"] > 100


@pytest.mark.e2e
def test_viewer_loads_each_part_jscad(page: Page, base_url: str):
    """Test that JSCAD endpoint works for every available part."""
    # Get all parts
    response = page.request.get(f"{base_url}/parts")
    parts = response.json()
    
    assert len(parts) > 0, "No parts available"
    
    # Test each part's JSCAD endpoint
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
    # Get all parts
    response = page.request.get(f"{base_url}/parts")
    parts = response.json()
    
    assert len(parts) > 0, "No parts available"
    
    # Test each part's SCAD endpoint
    for part in parts:
        part_name = part["name"]
        
        scad_response = page.request.get(f"{base_url}/parts/{part_name}/scad")
        assert scad_response.ok, \
            f"Part {part_name}: SCAD endpoint returned {scad_response.status}"
        
        content = scad_response.text()
        assert len(content) > 0, f"Part {part_name}: Empty SCAD response"


@pytest.mark.e2e
def test_viewer_integrated_loads_without_critical_errors(page: Page, base_url: str):
    """Test that the integrated viewer loads without critical JavaScript errors."""
    console_errors = []
    page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
    
    page.goto(f"{base_url}/viewer")
    
    # Wait for page to fully load
    page.wait_for_load_state("networkidle")
    
    # Wait a bit for any async errors
    page.wait_for_timeout(2000)
    
    # Filter out known non-critical errors
    critical_errors = [e for e in console_errors if not any(ignore in e.lower() for ignore in [
        "extension",
        "favicon",
        "chrome-extension",
    ])]
    
    assert len(critical_errors) == 0, f"Console errors found: {critical_errors}"


@pytest.mark.e2e
def test_viewer_download_buttons_work(page: Page, base_url: str):
    """Test that download dropdowns are functional after loading a part."""
    page.goto(f"{base_url}/viewer")
    
    # Select a part
    select = page.locator("#part-select")
    select.select_option(index=1)
    
    # Click load button
    load_btn = page.locator("#load-btn")
    load_btn.click()
    
    # Wait for load
    page.wait_for_timeout(500)
    
    # Verify dropdown buttons are visible (use exact name match)
    scad_dropdown = page.get_by_role("button", name="📥 SCAD ▼")
    expect(scad_dropdown).to_be_visible()
    
    jscad_dropdown = page.get_by_role("button", name="📥 JSCAD ▼")
    expect(jscad_dropdown).to_be_visible()
    
    # Hover to show dropdown and verify download link exists
    scad_dropdown.hover()
    download_link = page.locator("#download-scad")
    expect(download_link).to_be_visible()
