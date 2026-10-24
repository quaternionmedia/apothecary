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


# What a browser job spends before its tests, at most: checkout, sync and a Chromium
# installed with nothing cached took five and a half minutes on a run. The tests
# themselves ran faster there than durations.json records them here.
JOB_SETUP_S = 330


def test_each_test_has_a_limit_above_the_slowest_that_a_shard_can_spend_within_its_job():
    """pytest-timeout's limit (pyproject's ``timeout``) fails a test that has stopped,
    alone: above twice the slowest test the browser suite records, and short enough
    that a job's setup, the heaviest shard's recorded time and one test hung to the
    limit are still inside the shortest CI job's limit, so the job reaches the
    timeout's traceback, which names the test, rather than being cancelled first."""
    import json
    import re
    import tomllib

    sys.path.insert(0, str(ROOT / "tests" / "e2e"))
    from shards import shard_of

    limit = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["tool"]["pytest"][
        "ini_options"
    ]["timeout"]
    recorded = json.loads((ROOT / "tests" / "e2e" / "durations.json").read_text())
    workflow = (ROOT / ".github" / "workflows" / "pytest.yml").read_text(encoding="utf-8")
    job = min(int(m) for m in re.findall(r"timeout-minutes: (\d+)", workflow)) * 60
    (shards,) = {int(n) for n in re.findall(r'--shard "\$SHARD"/(\d+)', workflow)}
    files: dict = {}
    for nodeid, seconds in recorded.items():
        path = nodeid.split("::", 1)[0]
        files[path] = files.get(path, 0.0) + seconds
    load = [0.0] * shards
    for path, shard in shard_of(files, shards).items():
        load[shard] += files[path]
    assert 2 * max(recorded.values()) < limit, (max(recorded.values()), limit)
    assert JOB_SETUP_S + max(load) + limit < job, (JOB_SETUP_S, max(load), limit, job)
