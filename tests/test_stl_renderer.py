"""Tests for STL rendering and build_stl, the one way a part's STL is built."""

import os
import stat
import threading
import time
from enum import IntEnum
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner
from pydantic import BaseModel

from apothecary import Cube, Import
from apothecary.meshes import bounds, read_mesh
from apothecary.models import Vector3D
from apothecary.projects.parts.base import BasePart
from apothecary.projects.parts.stl_renderer import (
    SUPERSEDED,
    Cancellation,
    OpenSCADRenderer,
    RenderResult,
    build_stl,
    get_renderer,
    has_summary,
    read_params_sidecar,
    render_part,
    scad_dependencies,
    scad_literal,
    write_params_sidecar,
)
from apothecary.projects.registry import ProjectInfo

needs_openscad = pytest.mark.skipif(
    not get_renderer().is_available, reason="OpenSCAD not installed"
)


class TestOpenSCADRenderer:
    """Tests for OpenSCAD renderer."""

    @pytest.fixture(autouse=True)
    def _nothing_installed_here(self, tmp_path, monkeypatch):
        """No snapshot `apothecary openscad install` put down, and no override."""
        monkeypatch.setenv("APOTHECARY_TOOLS_DIR", str(tmp_path / "tools"))
        monkeypatch.delenv("APOTHECARY_OPENSCAD", raising=False)

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
        hangs.write_text(
            '#!/bin/sh\n[ "$1" = --version ] && echo "OpenSCAD version 2021.01" >&2 && exit 0\n'
            'printf "solid partial\\n" > "$2"\nexec sleep 30\n'
        )
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

    openscad_path = None

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
            def can_generate_stl(self, openscad=None):
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
        # Scratch files sit beside the STL: a snap's OpenSCAD has its own /tmp.
        assert [scratch.parent for _, _, scratch in seen] == [tmp_path] * len(seen)
        assert read_params_sidecar(part.get_stl_output_path())["params"] == {"x": 12}
        assert build_stl(part, {"x": 12}, renderer=Reading()).skipped == "fresh"
        assert sorted(p.name for p in tmp_path.iterdir()) == [
            "block.params.json",
            "block.scad",
            "block.stl",
        ]

    def test_an_import_in_python_geometry_names_its_file_absolutely(self, tmp_path):
        """The SCAD renders from a scratch directory, not from the part's folder."""

        class Imports(BasePart):
            def geometry(self, params):
                return Import(file="mesh.stl")

        part = Imports(name="block", source_file=_part(tmp_path).source_file)
        seen = []

        class Reading(FakeRenderer):
            def render_stl(self, scad_path, stl_path=None, timeout=120.0, params=None):
                seen.append(Path(scad_path).read_text())
                return super().render_stl(scad_path, stl_path, timeout, params)

        assert build_stl(part, renderer=Reading()).success
        assert f'import("{(tmp_path / "mesh.stl").as_posix()}"' in seen[0]

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


def _scripted_openscad(path: Path, version: str, body: str = "") -> Path:
    """An `openscad` that reports ``version``, logs its arguments to
    ``<path>.calls``, runs ``body`` for a render, then writes a stand-in STL
    where `-o` says and, when asked, a summary measuring 10 x 20 x 3."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "#!/bin/sh\n"
        f'echo "$@" >> "{path}.calls"\n'
        f'[ "$1" = --version ] && echo "OpenSCAD version {version}" >&2 && exit 0\n'
        f"{body}\n"
        'for arg in "$@"; do case "$arg" in --summary-file=*)\n'
        '  printf \'{"geometry":{"bounding_box":{"min":[0,0,0],"max":[10,20,3],'
        '"size":[10,20,3]}}}\' > "${arg#--summary-file=}";; esac; done\n'
        'printf "solid fake\\nendsolid fake\\n" > "$2"\n'
    )
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return path


def _renders(executable: Path) -> list[str]:
    log = Path(f"{executable}.calls")
    lines = log.read_text().splitlines() if log.exists() else []
    return [line for line in lines if line.startswith("-o")]


class TestStoppingARender:
    """A newer request's Cancellation stops an older render's OpenSCAD."""

    def test_a_cancelled_render_stops_its_openscad_and_leaves_nothing(self, tmp_path):
        exe = _scripted_openscad(tmp_path / "bin" / "openscad", "2021.01", "exec sleep 30")
        scad, stl = tmp_path / "part.scad", tmp_path / "out" / "part.stl"
        scad.write_text("cube(1);")
        cancel = Cancellation()
        done = {}
        worker = threading.Thread(
            target=lambda: done.update(
                result=OpenSCADRenderer(str(exe)).render_stl(scad, stl, 60, cancel=cancel)
            )
        )
        started = time.monotonic()
        worker.start()
        deadline = time.monotonic() + 10
        while not cancel._running and time.monotonic() < deadline:
            time.sleep(0.01)
        assert cancel._running, "the render never started"
        cancel.cancel()
        worker.join(10)
        assert not worker.is_alive()
        result = done["result"]
        assert result.cancelled and not result.success
        assert result.error_message == SUPERSEDED
        assert time.monotonic() - started < 10
        assert not cancel._running
        assert list(stl.parent.iterdir()) == []

    def test_a_cancelled_render_starts_nothing(self, tmp_path):
        exe = _scripted_openscad(tmp_path / "bin" / "openscad", "2021.01")
        scad = tmp_path / "part.scad"
        scad.write_text("cube(1);")
        cancel = Cancellation()
        cancel.cancel()
        result = OpenSCADRenderer(str(exe)).render_stl(scad, tmp_path / "p.stl", cancel=cancel)
        assert result.cancelled and _renders(exe) == []

    def test_a_turned_part_does_not_start_its_second_run_once_cancelled(self, tmp_path):
        exe = _scripted_openscad(tmp_path / "bin" / "openscad", "2021.01")
        cancel = Cancellation()

        class CancelledAfterOne(OpenSCADRenderer):
            def render_stl(self, *args, **kwargs):
                result = super().render_stl(*args, **kwargs)
                cancel.cancel()
                return result

        result = render_part(
            _part(tmp_path),
            tmp_path / "out.stl",
            renderer=CancelledAfterOne(str(exe)),
            rotation=[90, 0, 0],
            cancel=cancel,
        )
        assert result.cancelled
        assert len(_renders(exe)) == 1
        assert not (tmp_path / "out.stl").exists()


class TestMeasuredBounds:
    """The bounding box OpenSCAD measured, where its summary says it."""

    def test_an_openscad_with_a_summary_is_asked_for_one(self, tmp_path):
        exe = _scripted_openscad(tmp_path / "bin" / "openscad", "2026.09.27")
        scad = tmp_path / "part.scad"
        scad.write_text("cube([10, 20, 3]);")
        result = OpenSCADRenderer(str(exe)).render_stl(scad, tmp_path / "out" / "part.stl")
        assert result.success
        assert result.measured == {"min": [0, 0, 0], "max": [10, 20, 3], "size": [10, 20, 3]}
        assert "--summary=all" in _renders(exe)[0]
        # The summary is read and removed; only the STL is left.
        assert [p.name for p in (tmp_path / "out").iterdir()] == ["part.stl"]

    def test_2021_01_is_not_asked_and_measures_nothing(self, tmp_path):
        exe = _scripted_openscad(tmp_path / "bin" / "openscad", "2021.01")
        scad = tmp_path / "part.scad"
        scad.write_text("cube(1);")
        result = OpenSCADRenderer(str(exe)).render_stl(scad, tmp_path / "part.stl")
        assert result.success and result.measured is None
        assert "--summary" not in _renders(exe)[0]

    def test_a_turned_part_keeps_the_upright_measurement(self, tmp_path):
        """Declared bounds are the upright SCAD's (`apothecary parts verify`)."""
        exe = _scripted_openscad(
            tmp_path / "bin" / "openscad",
            "2026.09.27",
            # The turning run measures something else, which is not kept.
            'case "$*" in *rotate.scad*) for arg in "$@"; do case "$arg" in '
            '--summary-file=*) printf \'{"geometry":{"bounding_box":{"min":[0,0,0],'
            '"max":[1,1,1],"size":[1,1,1]}}}\' > "${arg#--summary-file=}";; esac; done; '
            'printf "solid t\\nendsolid t\\n" > "$2"; exit 0;; esac',
        )
        result = render_part(
            _part(tmp_path),
            tmp_path / "out.stl",
            renderer=OpenSCADRenderer(str(exe)),
            rotation=[90, 0, 0],
        )
        assert result.success
        assert result.measured["size"] == [10, 20, 3]

    @needs_openscad
    def test_the_installed_openscad_measures_a_cube_where_it_can(self, tmp_path):
        if not has_summary(get_renderer().openscad_path):
            pytest.skip("this OpenSCAD writes no summary")
        scad = tmp_path / "part.scad"
        scad.write_text("translate([1, 2, 3]) cube([10, 20, 3]);")
        result = get_renderer().render_stl(scad, tmp_path / "part.stl")
        assert result.success, result.stderr
        assert result.measured == {"min": [1, 2, 3], "max": [11, 22, 6], "size": [10, 20, 3]}


class TestIncludes:
    """What a SCAD reads is part of what its STL is built from."""

    def test_includes_uses_and_imports_are_followed(self, tmp_path):
        (tmp_path / "lib").mkdir()
        (tmp_path / "lib" / "a.scad").write_text("include <deeper.scad>\n")
        (tmp_path / "lib" / "deeper.scad").write_text("module d() cube(1);\n")
        (tmp_path / "b.scad").write_text("module b() cube(1);\n")
        (tmp_path / "mesh.stl").write_text("solid m\nendsolid m\n")
        main = tmp_path / "main.scad"
        main.write_text(
            "include <lib/a.scad>\nuse <b.scad>\n// include <commented.scad>\n"
            '/* use <block.scad> */\nimport("mesh.stl");\nimport(file = "other.stl");\n'
            "include <missing.scad>\n"
        )
        assert scad_dependencies(main) == {
            "main.scad:lib/a.scad": (tmp_path / "lib" / "a.scad").resolve(),
            "a.scad:deeper.scad": (tmp_path / "lib" / "deeper.scad").resolve(),
            "main.scad:b.scad": (tmp_path / "b.scad").resolve(),
            "main.scad:mesh.stl": (tmp_path / "mesh.stl").resolve(),
            "main.scad:other.stl": None,
            "main.scad:missing.scad": None,
        }

    def test_an_include_found_on_openscadpath(self, tmp_path, monkeypatch):
        library = tmp_path / "libraries"
        library.mkdir()
        (library / "shared.scad").write_text("module s() cube(1);\n")
        main = tmp_path / "part" / "main.scad"
        main.parent.mkdir()
        main.write_text("use <shared.scad>\n")
        monkeypatch.setenv("OPENSCADPATH", str(library))
        assert scad_dependencies(main) == {
            "main.scad:shared.scad": (library / "shared.scad").resolve()
        }

    def test_an_edited_include_rebuilds_the_stl(self, tmp_path):
        (tmp_path / "dims.scad").write_text("depth = 20;\n")
        (tmp_path / "block.scad").write_text(
            "include <dims.scad>\nx = 10;\ncube([x, depth, 30]);\n"
        )
        part, fake = _part(tmp_path), FakeRenderer()
        build_stl(part, renderer=fake)
        assert build_stl(part, renderer=fake).skipped == "fresh"

        later = part.get_stl_output_path().stat().st_mtime + 5
        os.utime(tmp_path / "dims.scad", (later, later))
        assert build_stl(part, renderer=fake).skipped is None
        assert len(fake.calls) == 2
