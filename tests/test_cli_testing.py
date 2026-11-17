"""`apothecary test` exits with the code pytest exits with."""

import os
import subprocess
import sys

import pytest
from click.testing import CliRunner

from apothecary.cli import cli, green, testing
from apothecary.projects.parts.skeleton import ROOT


@pytest.fixture
def pytest_exits(monkeypatch):
    """Stand in for pytest: each run returns the next code given, and its argv is kept."""

    def exits_with(*codes: int) -> list[list[str]]:
        ran, remaining = [], list(codes)

        def run(argv, env=None):
            ran.append(argv)
            return remaining.pop(0)

        monkeypatch.setattr(testing, "_pytest", run)
        return ran

    return exits_with


@pytest.fixture(autouse=True)
def digests(monkeypatch, tmp_path):
    """The record of what was green is this test's own, over a checkout that holds
    still: each unit file's digest and the walkthrough's, which a test may change."""
    monkeypatch.setenv(green.RECORD_ENV, str(tmp_path / "green.json"))
    held = {name: "as it was" for name in [testing.WALKTHROUGH, *testing.unit_files()]}
    monkeypatch.setattr(green, "digests", lambda root, groups: dict(held))
    monkeypatch.setattr(green, "environment", lambda root: {"Python": "this one"})
    return held


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
    every = testing.run_commands(workers=testing.unit_workers())
    assert ran == [argv + ["-x"] for argv in every]


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
        (["--workers", "2"], ["-n", "2", *testing.FILES_WHOLE], ["-n", "2", *testing.FILES_WHOLE]),
        (
            ["--workers", "3", "-x"],
            ["-n", "3", *testing.FILES_WHOLE, "-x"],
            ["-n", "3", *testing.FILES_WHOLE, "-x"],
        ),
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
    assert "not run, unchanged since green, and --even-unchanged runs it too" in said
    assert "on a core fewer than the machine has" in said and "--workers 1" in said


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
    """A change to a board's code reaches the machines group's unit files, the border
    check, and the machine area's browser files alone; one to the page reaches every
    browser file; one that reaches no area runs the unit files of its groups alone."""
    groups = testing._groups()
    unit, browser = testing.changed_commands(["apothecary/firmware/gcode.py"])
    assert unit == testing.unit_command(files=groups.files(["machines", "borders"]))
    assert _args(unit)[:2] == ["-q", "walkthrough"] and "tests/test_jobs.py" in unit
    assert "tests/test_slicer.py" not in unit
    files = [a for a in _args(browser) if a.startswith("tests/e2e/")]
    assert "tests/e2e/test_one_machine.py" in files and "tests/e2e/test_ring.py" not in files
    assert _args(browser)[-1] == "--start-server"
    _, every = testing.changed_commands(["templates/fractal_viewer.html.j2"], workers=3)
    assert _args(every) == ["-q", "tests/e2e", "--start-server", "-n", "3", *testing.FILES_WHOLE]
    assert testing.changed_commands(["docs/viewer.md"]) == [
        testing.unit_command(files=groups.files(["repository"]))
    ]
    every_unit, _ = testing.changed_commands(["apothecary/api.py"], workers=2)
    assert every_unit == testing.unit_command(workers=2)


def test_changed_exits_with_the_first_failing_code_and_lists_without_running(
    pytest_exits, monkeypatch
):
    monkeypatch.setattr(testing, "changed_paths", lambda since: ["apothecary/lighting.py"])
    ran = pytest_exits(0, 1)
    listed = CliRunner().invoke(cli, ["test", "changed", "--list"])
    assert listed.exit_code == 0
    assert listed.output.splitlines() == [
        *testing._groups().files(["viewer", "borders"]),
        "tests/e2e/test_lighting_overlay.py",
    ]
    assert ran == []  # --list ran nothing
    done = CliRunner().invoke(cli, ["test", "changed"])
    assert done.exit_code == 1 and len(ran) == 2
    assert "tests/e2e/test_lighting_overlay.py" in _args(ran[1])


GCODE = ["apothecary/firmware/gcode.py"]  # reaches the machines group and the borders


def _changed(*args: str):
    done = CliRunner().invoke(cli, ["test", "changed", *args])
    return done.exit_code, done.output.splitlines()


def _unit(ran) -> list[str]:
    """The unit files and walkthrough a run's unit pytest named, if it ran one."""
    named = [a for a in _args(ran[0]) if a == "walkthrough" or a.startswith("tests/test_")]
    return named if "--start-server" not in ran[0] else []


def test_changed_leaves_out_what_is_unchanged_since_green_and_says_it_apart(
    pytest_exits, monkeypatch, digests
):
    """A unit file, or the walkthrough, whose digest is the one a passing run kept is not
    run; each group of them is said on a line of its own, counted apart from what ran,
    with the command that runs them too."""
    monkeypatch.setattr(testing, "changed_paths", lambda since: GCODE)
    machines, borders = testing._groups().files(["machines"]), ["tests/test_boundaries.py"]
    ran = pytest_exits(0, 0)
    code, said = _changed()
    assert code == 0 and _unit(ran) == ["walkthrough", *machines, *borders]
    assert said[0].startswith("nothing left out as unchanged: no record of a run that passed")
    assert f"kept as green: {len(machines) + 1} unit file(s) and the walkthrough" in said[-1]
    # Nothing moved since: only the browser part runs, and the rest is said not run.
    ran = pytest_exits(0)
    code, said = _changed()
    assert code == 0 and len(ran) == 1 and "--start-server" in ran[0]
    assert [line.split(": ", 2)[2] for line in said if line.startswith("not run")] == [
        f"machines ({len(machines)} files)",
        "borders (1 file)",
        "the walkthrough",
    ]
    assert (
        "unit groups the change reaches: 0 ran; 2 not run, unchanged since green "
        "(machines, borders); the walkthrough not run, unchanged since green"
    ) in said
    assert f"`{testing.EVERY_ONE_REACHED}` runs what was not run too" in said
    # One file moves: it alone runs, and its group is said to have run the part that moved.
    digests["tests/test_jobs.py"] = "moved"
    ran = pytest_exits(0, 0)
    code, said = _changed()
    assert _unit(ran) == ["tests/test_jobs.py"]
    summary = next(line for line in said if line.startswith("unit groups"))
    assert summary.startswith("unit groups the change reaches: 1 ran (machines), files unchanged")
    assert f"machines {len(machines) - 1} of {len(machines)}" in summary
    assert "1 not run, unchanged since green (borders)" in summary
    # --even-unchanged runs every one the change reaches, and says nothing is left out.
    ran = pytest_exits(0, 0)
    code, said = _changed("--even-unchanged")
    assert _unit(ran) == ["walkthrough", *machines, *borders]
    assert not any(line.startswith("not run") for line in said)
    # --list names what would run, and what would not.
    listed = CliRunner().invoke(cli, ["test", "changed", "--list"]).output.splitlines()
    assert listed[0] == "no unit file" and listed[-1].endswith(": the walkthrough")


def test_changed_with_nothing_to_run_runs_no_pytest_and_passes(pytest_exits, monkeypatch):
    monkeypatch.setattr(testing, "changed_paths", lambda since: ["tests/test_jobs.py"])
    pytest_exits(0)
    assert _changed()[0] == 0
    ran = pytest_exits()
    code, said = _changed()
    assert code == 0 and ran == []
    assert "not run: unchanged since green at" in said[0] and said[0].endswith("machines (1 file)")


@pytest.mark.parametrize(
    "codes, args, kept",
    [
        ((1, 0), [], False),  # the unit part failed
        ((0, 1), [], True),  # the browser part failed: the unit files passed
        ((0, 0), ["-k", "gcode"], False),  # narrowed
        ((0, 0), ["tests/test_jobs.py"], False),  # narrowed to a path
        ((0, 0), ["-x"], True),  # stops at a failure, and none came
        ((5, 0), [], False),  # the unit part collected nothing
    ],
    ids=["unit-failed", "browser-failed", "narrowed", "a-path", "exitfirst", "nothing-collected"],
)
def test_changed_keeps_as_green_only_a_unit_part_that_passed_unnarrowed(
    pytest_exits, monkeypatch, codes, args, kept
):
    monkeypatch.setattr(testing, "changed_paths", lambda since: GCODE)
    pytest_exits(*codes)
    _, said = _changed(*args)
    assert any(line.startswith("kept as green") for line in said) is kept
    if args and not kept:
        assert "not kept as green: further pytest arguments may have narrowed the run" in said
    ran = pytest_exits(0, 0)
    _changed()
    assert bool(_unit(ran)) is not kept  # what was kept is not run again


def test_run_all_and_group_keep_what_their_unit_part_passed(pytest_exits, monkeypatch):
    """`test run`, `test all` and `test group` run what they name whatever the record
    holds, and keep what a passing unit part ran, as `test changed` does."""
    monkeypatch.setattr(testing, "changed_paths", lambda since: GCODE)
    every = [testing.WALKTHROUGH, *testing.unit_files()]
    for command, codes in ((["run"], (0, 0)), (["all"], (0, 0)), (["group", "making"], (0,))):
        ran = pytest_exits(*codes)
        done = CliRunner().invoke(cli, ["test", *command])
        assert done.exit_code == 0 and len(ran) == len(codes)
        assert "kept as green:" in done.output
        # Kept: run again, it runs what it names all the same.
        ran = pytest_exits(*codes)
        CliRunner().invoke(cli, ["test", *command])
        assert len(ran) == len(codes) and _args(ran[0])[1] == "walkthrough"
    record = green.read(ROOT, green.environment(ROOT))
    assert all(record.unchanged(name, "as it was") for name in every)
    ran = pytest_exits(0)
    _changed()
    assert len(ran) == 1 and "--start-server" in ran[0]  # every unit file kept


def test_a_whole_run_that_fails_keeps_nothing(pytest_exits, monkeypatch):
    pytest_exits(1, 0)
    assert "kept as green" not in CliRunner().invoke(cli, ["test", "run"]).output
    pytest_exits(0, 0)
    said = CliRunner().invoke(cli, ["test", "run", "-k", "cli"]).output
    assert "not kept as green: further pytest arguments may have narrowed the run" in said
    assert not green.record_path(ROOT).exists()


def test_what_changed_says_counts_groups_that_ran_apart_from_those_unchanged():
    group_of = {"tests/a.py": "one", "tests/b.py": "one", "tests/c.py": "two"}
    files = list(group_of)
    said = testing.unchanged_said(files, {}, group_of, walked=True)
    assert said == ["unit groups the change reaches: 2 ran (one, two); 0 not run, unchanged "
                    "since green; the walkthrough ran"]  # fmt: skip
    left = {"tests/b.py": "2026-11-17T09:00:00", "tests/c.py": "2026-11-17T08:00:00"}
    said = testing.unchanged_said(files, left, group_of, walked=True)
    assert said == [
        "not run: unchanged since green at 2026-11-17T08:00:00: two (1 file)",
        "unit groups the change reaches: 1 ran (one), files unchanged since green not run in "
        "one 1 of 2; 1 not run, unchanged since green (two); the walkthrough ran",
        f"`{testing.EVERY_ONE_REACHED}` runs what was not run too",
    ]


def test_changed_says_what_to_name_when_there_is_nothing_to_compare_with():
    done = CliRunner().invoke(cli, ["test", "changed", "--list", "--since", "no-such-ref-here"])
    assert done.exit_code != 0 and "name a ref with --since" in done.output


def test_a_crashed_worker_ends_a_parallel_run_and_names_its_test(tmp_path):
    """What FILES_WHOLE is for: a worker that crashes while other files wait, its own
    file's next test among them, ends the run rather than leaving it waiting forever."""
    (tmp_path / "test_crashes.py").write_text(
        "import os\n\ndef test_crashes():\n    os._exit(1)\n\ndef test_after_it():\n    pass\n"
    )
    for name in "bcde":
        (tmp_path / f"test_{name}.py").write_text(
            "import time\n\n"
            + "".join(f"def test_{n}():\n    time.sleep(0.2)\n\n" for n in range(3))
        )
    ran = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-n", "2"]
        + testing.FILES_WHOLE,
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert ran.returncode == 1
    assert "crashed while running 'test_crashes.py::test_crashes'" in ran.stdout


def test_group_lists_the_groups_and_runs_the_named_ones(pytest_exits):
    """One part of the package at a time: the walkthrough and the named groups' unit
    files, in parallel with --workers; a name the map does not hold is refused."""
    groups = testing._groups()
    listed = CliRunner().invoke(cli, ["test", "group"])
    assert listed.exit_code == 0
    assert [line.split()[0] for line in listed.output.splitlines()] == list(groups.GROUPS)
    ran = pytest_exits(0)
    done = CliRunner().invoke(cli, ["test", "group", "making", "family", "--workers", "2"])
    assert done.exit_code == 0
    assert ran == [testing.unit_command(files=groups.files(["making", "family"]), workers=2)]
    refused = CliRunner().invoke(cli, ["test", "group", "nowhere"])
    assert refused.exit_code != 0 and "no group named nowhere" in refused.output
    assert len(ran) == 1


@pytest.mark.parametrize(
    "cores, workers", [(1, 1), (2, 1), (3, 2), (4, 3), (5, 4), (16, 4), (None, None)]
)
def test_the_unit_part_runs_on_a_core_fewer_than_the_machine_has(cores, workers):
    """One core is left to what shares the machine, a browser run or a server's own
    test loop; a worker is not started for no gain past four."""
    import os

    assert testing.unit_workers(cores=cores) == (workers or max(1, min(4, os.cpu_count() - 1)))
    assert testing.unit_workers(1, cores=cores) == 1 and testing.unit_workers(6, cores=4) == 6


def test_the_ordinary_commands_run_the_unit_part_on_those_workers_and_the_browser_on_one(
    pytest_exits, monkeypatch
):
    monkeypatch.setattr(testing, "unit_workers", lambda named=None, cores=None: named or 3)
    monkeypatch.setattr(testing, "changed_paths", lambda since: GCODE)
    commands = (
        (["run"], (0, 0)),
        (["changed", "--even-unchanged"], (0, 0)),
        (["group", "cli"], (0,)),
    )
    for command, codes in commands:
        ran = pytest_exits(*codes)
        assert CliRunner().invoke(cli, ["test", *command]).exit_code == 0
        assert _args(ran[0])[-6:] == ["-n", "3", *testing.FILES_WHOLE], command
        assert all("-n" not in argv for argv in ran[1:]), command
    for command, codes in commands:
        ran = pytest_exits(*codes)
        CliRunner().invoke(cli, ["test", *command, "--workers", "1"])
        assert len(ran) == len(codes) and all("-n" not in argv for argv in ran), command
    ran = pytest_exits(0, 0)
    CliRunner().invoke(cli, ["test", "changed", "--workers", "2"])
    assert all(argv[argv.index("-n") + 1] == "2" for argv in ran)  # both parts, when named


def test_run_takes_workers_for_its_unit_part(pytest_exits):
    ran = pytest_exits(0, 0)
    assert CliRunner().invoke(cli, ["test", "run", "--workers", "4"]).exit_code == 0
    assert ran == testing.run_commands(workers=4)
    assert _args(ran[0])[-4:] == ["--dist", "loadfile", "--max-worker-restart", "0"]
    assert "-n" not in ran[1]
