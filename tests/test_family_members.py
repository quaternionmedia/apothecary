"""The family's own members, hosted in the hub, against the simulated bench."""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient
from hearth import conformance

from apothecary.api import app
from apothecary.demo import BOARD, CONTROLLER, DEVKIT, PRINTER, ROUTER, SITE
from apothecary.family import hub, members
from apothecary.firmware import devices, gcode
from apothecary.firmware import tasks as firmware_tasks

MACHINE_NODE = f"{SITE}:{BOARD}"
ROUTER_NODE = f"{SITE}:{CONTROLLER}"
SKETCH = "esp32_blink"
CUE = {"number": "1", "name": "a step", "fired_at": None}


@pytest.fixture
def bench(fake_arduino_cli, monkeypatch, tmp_path):
    """The demo's bench: the Ender and the router simulated and pinned, the devkit scripted."""
    monkeypatch.setenv("APOTHECARY_SERIAL_ENGINE", "simulated")
    monkeypatch.setenv("APOTHECARY_SIMULATED_ROUTER", ROUTER)
    monkeypatch.setenv("APOTHECARY_SIMULATED_SPEED", "0")
    monkeypatch.setenv("FAKE_DEVKIT", "1")
    monkeypatch.setenv("FAKE_ROUTER", "1")
    links = gcode.PrinterLinks()
    monkeypatch.setattr(gcode, "_LINKS", links)
    monkeypatch.setattr(firmware_tasks, "_RUNNER", firmware_tasks.TaskRunner())
    hub.close()
    for port, path in ((PRINTER, BOARD), (ROUTER, CONTROLLER)):
        devices.identify_printer(port)
        devices.get_state().set_binding(SITE, path, port)
    yield links
    links.stop_all()
    hub.close()


def _ended(name, cue, within=30.0):
    """How a member's work on ``cue`` ended, once it has."""
    member = members.hosted(name)
    deadline = time.monotonic() + within
    while time.monotonic() < deadline:
        ended = member.ended(cue)
        if ended is not None:
            return ended
        time.sleep(0.02)
    raise AssertionError(f"{name} did not end {cue} within {within}s")


def _deliver(name, action, number="1"):
    cue = {**CUE, "number": number}
    return cue, hub.deliver(name, cue, action)


def test_the_hub_hosts_its_members_and_a_page_reads_the_camera(bench):
    said = TestClient(app).get("/family/").json()["members"]
    assert said["machine"]["via"] == "local" and said["board"]["via"] == "local"
    assert said["camera"]["via"] == "pull"


def test_each_says_it_is_of_the_family(bench):
    client = TestClient(app)
    for name in ("machine", "board"):
        identity = client.get(f"/{name}/family/identity").json()
        assert (identity["member"], identity["family"]) == (name, "irl")


def test_a_page_from_elsewhere_reads_no_member_though_its_routes_are_open():
    client = TestClient(app, client=("127.0.0.1", 50000), base_url="http://127.0.0.1")
    assert client.get("/machine/family/state").status_code == 200
    foreign = {"Origin": "https://example.org"}
    assert client.get("/machine/family/state", headers=foreign).status_code == 403
    body = {"cue": CUE, "action": {"home": True}}
    assert client.post("/machine/family/cue", json=body, headers=foreign).status_code == 403


def test_a_step_moving_a_machine_is_refused_with_the_latch_down_and_changes_nothing(bench):
    before = members.hosted("machine").snapshot()["cue"]
    _, outcome = _deliver("machine", {"home": {"node": MACHINE_NODE}})
    assert outcome["status"] == 422 and "arm its control first" in outcome["error"]
    assert members.hosted("machine").snapshot()["cue"] == before


def test_a_machine_homes_when_its_latch_is_up_each_in_its_own_dialect(bench):
    for port, node, line in ((PRINTER, MACHINE_NODE, "G28"), (ROUTER, ROUTER_NODE, "$H")):
        bench.control.arm(port)
        cue, outcome = _deliver("machine", {"home": {"node": node}}, number=node)
        assert outcome["status"] == 202 and outcome["via"] == "local"
        assert outcome["instance"] == members.hosted("machine").instance
        ended = _ended("machine", cue)
        assert ended["ok"], ended.get("error")
        assert ended["line"] == line and ended["node"] == node


def test_with_two_machines_pinned_it_asks_which(bench):
    _, outcome = _deliver("machine", {"home": True})
    assert outcome["status"] == 422
    assert MACHINE_NODE in outcome["error"] and ROUTER_NODE in outcome["error"]


def test_a_node_with_no_machine_is_refused(bench):
    _, outcome = _deliver("machine", {"home": {"node": "garage:the_kettle"}})
    assert outcome["status"] == 422 and "no machine is pinned" in outcome["error"]


def test_one_verb_at_a_time(bench):
    _, outcome = _deliver("machine", {"home": True, "pause": True})
    assert outcome["status"] == 422 and "one verb at a time" in outcome["error"]


def test_pausing_nothing_is_refused(bench):
    _, outcome = _deliver("machine", {"pause": {"node": MACHINE_NODE}})
    assert outcome["status"] == 422 and "no job is running" in outcome["error"]


def test_a_kept_file_no_one_kept_is_refused(bench):
    bench.control.arm(PRINTER)
    _, outcome = _deliver("machine", {"run": {"node": MACHINE_NODE, "file": "nothing"}})
    assert outcome["status"] == 422 and "no such kept file" in outcome["error"]


def test_a_board_is_flashed_and_says_its_hello(bench):
    flash = {"port": DEVKIT, "sketch": f"{SKETCH}@arduino"}
    cue, outcome = _deliver("board", {"flash": flash}, number="flash")
    assert outcome["status"] == 202
    ended = _ended("board", cue)
    assert ended["ok"], ended.get("error")
    assert ended["sketch"] == f"{SKETCH}@arduino"
    # The flash is the node's now, by the by-sketch rule, so the node names the board.
    cue, outcome = _deliver("board", {"expect": {"node": f"{SITE}:{SKETCH}"}}, number="expect")
    assert outcome["status"] == 202, outcome
    ended = _ended("board", cue)
    assert ended["ok"] and ended["heard"] == SKETCH


def test_a_name_two_sketches_share_is_refused_saying_which(bench):
    _, outcome = _deliver("board", {"flash": {"port": DEVKIT, "sketch": SKETCH}})
    assert outcome["status"] == 422 and f"{SKETCH}@arduino" in outcome["error"]


def test_a_hello_not_heard_ends_as_a_failure_the_state_says(bench):
    cue, outcome = _deliver("board", {"expect": {"port": DEVKIT, "hello": "footpedal"}})
    assert outcome["status"] == 202
    ended = _ended("board", cue)
    assert not ended["ok"] and "not footpedal's" in ended["error"]
    assert members.hosted("board").snapshot()["state"]["last"]["ok"] is False


def test_a_port_a_task_is_writing_to_is_refused(bench, monkeypatch):
    held = type("Task", (), {"port": DEVKIT, "title": "Upload"})()
    monkeypatch.setattr(firmware_tasks.TaskRunner, "active", held)
    _, outcome = _deliver("board", {"expect": {"port": DEVKIT, "hello": SKETCH}})
    assert outcome["status"] == 422 and "is held" in outcome["error"]


@pytest.mark.parametrize(
    ("name", "action"),
    [
        ("machine", {"home": {"node": MACHINE_NODE}}),
        ("board", {"expect": {"port": DEVKIT, "hello": SKETCH}}),
    ],
)
def test_hearths_check_finds_each_member_conforms(bench, served, name, action):
    """By its routes alone, with one real action sent to the simulated bench."""
    bench.control.arm(PRINTER)
    report = conformance.check(f"{served}/{name}", action=action, timeout=10.0)
    failed = [f for f in report.findings if not f.ok]
    assert report.status == 0 and not failed, failed
