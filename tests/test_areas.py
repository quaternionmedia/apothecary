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
        (["tests/e2e/rings.py"], areas.ALL),
        (["apothecary/firmware/gcode.py"], ["tests/e2e/test_one_machine.py"]),
        (["tests/e2e/test_ring.py"], ["tests/e2e/test_ring.py"]),
        (["tests/e2e/test_gone.py"], []),
        (["docs/viewer.md", "apothecary/cli/release.py"], []),
    ],
    ids=[
        "the-page",
        "a-browser-helper",
        "a-board",
        "a-browser-file",
        "a-deleted-browser-file",
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
