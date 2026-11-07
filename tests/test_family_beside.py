"""The members beside the hub, started by it and kept running."""

from __future__ import annotations

import json
import os
import signal
import socket
import sys
import time

import httpx
import pytest
from fastapi.testclient import TestClient

from apothecary.api import app
from apothecary.family import beside, hub, procedures

CUE = {"number": "1", "name": "a step", "fired_at": None}

# A member of its own, served alone: what `start` names.
MEMBER = """
import hearth
from hearth import web

class Clock(hearth.Member):
    name, family, verbs = "clock", "instruments", ("lap",)
    laps = 0
    def understand(self, action):
        return self._lap
    def _lap(self):
        self.laps += 1
    def state(self):
        return {"laps": self.laps}

app = web.app(Clock())
"""


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


@pytest.fixture(autouse=True)
def a_state_folder(tmp_path, monkeypatch):
    monkeypatch.setenv("APOTHECARY_STATE_DIR", str(tmp_path))
    monkeypatch.delenv("APOTHECARY_CARLOS", raising=False)
    hub.close()
    yield tmp_path
    hub.close()


@pytest.fixture
def table(a_state_folder):
    """A table starting one member; the url it answers at."""
    (a_state_folder / "clock_member.py").write_text(MEMBER, encoding="utf-8")
    port = _free_port()
    url = f"http://127.0.0.1:{port}"
    entry = {
        "command": [
            sys.executable,
            "-m",
            "uvicorn",
            "clock_member:app",
            "--port",
            str(port),
            "--log-level",
            "warning",
        ],
        "url": url,
        "cwd": str(a_state_folder),
    }
    (a_state_folder / hub.TABLE).write_text(json.dumps({"start": {"clock": entry}}), "utf-8")
    return url


def _up(url, within=60.0, unless=None):
    """The instance answering at ``url``, once one other than ``unless`` does."""
    deadline = time.monotonic() + within
    while time.monotonic() < deadline:
        try:
            said = httpx.get(f"{url}/family/identity", timeout=1.0).json()["instance"]
            if said != unless:
                return said
        except (httpx.HTTPError, ValueError, KeyError):
            pass
        time.sleep(0.1)
    raise AssertionError(f"nothing new answered at {url} within {within}s")


def test_the_hub_starts_a_member_delivers_to_it_and_credits_what_took_it(table):
    assert hub.running().members == {"clock": table}  # named at once, up or not
    hub.start()
    instance = _up(table)
    outcome = hub.deliver("clock", CUE, {"lap": 1})
    assert outcome["status"] == 200 and outcome["via"] == "push"
    assert outcome["instance"] == instance
    # The supervisor looks a little after the member first answers.
    deadline = time.monotonic() + 10.0
    while beside.status()["clock"]["state"] != "up" and time.monotonic() < deadline:
        time.sleep(0.05)
    said = TestClient(app).get("/family/beside").json()["clock"]
    assert said["state"] == "up" and said["restarts"] == 0


def test_a_member_that_stops_is_started_again_and_is_someone_new(table):
    hub.start()
    first = _up(table)
    os.kill(beside.status()["clock"]["pid"], signal.SIGKILL)
    second = _up(table, unless=first)
    outcome = hub.deliver("clock", {**CUE, "number": "2"}, {"lap": 1})
    assert outcome["instance"] == second != first


def test_every_member_stops_with_the_hub(table):
    hub.start()
    _up(table)
    hub.close()
    with pytest.raises(httpx.HTTPError):
        httpx.get(f"{table}/family/identity", timeout=1.0)
    assert beside.status() == {}


def test_nothing_starts_with_nothing_named():
    hub.start()
    assert beside.status() == {}
    assert TestClient(app).get("/family/beside").json() == {}


@pytest.mark.parametrize(
    "entry",
    [
        "carlos serve",
        {"command": ["carlos"]},
        {"url": "http://127.0.0.1:9"},
        {"command": "carlos serve", "url": "http://127.0.0.1:9"},
        {"command": [], "url": "http://127.0.0.1:9"},
        {"command": ["carlos"], "url": "http://192.168.1.4:9"},
    ],
)
def test_an_entry_that_will_not_read_is_left_out_and_said(a_state_folder, entry, caplog):
    (a_state_folder / hub.TABLE).write_text(json.dumps({"start": {"far": entry}}), "utf-8")
    hub.start()
    assert beside.status() == {}
    assert "far" not in hub.running().members
    assert "start far is left out" in caplog.text


def test_a_tables_problem_is_said_once_however_often_it_is_read(a_state_folder, caplog):
    table = {"start": {"far": {"command": ["carlos"], "url": "http://192.168.1.4:9"}}}
    (a_state_folder / hub.TABLE).write_text(json.dumps(table), "utf-8")
    for _ in range(3):
        hub.running()
    assert caplog.text.count("start far is left out") == 1


def test_a_member_is_started_without_what_would_redirect_a_fetch(monkeypatch):
    monkeypatch.setenv("https_proxy", "http://elsewhere:3128")
    monkeypatch.setenv("VIRTUAL_ENV", "/this/projects/venv")
    entry = {"command": ["carlos"], "url": "http://127.0.0.1:9"}
    env = beside.specs({"carlos": entry}, hub.TABLE)[0].env
    assert env["https_proxy"] is None and env["VIRTUAL_ENV"] is None


def test_a_step_holds_the_sites_wiring_as_it_is_when_it_fires(fake_arduino_cli, a_carlos):
    url, heard, _ = a_carlos
    hub.table_file().parent.mkdir(parents=True, exist_ok=True)
    hub.table_file().write_text(json.dumps({"members": {"carlos": url}}), "utf-8")
    assert hub.carlos_at() == url
    body = {
        "steps": [
            {
                "number": "1",
                "name": "Hold the bench",
                "discipline": "network",
                "family": {"carlos": {"hold": {"wiring": "garage"}}},
            }
        ]
    }
    client = TestClient(app, client=("127.0.0.1", 50000), base_url="http://127.0.0.1")
    route = "/sites/garage/procedures/hold"
    assert client.put(route, json=body).status_code == 200
    answer = client.post(f"{route}/steps/1/go").json()["steps"][0]
    assert answer["status"] == procedures.DONE, answer
    assert answer["outcomes"][0]["status"] == 200
    path, held = heard[-1]
    assert path == "/family/cue"
    assert set(held["action"]["hold"]) == {"patch", "devices", "states"}
