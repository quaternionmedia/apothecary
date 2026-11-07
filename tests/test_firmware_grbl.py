"""The GRBL dialect of the machine seam: parsers, the simulated router, identify,
poll, control and query through the devices layer, a cut streamed, the status
the site takes and the evidence kept.

The replies the simulated controller gives follow grbl 1.1's interface document
and Grbl_ESP32's report code, not a recording of the garage's router
(docs/cnc.md says what the bench confirms); the Marlin seam's tests
(test_firmware_gcode.py) run against a recording of a real board.
"""

import threading
import time

import pytest
from click.testing import CliRunner
from fastapi.testclient import TestClient

from apothecary import jobs
from apothecary.api import app, printers_in
from apothecary.cli import cli
from apothecary.evidence import printers as evidence_printers
from apothecary.firmware import devices, gcode, grbl
from apothecary.firmware.models import GRBL, MACHINE_OF, MARLIN, PrinterInfo
from apothecary.firmware.toolchains import PortHeld, ToolchainError

PORT = "/dev/ttyFAKE1"  # the scripted arduino-cli's unmatched board
CONTROLLER = "cnc_router.frame_system.controller"

IDLE = "<Idle|MPos:-200.000,-300.000,-40.000|FS:0,0|WCO:0.000,0.000,0.000>"
RUN = "<Run|WPos:12.500,-3.000,-1.000|Bf:12,120|FS:800,12000|Pn:XZ|Ov:100,90,100|A:S>"
HELD = "<Hold:0|MPos:-10.000,-20.000,-5.000|FS:0,0|WCO:-10.000,-20.000,-5.000>"
BUILD_INFO = [
    "[VER:1.3a.20230715:]",
    "[OPT:VNMPH,35,1024,3]",
    "[MSG:Using machine:AnoleX 4060-Evo Ultra 2]",
    "ok",
]
PARSER_STATE = ["[GC:G1 G54 G17 G21 G90 G94 M3 M9 T0 F800 S12000]", "ok"]


@pytest.fixture
def router_links(monkeypatch):
    """The seam's link registry over the simulated router, its moves instant."""
    monkeypatch.setenv("APOTHECARY_SIMULATED_SPEED", "0")
    links = gcode.PrinterLinks(factory=grbl.SimulatedRouter)
    monkeypatch.setattr(gcode, "_LINKS", links)
    yield links
    links.stop_all()


@pytest.fixture
def garage():
    from apothecary import api as api_module

    api_module._site_store.reset("garage")
    yield api_module._site_store.get("garage")
    api_module._site_store.reset("garage")


# --- parsers ---------------------------------------------------------------------


def test_parse_status_report_reads_each_field_and_computes_the_other_position():
    idle = grbl.parse_status(IDLE)
    assert idle["machine_state"] == "Idle" and idle["substate"] is None
    assert idle["mpos"] == {"x": -200.0, "y": -300.0, "z": -40.0}
    assert idle["wpos"] == {"x": -200.0, "y": -300.0, "z": -40.0}  # WCO is zero
    assert idle["feed"] == 0 and idle["spindle_rpm"] == 0 and idle["pins"] == []
    run = grbl.parse_status(RUN)
    assert run["machine_state"] == "Run" and run["mpos"] is None  # no WCO in this report
    assert run["wpos"] == {"x": 12.5, "y": -3.0, "z": -1.0}
    assert run["buffer"] == {"planner": 12, "rx": 120}
    assert (run["feed"], run["spindle_rpm"]) == (800.0, 12000.0)
    assert run["pins"] == ["X", "Z"] and run["accessories"] == ["S"]
    assert run["overrides"] == {"feed": 100, "rapid": 90, "spindle": 100}
    held = grbl.parse_status(HELD)
    assert held["machine_state"] == "Hold" and held["substate"] == 0
    assert held["wpos"] == {"x": 0.0, "y": 0.0, "z": 0.0}
    assert grbl.parse_status("ok") is None and grbl.is_status_line(IDLE)
    assert [
        grbl.site_state(w) for w in ("Idle", "Run", "Jog", "Home", "Hold", "Door", "Alarm")
    ] == [
        "idle",
        "running",
        "running",
        "running",
        "hold",
        "hold",
        "alarm",
    ]


def test_parse_build_info_parser_state_settings_alarm_and_probe():
    info = grbl.parse_build_info(BUILD_INFO)
    assert info["version"] == "1.3a" and info["build"] == "20230715"
    assert info["options"] == "VNMPH,35,1024,3"
    assert info["machine"] == "AnoleX 4060-Evo Ultra 2"
    classic = grbl.parse_build_info(["[VER:1.1h.20190825:]", "[OPT:V,15,128]", "ok"])
    assert classic["version"] == "1.1h" and classic["machine"] is None
    state = grbl.parse_parser_state(PARSER_STATE)
    assert state["spindle_on"] and state["spindle_direction"] == "cw"
    assert (state["s"], state["f"], state["coordinate_system"]) == (12000.0, 800.0, "G54")
    assert state["units"] == "mm" and state["distance"] == "absolute"
    assert grbl.parse_alarm(["error:9", "ALARM:3", "ok"]) == 3 and grbl.parse_alarm(["ok"]) is None
    assert grbl.alarm_text(3).startswith("reset while in motion")


def test_the_kind_of_machine_follows_the_dialect():
    """A board's kind is read from the dialect it answered in, never kept beside it: a
    record that says otherwise reads as its dialect's kind, and the JSON carries it."""
    assert PrinterInfo(firmware_name="Marlin 2.1").machine == "printer"
    assert PrinterInfo(firmware_name="Grbl 1.3a", dialect=GRBL).machine == "router"
    kept = PrinterInfo(**{"firmware_name": "Grbl 1.3a", "dialect": "grbl", "machine": "printer"})
    assert kept.machine == "router"
    assert PrinterInfo(firmware_name="Grbl 1.3a", dialect=GRBL).model_dump()["machine"] == "router"
    assert (gcode.MACHINE, grbl.MACHINE) == (MACHINE_OF[MARLIN], MACHINE_OF[GRBL])


def test_router_info_names_the_firmware_the_machine_and_the_dialect():
    info = grbl.router_info_from(BUILD_INFO, 115200)
    assert (info.dialect, info.machine) == ("grbl", "router")
    assert info.firmware_name == "Grbl 1.3a" and info.machine_type == "AnoleX 4060-Evo Ultra 2"
    assert info.protocol_version == "20230715" and info.extruder_count == 0
    assert set(info.capabilities) == {"V", "N", "M", "P", "H"}
    classic = grbl.router_info_from(["[VER:1.1h.20190825:]", "[OPT:V,15,128]", "ok"], 115200)
    assert classic.firmware_name == "Grbl 1.1h" and classic.machine_type is None
    # The banner alone names the version, when $I says nothing useful.
    banner = grbl.router_info_from(["ok"], 115200, boot_lines=["Grbl 1.3a ['$' for help]"])
    assert banner.firmware_name == "Grbl 1.3a" and banner.machine_type == "Grbl_ESP32"
    with pytest.raises(ToolchainError, match="not a GRBL controller"):
        grbl.router_info_from(['echo:Unknown command: "$I"', "ok"], 115200)


# --- the allowlists ----------------------------------------------------------------


def test_control_allowlist_normalises_and_bounds():
    for line in (
        "$H",
        "$HZ",
        "$X",
        "$J=G91 G21 X10 F500",
        "$J=G91 G21 X-10 Y10 Z-1.5 F1000",
        "G90",
        "G1 X10 Y20 F800",
        "G0 X0 Y0",
        "G53 G0 Z0",
        "M3 S12000",
        "M5",
        "G10 L20 P1 X0 Y0 Z0",
        "G10 L20 P1 Z0",
        "G38.2 Z-20 F100",
        "hold",
        "resume",
        "reset",
        "jog-cancel",
    ):
        assert grbl.normalise_control(line) == " ".join(line.upper().split())
    for bad, why in (
        ("M3 S30000", "spindle above 24000"),
        ("$J=G91 G21 X700 F500", "beyond 600 mm"),
        ("G1 X10 F9000", "feedrate above 4000"),
        ("G38.2 Z-100 F100", "deeper than 80"),
        ("G38.2 Z-20 F900", "probe feed above 500"),
        ("$110=5000", "not an allowed"),
        ("M4 S100", "not an allowed"),
        ("M112", "not an allowed"),
        ("STATUS", "not an allowed"),
        ("G10 L2 P1 X0", "not an allowed"),
    ):
        with pytest.raises(ValueError, match=why):
            grbl.normalise_control(bad)
    assert grbl.normalise_query("$g") == "$G" and grbl.normalise_query("?") == "?"
    with pytest.raises(ValueError):
        grbl.normalise_query("M503")


def test_the_controller_s_numbers_have_words():
    """An error or alarm number is said in words beside the line and in a refusal."""
    assert grbl.explain("error:15") == "a jog would go past the travel"
    assert grbl.explain("ALARM:3") == "reset while in motion: machine position is lost"
    assert grbl.explain("error:999") == "error 999" and grbl.explain("ok") is None


def test_the_link_objects_in_each_dialect_s_own_words():
    """Marlin's words are the Marlin module's, GRBL's the GRBL module's, and the link
    closes an exchange on either, before a board is identified as speaking one."""
    assert gcode.ERROR_RE.match("Error:checksum mismatch") and gcode.ERROR_RE.match("!! kill")
    assert gcode.ERROR_RE.match("error:20") is None and gcode.ERROR_RE.match("ALARM:3") is None
    assert grbl.OBJECTION_RE in gcode.OBJECTIONS and gcode.ERROR_RE in gcode.OBJECTIONS
    assert grbl.OBJECTION_RE.match("error:20") and grbl.OBJECTION_RE.match("ALARM:3")
    assert grbl.OBJECTION_RE.match("Error:checksum mismatch") is None


def test_a_streamed_file_may_not_carry_settings_tool_changes_or_a_fast_spindle():
    text = "G21 G90\n$110=4000\nM6 T1\nM3 S30000\nM0\nG1 X10 F800\nS12000 M3\nM5\nM30\n"
    total, problems = grbl.check_gcode(text)
    assert total == 9
    assert problems == [
        "line 2: $110=4000 is a controller setting, not a job's to send",
        "line 3: M6 is a tool change: the host streams one tool",
        "line 3: M6 is not a GRBL code: the controller answers error:20 and the cut stops there",
        "line 4: M3 asks for 30000 rpm, above 24000",
        "line 5: M0 stops and waits for a button on the machine",
    ]
    assert grbl.line_timeout("G1 X10 F800") == grbl.JOB_MOVE_TIMEOUT_S
    assert grbl.line_timeout("M3 S12000") == grbl.JOB_LINE_TIMEOUT_S


# --- the simulated router, over a link ---------------------------------------------------


def test_the_simulated_router_is_a_plausible_grbl(router_links):
    link = router_links.open(PORT, 115200)
    info = grbl.identify_router(link)
    assert info.firmware_name == "Grbl 1.3a" and info.machine == "router"
    assert info.machine_type == grbl.SimulatedRouter.MACHINE_NAME
    st = grbl.poll_router(link)
    assert (st.dialect, st.state, st.machine_state) == ("grbl", "idle", "Idle")
    assert st.position == {"x": -200.0, "y": -300.0, "z": -40.0} == st.work_position
    assert st.spindle is not None and not st.spindle.on and st.spindle.rpm == 0
    assert (
        st.alarm is None
        and st.pins == []
        and st.overrides == {"feed": 100, "rapid": 100, "spindle": 100}
    )
    # The spindle: on at a speed, seen in the next report and the parser state.
    assert grbl.control_router(link, "M3 S12000") == ["ok"]
    st = grbl.poll_router(link)
    assert st.spindle.on and st.spindle.rpm == 12000 and st.spindle.target == 12000
    # A jog moves the tool (instantly here: APOTHECARY_SIMULATED_SPEED=0).
    assert grbl.control_router(link, "$J=G91 G21 X10 F500") == ["ok"]
    assert grbl.poll_router(link).position["x"] == -190.0
    # Work zero here: the work position reads zero, the offset is where the tool is.
    assert grbl.control_router(link, "G10 L20 P1 X0 Y0 Z0") == ["ok"]
    st = grbl.poll_router(link)
    assert st.work_position == {"x": 0.0, "y": 0.0, "z": 0.0}
    assert st.work_offset == {"x": -190.0, "y": -300.0, "z": -40.0}
    assert "[G54:-190.000,-300.000,-40.000]" in grbl.query_router(link, "$#")
    # A probe touches the plate 20 mm down and says where.
    assert grbl.control_router(link, "G38.2 Z-25 F100")[0] == "[PRB:-190.000,-300.000,-60.000:1]"
    assert grbl.poll_router(link).position["z"] == -60.0
    # Homing pulls off the switches at the back-right-top corner.
    assert grbl.control_router(link, "$H") == ["ok"]
    assert grbl.poll_router(link).position == {"x": -3.0, "y": -3.0, "z": -3.0}
    # A hold with nothing in motion still holds; a resume lets go.
    grbl.control_router(link, "HOLD")
    assert grbl.poll_router(link).machine_state == "Hold:0"
    grbl.control_router(link, "RESUME")
    assert grbl.poll_router(link).state == "idle"
    # The reset answers with the banner and turns the spindle off; `?` is a query too.
    said = grbl.control_router(link, "RESET")
    assert any(ln.startswith("Grbl 1.3a") for ln in said)
    assert not grbl.poll_router(link).spindle.on
    assert grbl.is_status_line(grbl.query_router(link, "?")[-1])
    # Not this dialect's: Marlin's codes get error:20, which the link raises.
    with pytest.raises(ToolchainError, match="error:20"):
        link.command("M105")
    # A refusal from the controller says the words, and the log keeps them beside the line.
    link.annotate = grbl.explain
    with pytest.raises(ToolchainError, match="error:15 \\(a jog would go past the travel\\)"):
        grbl.control_router(link, "$J=G91 G21 X500 F500")
    noted = [e for e in link.log.since(0)["entries"] if e.get("note")]
    assert noted and noted[-1]["text"] == "error:15"
    assert noted[-1]["note"] == "a jog would go past the travel"


def test_a_move_takes_its_time_and_a_hold_stops_it_where_it_is(router_links, monkeypatch):
    monkeypatch.setenv("APOTHECARY_SIMULATED_SPEED", "0.02")
    link = router_links.open(PORT, 115200)
    # 100 mm at F600 is ten seconds of real time: 0.2 s here.
    assert link.command("G1 X-100 F600") == ["ok"]
    st = grbl.poll_router(link)
    assert st.state == "running" and st.machine_state == "Run"
    grbl.control_router(link, "HOLD")
    held = grbl.poll_router(link)
    assert held.state == "hold" and held.machine_state == "Hold:1"
    time.sleep(0.05)
    assert grbl.poll_router(link).position == held.position  # it stays put
    # A reset in motion is an alarm: position lost, until unlocked or homed.
    grbl.control_router(link, "RESUME")
    said = grbl.control_router(link, "RESET")
    assert "ALARM:3" in said
    st = grbl.poll_router(link)
    assert st.state == "alarm" and st.alarm == 3
    assert st.alarm_text == "reset while in motion: machine position is lost"
    with pytest.raises(ToolchainError, match="error:9"):
        link.command("G1 X-50 F600")
    assert grbl.control_router(link, "$X")[0] == "[MSG:Caution: Unlocked]"
    assert grbl.poll_router(link).state == "idle"


def test_the_simulated_engine_picks_the_router_for_its_ports(monkeypatch):
    monkeypatch.setenv("APOTHECARY_SERIAL_ENGINE", "simulated")
    monkeypatch.setenv("APOTHECARY_SIMULATED_ROUTER", "/dev/ttyFAKE3, /dev/ttyFAKE4")
    assert isinstance(gcode.open_transport("/dev/ttyFAKE3", 115200), grbl.SimulatedRouter)
    assert isinstance(gcode.open_transport("/dev/ttyFAKE4", 115200), grbl.SimulatedRouter)
    assert isinstance(gcode.open_transport("/dev/ttyFAKE1", 115200), gcode.SimulatedPrinter)
    monkeypatch.setenv("APOTHECARY_SIMULATED_ROUTER_STATE", "alarm")
    link = gcode.GcodeLink("/dev/ttyFAKE3", 115200, gcode.open_transport("/dev/ttyFAKE3", 115200))
    booted = link.settle()
    assert booted == ["Grbl 1.3a ['$' for help]", "[MSG:'$H'|'$X' to unlock]"]
    st = grbl.poll_router(link)
    # As a real one powers up with homing enabled: in alarm, and no ALARM line says which.
    assert st.state == "alarm" and st.machine_state == "Alarm" and st.alarm is None
    assert grbl.control_router(link, "$H") == ["ok"]
    assert grbl.poll_router(link).state == "idle"


# --- through the devices layer: identify, poll, control, query ---------------------------


def test_a_port_that_answers_grbl_is_a_router_polled_in_its_dialect(fake_arduino_cli, router_links):
    device = devices.identify_printer(PORT)
    assert device.printer is not None
    assert (device.printer.dialect, device.printer.machine) == ("grbl", "router")
    assert devices.machine_kind(device) == "router" and devices.dialect_of(PORT) == "grbl"
    st = devices.printer_status(PORT)
    assert st.dialect == "grbl" and st.state == "idle" and st.machine_state == "Idle"
    assert router_links.get(PORT).annotate is grbl.explain  # the words ride the link
    assert "$G" in devices.query_codes(PORT) and "M503" not in devices.query_codes(PORT)
    assert "M503" in devices.query_codes(None)
    assert devices.printer_query(PORT, "$G").lines[-1] == "ok"
    with pytest.raises(ValueError, match="not a report-only GRBL query"):
        devices.printer_query(PORT, "M503")
    # The exchanges went in GRBL's dialect: $I to identify, ? and $G to poll, and M115
    # was tried once first, as a Marlin board would answer it.
    log = [e["text"] for e in router_links.log_for(PORT).since(0)["entries"] if e["kind"] == "tx"]
    assert log[0] == "M115" and "$I" in log and "?" in log and "$G" in log
    assert devices.emergency_stop_for(PORT) == "RESET"
    assert devices.is_emergency_stop("reset") and devices.is_emergency_stop("M112")
    assert router_links.close(PORT) is True


def test_control_needs_the_latch_and_the_reset_does_not(fake_arduino_cli, router_links):
    with pytest.raises(gcode.ControlNotArmed):
        devices.printer_control(PORT, "$H")
    with pytest.raises(ValueError, match="spindle above"):
        devices.printer_control(PORT, "M3 S30000")
    router_links.control.arm(PORT)
    assert devices.printer_control(PORT, "$H").lines == ["ok"]
    assert devices.printer_control(PORT, "m3 s8000").command == "M3 S8000"
    assert devices.printer_status(PORT).spindle.on
    # A printer's line is refused on a router once the port is known to be one.
    with pytest.raises(ValueError, match="not an allowed GRBL control"):
        devices.printer_control(PORT, "M104 S200")
    router_links.control.disarm(PORT)
    # The stop needs no latch, and a printer's word for it is the router's soft reset.
    said = devices.printer_control(PORT, "M112")
    assert said.command == "RESET" and any(ln.startswith("Grbl") for ln in said.lines)
    assert not devices.printer_status(PORT).spindle.on


def test_a_cut_streams_and_is_a_job_of_the_router(fake_arduino_cli, router_links):
    text = "G21 G90\nM3 S12000\nG0 X-10 Y-10\nG1 Z-1 F200\nG1 X-50 F800\nG1 Y-50\nG0 Z0\nM5\nM30\n"
    kept = devices.save_print_file("pocket.nc", text.encode(), machine="router")
    assert kept.lines == 9 and kept.problems == []
    with pytest.raises(gcode.ControlNotArmed, match="arm control first"):
        devices.start_print(PORT, kept.id)
    router_links.control.arm(PORT)
    job = devices.start_print(PORT, kept.id)
    assert job.op is jobs.CUT and job.snapshot()["kind"] == "cut"
    job.thread.join(5)
    assert job.stage == "done" and job.error is None
    rec = job.record
    assert rec.kind == "cut" and rec.machine.kind == "router" and rec.outcome == "done"
    assert rec.detail["sent"] == 9 == rec.detail["total"]
    assert rec.detail["firmware"] == "Grbl 1.3a"
    assert [r.id for r in jobs.list_jobs(kind="cut")] == [rec.id]
    log = router_links.log_for(PORT).since(0)["entries"]
    assert any(e["kind"] == "sys" and "cut started: pocket.nc (9 lines)" in e["text"] for e in log)
    assert any(e["kind"] == "sys" and "cut done: pocket.nc, 9/9" in e["text"] for e in log)
    st = devices.printer_status(PORT)
    assert (
        st.job is None and st.state == "idle" and st.position == {"x": -50.0, "y": -50.0, "z": 0.0}
    )


def test_a_cut_holds_when_paused_and_a_cancel_holds_and_resets(
    fake_arduino_cli, router_links, monkeypatch
):
    monkeypatch.setenv("APOTHECARY_SIMULATED_SPEED", "0.2")
    text = "M3 S12000\n" + "G4 P1\n" * 12 + "M5\n"
    kept = devices.save_print_file("dwell.nc", text.encode(), machine="router")
    router_links.control.arm(PORT)
    job = devices.start_print(PORT, kept.id)
    for _ in range(100):
        if job.sent >= 2:
            break
        time.sleep(0.02)
    st = devices.printer_status(PORT)
    # The lines are answered as they are queued, fifteen at a time: the cut's last line
    # may be sent while the controller still runs them (``finishing``).
    assert st.job["kind"] == "cut" and st.state == "running"
    assert st.job["stage"] in ("running", "finishing")
    with pytest.raises(PortHeld, match="a cut holds the port"):
        devices.printer_control(PORT, "$H")
    assert devices.printer_control(PORT, "M3 S9000").lines == ["ok"]  # the spindle stays in reach
    job.pause()
    time.sleep(0.3)
    assert job.stage == "paused"
    held = devices.printer_status(PORT)
    assert held.machine_state.startswith("Hold") and held.state == "hold"  # the controller's word
    sent = job.sent
    time.sleep(0.3)
    assert job.sent == sent  # nothing streams while paused
    assert devices.printer_status(PORT).machine_state.startswith("Hold")
    job.resume()
    time.sleep(0.3)
    assert job.stage in ("running", "finishing") and job.finished is None
    assert not devices.printer_status(PORT).machine_state.startswith("Hold")
    job.cancel()
    job.thread.join(5)
    rec = job.record
    assert rec.outcome == "cancelled" and rec.reason == "cancelled; held and reset, spindle off"
    assert "> HOLD" in rec.log and "> RESET" in rec.log
    st = devices.printer_status(PORT)
    assert st.job is None and not st.spindle.on


def test_a_router_poll_drives_cnc_router_and_is_kept_as_evidence(
    fake_arduino_cli, fresh_task_runner, router_links, garage
):
    c = TestClient(app)
    row = c.put(f"/sites/garage/nodes/{CONTROLLER}/device", json={"identity": PORT}).json()
    assert row["identity"] == "FAKESERIAL1"
    st = c.get("/firmware/printers/status", params={"port": PORT}).json()
    assert st["dialect"] == "grbl" and st["state"] == "idle" and st["machine_state"] == "Idle"
    assert st["synced"] == [
        {
            "site": "garage",
            "path": "cnc_router",
            "via": CONTROLLER,
            "status": "idle",
            "changed": False,
        }
    ]
    assert st["poll"]  # kept in the evidence log
    # A hold is the router's word, and the node takes it.
    c.post("/firmware/printers/control", json={"port": PORT, "armed": True})
    assert (
        c.post("/firmware/printers/command", json={"port": PORT, "command": "HOLD"}).status_code
        == 200
    )
    st = c.get("/firmware/printers/status", params={"port": PORT}).json()
    assert st["state"] == "hold" and st["synced"][0]["status"] == "hold"
    router = next(s for s in garage.children if s.name == "cnc_router")
    assert router.status == "hold"
    assert (
        c.post("/firmware/printers/command", json={"port": PORT, "command": "RESUME"}).status_code
        == 200
    )
    st = c.get("/firmware/printers/status", params={"port": PORT}).json()
    assert st["state"] == "idle" and router.status == "idle"
    # Where it is pinned: the router, with its working area, for the world's marks.
    where = c.get("/firmware/printers/where", params={"port": PORT}).json()
    assert where["board"]["path"] == CONTROLLER and where["printer"]["path"] == "cnc_router"
    assert where["printer"]["build_volume"] == [400.0, 600.0, 80.0]
    assert where["printer"]["build_origin"] == [115.0, 165.0, 100.0]
    # A router is no printer: nothing is sliced or printed on it.
    assert printers_in("garage") == []
    # The queries the page offers for this port are the dialect's.
    codes = {
        q["command"] for q in c.get("/firmware/printers/queries", params={"port": PORT}).json()
    }
    assert "$$" in codes and "M503" not in codes
    # Its observations: the state, the controller's word, both positions, the spindle.
    status = devices.last_statuses()[PORT]
    pin = evidence_printers.Pin("garage", CONTROLLER, "cnc_router", "FAKESERIAL1")
    said = {
        (o.subject, o.property): o
        for o in evidence_printers.observations_of(status, pin, "FAKESERIAL1")
    }
    assert said[("garage:cnc_router", "state")].value == "idle"
    assert said[("garage:cnc_router", "machine_state")].value == "Idle"
    assert said[("garage:cnc_router", "position")].unit == "mm"
    assert said[("garage:cnc_router", "work_position")].value == status.work_position
    assert said[("garage:cnc_router#spindle:main", "rpm")].unit == "rpm"
    assert said[("garage:cnc_router", "pins")].value == []
    assert said[("garage:cnc_router", "state")].origin.by.name == evidence_printers.BY_GRBL
    assert ("garage:cnc_router#heater:bed", "temperature") not in said
    # The Working space opens on it as on a printer: it is listed, and its hour answers.
    watched = c.get("/sites/garage/evidence/printers").json()["printers"]
    assert [m["path"] for m in watched] == ["cnc_router"] and watched[0]["port"] == PORT
    assert c.get("/sites/garage/evidence/printers/cnc_router").json()["port"] == PORT
    c.delete(f"/sites/garage/nodes/{CONTROLLER}/device")


def test_the_cli_reports_a_router(fake_arduino_cli, router_links):
    done = CliRunner().invoke(cli, ["firmware", "printer", PORT, "--query", "$G"])
    assert done.exit_code == 0, done.output
    assert "Grbl 1.3a" in done.output
    assert "controller: Idle" in done.output and "spindle: off" in done.output
    assert "work position: X-200.00 Y-300.00 Z-40.00" in done.output
    assert "> $G" in done.output and "[GC:" in done.output
    refused = CliRunner().invoke(cli, ["firmware", "printer", PORT, "--query", "M9999"])
    assert refused.exit_code != 0


def test_the_realtime_write_queues_behind_an_exchange_unless_told_now(router_links):
    link = router_links.open(PORT, 115200)
    link.time_scale = 1.0  # an exchange that waits seconds for its reply
    gate = threading.Event()

    class Delayed:
        """The simulated router, its reply to `$G` held back until the gate opens."""

        def __init__(self, inner):
            self.inner, self.held = inner, None

        def write(self, data):
            if data.strip() == b"$G" and not gate.is_set():
                self.held = data
                return
            self.inner.write(data)

        def read(self, timeout):
            if self.held is not None and gate.is_set():
                self.inner.write(self.held)
                self.held = None
            return self.inner.read(timeout)

        def pulse_reset(self):
            self.inner.pulse_reset()

        def close(self):
            self.inner.close()

    link._t = Delayed(link._t)
    answered = []
    t = threading.Thread(target=lambda: answered.extend(link.command("$G")))
    t.start()
    for _ in range(100):
        if link._t.held is not None:
            break
        time.sleep(0.01)
    # Told `now`, a hold goes through at once, ahead of the exchange holding the lock,
    # and reads nothing, since the exchange is reading.
    assert grbl.control_router(link, "HOLD") == []
    # Not told `now`, a status report waits its turn, and gives up when told to.
    with pytest.raises(gcode.LinkBusy):
        link.realtime(b"?", until=grbl.STATUS_RE, wait=0.05)
    gate.set()
    t.join(5)
    assert answered[-1] == "ok"
    assert grbl.poll_router(link).machine_state == "Hold:0"
