"""
End-to-end API tests using Playwright's request context.
"""
import json
import pytest
from playwright.sync_api import Page


@pytest.mark.e2e
def test_root_endpoint(page: Page, base_url: str):
    """Test the root endpoint redirects to viewer."""
    response = page.request.get(f"{base_url}/", max_redirects=0)
    
    # Root should redirect to /viewer
    assert response.status == 307 or response.status == 302


@pytest.mark.e2e
def test_health_endpoint_returns_json(page: Page, base_url: str):
    """Test the health API endpoint returns proper JSON."""
    response = page.request.get(f"{base_url}/health")
    
    assert response.ok
    data = response.json()
    
    assert data["status"] == "healthy"
    assert "version" in data


@pytest.mark.e2e
def test_parts_list_structure(page: Page, base_url: str):
    """Test that parts list has correct structure."""
    response = page.request.get(f"{base_url}/parts")
    
    assert response.ok
    parts = response.json()
    
    assert isinstance(parts, list)
    
    if len(parts) > 0:
        part = parts[0]
        required_fields = ["name", "description", "category", "tags", "source_file", "has_params"]
        
        for field in required_fields:
            assert field in part, f"Missing required field: {field}"


@pytest.mark.e2e
def test_part_detail_endpoint(page: Page, base_url: str):
    """Test getting details for a specific part."""
    # Get list of parts
    response = page.request.get(f"{base_url}/parts")
    parts = response.json()
    
    if len(parts) > 0:
        part_name = parts[0]["name"]
        
        # Get detail for first part
        detail_response = page.request.get(f"{base_url}/parts/{part_name}")
        
        assert detail_response.ok
        detail = detail_response.json()
        
        assert detail["name"] == part_name
        assert "params" in detail
        assert "include" in detail
        assert "download_url" in detail


@pytest.mark.e2e
def test_part_scad_download(page: Page, base_url: str):
    """Test downloading SCAD file."""
    response = page.request.get(f"{base_url}/parts")
    parts = response.json()
    
    if len(parts) > 0:
        part_name = parts[0]["name"]
        
        scad_response = page.request.get(f"{base_url}/parts/{part_name}/scad")
        
        assert scad_response.ok
        content = scad_response.text()
        
        # Should contain OpenSCAD code
        assert len(content) > 0
        assert isinstance(content, str)


@pytest.mark.e2e
def test_part_jscad_format(page: Page, base_url: str):
    """Test that JSCAD endpoint returns valid format."""
    response = page.request.get(f"{base_url}/parts")
    parts = response.json()
    
    if len(parts) > 0:
        part_name = parts[0]["name"]
        
        jscad_response = page.request.get(f"{base_url}/parts/{part_name}/jscad")
        
        assert jscad_response.ok
        assert jscad_response.headers["content-type"] == "application/javascript"
        
        content = jscad_response.text()
        
        # Verify JSCAD structure (CommonJS format)
        assert "const jscad = require('@jscad/modeling')" in content
        assert "const main = () => {" in content
        assert "module.exports = { main }" in content


@pytest.mark.e2e
def test_nonexistent_part_returns_404(page: Page, base_url: str):
    """Test that requesting a non-existent part returns 404."""
    response = page.request.get(f"{base_url}/parts/nonexistent-part-name-12345")
    
    assert response.status == 404


@pytest.mark.e2e
def test_render_scene_endpoint(page: Page, base_url: str):
    """Test the scene rendering endpoint."""
    scene_data = {
        "name": "test-scene",
        "objects": [
            {
                "type": "cube",
                "size": {"x": 10, "y": 10, "z": 10},
                "center": False
            }
        ]
    }
    
    response = page.request.post(
        f"{base_url}/render",
        headers={"Content-Type": "application/json"},
        data=json.dumps(scene_data)
    )
    
    assert response.ok
    data = response.json()
    
    assert data["success"] is True
    assert "code" in data
    # Code should contain some OpenSCAD content (either the cube or a fallback)
    assert len(data["code"]) > 0
    assert "openscad" in data["code"].lower()
