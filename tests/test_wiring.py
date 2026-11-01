"""The bench as a carlos.patch: apothecary/wiring/ and its routes."""

from __future__ import annotations

import json
import re

import pytest
from fastapi.testclient import TestClient

from apothecary.api import app
from apothecary.example_hierarchy import create_example_site
from apothecary.firmware.models import (
    DeviceInfo,
    ExpectedFirmware,
    FlashRecord,
    Heater,
    NodeBinding,
    PrinterStatus,
)
from apothecary.hierarchy import Assembly
from apothecary.projects.parts.skeleton import ROOT
from apothecary.wiring import catalogue
from apothecary.wiring.patch import HOST_MODULE, wiring_for_site

MAINBOARD = "printer_1.frame_system.mainboard"

# What carlos.patch version 3 has at its top level, and refuses anything beside.
TOP_LEVEL = {"format", "version", "name", "modules", "connections", "groups", "display", "midi"}


def _carlos_rules_hold(patch: dict) -> None:
    """The document rules carlos's validator checks, and the jack rules its browser does."""
    assert set(patch) == TOP_LEVEL
    assert patch["format"] == "carlos.patch" and patch["version"] == 3
    types = {m["id"]: m["type"] for m in patch["modules"]}
    assert len(types) == len(patch["modules"]), "module ids are unique"
    for lead in patch["connections"]:
        source, target = lead["source"], lead["target"]
        assert source["module"] != target["module"], "no device patched into itself"
        for end, kind in ((source, "output"), (target, "input")):
            jacks = {j["name"]: j for j in catalogue.entries()[types[end["module"]]]["jacks"]}
            assert jacks[end["jack"]]["type"] == kind


def _pinned(device: DeviceInfo, **row) -> NodeBinding:
    return NodeBinding(
        path=MAINBOARD,
        name="mainboard",
        part_ref="creality_v422",
        binding_source="manual",
        identity=device.identity,
        device=device,
        **row,
    )


def test_a_printer_s_state_says_what_its_last_poll_found():
    """Printer monitoring in carlos: while the Machine polls the printer, each poll's
    state, progress and heaters are lines of the mainboard's state."""
    from datetime import datetime, timezone

    board = DeviceInfo(port="/dev/ttyUSB0", serial_number="A106ZTEU")
    polled = datetime(2026, 10, 30, 20, 41, 3, tzinfo=timezone.utc)
    printing = PrinterStatus(
        port="/dev/ttyUSB0",
        polled_at=polled,
        state="printing",
        hotends=[Heater(actual=204.6, target=205)],
        bed=Heater(actual=59.9, target=60),
        sd_printing=True,
        sd_progress=0.43,
        print_time_s=734,
    )
    wiring = wiring_for_site(
        "garage", create_example_site(), [_pinned(board, printer_status=printing)]
    )
    state = wiring.states.modules[MAINBOARD]
    assert state.level == "ok"
    assert "printer: printing, 43% of its job, 12 min in, as polled at 20:41:03" in state.says
    assert "heaters: hotend 205/205 °C, bed 60/60 °C" in state.says

    resting = printing.model_copy(update={"state": "offline", "sd_printing": False, "bed": None})
    wiring = wiring_for_site(
        "garage", create_example_site(), [_pinned(board, printer_status=resting)]
    )
    state = wiring.states.modules[MAINBOARD]
    assert state.level == "warn"
    assert "printer: offline, as polled at 20:41:03" in state.says
    assert "heaters: hotend 205/205 °C" in state.says

    # No poll, no lines: the Machine is closed, or the board is no printer.
    wiring = wiring_for_site("garage", create_example_site(), [_pinned(board)])
    assert not any(line.startswith("printer:") for line in wiring.states.modules[MAINBOARD].says)


def test_every_board_the_garage_draws_is_a_module_plugged_in_or_not():
    wiring = wiring_for_site("garage", create_example_site(), [])
    types = {m["id"]: m["type"] for m in wiring.patch["modules"]}
    assert types == {
        MAINBOARD: "creality.v422",
        "esp32_blink": "espressif.esp32-devkitc",
        "footpedal": "quaternionmedia.footpedal",
        "arduino_uno": "arduino.uno-r3",
    }
    # Nothing answers on a port, so nothing is leaded and the computer is not drawn.
    assert wiring.patch["connections"] == [] and HOST_MODULE not in types
    assert not any(e.connected for e in wiring.evidence)
    _carlos_rules_hold(wiring.patch)


def test_a_connected_board_is_leaded_to_the_computer_and_its_evidence_says_how():
    board = DeviceInfo(port="/dev/ttyUSB0", serial_number="A106ZTEU")
    wiring = wiring_for_site("garage", create_example_site(), [_pinned(board)])
    assert wiring.patch["connections"] == [
        {
            "source": {"module": MAINBOARD, "jack": "usb"},
            "target": {"module": HOST_MODULE, "jack": "usb"},
        }
    ]
    assert {"id": HOST_MODULE, "type": "apothecary.host", "view": "front", "parameters": {}} in (
        wiring.patch["modules"]
    )
    known = next(e for e in wiring.evidence if e.module == MAINBOARD)
    assert known.connected and known.port == "/dev/ttyUSB0"
    assert known.identity == "A106ZTEU" and known.binding_source == "manual"
    _carlos_rules_hold(wiring.patch)


def test_what_was_flashed_and_whether_it_has_moved_on_ride_in_the_evidence():
    from datetime import datetime, timezone

    board = DeviceInfo(port="/dev/ttyUSB1", mac="24:6f:28:aa:bb:cc")
    record = FlashRecord(
        identity=board.identity,
        port=board.port,
        sketch="esp32_blink",
        flashed_at=datetime(2026, 10, 29, tzinfo=timezone.utc),
    )
    row = NodeBinding(
        path="esp32_blink",
        name="esp32_blink",
        part_ref="esp32_devkitc",
        sketch_ref="esp32_blink",
        sketch="esp32_blink",
        binding_source="sketch",
        identity=board.identity,
        device=board,
        expected=ExpectedFirmware(record=record, source_changed=True),
    )
    wiring = wiring_for_site("garage", create_example_site(), [row])
    known = next(e for e in wiring.evidence if e.module == "esp32_blink")
    assert known.flashed == "esp32_blink" and known.source_changed and not known.build_changed
    assert known.identity == "24:6f:28:aa:bb:cc"


def test_a_board_with_no_catalogued_device_is_unplaced_and_not_in_the_document():
    site = Assembly(
        name="bench",
        children=[
            Assembly(name="mystery", sketch_ref="esp32_blink"),
            Assembly(name="pi", part_ref="raspberry_pi_4"),
        ],
    )
    board = DeviceInfo(port="/dev/ttyUSB2")
    rows = [
        NodeBinding(path="mystery", name="mystery", sketch_ref="esp32_blink", device=board),
        NodeBinding(path="pi", name="pi", part_ref="raspberry_pi_4", binding_source="manual"),
    ]
    wiring = wiring_for_site("bench", site, rows)
    assert wiring.patch["modules"] == [] and wiring.evidence == []
    assert [(u.path, u.port, u.why) for u in wiring.unplaced] == [
        ("mystery", "/dev/ttyUSB2", "no part says which device this is"),
        ("pi", None, "part 'raspberry_pi_4' draws no catalogued device"),
    ]


def test_each_entry_is_named_for_its_id_and_has_one_usb_socket():
    for path in sorted(catalogue.ROOT.glob("*.json")):
        entry = json.loads(path.read_text(encoding="utf-8"))
        assert path.stem == entry["id"], "carlos names a device's file for its id"
        assert re.fullmatch(r"[a-z0-9-]+\.[a-z0-9-]+", entry["id"])
        names = [j["name"] for j in entry["jacks"]]
        assert len(names) == len(set(names))
        # Every device on the bench has its one USB socket; a supply has none.
        expected = None if entry["id"] == catalogue.SUPPLY else "usb"
        assert catalogue.usb_jack(entry["id"]) == expected
    named = set(catalogue.PARTS.values()) | set(catalogue.BY_FQBN.values())
    assert named | {catalogue.HOST, catalogue.UNNAMED, catalogue.SUPPLY} == set(catalogue.entries())


@pytest.mark.parametrize(
    "part", sorted(p for p in catalogue.PARTS if (ROOT / "parts" / "boards" / p).is_dir())
)
def test_a_boards_box_is_its_drawings_bounds(part):
    bounds = json.loads((ROOT / "parts" / "boards" / part / "part.json").read_text())["bounds"]
    width, height, depth = (
        round(hi - lo, 2) for lo, hi in zip(bounds["min"], bounds["max"], strict=True)
    )
    box = catalogue.entries()[catalogue.PARTS[part]]["layout"]["box"]
    assert (box["width"], box["height"], box["depth"]) == (width, height, depth)


@pytest.fixture
def garage():
    import apothecary.api as api_module

    yield api_module._site_store.get("garage")
    api_module._site_store.reset("garage")


def test_the_routes_answer_the_pinned_mainboard_as_a_lead_and_the_document_alone(
    fake_arduino_cli, garage
):
    client = TestClient(app)
    pinned = client.put(
        f"/sites/garage/nodes/{MAINBOARD}/device", json={"identity": "/dev/ttyFAKE1"}
    )
    assert pinned.status_code == 200
    body = client.get("/sites/garage/wiring").json()
    assert set(body) == {"site", "patch", "evidence", "states", "unplaced"}
    assert {"module": MAINBOARD, "jack": "usb"} in [
        c["source"] for c in body["patch"]["connections"]
    ]
    known = next(e for e in body["evidence"] if e["module"] == MAINBOARD)
    assert known["connected"] and known["port"] == "/dev/ttyFAKE1"
    alone = client.get("/sites/garage/wiring/patch").json()
    assert alone == body["patch"]
    _carlos_rules_hold(alone)
    assert client.get("/sites/nowhere/wiring").status_code == 404


# --- the states, the declared leads and the boards no node names ----------------


def test_an_expected_board_not_answering_is_absent_with_a_declared_lead():
    row = NodeBinding(
        path="esp32_blink",
        name="esp32_blink",
        part_ref="esp32_devkitc",
        sketch_ref="esp32_blink",
        sketch="esp32_blink",
        note="never flashed from apothecary",
    )
    wiring = wiring_for_site("garage", create_example_site(), [row])
    state = wiring.states.modules["esp32_blink"]
    assert state.level == "fault"
    assert state.says == [
        "absent: expected, and not answering",
        "firmware: esp32_blink never flashed from here",
        "known by: the site's drawing",
    ]
    (lead,) = wiring.states.connections
    assert lead.source == {"module": "esp32_blink", "jack": "usb"}
    assert lead.level == "fault" and lead.says == ["declared: the board is not answering"]
    # A board placed and naming nothing is on the bench, and has no lead.
    assert wiring.states.modules["arduino_uno"].says[0] == "on the bench: not expected plugged in"
    assert wiring.states.modules["arduino_uno"].level == "none"
    _carlos_rules_hold(wiring.patch)


def test_a_pinned_board_says_it_is_present_and_known_by_its_serial_number():
    board = DeviceInfo(port="/dev/ttyUSB0", serial_number="A106ZTEU")
    wiring = wiring_for_site("garage", create_example_site(), [_pinned(board)])
    state = wiring.states.modules[MAINBOARD]
    assert state.level == "ok"
    assert state.says == [
        "present: answering on /dev/ttyUSB0",
        "known by: pinned, by its USB serial number",
    ]
    assert [c.says for c in wiring.states.connections] == [["seen: answering on /dev/ttyUSB0"]]
    assert wiring.states.modules[HOST_MODULE].level == "ok"


def test_a_board_flashed_from_an_older_source_is_a_warning():
    from datetime import datetime, timezone

    board = DeviceInfo(port="/dev/ttyUSB1", mac="24:6f:28:aa:bb:cc")
    record = FlashRecord(
        identity=board.identity,
        port=board.port,
        sketch="esp32_blink",
        flashed_at=datetime(2026, 10, 29, tzinfo=timezone.utc),
    )
    row = NodeBinding(
        path="esp32_blink",
        name="esp32_blink",
        part_ref="esp32_devkitc",
        sketch="esp32_blink",
        binding_source="sketch",
        identity=board.identity,
        device=board,
        expected=ExpectedFirmware(record=record, source_changed=True),
    )
    state = wiring_for_site("garage", create_example_site(), [row]).states.modules["esp32_blink"]
    assert state.level == "warn"
    assert "firmware: esp32_blink, flashed from an older source" in state.says
    assert "known by: the board esp32_blink was last flashed to" in state.says


def test_a_board_on_a_port_no_node_names_is_unexpected_and_typed_by_its_match():
    uno = DeviceInfo(port="/dev/ttyACM0", board_name="Arduino Uno", fqbn="arduino:avr:uno")
    other = DeviceInfo(port="/dev/ttyUSB3", serial_number="0001")
    pinned = DeviceInfo(port="/dev/ttyUSB0", serial_number="A106ZTEU")
    wiring = wiring_for_site(
        "garage", create_example_site(), [_pinned(pinned)], [uno, other, pinned]
    )
    types = {m["id"]: m["type"] for m in wiring.patch["modules"]}
    assert types["usb:/dev/ttyACM0"] == "arduino.uno-r3"
    assert types["usb:0001"] == "apothecary.usb-device"
    assert not any(t.startswith("usb:") and t.endswith("A106ZTEU") for t in types)
    state = wiring.states.modules["usb:/dev/ttyACM0"]
    assert state.level == "warn"
    assert state.says == [
        "unexpected: answering on /dev/ttyACM0, and no node names it",
        "known by: its port, which arduino-cli matches to Arduino Uno",
    ]
    assert len(wiring.patch["connections"]) == 3
    _carlos_rules_hold(wiring.patch)


# --- sending it to carlos --------------------------------------------------------


def test_the_hold_carries_the_rig_every_entry_it_names_and_the_states():
    from apothecary.wiring.carlos import hold_body

    board = DeviceInfo(port="/dev/ttyUSB0", serial_number="A106ZTEU")
    wiring = wiring_for_site("garage", create_example_site(), [_pinned(board)])
    body = hold_body(wiring)
    assert body["cue"]["number"] == "garage" and body["cue"]["name"] == "apothecary: garage"
    hold = body["action"]["hold"]
    assert hold["patch"] == wiring.patch
    assert {d["id"] for d in hold["devices"]} == {m["type"] for m in wiring.patch["modules"]}
    assert hold["states"]["modules"][MAINBOARD]["level"] == "ok"


@pytest.fixture
def a_carlos():
    """A stand-in for carlos on loopback: what it was sent, and what it answers."""
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    heard = []
    answer = {"status": 200, "body": {"ok": True}}

    class Cue(BaseHTTPRequestHandler):
        def do_POST(self):
            length = int(self.headers["Content-Length"])
            heard.append((self.path, json.loads(self.rfile.read(length))))
            self.send_response(answer["status"])
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(answer["body"]).encode())

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Cue)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}", heard, answer
    server.shutdown()
    server.server_close()


def test_the_follower_sends_once_for_an_unchanged_bench_and_again_when_it_changes(a_carlos):
    from apothecary.wiring.carlos import Follower

    url, heard, answer = a_carlos
    rows = []
    follower = Follower(url, lambda: wiring_for_site("garage", create_example_site(), rows))
    assert follower.look() and not follower.look()
    rows.append(_pinned(DeviceInfo(port="/dev/ttyUSB0", serial_number="A106ZTEU")))
    assert follower.look()
    assert [path for path, _ in heard] == ["/family/cue", "/family/cue"]
    assert heard[-1][1]["action"]["hold"]["states"]["modules"][MAINBOARD]["level"] == "ok"
    # A refusal is not taken as sent: the next look sends again.
    answer.update(status=422, body={"ok": False, "error": "not a rig"})
    rows.clear()
    assert not follower.look() and follower.last_error.endswith("(422): not a rig")
    answer.update(status=200, body={"ok": True})
    assert follower.look()


def test_a_look_that_fails_the_same_way_is_logged_once(caplog):
    """APOTHECARY_CARLOS_SITE naming no site fails every look with the route's 404:
    one traceback for it, and one more when a look fails another way."""
    import threading

    from fastapi import HTTPException

    from apothecary.wiring.carlos import Follower

    looks = []
    six = threading.Event()

    def wiring():
        looks.append(1)
        if len(looks) >= 6:
            six.set()
        if len(looks) <= 3:
            raise HTTPException(status_code=404, detail="Site 'nowhere' not found")
        raise OSError("the state folder is not there")

    follower = Follower("http://127.0.0.1:1", wiring, every=0.01)
    with caplog.at_level("ERROR", logger="apothecary.wiring.carlos"):
        follower.start()
        assert six.wait(5)
        follower.stop()
    failed = [r for r in caplog.records if r.getMessage() == "wiring: a look at the bench failed"]
    assert [type(r.exc_info[1]).__name__ for r in failed] == ["HTTPException", "OSError"]


def test_carlos_is_reached_on_this_machine_only():
    from apothecary.wiring.carlos import loopback_url

    assert loopback_url("http://127.0.0.1:4186/") == "http://127.0.0.1:4186"
    for elsewhere in ("http://192.168.1.4:4186", "https://127.0.0.1:4186", "ftp://localhost"):
        with pytest.raises(ValueError):
            loopback_url(elsewhere)


def test_sending_asks_for_a_carlos_and_says_what_it_answered(
    fake_arduino_cli, garage, a_carlos, monkeypatch
):
    client = TestClient(app)
    monkeypatch.delenv("APOTHECARY_CARLOS", raising=False)
    assert client.post("/sites/garage/wiring/send").status_code == 409
    url, heard, _ = a_carlos
    monkeypatch.setenv("APOTHECARY_CARLOS", url)
    sent = client.post("/sites/garage/wiring/send")
    assert sent.status_code == 200 and sent.json() == {"sent": url, "answer": {"ok": True}}
    hold = heard[-1][1]["action"]["hold"]
    # The scripted bench's two ports no node names are in the rig, unexpected.
    assert {"usb:/dev/ttyFAKE0", "usb:FAKESERIAL1"} <= set(hold["states"]["modules"])
