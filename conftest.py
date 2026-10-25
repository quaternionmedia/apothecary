"""What every pytest session in this repository starts from -- the unit tests
under ``tests/``, the browser tests under ``tests/e2e/``, and the walkthrough
pages under ``walkthrough/``, whose examples run as doctests.

The app answers this machine only (``apothecary/stays_local.py``). Starlette's
``TestClient`` presents itself as "testclient" at "testserver", which is
nowhere; every test here runs on this machine, so what the client presents is
this machine. The guard goes on here, before any test is collected, so a
test connects to nothing past this machine whichever module it imports.

The state folder is the run's own too: a site a test builds is given the
cameras recorded in the state folder, and a person's own (``~/.apothecary``)
must neither appear in a test's site nor be written by one.

Every test has a time bound, run here or in CI: each phase of it -- its setup,
its call, its teardown -- ends at the ceiling below, twice the longest test the
suite records, and the process with it, every thread's stack written. So a hang
no signal reaches -- a fixture's teardown spinning, a loop in C -- still ends, and
under xdist the worker's crash names the test. No bound is chosen by hand. In CI a
browser test the suite records also fails at twice its recorded time
(``tests/e2e/conftest.py``).
"""

from apothecary.stays_local import install_guard

install_guard()

import faulthandler
import json
import math
import os
from contextlib import contextmanager
from pathlib import Path

import pytest
import starlette.testclient as _st

DURATIONS = Path(__file__).parent / "tests" / "e2e" / "durations.json"

_test_client_init = _st.TestClient.__init__


def _from_this_machine(
    self, app, base_url="http://127.0.0.1", *args, client=("127.0.0.1", 50000), **kwargs
):
    _test_client_init(self, app, base_url, *args, client=client, **kwargs)


_st.TestClient.__init__ = _from_this_machine


@pytest.fixture(autouse=True, scope="session")
def _state_folder_of_the_runs_own(tmp_path_factory):
    """Pins and camera records go to a state folder of the run's own unless a test
    names another; never the person's."""
    previous = os.environ.get("APOTHECARY_STATE_DIR")
    os.environ["APOTHECARY_STATE_DIR"] = str(tmp_path_factory.mktemp("state"))
    yield
    if previous is None:
        os.environ.pop("APOTHECARY_STATE_DIR", None)
    else:
        os.environ["APOTHECARY_STATE_DIR"] = previous


def ceiling(known: dict) -> int | None:
    """Every phase's bound: twice the longest test the suite records."""
    return math.ceil(2 * max(known.values())) if known else None


CEILING = pytest.StashKey[int | None]()
STDERR = pytest.StashKey[int]()


def pytest_configure(config):
    known = json.loads(DURATIONS.read_text()) if DURATIONS.exists() else {}
    config.stash[CEILING] = ceiling(known)
    # stderr as it is before any test captures it, for a phase's stack.
    config.stash[STDERR] = os.dup(2)


def pytest_unconfigure(config):
    os.close(config.stash[STDERR])


@contextmanager
def ended_after(seconds: int | None, stderr: int):
    """The process ends, every thread's stack written to ``stderr``, if the block runs
    past ``seconds``: from a thread of the interpreter's own, so a loop that never
    returns to Python is ended too. Under xdist the worker's crash names the test."""
    if seconds is None:
        yield
        return
    faulthandler.dump_traceback_later(seconds, exit=True, file=stderr)
    try:
        yield
    finally:
        faulthandler.cancel_dump_traceback_later()


# One phase at a time: pytest cancels a pending dump when a phase fails
# (pytest_exception_interact), so a bound spanning the test would be gone by the
# teardown that follows a failed call.
@pytest.hookimpl(wrapper=True)
def pytest_runtest_setup(item):
    with ended_after(item.config.stash[CEILING], item.config.stash[STDERR]):
        return (yield)


@pytest.hookimpl(wrapper=True)
def pytest_runtest_call(item):
    with ended_after(item.config.stash[CEILING], item.config.stash[STDERR]):
        return (yield)


@pytest.hookimpl(wrapper=True)
def pytest_runtest_teardown(item, nextitem):
    with ended_after(item.config.stash[CEILING], item.config.stash[STDERR]):
        return (yield)
