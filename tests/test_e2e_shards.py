"""The browser suite's shards keep each file whole and share the time out evenly."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "e2e"))

from shards import shard_of  # noqa: E402


def test_every_file_lands_on_exactly_one_shard():
    files = {f"f{i}.py": float(i) for i in range(10)}
    placed = shard_of(files, 3)
    assert set(placed) == set(files)
    assert set(placed.values()) == {0, 1, 2}


def test_the_heaviest_file_is_alone_when_it_outweighs_the_rest():
    placed = shard_of({"heavy.py": 100.0, "a.py": 10.0, "b.py": 10.0, "c.py": 10.0}, 2)
    assert [f for f, s in placed.items() if s == placed["heavy.py"]] == ["heavy.py"]


def test_the_shards_are_within_the_largest_file_of_each_other():
    files = {
        "a.py": 98.0,
        "b.py": 82.4,
        "c.py": 65.4,
        "d.py": 35.4,
        "e.py": 30.4,
        "f.py": 30.4,
        "g.py": 29.5,
        "h.py": 19.5,
        "i.py": 8.3,
        "j.py": 6.4,
    }
    placed = shard_of(files, 3)
    load = [sum(s for f, s in files.items() if placed[f] == k) for k in range(3)]
    assert max(load) - min(load) <= max(files.values())


def _skipped(*args: str) -> str:
    """A browser run of the firmware steps with no server named, its skips said."""
    import os
    import subprocess

    done = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/e2e/test_steps_firmware.py", "-rs", *args],
        cwd=Path(__file__).resolve().parents[1],
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert done.returncode == 0, done.stdout[-2000:] + done.stderr[-2000:]
    return done.stdout


def test_the_step_through_tests_skip_unless_asked_for():
    """Each walks a loop another browser test holds end to end, so a browser run skips
    them and says how to run them; under --steps they go on to their servers (and here,
    with none named, skip for that reason instead)."""
    assert "runs with --steps, or one step with --step N" in _skipped()
    assert "runs with --steps" not in _skipped("--steps")


def test_in_ci_a_recorded_browser_test_is_capped_at_twice_its_time_and_no_other_is():
    """tests/e2e/conftest.py's caps: twice the recorded time, for a recorded test with
    no cap of its own; none for one with no record, or with its own."""
    import importlib.util
    import json

    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location("e2e_conftest", root / "tests/e2e/conftest.py")
    conftest = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(conftest)

    class Item:
        def __init__(self, nodeid, own=None):
            self.nodeid, self._own = nodeid, own

        def get_closest_marker(self, name):
            return self._own if name == "timeout" else None

    known = json.loads((root / "tests" / "e2e" / "durations.json").read_text())
    nodeid, seconds = next(iter(known.items()))
    assert conftest.recorded_caps(
        [Item(nodeid), Item("tests/e2e/test_new.py::test_unrecorded")], known
    ) == {nodeid: -(-2 * seconds // 1)}
    assert conftest.recorded_caps([Item(nodeid, own=1)], known) == {}
