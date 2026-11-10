"""Tests for STL rendering and build_stl, the one way a part's STL is built."""

import os
import shutil
import stat
import threading
import time
from enum import IntEnum
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner
from pydantic import BaseModel, ValidationError
from rendered_parts import face_up

from apothecary import Cube, Import
from apothecary.meshes import bounds, read_mesh
from apothecary.models import Vector3D
from apothecary.projects.parts.assignments import last_of, parse_assignments
from apothecary.projects.parts.base import BasePart
from apothecary.projects.parts.skeleton import ROOT
from apothecary.projects.parts.stl_renderer import (
    SUPERSEDED,
    Cancellation,
    OpenSCADRenderer,
    RenderResult,
    build_stl,
    get_renderer,
    has_summary,
    read_params_sidecar,
    scad_dependencies,
    scad_literal,
    write_params_sidecar,
)
from apothecary.projects.registry import ProjectInfo, load_part, part_named, scan_projects

needs_openscad = pytest.mark.skipif(
    not get_renderer().is_available, reason="OpenSCAD not installed"
)

# The parts whose SCAD lays them the way up they print and, with print=false, turns
# them as they rest: the x, y and z extent of each pose, as OpenSCAD renders it.
PRINTS_AND_RESTS = {
    "solderfan": ((134, 134, 12), (134, 12, 134)),  # a tray flat on its base; on its edge
    "fifel": ((25, 25.43, 200), (25, 200, 25.43)),  # standing on its head; on its tube
}


def _library():
    """Every part of the library, as the registry loads it."""
    for item in scan_projects(ROOT):
        if item.kind == "part" and item.has_part:
            yield load_part(item)


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

    def test_the_scad_gets_the_parts_translation_and_the_sidecar_the_params(self, tmp_path):
        class Renamed(BasePart):
            def scad_overrides(self, params):
                return {f"size_{name}": value for name, value in params.items()}

        scad = tmp_path / "block.scad"
        scad.write_text("size_x = 10;\ncube([size_x, 20, 30]);\n")
        part = Renamed(name="block", source_file=scad, params_model=Size)
        fake = FakeRenderer()
        assert build_stl(part, {"x": 12}, renderer=fake).success
        assert fake.calls[0] == (scad, {"size_x": 12})
        assert read_params_sidecar(part.get_stl_output_path())["params"] == {"x": 12}
        assert build_stl(part, {"x": 12}, renderer=fake).skipped == "fresh"

    def test_python_geometry_is_what_renders(self, tmp_path):
        part = _Built(name="block", source_file=_part(tmp_path).source_file, params_model=Size)
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

    def test_a_default_build_clears_a_variants_sidecar(self, tmp_path):
        part, fake = _part(tmp_path), FakeRenderer()
        build_stl(part, {"x": 12}, renderer=fake)
        stl = part.get_stl_output_path()
        assert read_params_sidecar(stl)["params"] == {"x": 12}
        build_stl(part, renderer=fake)
        assert read_params_sidecar(stl) is None

    @needs_openscad
    def test_the_footpedal_is_built_as_its_scad_lays_it(self, tmp_path):
        """The footpedal's SCAD lays it on its button face, the way up it prints: the
        STL it builds is that render, as tall as its z, not stood on its edge."""
        from apothecary.projects.parts.footpedal import DEFAULT as PEDAL

        scad = tmp_path / "footpedal.scad"
        shutil.copyfile(PEDAL.source_file, scad)
        built = build_stl(PEDAL.model_copy(update={"source_file": scad}))
        own = get_renderer().render_stl(scad, tmp_path / "own.stl")
        assert built.success and own.success, (built.error_message, own.error_message)
        lo, hi = bounds(read_mesh(built.stl_path))
        size = [hi[axis] - lo[axis] for axis in range(3)]
        assert size[2] == pytest.approx(PEDAL.params_model().z, abs=1), size
        own_lo, own_hi = bounds(read_mesh(own.stl_path))
        assert [*lo, *hi] == pytest.approx([*own_lo, *own_hi], abs=1e-3)

    @needs_openscad
    def test_the_footpedal_rests_on_its_base_and_prints_on_its_button_face(self, tmp_path):
        """Its rest pose is its SCAD with print=false, in a file of its own: on its
        base (z 0), the largest face that faces up its button face, tilted by theta.
        Its STL, the print pose, has a flat face up: the inside of the top plate."""
        from apothecary.projects.parts.footpedal import DEFAULT as PEDAL

        scad = tmp_path / "footpedal.scad"
        shutil.copyfile(PEDAL.source_file, scad)
        part = PEDAL.model_copy(update={"source_file": scad})
        printed, rests = build_stl(part), build_stl(part, pose="rest")
        assert printed.success and rests.success, (printed.error_message, rests.error_message)
        assert printed.stl_path == part.get_stl_output_path() != rests.stl_path
        lo, hi = bounds(read_mesh(rests.stl_path))
        assert lo[2] == pytest.approx(0, abs=1e-3), (lo, hi)
        assert face_up(rests.stl_path) == pytest.approx(-PEDAL.params_model().theta, abs=0.5)
        assert face_up(printed.stl_path) == pytest.approx(0, abs=0.5)
        assert build_stl(part, pose="rest").skipped == "fresh"

    @needs_openscad
    @pytest.mark.parametrize("name", sorted(PRINTS_AND_RESTS))
    def test_a_part_turned_to_rest_prints_as_its_scad_lays_it(self, tmp_path, name):
        """solderfan's SCAD lays the tray flat on its base and fifel's stands the fife
        on its head, each the way up it prints, and its STL is that render, unturned;
        print=false turns it as it rests, the tray stood on its edge, the fife laid on
        its side. Each pose stands on z 0."""
        own = part_named(name, ROOT)
        scad = tmp_path / own.source_file.name
        shutil.copyfile(own.source_file, scad)
        part = own.model_copy(update={"source_file": scad})
        printed, rests = build_stl(part), build_stl(part, pose="rest")
        assert printed.success and rests.success, (printed.error_message, rests.error_message)
        for result, size in zip((printed, rests), PRINTS_AND_RESTS[name], strict=True):
            lo, hi = bounds(read_mesh(result.stl_path))
            assert [hi[axis] - lo[axis] for axis in range(3)] == pytest.approx(size, abs=0.01)
            assert lo[2] == pytest.approx(0, abs=1e-3), (result.stl_path.name, lo, hi)

    @needs_openscad
    def test_the_fife_rests_on_its_tube_its_lip_rest_up(self, tmp_path):
        """Laid the other way the fife would rest on its lip rest's tip and roll: it lies
        on its tube, the head's rim on z 0, and what of it stands highest is its lip
        rest, 20 from its head."""
        own = part_named("fifel", ROOT)
        scad = tmp_path / own.source_file.name
        shutil.copyfile(own.source_file, scad)
        rests = build_stl(own.model_copy(update={"source_file": scad}), pose="rest")
        assert rests.success, rests.error_message
        corners = [corner for triangle in read_mesh(rests.stl_path) for corner in triangle]
        floor, top = min(z for *_, z in corners), max(z for *_, z in corners)
        assert floor == pytest.approx(0, abs=1e-3)
        assert {round(y) for _, y, z in corners if z < floor + 0.01} == {0}
        highest = [y for _, y, z in corners if z > top - 0.3]
        assert 11 < min(highest) and max(highest) < 29, (min(highest), max(highest))

    def test_no_part_offers_how_it_rests_as_a_control(self):
        """A rest definition is its SCAD's own pose flag, not a parameter: each one a
        part of the library declares is assigned in its SCAD after ``/* [Hidden] */``
        and is no field of its model, so neither the page's controls nor OpenSCAD's
        customizer offer it, where a person setting it would change what a slice
        reads."""
        offered, declared = {}, []
        for part in _library():
            if not part.rest:
                continue
            declared.append(part.name)
            assigned = last_of(parse_assignments(part.source_file.read_text(encoding="utf-8")))
            fields = part.params_model.model_fields if part.params_model else {}
            shown = [
                n for n in part.rest if n not in assigned or assigned[n].parameter or n in fields
            ]
            if shown:
                offered[part.name] = shown
        assert sorted(declared) == ["fifel", "footpedal", "solderfan"]
        assert offered == {}

    def test_the_rest_definitions_reach_the_scad_beside_the_parameters(self, tmp_path):
        (tmp_path / "block.scad").write_text("x = 10;\nstanding = false;\ncube([x, 20, 30]);\n")
        part, fake = _part(tmp_path, rest={"standing": True}), FakeRenderer()
        rests = build_stl(part, {"x": 12}, renderer=fake, pose="rest")
        assert rests.success and rests.stl_path == tmp_path / "block.rest.stl"
        assert fake.calls == [(part.source_file, {"x": 12, "standing": True})]
        assert read_params_sidecar(rests.stl_path)["params"] == {"x": 12}
        assert build_stl(part, {"x": 12}, renderer=fake, pose="rest").skipped == "fresh"
        assert build_stl(part, {"x": 12}, renderer=fake).stl_path == tmp_path / "block.stl"
        assert fake.calls[1:] == [(part.source_file, {"x": 12})]

    def test_a_part_without_a_rest_pose_builds_one_stl(self, tmp_path):
        part, fake = _part(tmp_path), FakeRenderer()
        assert build_stl(part, renderer=fake, pose="rest").stl_path == part.get_stl_output_path()
        assert build_stl(part, renderer=fake).skipped == "fresh"
        assert len(fake.calls) == 1
        assert sorted(p.name for p in tmp_path.iterdir()) == ["block.scad", "block.stl"]

    def test_a_rest_pose_is_what_d_can_carry(self, tmp_path):
        with pytest.raises(ValidationError, match="rest: .*nested parameter model"):
            _part(tmp_path, rest={"size": Size()})

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
        exe = _scripted_openscad(tmp_path / "bin" / "openscad", "2021.01", "exec sleep 300")
        scad, stl = tmp_path / "part.scad", tmp_path / "out" / "part.stl"
        scad.write_text("cube(1);")
        cancel = Cancellation()
        done = {}
        worker = threading.Thread(
            target=lambda: done.update(
                result=OpenSCADRenderer(str(exe)).render_stl(scad, stl, 60, cancel=cancel)
            )
        )
        worker.start()
        deadline = time.monotonic() + 10
        while not cancel._running and time.monotonic() < deadline:
            time.sleep(0.01)
        assert cancel._running, "the render never started"
        cancel.cancel()
        worker.join(60)  # a render left to run takes five minutes
        assert not worker.is_alive()
        result = done["result"]
        assert result.cancelled and not result.success
        assert result.error_message == SUPERSEDED
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
