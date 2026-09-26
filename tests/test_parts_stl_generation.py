"""Every registered part loads, evaluates in OpenSCAD, and renders to an STL.

Cases come from the registry, so a part described by a part.json or living in
a nested package is checked like any other.
"""

import subprocess
from pathlib import Path
from typing import Optional

import pytest
from rendered_parts import built_stl_fixture, registered_parts  # noqa: F401

from apothecary.projects.parts.base import BasePart
from apothecary.projects.parts.stl_renderer import get_renderer

ALL_PARTS = registered_parts()


@pytest.mark.parametrize("part_name,part", ALL_PARTS, ids=[p[0] for p in ALL_PARTS])
class TestPartSTLGeneration:
    def test_part_exists(self, part_name: str, part: Optional[BasePart]):
        assert part is not None, f"Failed to import part wrapper for '{part_name}'"

    def test_source_file_exists(self, part_name: str, part: Optional[BasePart]):
        if part is None:
            pytest.skip("Part not loaded")
        assert part.source_file.exists(), f"Source file missing: {part.source_file}"

    @pytest.mark.skipif(not get_renderer().is_available, reason="OpenSCAD not installed")
    def test_scad_evaluates(self, part_name: str, part: Optional[BasePart], tmp_path: Path):
        """The SCAD parses and evaluates: a CSG export runs everything but CGAL's
        booleans, so a syntax error, a missing include or an undefined module
        fails here in a hundredth of a second. The full render is the slow test."""
        if part is None or not part.source_file.exists():
            pytest.skip("Part not loaded")
        can_gen, reason = part.can_generate_stl()
        if not can_gen:
            pytest.skip(f"Part cannot generate STL: {reason}")
        openscad = str(part.get_openscad_path() or get_renderer().openscad_path)
        done = subprocess.run(
            [openscad, "-o", str(tmp_path / f"{part_name}.csg"), str(part.source_file)],
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert done.returncode == 0, f"{part_name}: {done.stderr[-2000:]}"
        errors = [line for line in done.stderr.splitlines() if line.startswith("ERROR")]
        assert not errors, f"{part_name}: {errors}"

    @pytest.mark.slow
    def test_stl_generation(self, part_name: str, part: Optional[BasePart], built_stl):
        if part is None:
            pytest.skip("Part not loaded")
        assert built_stl(part).stat().st_size > 0, "STL file is empty"


def test_cases_include_described_and_nested_parts():
    names = {name for name, _ in ALL_PARTS}
    assert {"datum_core", "esp32_devkitc", "snowplow"} <= names


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
                    f"Expected gridfinity to use nightly ({nightly}), got {custom_path}"
                )

                can_gen, reason = gridfinity.can_generate_stl()
                assert can_gen is True, f"Should be able to generate with nightly: {reason}"
                assert "nightly" in reason.lower(), f"Reason should mention nightly: {reason}"
            else:
                # No nightly available - should report can't generate
                can_gen, reason = gridfinity.can_generate_stl()
                assert can_gen is False, "Should not be able to generate without nightly"
                assert "2024" in reason or "nightly" in reason.lower(), (
                    f"Reason should explain version requirement: {reason}"
                )
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
        assert "gridfinity-rebuilt-openscad" not in str(stl_path), (
            f"STL should not be in submodule: {stl_path}"
        )

        # Should be in parts/gridfinity/
        assert stl_path.parent.name == "gridfinity", (
            f"STL should be in parts/gridfinity/: {stl_path}"
        )
        assert stl_path.name == "gridfinity.stl", f"STL should be named gridfinity.stl: {stl_path}"
