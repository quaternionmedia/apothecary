"""`apothecary test run` collects the runs that write walkthrough pages 11 and 12."""

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


# A loop's page is written by the browser suite alone (the loops plan, 2026-10-10), so
# `apothecary test run` stays quick: its test is marked e2e and not walkthrough.
LOOP_PAGES = {
    Path(__file__).resolve().parent / "e2e" / "test_the_firmware_loop.py": (
        "test_the_firmware_loop_goes_round_with_arduino_then_rust",
        ROOT / "walkthrough" / "15-firmware.md",
    ),
}


def test_a_loop_s_page_is_written_by_the_browser_suite_alone():
    quick = subprocess.run(
        testing.run_command() + ["--collect-only"], cwd=ROOT, capture_output=True, text=True
    )
    assert quick.returncode == 0, quick.stderr[-2000:]
    browser = subprocess.run(
        testing.run_command(e2e=True) + ["--collect-only"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert browser.returncode == 0, browser.stderr[-2000:]
    for module, (run, page) in LOOP_PAGES.items():
        assert run not in quick.stdout, f"`test run` collects {module.name}::{run}"
        assert run in browser.stdout, f"`test run --e2e` does not collect {module.name}::{run}"
        assert page.is_file(), f"{page.name} is not written"


def test_the_command_supplies_what_the_demonstration_needs():
    """The demonstration drives a browser against a real server."""
    assert "--start-server" in testing.run_command()


def test_the_demonstration_is_not_a_docs_workflow():
    """`docs`-marked runs render into docs/generated/, a second page about the same path."""
    argv = [sys.executable, "-m", "pytest", "--collect-only", "-m", "docs", *DEMONSTRATION_MODULES]
    collected = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True)
    assert collected.returncode == pytest.ExitCode.NO_TESTS_COLLECTED, collected.stdout[-2000:]
