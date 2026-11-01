"""Carlos, run from a checkout of its own, for the browser tests that hold apothecary
and carlos together (``test_carlos_*.py``).

Carlos is another repository, so the checkout is named, never assumed:
``CARLOS_CHECKOUT``, its ``.venv`` synced, on a branch that holds a rig and turns it
in place. Without it these tests skip, saying so. Carlos is started as its demo
contract starts it (``carlos serve --port --state``), on a free port with a state
folder of the test's, and stopped when the module's tests are done. Its page is
carlos's, so these tests' pages have no apothecary server's address.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import time
import urllib.request
from pathlib import Path

import pytest
from browsers import CHROMIUM_MISSING

CHECKOUT_ENV = "CARLOS_CHECKOUT"
# No proxy: carlos is on this machine.
_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def checkout() -> Path:
    named = os.environ.get(CHECKOUT_ENV)
    if not named:
        pytest.skip(f"{CHECKOUT_ENV} names no carlos checkout to run carlos from")
    path = Path(named)
    if not (path / ".venv" / "bin" / "carlos").exists():
        pytest.skip(f"{path} has no synced .venv with carlos in it: run `uv sync` there")
    return path


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def family_state(url: str) -> dict:
    """What carlos holds: ``GET /family/state``."""
    with _OPENER.open(f"{url}/family/state", timeout=5) as answer:
        return json.load(answer)


@pytest.fixture(scope="module", name="carlos")
def carlos_server(tmp_path_factory):
    """Carlos on a port of its own, until the module's tests are done."""
    found = checkout()
    port = free_port()
    state = tmp_path_factory.mktemp("carlos-state")
    log = (tmp_path_factory.mktemp("carlos-log") / "carlos.log").open("w")
    server = subprocess.Popen(
        [
            str(found / ".venv" / "bin" / "carlos"),
            "serve",
            "--port",
            str(port),
            "--state",
            str(state),
        ],
        cwd=found,
        stdout=log,
        stderr=subprocess.STDOUT,
    )
    url = f"http://127.0.0.1:{port}"
    deadline = time.monotonic() + 30
    while True:
        try:
            with _OPENER.open(f"{url}/healthz", timeout=2):
                break
        except OSError:
            if server.poll() is not None or time.monotonic() > deadline:
                server.kill()
                pytest.fail(f"carlos did not start; its log is {log.name}")
            time.sleep(0.25)
    yield url
    server.terminate()
    try:
        server.wait(timeout=10)
    except subprocess.TimeoutExpired:
        server.kill()
    log.close()


@pytest.fixture(scope="session", autouse=True)
def _chromium_here(browser_type):
    if not Path(browser_type.executable_path).exists():
        pytest.skip(CHROMIUM_MISSING)


@pytest.fixture
def browser_context_args():
    """No apothecary server's address: the page is carlos's."""
    return {}


@pytest.fixture(scope="session")
def _verify_url():
    """pytest-base-url checks a server's address before each test; carlos's is checked here."""
