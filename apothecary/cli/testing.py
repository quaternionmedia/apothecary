"""`apothecary test`: run the suite with pytest and exit with pytest's own code.

Click ignores a command's return value, so each command exits through SystemExit.

Each command runs two pytests, one after the other: the unit suite with the
walkthrough's pages, then the browser part. Two processes, not one: a browser
test leaves Playwright's event loop running, and a unit test after it in the
same process that starts a loop of its own is refused ("asyncio.run() cannot be
called from a running event loop").
"""

import subprocess
import sys

import click

from ..projects.parts.skeleton import ROOT
from .retired import retired

# Named on every argv: pytest ignores testpaths once it is given a path.
WALKTHROUGH = "walkthrough"
BROWSER = "tests/e2e"


def _pytest_argv(*args: str) -> list[str]:
    # -q: the dots and the summary line; pyproject's addopts leaves the verbosity alone.
    return [sys.executable, "-m", "pytest", "-q", *args]


def unit_command(slow: bool = False) -> list[str]:
    """The unit suite and the walkthrough's pages, without a browser."""
    argv = _pytest_argv(WALKTHROUGH, "tests", f"--ignore={BROWSER}")
    if slow:
        argv.append("--slow")
    return argv


def browser_command(every: bool = False) -> list[str]:
    """The browser part on a server of its own: the walkthrough's runs (those marked
    `walkthrough`), or with ``every`` every browser test."""
    argv = _pytest_argv(BROWSER, "--start-server")
    if not every:
        argv += ["-m", "walkthrough"]
    return argv


def run_commands(e2e: bool = False, slow: bool = False) -> list[list[str]]:
    """The argvs `apothecary test run` executes, one pytest each, in order."""
    return [unit_command(slow=slow), browser_command(every=e2e)]


def _pytest(argv: list[str]) -> int:
    return subprocess.run(argv, cwd=ROOT).returncode


# pytest's exit code when it collected nothing (pytest.ExitCode.NO_TESTS_COLLECTED).
NO_TESTS = 5


def _first_failure(codes: list[int]) -> int:
    """The first code that is not a pass. A part that collected nothing is a pass
    when another part ran tests -- `test run -k cli` selects no browser test -- and
    the run's code when none did."""
    ran = [code for code in codes if code != NO_TESTS]
    if not ran:
        return NO_TESTS
    return next((code for code in ran if code != 0), 0)


HELP = """Run the test suite: `run` is the ordinary command, `all` the whole of it.

\b
  apothecary test run    the unit tests and the walkthrough, then the
                         walkthrough's browser part in a pytest of its own
  apothecary test all    the same, then every browser test
  uv run pytest -q       the quick inner loop: unit tests and the walkthrough's
                         pages; browser tests skip

The browser part needs Chromium: `uv run playwright install chromium`.
"""


@click.group(help=HELP)
def test():
    pass


@test.command("run", context_settings={"ignore_unknown_options": True})
@click.option("--e2e", is_flag=True, help="Run every browser test, not only the walkthrough's.")
@click.option("--slow", is_flag=True, help="Also run tests marked slow.")
@click.argument("pytest_args", nargs=-1, type=click.UNPROCESSED)
def test_run(e2e: bool, slow: bool, pytest_args: tuple[str, ...]):
    """The ordinary test command: the unit tests and the walkthrough, then the
    walkthrough's browser part (pages 11 and 12) in a pytest of its own, on a
    server of its own.

    Further arguments go to both pytests. Exits with the first failing code;
    a part that selects no test is not a failure when the other ran some.
    """
    codes = [_pytest(argv + list(pytest_args)) for argv in run_commands(e2e=e2e, slow=slow)]
    raise SystemExit(_first_failure(codes))


@test.command("all")
@click.option("--slow", is_flag=True, help="Also run unit tests marked slow.")
def test_all(slow: bool):
    """Everything: the unit tests and the walkthrough, then every browser test,
    loops' pages 13 to 16 among them, in a pytest of its own. What CI runs, on
    one machine."""
    unit_code = _pytest(unit_command(slow=slow))
    browser_code = _pytest(browser_command(every=True))
    raise SystemExit(unit_code or browser_code)


for _name, _instead in (
    ("setup-e2e", "use `uv run playwright install chromium`"),
    ("validate-e2e", "use `apothecary test all`"),
    ("run-e2e", "use `apothecary test all`"),
):
    test.add_command(retired(f"test {_name}", _instead), name=_name)
