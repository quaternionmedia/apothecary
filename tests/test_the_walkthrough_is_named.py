"""`apothecary test run` collects the runs that write walkthrough pages 01 and 02,
and not the runs that write a loop's page (03, 04, 05, 06), which the browser suite
writes: CI's browser shards write them and check them against what is committed."""

import functools
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


@functools.cache
def _begun(argv: tuple[str, ...]) -> subprocess.Popen:
    """One pytest's collection, begun once per command for the module's tests."""
    return subprocess.Popen(
        [*argv, "--collect-only"],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


@functools.cache
def _ended(argv: tuple[str, ...]) -> tuple[int, str, str]:
    """That collection's exit code, listing and errors, once it has ended."""
    begun = _begun(argv)
    out, err = begun.communicate()
    return begun.returncode, out, err


def _listing(argv: tuple[str, ...]) -> str:
    code, out, err = _ended(argv)
    assert code == 0, out[-2000:] + err[-2000:]
    return out


def _collected(every: bool = False) -> str:
    """What the browser part of `apothecary test run` collects (with ``every``, of `test
    all`). The unit part ignores tests/e2e, which the test below holds, so it collects
    none of the runs these tests name, and is not collected here."""
    _, browser = testing.run_commands()
    if every:
        browser = testing.browser_command(every=True)
    return _listing(tuple(browser))


def _named(module: Path, run: str) -> str:
    """A run's node id as a listing prints it, from the root."""
    return f"{module.relative_to(ROOT).as_posix()}::{run}"


def test_the_command_collects_the_run_that_writes_the_page():
    """Collection, not the argv's text: the marker expression is what selects the run."""
    collected = _collected()
    for module, run in DEMONSTRATION_MODULES.items():
        named = _named(module, run)
        assert named in collected, f"`test run` does not collect {named}"


# A loop's page is written by the browser suite alone, so
# `apothecary test run` stays quick: its test is marked e2e and not walkthrough, and
# passes browser_suite_only=True to the walkthrough fixture, which says so in the page.
LOOP_PAGES = {
    Path(__file__).resolve().parent / "e2e" / "test_picture_to_print.py": (
        "test_a_picture_to_a_print_twice",
        ROOT / "walkthrough" / "03-a-picture-to-a-print.md",
    ),
    Path(__file__).resolve().parent / "e2e" / "test_part_loop.py": (
        "test_designing_a_part_twice_round",
        ROOT / "walkthrough" / "04-designing-a-part.md",
    ),
    Path(__file__).resolve().parent / "e2e" / "test_the_firmware_loop.py": (
        "test_the_firmware_loop_goes_round_with_arduino_then_rust",
        ROOT / "walkthrough" / "05-firmware.md",
    ),
    Path(__file__).resolve().parent / "e2e" / "test_scad_loop.py": (
        "test_editing_a_parts_scad_twice_round",
        ROOT / "walkthrough" / "06-editing-a-parts-scad.md",
    ),
    Path(__file__).resolve().parent / "e2e" / "test_whiteboard_round_twice.py": (
        "test_a_whiteboard_to_a_model_round_twice",
        ROOT / "walkthrough" / "30-a-whiteboard-round-twice-through-the-page.md",
    ),
    Path(__file__).resolve().parent / "e2e" / "test_working_space.py": (
        "test_the_working_space_from_each_of_its_doors",
        ROOT / "walkthrough" / "18-the-working-space.md",
    ),
}


def test_a_loop_s_page_is_written_by_the_browser_suite_alone():
    quick, browser = _collected(), _collected(every=True)
    for module, (run, page) in LOOP_PAGES.items():
        named = _named(module, run)
        assert named not in quick, f"`test run` collects {named}"
        assert named in browser, f"`test all` does not collect {named}"
        assert page.is_file(), f"{page.name} is not written"
        # The page says who writes it, and how to run it alone.
        text = page.read_text(encoding="utf-8")
        assert "rewritten by every run of the browser suite" in text, page.name
        assert f"uv run pytest {module.relative_to(ROOT).as_posix()} --start-server" in text


def test_the_command_supplies_what_the_demonstration_needs():
    """The demonstration drives a browser against a real server, in a pytest of its own."""
    unit, browser = testing.run_commands()
    assert "--start-server" in browser
    assert "--ignore=tests/e2e" in unit


# The `docs`-marked runs among the modules that write pages.
DOCS = (
    sys.executable,
    "-m",
    "pytest",
    "-m",
    "docs",
    *map(str, [*DEMONSTRATION_MODULES, *LOOP_PAGES]),
)


@pytest.fixture(autouse=True, scope="module")
def _collections_begun_together():
    """Each collection the tests read is a pytest of its own, and none waits on another:
    they are begun together, and each test reads the one it names."""
    _, browser = testing.run_commands()
    commands = [tuple(browser), tuple(testing.browser_command(every=True)), DOCS]
    for argv in commands:
        _begun(argv)
    yield
    for argv in commands:
        _ended(argv)


def test_the_demonstration_is_not_a_docs_workflow():
    """`docs`-marked runs render into docs/generated/, a second page about the same path."""
    code, out, _ = _ended(DOCS)
    assert code == pytest.ExitCode.NO_TESTS_COLLECTED, out[-2000:]
