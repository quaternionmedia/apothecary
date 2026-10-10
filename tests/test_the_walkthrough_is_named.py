"""`apothecary test run` collects the runs that write walkthrough pages 11 and 12,
and not the runs that write a loop's page (13, 14, 15), which the browser suite
writes: CI's browser shards write them and check them against what is committed."""

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
# `apothecary test run` stays quick: its test is marked e2e and not walkthrough, and
# passes browser_suite_only=True to the walkthrough fixture, which says so in the page.
LOOP_PAGES = {
    Path(__file__).resolve().parent / "e2e" / "test_picture_to_print.py": (
        "test_a_picture_to_a_print_twice",
        ROOT / "walkthrough" / "13-a-picture-to-a-print.md",
    ),
    Path(__file__).resolve().parent / "e2e" / "test_part_loop.py": (
        "test_designing_a_part_twice_round",
        ROOT / "walkthrough" / "14-designing-a-part.md",
    ),
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
        # The page says who writes it, and how to run it alone.
        text = page.read_text(encoding="utf-8")
        assert "rewritten by every run of the browser suite" in text, page.name
        assert f"uv run pytest {module.relative_to(ROOT).as_posix()} --start-server" in text


def test_the_command_supplies_what_the_demonstration_needs():
    """The demonstration drives a browser against a real server."""
    assert "--start-server" in testing.run_command()


def test_the_demonstration_is_not_a_docs_workflow():
    """`docs`-marked runs render into docs/generated/, a second page about the same path."""
    argv = [
        sys.executable,
        "-m",
        "pytest",
        "--collect-only",
        "-m",
        "docs",
        *DEMONSTRATION_MODULES,
        *LOOP_PAGES,
    ]
    collected = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True)
    assert collected.returncode == pytest.ExitCode.NO_TESTS_COLLECTED, collected.stdout[-2000:]
