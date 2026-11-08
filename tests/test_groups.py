"""The unit suite's groups (tests/groups.py): every unit file is in one group, every
pattern names something this checkout tracks, every module of the package is in a
group or shared ground, and a change reaches the files of the groups it touches, all
of them when it touches shared ground."""

from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("groups", ROOT / "tests/groups.py")
groups = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(groups)

TRACKED = subprocess.run(
    ["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True
).stdout.splitlines()
PATTERNS = [*groups.SHARED, *(s for group in groups.GROUPS.values() for s in group["sources"])]


def test_every_unit_file_is_in_one_group():
    files = sorted(p.name for p in (ROOT / "tests").glob("test_*.py"))
    held = [name for group in groups.GROUPS.values() for name in group["tests"]]
    assert sorted(held) == files, {
        "in no group": sorted(set(files) - set(held)),
        "no such file": sorted(set(held) - set(files)),
        "in two": sorted({n for n in held if held.count(n) > 1}),
    }


@pytest.mark.parametrize("pattern", PATTERNS)
def test_every_pattern_names_something_tracked(pattern):
    assert any(groups._matches(path, [pattern]) for path in TRACKED), pattern


def test_every_module_of_the_package_reaches_some_unit_file():
    """A module no group names would reach no test in `apothecary test changed`."""
    modules = [p for p in TRACKED if p.startswith("apothecary/") and p.endswith(".py")]
    assert [p for p in modules if not groups._matches(p, PATTERNS)] == []


def _of(name):
    return [f"tests/{n}" for n in groups.GROUPS[name]["tests"]]


@pytest.mark.parametrize(
    "changed, reached",
    [
        (["apothecary/api.py"], groups.ALL),
        (["tests/conftest.py"], groups.ALL),
        (["tests/a_helper_nothing_imports.py"], []),
        (["apothecary/firmware/gcode.py"], _of("machines")),
        (["apothecary/cam/toolpath.py"], _of("making")),
        (["tests/slicer_helpers.py"], groups.ALL),
        (["tests/ring_helpers.py"], _of("viewer")),
        (["tests/e2e/areas.py"], _of("cli") + _of("repository")),
        (["tests/test_jobs.py"], ["tests/test_jobs.py"]),
        (["tests/test_gone.py"], []),
        (["apothecary/family/hub.py", "docs/cnc.md"], _of("family") + _of("repository")),
        (["Cargo.toml"], []),
    ],
    ids=[
        "the-app",
        "the-conftest",
        "a-helper-nothing-imports",
        "a-board",
        "a-toolpath",
        "a-helper-the-conftest-imports",
        "a-helper-of-one-group",
        "the-browser-map",
        "a-unit-file",
        "a-deleted-unit-file",
        "two-groups",
        "nothing-a-unit-file-runs",
    ],
)
def test_a_change_reaches_the_files_of_its_groups(changed, reached):
    assert groups.reached(changed) == reached


# A suite of its own: who imports whom, in each form an import statement takes.
SUITE = {
    "conftest.py": "",
    "tests/conftest.py": "from fixtures_helper import made\n",
    "tests/fixtures_helper.py": "import base_helper\n",
    "tests/base_helper.py": "",
    "tests/solo_helper.py": "",
    "tests/test_one.py": "from solo_helper import thing\nimport gone_helper\n",
    "tests/via_helper.py": "from . import under_helper\n",
    "tests/under_helper.py": "",
    "tests/test_two.py": "def test_it():\n    from tests.via_helper import thing\n",
    "tests/unused_helper.py": "",
    "tests/test_three.py": "SCRIPT = 'import unused_helper'\nimport shared\n",
    "tests/e2e/conftest.py": "import browser_only\n",
    "tests/e2e/browser_only.py": "",
    "tests/e2e/shared.py": "",
    "tests/test_broken.py": "import half_helper\ndef half(\n",
}


@pytest.mark.parametrize(
    "changed, reached",
    [
        (["tests/solo_helper.py"], ["tests/test_one.py"]),
        (["tests/under_helper.py"], ["tests/test_two.py"]),
        (["tests/via_helper.py"], ["tests/test_two.py"]),
        (["tests/base_helper.py"], groups.ALL),
        (["tests/fixtures_helper.py"], groups.ALL),
        (["tests/unused_helper.py"], []),
        (["tests/gone_helper.py"], ["tests/test_one.py"]),
        (["tests/e2e/browser_only.py"], _of("repository")),
        (["tests/e2e/shared.py"], _of("repository") + ["tests/test_three.py"]),
        (["tests/half_helper.py"], ["tests/test_broken.py"]),
    ],
    ids=[
        "a-helper-one-file-imports",
        "a-helper-imported-through-another",
        "the-helper-between",
        "a-helper-the-conftest-imports-through-another",
        "a-helper-the-conftest-imports",
        "a-helper-only-a-string-names",
        "a-deleted-helper-still-imported",
        "a-helper-only-the-browser-conftest-imports",
        "a-browser-helper-a-unit-file-imports",
        "a-file-mid-edit-that-spells-it",
    ],
)
def test_a_helper_reaches_the_unit_files_that_import_it(tmp_path, monkeypatch, changed, reached):
    for path, text in SUITE.items():
        (tmp_path / path).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / path).write_text(text, encoding="utf-8")
    monkeypatch.setattr(groups, "ROOT", tmp_path)
    assert groups.reached(changed) == reached


def test_a_group_is_named_or_refused():
    assert groups.files(["making"]) == _of("making")
    with pytest.raises(KeyError, match="no group named nowhere"):
        groups.files(["nowhere"])
