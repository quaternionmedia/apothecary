"""Every test has a time bound, run here or in CI (conftest.py): each phase of it ends
at twice the longest test the suite records, the process with it. No bound is chosen
by hand."""

import json
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def root_conftest(pytestconfig):
    """The repository root's conftest, as the session registered it (tests/ has a
    conftest of its own, so `import conftest` would name either)."""
    return pytestconfig.pluginmanager.get_plugin(str(ROOT / "conftest.py"))


def test_the_ceiling_is_twice_the_longest_recorded_test(root_conftest):
    assert root_conftest.ceiling({"a": 1.2, "b": 40.1, "c": 3}) == 81
    assert root_conftest.ceiling({}) is None


def test_each_phase_of_a_test_is_ended_at_the_ceiling(pytestconfig, root_conftest):
    known = json.loads((ROOT / "tests" / "e2e" / "durations.json").read_text())
    assert pytestconfig.stash[root_conftest.CEILING] == root_conftest.ceiling(known)
    for phase in ("setup", "call", "teardown"):
        hook = getattr(pytestconfig.pluginmanager.hook, f"pytest_runtest_{phase}")
        assert any(i.plugin is root_conftest and i.wrapper for i in hook.get_hookimpls())


def test_a_phase_past_its_bound_ends_the_process_with_its_stack():
    """A regular expression backtracking in C holds the interpreter: no signal handler
    runs until it returns, and the bound ends it all the same."""
    script = (
        "import re, sys\n"
        f"sys.path.insert(0, {str(ROOT)!r})\n"
        "from conftest import ended_after\n"
        "with ended_after(1, 2):\n"
        "    re.match(r'(a+)+$', 'a' * 64 + 'b')\n"
    )
    began = time.monotonic()
    ended = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, timeout=60
    )
    assert ended.returncode == 1
    assert "Timeout (0:00:01)!" in ended.stderr
    assert time.monotonic() - began < 30
