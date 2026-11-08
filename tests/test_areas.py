"""The browser suite's areas (tests/e2e/areas.py): every browser file is in one area,
every pattern names something this checkout tracks, and a change reaches the files of
the areas it touches, all of them when it touches shared ground."""

from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("areas", ROOT / "tests/e2e/areas.py")
areas = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(areas)

TRACKED = subprocess.run(
    ["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True
).stdout.splitlines()


def test_every_browser_file_is_in_one_area():
    files = sorted(p.name for p in (ROOT / "tests" / "e2e").glob("test_*.py"))
    held = [name for area in areas.AREAS.values() for name in area["tests"]]
    assert sorted(held) == files, {
        "in no area": sorted(set(files) - set(held)),
        "no such file": sorted(set(held) - set(files)),
        "in two": sorted({n for n in held if held.count(n) > 1}),
    }


@pytest.mark.parametrize(
    "pattern",
    [*areas.SHARED, *(s for area in areas.AREAS.values() for s in area["sources"])],
)
def test_every_pattern_names_something_tracked(pattern):
    assert any(areas._matches(path, [pattern]) for path in TRACKED), pattern


@pytest.mark.parametrize(
    "changed, reached",
    [
        (["templates/fractal_viewer.html.j2"], areas.ALL),
        (["conftest.py"], areas.ALL),
        (["tests/e2e/rings.py"], areas.ALL),
        (["tests/views_helpers.py"], areas.ALL),
        (["tests/e2e/stepping.py"], ["tests/e2e/test_steps_firmware.py"]),
        (["tests/e2e/areas.py"], []),
        (["tests/e2e/picture_drift.py"], []),
        (["apothecary/firmware/gcode.py"], ["tests/e2e/test_one_machine.py"]),
        (["tests/e2e/test_ring.py"], ["tests/e2e/test_ring.py"]),
        (["tests/e2e/test_gone.py"], []),
        (["tests/conformance/nine_cells.json"], ["tests/e2e/test_ring.py"]),
        (["tests/assignment_cases.json"], ["tests/e2e/test_assignments_in_the_page.py"]),
        (["tests/rig_catalogue.json"], []),
        (["docs/viewer.md", "apothecary/cli/release.py"], []),
    ],
    ids=[
        "the-page",
        "the-root-conftest",
        "a-helper-the-conftest-imports",
        "a-unit-helper-the-conftest-imports",
        "a-helper-some-files-import",
        "this-map",
        "a-helper-no-browser-file-imports",
        "a-board",
        "a-browser-file",
        "a-deleted-browser-file",
        "a-vector-a-browser-file-reads",
        "a-table-a-browser-file-reads",
        "a-table-no-browser-file-reads",
        "nothing-the-page-runs",
    ],
)
def test_a_change_reaches_the_files_of_its_areas(changed, reached):
    got = areas.reached(changed)
    if reached == areas.ALL or not reached:
        assert got == reached
    else:
        assert set(reached) <= set(got)
        if changed[0].startswith("apothecary/firmware/"):
            machine = {f"tests/e2e/{n}" for n in areas.AREAS["machine"]["tests"]}
            assert set(got) == machine


# A suite of its own: who imports whom, in each form an import statement takes.
SUITE = {
    "conftest.py": "",
    "tests/conftest.py": "def made():\n    from unit_helper import made\n",
    "tests/unit_helper.py": "",
    "tests/e2e/conftest.py": "import page_helper\n",
    "tests/e2e/page_helper.py": "from .deep import thing\n",
    "tests/e2e/deep.py": "",
    "tests/e2e/solo.py": "",
    "tests/e2e/test_one.py": "import solo\nimport gone\n",
    "tests/e2e/via.py": "from tests.e2e import under\n",
    "tests/e2e/under.py": "",
    "tests/e2e/test_two.py": "def test_it():\n    from via import thing\n",
    "tests/e2e/unused.py": "",
    "tests/e2e/test_three.py": "SCRIPT = 'import unused'\nfrom views import picture\n",
    "tests/views.py": "",
}


@pytest.mark.parametrize(
    "changed, reached",
    [
        (["tests/e2e/solo.py"], ["tests/e2e/test_one.py"]),
        (["tests/e2e/under.py"], ["tests/e2e/test_two.py"]),
        (["tests/e2e/via.py"], ["tests/e2e/test_two.py"]),
        (["tests/e2e/deep.py"], areas.ALL),
        (["tests/e2e/page_helper.py"], areas.ALL),
        (["tests/unit_helper.py"], areas.ALL),
        (["tests/e2e/unused.py"], []),
        (["tests/e2e/gone.py"], ["tests/e2e/test_one.py"]),
        (["tests/views.py"], ["tests/e2e/test_three.py"]),
        (
            ["tests/e2e/solo.py", "tests/e2e/under.py"],
            [
                "tests/e2e/test_one.py",
                "tests/e2e/test_two.py",
            ],
        ),
    ],
    ids=[
        "a-helper-one-file-imports",
        "a-helper-imported-through-another",
        "the-helper-between",
        "a-helper-the-conftest-imports-through-another",
        "a-helper-the-conftest-imports",
        "a-helper-a-parent-conftest-imports",
        "a-helper-only-a-string-names",
        "a-deleted-helper-still-imported",
        "a-unit-helper-a-browser-file-imports",
        "two-helpers",
    ],
)
def test_a_helper_reaches_the_browser_files_that_import_it(tmp_path, monkeypatch, changed, reached):
    for path, text in SUITE.items():
        (tmp_path / path).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / path).write_text(text, encoding="utf-8")
    monkeypatch.setattr(areas, "ROOT", tmp_path)
    assert areas.reached(changed) == reached
