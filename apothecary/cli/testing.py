"""`apothecary test`: run the suite with pytest and exit with pytest's own code.

Click ignores a command's return value, so each command exits through SystemExit.

Each command that runs the suite runs two pytests, one after the other: the unit
suite with the walkthrough's pages, then the browser part. Two processes, not one: a browser
test leaves Playwright's event loop running, and a unit test after it in the
same process that starts a loop of its own is refused ("asyncio.run() cannot be
called from a running event loop").
"""

import functools
import importlib.util
import os
import subprocess
import sys

import click

from ..projects.parts.skeleton import ROOT
from . import coverage_summary, green
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


def unit_command(
    slow: bool = False,
    files: list[str] | None = None,
    workers: int = 1,
    walkthrough: bool = True,
) -> list[str]:
    """The walkthrough's pages and the unit suite, without a browser: every unit file, or
    only ``files`` (tests/groups.py's); with ``workers`` above one, that many in
    parallel, a file's tests together. Without ``walkthrough``, the unit files alone."""
    tests = ["tests", f"--ignore={BROWSER}"] if files is None else files
    argv = _pytest_argv(*([WALKTHROUGH] if walkthrough else []), *tests)
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
                        the branch's upstream by default); a unit file or the
                        walkthrough unchanged since a run in which it passed is
                        said not run, unchanged since green, and
                        --even-unchanged runs it too
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
    kept = Kept.before(pytest_args)
    codes = [_pytest(argv + list(pytest_args)) for argv in run_commands(slow=slow, workers=workers)]
    _say(kept.keep([WALKTHROUGH, *unit_files()], codes[0], pytest_args))
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
    included, and says what they covered, as `test coverage` does. Before a stack is
    pulled it runs once on its head: docs/integration-checklist.md, box by box."""
    env = coverage_env() if coverage else None
    kept = Kept.before(pytest_args)
    codes = [
        _pytest(argv + list(pytest_args), env=env)
        for argv in all_commands(slow=slow, workers=workers, coverage=coverage)
    ]
    _say(kept.keep([WALKTHROUGH, *unit_files()], codes[0], pytest_args))
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


@functools.cache
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


def browser_files_command(files: list[str], workers: int = 1) -> list[str]:
    """The browser files ``files`` on a server of their own."""
    argv = _pytest_argv(*files, "--start-server")
    if workers > 1:
        argv += ["-n", str(workers), *FILES_WHOLE]
    return argv


def changed_commands(changed: list[str], workers: int = 1) -> list[list[str]]:
    """The argvs `apothecary test changed` runs, the record of what was green left
    aside: the walkthrough's pages with the unit files the change reaches (all of them
    when it touches shared ground), then the browser files it reaches, if it reaches any."""
    groups, areas = _groups(), _areas()
    units, reached = groups.reached(changed), areas.reached(changed)
    commands = [unit_command(files=None if units == groups.ALL else units, workers=workers)]
    browser = [BROWSER] if reached == areas.ALL else reached
    if browser:
        commands.append(browser_files_command(browser, workers=workers))
    return commands


def unit_files() -> list[str]:
    """Every unit file, as a path from the root."""
    return sorted(f"tests/{p.name}" for p in (ROOT / "tests").glob("test_*.py") if p.is_file())


class Kept:
    """The record of what was green (green.py), as one command reads it: this checkout's
    environment, the digest of each unit file and of the walkthrough, and the record read
    in that environment. A checkout git cannot list keeps nothing, and leaves nothing out."""

    @classmethod
    def before(cls, pytest_args):
        """What a whole run keeps, read before it runs: nothing, when further pytest
        arguments may narrow it, and it keeps nothing then."""
        return cls(None) if narrows(pytest_args) else cls(_groups())

    def __init__(self, groups):
        if groups is None:
            self.env, self.digests = None, {}
            self.record = green.Record({}, "further pytest arguments may narrow the run")
            return
        try:
            self.env = green.environment(ROOT)
            self.digests = green.digests(ROOT, groups)
        except (OSError, subprocess.CalledProcessError) as unread:
            self.env, self.digests = None, {}
            self.record = green.Record({}, f"the checkout could not be listed: {unread}")
            return
        self.record = green.read(ROOT, self.env)

    def unchanged(self, names) -> dict[str, str]:
        """Of ``names``, each the record holds as green at its digest now, with when."""
        found = {}
        for name in names:
            digest = self.digests.get(name)
            at = self.record.unchanged(name, digest) if digest else None
            if at:
                found[name] = at
        return found

    def keep(self, ran: list[str], code: int, pytest_args) -> str:
        """Keep ``ran`` as green when its pytest passed and nothing narrowed it; say what
        was kept, or why nothing was."""
        if code != 0:
            return ""
        if narrows(pytest_args):
            return "not kept as green: further pytest arguments may have narrowed the run"
        if self.env is None:
            return f"not kept as green: {self.record.distrust}"
        green.write(ROOT, self.env, {name: self.digests[name] for name in ran})
        files = [name for name in ran if name != WALKTHROUGH]
        walked = " and the walkthrough" if WALKTHROUGH in ran else ""
        return f"kept as green: {len(files)} unit file(s){walked} ({green.record_path(ROOT)})"


# Further pytest arguments that select no fewer tests: a run given only these that
# passes ran everything it names. Any other may narrow it (`-k`, `-m`, `--lf`, a path).
SELECT_NO_FEWER = {
    "-q", "-v", "-vv", "-s", "-x", "--exitfirst", "--slow", "--steps", "--gpu",
    "--record-durations",
}  # fmt: skip


def narrows(pytest_args) -> bool:
    """Whether further pytest arguments may run fewer tests than the command names."""
    return any(arg not in SELECT_NO_FEWER for arg in pytest_args)


def _say(line: str) -> None:
    if line:
        click.echo(line)


# The command that runs, too, what the record leaves out.
EVERY_ONE_REACHED = "apothecary test changed --even-unchanged"


def unchanged_said(
    files: list[str], left: dict[str, str], group_of: dict[str, str], walked: bool
) -> list[str]:
    """What `test changed` says of the unit part: each group the change reaches none of
    whose files ran, on a line of its own, with when it was green, and the walkthrough
    if it did not run; then how many groups ran and how many did not, and why; and the
    command that runs the rest."""
    lines, ran, not_run, partly = [], [], [], []
    by_group: dict[str, list[str]] = {}
    for name in files:
        by_group.setdefault(group_of.get(name, "no group"), []).append(name)
    for group, names in by_group.items():
        out = [name for name in names if name in left]
        if len(out) == len(names):
            not_run.append(group)
            when = min(left[name] for name in out)
            lines.append(f"not run: unchanged since green at {when}: {group} ({len(out)} files)")
        else:
            ran.append(group)
            if out:
                partly.append(f"{group} {len(out)} of {len(names)}")
    if WALKTHROUGH in left:
        lines.append(f"not run: unchanged since green at {left[WALKTHROUGH]}: the walkthrough")
    said = f"unit groups the change reaches: {len(ran)} ran"
    said += f" ({', '.join(ran)})" if ran else ""
    if partly:
        said += f", files unchanged since green not run in {', '.join(partly)}"
    said += f"; {len(not_run)} not run, unchanged since green"
    said += f" ({', '.join(not_run)})" if not_run else ""
    said += "; the walkthrough " + ("ran" if walked else "not run, unchanged since green")
    lines.append(said)
    if left:
        lines.append(f"`{EVERY_ONE_REACHED}` runs what was not run too")
    return lines


@test.command("changed", context_settings={"ignore_unknown_options": True})
@click.option("--since", default=None, help="The ref to compare with (default: the upstream).")
@click.option(
    "--list",
    "only_list",
    is_flag=True,
    help="Name the files the change reaches, and what of them is not run, and run nothing.",
)
@click.option(
    "--workers",
    type=click.IntRange(min=1),
    default=1,
    show_default=True,
    help="Both parts in parallel, a file's tests together (pytest-xdist).",
)
@click.option(
    "--even-unchanged",
    is_flag=True,
    help="Run every unit file the change reaches, those unchanged since green too.",
)
@click.argument("pytest_args", nargs=-1, type=click.UNPROCESSED)
def test_changed(
    since: str | None,
    only_list: bool,
    workers: int,
    even_unchanged: bool,
    pytest_args: tuple[str, ...],
):
    """The walkthrough and the unit files of the groups a change reaches
    (tests/groups.py), then the browser files of the areas it reaches
    (tests/e2e/areas.py): every file of a part when the change touches its shared
    ground, a file itself when it changes, none when it reaches no group or area. The
    change is what this checkout holds against --since, uncommitted and new files
    included; without it, against the branch's upstream.

    A unit file, or the walkthrough, unchanged since a run in which it passed is not
    run, and said apart: not run, unchanged since green at a time, counted on its own
    (apothecary/cli/green.py says what unchanged is, and what makes the record not
    trusted). --even-unchanged runs them too. A unit part that passes, given no further
    pytest arguments, keeps what it ran as green, as `test run`, `test all` and `test
    group` do. It is for while working: the run before a merge is `test all`'s, the
    whole suite, on the stack's head."""
    changed = changed_paths(since)
    groups, areas = _groups(), _areas()
    units, reached = groups.reached(changed), areas.reached(changed)
    every = units == groups.ALL
    files = unit_files() if every else units
    kept = Kept(groups)
    left = {} if even_unchanged else kept.unchanged([WALKTHROUGH, *files])
    run = [name for name in files if name not in left]
    walked = WALKTHROUGH not in left
    group_of = {f"tests/{n}": g for g, held in groups.GROUPS.items() for n in held["tests"]}
    said = unchanged_said(files, left, group_of, walked)
    if kept.record.distrust and not even_unchanged:
        said.insert(0, f"nothing left out as unchanged: {kept.record.distrust}")
    browser = [BROWSER] if reached == areas.ALL else reached
    if only_list:
        if every and not left:
            click.echo("every unit file (tests): the change touches shared ground")
        else:
            click.echo("\n".join(run) if run else "no unit file")
        if reached == areas.ALL:
            click.echo(f"every browser file ({BROWSER}): the change touches shared ground")
        else:
            click.echo("\n".join(reached) if reached else "no browser file")
        for line in said:
            if line.startswith("not run"):
                click.echo(line)
        return
    codes, ran = [], []
    if run or walked:
        whole = every and not left  # the ordinary argv, which names no file
        unit = unit_command(files=None if whole else run, workers=workers, walkthrough=walked)
        codes.append(_pytest(unit + list(pytest_args)))
        ran = ([WALKTHROUGH] if walked else []) + (files if whole else run)
    if browser:
        codes.append(_pytest(browser_files_command(browser, workers=workers) + list(pytest_args)))
    if ran:
        said.append(kept.keep(ran, codes[0], pytest_args))
    click.echo("\n".join(line for line in said if line))
    raise SystemExit(_first_failure(codes) if codes else 0)


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
    kept = Kept.before(pytest_args)
    code = _pytest(unit_command(files=files, workers=workers) + pytest_args)
    _say(kept.keep([WALKTHROUGH, *files], code, pytest_args))
    raise SystemExit(code)
