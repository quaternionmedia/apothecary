"""`apothecary test`: run the suite with pytest and exit with pytest's own code.

Click ignores a command's return value, so each command exits through SystemExit.

Each command runs two pytests, one after the other: the unit suite with the
walkthrough's pages, then the browser part. Two processes, not one: a browser
test leaves Playwright's event loop running, and a unit test after it in the
same process that starts a loop of its own is refused ("asyncio.run() cannot be
called from a running event loop").
"""

import importlib.util
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


# The browser tests the ordinary command runs: the walkthrough's demonstration, and
# the window manager on a page of its own, which starts no server.
ORDINARY_BROWSER = "walkthrough or windows"


def browser_command(every: bool = False, workers: int = 1) -> list[str]:
    """The browser part on a server of its own: the walkthrough's runs and the window
    manager's (ORDINARY_BROWSER), or with ``every`` every browser test; with
    ``workers`` above one, that many in parallel, a file's tests together."""
    argv = _pytest_argv(BROWSER, "--start-server")
    if not every:
        argv += ["-m", ORDINARY_BROWSER]
    if workers > 1:
        argv += ["-n", str(workers), "--dist", "loadfile"]
    return argv


def run_commands(slow: bool = False) -> list[list[str]]:
    """The argvs `apothecary test run` executes, one pytest each, in order."""
    return [unit_command(slow=slow), browser_command()]


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


HELP = """Run the test suite, exiting as pytest does.

\b
  apothecary test run   the ordinary command: the unit tests and the
                        walkthrough, its browser part -- the walkthrough's
                        demonstration and the window manager -- in a pytest of
                        its own
  apothecary test all   the same, then every browser test (--workers N in
                        parallel; further arguments go to pytest)
  apothecary test changed
                        while working: the unit tests and the walkthrough, then
                        the browser files of the areas a change reaches (--since
                        REF; the branch's upstream by default)
  uv run pytest         the quick inner loop, browser tests skipped

The walkthrough's demonstration and every browser test drive Chromium:
`uv run playwright install chromium` once per machine. CONTRIBUTING.md has the rest.
"""


@click.group(help=HELP, short_help="Run the tests: `test run` is the ordinary command.")
def test():
    pass


def _every_browser_test_is_test_all(ctx, param, value):
    if value:
        raise click.ClickException(
            "`apothecary test run --e2e` is retired; use `apothecary test all`"
        )
    return value


@test.command("run", context_settings={"ignore_unknown_options": True})
@click.option(
    "--slow", is_flag=True, help="Also run tests marked slow (full renders, accuracy benches)."
)
# Every browser test is `test all`'s; the flag stays, hidden, to say so.
@click.option(
    "--e2e", is_flag=True, hidden=True, expose_value=False, callback=_every_browser_test_is_test_all
)
@click.argument("pytest_args", nargs=-1, type=click.UNPROCESSED)
def test_run(slow: bool, pytest_args: tuple[str, ...]):
    """The ordinary command: the unit tests and the walkthrough, whose demonstration
    drives Chromium in a pytest of its own; further arguments go to pytest.

    They go to both pytests, and it exits with the first failing code; a part that
    selects no test is not a failure when the other ran some.
    """
    codes = [_pytest(argv + list(pytest_args)) for argv in run_commands(slow=slow)]
    raise SystemExit(_first_failure(codes))


@test.command("all", context_settings={"ignore_unknown_options": True})
@click.option(
    "--slow", is_flag=True, help="Also run unit tests marked slow (full renders, accuracy benches)."
)
@click.option(
    "--workers",
    type=click.IntRange(min=1),
    default=1,
    show_default=True,
    help="Browser tests in parallel, a file's tests together (pytest-xdist).",
)
@click.argument("pytest_args", nargs=-1, type=click.UNPROCESSED)
def test_all(slow: bool, workers: int, pytest_args: tuple[str, ...]):
    """The unit tests and the walkthrough, then every browser test in a pytest of its
    own, on a server of its own (--start-server); further arguments go to pytest, to
    both, as `test run`'s do (`-k part` narrows each). --record-durations, passed
    through, writes the browser tests' times into tests/e2e/durations.json, which
    the shards are balanced by; --steps runs the step-through tests too, which skip
    otherwise."""
    codes = [
        _pytest(unit_command(slow=slow) + list(pytest_args)),
        _pytest(browser_command(every=True, workers=workers) + list(pytest_args)),
    ]
    raise SystemExit(_first_failure(codes))


for _name, _instead in (
    ("setup-e2e", "use `uv run playwright install chromium`"),
    ("validate-e2e", "use `apothecary test all`"),
    ("run-e2e", "use `apothecary test all`"),
):
    test.add_command(retired(f"test {_name}", _instead), name=_name)


def _areas():
    """The browser suite's areas (tests/e2e/areas.py): a checkout's, not the package's."""
    spec = importlib.util.spec_from_file_location("areas", ROOT / BROWSER / "areas.py")
    areas = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(areas)
    return areas


def changed_paths(since: str | None) -> list[str]:
    """What this checkout changes against ``since`` -- the branch's upstream when not
    given, so what is not pushed yet -- committed or not, with the files it adds."""
    ref = since or "@{upstream}"
    diff = subprocess.run(
        ["git", "diff", "--name-only", ref], cwd=ROOT, capture_output=True, text=True
    )
    if diff.returncode != 0:
        raise click.ClickException(
            f"cannot compare with {ref}: {diff.stderr.strip()} -- name a ref with --since"
        )
    added = subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    return sorted(set(diff.stdout.split()) | set(added.stdout.split()))


def changed_commands(changed: list[str], workers: int = 1) -> list[list[str]]:
    """The argvs `apothecary test changed` runs: the unit suite with the walkthrough, then
    the browser files the change reaches, if it reaches any."""
    areas = _areas()
    reached = areas.reached(changed)
    commands = [unit_command()]
    browser = [BROWSER] if reached == areas.ALL else reached
    if browser:
        argv = _pytest_argv(*browser, "--start-server")
        if workers > 1:
            argv += ["-n", str(workers), "--dist", "loadfile"]
        commands.append(argv)
    return commands


@test.command("changed", context_settings={"ignore_unknown_options": True})
@click.option("--since", default=None, help="The ref to compare with (default: the upstream).")
@click.option(
    "--list",
    "only_list",
    is_flag=True,
    help="Name the browser files the change reaches, and run nothing.",
)
@click.option(
    "--workers",
    type=click.IntRange(min=1),
    default=1,
    show_default=True,
    help="Browser tests in parallel, a file's tests together (pytest-xdist).",
)
@click.argument("pytest_args", nargs=-1, type=click.UNPROCESSED)
def test_changed(since: str | None, only_list: bool, workers: int, pytest_args: tuple[str, ...]):
    """The unit tests and the walkthrough, then the browser files of the areas a change
    reaches (tests/e2e/areas.py): every browser file when it touches shared ground, a
    browser file itself when it changes, none when it reaches no area. The change is
    what this checkout holds against --since, uncommitted and new files included;
    without it, against the branch's upstream. It is for while working: the run before
    a merge is `test all`'s, the whole suite."""
    changed = changed_paths(since)
    if only_list:
        areas = _areas()
        reached = areas.reached(changed)
        if reached == areas.ALL:
            click.echo(f"every browser file ({BROWSER}): the change touches shared ground")
        else:
            click.echo("\n".join(reached) if reached else "no browser file")
        return
    commands = changed_commands(changed, workers=workers)
    codes = [_pytest(argv + list(pytest_args)) for argv in commands]
    raise SystemExit(_first_failure(codes))
