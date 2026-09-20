"""G-code seam: parsers, the held-open link, identify/poll, routes and CLI.

The scripted transport replays what a Creality mainboard running Marlin
(TH3D UFW 2.94a) actually said over /dev/ttyUSB1 on 2026-09-19, so the
parsers are tested against real output, not an idealised one.
"""

import json
import os
import threading
import time

import pytest
from click.testing import CliRunner
from fastapi.testclient import TestClient

from apothecary.api import app
from apothecary.cli import cli
from apothecary.firmware import devices, gcode
from apothecary.firmware.toolchains import ToolchainError

BOOT = [
    "start",
    " External Reset",
    "Marlin TH3D UFW 2.94a",
    "echo: Last Updated: 2024-12-05 | Author: TH3D Studio",
    "echo: Compiled: Jan 17 2025",
    "echo: Free Memory: 1289  PlannerBufferBytes: 1200",
    "echo:V88 stored settings retrieved (702 bytes; crc 8322)",
]

REPLIES = {
    "M115": [
        "echo:SD card ok",
        "FIRMWARE_NAME:Marlin TH3D UFW 2.94a (Jan 17 2025 11:35:34) SOURCE_CODE_URL:TH3DStudio.com "
        "PROTOCOL_VERSION:1.0 MACHINE_TYPE:TH3D EZABL EXTRUDER_COUNT:1 "
        "UUID:cede2a2f-41a2-4748-9b12-c55c62f367ff",
        "ok",
    ],
    "M105": ["ok T:22.30 /0.00 B:23.59 /0.00 @:0 B@:0"],
    "M114": ["X:0.00 Y:0.00 Z:0.00 E:0.00 Count X:0 Y:0 Z:0", "ok"],
    "M119": [
        "Reporting endstop status",
        "x_min: open",
        "y_min: TRIGGERED",
        "z_min: open",
        "filament: TRIGGERED",
        "ok",
    ],
    "M27": ["Not SD printing", "ok"],
    "M31": ["echo:Print time: 0s", "ok"],
}

PRINTING = {
    **REPLIES,
    "M105": ["ok T:209.8 /210.00 B:60.02 /60.00 @:78 B@:12"],
    "M114": ["X:110.25 Y:98.40 Z:3.60 E:412.10 Count X:8820 Y:7872 Z:1440", "ok"],
    "M27": ["SD printing byte 152673/358856", "ok"],
    "M31": ["echo:Print time: 1h 2m 3s", "ok"],
}


class ScriptedTransport:
    """Answers each command from a table; prints the boot banner when reset is pulsed.

    ``boot_on_open`` mimics a previous holder having dropped DTR, so the open
    itself reboots the board.
    """

    instances = []

    def __init__(self, port, baud, replies=None, boot=BOOT, boot_on_open=False):
        self.port, self.baud = port, baud
        self.replies = replies or REPLIES
        self.boot = boot
        self.pending = "".join(ln + "\n" for ln in boot).encode() if boot_on_open else b""
        self.sent = []
        self.resets = 0
        self.closed = False
        ScriptedTransport.instances.append(self)

    def pulse_reset(self):
        self.resets += 1
        self.pending += "".join(ln + "\n" for ln in self.boot).encode()

    def write(self, data):
        cmd = data.decode().strip()
        self.sent.append(cmd)
        reply = self.replies.get(cmd)
        if reply is None:
            reply = [f'echo:Unknown command: "{cmd}"', "ok"]
        self.pending += "".join(ln + "\n" for ln in reply).encode()

    def read(self, timeout):
        if not self.pending:
            time.sleep(min(timeout, 0.01))
            return b""
        out, self.pending = self.pending[:64], self.pending[64:]
        return out

    def close(self):
        self.closed = True


@pytest.fixture
def scripted_links(monkeypatch):
    """Route the seam's link registry through ScriptedTransport; yields the registry."""
    ScriptedTransport.instances.clear()
    links = gcode.PrinterLinks(factory=ScriptedTransport)
    monkeypatch.setattr(gcode, "_LINKS", links)
    yield links
    links.stop_all()


# --- parsers ---------------------------------------------------------------------


def test_parse_m115_fields_and_caps():
    fields = gcode.parse_m115(REPLIES["M115"] + ["Cap:AUTOREPORT_TEMP:1", "Cap:EEPROM:0"])
    assert fields["firmware_name"] == "Marlin TH3D UFW 2.94a (Jan 17 2025 11:35:34)"
    assert fields["machine_type"] == "TH3D EZABL"
    assert fields["source_code_url"] == "TH3DStudio.com"
    assert fields["uuid"] == "cede2a2f-41a2-4748-9b12-c55c62f367ff"
    assert fields["capabilities"] == {"AUTOREPORT_TEMP": True, "EEPROM": False}
    assert gcode.parse_m115(["ok"]) == {}


def test_parse_m105_single_and_multi_hotend():
    out = gcode.parse_m105("ok T:22.30 /0.00 B:23.59 /0.00 @:0 B@:0")
    assert len(out["hotends"]) == 1 and out["hotends"][0].actual == 22.3
    assert out["bed"].actual == 23.59 and out["bed"].power == 0
    multi = gcode.parse_m105(
        "ok T:210.0 /210.0 T0:210.0 /210.0 T1:25.0 /0.0 B:60.0 /60.0 @:64 @1:0 B@:127"
    )
    assert [h.target for h in multi["hotends"]] == [210.0, 0.0]
    assert multi["hotends"][1].power == 0 and multi["bed"].power == 127
    assert gcode.is_temperature_line(" T:22.46 /0.00 B:23.75 /0.00 @:0 B@:0")  # M155 autoreport
    assert not gcode.is_temperature_line("ok")


def test_parse_position_endstops_sd_and_time():
    assert gcode.parse_m114(PRINTING["M114"]) == {"x": 110.25, "y": 98.4, "z": 3.6, "e": 412.1}
    assert gcode.parse_m114(["ok"]) is None
    stops = gcode.parse_m119(REPLIES["M119"])
    assert stops == {
        "x_min": "open",
        "y_min": "TRIGGERED",
        "z_min": "open",
        "filament": "TRIGGERED",
    }
    assert gcode.parse_m27(REPLIES["M27"]) == {"sd_printing": False, "sd_progress": None}
    sd = gcode.parse_m27(PRINTING["M27"])
    assert sd["sd_printing"] and abs(sd["sd_progress"] - 152673 / 358856) < 1e-9
    assert gcode.parse_m31(PRINTING["M31"]) == 3723 and gcode.parse_m31(REPLIES["M31"]) == 0
    assert gcode.parse_duration("2d 1h") == 2 * 86400 + 3600


# --- link -------------------------------------------------------------------------


def test_link_settles_resets_on_request_and_answers_commands():
    t = ScriptedTransport("/dev/ttyFAKE9", 115200)
    link = gcode.GcodeLink("/dev/ttyFAKE9", 115200, t)
    assert link.settle(first=0.2) == [] and t.resets == 0  # a quiet board: no reboot, no wait
    assert link.reset() == BOOT and t.resets == 1
    assert link.command("M115")[-1] == "ok"
    assert t.sent == ["M115"]
    stray = ScriptedTransport("/dev/ttyFAKE9", 115200, boot_on_open=True)
    assert gcode.GcodeLink("/dev/ttyFAKE9", 115200, stray).settle(first=0.5) == BOOT
    with pytest.raises(ValueError):
        link.command("M105\nM112")  # one command per exchange, never a smuggled second one


def test_link_waits_through_busy_and_raises_on_error_or_silence():
    t = ScriptedTransport("/dev/ttyFAKE9", 115200)
    t.replies = {
        "G28": ["echo:busy: processing", "echo:busy: processing", "ok"],
        "M999": ["Error:Printer halted. kill() called!"],
    }
    link = gcode.GcodeLink("/dev/ttyFAKE9", 115200, t)
    assert link.command("G28") == ["echo:busy: processing", "echo:busy: processing", "ok"]
    with pytest.raises(ToolchainError, match="Printer halted"):
        link.command("M999")
    t.replies = {"M105": []}
    with pytest.raises(ToolchainError, match="no `ok`"):
        link.command("M105", timeout=0.3)


def test_links_registry_reuses_and_releases(scripted_links):
    a = scripted_links.open("/dev/ttyFAKE1", 115200)
    assert scripted_links.open("/dev/ttyFAKE1", 115200) is a  # no second reset
    b = scripted_links.open("/dev/ttyFAKE1", 250000)  # a different rate reopens
    assert b is not a and ScriptedTransport.instances[0].closed
    assert scripted_links.open_ports == ["/dev/ttyFAKE1"]
    assert scripted_links.close("/dev/ttyFAKE1") and not scripted_links.close("/dev/ttyFAKE1")
    scripted_links.open("/dev/ttyFAKE1", 115200)
    scripted_links.stop_all()
    assert scripted_links.open_ports == [] and all(t.closed for t in ScriptedTransport.instances)


# --- engines --------------------------------------------------------------------------


def test_engine_selection(monkeypatch):
    monkeypatch.delenv("APOTHECARY_SERIAL_ENGINE", raising=False)
    monkeypatch.setattr(gcode, "pyserial_available", lambda: True)
    assert gcode.serial_engine() == "pyserial"
    monkeypatch.setattr(gcode, "pyserial_available", lambda: False)
    assert gcode.serial_engine() == "termios"
    monkeypatch.setenv("APOTHECARY_SERIAL_ENGINE", "PySerial")
    assert gcode.serial_engine() == "pyserial"
    monkeypatch.setenv("APOTHECARY_SERIAL_ENGINE", "usbmuxd")
    with pytest.raises(ToolchainError, match="known engines"):
        gcode.serial_engine()
    assert set(gcode.ENGINES) == {"pyserial", "termios", "simulated"}


def test_simulated_engine_is_a_plausible_marlin(monkeypatch):
    monkeypatch.setenv("APOTHECARY_SIMULATED_PRINTER", "printing")
    link = gcode.GcodeLink("/dev/ttySIM", 115200, gcode.SimulatedPrinter("/dev/ttySIM", 115200))
    info = gcode.identify_printer(link, reset=True)
    assert info.firmware_name.startswith("Marlin Apothecary Simulator")
    assert info.boot_lines[0] == "start" and info.capabilities == {"AUTOREPORT_TEMP": True}
    st = gcode.poll_printer(link)
    assert st.state == "printing" and st.hotends[0].target == 210.0 and st.sd_progress is not None
    assert st.print_time_s is not None and st.filament_present is True
    monkeypatch.setenv("APOTHECARY_SIMULATED_PRINTER", "idle")
    st = gcode.poll_printer(gcode.GcodeLink("/dev/ttySIM", 115200, gcode.SimulatedPrinter("x", 1)))
    assert st.state == "idle" and st.bed.target == 0.0


def test_pyserial_engine_round_trip_on_loopback():
    pytest.importorskip("serial")
    t = gcode.PySerialTransport("loop://", 115200)
    t.write(b"M105\n")
    assert t.read(0.5) == b"M105\n" and t.read(0.1) == b""
    t.pulse_reset()  # a no-op on a loopback, but the code path runs
    t.close()
    with pytest.raises(ToolchainError, match="cannot open"):
        gcode.PySerialTransport("/dev/ttyDOES_NOT_EXIST", 115200)


def test_pyserial_engine_leaves_dtr_up_on_close():
    """A real tty (a pty here) is opened with HUPCL cleared, so closing it keeps DTR.

    Seen on the bench: with HUPCL set the kernel drops DTR on close and the
    Creality board reboots on the next program's open -- the very reset the
    seam promises not to cause.
    """
    pytest.importorskip("serial")
    termios = pytest.importorskip("termios")
    master, slave = os.openpty()
    try:
        attr = termios.tcgetattr(slave)
        attr[2] |= termios.HUPCL  # what a real USB serial port comes up with
        termios.tcsetattr(slave, termios.TCSANOW, attr)
        assert termios.tcgetattr(slave)[2] & termios.HUPCL
        t = gcode.PySerialTransport(os.ttyname(slave), 115200)
        assert not termios.tcgetattr(t._s.fd)[2] & termios.HUPCL
        t.close()
    finally:
        os.close(master)
        os.close(slave)
    assert gcode.keep_dtr_on_close(None) is False


def test_termios_engine_rejects_odd_rates_and_missing_ports():
    pytest.importorskip("termios")
    with pytest.raises(ToolchainError, match="standard termios table"):
        gcode.TermiosTransport("/dev/null", 250000)
    with pytest.raises(ToolchainError, match="cannot open"):
        gcode.TermiosTransport("/dev/ttyDOES_NOT_EXIST", 115200)
    with pytest.raises(ToolchainError, match="not a serial port"):
        gcode.TermiosTransport("/dev/null", 115200)


# --- identify / poll ----------------------------------------------------------------


def test_identify_caches_printer_and_poll_reuses_link(fake_arduino_cli, scripted_links):
    d = devices.identify_printer("/dev/ttyFAKE1", 115200)
    assert d.printer.firmware_name.startswith("Marlin TH3D UFW 2.94a")
    assert d.printer.machine_type == "TH3D EZABL"
    assert d.printer.boot_lines == [] and ScriptedTransport.instances[0].resets == 0
    with_banner = devices.identify_printer("/dev/ttyFAKE1", 115200, reset=True)
    assert with_banner.printer.boot_lines[0] == "start"
    assert ScriptedTransport.instances[0].resets == 1 and len(ScriptedTransport.instances) == 1
    # Cached like an esptool probe: the next device listing carries it, no port touched.
    again = next(x for x in devices.detected_devices() if x.port == "/dev/ttyFAKE1")
    assert again.printer.uuid == "cede2a2f-41a2-4748-9b12-c55c62f367ff"

    st = devices.printer_status("/dev/ttyFAKE1")
    assert st.state == "idle" and not st.heating and st.filament_present is True
    assert st.endstops == {"x_min": "open", "y_min": "TRIGGERED", "z_min": "open"}
    assert st.position == {"x": 0.0, "y": 0.0, "z": 0.0, "e": 0.0}
    assert len(ScriptedTransport.instances) == 1  # one open for every call
    assert ScriptedTransport.instances[0].sent == ["M115", "M115", "M105", "M114", "M27", "M119"]

    # A printer mainboard is never handed to esptool.
    assert devices.probe_device("/dev/ttyFAKE1").printer is not None
    assert ScriptedTransport.instances[0].sent[-1] == "M119"


def test_poll_reports_a_running_sd_print(fake_arduino_cli, scripted_links):
    scripted_links.factory = lambda port, baud: ScriptedTransport(port, baud, PRINTING)
    st = devices.printer_status("/dev/ttyFAKE1")  # never identified: identifies first
    assert st.state == "printing" and st.sd_printing and st.print_time_s == 3723
    assert abs(st.sd_progress - 152673 / 358856) < 1e-9
    assert st.hotends[0].target == 210.0 and st.bed.power == 12 and not st.heating


def test_identify_refuses_non_gcode_board_and_releases(fake_arduino_cli, scripted_links):
    scripted_links.factory = lambda port, baud: ScriptedTransport(
        port, baud, {"M115": ["blink 1", "blink 2"]}, boot=["apothecary fake_blink: hello"]
    )  # an ESP32 sketch, not a printer
    with pytest.raises(ToolchainError, match="no `ok`"):
        devices.identify_printer("/dev/ttyFAKE0", 115200)
    assert scripted_links.open_ports == []
    with pytest.raises(ToolchainError, match="no board detected"):
        devices.identify_printer("/dev/ttyNOPE", 115200)


def test_poll_failure_goes_offline_and_drops_link(fake_arduino_cli, scripted_links):
    devices.identify_printer("/dev/ttyFAKE1", 115200)
    ScriptedTransport.instances[0].replies = {"M105": []}
    st = devices.printer_status("/dev/ttyFAKE1")
    assert st.state == "offline" and "no `ok`" in st.raw[0]
    assert scripted_links.open_ports == []


# --- routes ---------------------------------------------------------------------------


def test_identify_and_status_routes(fake_arduino_cli, fresh_task_runner, scripted_links):
    c = TestClient(app)
    assert c.post("/firmware/devices/identify", json={"port": "ttyUSB1"}).status_code == 422
    r = c.post("/firmware/devices/identify", json={"port": "/dev/ttyFAKE1", "baud": 115200})
    assert r.status_code == 200
    assert r.json()["device"]["printer"]["machine_type"] == "TH3D EZABL"
    assert r.json()["device"]["printer"]["boot_lines"] == []
    r = c.post("/firmware/devices/identify", json={"port": "/dev/ttyFAKE1", "reset": True})
    assert r.json()["device"]["printer"]["boot_lines"][0] == "start"
    assert c.get("/firmware/devices").json()["printers"] == ["/dev/ttyFAKE1"]

    r = c.get("/firmware/printers/status", params={"port": "/dev/ttyFAKE1"})
    assert r.status_code == 200
    body = r.json()
    assert body["state"] == "idle" and body["heating"] is False and body["bed"]["actual"] == 23.59
    assert c.get("/firmware/printers/status", params={"port": "nope"}).status_code == 422

    r = c.post("/firmware/printers/release", json={"port": "/dev/ttyFAKE1"})
    assert r.json() == {"port": "/dev/ttyFAKE1", "released": True}
    assert c.get("/firmware/devices").json()["printers"] == []
    assert c.post("/firmware/devices/identify", json={"port": "/dev/ttyNOPE"}).status_code == 503


def test_upload_releases_only_its_own_printer_link(
    fake_arduino_cli, fresh_task_runner, scripted_links
):
    c = TestClient(app)
    for port in ("/dev/ttyFAKE0", "/dev/ttyFAKE1"):
        c.post("/firmware/devices/identify", json={"port": port})
    assert sorted(scripted_links.open_ports) == ["/dev/ttyFAKE0", "/dev/ttyFAKE1"]
    r = c.post(
        "/firmware/sketches/footpedal/upload",
        json={"fqbn": "arduino:avr:uno", "port": "/dev/ttyFAKE0"},
    )
    assert r.status_code == 202
    assert scripted_links.open_ports == ["/dev/ttyFAKE1"]  # the other printer keeps running
    deadline = time.time() + 5
    while (
        c.get(f"/firmware/tasks/{r.json()['id']}").json()["status"] == "running"
        and time.time() < deadline
    ):
        time.sleep(0.02)
    # And while a task holds the toolchain, polls are refused rather than racing it.
    fresh_task_runner.run("x", "hold", [["/bin/sleep", "2"]])
    assert c.get("/firmware/printers/status", params={"port": "/dev/ttyFAKE1"}).status_code == 409
    assert c.post("/firmware/devices/identify", json={"port": "/dev/ttyFAKE1"}).status_code == 409
    fresh_task_runner.cancel(fresh_task_runner.active.id)


# --- CLI ----------------------------------------------------------------------------


def test_cli_printer_command(fake_arduino_cli, scripted_links):
    r = CliRunner().invoke(cli, ["firmware", "printer", "/dev/ttyFAKE1"])
    assert r.exit_code == 0, r.output
    assert "Marlin TH3D UFW 2.94a" in r.output and "TH3D EZABL" in r.output
    assert "state: idle" in r.output and "y_min=TRIGGERED" in r.output
    assert "filament: present" in r.output
    assert scripted_links.open_ports == []  # one-shot: released on exit

    r = CliRunner().invoke(cli, ["firmware", "printer", "/dev/ttyFAKE1", "--reset"])
    assert "boot: start |  External Reset" in r.output

    r = CliRunner().invoke(cli, ["firmware", "printer", "/dev/ttyFAKE1", "--json-out"])
    data = json.loads(r.output)
    assert data["device"]["printer"]["extruder_count"] == 1 and data["status"]["heating"] is False

    r = CliRunner().invoke(cli, ["firmware", "devices"])
    assert "printer: Marlin TH3D UFW 2.94a" in r.output
    assert CliRunner().invoke(cli, ["firmware", "printer", "COM"]).exit_code != 0


# --- status sync: a poll drives the bound scene node ---------------------------------


@pytest.fixture
def garage(monkeypatch):
    """A fresh garage site in the API's store, so status edits do not leak between tests."""
    from apothecary import api as api_module

    api_module._site_store.reset("garage")
    yield api_module._site_store.get("garage")
    api_module._site_store.reset("garage")


def test_poll_syncs_bound_printer_node(fake_arduino_cli, fresh_task_runner, scripted_links, garage):
    c = TestClient(app)
    assert (
        c.put(
            "/sites/garage/nodes/printer_1/device", json={"identity": "/dev/ttyFAKE1"}
        ).status_code
        == 200
    )
    printer_1 = next(s for s in garage.children if s.name == "printer_1")
    assert printer_1.status == "idle"

    scripted_links.factory = lambda port, baud: ScriptedTransport(port, baud, PRINTING)
    body = c.get("/firmware/printers/status", params={"port": "/dev/ttyFAKE1"}).json()
    assert body["synced"] == [
        {"site": "garage", "path": "printer_1", "status": "printing", "changed": True}
    ]
    assert printer_1.status == "printing"
    body = c.get("/firmware/printers/status", params={"port": "/dev/ttyFAKE1"}).json()
    assert body["synced"][0]["changed"] is False  # steady state: nothing to redraw

    # The site's device view carries the last poll and refreshes held links itself.
    rows = c.get("/sites/garage/devices").json()["bindings"]
    row = next(r for r in rows if r["path"] == "printer_1")
    assert row["printer_status"]["state"] == "printing" and row["printer_status"]["sd_printing"]
    assert ScriptedTransport.instances[0].sent.count("M105") == 3

    # A hand-set maintenance status is not overridden by a poll.
    c.post("/sites/garage/structures/printer_1/status", json={"status": "maintenance"})
    body = c.get("/firmware/printers/status", params={"port": "/dev/ttyFAKE1"}).json()
    assert body["synced"][0] == {
        "site": "garage",
        "path": "printer_1",
        "status": "maintenance",
        "changed": False,
        "held": True,
    }
    assert printer_1.status == "maintenance"

    # A failed poll reads as offline.
    c.post("/sites/garage/structures/printer_1/status", json={"status": "idle"})
    ScriptedTransport.instances[0].replies = {"M105": []}
    body = c.get("/firmware/printers/status", params={"port": "/dev/ttyFAKE1"}).json()
    assert body["state"] == "offline" and printer_1.status == "offline"

    # Unpinned: polls no longer touch the node.
    c.delete("/sites/garage/nodes/printer_1/device")
    scripted_links.factory = lambda port, baud: ScriptedTransport(port, baud)
    body = c.get("/firmware/printers/status", params={"port": "/dev/ttyFAKE1"}).json()
    assert body["synced"] == [] and printer_1.status == "offline"


def test_sync_skips_nodes_without_status(fake_arduino_cli, scripted_links, garage):
    c = TestClient(app)
    c.put("/sites/garage/nodes/footpedal/device", json={"identity": "/dev/ttyFAKE1"})
    body = c.get("/firmware/printers/status", params={"port": "/dev/ttyFAKE1"}).json()
    assert body["synced"] == []
    assert next(s for s in garage.children if s.name == "footpedal").status is None
    c.delete("/sites/garage/nodes/footpedal/device")


# --- manual queries: allowlisted report codes only -------------------------------------


def test_query_allowlist_normalises_and_refuses():
    assert gcode.normalise_query(" m420   v ") == "M420 V"
    assert gcode.normalise_query("M503") == "M503"
    for bad in ("M104 S200", "G28", "M112", "M500", "M420 S1", "", "M503; G28", "M503\nG28"):
        with pytest.raises(ValueError):
            gcode.normalise_query(bad)
    assert "M503" in gcode.QUERY_CODES and "M104" not in gcode.QUERY_CODES


def test_query_route_and_cli(fake_arduino_cli, fresh_task_runner, scripted_links):
    c = TestClient(app)
    assert c.get("/firmware/printers/queries").json()[0]["command"] == "M105"
    r = c.post("/firmware/printers/query", json={"port": "/dev/ttyFAKE1", "command": "M119"})
    assert r.status_code == 200
    assert r.json()["command"] == "M119" and r.json()["lines"][-1] == "ok"
    assert "y_min: TRIGGERED" in r.json()["lines"]
    # Identified + opened on first use, then reused: one transport, the query last.
    assert len(ScriptedTransport.instances) == 1
    assert ScriptedTransport.instances[0].sent[-1] == "M119"
    r = c.post("/firmware/printers/query", json={"port": "/dev/ttyFAKE1", "command": "M104 S200"})
    assert r.status_code == 422 and "report-only" in r.json()["detail"]
    assert "M104" not in ScriptedTransport.instances[0].sent
    assert (
        c.post("/firmware/printers/query", json={"port": "nope", "command": "M503"}).status_code
        == 422
    )

    scripted_links.stop_all()
    r = CliRunner().invoke(
        cli, ["firmware", "printer", "/dev/ttyFAKE1", "--query", "M119", "--query", "m27"]
    )
    assert r.exit_code == 0, r.output
    assert "> M119" in r.output and "y_min: TRIGGERED" in r.output and "> M27" in r.output
    assert (
        CliRunner()
        .invoke(cli, ["firmware", "printer", "/dev/ttyFAKE1", "--query", "G28"])
        .exit_code
        != 0
    )


def test_site_devices_fresh_forces_a_scan(fake_arduino_cli, scripted_links, garage):
    from firmware_helpers import fake_cli_calls

    c = TestClient(app)
    c.get("/sites/garage/devices")
    c.get("/sites/garage/devices")
    c.get("/sites/garage/devices", params={"fresh": 1})
    scans = [a for a in fake_cli_calls(fake_arduino_cli) if a[:2] == ["board", "list"]]
    assert len(scans) == 2


# --- the port scan cache -------------------------------------------------------------


def test_port_scan_is_cached_briefly(fake_arduino_cli, monkeypatch):
    from firmware_helpers import fake_cli_calls

    def scans():
        return sum(1 for argv in fake_cli_calls(fake_arduino_cli) if argv[:2] == ["board", "list"])

    devices.detected_devices()
    devices.detected_devices()
    assert scans() == 1  # coalesced
    devices.detected_devices(fresh=True)
    assert scans() == 2  # an explicit rescan
    monkeypatch.setattr(devices, "SCAN_TTL", 0.0)
    devices.detected_devices()
    assert scans() == 3  # expired
    c = TestClient(app)
    c.get("/firmware/devices")
    c.get("/firmware/devices", params={"fresh": 1})
    assert scans() == 5


# --- comms log, reconnect, reset, monitor page ----------------------------------------


def test_comms_log_records_traffic_and_survives_reconnect(fake_arduino_cli, scripted_links):
    devices.identify_printer("/dev/ttyFAKE1", 115200)
    devices.printer_status("/dev/ttyFAKE1")
    log = scripted_links.log_for("/dev/ttyFAKE1")
    kinds = [(e["kind"], e["text"]) for e in log.since(0)["entries"]]
    assert kinds[0][0] == "sys" and "opened /dev/ttyFAKE1 @ 115200" in kinds[0][1]
    assert ("tx", "M115") in kinds and ("rx", "ok") in kinds and ("tx", "M105") in kinds
    n = log.next_index
    assert log.since(n) == {"entries": [], "next": n}

    # Reconnect: a new transport, same log, story continues.
    st = devices.printer_reconnect("/dev/ttyFAKE1")
    assert st.state == "idle" and len(ScriptedTransport.instances) == 2
    later = [e["text"] for e in log.since(n)["entries"] if e["kind"] == "sys"]
    assert any("closed" in t for t in later) and any("opened" in t for t in later)

    # Reset: logged, boot lines returned, transport pulsed.
    boot = devices.printer_reset("/dev/ttyFAKE1")
    assert boot[0] == "start" and ScriptedTransport.instances[-1].resets == 1
    entries = log.since(0)["entries"]
    assert any(e["kind"] == "boot" and e["text"] == "start" for e in entries)
    assert any(e["kind"] == "sys" and "reset" in e["text"] for e in entries)

    # The ring drops the oldest quarter once full.
    small = gcode.CommsLog("/dev/x", capacity=8)
    for i in range(10):
        small.add("rx", str(i))
    got = small.since(0)
    assert [e["text"] for e in got["entries"]] == [str(i) for i in range(2, 10)]
    assert got["entries"][0]["i"] == 2 and got["next"] == 10


def test_monitor_routes(fake_arduino_cli, fresh_task_runner, scripted_links):
    c = TestClient(app)
    r = c.get("/firmware/monitor", params={"port": "/dev/ttyFAKE1"})
    assert r.status_code == 200 and "Printer monitor" in r.text and "/dev/ttyFAKE1" in r.text

    info = c.get("/firmware/printers/info", params={"port": "/dev/ttyFAKE1"}).json()
    assert info["detected"] and info["link"] is None and info["last_status"] is None
    assert info["engine"] in ("pyserial", "termios", "simulated")
    c.get("/firmware/printers/status", params={"port": "/dev/ttyFAKE1"})
    info = c.get("/firmware/printers/info", params={"port": "/dev/ttyFAKE1"}).json()
    assert info["link"]["baud"] == 115200 and info["link"]["engine"] == "ScriptedTransport"
    assert info["last_status"]["state"] == "idle" and info["device"]["device"]["printer"]

    log = c.get("/firmware/printers/log", params={"port": "/dev/ttyFAKE1"}).json()
    assert log["held"] and log["entries"][0]["kind"] == "sys" and log["next"] > 5
    tail = c.get(
        "/firmware/printers/log", params={"port": "/dev/ttyFAKE1", "since": log["next"]}
    ).json()
    assert tail["entries"] == []

    r = c.post("/firmware/printers/reconnect", json={"port": "/dev/ttyFAKE1"})
    assert r.status_code == 200 and r.json()["state"] == "idle" and "heating" in r.json()
    r = c.post("/firmware/printers/reset", json={"port": "/dev/ttyFAKE1"})
    assert r.status_code == 200 and r.json()["boot_lines"][0] == "start"
    assert c.get("/firmware/printers/log", params={"port": "nope"}).status_code == 422
    assert c.get("/firmware/printers/info", params={"port": "nope"}).status_code == 422
    assert c.post("/firmware/printers/reset", json={"port": "/dev/ttyNOPE"}).status_code == 503

    # Viewer and firmware page link to the monitor for a printer.
    assert "/firmware/monitor" in c.get("/viewer/sites/garage").text
    assert "/firmware/monitor" in c.get("/firmware").text


# --- the board inside the printer drives the printer --------------------------------

BOARD = "printer_1.frame_system.mainboard"


def test_garage_printers_carry_a_mainboard(garage):
    from apothecary.api import _find_node_by_path, status_bearer_for

    board = _find_node_by_path(garage, BOARD)
    assert board is not None and board.status is None and board.category == "electrical"
    assert board.footprint.max_point.x == 102.0
    assert status_bearer_for(garage, BOARD) == "printer_1"
    assert status_bearer_for(garage, "printer_1") == "printer_1"
    assert status_bearer_for(garage, "footpedal") is None
    assert status_bearer_for(garage, "printer_1.no_such_child") == "printer_1"


def test_poll_on_the_board_drives_the_printer(
    fake_arduino_cli, fresh_task_runner, scripted_links, garage
):
    c = TestClient(app)
    assert (
        c.put(f"/sites/garage/nodes/{BOARD}/device", json={"identity": "/dev/ttyFAKE1"}).status_code
        == 200
    )
    printer_1 = next(s for s in garage.children if s.name == "printer_1")
    scripted_links.factory = lambda port, baud: ScriptedTransport(port, baud, PRINTING)
    body = c.get("/firmware/printers/status", params={"port": "/dev/ttyFAKE1"}).json()
    assert body["synced"] == [
        {"site": "garage", "path": "printer_1", "via": BOARD, "status": "printing", "changed": True}
    ]
    assert printer_1.status == "printing"

    # The bindings view has a row for the board, none for the printer itself.
    rows = {r["path"]: r for r in c.get("/sites/garage/devices").json()["bindings"]}
    assert BOARD in rows and "printer_1" not in rows
    assert rows[BOARD]["printer_status"]["state"] == "printing"

    # maintenance on the printer still holds against the board's polls.
    c.post("/sites/garage/structures/printer_1/status", json={"status": "maintenance"})
    body = c.get("/firmware/printers/status", params={"port": "/dev/ttyFAKE1"}).json()
    assert body["synced"][0]["held"] is True and printer_1.status == "maintenance"
    c.delete(f"/sites/garage/nodes/{BOARD}/device")


# --- latched control: heaters, motion, SD control only while armed ----------------


def test_control_allowlist_and_bounds():
    ok = [
        "m104 s200",
        "M140 S60",
        "M106",
        "M106 S128",
        "M107",
        "G28",
        "G28 X Y",
        "G91",
        "G90",
        "G1 X10 F3000",
        "G0 Z-0.1",
        "G1 X-10 Y10 Z5",
        "M84",
        "M23 GRIDFI~1.GCO",
        "M24",
        "M25",
        "M524",
        "M420 S1",
        "M108",
        "M410",
        "G29",
        "G30 X110 Y110",
        "m112",
    ]
    for cmd in ok:
        gcode.normalise_control(cmd)
    assert gcode.normalise_control(" g1  x10   f3000 ") == "G1 X10 F3000"
    bad = [
        "M104 S301",
        "M140 S131",
        "M106 S256",
        "G1 X301",
        "G1 X10 F20000",
        "G1 E50",
        "G29 P1",
        "G30 X1000",
        "M500",
        "M502",
        "M503",
        "M105",
        "M23 ../etc",
        "G1 X10; M112",
        "",
        "M104",
    ]
    for cmd in bad:
        with pytest.raises(ValueError):
            gcode.normalise_control(cmd)


def test_control_latch_arms_renews_and_lapses(monkeypatch):
    latch = gcode.ControlLatch()
    assert not latch.armed("/dev/x") and latch.seconds_left("/dev/x") == 0
    latch.arm("/dev/x", ttl=0.2)
    assert latch.armed("/dev/x") and 0 < latch.seconds_left("/dev/x") <= 0.2
    time.sleep(0.25)
    assert not latch.armed("/dev/x")
    latch.renew("/dev/x")  # renewing a lapsed latch does not arm it
    assert not latch.armed("/dev/x")
    latch.arm("/dev/x")
    latch.disarm("/dev/x")
    assert not latch.armed("/dev/x")


def test_control_route_requires_the_latch(fake_arduino_cli, fresh_task_runner, scripted_links):
    c = TestClient(app)
    port = "/dev/ttyFAKE1"
    assert c.get("/firmware/printers/controls").json()["bounds"]["hotend_max_c"] == 300
    assert c.get("/firmware/printers/control", params={"port": port}).json()["armed"] is False

    r = c.post("/firmware/printers/command", json={"port": port, "command": "M104 S200"})
    assert r.status_code == 409 and "not armed" in r.json()["detail"]
    assert (
        c.post("/firmware/printers/command", json={"port": port, "command": "M500"}).status_code
        == 422
    )
    assert not ScriptedTransport.instances  # nothing reached a port

    r = c.post("/firmware/printers/control", json={"port": port, "armed": True, "ttl_s": 60})
    assert r.json()["armed"] is True and 55 <= r.json()["seconds_left"] <= 60
    r = c.post("/firmware/printers/command", json={"port": port, "command": "m104 s200"})
    assert r.status_code == 200 and r.json()["command"] == "M104 S200"
    assert r.json()["control"]["armed"] is True and r.json()["lines"][-1] == "ok"
    assert ScriptedTransport.instances[0].sent[-1] == "M104 S200"
    log = scripted_links.log_for(port).since(0)["entries"]
    assert any(e["origin"] == "control" and e["text"] == "M104 S200" for e in log)
    assert any(e["kind"] == "sys" and "control armed" in e["text"] for e in log)

    # Disarm: commands stop; the emergency stop still goes through.
    c.post("/firmware/printers/control", json={"port": port, "armed": False})
    assert (
        c.post("/firmware/printers/command", json={"port": port, "command": "G28"}).status_code
        == 409
    )
    ScriptedTransport.instances[0].replies = {
        **REPLIES,
        "M112": ["Error:Printer halted. kill() called!"],
    }
    r = c.post("/firmware/printers/command", json={"port": port, "command": "M112"})
    assert r.status_code == 503 and "halted" in r.json()["detail"]  # the board says so; it was sent
    assert ScriptedTransport.instances[0].sent[-1] == "M112"

    # Release drops the latch with the link.
    c.post("/firmware/printers/control", json={"port": port, "armed": True})
    c.post("/firmware/printers/release", json={"port": port})
    assert (
        c.get("/firmware/printers/info", params={"port": port}).json()["control"]["armed"] is False
    )


def test_simulator_honours_controls(monkeypatch):
    monkeypatch.setenv("APOTHECARY_SIMULATED_PRINTER", "idle")
    link = gcode.GcodeLink("/dev/ttySIM", 115200, gcode.SimulatedPrinter("/dev/ttySIM", 115200))
    gcode.control_printer(link, "M104 S50")
    gcode.control_printer(link, "M140 S40")
    st = gcode.poll_printer(link)
    assert st.hotends[0].target == 50.0 and abs(st.hotends[0].actual - 50) < 1
    assert st.bed.target == 40.0
    gcode.control_printer(link, "G28")
    gcode.control_printer(link, "G91")
    gcode.control_printer(link, "G1 X10 Z-1 F3000")
    gcode.control_printer(link, "G90")
    st = gcode.poll_printer(link)
    assert st.position == {"x": 10.0, "y": 0.0, "z": -1.0, "e": 0.0}
    gcode.control_printer(link, "M24")
    assert gcode.poll_printer(link).state == "printing"
    gcode.control_printer(link, "M25")
    assert gcode.poll_printer(link).state == "idle"
    with pytest.raises(ToolchainError, match="halted"):
        gcode.control_printer(link, "M112")
    with pytest.raises(ToolchainError, match="halted"):
        gcode.poll_printer(link)


# --- review fixes: the monitor page never reflects a raw port; polls carry the latch -------


def test_monitor_page_emits_the_port_as_json_and_drops_bad_ones(fake_arduino_cli):
    c = TestClient(app)
    r = c.get("/firmware/monitor", params={"port": '";alert(1);//'})
    assert r.status_code == 200 and "alert(1)" not in r.text and 'port: ""' in r.text
    r = c.get("/firmware/monitor", params={"port": "</script><script>alert(2)</script>"})
    assert "alert(2)" not in r.text
    r = c.get("/firmware/monitor", params={"port": "/dev/ttyFAKE1"})
    assert 'port: "/dev/ttyFAKE1"' in r.text


def test_status_poll_reports_held_link_and_latch(
    fake_arduino_cli, fresh_task_runner, scripted_links
):
    c = TestClient(app)
    port = "/dev/ttyFAKE1"
    body = c.get("/firmware/printers/status", params={"port": port}).json()
    assert body["held"] is True and body["control"] == {
        "port": port,
        "armed": False,
        "seconds_left": 0,
    }
    c.post("/firmware/printers/control", json={"port": port, "armed": True})
    body = c.get("/firmware/printers/status", params={"port": port}).json()
    assert body["control"]["armed"] is True
    # A failed poll drops the link and, with it, the latch -- and says so.
    ScriptedTransport.instances[0].replies = {"M105": []}
    body = c.get("/firmware/printers/status", params={"port": port}).json()
    assert (
        body["state"] == "offline" and body["held"] is False and body["control"]["armed"] is False
    )


# --- where a port is pinned, for the board view -----------------------------------------


def test_where_a_port_is_pinned_carries_the_geometry_a_view_needs(fake_arduino_cli, garage):
    c = TestClient(app)
    assert (
        c.get("/firmware/printers/where", params={"port": "/dev/ttyFAKE1"}).json()["board"] is None
    )
    c.put(f"/sites/garage/nodes/{BOARD}/device", json={"identity": "/dev/ttyFAKE1"})
    where = c.get("/firmware/printers/where", params={"port": "/dev/ttyFAKE1"}).json()
    assert where["site"] == "garage" and where["board"]["path"] == BOARD
    assert where["board"]["footprint"]["max"] == [102.0, 74.0, 15.0]
    assert where["printer"]["path"] == "printer_1"
    assert where["printer"]["build_volume"] == [220.0, 220.0, 250.0]
    assert where["printer"]["base_height"] == 50.0  # the enclosure the bed sits on
    # World positions: the board sits inside the printer, which sits on the bench.
    p, b = where["printer"]["position"], where["board"]["position"]
    assert (b["x"] - p["x"], b["y"] - p["y"], b["z"] - p["z"]) == (20.0, 20.0, 5.0)
    c.delete(f"/sites/garage/nodes/{BOARD}/device")
    # A pin on the printer itself: the board is the printer, and there is no separate printer.
    c.put("/sites/garage/nodes/printer_1/device", json={"identity": "/dev/ttyFAKE1"})
    where = c.get("/firmware/printers/where", params={"port": "/dev/ttyFAKE1"}).json()
    assert where["board"]["path"] == "printer_1" and where["printer"] is None
    c.delete("/sites/garage/nodes/printer_1/device")


# --- bed leveling: Marlin's mesh read, a probe run as a job, and its records ------------

MESH_REPORT = [
    "Bilinear Leveling Grid:",
    "      0      1      2",
    " 0 -0.150 +0.000 +0.150",
    " 1 -0.100 +0.050 +0.200",
    " 2 -0.050 +0.100 +0.250",
    "",
    "Subdivided with CATMULL ROM LEVELING GRID:",
    "       0       1       2       3       4",
    " 0 -0.1500 -0.0750 +0.0000 +0.0750 +0.1500",
    " 1 -0.1250 -0.0500 +0.0250 +0.1000 +0.1750",
    " 2 -0.1000 -0.0250 +0.0500 +0.1250 +0.2000",
    " 3 -0.0750 +0.0000 +0.0750 +0.1500 +0.2250",
    " 4 -0.0500 +0.0250 +0.1000 +0.1750 +0.2500",
    "echo:Bed Leveling ON",
    "echo:Fade Height 10.00",
    "ok",
]

LEVELING = {
    **REPLIES,
    "G28": ["ok"],
    "G29": ["echo:busy: processing", "echo:busy: processing", *MESH_REPORT[:6], "ok"],
    "M420 V": MESH_REPORT,
    "M851": ["echo:  M851 X-44.00 Y-10.00 Z-3.15 ; (mm)", "ok"],
}


def test_parse_meshes_reads_the_grid_and_the_subdivided_one():
    grids = gcode.parse_meshes(MESH_REPORT)
    assert len(grids) == 2
    assert grids[0] == [[-0.15, 0.0, 0.15], [-0.1, 0.05, 0.2], [-0.05, 0.1, 0.25]]
    assert len(grids[1]) == 5 and all(len(row) == 5 for row in grids[1])
    assert grids[1][4][4] == 0.25
    # A board that stores its mesh answers M503 with one point per line; those gather too.
    points = [
        "echo:  G29 W I0 J0 Z-0.10000",
        "echo:  G29 W I1 J0 Z0.10000",
        "echo:  G29 W I0 J1 Z0.00000",
        "echo:  G29 W I1 J1 Z0.20000",
        "ok",
    ]
    assert gcode.parse_meshes(points) == [[[-0.1, 0.1], [0.0, 0.2]]]
    assert gcode.parse_meshes(["echo:Bed Leveling OFF", "ok"]) == []


def test_mesh_stats_reports_range_tilt_and_corners():
    stats = gcode.mesh_stats([[-0.15, 0.0, 0.15], [-0.1, 0.05, 0.2], [-0.05, 0.1, 0.25]])
    assert stats["rows"] == 3 and stats["cols"] == 3
    assert stats["min"] == -0.15 and stats["max"] == 0.25 and stats["range"] == 0.4
    assert stats["mean"] == 0.05
    # The plane is z = 0.15*x + 0.05*y - 0.15: 0.3 mm of rise across X, 0.1 across Y.
    assert stats["tilt_x"] == pytest.approx(0.3) and stats["tilt_y"] == pytest.approx(0.1)
    assert stats["corners"] == {
        "front_left": -0.2,
        "front_right": 0.1,
        "back_left": -0.1,
        "back_right": 0.2,
    }
    assert gcode.mesh_stats([]) == {"rows": 0, "cols": 0}
    assert gcode.mesh_stats([[0.3]])["tilt_x"] == 0.0


def test_parse_probe_offset_single_probe_and_leveling_state():
    assert gcode.parse_probe_offset(LEVELING["M851"]) == {"x": -44.0, "y": -10.0, "z": -3.15}
    assert gcode.parse_probe_offset(["ok"]) is None
    assert gcode.parse_g30(["Bed X: 110.00 Y: 110.00 Z: 0.12", "ok"]) == {
        "x": 110.0,
        "y": 110.0,
        "z": 0.12,
    }
    assert gcode.parse_g30(["ok"]) is None
    assert gcode.parse_leveling_state(MESH_REPORT) is True
    assert gcode.parse_leveling_state(["echo:Bed Leveling OFF"]) is False
    assert gcode.parse_leveling_state(["ok"]) is None


def test_the_probe_codes_are_controls_within_bounds():
    assert gcode.normalise_control("g29") == "G29"
    assert gcode.normalise_control("G30 X110 Y110") == "G30 X110 Y110"
    assert gcode.normalise_control("M420 S1") == "M420 S1"
    with pytest.raises(ValueError):
        gcode.normalise_control("G30 X1000 Y10")  # off the bed
    with pytest.raises(ValueError):
        gcode.normalise_control("G29 P1")  # only the plain probe


def test_simulator_answers_the_leveling_codes(monkeypatch):
    monkeypatch.setenv("APOTHECARY_SIMULATED_PRINTER", "idle")
    link = gcode.GcodeLink("/dev/ttySIM", 115200, gcode.SimulatedPrinter("/dev/ttySIM", 115200))
    probed = gcode.control_printer(link, "G29")
    assert probed[0].startswith("echo:busy") and probed[-1] == "ok"
    grids = gcode.parse_meshes(link.command("M420 V"))
    assert len(grids) == 1 and len(grids[0]) == 5 and len(grids[0][0]) == 5
    stats = gcode.mesh_stats(grids[0])
    assert 0.3 < stats["range"] < 1.2 and stats["tilt_x"] > 0 > stats["tilt_y"]
    assert gcode.parse_probe_offset(link.command("M851")) == {"x": -44.0, "y": -10.0, "z": -3.15}
    hit = gcode.parse_g30(gcode.control_printer(link, "G30 X110 Y110"))
    assert hit["x"] == 110.0 and hit["y"] == 110.0 and abs(hit["z"]) < 0.5


def test_leveling_job_homes_probes_reads_and_saves(fake_arduino_cli, scripted_links):
    port = "/dev/ttyFAKE1"
    gate = threading.Event()

    class SlowProbe(ScriptedTransport):
        def write(self, data):
            if data.decode().strip() == "G29":
                gate.wait(5)  # a probe takes minutes; the test says when it is done
            super().write(data)

    scripted_links.factory = SlowProbe
    for t in ScriptedTransport.instances:
        t.replies = LEVELING
    with pytest.raises(gcode.ControlNotArmed):
        devices.start_leveling(port, probe=True, links=scripted_links)
    scripted_links.control.arm(port)
    job = devices.start_leveling(port, probe=True, note="after new springs", links=scripted_links)
    ScriptedTransport.instances[0].replies = LEVELING
    for _ in range(200):
        if job.stage == "probing":
            break
        time.sleep(0.01)
    assert job.stage == "probing" and job.snapshot()["running"] is True
    # While the probe runs the port is spoken for: polls say so without touching
    # it, queries and controls are refused, the emergency stop is not.
    st = devices.printer_status(port, links=scripted_links)
    assert st.job["kind"] == "leveling" and st.job["stage"] == "probing"
    with pytest.raises(ToolchainError, match="bed reading holds the port"):
        devices.printer_query(port, "M105", links=scripted_links)
    with pytest.raises(ToolchainError, match="bed reading holds the port"):
        devices.printer_control(port, "G28", links=scripted_links)
    with pytest.raises(ToolchainError, match="already probing"):
        devices.start_leveling(port, probe=False, links=scripted_links)
    gate.set()
    job.thread.join(5)
    assert job.stage == "saved" and job.error is None and job.record is not None
    sent = ScriptedTransport.instances[0].sent
    assert sent.index("G28") < sent.index("G29") < sent.index("M420 V") < sent.index("M851")
    rec = job.record
    assert rec.method == "probe" and rec.note == "after new springs"
    assert rec.mesh == [[-0.15, 0.0, 0.15], [-0.1, 0.05, 0.2], [-0.05, 0.1, 0.25]]
    assert rec.subdivided is not None and len(rec.subdivided) == 5
    assert rec.stats["range"] == 0.4 and rec.leveling_on is True
    assert rec.probe_offset == {"x": -44.0, "y": -10.0, "z": -3.15}
    assert rec.hotend_c == 22.3 and rec.bed_c == 23.59
    assert rec.firmware == "Marlin TH3D UFW 2.94a (Jan 17 2025 11:35:34)"
    assert "echo:Bed Leveling ON" in rec.lines
    saved = devices.leveling_records(port)
    assert [r.id for r in saved] == [rec.id] and devices.leveling_record(rec.id) == rec
    assert devices.leveling_records("/dev/ttyOTHER") == []
    assert (devices.leveling_dir() / f"{rec.id}.json").is_file()
    # The port is free again, and the poll goes to the board.
    assert devices.printer_status(port, links=scripted_links).job is None
    # A read without a probe needs no latch and moves nothing.
    scripted_links.control.disarm(port)
    job = devices.start_leveling(port, probe=False, links=scripted_links)
    job.thread.join(5)
    assert job.stage == "saved" and job.record.method == "read"
    assert sent.count("G29") == 1 and sent.count("G28") == 1
    assert len(devices.leveling_records(port)) == 2


def test_leveling_job_reports_a_board_that_will_not_probe(fake_arduino_cli, scripted_links):
    port = "/dev/ttyFAKE1"
    scripted_links.control.arm(port)
    devices.printer_status(port, links=scripted_links)
    ScriptedTransport.instances[0].replies = {**LEVELING, "G29": ["Error:Probing failed"]}
    job = devices.start_leveling(port, probe=True, links=scripted_links)
    job.thread.join(5)
    assert job.stage == "failed" and "Probing failed" in job.error
    assert job.record is None and devices.leveling_records(port) == []
    log = scripted_links.log_for(port).since(0)["entries"]
    assert any(e["kind"] == "sys" and "bed reading failed" in e["text"] for e in log)


def test_leveling_routes(fake_arduino_cli, fresh_task_runner, scripted_links):
    c = TestClient(app)
    port = "/dev/ttyFAKE1"
    assert c.get("/firmware/printers/level", params={"port": port}).json() == {
        "port": port,
        "running": False,
        "stage": None,
    }
    assert c.get("/firmware/printers/leveling", params={"port": port}).json() == []
    assert c.get("/firmware/printers/leveling/nope").status_code == 404
    assert c.get("/firmware/printers/level", params={"port": "bad port"}).status_code == 422

    r = c.post("/firmware/printers/level", json={"port": port, "probe": True})
    assert r.status_code == 409 and "arm control" in r.json()["detail"]
    c.post("/firmware/printers/control", json={"port": port, "armed": True})
    c.get("/firmware/printers/status", params={"port": port})  # opens the link
    ScriptedTransport.instances[0].replies = LEVELING
    r = c.post("/firmware/printers/level", json={"port": port, "probe": True, "note": "first"})
    assert r.status_code == 202 and r.json()["kind"] == "leveling"
    for _ in range(500):
        job = c.get("/firmware/printers/level", params={"port": port}).json()
        if not job["running"]:
            break
        time.sleep(0.01)
    assert job["stage"] == "saved" and job["record_id"]
    records = c.get("/firmware/printers/leveling", params={"port": port}).json()
    assert len(records) == 1 and records[0]["id"] == job["record_id"]
    assert records[0]["note"] == "first" and records[0]["stats"]["rows"] == 3
    assert "lines" not in records[0] and "subdivided" not in records[0]
    full = c.get(f"/firmware/printers/leveling/{job['record_id']}").json()
    assert full["mesh"][2][2] == 0.25 and len(full["subdivided"]) == 5
    assert full["lines"][-1].startswith("ok T:")  # the temperatures, last of the reading
    assert c.get("/firmware/printers/leveling").json()[0]["port"] == port


# --- host printing: a file streamed one line per ok, with the polls between ------------

SMALL_PRINT = """; a sliced file, as a slicer writes one
M140 S60 ; bed
M104 S200
G28
G90
G1 Z0.2 F600
G1 X10 Y10 E0.5 F1200 ; first line
G1 X20 Y10 E1.0
(a bracket comment) G1 X20 Y20 E1.5
M107
M104 S0
M140 S0
M84
"""


def test_check_gcode_counts_lines_and_refuses_what_it_must():
    total, problems = gcode.check_gcode(SMALL_PRINT)
    assert total == 12 and problems == []
    total, problems = gcode.check_gcode("G28\nM500\nM104 S310\nM190 R140\nM997\n")
    assert total == 5
    assert problems == [
        "line 2: M500 saves settings to EEPROM",
        "line 3: M104 asks for 310 degC, above 300",
        "line 4: M190 asks for 140 degC, above 130",
        "line 5: M997 starts a firmware update",
    ]
    assert gcode.strip_gcode("  g1  x10 ; move") == "G1 X10"
    assert gcode.line_timeout("M109 S200") == gcode.PRINT_SLOW_TIMEOUT_S
    assert gcode.line_timeout("G1 X1") == gcode.PRINT_LINE_TIMEOUT_S


def test_print_files_are_kept_checked_and_forgotten(fake_arduino_cli):
    kept = devices.save_print_file("Bracket v2.gcode", SMALL_PRINT.encode())
    assert kept.name == "Bracket v2.gcode" and kept.lines == 12 and kept.problems == []
    assert kept.id.endswith("-Bracket_v2") and kept.size == len(SMALL_PRINT)
    bad = devices.save_print_file("../../evil.gcode", b"M500\n")
    assert bad.problems == ["line 1: M500 saves settings to EEPROM"]
    assert "/" not in bad.id and (devices.prints_dir() / f"{bad.id}.gcode").is_file()
    assert [f.id for f in devices.print_files()] == [bad.id, kept.id]
    assert devices.print_file(kept.id) == kept and devices.print_file("nope") is None
    assert devices.delete_print_file(bad.id) is True
    assert devices.delete_print_file(bad.id) is False
    assert [f.id for f in devices.print_files()] == [kept.id]


def test_print_job_streams_pauses_resumes_and_polls_between_lines(fake_arduino_cli, scripted_links):
    port = "/dev/ttyFAKE1"
    kept = devices.save_print_file("small.gcode", SMALL_PRINT.encode())
    gate = threading.Event()
    gate.set()

    class GatedTransport(ScriptedTransport):
        def write(self, data):
            cmd = data.decode().strip()
            if cmd.startswith("G1 X20 Y10"):
                gate.wait(5)  # the test holds the stream here
            super().write(data)

    scripted_links.factory = GatedTransport
    with pytest.raises(gcode.ControlNotArmed):
        devices.start_print(port, kept.id, links=scripted_links)
    scripted_links.control.arm(port)
    with pytest.raises(ToolchainError, match="no such print file"):
        devices.start_print(port, "nope", links=scripted_links)
    gate.clear()
    job = devices.start_print(port, kept.id, links=scripted_links)
    transport = ScriptedTransport.instances[0]
    for _ in range(300):
        if "G1 X10 Y10 E0.5 F1200" in transport.sent:
            break
        time.sleep(0.01)
    assert job.stage == "printing" and job.snapshot()["running"] is True
    # The board is held mid-line: a poll declines to queue and says what holds it.
    st = devices.printer_status(port, links=scripted_links)
    assert st.job["kind"] == "print" and st.job["name"] == "small.gcode"
    assert st.state == "printing" and 0 < st.job["progress"] < 1
    # A second print, a bed reading, a release, a reset: all refused; a query and a
    # heater change wait their turn; motion is the job's.
    with pytest.raises(ToolchainError, match="already holds the port"):
        devices.start_print(port, kept.id, links=scripted_links)
    with pytest.raises(ToolchainError, match="a print holds the port"):
        devices.start_leveling(port, probe=False, links=scripted_links)
    with pytest.raises(ToolchainError, match="cancel it first"):
        scripted_links.close(port)
    with pytest.raises(ToolchainError, match="not resetting"):
        devices.printer_reset(port, links=scripted_links)
    with pytest.raises(ToolchainError, match="a print holds the port"):
        devices.printer_control(port, "G28", links=scripted_links)
    job.pause()
    assert job.stage == "paused"
    gate.set()  # the held line answers; the feed is paused so nothing follows it
    time.sleep(0.3)
    sent_while_paused = len(transport.sent)
    assert "G1 X20 Y20 E1.5" not in transport.sent
    # Paused, the link is free: a poll goes to the board and still says "paused".
    st = devices.printer_status(port, links=scripted_links)
    assert st.job["stage"] == "paused" and st.state == "printing" and "M105" in transport.sent
    assert devices.printer_control(port, "M104 S205", links=scripted_links).lines[-1] == "ok"
    assert devices.printer_query(port, "M119", links=scripted_links).lines[-1] == "ok"
    job.resume()
    job.thread.join(5)
    assert job.stage == "done" and job.error is None
    streamed = [
        c
        for c in transport.sent
        if c not in ("M105", "M114", "M27", "M119", "M31", "M115", "M104 S205")
    ]
    assert streamed == [
        "M140 S60",
        "M104 S200",
        "G28",
        "G90",
        "G1 Z0.2 F600",
        "G1 X10 Y10 E0.5 F1200",
        "G1 X20 Y10 E1.0",
        "G1 X20 Y20 E1.5",
        "M107",
        "M104 S0",
        "M140 S0",
        "M84",
    ]
    assert len(transport.sent) > sent_while_paused
    rec = job.record
    assert rec is not None and rec.outcome == "done" and rec.sent == 12 == rec.total
    assert rec.firmware == "Marlin TH3D UFW 2.94a (Jan 17 2025 11:35:34)"
    assert [r.id for r in devices.print_records(port)] == [rec.id]
    assert devices.print_record(rec.id) == rec
    # The stream stays out of the comms log (a print is thousands of lines); the
    # record keeps the tail, and the log says how it started and how it ended.
    log = scripted_links.log_for(port).since(0)["entries"]
    assert not any(e["origin"] == "print" and e["kind"] == "tx" for e in log)
    assert any(
        e["kind"] == "sys" and "print started: small.gcode (12 lines)" in e["text"] for e in log
    )
    assert any(e["kind"] == "sys" and "print done: small.gcode, 12/12" in e["text"] for e in log)
    assert rec.lines[-3:] == ["> M140 S0", "ok", "> M84"] or rec.lines[-1] == "ok"
    # The port is free again: the poll goes to the board and the state is the card's.
    st = devices.printer_status(port, links=scripted_links)
    assert st.job is None and st.state == "idle"
    assert scripted_links.close(port) is True


def test_print_job_cancel_sends_the_safe_off_and_a_stop_does_not(fake_arduino_cli, scripted_links):
    port = "/dev/ttyFAKE1"
    kept = devices.save_print_file("long.gcode", ("G1 X1\n" * 400).encode())
    gate = threading.Event()

    class SlowTransport(ScriptedTransport):
        def write(self, data):
            if data.decode().strip() == "G1 X1":
                gate.wait(0.02)  # a slow board: the stream is still going when we cancel
            super().write(data)

    scripted_links.factory = SlowTransport
    scripted_links.control.arm(port)
    job = devices.start_print(port, kept.id, links=scripted_links)
    time.sleep(0.2)
    job.cancel()
    job.thread.join(5)
    transport = ScriptedTransport.instances[0]
    assert job.stage == "cancelled" and 0 < job.sent < 400
    assert transport.sent[-4:] == ["M104 S0", "M140 S0", "M107", "M84"]
    assert job.record.outcome == "cancelled" and job.record.sent == job.sent
    # The stop: the board halts, the job is cancelled quietly, nothing more is sent.
    job = devices.start_print(port, kept.id, links=scripted_links)
    time.sleep(0.1)
    transport.replies = {**REPLIES, "M112": ["Error:Printer halted. kill() called!"]}
    with pytest.raises(ToolchainError, match="halted"):
        devices.printer_control(port, "M112", links=scripted_links)
    job.thread.join(5)
    assert job.stage == "cancelled" and job.record.outcome == "cancelled"
    assert "M112" in transport.sent and transport.sent[-1] != "M84"
    assert transport.sent.index("M112") >= len(transport.sent) - 2  # at most one line after


def test_print_job_fails_on_a_board_error_and_still_turns_the_heat_off(
    fake_arduino_cli, scripted_links
):
    port = "/dev/ttyFAKE1"
    kept = devices.save_print_file("bad.gcode", b"G28\nG1 X5\nG1 X6\n")
    scripted_links.control.arm(port)
    devices.printer_status(port, links=scripted_links)
    ScriptedTransport.instances[0].replies = {
        **REPLIES,
        "G1 X5": ["Error:Failed to enable Bed Leveling"],
    }
    job = devices.start_print(port, kept.id, links=scripted_links)
    job.thread.join(5)
    assert job.stage == "failed" and "Failed to enable" in job.error
    log = scripted_links.log_for(port).since(0)["entries"]
    objected = [e for e in log if e["origin"] == "print" and e["kind"] in ("tx", "rx")]
    assert [e["text"] for e in objected][:2] == ["G1 X5", "Error:Failed to enable Bed Leveling"]
    # The safe-off is said out loud.
    assert [e["text"] for e in objected[2:] if e["kind"] == "tx"] == list(devices.PRINT_SAFE_OFF)
    sent = ScriptedTransport.instances[0].sent
    assert sent[-4:] == ["M104 S0", "M140 S0", "M107", "M84"] and "G1 X6" not in sent
    assert job.record.outcome == "failed" and job.record.sent == 1


def test_print_refuses_a_file_with_problems_and_a_card_that_is_printing(
    fake_arduino_cli, scripted_links
):
    port = "/dev/ttyFAKE1"
    bad = devices.save_print_file("bad.gcode", b"M500\n")
    empty = devices.save_print_file("empty.gcode", b"; nothing\n")
    good = devices.save_print_file("ok.gcode", b"G28\n")
    scripted_links.control.arm(port)
    with pytest.raises(ToolchainError, match="may not be sent"):
        devices.start_print(port, bad.id, links=scripted_links)
    with pytest.raises(ToolchainError, match="nothing to send"):
        devices.start_print(port, empty.id, links=scripted_links)
    devices.printer_status(port, links=scripted_links)
    ScriptedTransport.instances[0].replies = PRINTING
    devices.printer_status(port, links=scripted_links)
    with pytest.raises(ToolchainError, match="the card is printing"):
        devices.start_print(port, good.id, links=scripted_links)


def test_print_routes(fake_arduino_cli, fresh_task_runner, scripted_links):
    c = TestClient(app)
    port = "/dev/ttyFAKE1"
    assert c.get("/firmware/printers/prints").json() == []
    assert (
        c.post("/firmware/printers/prints", params={"name": "x.gcode"}, content=b"").status_code
        == 422
    )
    r = c.post(
        "/firmware/printers/prints", params={"name": "small.gcode"}, content=SMALL_PRINT.encode()
    )
    assert r.status_code == 201 and r.json()["lines"] == 12 and r.json()["problems"] == []
    file_id = r.json()["id"]
    assert c.get("/firmware/printers/prints").json()[0]["id"] == file_id
    assert c.get("/firmware/printers/print", params={"port": port}).json()["running"] is False
    assert c.post("/firmware/printers/print/pause", json={"port": port}).status_code == 409

    r = c.post("/firmware/printers/print", json={"port": port, "file_id": file_id})
    assert r.status_code == 409 and "arm control" in r.json()["detail"]
    c.post("/firmware/printers/control", json={"port": port, "armed": True})
    assert (
        c.post("/firmware/printers/print", json={"port": port, "file_id": "nope"}).status_code
        == 409
    )
    r = c.post("/firmware/printers/print", json={"port": port, "file_id": file_id})
    assert r.status_code == 202 and r.json()["kind"] == "print" and r.json()["total"] == 12
    # While it streams, the file cannot be forgotten and the link cannot be dropped.
    assert c.delete(f"/firmware/printers/prints/{file_id}").status_code in (409, 200)
    for _ in range(500):
        job = c.get("/firmware/printers/print", params={"port": port}).json()
        if not job["running"]:
            break
        time.sleep(0.01)
    assert job["stage"] == "done" and job["sent"] == 12 and job["record_id"]
    records = c.get("/firmware/printers/print/records", params={"port": port}).json()
    assert len(records) == 1 and records[0]["outcome"] == "done" and "lines" not in records[0]
    full = c.get(f"/firmware/printers/print/records/{job['record_id']}").json()
    assert full["lines"][-1] == "ok"
    assert c.get("/firmware/printers/print/records/nope").status_code == 404
    assert c.post("/firmware/printers/release", json={"port": port}).json()["released"] is True
    assert c.delete(f"/firmware/printers/prints/{file_id}").json()["deleted"] is True
    assert c.delete(f"/firmware/printers/prints/{file_id}").status_code == 404


def test_release_reconnect_reset_and_upload_are_refused_mid_print(
    fake_arduino_cli, fresh_task_runner, scripted_links
):
    c = TestClient(app)
    port = "/dev/ttyFAKE1"
    gate = threading.Event()

    class HeldTransport(ScriptedTransport):
        def write(self, data):
            if data.decode().strip() == "G1 X2":
                gate.wait(5)
            super().write(data)

    scripted_links.factory = HeldTransport
    kept = devices.save_print_file("held.gcode", b"G1 X1\nG1 X2\nG1 X3\n")
    c.post("/firmware/printers/control", json={"port": port, "armed": True})
    assert (
        c.post("/firmware/printers/print", json={"port": port, "file_id": kept.id}).status_code
        == 202
    )
    time.sleep(0.2)
    assert c.post("/firmware/printers/release", json={"port": port}).status_code == 409
    assert c.post("/firmware/printers/reconnect", json={"port": port}).status_code == 409
    assert c.post("/firmware/printers/reset", json={"port": port}).status_code == 409
    r = c.post(
        "/firmware/sketches/footpedal/upload", json={"fqbn": "arduino:avr:uno", "port": port}
    )
    assert r.status_code == 409 and "print holds the port" in r.json()["detail"]
    # Pause needs no latch; resume does; cancel ends it and frees the port.
    c.post("/firmware/printers/control", json={"port": port, "armed": False})
    assert c.post("/firmware/printers/print/pause", json={"port": port}).json()["stage"] == "paused"
    assert c.post("/firmware/printers/print/resume", json={"port": port}).status_code == 409
    c.post("/firmware/printers/control", json={"port": port, "armed": True})
    assert (
        c.post("/firmware/printers/print/resume", json={"port": port}).json()["stage"] == "printing"
    )
    gate.set()
    assert c.post("/firmware/printers/print/cancel", json={"port": port}).json()["stage"] in (
        "cancelling",
        "cancelled",
        "done",
    )
    devices.print_job(port).thread.join(5)
    assert c.get("/firmware/printers/print", params={"port": port}).json()["running"] is False
    assert c.post("/firmware/printers/release", json={"port": port}).status_code == 200


# --- a pin follows the board, not the socket -------------------------------------------


def test_a_pin_by_port_is_kept_as_the_board_and_survives_renumbering(
    fake_arduino_cli, fresh_task_runner, scripted_links, garage, monkeypatch
):
    """Seen on the bench: the printer came back as /dev/ttyUSB0 after a night as
    /dev/ttyUSB1, and the pin made by port name pointed at nothing. A pin is
    kept as the bridge's serial number when it has one, and matches the board
    wherever the kernel puts it; a by-id path or a udev name matches too."""
    c = TestClient(app)
    row = c.put(f"/sites/garage/nodes/{BOARD}/device", json={"identity": "/dev/ttyFAKE1"}).json()
    assert row["identity"] == "FAKESERIAL1" and row["binding_source"] == "manual"
    assert row["device"]["port"] == "/dev/ttyFAKE1"
    # A port with no serial number stays a port.
    row = c.put("/sites/garage/nodes/printer_2/device", json={"identity": "/dev/ttyFAKE0"}).json()
    assert row["identity"] == "/dev/ttyFAKE0"
    c.delete("/sites/garage/nodes/printer_2/device")
    # The board view and the status sync find the pin by the port it is on now.
    assert (
        c.get("/firmware/printers/where", params={"port": "/dev/ttyFAKE1"}).json()["board"]["path"]
        == BOARD
    )
    body = c.get("/firmware/printers/status", params={"port": "/dev/ttyFAKE1"}).json()
    assert body["synced"] and body["synced"][0]["via"] == BOARD

    # Overnight the kernel renumbers: the same bridge is now on /dev/ttyFAKE2.
    from apothecary.firmware import devices

    def renumbered(cli=None, state=None, fresh=False):
        found = list(_real_detected(cli, state, fresh))
        return [
            d.model_copy(update={"port": "/dev/ttyFAKE2"}) if d.port == "/dev/ttyFAKE1" else d
            for d in found
        ]

    _real_detected = devices.detected_devices
    monkeypatch.setattr(devices, "detected_devices", renumbered)
    monkeypatch.setattr(devices, "_SCAN", None)
    rows = c.get("/sites/garage/devices").json()["bindings"]
    row = next(r for r in rows if r["path"] == BOARD)
    assert row["identity"] == "FAKESERIAL1" and row["device"]["port"] == "/dev/ttyFAKE2"
    assert (
        c.get("/firmware/printers/where", params={"port": "/dev/ttyFAKE2"}).json()["board"]["path"]
        == BOARD
    )
    body = c.get("/firmware/printers/status", params={"port": "/dev/ttyFAKE2"}).json()
    assert body["synced"] and body["synced"][0]["via"] == BOARD


def test_a_pin_by_a_path_that_resolves_to_the_port_matches(tmp_path):
    from apothecary.firmware.bindings import same_device
    from apothecary.firmware.models import DeviceInfo, validate_identity

    real = tmp_path / "ttyUSB0"
    real.write_text("")
    link = tmp_path / "ender"
    link.symlink_to(real)
    assert same_device(str(link), str(real))
    assert same_device(str(real), str(real))
    assert not same_device(str(tmp_path / "other"), str(real))
    dev = DeviceInfo(port="/dev/ttyUSB0", serial_number="A106ZTEU")
    assert same_device("a106zteu", "/dev/ttyUSB0", dev) and dev.identity == "A106ZTEU"
    assert not same_device("A106ZTEU", "/dev/ttyUSB0", None)
    assert validate_identity("A106ZTEU") == "A106ZTEU"
    with pytest.raises(ValueError):
        validate_identity("no spaces here")
