"""The state folder has one module: where it is, how a folder in it is made the
person's alone, and how a record reaches it whole (apothecary/state_folder.py)."""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

import pytest

from apothecary import state_folder

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "apothecary"
VARIABLE = "APOTHECARY_STATE_DIR"


def _reads_the_variable(tree: ast.AST) -> bool:
    """Whether the module reads the state folder's variable: ``os.environ.get``,
    ``os.getenv`` or a subscript of it. Naming it as a key of a dict it builds for
    another process (the demo, the docs' example) is not a read."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if (
                getattr(func, "attr", None) in ("get", "getenv", "pop")
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and node.args[0].value == VARIABLE
            ):
                return True
        elif isinstance(node, ast.Subscript) and isinstance(node.ctx, ast.Load):
            key = node.slice
            if isinstance(key, ast.Constant) and key.value == VARIABLE:
                return True
    return False


def test_the_package_has_one_reader_of_the_state_folder_s_variable():
    """Where the folder is, is the leaf's to say: no other module reads the
    variable or spells the default."""
    readers = sorted(
        source.relative_to(PACKAGE).as_posix()
        for source in PACKAGE.rglob("*.py")
        if source.name != "state_folder.py"
        and _reads_the_variable(ast.parse(source.read_text(encoding="utf-8")))
    )
    assert readers == []


def test_a_job_is_listed_without_the_firmware_package(tmp_path):
    """The jobs module keeps its records through the leaf, so a process that lists
    jobs never imports the firmware package for the folder's name."""
    run = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys\n"
            "from apothecary import jobs\n"
            "jobs.list_jobs()\n"
            "print(sorted(m for m in sys.modules if m.startswith('apothecary.firmware')))\n",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=120,
        env={**dict(__import__("os").environ), VARIABLE: str(tmp_path / "state")},
    )
    assert run.returncode == 0, run.stderr
    assert run.stdout.strip() == "[]"


def test_a_record_that_fails_to_write_leaves_the_one_there(tmp_path, monkeypatch):
    monkeypatch.setenv(VARIABLE, str(tmp_path))
    path = tmp_path / "records" / "one.json"
    assert state_folder.write_whole(path, "first") == path
    assert path.read_text(encoding="utf-8") == "first"
    assert path.parent.stat().st_mode & 0o777 == 0o700  # the person's alone

    def refuse(src, dst):
        raise OSError("no room")

    monkeypatch.setattr(state_folder.os, "replace", refuse)
    with pytest.raises(OSError):
        state_folder.write_whole(path, "second")
    assert path.read_text(encoding="utf-8") == "first"
    assert [p.name for p in path.parent.iterdir()] == ["one.json"]  # no half-written file left
