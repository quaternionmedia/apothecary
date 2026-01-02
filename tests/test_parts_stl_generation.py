"""
Parameterized tests for STL generation across all parts.

This test discovers all registered parts and attempts STL generation,
reporting any OpenSCAD errors.
"""
import pytest
from pathlib import Path
from typing import List, Tuple, Optional

from apothecary.projects.parts.stl_renderer import OpenSCADRenderer, get_renderer
from apothecary.projects.parts.base import BasePart


def discover_all_parts() -> List[Tuple[str, Optional[BasePart]]]:
    """Discover all registered parts by importing the parts package."""
    parts = []
    
    # Import the parts package and iterate over modules
    from apothecary.projects import parts as parts_pkg
    import pkgutil
    import importlib
    
    for importer, modname, ispkg in pkgutil.iter_modules(parts_pkg.__path__):
        if ispkg or modname.startswith("_"):
            continue
        # Skip non-part modules
        if modname in ("base", "skeleton", "part_files", "stl_renderer"):
            continue
        
        try:
            module = importlib.import_module(f"apothecary.projects.parts.{modname}")
            if hasattr(module, "DEFAULT"):
                part = module.DEFAULT
                if isinstance(part, BasePart):
                    parts.append((part.name, part))
        except Exception as e:
            # Still add for test discovery - will fail with import error
            parts.append((modname, None))
    
    return parts


# Discover parts at collection time
ALL_PARTS = discover_all_parts()


@pytest.fixture(scope="module")
def renderer() -> OpenSCADRenderer:
    """Get OpenSCAD renderer instance."""
    return get_renderer()


@pytest.mark.parametrize("part_name,part", ALL_PARTS, ids=[p[0] for p in ALL_PARTS])
class TestPartSTLGeneration:
    """Test STL generation for each registered part."""
    
    def test_part_exists(self, part_name: str, part: Optional[BasePart]):
        """Verify part wrapper loaded successfully."""
        assert part is not None, f"Failed to import part wrapper for '{part_name}'"
    
    def test_source_file_exists(self, part_name: str, part: Optional[BasePart]):
        """Verify source SCAD file exists."""
        if part is None:
            pytest.skip("Part not loaded")
        
        assert part.source_file.exists(), (
            f"Source file missing: {part.source_file}"
        )
    
    @pytest.mark.skipif(
        not get_renderer().is_available,
        reason="OpenSCAD not installed"
    )
    def test_stl_generation(self, part_name: str, part: Optional[BasePart], renderer: OpenSCADRenderer, tmp_path: Path):
        """Attempt STL generation and report any errors."""
        if part is None:
            pytest.skip("Part not loaded")
        
        if not part.source_file.exists():
            pytest.skip("Source file missing")
        
        # Generate to temp directory to avoid polluting parts folder
        stl_output = tmp_path / f"{part_name}.stl"
        
        result = renderer.render_stl(
            scad_path=part.source_file,
            stl_path=stl_output,
            timeout=60.0  # 1 minute per part
        )
        
        if not result.success:
            # Build detailed error message
            error_details = [f"STL generation failed for '{part_name}'"]
            error_details.append(f"Source: {part.source_file}")
            
            if result.error_message:
                error_details.append(f"Error: {result.error_message}")
            
            if result.stderr:
                error_details.append(f"OpenSCAD stderr:\n{result.stderr}")
            
            if result.stdout:
                error_details.append(f"OpenSCAD stdout:\n{result.stdout}")
            
            pytest.fail("\n".join(error_details))
        
        # Verify STL was actually created and has content
        assert stl_output.exists(), "STL file not created"
        assert stl_output.stat().st_size > 0, "STL file is empty"


# Additional convenience test to show summary
class TestPartsSummary:
    """Summary test for part discovery."""
    
    def test_parts_discovered(self):
        """Verify that parts were discovered."""
        assert len(ALL_PARTS) > 0, "No parts discovered"
        print(f"\nDiscovered {len(ALL_PARTS)} parts:")
        for name, part in ALL_PARTS:
            status = "✓" if part and part.source_file.exists() else "✗"
            print(f"  {status} {name}")
    
    @pytest.mark.skipif(
        not get_renderer().is_available,
        reason="OpenSCAD not installed"
    )
    def test_openscad_available(self):
        """Verify OpenSCAD is available."""
        renderer = get_renderer()
        print(f"\nOpenSCAD path: {renderer.openscad_path}")
        version = renderer.get_version()
        if version:
            print(f"OpenSCAD version: {version}")
