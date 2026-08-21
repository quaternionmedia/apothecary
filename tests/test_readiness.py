"""Whether a part is ready to print, answered from what the repo already knows.

The rule the module turns on: an unanswered question is not a pass. A checklist
that ticks a box it could not check is worse than no checklist, and this module
shipped exactly that defect once -- it read `build()` as one object when it
returns two, so it reported "no stubs remain" for an assembly it had never
looked at.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from apothecary.api import app
from apothecary.projects.parts.datum_cap import DEFAULT as CAP
from apothecary.projects.parts.datum_core import DEFAULT as CORE
from apothecary.projects.parts.readiness import BLOCKED, PASS, UNKNOWN, Check, Readiness, assess

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
        """datum-core has three; a part cannot be called ready while its own
        sources disagree about how big it is.
        """
        report = assess(CORE)
        disputed = next(c for c in report.checks if c.name == "No disputed dimensions")
        assert disputed.state == BLOCKED
        assert "walls" in disputed.detail

    def test_print_settings_are_reported_when_declared(self):
        report = assess(CORE)
        settings = next(c for c in report.checks if c.name == "Print settings declared")
        assert settings.state == PASS
        assert "nozzle" in settings.detail

    def test_the_stub_check_actually_reads_the_assembly(self):
        """It once reported "no stubs remain" without looking, because
        `build()` returns a tuple and it read the tuple as an Assembly.

        The part the assembly actually drives is `parts/datum`, so that is
        where the stubs surface.
        """
        from apothecary.projects.parts.datum import DEFAULT as DATUM_PART

        report = assess(DATUM_PART)
        stubs = next(c for c in report.checks if c.name == "Fitted to measured artifacts")
        assert stubs.state == UNKNOWN
        assert "still guessed" in stubs.detail
        assert "board" in stubs.detail

    def test_a_part_the_assembly_does_not_place_is_not_told_about_its_stubs(self):
        """`calibration_cube` was reported as fitted to datum's board, because
        the check read the bench for every part in the library.
        """
        report = assess(CORE)
        stubs = next(c for c in report.checks if c.name == "Fitted to measured artifacts")
        assert stubs.state == PASS
        assert "not fitted to a black box" in stubs.detail

    def test_every_non_passing_check_says_what_to_do(self):
        report = assess(CORE)
        for check in report.checks:
            if check.state != PASS:
                assert check.fix or check.detail, check.name


class TestBothPiecesAreAssessable:
    @pytest.mark.parametrize("part", [CORE, CAP], ids=["datum-core", "datum-cap"])
    def test_each_piece_produces_a_full_report(self, part):
        report = assess(part, build_volume=(220.0, 220.0, 250.0))
        assert report.part == part.name
        assert len(report.checks) >= 6


class TestServedFromTheOneEntryPoint:
    def test_the_endpoint_mirrors_the_command(self):
        body = client.get("/parts/datum-core/checklist").json()
        report = assess(CORE)
        assert body["ready"] is report.ready
        assert len(body["checks"]) == len(report.checks)

    def test_a_bad_build_volume_is_refused(self):
        assert client.get("/parts/datum-core/checklist?build_volume=nope").status_code == 422
        assert client.get("/parts/datum-core/checklist?build_volume=1,2").status_code == 422

    def test_an_unknown_part_is_404(self):
        assert client.get("/parts/no-such-part/checklist").status_code == 404

    def test_the_viewer_carries_it(self):
        """The checklist has to live where the parts do, or it is a second
        surface people have to remember to look at.
        """
        page = client.get("/viewer/sites/parts_library").text
        assert "loadPartChecklist" in page
        assert "part-checklist" in page


class TestAStaleRenderIsNotDrift:
    """datum-core was reported as drifted by 1.2 mm. Nothing had drifted: the
    SCAD was untouched, the wrapper's `walls` default had moved to the house
    constant, and the STL on disk still answered the old question. A forced
    re-render put declared and measured at 46.8 exactly.

    So the wrapper counts as an input, not just the SCAD -- and an out-of-date
    render is a render to redo, never a disagreement to investigate.
    """

    def test_a_render_older_than_its_wrapper_is_flagged_for_regeneration(self):
        import os

        stl = CORE.get_stl_output_path()
        if not stl.exists():
            pytest.skip("datum-core is not built here")
        was = (stl.stat().st_atime, stl.stat().st_mtime)
        try:
            os.utime(stl, (was[0], 0))  # older than anything in the repo
            report = assess(CORE)
            renders = next(c for c in report.checks if c.name == "Geometry renders")
            assert renders.state == UNKNOWN
            assert "older than" in renders.detail
            assert "--force" in renders.fix
        finally:
            os.utime(stl, was)

    def test_a_stale_render_never_reports_bounds_it_did_not_measure(self):
        import os

        stl = CORE.get_stl_output_path()
        if not stl.exists():
            pytest.skip("datum-core is not built here")
        was = (stl.stat().st_atime, stl.stat().st_mtime)
        try:
            os.utime(stl, (was[0], 0))
            report = assess(CORE)
            bounds = [c for c in report.checks if c.name == "Declared bounds match geometry"]
            assert len(bounds) == 1, "the bounds check was added twice"
            assert bounds[0].state == UNKNOWN
        finally:
            os.utime(stl, was)

    def test_a_current_render_still_passes(self):
        stl = CORE.get_stl_output_path()
        if not stl.exists():
            pytest.skip("datum-core is not built here")
        report = assess(CORE)
        renders = next(c for c in report.checks if c.name == "Geometry renders")
        assert renders.state == PASS


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
        assert not list(submodule.glob("*.stl")), (
            "a render landed in a third-party checkout"
        )
