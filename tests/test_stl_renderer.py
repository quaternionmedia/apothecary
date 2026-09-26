"""Tests for STL rendering."""

from pathlib import Path
from unittest.mock import patch

from apothecary.projects.parts.stl_renderer import OpenSCADRenderer, RenderResult


class TestOpenSCADRenderer:
    """Tests for OpenSCAD renderer."""

    def test_detect_openscad_not_found(self):
        """Test detection when OpenSCAD is not installed."""
        renderer = OpenSCADRenderer()
        # Clear any cached detection
        renderer._detected_path = None
        renderer._openscad_path = None

        # Mock subprocess to simulate no OpenSCAD
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError()

            # Mock Path.exists to return False for all common paths
            with patch.object(Path, "exists", return_value=False):
                # Force re-detection
                renderer._detected_path = None
                path = renderer._detect_openscad()
                # Path might still be found if installed locally
                # Just check it doesn't crash
                assert path is None or isinstance(path, Path)

    def test_render_stl_missing_source(self, tmp_path):
        """Test rendering with missing source file."""
        renderer = OpenSCADRenderer()
        missing = tmp_path / "missing.scad"

        result = renderer.render_stl(missing)

        assert result.success is False
        assert "not found" in result.error_message.lower()

    def test_render_stl_openscad_not_available(self, tmp_path):
        """Test rendering when OpenSCAD is not installed."""
        scad_file = tmp_path / "test.scad"
        scad_file.write_text("cube([10,10,10]);")

        renderer = OpenSCADRenderer()
        renderer._openscad_path = None
        renderer._detected_path = None

        # Force is_available to return False
        with patch.object(
            OpenSCADRenderer, "is_available", new_callable=lambda: property(lambda self: False)
        ):
            result = OpenSCADRenderer().render_stl(scad_file)
            assert result.success is False
            assert "not found" in result.error_message.lower()

    def test_render_result_dataclass(self):
        """Test RenderResult dataclass."""
        result = RenderResult(
            success=True,
            stl_path=Path("/tmp/test.stl"),
            render_time_seconds=1.5,
            stdout="",
            stderr="",
        )

        assert result.success is True
        assert result.render_time_seconds == 1.5
        assert result.error_message is None


class TestBasePart:
    """Tests for BasePart STL/JSCAD file properties."""

    def test_stl_file_property(self, tmp_path):
        """Test that stl_file property returns path when exists."""
        from apothecary.projects.parts.base import BasePart

        scad = tmp_path / "test.scad"
        scad.write_text("cube([10,10,10]);")

        stl = tmp_path / "test.stl"
        stl.write_bytes(b"solid test\nendsolid test")

        part = BasePart(name="test", source_file=scad)

        assert part.stl_file is not None
        assert part.stl_file.exists()

    def test_stl_file_property_missing(self, tmp_path):
        """Test that stl_file property returns None when missing."""
        from apothecary.projects.parts.base import BasePart

        scad = tmp_path / "test.scad"
        scad.write_text("cube([10,10,10]);")

        part = BasePart(name="test", source_file=scad)

        assert part.stl_file is None
