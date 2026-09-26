"""Tests for STL rendering and build_stl, the one way a part's STL is built."""

import os
import stat
from enum import IntEnum
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner
from pydantic import BaseModel

from apothecary import Cube
from apothecary.meshes import bounds, read_mesh
from apothecary.models import Vector3D
from apothecary.projects.parts.base import BasePart
from apothecary.projects.parts.stl_renderer import (
    OpenSCADRenderer,
    RenderResult,
    build_stl,
    get_renderer,
    read_params_sidecar,
    scad_literal,
    write_params_sidecar,
)
from apothecary.projects.registry import ProjectInfo

needs_openscad = pytest.mark.skipif(
    not get_renderer().is_available, reason="OpenSCAD not installed"
)


class TestOpenSCADRenderer:
    """Tests for OpenSCAD renderer."""

    def test_detect_openscad_on_path(self, monkeypatch):
        monkeypatch.setattr("shutil.which", lambda name: "/opt/bin/openscad")
        assert OpenSCADRenderer()._detect_openscad() == Path("/opt/bin/openscad")

    def test_detect_openscad_not_found(self, monkeypatch):
        monkeypatch.setattr("shutil.which", lambda name: None)
        monkeypatch.setattr(OpenSCADRenderer, "OPENSCAD_PATHS", [])
        monkeypatch.setattr(OpenSCADRenderer, "OPENSCAD_NIGHTLY_PATHS", [])
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


class Size(BaseModel):
    x: float = 10


class FakeRenderer:
    """Writes a stand-in STL and counts the renders."""

    def __init__(self):
        self.calls = []

    def render_stl(self, scad_path, stl_path=None, timeout=120.0, params=None):
        self.calls.append((Path(scad_path), params))
        stl_path.write_text("solid fake\nendsolid fake\n")
        return RenderResult(success=True, stl_path=stl_path)


class _Built(BasePart):
    """A part built in Python: an x by 40 by 30 block, where its SCAD says x by 20 by 30."""

    def geometry(self, params):
        return Cube(size=Vector3D(x=params.get("x", 10), y=40, z=30))


def _part(tmp_path, **kw) -> BasePart:
    scad = tmp_path / "block.scad"
    if not scad.exists():
        scad.write_text("x = 10;\ncube([x, 20, 30]);\n")
    return BasePart(name="block", source_file=scad, params_model=Size, **kw)


class TestBuildStl:
    def test_an_up_to_date_stl_is_kept_and_an_edited_scad_rebuilds_it(self, tmp_path):
        part, fake = _part(tmp_path), FakeRenderer()
        assert build_stl(part, renderer=fake).skipped is None
        assert build_stl(part, renderer=fake).skipped == "fresh"
        assert len(fake.calls) == 1

        later = part.get_stl_output_path().stat().st_mtime + 5
        os.utime(part.source_file, (later, later))
        result = build_stl(part, renderer=fake)
        assert result.success and result.skipped is None
        assert len(fake.calls) == 2

    def test_other_parameters_are_not_up_to_date(self, tmp_path):
        part, fake = _part(tmp_path), FakeRenderer()
        build_stl(part, {"x": 12}, renderer=fake)
        assert build_stl(part, {"x": 12}, renderer=fake).skipped == "fresh"
        assert build_stl(part, renderer=fake).skipped is None
        assert len(fake.calls) == 2

    def test_overrides_are_validated_before_anything_renders(self, tmp_path):
        part, fake = _part(tmp_path), FakeRenderer()
        with pytest.raises(ValueError, match="unknown parameter.*y.*declares: x"):
            build_stl(part, {"y": 1}, renderer=fake)
        assert fake.calls == []

    def test_a_part_that_cannot_be_built_here_is_refused(self, tmp_path):
        class Unbuildable(BasePart):
            def can_generate_stl(self):
                return False, "needs a newer OpenSCAD"

        scad = tmp_path / "block.scad"
        scad.write_text("cube(1);")
        fake = FakeRenderer()
        result = build_stl(Unbuildable(name="block", source_file=scad), renderer=fake)
        assert not result.success and result.skipped == "refused"
        assert result.error_message == "needs a newer OpenSCAD"
        assert fake.calls == [] and not (tmp_path / "block.stl").exists()

    @pytest.mark.parametrize(
        "rotation", [Vector3D(), Vector3D(x=90, y=0, z=0)], ids=["upright", "rotated"]
    )
    def test_the_scad_gets_the_parts_translation_and_the_sidecar_the_params(
        self, tmp_path, rotation
    ):
        class Renamed(BasePart):
            def scad_overrides(self, params):
                return {f"size_{name}": value for name, value in params.items()}

        scad = tmp_path / "block.scad"
        scad.write_text("size_x = 10;\ncube([size_x, 20, 30]);\n")
        part = Renamed(name="block", source_file=scad, params_model=Size, display_rotation=rotation)
        fake = FakeRenderer()
        assert build_stl(part, {"x": 12}, renderer=fake).success
        assert fake.calls[0] == (scad, {"size_x": 12})
        assert read_params_sidecar(part.get_stl_output_path())["params"] == {"x": 12}
        assert build_stl(part, {"x": 12}, renderer=fake).skipped == "fresh"

    @pytest.mark.parametrize(
        "rotation", [Vector3D(), Vector3D(x=90, y=0, z=0)], ids=["upright", "rotated"]
    )
    def test_python_geometry_is_what_renders(self, tmp_path, rotation):
        part = _Built(
            name="block",
            source_file=_part(tmp_path).source_file,
            params_model=Size,
            display_rotation=rotation,
        )
        seen = []

        class Reading(FakeRenderer):
            def render_stl(self, scad_path, stl_path=None, timeout=120.0, params=None):
                seen.append((Path(scad_path).read_text(), params, Path(scad_path).parent))
                return super().render_stl(scad_path, stl_path, timeout, params)

        assert build_stl(part, {"x": 12}, renderer=Reading()).success
        text, definitions, where = seen[0]
        assert text == "cube([12.0, 40.0, 30.0], center=false);\n"
        assert definitions is None and where != tmp_path
        assert read_params_sidecar(part.get_stl_output_path())["params"] == {"x": 12}
        assert build_stl(part, {"x": 12}, renderer=Reading()).skipped == "fresh"
        assert sorted(p.name for p in tmp_path.iterdir()) == [
            "block.params.json",
            "block.scad",
            "block.stl",
        ]

    @needs_openscad
    def test_python_geometry_is_turned_by_display_rotation(self, tmp_path):
        part = _Built(
            name="block",
            source_file=_part(tmp_path).source_file,
            params_model=Size,
            display_rotation=Vector3D(x=90, y=0, z=0),
        )
        result = build_stl(part, {"x": 12})
        assert result.success, result.error_message
        lo, hi = bounds(read_mesh(result.stl_path))
        assert [round(hi[axis] - lo[axis], 3) for axis in range(3)] == [12, 30, 40]

    def test_a_default_build_clears_a_variants_sidecar(self, tmp_path):
        part, fake = _part(tmp_path), FakeRenderer()
        build_stl(part, {"x": 12}, renderer=fake)
        stl = part.get_stl_output_path()
        assert read_params_sidecar(stl)["params"] == {"x": 12}
        build_stl(part, renderer=fake)
        assert read_params_sidecar(stl) is None

    @needs_openscad
    def test_display_rotation_is_applied(self, tmp_path):
        part = _part(tmp_path, display_rotation=Vector3D(x=90, y=0, z=0))
        result = build_stl(part)
        assert result.success, result.error_message
        lo, hi = bounds(read_mesh(result.stl_path))
        size = [round(hi[axis] - lo[axis], 3) for axis in range(3)]
        assert size == [10, 30, 20]  # 10 x 20 x 30, turned about X
        # The upright render and its wrapper live in a scratch directory.
        assert sorted(p.name for p in tmp_path.iterdir()) == ["block.scad", "block.stl"]

    @needs_openscad
    def test_generate_stl_all_clears_a_stale_sidecar(self, tmp_path, monkeypatch):
        part = _part(tmp_path)
        stl = part.get_stl_output_path()
        stl.write_text("solid variant\nendsolid variant\n")
        write_params_sidecar(stl, {"x": 12})
        entry = ProjectInfo(
            name="block", path=part.source_file, kind="part", files=[], readme=False
        )
        monkeypatch.setattr("apothecary.cli.parts.scan_projects", lambda root: [entry])

        from apothecary.cli import cli

        result = CliRunner().invoke(cli, ["parts", "generate-stl", "--all"])
        assert result.exit_code == 0, result.output
        assert "1 generated" in result.output
        assert read_params_sidecar(stl) is None
        lo, hi = bounds(read_mesh(stl))
        assert round(hi[0] - lo[0], 3) == 10


class TestBasePart:
    """Tests for BasePart STL/JSCAD file properties."""

    def test_stl_file_property(self, tmp_path):
        """Test that stl_file property returns path when exists."""
        scad = tmp_path / "test.scad"
        scad.write_text("cube([10,10,10]);")

        stl = tmp_path / "test.stl"
        stl.write_bytes(b"solid test\nendsolid test")

        part = BasePart(name="test", source_file=scad)

        assert part.stl_file is not None
        assert part.stl_file.exists()

    def test_stl_file_property_missing(self, tmp_path):
        """Test that stl_file property returns None when missing."""
        scad = tmp_path / "test.scad"
        scad.write_text("cube([10,10,10]);")

        part = BasePart(name="test", source_file=scad)

        assert part.stl_file is None
