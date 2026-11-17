"""``can_now`` says a command is refused exactly when the route refuses it.

Each case puts a simulated machine in one condition (latch down, a task on the
port, a cut under way, a home not proved, a card printing, a board gone quiet),
asks ``can_now`` first, then sends the command to the real route and compares:
``ok: false`` with a reason where the route answers 4xx or 5xx, ``ok: true`` where
it accepts. The predicates are the ones the routes raise from
(``apothecary/firmware/can.py``), so a case that disagrees is a predicate that
was bent in one place.
"""

import threading
import time
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from firmware_helpers import PRINTING, ScriptedTransport

from apothecary.api import app
from apothecary.firmware import api as firmware_api
from apothecary.firmware import can, devices, gcode, grbl, tasks

PORT = "/dev/ttyFAKE1"

SMALL_PRINT = "G28\nG1 X1\nG1 X2\nG1 X3\n"
DWELLS = "M3 S12000\n" + "G4 P1\n" * 60 + "M5\n"

# The line each command sends, in each machine's dialect.
LINES = {
    "printer": {
        "home": "G28",
        "off": "M104 S0",
        "heat": "M104 S200",
        "spindle": "M3 S1000",
        "unlock": "$X",
        "resume": "RESUME",
        "interrupt": "M108",
        "quickstop": "M410",
        "card.pause": "M25",
        "control": "M84",
        "query": "M105",
    },
    "router": {
        "home": "$H",
        "home.X": "$HX",
        "off": "M5",
        "heat": "M104 S200",
        "spindle": "M3 S1000",
        "unlock": "$X",
        "resume": "RESUME",
        "interrupt": "HOLD",
        "quickstop": "JOG-CANCEL",
        "card.pause": "M25",
        "control": "G0 X0 Y0",
        "query": "$G",
    },
}
COMMAND_VERBS = [
    "home",
    "home.X",
    "off",
    "heat",
    "spindle",
    "unlock",
    "resume",
    "interrupt",
    "quickstop",
    "card.pause",
    "control",
]
PORT_VERBS = ["reconnect", "reset", "release"]
LEVEL_VERBS = ["level.probe", "level.read"]
PRINT_VERBS = ["print.start", "print.pause", "print.resume", "print.cancel"]
ALL_VERBS = [
    "jog",
    *COMMAND_VERBS,
    *PRINT_VERBS,
    *LEVEL_VERBS,
    *PORT_VERBS,
    "query",
]


class Rig:
    def __init__(self, kind, links, client, monkeypatch):
        self.kind, self.links, self.client = kind, links, client
        self.monkeypatch = monkeypatch
        self.file_id = None
        self.job = None
        self.gate = threading.Event()

    # -- conditions ---------------------------------------------------------
    def poll(self):
        """The port opened and identified, as a page's first poll does."""
        return devices.printer_status(PORT)

    def arm(self):
        self.links.control.arm(PORT)

    def keep_a_file(self, text=SMALL_PRINT):
        machine = "router" if self.kind == "router" else "printer"
        self.file_id = devices.save_print_file("file.gcode", text.encode(), machine=machine).id

    def task_on_the_port(self):
        active = SimpleNamespace(id="t1", title="upload", port=PORT, snapshot=lambda: {"id": "t1"})
        runner = SimpleNamespace(active=active)
        self.monkeypatch.setattr(firmware_api, "get_task_runner", lambda: runner)
        self.monkeypatch.setattr(tasks, "get_task_runner", lambda: runner)

    def a_print_under_way(self):
        """A job streaming and held on its second line."""
        if self.kind == "router":
            self.monkeypatch.setenv("APOTHECARY_SIMULATED_SPEED", "0.2")
            self.keep_a_file(DWELLS)
            self.arm()
            self.job = devices.start_print(PORT, self.file_id)
            for _ in range(200):
                if self.job.sent >= 2:
                    break
                time.sleep(0.02)
        else:
            gate = self.gate

            class Held(ScriptedTransport):
                def write(self, data):
                    if data.decode().strip() == "G1 X2":
                        gate.wait(5)
                    super().write(data)

            self.links.factory = Held
            self.links.close(PORT)
            self.keep_a_file("G1 X1\nG1 X2\nG1 X3\n")
            self.arm()
            self.job = devices.start_print(PORT, self.file_id)
            time.sleep(0.2)

    def unproved(self):
        grbl.proof_of(self.links.get(PORT)).assumed = False

    def the_card_prints(self):
        self.links.factory = lambda port, baud: ScriptedTransport(port, baud, replies=PRINTING)
        self.links.close(PORT)
        assert self.poll().sd_printing

    def the_board_goes_quiet(self):
        """Nothing answers a poll: the link is let go and the poll says offline."""

        class Quiet(ScriptedTransport):
            def write(self, data):
                self.sent.append(data.decode().strip())  # heard, and nothing said

        self.links.factory = Quiet
        self.links.close(PORT)
        assert devices.printer_status(PORT).state == "offline"

    def release(self):
        self.gate.set()
        if self.job is not None:
            self.job.cancel()
            self.job.thread.join(5)

    # -- the routes -----------------------------------------------------------
    def request(self, verb):
        line = LINES[self.kind]
        post = self.client.post
        if verb == "jog":
            return post(
                "/firmware/printers/jog", json={"port": PORT, "axis": "X", "mm": 1, "feed": 1000}
            )
        if verb in COMMAND_VERBS:
            return post("/firmware/printers/command", json={"port": PORT, "command": line[verb]})
        if verb == "query":
            return post("/firmware/printers/query", json={"port": PORT, "command": line["query"]})
        if verb == "print.start":
            return post("/firmware/printers/print", json={"port": PORT, "file_id": self.file_id})
        if verb.startswith("print."):
            return post(f"/firmware/printers/print/{verb[6:]}", json={"port": PORT})
        if verb == "level.probe":
            return post("/firmware/printers/level", json={"port": PORT, "probe": True})
        if verb == "level.read":
            return post("/firmware/printers/level", json={"port": PORT, "probe": False})
        if verb == "identify":
            return post("/firmware/devices/identify", json={"port": PORT})
        return post(f"/firmware/printers/{verb}", json={"port": PORT})


@pytest.fixture
def rig(request, fake_arduino_cli, fresh_task_runner, monkeypatch):
    ScriptedTransport.instances.clear()
    if request.param == "router":
        monkeypatch.setenv("APOTHECARY_SIMULATED_SPEED", "0")
        links = gcode.PrinterLinks(factory=grbl.SimulatedRouter)
    else:
        links = gcode.PrinterLinks(factory=ScriptedTransport)
    monkeypatch.setattr(gcode, "_LINKS", links)
    made = Rig(request.param, links, TestClient(app), monkeypatch)
    yield made
    made.release()
    links.stop_all()


KINDS = ["printer", "router"]


def refused(answer):
    return answer.status_code >= 400


# Each condition: how the rig is put in it, and for which kinds it can be.
def idle_armed(rig):
    rig.poll()
    rig.keep_a_file()
    rig.arm()


def disarmed(rig):
    rig.poll()
    rig.keep_a_file()


def task_holds(rig):
    idle_armed(rig)
    rig.task_on_the_port()


def under_way(rig):
    rig.poll()
    rig.a_print_under_way()


def not_proved(rig):
    idle_armed(rig)
    rig.unproved()


def card_prints(rig):
    rig.keep_a_file()
    rig.the_card_prints()
    rig.arm()


def quiet(rig):
    rig.poll()
    rig.keep_a_file()
    rig.arm()
    rig.the_board_goes_quiet()


CONDITIONS = {
    "armed-and-idle": (idle_armed, {"printer", "router"}, ALL_VERBS),
    "latch-down": (disarmed, {"printer", "router"}, ALL_VERBS),
    "a-task-holds-the-port": (task_holds, {"printer", "router"}, ALL_VERBS),
    "a-print-is-under-way": (under_way, {"printer", "router"}, ALL_VERBS),
    "a-home-not-proved": (not_proved, {"router"}, ["home", "home.X", "print.start", "jog"]),
    "the-card-prints": (card_prints, {"printer"}, ["print.start", "jog", "off"]),
    "the-board-is-quiet": (
        quiet,
        {"printer"},
        ["jog", "home", "off", "heat", "control", "print.start", "level.probe", "level.read"],
    ),
}
CASES = [
    pytest.param(kind, name, verb, id=f"{kind}:{name}:{verb}")
    for name, (_, kinds, verbs) in CONDITIONS.items()
    for kind in ("printer", "router")
    if kind in kinds
    for verb in verbs
    if not (verb == "home.X" and kind == "printer")  # only a router homes one axis
]


@pytest.mark.parametrize("rig,condition,verb", CASES, indirect=["rig"])
def test_can_now_agrees_with_the_route(rig, condition, verb):
    CONDITIONS[condition][0](rig)
    verdict = can.can_now(PORT)[verb]
    answer = rig.request(verb)
    said = f"{rig.kind}/{condition}/{verb}: can said {verdict}, route said {answer.status_code} {answer.text[:200]}"
    if verdict["ok"]:
        assert not refused(answer), said
        assert verdict["why"] is None and verdict["kind"] is None, said
    else:
        assert refused(answer), said
        assert verdict["why"] and verdict["kind"], said


@pytest.mark.parametrize("rig", KINDS, indirect=True)
def test_a_stop_is_always_ok(rig):
    rig.poll()
    rig.a_print_under_way()
    assert can.can_now(PORT)["estop"] == {"ok": True, "why": None, "kind": None}


@pytest.mark.parametrize("rig", KINDS, indirect=True)
def test_the_kinds_say_what_stands_in_the_way(rig):
    rig.poll()
    down = can.can_now(PORT)
    assert down["jog"]["kind"] == "armed" and "arm it first" in down["jog"]["why"]
    assert down["print.pause"]["kind"] == "idle"
    assert down["off"]["ok"] and down["release"]["ok"]
    rig.arm()
    up = can.can_now(PORT)
    assert up["jog"]["ok"] and up["print.start"]["ok"]
    rig.task_on_the_port()
    held = can.can_now(PORT)
    assert held["jog"]["kind"] == "held" and "holds" in held["jog"]["why"]
    assert held["off"]["kind"] == "held"
    assert held["estop"]["ok"]


def test_a_router_in_alarm_cannot_jog_and_can_unlock(router_alarm):
    asked = can.can_now(PORT)
    assert asked["jog"]["kind"] == "alarm" and "Unlock" in asked["jog"]["why"]
    assert asked["unlock"]["ok"] and asked["home"]["ok"]


@pytest.fixture
def router_alarm(fake_arduino_cli, fresh_task_runner, monkeypatch):
    """The last poll of a router said Alarm: nothing moves, a jog included. The
    controller refuses that jog, not this server, so it is not compared with a route."""
    monkeypatch.setenv("APOTHECARY_SIMULATED_SPEED", "0")
    links = gcode.PrinterLinks(factory=grbl.SimulatedRouter)
    monkeypatch.setattr(gcode, "_LINKS", links)
    status = devices.printer_status(PORT)
    links.control.arm(PORT)
    devices._LAST_STATUS[PORT] = status.model_copy(update={"machine_state": "Alarm", "alarm": 1})
    yield
    links.stop_all()


@pytest.mark.parametrize("rig", KINDS, indirect=True)
def test_a_file_the_machine_cannot_take_is_not_startable(rig):
    idle_armed(rig)
    other = "printer" if rig.kind == "router" else "router"
    kept = devices.save_print_file("other.gcode", SMALL_PRINT.encode(), machine=other)
    verdict = can.can_start(PORT, kept.id)
    assert verdict["ok"] is False and verdict["kind"] == "file"
    answer = rig.client.post("/firmware/printers/print", json={"port": PORT, "file_id": kept.id})
    assert refused(answer)
    assert can.can_start(PORT, rig.file_id)["ok"] is True
    gone = can.can_start(PORT, "nope")
    assert gone["ok"] is False and "no such print file" in gone["why"]


@pytest.mark.parametrize("rig", KINDS, indirect=True)
def test_a_flash_to_a_machines_controller_is_refused_and_a_running_task_too(rig, monkeypatch):
    rig.poll()
    flash = can.can_now(PORT)["flash"]
    assert flash["ok"] is False and flash["kind"] == "kind"
    assert "controller" in flash["why"]
    with pytest.raises(ValueError):
        devices.not_a_machines_controller(PORT)
    devices.not_a_machines_controller(PORT, replace=True)  # asked for by name: allowed

    class Busy:
        id, title, port = "t9", "compile", None

    monkeypatch.setattr(tasks, "get_task_runner", lambda: SimpleNamespace(active=Busy))
    assert can.can_now(PORT)["flash"]["kind"] == "busy"


@pytest.mark.parametrize("rig", KINDS, indirect=True)
def test_the_status_and_the_info_carry_the_answer_and_a_route_answers_for_a_file(rig):
    idle_armed(rig)
    asked = can.can_now(PORT)
    status = rig.client.get("/firmware/printers/status", params={"port": PORT}).json()
    info = rig.client.get("/firmware/printers/info", params={"port": PORT}).json()
    assert status["can"] == asked == info["can"]
    ok = rig.client.get(
        "/firmware/printers/can-start", params={"port": PORT, "file_id": rig.file_id}
    ).json()
    assert ok == {"ok": True, "why": None, "kind": None}
    rig.links.control.disarm(PORT)
    down = rig.client.get(
        "/firmware/printers/can-start", params={"port": PORT, "file_id": rig.file_id}
    ).json()
    assert down["ok"] is False and down["kind"] == "armed"
    assert (
        rig.client.get(
            "/firmware/printers/can-start", params={"port": PORT, "file_id": "nope"}
        ).json()["kind"]
        == "file"
    )
    # While a task holds the port the poll is refused (409) and the info still answers.
    rig.task_on_the_port()
    assert rig.client.get("/firmware/printers/status", params={"port": PORT}).status_code == 409
    held = rig.client.get("/firmware/printers/info", params={"port": PORT}).json()["can"]
    assert held["jog"]["kind"] == "held"
