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
from apothecary.projects.parts.gridfinity import DEFAULT as GRIDFINITY
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


def _fake_openscad(path: Path, version: str) -> Path:
    """An `openscad` that reports ``version``, writes a stand-in STL where `-o`
    says, and logs its arguments to ``<path>.calls``."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "#!/bin/sh\n"
        f'echo "$@" >> "{path}.calls"\n'
        f'echo "OpenSCAD version {version}" >&2\n'
        'if [ "$1" = "-o" ]; then printf "solid fake\\nendsolid fake\\n" > "$2"; fi\n'
    )
    path.chmod(0o755)
    return path


def _calls(executable: Path) -> list[str]:
    log = Path(f"{executable}.calls")
    return log.read_text().splitlines() if log.exists() else []


@pytest.fixture
def installed(tmp_path, monkeypatch):
    """``installed(default=, nightly=, on_path=)``: the OpenSCADs the resolver can
    find are these fakes and nothing else. Returns (default, nightly) paths."""

    def install(default=None, nightly=None, on_path=None):
        from apothecary.projects.parts import stl_renderer
        from apothecary.projects.parts.stl_renderer import OpenSCADRenderer

        bin_dir = tmp_path / "bin"
        bin_dir.mkdir(exist_ok=True)
        monkeypatch.setenv("PATH", str(bin_dir))
        if on_path:
            _fake_openscad(bin_dir / "openscad-nightly", on_path)
        stable = tmp_path / "stable" / "openscad"
        if default:
            _fake_openscad(stable, default)
        snapshot = _fake_openscad(tmp_path / "nightly" / "openscad", nightly) if nightly else None
        # Found as on a real machine: the default at a usual place, if it is there.
        monkeypatch.setattr(OpenSCADRenderer, "OPENSCAD_PATHS", [str(stable)])
        paths = [str(snapshot)] if snapshot else []
        monkeypatch.setattr(OpenSCADRenderer, "OPENSCAD_NIGHTLY_PATHS", paths)
        monkeypatch.setattr(stl_renderer, "_renderer", None)
        monkeypatch.setattr(stl_renderer, "_VERSIONS", {}, raising=False)
        return stable, snapshot

    return install


def _needs(tmp_path, version="2021.08.24") -> BasePart:
    return BasePart(name="p", source_file=tmp_path / "p.scad", openscad_min_version=version)


class TestOpenSCADRequirement:
    """A part that names an OpenSCAD minimum gets the first install that meets it."""

    @pytest.mark.parametrize(
        "text,version",
        [
            ("OpenSCAD version 2021.01", (2021, 1)),
            ("OpenSCAD version 2025.03.15", (2025, 3, 15)),
            ("OpenSCAD version 2024.12.06.ai21474", (2024, 12, 6)),
            ("no version here", None),
        ],
    )
    def test_versions_parse_to_comparable_tuples(self, text, version):
        from apothecary.projects.parts.stl_renderer import parse_openscad_version

        assert parse_openscad_version(text) == version

    def test_a_snapshot_alone_is_the_default(self, installed):
        _, snapshot = installed(nightly="2025.03.15")
        assert get_renderer().openscad_path == snapshot

    def test_two_links_to_one_executable_are_two_openscads(self, installed, tmp_path):
        """A snap links every app in /snap/bin to /usr/bin/snap, which runs the
        one its name says: openscad and openscad-nightly are two programs."""
        installed()
        multiplexer = tmp_path / "snap"
        multiplexer.write_text(
            '#!/bin/sh\ncase "$0" in *nightly) v=2025.03.15;; *) v=2021.01;; esac\n'
            'echo "OpenSCAD version $v" >&2\n'
        )
        multiplexer.chmod(0o755)
        for name in ("openscad", "openscad-nightly"):
            (tmp_path / "bin" / name).symlink_to(multiplexer)
        assert _needs(tmp_path).get_openscad_path() == tmp_path / "bin" / "openscad-nightly"

    def test_a_snapshot_stands_in_for_a_default_that_is_too_old(self, installed, tmp_path):
        _, snapshot = installed(default="2021.01", nightly="2025.03.15")
        part = _needs(tmp_path)
        assert part.can_generate_stl() == (True, "")
        assert part.get_openscad_path() == snapshot

    def test_openscad_nightly_on_path_is_a_snapshot(self, installed, tmp_path):
        installed(default="2021.01", on_path="2024.12.06.ai21474")
        assert _needs(tmp_path).get_openscad_path() == tmp_path / "bin" / "openscad-nightly"

    def test_a_default_that_is_new_enough_comes_first(self, installed, tmp_path):
        stable, _ = installed(default="2021.10.01", nightly="2025.03.15")
        assert _needs(tmp_path).get_openscad_path() == stable

    def test_nothing_new_enough_is_refused_naming_the_version(self, installed, tmp_path):
        stable, _ = installed(default="2021.01")
        can_build, reason = _needs(tmp_path).can_generate_stl()
        assert not can_build
        assert "2021.08.24 or newer" in reason and f"{stable} is OpenSCAD version 2021.01" in reason
        assert "https://openscad.org/downloads.html#snapshots" in reason

    def test_no_openscad_at_all_is_refused(self, installed, tmp_path):
        installed()
        can_build, reason = _needs(tmp_path).can_generate_stl()
        assert not can_build and "none is installed" in reason

    def test_each_executable_is_asked_its_version_once(self, installed, tmp_path):
        stable, snapshot = installed(default="2021.01", nightly="2025.03.15")
        part = _needs(tmp_path)
        for _ in range(3):
            part.can_generate_stl()
            part.get_openscad_path()
        assert _calls(stable) == ["--version"]
        assert _calls(snapshot) == ["--version"]

    def test_a_minimum_that_is_not_a_version_is_refused(self, tmp_path):
        with pytest.raises(ValueError, match="not an OpenSCAD version"):
            _needs(tmp_path, "latest")


@pytest.mark.skipif(
    not GRIDFINITY.submodule_initialized, reason="gridfinity submodule not initialized"
)
class TestGridfinityOpenSCAD:
    """gridfinity-rebuilt-openscad 2.0.0 needs a build newer than OpenSCAD 2021.01."""

    def test_it_takes_a_snapshot_when_the_default_is_too_old(self, installed):
        _, snapshot = installed(default="2021.01", nightly="2025.03.15")
        assert GRIDFINITY.can_generate_stl() == (True, "")
        assert GRIDFINITY.get_openscad_path() == snapshot

    def test_a_late_2021_snapshot_is_new_enough(self, installed):
        stable, _ = installed(default="2021.10.01")
        assert GRIDFINITY.can_generate_stl() == (True, "")
        assert GRIDFINITY.get_openscad_path() == stable

    def test_a_snapshot_alone_builds_it_through_the_api(self, installed, monkeypatch, tmp_path):
        """What the part's metadata offers, the build route does."""
        from fastapi.testclient import TestClient

        from apothecary.api import app

        _, snapshot = installed(nightly="2025.03.15")
        stl = tmp_path / "gridfinity.stl"
        monkeypatch.setattr(type(GRIDFINITY), "get_stl_output_path", lambda self: stl)
        client = TestClient(app)
        assert client.get("/parts/gridfinity").json()["files"]["stl"]["can_generate"] is True
        r = client.post("/parts/gridfinity/stl/generate")
        assert r.status_code == 200, r.text
        assert [call.split()[0] for call in _calls(snapshot)] == ["--version", "-o"]
        assert stl.exists()

    def test_it_is_refused_on_2021_01_naming_what_it_needs(self, installed):
        from apothecary.projects.parts.gridfinity import OPENSCAD_MIN_VERSION

        installed(default="2021.01")
        can_build, reason = GRIDFINITY.can_generate_stl()
        assert not can_build
        assert f"needs OpenSCAD {OPENSCAD_MIN_VERSION} or newer" in reason

    def test_generate_stl_all_skips_it_without_rendering(self, installed, monkeypatch):
        from click.testing import CliRunner

        from apothecary.cli import cli
        from apothecary.projects.registry import ProjectInfo

        stable, _ = installed(default="2021.01")
        entry = ProjectInfo(
            name="gridfinity",
            path=GRIDFINITY.source_file,
            kind="part",
            files=[],
            readme=False,
            wrapper="apothecary.projects.parts.gridfinity",
        )
        monkeypatch.setattr("apothecary.cli.parts.scan_projects", lambda root: [entry])
        result = CliRunner().invoke(cli, ["parts", "generate-stl", "--all", "--force"])
        assert result.exit_code == 0, result.output
        assert "gridfinity: cannot build here (needs OpenSCAD" in result.output
        assert _calls(stable) == ["--version"]

    def test_the_server_does_not_render_it_at_startup(
        self, installed, monkeypatch, tmp_path, capsys
    ):
        import asyncio

        from apothecary import api
        from apothecary.projects.registry import ProjectInfo

        stable, _ = installed(default="2021.01")
        entry = ProjectInfo(
            name="gridfinity",
            path=GRIDFINITY.source_file,
            kind="part",
            files=[],
            readme=False,
            wrapper="apothecary.projects.parts.gridfinity",
        )
        monkeypatch.setattr(api, "scan_projects", lambda root: [entry])
        monkeypatch.setattr(
            type(GRIDFINITY), "get_stl_output_path", lambda self: tmp_path / "gridfinity.stl"
        )
        monkeypatch.delenv("APOTHECARY_SKIP_STL_GENERATION", raising=False)
        asyncio.run(api._generate_missing_stls())
        assert "skipped: needs OpenSCAD" in capsys.readouterr().out
        assert _calls(stable) == ["--version"]
        assert not (tmp_path / "gridfinity.stl").exists()


class TestGridfinityOutput:
    def test_gridfinity_stl_output_not_in_submodule(self):
        """Verify gridfinity STL is stored in parts/gridfinity, not inside submodule."""
        stl_path = GRIDFINITY.get_stl_output_path()

        # Should NOT be inside the submodule directory
        assert "gridfinity-rebuilt-openscad" not in str(stl_path), (
            f"STL should not be in submodule: {stl_path}"
        )

        # Should be in parts/gridfinity/
        assert stl_path.parent.name == "gridfinity", (
            f"STL should be in parts/gridfinity/: {stl_path}"
        )
        assert stl_path.name == "gridfinity.stl", f"STL should be named gridfinity.stl: {stl_path}"
