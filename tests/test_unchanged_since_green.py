"""What `apothecary test changed` leaves out (apothecary/cli/green.py): a unit file, or
the walkthrough, whose digest -- of every file a change to which reaches it -- is the
one a passing run kept; and that record, trusted only as written and only in the
environment it was written in."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

from apothecary.cli import green

ROOT = Path(__file__).resolve().parents[1]

# A checkout of its own: two groups, the shared ground, a helper and a page.
CHECKOUT = {
    "conftest.py": "",
    "tests/conftest.py": "",
    "pyproject.toml": "",
    "uv.lock": "",
    "tests/groups.py": "",
    "apothecary/core.py": "",
    "apothecary/firmware/gcode.py": "",
    "apothecary/cam/toolpath.py": "",
    "tests/firmware_helpers.py": "",
    "tests/test_jobs.py": "import firmware_helpers\n",
    "tests/test_board.py": "",
    "tests/test_cam.py": "",
    "walkthrough/01-a-page.md": "",
    "docs/a-page.md": "",
}
SHARED = ("conftest.py", "tests/conftest.py", "pyproject.toml", "uv.lock", "apothecary/core.py")
GROUPS = {
    "machines": {"sources": ("apothecary/firmware/*",), "tests": ("test_jobs.py", "test_board.py")},
    "making": {"sources": ("apothecary/cam/*",), "tests": ("test_cam.py",)},
}
JOBS, BOARD, CAM = "tests/test_jobs.py", "tests/test_board.py", "tests/test_cam.py"
WALK = green.WALKTHROUGH
EVERY = {JOBS, BOARD, CAM, WALK}


# What the session named for the record, before each test here names its own.
NAMED_BY_THE_SESSION: list = []


@pytest.fixture(autouse=True)
def _a_record_of_each_tests_own(tmp_path, monkeypatch):
    NAMED_BY_THE_SESSION.append(os.environ.get(green.RECORD_ENV))
    monkeypatch.setenv(green.RECORD_ENV, str(tmp_path / "kept" / "green.json"))


@pytest.fixture
def checkout(tmp_path, monkeypatch):
    """The checkout above, tracked by git, and the suite's map read over it."""
    for path, text in CHECKOUT.items():
        (tmp_path / path).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / path).write_text(text, encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    spec = importlib.util.spec_from_file_location("groups_of_its_own", ROOT / "tests/groups.py")
    groups = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(groups)
    monkeypatch.setattr(groups, "ROOT", tmp_path)
    monkeypatch.setattr(groups, "SHARED", SHARED)
    monkeypatch.setattr(groups, "GROUPS", GROUPS)
    return tmp_path, groups


def _moved(before: dict, after: dict) -> set:
    return {name for name in before.keys() | after.keys() if before.get(name) != after.get(name)}


def _write(root: Path, path: str, text: str = "changed\n") -> None:
    (root / path).parent.mkdir(parents=True, exist_ok=True)
    (root / path).write_text(text, encoding="utf-8")


@pytest.mark.parametrize(
    "change, moved",
    [
        (lambda root: _write(root, "apothecary/firmware/gcode.py"), {JOBS, BOARD, WALK}),
        (lambda root: _write(root, "apothecary/cam/toolpath.py"), {CAM, WALK}),
        (lambda root: _write(root, "apothecary/core.py"), EVERY),
        (lambda root: _write(root, "tests/conftest.py"), EVERY),
        (lambda root: _write(root, "uv.lock"), EVERY),
        (
            lambda root: _write(root, "tests/test_jobs.py", "import firmware_helpers\n# more\n"),
            {JOBS},
        ),
        (lambda root: _write(root, "tests/firmware_helpers.py"), {JOBS}),
        (lambda root: _write(root, "docs/a-page.md"), {WALK}),
        (lambda root: _write(root, "walkthrough/01-a-page.md"), {WALK}),
        (lambda root: _write(root, "apothecary/cam/added.py"), {CAM, WALK}),
        (lambda root: (root / "apothecary/cam/toolpath.py").unlink(), {CAM, WALK}),
        (lambda root: _write(root, "tests/test_cam.py", "x = 1\n"), {CAM}),
    ],
    ids=[
        "a-group-source",
        "another-group-source",
        "shared-ground",
        "the-conftest",
        "the-lockfile",
        "a-unit-file-itself",
        "a-helper-one-file-imports",
        "a-page-of-the-docs",
        "a-walkthrough-page",
        "a-file-added-untracked",
        "a-file-deleted",
        "another-unit-file",
    ],
)
def test_a_change_moves_the_digests_of_what_it_reaches_and_of_nothing_else(checkout, change, moved):
    root, groups = checkout
    before = green.digests(root, groups)
    assert set(before) == EVERY
    change(root)
    assert _moved(before, green.digests(root, groups)) == moved


def test_a_file_ignored_moves_nothing(checkout):
    root, groups = checkout
    _write(root, ".gitignore", "*.stl\n")
    subprocess.run(["git", "add", ".gitignore"], cwd=root, check=True)
    before = green.digests(root, groups)
    _write(root, "apothecary/cam/made.stl")
    assert green.digests(root, groups) == before


ENV = {
    "Python": "3.x",
    "the lockfile": "a",
    "the conftests": "b",
    "tests/groups.py": "c",
    "OpenSCAD": "d",
    "the tools folder": "e",
    "node": "f",
}
AT = datetime(2026, 11, 17, 9, 30, tzinfo=timezone.utc)


def test_a_record_kept_is_read_back_in_its_environment(tmp_path):
    green.write(tmp_path, ENV, {JOBS: "d1", WALK: "w1"}, at=AT)
    record = green.read(tmp_path, ENV)
    assert record.distrust is None
    when = AT.astimezone().isoformat(timespec="seconds")
    assert record.unchanged(JOBS, "d1") == when and record.unchanged(WALK, "w1") == when
    assert record.unchanged(JOBS, "d2") is None  # changed since
    assert record.unchanged(CAM, "d1") is None  # never green
    # A later pass keeps what it ran beside what was kept.
    green.write(tmp_path, ENV, {CAM: "c1", JOBS: "d3"})
    record = green.read(tmp_path, ENV)
    assert record.unchanged(CAM, "c1") and record.unchanged(JOBS, "d3")
    assert record.unchanged(WALK, "w1") == when and record.unchanged(JOBS, "d1") is None


def test_no_record_is_said_and_leaves_nothing_out(tmp_path):
    record = green.read(tmp_path, ENV)
    assert record.entries == {} and "no record of a run that passed" in record.distrust


@pytest.mark.parametrize("part", list(ENV))
def test_a_record_is_not_trusted_once_a_part_of_its_environment_changes(tmp_path, part):
    green.write(tmp_path, ENV, {JOBS: "d1"})
    record = green.read(tmp_path, {**ENV, part: "another"})
    assert record.entries == {} and record.unchanged(JOBS, "d1") is None
    assert record.distrust == f"{part} changed since the record was written"
    # Kept again in the new environment, it holds what that run ran and nothing older.
    green.write(tmp_path, {**ENV, part: "another"}, {CAM: "c1"})
    assert set(green.read(tmp_path, {**ENV, part: "another"}).entries) == {CAM}


def _environment_moves(root: Path, monkeypatch, tools: Path, act) -> set:
    monkeypatch.setenv("APOTHECARY_TOOLS_DIR", str(tools))
    before = green.environment(root)
    act()
    after = green.environment(root)
    return {part for part in before if before[part] != after[part]}


def _named(path):
    return lambda: path


@pytest.mark.parametrize(
    "part, act",
    [
        ("Python", lambda root, tools, mp: mp.setattr(sys, "version", sys.version + "+")),
        ("the lockfile", lambda root, tools, mp: _write(root, "uv.lock")),
        ("the lockfile", lambda root, tools, mp: _write(root, "pyproject.toml")),
        ("the conftests", lambda root, tools, mp: _write(root, "conftest.py")),
        ("the conftests", lambda root, tools, mp: _write(root, "tests/conftest.py")),
        ("tests/groups.py", lambda root, tools, mp: _write(root, "tests/groups.py")),
        (
            "OpenSCAD",
            lambda root, tools, mp: mp.setattr(
                "apothecary.openscad_installer.current_version", lambda: "2099.01.01"
            ),
        ),
        ("the tools folder", lambda root, tools, mp: (tools / "orcaslicer").mkdir()),
        (
            "the tools folder",
            lambda root, tools, mp: _write(tools, "arduino-cli/libraries", "FastLED"),
        ),
        (
            "node",
            lambda root, tools, mp: mp.setattr(green.shutil, "which", lambda name: sys.executable),
        ),
    ],
    ids=[
        "python",
        "the-lockfile",
        "pyproject",
        "the-root-conftest",
        "the-suite-conftest",
        "the-map",
        "another-openscad",
        "a-tool-installed",
        "a-tool-changed-inside",
        "node",
    ],
)
def test_each_part_of_the_environment_moves_with_what_it_names(
    checkout, tmp_path, monkeypatch, part, act
):
    root, _ = checkout
    tools = tmp_path / "tools"
    (tools / "arduino-cli").mkdir(parents=True)
    monkeypatch.setattr(green.shutil, "which", lambda name: None)
    moved = _environment_moves(root, monkeypatch, tools, lambda: act(root, tools, monkeypatch))
    assert moved == {part}


def test_the_openscad_part_names_the_executable_the_renders_use(monkeypatch, tmp_path):
    from apothecary.projects.parts import stl_renderer

    said = []
    for name, made in (("one", b"a"), ("two", b"bb")):
        (tmp_path / name).write_bytes(made)
        monkeypatch.setenv("APOTHECARY_OPENSCAD", str(tmp_path / name))
        monkeypatch.setattr(stl_renderer, "_renderer", None)  # the renderer, found again
        said.append(green.environment(tmp_path)["OpenSCAD"])
    assert str((tmp_path / "one").resolve()) in said[0]
    assert str((tmp_path / "two").resolve()) in said[1]


def _kept(tmp_path) -> dict:
    green.write(tmp_path, ENV, {JOBS: "d1"})
    return json.loads(green.record_path(tmp_path).read_text(encoding="utf-8"))


def _rewrite(tmp_path, kept: dict) -> None:
    green.record_path(tmp_path).write_text(json.dumps(kept), encoding="utf-8")


def _resealed(kept: dict) -> dict:
    body = {k: kept[k] for k in ("version", "environment", "entries")}
    return {**body, "seal": green._seal(body)}


@pytest.mark.parametrize(
    "tamper, said",
    [
        (lambda k: k["entries"][JOBS].update(digest="d2"), "does not hold what its seal says"),
        (lambda k: k["entries"].update({CAM: {"digest": "c", "at": "x"}}), "its seal says"),
        (lambda k: k["environment"].update(node="g"), "does not hold what its seal says"),
        (lambda k: k.pop("seal"), "does not read as a record"),
        (lambda k: k.update(seal="0" * 64), "does not hold what its seal says"),
    ],
    ids=[
        "a-digest-edited",
        "an-entry-added",
        "its-environment-edited",
        "no-seal",
        "a-seal-made-up",
    ],
)
def test_a_record_changed_by_hand_is_not_trusted(tmp_path, tamper, said):
    kept = _kept(tmp_path)
    tamper(kept)
    _rewrite(tmp_path, kept)
    record = green.read(tmp_path, ENV)
    assert record.entries == {} and said in record.distrust


@pytest.mark.parametrize(
    "written, said",
    [
        ("not json", "does not read as a record"),
        ("[1, 2]", "does not read as a record"),
        ('{"version": 1}', "does not read as a record"),
    ],
)
def test_a_record_that_does_not_read_is_not_trusted(tmp_path, written, said):
    path = green.record_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(written, encoding="utf-8")
    record = green.read(tmp_path, ENV)
    assert record.entries == {} and said in record.distrust


def test_a_record_of_another_version_or_shape_is_not_trusted_however_sealed(tmp_path):
    kept = _kept(tmp_path)
    _rewrite(tmp_path, _resealed({**kept, "version": green.VERSION + 1}))
    assert "another version" in green.read(tmp_path, ENV).distrust
    _rewrite(tmp_path, _resealed({**kept, "entries": [JOBS]}))
    assert "does not read as a record" in green.read(tmp_path, ENV).distrust


def test_the_record_is_kept_where_the_session_names_and_in_the_checkouts_cache_otherwise(
    monkeypatch, tmp_path
):
    """A test session names a file of its own (conftest.py), so no test's stand-in pass
    is kept for the checkout."""
    named = NAMED_BY_THE_SESSION[-1]
    assert named and not Path(named).resolve().is_relative_to(ROOT)
    monkeypatch.delenv(green.RECORD_ENV)
    assert green.record_path(tmp_path) == tmp_path / ".cache" / "test-changed" / "green.json"
    ignored = subprocess.run(
        ["git", "check-ignore", "-q", str(green.RECORD)], cwd=ROOT, check=False
    )
    assert ignored.returncode == 0, "the record's folder is not ignored"
