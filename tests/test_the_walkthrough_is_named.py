"""`apothecary test run` collects the runs that write walkthrough pages 11 and 12,
and not the run that writes a loop's page (14), which the browser suite writes."""

import subprocess
import sys
from pathlib import Path

import pytest

from apothecary.cli import testing
from apothecary.projects.parts.skeleton import ROOT

# The runs that write pages, and the test in each that does the writing.
DEMONSTRATION_MODULES = {
    Path(__file__).resolve().parent / "e2e" / "test_docs_photo_walkthrough.py": (
        "test_photographs_into_pieces"
    ),
    Path(__file__).resolve().parent / "e2e" / "test_docs_bench_walkthrough.py": (
        "test_the_bench_as_it_is"
    ),
}


def test_the_command_collects_the_run_that_writes_the_page():
    """Collection, not the argv's text: the marker expression is what selects the run."""
    collected = subprocess.run(
        testing.run_command() + ["--collect-only"], cwd=ROOT, capture_output=True, text=True
    )
    assert collected.returncode == 0, collected.stderr[-2000:]
    for module, run in DEMONSTRATION_MODULES.items():
        assert run in collected.stdout, f"`test run` does not collect {module.name}::{run}"


def test_the_command_supplies_what_the_demonstration_needs():
    """The demonstration drives a browser against a real server."""
    assert "--start-server" in testing.run_command()


def test_the_demonstration_is_not_a_docs_workflow():
    """`docs`-marked runs render into docs/generated/, a second page about the same path."""
    argv = [sys.executable, "-m", "pytest", "--collect-only", "-m", "docs", *DEMONSTRATION_MODULES]
    collected = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True)
    assert collected.returncode == pytest.ExitCode.NO_TESTS_COLLECTED, collected.stdout[-2000:]


# A loop's page is written by the browser suite only, so `apothecary test run`
# stays quick (docs/plans/ui-flows-2026-10-08.md, decided with the owner): its
# run is marked e2e and not walkthrough.
LOOP_PAGES = {
    Path(__file__).resolve().parent / "e2e" / "test_part_loop.py": (
        "test_designing_a_part_twice_round"
    ),
}


def test_a_loops_page_is_written_by_the_browser_suite_only():
    def collected(argv):
        done = subprocess.run(argv + ["--collect-only"], cwd=ROOT, capture_output=True, text=True)
        assert done.returncode == 0, done.stderr[-2000:]
        return done.stdout

    quick, suite = collected(testing.run_command()), collected(testing.run_command(e2e=True))
    for module, run in LOOP_PAGES.items():
        assert run not in quick, f"`test run` collects {module.name}::{run}"
        assert run in suite, f"the browser suite does not collect {module.name}::{run}"
