"""`apothecary test`: run the suite with pytest and exit with pytest's own code.

Click ignores a command's return value, so each command exits through SystemExit.

Each command that runs the suite runs two pytests, one after the other: the unit
suite with the walkthrough's pages, then the browser part. Two processes, not one: a browser
test leaves Playwright's event loop running, and a unit test after it in the
same process that starts a loop of its own is refused ("asyncio.run() cannot be
called from a running event loop").
"""

import importlib.util
import os
import subprocess
import sys

import click

from ..projects.parts.skeleton import ROOT
from . import coverage_summary
from .retired import retired

# Named on every argv: pytest ignores testpaths once it is given a path.
WALKTHROUGH = "walkthrough"
BROWSER = "tests/e2e"


def _pytest_argv(*args: str) -> list[str]:
    # -q: the dots and the summary line; pyproject's addopts leaves the verbosity alone.
    return [sys.executable, "-m", "pytest", "-q", *args]


# Tests in parallel: a file's tests on one worker, and a worker that crashes ends the
# run, its test named. One started in its place leaves xdist's loadfile scheduler
# waiting on the crashed file forever.
FILES_WHOLE = ["--dist", "loadfile", "--max-worker-restart", "0"]


def unit_command(slow: bool = False, files: list[str] | None = None, workers: int = 1) -> list[str]:
    """The walkthrough's pages and the unit suite, without a browser: every unit file, or
    only ``files`` (tests/groups.py's); with ``workers`` above one, that many in
    parallel, a file's tests together."""
    tests = ["tests", f"--ignore={BROWSER}"] if files is None else files
    argv = _pytest_argv(WALKTHROUGH, *tests)
    if workers > 1:
        argv += ["-n", str(workers), *FILES_WHOLE]
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
        argv += ["-n", str(workers), *FILES_WHOLE]
    return argv


# Every part measured into one data file: the unit part starts it, the browser part
# appends to it (pyproject's [tool.coverage.run] follows the server into its process).
COVERAGE = ["--cov", "--cov-report="]


def all_commands(slow: bool = False, workers: int = 1, coverage: bool = False) -> list[list[str]]:
    """The argvs `apothecary test all` executes, one pytest each, in order."""
    unit = unit_command(slow=slow, workers=workers)
    browser = browser_command(every=True, workers=workers)
    if coverage:
        unit += COVERAGE
        browser += [*COVERAGE, "--cov-append"]
    return [unit, browser]


def run_commands(slow: bool = False, workers: int = 1) -> list[list[str]]:
    """The argvs `apothecary test run` executes, one pytest each, in order: ``workers``
    runs the unit part in parallel; the walkthrough's demonstration is one browser."""
    return [unit_command(slow=slow, workers=workers), browser_command()]


def _pytest(argv: list[str], env: dict | None = None) -> int:
    return subprocess.run(argv, cwd=ROOT, env=env).returncode


def coverage_env() -> dict | None:
    """The environment a measured run's pytests -- and the server they start -- inherit.
    From Python 3.12 coverage measures through sys.monitoring, which costs the browser
    tests next to nothing; its older tracer doubles the server's time, and a window
    waited for misses its wait."""
    if sys.version_info < (3, 12):
        return None
    return {**os.environ, "COVERAGE_CORE": "sysmon"}


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
                        parallel; further arguments go to pytest); with
                        --coverage, what it covered
  apothecary test coverage
                        what the last `test all --coverage` covered: the
                        package's statements, and those the change adds or
                        changes (--markdown: a line for a pull request's body)
  apothecary test changed
                        while working, and before each commit: the walkthrough
                        and the unit files of the groups a change reaches, then
                        the browser files of the areas it reaches (--since REF;
                        the branch's upstream by default)
  apothecary test group [NAME...]
                        the unit suite's groups; with names, their unit files and
                        the walkthrough
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
@click.option(
    "--workers",
    type=click.IntRange(min=1),
    default=1,
    show_default=True,
    help="The unit part in parallel, a file's tests together (pytest-xdist).",
)
# Every browser test is `test all`'s; the flag stays, hidden, to say so.
@click.option(
    "--e2e", is_flag=True, hidden=True, expose_value=False, callback=_every_browser_test_is_test_all
)
@click.argument("pytest_args", nargs=-1, type=click.UNPROCESSED)
def test_run(slow: bool, workers: int, pytest_args: tuple[str, ...]):
    """The ordinary command: the unit tests and the walkthrough, whose demonstration
    drives Chromium in a pytest of its own; further arguments go to pytest.

    They go to both pytests, and it exits with the first failing code; a part that
    selects no test is not a failure when the other ran some.
    """
    codes = [_pytest(argv + list(pytest_args)) for argv in run_commands(slow=slow, workers=workers)]
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
    help="Both parts in parallel, a file's tests together (pytest-xdist).",
)
@click.option(
    "--coverage",
    is_flag=True,
    help="Measure what the run covers, and say it: the package's statements, and those "
    "the change adds or changes since --since.",
)
@click.option(
    "--since",
    default=coverage_summary.BASE,
    show_default=True,
    help="With --coverage, the base the change is measured against.",
)
@click.argument("pytest_args", nargs=-1, type=click.UNPROCESSED)
def test_all(slow: bool, workers: int, coverage: bool, since: str, pytest_args: tuple[str, ...]):
    """The unit tests and the walkthrough, then every browser test in a pytest of its
    own, on a server of its own (--start-server); further arguments go to pytest, to
    both, as `test run`'s do (`-k part` narrows each). --record-durations, passed
    through, writes the browser tests' times into tests/e2e/durations.json, which
    the shards are balanced by; --steps runs the step-through tests too, which skip
    otherwise. --coverage measures both parts, the server the browser tests drive
    included, and says what they covered, as `test coverage` does."""
    env = coverage_env() if coverage else None
    codes = [
        _pytest(argv + list(pytest_args), env=env)
        for argv in all_commands(slow=slow, workers=workers, coverage=coverage)
    ]
    if coverage:
        try:
            click.echo(_covered(since))
        except click.ClickException as unread:
            click.echo(unread.format_message(), err=True)
    raise SystemExit(_first_failure(codes))


def _covered(since: str, markdown: bool = False) -> str:
    measured = coverage_summary.measure(coverage_summary.change_against(since))
    say = coverage_summary.markdown if markdown else coverage_summary.said
    return say(measured, since)


@test.command("coverage")
@click.option(
    "--since",
    default=coverage_summary.BASE,
    show_default=True,
    help="The base the change is measured against: the pull request's.",
)
@click.option("--markdown", is_flag=True, help="As a line for a pull request's body.")
def test_coverage(since: str, markdown: bool):
    """What the last `test all --coverage` covered: the package's statements, and of
    the statements this checkout adds or changes since --since, how many ran, naming
    those that did not. It informs a pull request's reader; nothing fails on a number."""
    click.echo(_covered(since, markdown=markdown))


for _name, _instead in (
    ("setup-e2e", "use `uv run playwright install chromium`"),
    ("validate-e2e", "use `apothecary test all`"),
    ("run-e2e", "use `apothecary test all`"),
):
    test.add_command(retired(f"test {_name}", _instead), name=_name)


def _map(path: str):
    """A checkout's map of its suite, not the package's: tests/groups.py for the unit
    files, tests/e2e/areas.py for the browser files."""
    spec = importlib.util.spec_from_file_location(path.rsplit("/", 1)[-1][:-3], ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _areas():
    """The browser suite's areas (tests/e2e/areas.py)."""
    return _map(f"{BROWSER}/areas.py")


def _groups():
    """The unit suite's groups (tests/groups.py)."""
    return _map("tests/groups.py")


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
    """The argvs `apothecary test changed` runs: the walkthrough's pages with the unit
    files the change reaches (all of them when it touches shared ground), then the
    browser files it reaches, if it reaches any."""
    groups, areas = _groups(), _areas()
    units, reached = groups.reached(changed), areas.reached(changed)
    commands = [unit_command(files=None if units == groups.ALL else units, workers=workers)]
    browser = [BROWSER] if reached == areas.ALL else reached
    if browser:
        argv = _pytest_argv(*browser, "--start-server")
        if workers > 1:
            argv += ["-n", str(workers), *FILES_WHOLE]
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
    help="Both parts in parallel, a file's tests together (pytest-xdist).",
)
@click.argument("pytest_args", nargs=-1, type=click.UNPROCESSED)
def test_changed(since: str | None, only_list: bool, workers: int, pytest_args: tuple[str, ...]):
    """The walkthrough and the unit files of the groups a change reaches
    (tests/groups.py), then the browser files of the areas it reaches
    (tests/e2e/areas.py): every file of a part when the change touches its shared
    ground, a file itself when it changes, none when it reaches no group or area. The
    change is what this checkout holds against --since, uncommitted and new files
    included; without it, against the branch's upstream. It is for while working: the
    run before a merge is `test all`'s, the whole suite, on the stack's head."""
    changed = changed_paths(since)
    if only_list:
        groups, areas = _groups(), _areas()
        units, reached = groups.reached(changed), areas.reached(changed)
        if units == groups.ALL:
            click.echo("every unit file (tests): the change touches shared ground")
        else:
            click.echo("\n".join(units) if units else "no unit file")
        if reached == areas.ALL:
            click.echo(f"every browser file ({BROWSER}): the change touches shared ground")
        else:
            click.echo("\n".join(reached) if reached else "no browser file")
        return
    commands = changed_commands(changed, workers=workers)
    codes = [_pytest(argv + list(pytest_args)) for argv in commands]
    raise SystemExit(_first_failure(codes))


@test.command("group", context_settings={"ignore_unknown_options": True})
@click.argument("names", nargs=-1)
@click.option(
    "--workers",
    type=click.IntRange(min=1),
    default=1,
    show_default=True,
    help="Unit files in parallel, a file's tests together (pytest-xdist).",
)
def test_group(names: tuple[str, ...], workers: int):
    """The walkthrough and the unit files of the groups NAMES (tests/groups.py): one part
    of the package at a time, as quick as that part. Without a name, the groups, each
    with what it holds. Further pytest arguments follow `--`."""
    groups = _groups()
    if not names:
        for name, group in groups.GROUPS.items():
            click.echo(
                f"{name:12} {len(group['tests']):3} files  {', '.join(group['sources'][:3])}"
            )
        return
    pytest_args = [n for n in names if n.startswith("-")]
    try:
        files = groups.files([n for n in names if not n.startswith("-")])
    except KeyError as unknown:
        raise click.ClickException(unknown.args[0]) from None
    raise SystemExit(_pytest(unit_command(files=files, workers=workers) + pytest_args))
