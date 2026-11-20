"""The GRBL dialect of the machine seam: parsers, the simulated router, identify,
poll, control and query through the devices layer, a cut streamed, the status
the site takes and the evidence kept.

The replies the simulated controller gives follow grbl 1.1's interface document
and Grbl_ESP32's report code, not a recording of the garage's router
(docs/cnc.md says what the bench confirms); the Marlin seam's tests
(test_firmware_gcode.py) run against a recording of a real board.
"""

import dataclasses
import threading
import time
import types

import pytest
from click.testing import CliRunner
from fastapi.testclient import TestClient

from apothecary import jobs, sites
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
    sites.store.reset("garage")
    yield sites.store.get("garage")
    sites.store.reset("garage")


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


def test_the_simulated_router_homes_the_axis_it_is_told_and_no_other(router_links):
    link = router_links.open(PORT, 115200)

    def at():
        return grbl.poll_router(link).position

    assert at() == {"x": -200.0, "y": -300.0, "z": -40.0}
    # Each axis alone: it goes to its switch and pulls off; the others stay put.
    assert grbl.control_router(link, "$HZ") == ["ok"]
    assert at() == {"x": -200.0, "y": -300.0, "z": -3.0}
    assert grbl.control_router(link, "$HX") == ["ok"]
    assert at() == {"x": -3.0, "y": -300.0, "z": -3.0}
    assert grbl.control_router(link, "$HY") == ["ok"]
    assert at() == {"x": -3.0, "y": -3.0, "z": -3.0}
    # A bare $H still homes all three.
    assert grbl.control_router(link, "$J=G91 G21 X-20 Y-20 Z-20 F500") == ["ok"]
    assert grbl.control_router(link, "$H") == ["ok"]
    assert at() == {"x": -3.0, "y": -3.0, "z": -3.0}
    # A word after $H that is no axis is refused.
    with pytest.raises(ToolchainError, match="error:3"):
        link.command("$HA")


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
    monkeypatch.setenv("APOTHECARY_SIMULATED_SPEED", "0")  # its homing instant, as router_links'
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


def test_the_reset_disarms_the_router_it_stops(fake_arduino_cli, router_links):
    router_links.control.arm(PORT)
    devices.printer_control(PORT, "m3 s8000")
    assert devices.printer_control(PORT, "RESET").command == "RESET"
    assert not router_links.control.armed(PORT)
    assert not devices.printer_status(PORT).spindle.on
    with pytest.raises(gcode.ControlNotArmed):
        devices.printer_control(PORT, "$J=G91 G21 X1 F1000")


def test_a_reset_that_fails_still_disarms(fake_arduino_cli, router_links, monkeypatch):
    router_links.control.arm(PORT)
    devices.printer_control(PORT, "$H")
    real = devices.dialect_for

    def fails(link, cmd):
        raise ToolchainError("the port went away")

    monkeypatch.setattr(
        devices,
        "dialect_for",
        lambda port, state=None: dataclasses.replace(real(port, state), control=fails),
    )
    with pytest.raises(ToolchainError, match="went away"):
        devices.printer_control(PORT, "RESET")
    assert not router_links.control.armed(PORT)


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
    # The part it is drawn from, whose table carries Y under a tool standing still there.
    assert where["printer"]["part_ref"] == "anolex_4060_evo_ultra_2"
    assert where["printer"]["bed_moves_y"] == 300.0
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
    # The Workspace opens on it as on a printer: it is listed, and its hour answers.
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


# --- homing: proved before it is asked ---------------------------------------------------


@pytest.fixture
def unproved(router_links):
    """A router's link held to what a real port is: nothing assumed of its switches."""
    link = router_links.open(PORT, 115200)
    grbl.proof_of(link).assumed = False
    return link, link._t


def _press(link, sim, pins):
    """A switch held while a poll reads it, then let go and read again."""
    sim.pins = pins
    assert grbl.poll_router(link).pins == list(pins)
    sim.pins = ""
    grbl.poll_router(link)


def _sent(link):
    return [e["text"] for e in link.log.since(0)["entries"] if e["kind"] == "tx"]


def test_a_simulated_routers_homes_are_held_to_no_proof(router_links):
    link = router_links.open(PORT, 115200)
    assert grbl.proof_of(link).assumed
    assert grbl.control_router(link, "$HZ") == ["ok"]


def test_a_home_is_refused_until_the_axis_has_shown_its_switch_and_which_way_it_goes(unproved):
    link, sim = unproved
    start = grbl.poll_router(link).position
    with pytest.raises(grbl.NotProved) as refusal:
        grbl.control_router(link, "$HZ")
    said = str(refusal.value)
    assert "Z will seek +Z at" in said and "for up to" in said  # the controller's own figures
    assert "limit switch has not been seen" in said and "not been jogged 1 mm toward +Z" in said
    assert "$HZ" not in _sent(link) and grbl.poll_router(link).position == start

    _press(link, sim, "Z")
    with pytest.raises(grbl.NotProved) as refusal:
        grbl.control_router(link, "$HZ")
    assert "limit switch" not in str(refusal.value) and "toward +Z" in str(refusal.value)

    grbl.control_router(link, "$J=G91 G21 Z-1 F1000")  # the other way shows nothing of this one
    grbl.control_router(link, "$J=G91 G21 Z0.5 F1000")  # and half a millimetre is not one
    with pytest.raises(grbl.NotProved):
        grbl.control_router(link, "$HZ")
    grbl.control_router(link, "$J=G91 G21 Z0.5 F1000")  # two halves are
    assert grbl.control_router(link, "$HZ") == ["ok"]
    assert grbl.poll_router(link).position["z"] == -grbl.SimulatedRouter.PULL_OFF


def test_a_switch_still_held_has_not_been_seen_and_another_axis_s_shows_nothing(unproved):
    link, sim = unproved
    grbl.control_router(link, "$J=G91 G21 Z1 F1000")
    sim.pins = "Z"
    grbl.poll_router(link)  # on, and never off: a switch stuck closed, or a pin held high
    with pytest.raises(grbl.NotProved, match="limit switch has not been seen"):
        grbl.control_router(link, "$HZ")
    sim.pins = ""
    grbl.poll_router(link)
    assert grbl.control_router(link, "$HZ") == ["ok"]
    _press(link, sim, "Y0")  # Y's, and an input that is no axis
    grbl.control_router(link, "$J=G91 G21 X1 F1000")
    with pytest.raises(grbl.NotProved, match="X will seek"):
        grbl.control_router(link, "$HX")


def test_the_way_an_axis_must_be_jogged_is_the_way_the_controller_says_it_homes(unproved):
    link, sim = unproved
    sim.settings[23] = 1  # X homes toward its minimum
    _press(link, sim, "X")
    grbl.control_router(link, "$J=G91 G21 X1 F1000")
    with pytest.raises(grbl.NotProved, match=r"X will seek -X.*toward -X"):
        grbl.control_router(link, "$HX")
    grbl.control_router(link, "$J=G91 G21 X-1 F1000")
    assert grbl.control_router(link, "$HX") == ["ok"]
    del sim.settings[23]  # a controller that does not say which way: nothing can be shown
    with pytest.raises(grbl.NotProved, match=r"does not say which way it homes"):
        grbl.control_router(link, "$HX")


def test_home_all_needs_every_axis_and_says_each_that_is_missing(unproved):
    link, sim = unproved
    way = {one["axis"]: one["way"].strip("+") for one in grbl.homing_of(link)}  # "" or "-"
    _press(link, sim, "XZ")
    grbl.control_router(link, f"$J=G91 G21 X{way['X']}1 Z{way['Z']}1 F1000")
    with pytest.raises(grbl.NotProved) as refusal:
        grbl.control_router(link, "$H")
    said = str(refusal.value)
    assert "Y will seek" in said and "X will seek" not in said and "Z will seek" not in said
    _press(link, sim, "Y")
    grbl.control_router(link, f"$J=G91 G21 Y{way['Y']}1 F1000")
    assert grbl.control_router(link, "$H") == ["ok"]


def test_what_a_port_showed_is_gone_when_it_is_opened_again(unproved, router_links):
    link, sim = unproved
    _press(link, sim, "Z")
    grbl.control_router(link, "$J=G91 G21 Z1 F1000")
    assert grbl.homing_of(link, "Z")[0]["switch_seen"] and grbl.homing_of(link, "Z")[0]["jogged"]
    router_links.close(PORT)
    again = router_links.open(PORT, 115200)
    grbl.proof_of(again).assumed = False
    assert not grbl.homing_of(again, "Z")[0]["switch_seen"]
    assert not grbl.homing_of(again, "Z")[0]["jogged"]


def test_a_jog_the_controller_refused_and_a_move_that_is_no_jog_show_nothing(unproved):
    link, sim = unproved
    proof = grbl.proof_of(link)
    proof.jog("$J=G91 G21 Z5 F1000", ["error:15"])
    proof.jog("G0 Z5", ["ok"])
    proof.jog("$J=G90 G21 Z5 F1000", ["ok"])  # to a place, not a way
    assert proof.jogged["Z"] == {"+": 0.0, "-": 0.0}
    proof.jog("$J=G21 G91 Z5 F1000", ["ok"])
    assert proof.jogged["Z"] == {"+": 5.0, "-": 0.0}


def test_a_home_not_proved_is_refused_by_the_route_in_words_and_nothing_is_sent(
    fake_arduino_cli, router_links
):
    client = TestClient(app)
    router_links.control.arm(PORT)
    assert devices.printer_status(PORT).state == "idle"  # the port opened and identified
    link = router_links.get(PORT)
    grbl.proof_of(link).assumed = False
    answer = client.post("/firmware/printers/command", json={"port": PORT, "command": "$HZ"})
    assert 400 <= answer.status_code < 500, answer.text
    assert "home refused: Z will seek" in answer.json()["detail"]
    assert "$HZ" not in _sent(link)
    with pytest.raises(grbl.NotProved):  # and Probe table's own home is the same home
        grbl.probe_table(link)


# --- what stopped a person is in the machine's state ----------------------------------


def test_a_refused_line_is_in_the_status_until_one_goes(fake_arduino_cli, router_links):
    assert devices.printer_status(PORT).refused is None
    with pytest.raises(gcode.ControlNotArmed):
        devices.printer_control(PORT, "$J=G91 G21 X1 F1000")
    said = devices.printer_status(PORT).refused
    assert said["command"] == "$J=G91 G21 X1 F1000" and "not armed" in said["said"] and said["at"]
    router_links.control.arm(PORT)
    with pytest.raises(ValueError, match="spindle above"):
        devices.printer_control(PORT, "M3 S30000")
    assert "spindle above" in devices.printer_status(PORT).refused["said"]
    devices.printer_control(PORT, "$J=G91 G21 X1 F1000")
    assert devices.printer_status(PORT).refused is None
    devices.printer_control(PORT, "M112")  # a stop is never what stopped a person
    assert devices.printer_status(PORT).refused is None


def test_the_boards_own_objection_is_in_the_status_with_what_the_alarm_asks(
    fake_arduino_cli, router_links, monkeypatch
):
    monkeypatch.setenv("APOTHECARY_SIMULATED_ROUTER_STATE", "alarm")
    router_links.control.arm(PORT)
    status = devices.printer_status(PORT)
    assert status.state == "alarm" and len(status.todo) == 1
    assert "nothing moves, a jog included, until Unlock ($X) or a home" in status.todo[0]
    with pytest.raises(ToolchainError):
        devices.printer_control(PORT, "$J=G91 G21 Z1 F1000")  # locked out, as a real one is
    status = devices.printer_status(PORT)
    assert status.refused["command"] == "$J=G91 G21 Z1 F1000" and "error:" in status.refused["said"]
    devices.printer_control(PORT, "$X")
    status = devices.printer_status(PORT)
    assert status.todo == [] and status.refused is None and status.state == "idle"


def test_a_poll_says_each_axis_s_homing_and_what_it_has_shown(fake_arduino_cli, router_links):
    devices.printer_status(PORT)
    link = router_links.get(PORT)
    assert all(one["ready"] for one in devices.printer_status(PORT).homing)  # simulated: assumed
    grbl.proof_of(link).assumed = False
    homing = {one["axis"]: one for one in devices.printer_status(PORT).homing}
    assert set(homing) == {"X", "Y", "Z"} and not any(one["ready"] for one in homing.values())
    assert homing["Z"]["way"] in "+-" and homing["Z"]["seek"] and homing["Z"]["search"]
    _press(link, link._t, "Z")
    router_links.control.arm(PORT)
    devices.printer_control(PORT, f"$J=G91 G21 Z{homing['Z']['way'].strip('+')}1 F1000")
    z = next(one for one in devices.printer_status(PORT).homing if one["axis"] == "Z")
    assert z["switch_seen"] and z["jogged"] and z["ready"]
    assert _sent(link).count("$$") == 1  # the settings are asked for once, not at every poll


# --- the touch plate: Z zero from a touch, called the plate's thickness -----------------


def test_probe_z_to_plate_calls_the_touch_the_plates_thickness_and_lifts_off(
    fake_arduino_cli, router_links
):
    router_links.control.arm(PORT)
    before = devices.printer_status(PORT)
    said = devices.printer_control(PORT, "probe-plate z19.08 d50 f100").lines
    assert any(line.endswith(":1]") and line.startswith("[PRB:") for line in said)
    after = devices.printer_status(PORT)
    plate_top = before.position["z"] - grbl.SimulatedRouter.PLATE
    assert after.position["z"] == pytest.approx(plate_top + grbl.PLATE_RETRACT_MM)
    # Work Z is the plate's thickness at the touch, so 5 mm above it after the lift.
    assert after.work_position["z"] == pytest.approx(19.08 + grbl.PLATE_RETRACT_MM)
    assert "G90" in " ".join(after.raw)  # and the parser is back in absolute moves
    sent = _sent(router_links.get(PORT))
    assert "G10 L20 P1 Z19.08" in sent and not any(line.startswith("G92") for line in sent)


def test_a_probe_that_touches_nothing_sets_no_zero_and_says_so(fake_arduino_cli, router_links):
    router_links.control.arm(PORT)
    offset = devices.printer_status(PORT).work_offset
    with pytest.raises(ToolchainError, match="touched nothing within 10 mm, and no zero was set"):
        devices.printer_control(PORT, "PROBE-PLATE Z19.08 D10 F100")  # the plate is 20 mm down
    status = devices.printer_status(PORT)
    assert status.work_offset == offset and status.state == "alarm"
    assert "G10 L20 P1 Z19.08" not in _sent(router_links.get(PORT))
    assert "touched nothing" in status.refused["said"]


def test_the_plate_probe_is_bounded_and_needs_the_latch(fake_arduino_cli, router_links):
    with pytest.raises(gcode.ControlNotArmed):
        devices.printer_control(PORT, "PROBE-PLATE Z19 D50 F100")
    router_links.control.arm(PORT)
    for line, why in (
        ("PROBE-PLATE Z60 D50 F100", "a plate of 60 mm"),
        ("PROBE-PLATE Z19 D90 F100", "probe deeper than"),
        ("PROBE-PLATE Z19 D50 F900", "probe feed above"),
    ):
        with pytest.raises(ValueError, match=why):
            devices.printer_control(PORT, line)
    with pytest.raises(ValueError, match="not an allowed GRBL control"):
        devices.printer_control(PORT, "PROBE-PLATE Z19 D50 F100 G92")


def test_a_plates_thickness_is_the_makers_nominal_until_one_is_measured_and_kept(
    fake_arduino_cli, router_links
):
    client = TestClient(app)
    first = client.get("/firmware/printers/plate", params={"port": PORT}).json()
    assert (first["thickness_mm"], first["measured"]) == (grbl.PLATE_NOMINAL_MM, False)
    assert "manual.json" in first["source"]
    kept = client.put("/firmware/printers/plate", json={"port": PORT, "thickness_mm": 19.08})
    assert kept.status_code == 200 and kept.json()["measured"] is True
    again = client.get("/firmware/printers/plate", params={"port": PORT}).json()
    assert again["thickness_mm"] == 19.08
    for wrong in (0, 51):
        refused = client.put("/firmware/printers/plate", json={"port": PORT, "thickness_mm": wrong})
        assert refused.status_code == 422


def test_probe_z_goes_down_its_depth_wherever_the_work_zero_is(fake_arduino_cli, router_links):
    """As on the bench: the tool 100 mm below the work zero and Probe Z asked for 3 mm. In
    absolute moves that is work Z -3, 97 mm up; it is sent as a distance, and goes down."""
    router_links.control.arm(PORT)
    start = devices.printer_status(PORT).position["z"]
    sim = router_links.get(PORT)._t
    sim.wco["z"] = start + 100.0  # the work zero 100 mm above the tool
    assert devices.printer_status(PORT).work_position["z"] == pytest.approx(-100.0)
    with pytest.raises(
        ToolchainError, match="ALARM:5"
    ):  # nothing within 3 mm: the plate is 20 down
        devices.printer_control(PORT, "G38.2 Z-3 F100")
    assert devices.printer_status(PORT).position["z"] == pytest.approx(start - 3.0)  # down, not up
    devices.printer_control(PORT, "$X")
    said = devices.printer_control(PORT, "G38.2 Z-25 F100").lines
    assert any(line.startswith("[PRB:") and line.endswith(":1]") for line in said)
    after = devices.printer_status(PORT)
    assert after.position["z"] == pytest.approx(start - 3.0 - grbl.SimulatedRouter.PLATE)
    assert "G90" in " ".join(after.raw)
    sent = _sent(router_links.get(PORT))
    at = sent.index("G38.2 Z-3.00 F100")
    assert sent[at - 1] == "G91" and sent[at + 1] == "G90"


def test_a_touch_is_read_from_a_controller_that_reports_a_fourth_axis(
    fake_arduino_cli, router_links, monkeypatch
):
    """The AnoleX's Grbl_ESP32 answers a probe with four coordinates; the line is the
    bench's own. Read as three, the touch was no touch, and Probe Z to plate set nothing."""
    said = ["[PRB:168.074,-126.100,-78.175,0.000:1]", "ok"]
    assert grbl.parse_probe(said) == {"x": 168.074, "y": -126.1, "z": -78.175, "touched": True}
    assert grbl.parse_probe(["[PRB:0.000,0.000,-5.000,0.000:0]"])["touched"] is False
    router_links.control.arm(PORT)
    devices.printer_status(PORT)
    sim = router_links.get(PORT)._t
    three = sim._reply

    def four(cmd):
        return [
            line.replace(":1]", ",0.000:1]") if line.startswith("[PRB:") else line
            for line in three(cmd)
        ]

    monkeypatch.setattr(sim, "_reply", four)
    lines = devices.printer_control(PORT, "PROBE-PLATE Z19.08 D50 F100").lines
    assert any(line.endswith(",0.000:1]") for line in lines)
    assert "G10 L20 P1 Z19.08" in _sent(router_links.get(PORT))


def test_the_work_position_is_known_between_the_reports_that_carry_the_offset():
    """As the AnoleX reports: the offset in one report of ten, the machine position in all.
    The bench's lines, a fourth axis and all."""
    link = types.SimpleNamespace()
    bare = grbl.parse_status("<Idle|MPos:168.074,-127.100,-68.765,0.000|FS:0,0|Pn:0>")
    assert grbl.with_offset(link, dict(bare))["wpos"] is None  # no offset given yet
    carrying = grbl.parse_status(
        "<Idle|MPos:168.074,-127.100,-68.765,0.000|FS:0,0|Pn:0|WCO:168.074,-126.100,-73.265,0.000>"
    )
    assert grbl.with_offset(link, carrying)["wpos"] == {"x": 0.0, "y": -1.0, "z": 4.5}
    after = grbl.with_offset(link, dict(bare))
    assert after["wpos"] == {"x": 0.0, "y": -1.0, "z": 4.5}
    assert after["wco"] == {"x": 168.074, "y": -126.1, "z": -73.265}
    moved = grbl.parse_status("<Idle|MPos:170.074,-127.100,-68.765,0.000|FS:0,0|Pn:0>")
    assert grbl.with_offset(link, moved)["wpos"]["x"] == 2.0


# --- where the tool is in the machine's volume -------------------------------------------


def test_an_axis_is_counted_the_way_its_controller_homes_it():
    """The AnoleX's own settings and a homed position: X homes to its minimum and counts
    up from it, Y and Z home to their maximum and count down from it."""
    anolex = {23: 1, 130: 400.0, 131: 600.0, 132: 130.0}
    homed = {"x": 0.9, "y": -1.1, "z": -1.1}
    assert grbl.in_volume(homed, anolex) == {"x": 0.9, "y": 598.9, "z": 128.9}
    at_work = {"x": 168.074, "y": -126.1, "z": -73.266}
    assert grbl.in_volume(at_work, anolex) == {"x": 168.074, "y": 473.9, "z": 56.734}
    every_axis_from_its_maximum = {**anolex, 23: 0}
    assert grbl.in_volume(homed, every_axis_from_its_maximum)["x"] == 400.9
    assert grbl.in_volume(homed, None) is None and grbl.in_volume(None, anolex) is None
    assert grbl.in_volume(homed, {23: 1, 130: 400.0}) is None  # a travel it does not say


def test_a_poll_says_where_the_tool_and_the_work_zero_stand_in_the_volume(
    fake_arduino_cli, router_links
):
    status = devices.printer_status(PORT)
    # The simulated router homes every axis to its maximum, and starts mid-table.
    assert status.travel == {"x": 400.0, "y": 600.0, "z": 80.0}
    assert status.tool_position == {
        axis: status.position[axis] + status.travel[axis] for axis in "xyz"
    }
    assert status.work_origin == {
        axis: status.work_offset[axis] + status.travel[axis] for axis in "xyz"
    }


def test_a_cut_paused_while_it_waits_for_the_planner_sends_every_line(
    fake_arduino_cli, router_links, monkeypatch
):
    """A pause that lands while a line waits for room in the planner keeps that line:
    resumed, the cut sends it, then the rest."""
    moves = [f"G1 X-{n} F800" for n in range(10, 60, 10)]
    kept = devices.save_print_file("row.nc", ("\n".join(moves) + "\n").encode(), machine="router")
    router_links.control.arm(PORT)
    held: list = []

    def wait(self, link, cmd, abandoned):
        if cmd == moves[2] and not held:
            held.append(cmd)
            job.pause()
            return False  # as the room says when the job is paused meanwhile
        return True

    monkeypatch.setattr(grbl.PlannerRoom, "wait", wait)
    job = devices.start_print(PORT, kept.id)
    for _ in range(200):
        if job.stage == "paused":
            break
        time.sleep(0.01)
    assert job.stage == "paused" and held == [moves[2]]
    job.resume()
    job.thread.join(5)
    rec = job.record
    assert rec.outcome == "done" and rec.detail["sent"] == len(moves)
    assert [line for line in rec.log if line.startswith("> G1")] == [f"> {m}" for m in moves]


def test_a_cut_paused_and_resumed_while_it_waits_for_the_planner_sends_every_line(
    fake_arduino_cli, router_links, monkeypatch
):
    """A pause and a resume that both land while a line waits for room -- a person's two
    presses, or a resume read back before the wait gives up -- keep that line too: the
    wait gave up for the pause, not for want of room."""
    moves = [f"G1 X-{n} F800" for n in range(10, 60, 10)]
    kept = devices.save_print_file("row.nc", ("\n".join(moves) + "\n").encode(), machine="router")
    router_links.control.arm(PORT)
    held: list = []

    def wait(self, link, cmd, abandoned):
        if cmd == moves[2] and not held:
            held.append(cmd)
            job = abandoned.__self__  # the cut whose wait this is
            job.pause()
            job.resume()
            return False  # as the room said when the pause landed
        return True

    monkeypatch.setattr(grbl.PlannerRoom, "wait", wait)
    job = devices.start_print(PORT, kept.id)
    job.thread.join(5)
    rec = job.record
    assert held == [moves[2]]
    assert rec.outcome == "done" and rec.detail["sent"] == len(moves), rec.reason
    assert [line for line in rec.log if line.startswith("> G1")] == [f"> {m}" for m in moves]


def test_a_cut_whose_planner_never_has_room_fails_and_is_held_and_reset(
    fake_arduino_cli, router_links, monkeypatch
):
    """A line the planner had no room for within a move's time ends the cut as failed,
    held and reset; it is never left out and the rest sent."""
    kept = devices.save_print_file("row.nc", b"G1 X-10 F800\nG1 X-20\nG1 X-30\n", machine="router")
    router_links.control.arm(PORT)
    monkeypatch.setattr(grbl.PlannerRoom, "wait", lambda self, link, cmd, gone: cmd != "G1 X-20")
    job = devices.start_print(PORT, kept.id)
    job.thread.join(5)
    rec = job.record
    assert rec.outcome == "failed" and "no room" in rec.reason and "G1 X-20" in rec.reason
    assert rec.detail["sent"] == 1 and "> G1 X-30" not in rec.log
    assert "> HOLD" in rec.log and "> RESET" in rec.log


@pytest.mark.parametrize(
    "ends, said",
    [("Alarm", "in alarm"), ("Run", "still running")],
)
def test_a_cut_that_ends_in_alarm_or_never_idles_is_not_recorded_done(
    fake_arduino_cli, router_links, monkeypatch, ends, said
):
    """A cut is done when its controller is idle again: one that ends in alarm, or is
    still running when a move's time has run out, failed, and is held and reset."""
    kept = devices.save_print_file("row.nc", b"M3 S9000\nG1 X-10 F800\nM5\n", machine="router")
    router_links.control.arm(PORT)
    real = grbl.report

    def report(link, *a, **kw):
        status, lines = real(link, *a, **kw)
        finishing = devices.print_job(PORT) and devices.print_job(PORT).stage == "finishing"
        return ({**status, "machine_state": ends} if finishing else status), lines

    job = devices.start_print(PORT, kept.id)
    monkeypatch.setattr(grbl, "report", report)
    monkeypatch.setattr(grbl, "JOB_MOVE_TIMEOUT_S", 0.3)
    job.thread.join(5)
    rec = job.record
    assert rec.outcome == "failed" and said in rec.reason
    assert "> HOLD" in rec.log and "> RESET" in rec.log


def test_a_cut_that_is_done_leaves_the_spindle_off(fake_arduino_cli, router_links):
    """A file that never says M5 does not leave the spindle turning once it is done."""
    kept = devices.save_print_file("row.nc", b"M3 S9000\nG1 X-10 F800\n", machine="router")
    router_links.control.arm(PORT)
    job = devices.start_print(PORT, kept.id)
    job.thread.join(5)
    assert job.record.outcome == "done" and "> M5" in job.record.log
    assert not devices.printer_status(PORT).spindle.on


# --- what a router is left doing: off switches, holds told to the cut, where the tool is --


def test_a_routers_off_switches_go_with_the_latch_down(fake_arduino_cli, router_links):
    """The spindle off, a hold and a jog cancelled go unarmed and arm nothing; what
    turns or moves is refused."""
    for line in ("M5", "HOLD", "JOG-CANCEL"):
        assert devices.printer_control(PORT, line).command == line
        assert not router_links.control.armed(PORT)
    for line in ("M3 S9000", "RESUME", "$X", "$J=G91 G21 X1 F500"):
        with pytest.raises(gcode.ControlNotArmed):
            devices.printer_control(PORT, line)


def test_a_hold_typed_at_a_cut_is_the_cuts_pause_and_a_resume_its_resume(
    fake_arduino_cli, router_links, monkeypatch
):
    """HOLD and RESUME sent as control lines while a cut streams are told to the cut:
    it stops feeding a held controller, and feeds again once it runs."""
    monkeypatch.setenv("APOTHECARY_SIMULATED_SPEED", "0.2")
    kept = devices.save_print_file("dwell.nc", ("G4 P1\n" * 30).encode(), machine="router")
    router_links.control.arm(PORT)
    job = devices.start_print(PORT, kept.id)
    for _ in range(100):
        if job.sent >= 2:
            break
        time.sleep(0.02)
    devices.printer_control(PORT, "HOLD")
    assert job.stage == "paused"
    assert devices.printer_status(PORT).machine_state.startswith("Hold")
    sent = job.sent
    time.sleep(0.3)
    assert job.sent == sent
    devices.printer_control(PORT, "RESUME")
    assert job.stage in ("running", "finishing")
    time.sleep(0.3)
    assert not devices.printer_status(PORT).machine_state.startswith("Hold")
    job.cancel()
    job.thread.join(5)


def test_a_cut_needs_the_tool_placed_since_the_port_opened_or_the_controller_restarted(
    fake_arduino_cli, router_links, monkeypatch
):
    """A cut is refused until each axis has been homed or given a work zero on this
    port; a banner nothing here asked for, or a reset in motion, takes that away, and
    this server's own reset of an idle controller does not."""
    monkeypatch.setenv(grbl.UNPROVED_ENV, "1")
    kept = devices.save_print_file("row.nc", b"G1 X-10 F800\nM5\n", machine="router")
    router_links.control.arm(PORT)
    with pytest.raises(ValueError, match="X, Y, Z have been neither homed nor given a work zero"):
        devices.start_print(PORT, kept.id)
    st = devices.printer_status(PORT)
    assert any(
        line.startswith("No cut yet: X, Y, Z") and "port was opened" in line for line in st.todo
    )
    devices.printer_control(PORT, "G10 L20 P1 X0 Y0")
    with pytest.raises(ValueError, match="Z has been neither homed"):
        devices.start_print(PORT, kept.id)
    devices.printer_control(PORT, "G10 L20 P1 Z0")
    assert not any(line.startswith("No cut yet") for line in devices.printer_status(PORT).todo)
    job = devices.start_print(PORT, kept.id)
    job.thread.join(5)
    assert job.record.outcome == "done"
    # This server's own reset, of a controller standing still: the place is kept.
    devices.printer_control(PORT, "RESET")
    router_links.control.arm(PORT)
    job = devices.start_print(PORT, kept.id)
    job.thread.join(5)
    assert job.record.outcome == "done"
    # A banner nobody asked for: its power was cycled, and it knows nothing.
    link = router_links.get(PORT)
    monkeypatch.setattr(link, "_asked_reset", float("-inf"))
    link._t._pending += b"Grbl 1.3a ['$' for help]\n"
    st = devices.printer_status(PORT)
    assert any("its controller restarted" in line for line in st.todo)
    with pytest.raises(ValueError, match="since its controller restarted"):
        devices.start_print(PORT, kept.id)
    # Reset while moving: the controller says so itself, and is believed.
    devices.printer_control(PORT, "G10 L20 P1 X0 Y0 Z0")
    link.alarm = "ALARM:3"
    with pytest.raises(ValueError, match="reset while moving"):
        devices.start_print(PORT, kept.id)


def test_a_cut_a_dead_server_left_running_has_its_spindle_turned_off_when_idle(
    fake_arduino_cli, router_links
):
    from datetime import datetime, timezone

    devices.printer_status(PORT)  # identified, and kept as a router
    router_links.close(PORT)
    started = datetime.now(timezone.utc)
    lost = jobs.begin(
        jobs.Job(
            id=jobs.new_id(started, PORT),
            kind="cut",
            machine=jobs.JobMachine(kind="router", port=PORT, identity="FAKESERIAL1"),
            input=jobs.JobInput(name="lost.nc", size=1, sha256="0" * 64, file_id="x"),
            started_at=started,
        ),
        live=lambda: None,
    )
    jobs._LIVE.pop(lost.id)
    devices.printer_status(PORT)
    kept = jobs.get(lost.id)
    assert kept.outcome == "failed" and "the spindle was turned off (M5)" in kept.reason
    log = router_links.log_for(PORT).since(0)["entries"]
    assert any(e["kind"] == "tx" and e["text"] == "M5" and e["origin"] == "cut" for e in log)


def test_a_stopping_server_holds_and_resets_a_router_under_a_table_map(
    fake_arduino_cli, router_links
):
    """A table map stopped with the server sends no further point: the router is held
    and reset under it, and the map ends failed."""
    gate = threading.Event()

    class SlowProbe(grbl.SimulatedRouter):
        def write(self, data):
            if b"G38.2" in data:
                gate.wait(5)  # the first probe is on its way down
            super().write(data)

    router_links.factory = SlowProbe
    router_links.control.arm(PORT)
    job = devices.start_leveling(PORT, probe=True)
    for _ in range(500):
        if job.stage == "probing":
            break
        time.sleep(0.01)
    assert job.stage == "probing"
    said: list = []
    stopping = threading.Thread(target=lambda: said.extend(devices.stop_jobs(timeout=10)))
    stopping.start()
    time.sleep(0.1)
    gate.set()
    stopping.join(15)
    assert job.finished is not None and job.error and "stopped" in job.error
    assert said == [f"{PORT}: a table map stopped with the server, and made safe"]
    log = [e["text"] for e in router_links.log_for(PORT).since(0)["entries"] if e["kind"] == "tx"]
    assert "HOLD" in log and log.count("RESET") == 1
    assert [line for line in log if line.startswith("G53 G0 X")][1:] == []  # the first point only


def _tx_since(links, since):
    return [e["text"] for e in links.log_for(PORT).since(0)["entries"] if e["kind"] == "tx"][since:]


def test_a_poll_while_a_cut_streams_is_the_report_alone_and_holds_the_programmed_speed(
    fake_arduino_cli, router_links
):
    devices.identify_printer(PORT)
    router_links.control.arm(PORT)
    assert devices.printer_control(PORT, "M3 S12000")
    before = len(_tx_since(router_links, 0))
    idle = devices.printer_status(PORT)
    assert idle.spindle.target == 12000 and idle.held == {}
    link = router_links.get(PORT)
    seen = len(_tx_since(router_links, 0))
    assert "$G" in _tx_since(router_links, before)  # an idle poll asks for the parser state
    # Polled mid-cut, the poll is `?` alone; the programmed speed is the last one read.
    streaming = grbl.poll_router(link, streaming=True)
    assert _tx_since(router_links, seen) == ["?"]
    assert streaming.spindle.target == 12000 and streaming.spindle.rpm == 12000
    assert streaming.position == idle.position and streaming.pins == idle.pins
    devices._hold_unread(streaming, idle)
    assert streaming.held == {"spindle.target": idle.polled_at}
    # The first poll after is a full one.
    after = grbl.poll_router(link)
    assert _tx_since(router_links, seen)[-2:] == ["?", "$G"] and after.spindle.target == 12000


def test_a_cut_polled_between_its_lines_sends_no_parser_state_request(
    fake_arduino_cli, router_links, monkeypatch
):
    monkeypatch.setenv("APOTHECARY_SIMULATED_SPEED", "0.05")  # a two-second cut, polled throughout
    devices.identify_printer(PORT)
    full = devices.printer_status(PORT)
    kept = devices.save_print_file(
        "dw.nc", ("M3 S9000\n" + "G4 P1\n" * 40 + "M5\n").encode(), "router"
    )
    router_links.control.arm(PORT)
    seen = len(_tx_since(router_links, 0))
    job = devices.start_print(PORT, kept.id)
    during = []
    while job.thread.is_alive():
        during.append(devices.printer_status(PORT))
        time.sleep(0.02)
    job.thread.join(10)
    cut = [s for s in during if s.job is not None and s.raw]
    sent = _tx_since(router_links, seen)
    assert cut and "?" in sent and "$G" not in sent
    assert all(set(s.held) <= {"spindle.target"} for s in cut)
    assert devices.printer_status(PORT).held == {}
    assert full.job is None
