"""`apothecary test run` collects the runs that write walkthrough pages 11 and 12; page
13's run, the loop from a picture to a print, is the browser suite's alone, so the
quick run stays quick (the owner's answer of 2026-10-10), and CI's browser shards
write it and check it against what is committed."""

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

# The runs that write pages from the browser suite only, and the test in each.
BROWSER_SUITE_ONLY = {
    Path(__file__).resolve().parent / "e2e" / "test_picture_to_print.py": (
        "test_a_picture_to_a_print_twice"
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
    for module, run in BROWSER_SUITE_ONLY.items():
        assert run not in collected.stdout, f"`test run` collects {module.name}::{run}"


def test_the_browser_suite_collects_the_runs_that_write_pages_of_their_own():
    """The browser suite (`pytest tests/e2e`, what CI's shards run before checking the
    committed walkthrough) collects page 13's run, unmarked as a docs workflow."""
    argv = [sys.executable, "-m", "pytest", "--collect-only", *BROWSER_SUITE_ONLY]
    collected = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True)
    assert collected.returncode == 0, collected.stderr[-2000:]
    for module, run in BROWSER_SUITE_ONLY.items():
        assert run in collected.stdout, f"the browser suite does not collect {module.name}::{run}"
    docs = subprocess.run([*argv, "-m", "docs"], cwd=ROOT, capture_output=True, text=True)
    assert docs.returncode == pytest.ExitCode.NO_TESTS_COLLECTED, docs.stdout[-2000:]


def test_the_command_supplies_what_the_demonstration_needs():
    """The demonstration drives a browser against a real server."""
    assert "--start-server" in testing.run_command()


def test_the_demonstration_is_not_a_docs_workflow():
    """`docs`-marked runs render into docs/generated/, a second page about the same path."""
    argv = [sys.executable, "-m", "pytest", "--collect-only", "-m", "docs", *DEMONSTRATION_MODULES]
    collected = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True)
    assert collected.returncode == pytest.ExitCode.NO_TESTS_COLLECTED, collected.stdout[-2000:]
