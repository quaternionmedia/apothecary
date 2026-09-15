"""
Parameterized tests for STL generation across all parts.

This test discovers all registered parts and attempts STL generation,
reporting any OpenSCAD errors.
"""

from pathlib import Path
from typing import List, Optional, Tuple

import pytest

from apothecary.projects.parts.base import BasePart
from apothecary.projects.parts.stl_renderer import OpenSCADRenderer, get_renderer


def discover_all_parts() -> List[Tuple[str, Optional[BasePart]]]:
    """Discover all registered parts by importing the parts package."""
    parts = []

    # Import the parts package and iterate over modules
    import importlib
    import pkgutil

    from apothecary.projects import parts as parts_pkg

    for _importer, modname, ispkg in pkgutil.iter_modules(parts_pkg.__path__):
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
        except Exception:
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

        assert part.source_file.exists(), f"Source file missing: {part.source_file}"

    @pytest.mark.skipif(not get_renderer().is_available, reason="OpenSCAD not installed")
    def test_stl_generation(
        self, part_name: str, part: Optional[BasePart], renderer: OpenSCADRenderer, tmp_path: Path
    ):
        """Attempt STL generation and report any errors."""
        if part is None:
            pytest.skip("Part not loaded")

        if not part.source_file.exists():
            pytest.skip("Source file missing")

        # Check if part has special STL generation requirements
        if hasattr(part, "can_generate_stl"):
            can_gen, reason = part.can_generate_stl()
            if not can_gen:
                pytest.skip(f"Part cannot generate STL: {reason}")

        # Use part-specific OpenSCAD path if available (e.g., nightly build)
        part_renderer = renderer
        if hasattr(part, "get_openscad_path"):
            custom_path = part.get_openscad_path()
            if custom_path and custom_path != renderer.openscad_path:
                part_renderer = OpenSCADRenderer(openscad_path=str(custom_path))

        # Generate to temp directory to avoid polluting parts folder
        stl_output = tmp_path / f"{part_name}.stl"

        result = part_renderer.render_stl(
            scad_path=part.source_file,
            stl_path=stl_output,
            timeout=60.0,  # 1 minute per part
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

    @pytest.mark.skipif(not get_renderer().is_available, reason="OpenSCAD not installed")
    def test_openscad_available(self):
        """Verify OpenSCAD is available."""
        renderer = get_renderer()
        print(f"\nOpenSCAD path: {renderer.openscad_path}")
        version = renderer.get_version()
        if version:
            print(f"OpenSCAD version: {version}")


class TestCustomOpenSCADPaths:
    """Test parts that require specific OpenSCAD versions."""

    def test_gridfinity_uses_nightly_when_stable_too_old(self):
        """Verify gridfinity part selects nightly build when stable version is too old."""
        from apothecary.projects.parts.gridfinity import DEFAULT as gridfinity

        renderer = get_renderer()
        if not renderer.is_available:
            pytest.skip("OpenSCAD not installed")

        # Check if stable version is old (pre-2024)
        stable_version = renderer.get_version() or ""
        is_old_stable = any(
            year in stable_version for year in ["2019", "2020", "2021", "2022", "2023"]
        )

        if is_old_stable:
            # Part should detect this and use nightly if available
            nightly = renderer.find_nightly()
            if nightly:
                custom_path = gridfinity.get_openscad_path()
                assert custom_path == nightly, (
                    f"Expected gridfinity to use nightly ({nightly}), " f"got {custom_path}"
                )

                can_gen, reason = gridfinity.can_generate_stl()
                assert can_gen is True, f"Should be able to generate with nightly: {reason}"
                assert "nightly" in reason.lower(), f"Reason should mention nightly: {reason}"
            else:
                # No nightly available - should report can't generate
                can_gen, reason = gridfinity.can_generate_stl()
                assert can_gen is False, "Should not be able to generate without nightly"
                assert (
                    "2024" in reason or "nightly" in reason.lower()
                ), f"Reason should explain version requirement: {reason}"
        else:
            # Stable version is new enough - should just work
            can_gen, reason = gridfinity.can_generate_stl()
            if gridfinity.submodule_initialized:
                assert can_gen is True, f"Modern OpenSCAD should work: {reason}"

    def test_gridfinity_stl_output_not_in_submodule(self):
        """Verify gridfinity STL is stored in parts/gridfinity, not inside submodule."""
        from apothecary.projects.parts.gridfinity import DEFAULT as gridfinity

        stl_path = gridfinity.get_stl_output_path()

        # Should NOT be inside the submodule directory
        assert "gridfinity-rebuilt-openscad" not in str(
            stl_path
        ), f"STL should not be in submodule: {stl_path}"

        # Should be in parts/gridfinity/
        assert (
            stl_path.parent.name == "gridfinity"
        ), f"STL should be in parts/gridfinity/: {stl_path}"
        assert stl_path.name == "gridfinity.stl", f"STL should be named gridfinity.stl: {stl_path}"

    def test_part_can_generate_stl_returns_tuple(self):
        """Verify can_generate_stl returns proper (bool, str) tuple."""
        from apothecary.projects.parts.gridfinity import DEFAULT as gridfinity

        result = gridfinity.can_generate_stl()

        assert isinstance(result, tuple), f"Expected tuple, got {type(result)}"
        assert len(result) == 2, f"Expected 2-tuple, got {len(result)} elements"
        assert isinstance(result[0], bool), f"First element should be bool, got {type(result[0])}"
        assert isinstance(result[1], str), f"Second element should be str, got {type(result[1])}"
