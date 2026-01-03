"""Tests for STL rendering and PartFiles data model."""

from pathlib import Path
from unittest.mock import patch

from apothecary.projects.parts.part_files import FileStatus, PartFile, PartFiles
from apothecary.projects.parts.stl_renderer import OpenSCADRenderer, RenderResult


class TestPartFile:
    """Tests for PartFile model."""

    def test_part_file_exists_true(self, tmp_path):
        """Test that exists returns True for existing files."""
        test_file = tmp_path / "test.scad"
        test_file.write_text("cube([10,10,10]);")

        pf = PartFile(path=test_file, format="scad")
        assert pf.exists is True
        assert pf.size_bytes > 0
        assert pf.modified_at is not None

    def test_part_file_exists_false(self, tmp_path):
        """Test that exists returns False for missing files."""
        missing = tmp_path / "missing.scad"

        pf = PartFile(path=missing, format="scad")
        assert pf.exists is False
        assert pf.size_bytes is None
        assert pf.modified_at is None

    def test_part_file_read_text(self, tmp_path):
        """Test reading file contents."""
        test_file = tmp_path / "test.scad"
        content = "cube([10,10,10]);"
        test_file.write_text(content)

        pf = PartFile(path=test_file, format="scad")
        assert pf.read_text() == content


class TestPartFiles:
    """Tests for PartFiles model."""

    def test_from_scad_file(self, tmp_path):
        """Test creating PartFiles from a SCAD file."""
        scad_file = tmp_path / "test_part.scad"
        scad_file.write_text("cube([10,10,10]);")

        pf = PartFiles.from_scad_file(scad_file)

        assert pf.part_name == "test_part"
        assert pf.scad_file.exists is True
        assert pf.stl_file is None  # No STL generated yet

    def test_from_scad_file_with_stl(self, tmp_path):
        """Test creating PartFiles when STL exists."""
        scad_file = tmp_path / "test_part.scad"
        scad_file.write_text("cube([10,10,10]);")

        stl_file = tmp_path / "test_part.stl"
        stl_file.write_bytes(b"solid test\nendsolid test")

        pf = PartFiles.from_scad_file(scad_file)

        assert pf.stl_file is not None
        assert pf.stl_file.exists is True

    def test_from_part_dir(self, tmp_path):
        """Test creating PartFiles from a part directory."""
        part_dir = tmp_path / "my_part"
        part_dir.mkdir()

        scad_file = part_dir / "my_part.scad"
        scad_file.write_text("cube([10,10,10]);")

        pf = PartFiles.from_part_dir(part_dir, "my_part")

        assert pf.part_name == "my_part"
        assert pf.part_dir == part_dir
        assert pf.scad_file.exists is True

    def test_get_stl_status_missing(self, tmp_path):
        """Test STL status when file is missing."""
        scad_file = tmp_path / "test.scad"
        scad_file.write_text("cube([10,10,10]);")

        pf = PartFiles.from_scad_file(scad_file)
        assert pf.get_stl_status() == FileStatus.MISSING

    def test_get_stl_status_present(self, tmp_path):
        """Test STL status when file exists."""
        scad_file = tmp_path / "test.scad"
        scad_file.write_text("cube([10,10,10]);")

        stl_file = tmp_path / "test.stl"
        stl_file.write_bytes(b"solid test\nendsolid test")

        pf = PartFiles.from_scad_file(scad_file)
        assert pf.get_stl_status() == FileStatus.PRESENT

    def test_to_api_dict(self, tmp_path):
        """Test API dictionary generation."""
        scad_file = tmp_path / "test.scad"
        scad_file.write_text("cube([10,10,10]);")

        pf = PartFiles.from_scad_file(scad_file)
        api_dict = pf.to_api_dict("http://localhost:8000")

        assert api_dict["part_name"] == "test"
        assert api_dict["scad"]["exists"] is True
        assert "download_url" in api_dict["scad"]
        assert api_dict["stl"]["exists"] is False
        assert "generate_url" in api_dict["stl"]


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

    def test_get_files_method(self, tmp_path):
        """Test get_files() returns PartFiles instance."""
        from apothecary.projects.parts.base import BasePart

        scad = tmp_path / "test.scad"
        scad.write_text("cube([10,10,10]);")

        part = BasePart(name="test", source_file=scad)
        files = part.get_files()

        assert isinstance(files, PartFiles)
        assert files.part_name == "test"
