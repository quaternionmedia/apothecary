"""`apothecary test`: run the suite with pytest and exit with pytest's own code.

Click ignores a command's return value, so each command exits through SystemExit.
"""

import subprocess
import sys

import click

from ..projects.parts.skeleton import ROOT
from .retired import retired

# Named on every argv: pytest ignores testpaths once it is given a path.
WALKTHROUGH = "walkthrough"


def run_command(e2e: bool = False, slow: bool = False) -> list[str]:
    """The argv `apothecary test run` executes."""
    # The walkthrough's demonstration drives a browser, so the server is always asked for.
    argv = [sys.executable, "-m", "pytest", WALKTHROUGH, "tests", "--start-server"]
    if not e2e:
        argv += ["-m", "not e2e or walkthrough"]
    if slow:
        argv.append("--slow")
    return argv


def _pytest(argv: list[str]) -> int:
    return subprocess.run(argv, cwd=ROOT).returncode


@click.group()
def test():
    """Run the test suite."""


@test.command("run", context_settings={"ignore_unknown_options": True})
@click.option("--e2e", is_flag=True, help="Run every browser test, not only the walkthrough's.")
@click.option("--slow", is_flag=True, help="Also run tests marked slow.")
@click.argument("pytest_args", nargs=-1, type=click.UNPROCESSED)
def test_run(e2e: bool, slow: bool, pytest_args: tuple[str, ...]):
    """Unit tests and the walkthrough; any further arguments go to pytest."""
    raise SystemExit(_pytest(run_command(e2e=e2e, slow=slow) + list(pytest_args)))


@test.command("all")
@click.option("--slow", is_flag=True, help="Also run unit tests marked slow.")
def test_all(slow: bool):
    """Unit tests and the walkthrough, then every browser test."""
    unit = [sys.executable, "-m", "pytest", WALKTHROUGH, "tests", "--ignore=tests/e2e"]
    if slow:
        unit.append("--slow")
    unit_code = _pytest(unit)
    browser_code = _pytest([sys.executable, "-m", "pytest", "tests/e2e", "--start-server"])
    raise SystemExit(unit_code or browser_code)


for _name, _instead in (
    ("setup-e2e", "use `uv run playwright install chromium`"),
    ("validate-e2e", "use `apothecary test run --e2e`"),
    ("run-e2e", "use `apothecary test run --e2e`"),
):
    test.add_command(retired(f"test {_name}", _instead), name=_name)
