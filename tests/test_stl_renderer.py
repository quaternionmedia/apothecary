"""Tests for STL rendering."""

import stat
from enum import IntEnum
from pathlib import Path
from unittest.mock import patch

import pytest
from pydantic import BaseModel

from apothecary.projects.parts.stl_renderer import OpenSCADRenderer, RenderResult, scad_literal


class TestOpenSCADRenderer:
    """Tests for OpenSCAD renderer."""

    def test_detect_openscad_on_path(self, monkeypatch):
        monkeypatch.setattr("shutil.which", lambda name: "/opt/bin/openscad")
        assert OpenSCADRenderer()._detect_openscad() == Path("/opt/bin/openscad")

    def test_detect_openscad_not_found(self, monkeypatch):
        monkeypatch.setattr("shutil.which", lambda name: None)
        monkeypatch.setattr(OpenSCADRenderer, "OPENSCAD_PATHS", [])
        assert OpenSCADRenderer()._detect_openscad() is None

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

    def test_a_killed_render_leaves_no_stl(self, tmp_path):
        """OpenSCAD writes a temporary file that replaces the STL only on success."""
        hangs = tmp_path / "openscad"
        # Writes half a file where it was told to, then never finishes.
        hangs.write_text('#!/bin/sh\nprintf "solid partial\\n" > "$2"\nexec sleep 30\n')
        hangs.chmod(hangs.stat().st_mode | stat.S_IEXEC)
        scad = tmp_path / "part.scad"
        scad.write_text("cube(1);")
        stl = tmp_path / "part.stl"

        result = OpenSCADRenderer(str(hangs)).render_stl(scad, stl, timeout=0.3)
        assert not result.success and "timed out" in result.error_message
        assert not stl.exists()
        assert sorted(p.name for p in tmp_path.iterdir()) == ["openscad", "part.scad"]

        stl.write_text("solid previous\nendsolid previous\n")
        OpenSCADRenderer(str(hangs)).render_stl(scad, stl, timeout=0.3)
        assert stl.read_text() == "solid previous\nendsolid previous\n"


class TestScadLiteralTypes:
    def test_an_enum_is_its_value(self):
        class Tab(IntEnum):
            LEFT = 2

        assert scad_literal(Tab.LEFT) == "2"

    def test_a_nested_model_is_refused_by_name(self):
        class Holes(BaseModel):
            magnets: bool = True

        with pytest.raises(TypeError, match="Holes is a nested parameter model"):
            scad_literal(Holes())


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
