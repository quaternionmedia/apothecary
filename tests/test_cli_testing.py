"""`apothecary test` exits with the code pytest exits with."""

import os
import subprocess
import sys

import pytest
from click.testing import CliRunner

from apothecary.cli import cli, testing
from apothecary.projects.parts.skeleton import ROOT


@pytest.fixture
def pytest_exits(monkeypatch):
    """Stand in for pytest: each run returns the next code given, and its argv is kept."""

    def exits_with(*codes: int) -> list[list[str]]:
        ran, remaining = [], list(codes)

        def run(argv, **kwargs):
            ran.append(argv)
            return subprocess.CompletedProcess(argv, remaining.pop(0))

        monkeypatch.setattr(testing.subprocess, "run", run)
        return ran

    return exits_with


def _args(argv: list[str]) -> list[str]:
    """What follows `python -m pytest`."""
    return argv[3:]


def test_run_is_two_pytests_the_browser_part_in_its_own():
    """The unit suite, then the walkthrough's browser runs in a process of their own:
    a browser test leaves an event loop running that a unit test after it cannot share."""
    unit, browser = testing.run_commands()
    assert _args(unit) == ["-q", "walkthrough", "tests", "--ignore=tests/e2e"]
    assert _args(browser) == ["-q", "tests/e2e", "--start-server", "-m", "walkthrough or windows"]
    assert _args(testing.browser_command(every=True)) == ["-q", "tests/e2e", "--start-server"]
    slow, _ = testing.run_commands(slow=True)
    assert slow[-1] == "--slow"


@pytest.mark.parametrize(
    ("unit", "browser", "code"),
    [(0, 0, 0), (1, 0, 1), (0, 1, 1), (2, 1, 2), (0, 5, 0), (5, 0, 0), (5, 5, 5), (5, 1, 1)],
)
def test_run_exits_with_the_first_failure(pytest_exits, unit, browser, code):
    ran = pytest_exits(unit, browser)
    result = CliRunner().invoke(cli, ["test", "run", "-x"])
    assert result.exit_code == code
    assert ran == [argv + ["-x"] for argv in testing.run_commands()]


@pytest.mark.parametrize(
    ("unit", "browser", "code"), [(0, 0, 0), (1, 0, 1), (0, 5, 0), (5, 5, 5), (2, 1, 2)]
)
def test_all_runs_both_phases_and_exits_with_the_first_failure(pytest_exits, unit, browser, code):
    ran = pytest_exits(unit, browser)
    result = CliRunner().invoke(cli, ["test", "all"])
    assert result.exit_code == code
    assert [_args(argv) for argv in ran] == [
        ["-q", "walkthrough", "tests", "--ignore=tests/e2e"],
        ["-q", "tests/e2e", "--start-server"],
    ]


@pytest.mark.parametrize(
    ("given", "unit_extra", "browser_extra"),
    [
        ([], [], []),
        (["-k", "part"], ["-k", "part"], ["-k", "part"]),
        (["--workers", "2"], [], ["-n", "2", "--dist", "loadfile"]),
        (["--workers", "3", "-x"], ["-x"], ["-n", "3", "--dist", "loadfile", "-x"]),
    ],
    ids=["defaults", "pytest-args-to-both", "workers", "workers-and-pytest-args"],
)
def test_all_takes_workers_and_hands_the_rest_to_pytest(
    pytest_exits, given, unit_extra, browser_extra
):
    ran = pytest_exits(0, 0)
    assert CliRunner().invoke(cli, ["test", "all", *given]).exit_code == 0
    assert [_args(argv) for argv in ran] == [
        ["-q", "walkthrough", "tests", "--ignore=tests/e2e", *unit_extra],
        ["-q", "tests/e2e", "--start-server", *browser_extra],
    ]


def test_run_e2e_names_test_all(pytest_exits):
    ran = pytest_exits()
    result = CliRunner().invoke(cli, ["test", "run", "--e2e"])
    assert result.exit_code == 1
    assert "use `apothecary test all`" in result.output
    assert ran == []


def test_help_says_what_run_and_all_each_do():
    said = " ".join(CliRunner().invoke(cli, ["test", "--help"]).output.split())
    assert "apothecary test run" in said and "apothecary test all" in said
    assert "every browser test" in said
    assert "uv run playwright install chromium" in said


@pytest.mark.parametrize("name", ["setup-e2e", "validate-e2e", "run-e2e"])
def test_a_retired_subcommand_names_its_replacement_and_fails(name):
    result = CliRunner().invoke(cli, ["test", name, "--headed"])
    assert result.exit_code == 1
    assert "is retired; use `" in result.output


# Playwright's own words when the browser is missing, which tests/e2e/browsers.py reads.
NO_BROWSER = """
import sys
sys.path.insert(0, "tests/e2e")
from _pytest.outcomes import Exit
from playwright.sync_api import sync_playwright
from browsers import launch
with sync_playwright() as p:
    try:
        launch(p.chromium).close()
    except Exit as stopped:
        print(stopped.msg)
"""


def test_without_chromium_the_browser_part_says_how_to_install_it_in_one_line(tmp_path):
    """With nowhere holding a browser, the run stops on the one line, not Playwright's box."""
    env = {**os.environ, "PLAYWRIGHT_BROWSERS_PATH": str(tmp_path / "none")}
    done = subprocess.run(
        [sys.executable, "-c", NO_BROWSER], cwd=ROOT, env=env, capture_output=True, text=True
    )
    assert done.returncode == 0, done.stderr[-2000:]
    assert done.stdout.strip().splitlines() == [
        "the browser tests need Chromium, which Playwright has not installed here: "
        "run `uv run playwright install chromium`"
    ]


def test_changed_runs_the_unit_part_then_the_browser_files_the_change_reaches():
    """A change to a board's code reaches the machine area's files alone; one to the
    page reaches every browser file; one that reaches no area runs the unit part alone."""
    unit, browser = testing.changed_commands(["apothecary/firmware/gcode.py"])
    assert unit == testing.unit_command()
    files = [a for a in _args(browser) if a.startswith("tests/e2e/")]
    assert "tests/e2e/test_one_machine.py" in files and "tests/e2e/test_ring.py" not in files
    assert _args(browser)[-1] == "--start-server"
    _, every = testing.changed_commands(["templates/fractal_viewer.html.j2"], workers=3)
    assert _args(every) == ["-q", "tests/e2e", "--start-server", "-n", "3", "--dist", "loadfile"]
    assert testing.changed_commands(["docs/viewer.md"]) == [testing.unit_command()]


def test_changed_exits_with_the_first_failing_code_and_lists_without_running(
    pytest_exits, monkeypatch
):
    monkeypatch.setattr(testing, "changed_paths", lambda since: ["apothecary/lighting.py"])
    ran = pytest_exits(0, 1)
    done = CliRunner().invoke(cli, ["test", "changed"])
    assert done.exit_code == 1 and len(ran) == 2
    assert "tests/e2e/test_lighting_overlay.py" in _args(ran[1])
    listed = CliRunner().invoke(cli, ["test", "changed", "--list"])
    assert listed.exit_code == 0 and listed.output.strip() == "tests/e2e/test_lighting_overlay.py"
    assert len(ran) == 2  # --list ran nothing


def test_changed_says_what_to_name_when_there_is_nothing_to_compare_with():
    done = CliRunner().invoke(cli, ["test", "changed", "--list", "--since", "no-such-ref-here"])
    assert done.exit_code != 0 and "name a ref with --since" in done.output
