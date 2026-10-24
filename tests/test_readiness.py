"""Whether a part is ready to print, answered from what the repo already knows.

The rule the module turns on: an unanswered question is not a pass. A checklist
that ticks a box it could not check is worse than no checklist.
"""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from rendered_parts import built_stl_fixture  # noqa: F401

from apothecary import meshes
from apothecary.api import app
from apothecary.models import BoundingBox3D, Vector3D
from apothecary.projects.parts import readiness
from apothecary.projects.parts.base import BasePart
from apothecary.projects.parts.datum_cap import DEFAULT as CAP
from apothecary.projects.parts.datum_core import DEFAULT as CORE
from apothecary.projects.parts.readiness import (
    BLOCKED,
    BOUNDS,
    PASS,
    UNKNOWN,
    Check,
    Readiness,
    _bounds_check,
    assess,
    compare_bounds,
)
from apothecary.projects.parts.stl_renderer import write_params_sidecar

client = TestClient(app)


class TestUnknownIsNeverAPass:
    def test_an_unanswered_question_blocks_readiness(self):
        report = Readiness(part="x", checks=[Check("asked", PASS), Check("could not ask", UNKNOWN)])
        assert not report.ready
        assert report.unknown

    def test_all_passes_is_ready(self):
        report = Readiness(part="x", checks=[Check("a", PASS), Check("b", PASS)])
        assert report.ready

    def test_blocked_is_not_ready(self):
        report = Readiness(part="x", checks=[Check("a", PASS), Check("b", BLOCKED)])
        assert not report.ready
        assert report.blocked


class TestTheChecksAnswerHonestly:
    def test_a_part_with_no_build_volume_reports_unknown_not_pass(self):
        report = assess(CORE, build_volume=None)
        fit = next(c for c in report.checks if c.name == "Fits the printer")
        assert fit.state == UNKNOWN

    def test_a_part_that_fits_passes(self):
        report = assess(CORE, build_volume=(220.0, 220.0, 250.0))
        fit = next(c for c in report.checks if c.name == "Fits the printer")
        assert fit.state == PASS

    def test_a_part_too_large_is_blocked_and_says_which_axis(self):
        report = assess(CORE, build_volume=(20.0, 220.0, 250.0))
        fit = next(c for c in report.checks if c.name == "Fits the printer")
        assert fit.state == BLOCKED
        assert "X" in fit.detail

    def test_contested_dimensions_block(self):
        """A part cannot be called ready while its own sources disagree about
        how big it is.

        `walls` and `tolerence` were contested only by `parts/datum`, the
        single-piece tray this part replaced; retiring it left the house
        constants unopposed. `board_y` is the one that survives, because the
        two sources that disagree about the board are both still live.
        """
        report = assess(CORE)
        disputed = next(c for c in report.checks if c.name == "No disputed dimensions")
        assert disputed.state == BLOCKED
        assert "board_y" in disputed.detail

    def test_print_settings_are_reported_when_declared(self):
        report = assess(CORE)
        settings = next(c for c in report.checks if c.name == "Print settings declared")
        assert settings.state == PASS
        assert "nozzle" in settings.detail

    def test_the_stub_check_actually_reads_the_assembly(self):
        """It once reported "no stubs remain" without looking, because
        `build()` returns a tuple and it read the tuple as an Assembly.

        The bench drives `datum_core` -- the compound that replaced the
        single-piece `parts/datum` and inherited its black-box seam -- so that
        is where the stubs surface.
        """
        report = assess(CORE)
        stubs = next(c for c in report.checks if c.name == "Fitted to measured artifacts")
        assert stubs.state == UNKNOWN
        assert "still guessed" in stubs.detail
        assert "board" in stubs.detail

    def test_a_part_the_assembly_does_not_place_is_not_told_about_its_stubs(self):
        """`calibration_cube` was reported as fitted to datum's board, because
        the check read the bench for every part in the library.
        """
        from apothecary.projects.parts.calibration_cube import DEFAULT as CUBE

        report = assess(CUBE)
        stubs = next(c for c in report.checks if c.name == "Fitted to measured artifacts")
        assert stubs.state == PASS
        assert "not fitted to a black box" in stubs.detail

    def test_every_non_passing_check_says_what_to_do(self):
        report = assess(CORE)
        for check in report.checks:
            if check.state != PASS:
                assert check.fix or check.detail, check.name


class TestBothPiecesAreAssessable:
    @pytest.mark.parametrize("part", [CORE, CAP], ids=["datum_core", "datum_cap"])
    def test_each_piece_produces_a_full_report(self, part):
        report = assess(part, build_volume=(220.0, 220.0, 250.0))
        assert report.part == part.name
        assert len(report.checks) >= 6


class TestServedFromTheOneEntryPoint:
    def test_the_endpoint_mirrors_the_command(self):
        body = client.get("/parts/datum_core/checklist").json()
        report = assess(CORE)
        assert body["ready"] is report.ready
        assert len(body["checks"]) == len(report.checks)

    def test_a_bad_build_volume_is_refused(self):
        assert client.get("/parts/datum_core/checklist?build_volume=nope").status_code == 422
        assert client.get("/parts/datum_core/checklist?build_volume=1,2").status_code == 422

    def test_an_unknown_part_is_404(self):
        assert client.get("/parts/no-such-part/checklist").status_code == 404

    def test_the_viewer_carries_it(self):
        """The checklist has to live where the parts do, or it is a second
        surface people have to remember to look at.
        """
        page = client.get("/viewer/sites/parts_library").text
        assert "loadPartChecklist" in page
        assert "part-checklist" in page


def _box_stl(path: Path, x: float, y: float, z: float) -> Path:
    """An STL whose extents are x by y by z: one triangle spans them."""
    meshes.write_stl([((0, 0, 0), (x, 0, 0), (0, y, z))], path)
    return path


@pytest.fixture
def core_stl_at(monkeypatch):
    """Point datum_core at an STL the test owns, never the one in parts/."""

    def point(stl: Path) -> Path:
        monkeypatch.setattr(type(CORE), "get_stl_output_path", lambda self: stl)
        return stl

    return point


class TestAStaleRenderIsNotDrift:
    """The wrapper counts as an input, not just the SCAD, and an out-of-date
    render is a render to redo, never a disagreement to investigate."""

    @pytest.fixture
    def stale(self, tmp_path, core_stl_at, monkeypatch):
        monkeypatch.setattr(readiness, "get_renderer", lambda: SimpleNamespace(is_available=True))
        stl = core_stl_at(_box_stl(tmp_path / "datum_core.stl", 1, 1, 1))
        os.utime(stl, (0, 0))  # older than anything in the repo
        return stl

    def test_a_render_older_than_its_wrapper_is_flagged_for_regeneration(self, stale):
        report = assess(CORE)
        renders = next(c for c in report.checks if c.name == "Geometry renders")
        assert renders.state == UNKNOWN
        assert "older than" in renders.detail
        assert "--force" in renders.fix

    def test_a_stale_render_never_reports_bounds_it_did_not_measure(self, stale):
        report = assess(CORE)
        bounds = [c for c in report.checks if c.name == BOUNDS]
        assert len(bounds) == 1, "the bounds check was added twice"
        assert bounds[0].state == UNKNOWN

    @pytest.mark.slow
    def test_a_current_render_still_passes(self, built_stl, core_stl_at):
        """The check must not cry stale at a render that is up to date."""
        core_stl_at(built_stl(CORE))
        report = assess(CORE)
        renders = next(c for c in report.checks if c.name == "Geometry renders")
        assert renders.state == PASS
        bounds = next(c for c in report.checks if c.name == BOUNDS)
        assert bounds.state == PASS, bounds.detail


class TestBoundsAreMeasuredFromTheMesh:
    """Declared bounds are for the default parameters, upright; the STL on disk
    may be neither, and a check that cannot compare says so."""

    @staticmethod
    def _part(tmp_path, rotation=(0, 0, 0)) -> BasePart:
        x, y, z = rotation
        return BasePart(
            name="box",
            source_file=tmp_path / "box.scad",
            default_bounds=BoundingBox3D(max_point=Vector3D(x=10, y=20, z=30)),
            display_rotation=Vector3D(x=x, y=y, z=z),
        )

    def _check(self, part) -> Check:
        return _bounds_check(part, part.get_stl_output_path(), tolerance=0.5)

    def test_a_render_the_declared_size_passes(self, tmp_path):
        part = self._part(tmp_path)
        _box_stl(part.get_stl_output_path(), 10, 20, 30.4)
        assert self._check(part).state == PASS

    def test_a_render_off_by_more_than_the_tolerance_is_blocked(self, tmp_path):
        part = self._part(tmp_path)
        _box_stl(part.get_stl_output_path(), 10, 20, 31)
        check = self._check(part)
        assert check.state == BLOCKED
        assert "off by 1.00 mm" in check.detail

    def test_a_render_with_overridden_parameters_is_not_compared(self, tmp_path):
        part = self._part(tmp_path)
        stl = _box_stl(part.get_stl_output_path(), 10, 20, 45)
        write_params_sidecar(stl, {"height": 45})
        check = self._check(part)
        assert check.state == UNKNOWN
        assert "height" in check.detail
        assert check.fix == "apothecary parts generate-stl box"

    def test_a_sidecar_recording_no_overrides_is_a_default_render(self, tmp_path):
        part = self._part(tmp_path)
        stl = _box_stl(part.get_stl_output_path(), 10, 20, 30)
        write_params_sidecar(stl, {})
        assert self._check(part).state == PASS

    def test_a_quarter_turned_render_is_held_to_the_turned_box(self, tmp_path):
        part = self._part(tmp_path, rotation=(90, 0, 0))
        _box_stl(part.get_stl_output_path(), 10, 30, 20)
        assert self._check(part).state == PASS

    def test_any_other_turn_is_not_compared(self, tmp_path):
        part = self._part(tmp_path, rotation=(45, 0, 0))
        _box_stl(part.get_stl_output_path(), 10, 20, 30)
        check = self._check(part)
        assert check.state == UNKNOWN
        assert check.fix == "apothecary parts verify box"

    def test_an_unreadable_stl_is_unknown_and_says_why(self, tmp_path):
        part = self._part(tmp_path)
        part.get_stl_output_path().write_text("solid box\n vertex 1 2 nope\nendsolid box\n")
        check = self._check(part)
        assert check.state == UNKNOWN
        assert "not a vertex" in check.detail

    def test_a_new_render_is_measured_again(self, tmp_path):
        part = self._part(tmp_path)
        stl = _box_stl(part.get_stl_output_path(), 10, 20, 30)
        os.utime(stl, ns=(0, 1_000_000_000))
        assert self._check(part).state == PASS
        _box_stl(stl, 10, 20, 31)
        os.utime(stl, ns=(0, 2_000_000_000))
        assert self._check(part).state == BLOCKED


class TestCompareBounds:
    def test_each_axis_is_held_to_the_tolerance(self):
        result = compare_bounds((10, 20, 30), (10.2, 19.5, 30), tol=0.5)
        assert result.deltas == pytest.approx((0.2, 0.5, 0))
        assert result.worst == pytest.approx(0.5)
        assert result.ok

    def test_one_axis_past_it_fails(self):
        assert not compare_bounds((10, 20, 30), (10, 20, 30.6), tol=0.5).ok


class TestThePartDecidesWhereItsStlLives:
    """`gridfinity`'s SCAD is inside a third-party submodule, and its wrapper
    overrides `get_stl_output_path` precisely so the render does not land in
    somebody else's checkout. Assuming `source_file.with_suffix('.stl')`
    looked in the wrong place — and the render that put it there left
    untracked content in that submodule.
    """

    def test_readiness_reads_the_path_the_part_names(self):
        from apothecary.cli.utils import _load_part_wrapper

        part = _load_part_wrapper("gridfinity").DEFAULT
        assert part.get_stl_output_path() != part.source_file.with_suffix(".stl")

        report = assess(part)
        renders = next(c for c in report.checks if c.name == "Geometry renders")
        # Either it is built or it is not, but the answer must come from the
        # path the part names, not from inside the submodule.
        assert renders.state in (PASS, UNKNOWN)
        assert "gridfinity-rebuilt-openscad" not in renders.detail

    def test_no_render_lands_inside_the_submodule(self):
        from apothecary.projects.parts.skeleton import ROOT

        submodule = ROOT / "parts" / "gridfinity" / "gridfinity-rebuilt-openscad"
        assert not list(submodule.glob("*.stl")), "a render landed in a third-party checkout"


def test_a_described_part_counts_its_part_json_as_a_source(tmp_path):
    """A described part's wrapper is its part.json; an edit there makes its render stale."""
    import importlib
    import os

    from apothecary.projects.parts.readiness import _sources_newer_than
    from apothecary.projects.parts.skeleton import ROOT
    from apothecary.projects.registry import scan_projects

    item = next(p for p in scan_projects(ROOT) if p.kind == "part" and p.name == "esp32_devkitc")
    part = importlib.import_module(item.wrapper).DEFAULT
    old_render = tmp_path / "old.stl"
    old_render.write_text("solid x\nendsolid x\n")
    os.utime(old_render, (0, 0))
    assert "part.json" in _sources_newer_than(part, old_render)
