"""A kept file is for one kind of machine, and is sent to that kind alone.

A printer's file on a router homes it with ``G28`` and waits out its millisecond
dwells as seconds; a router's on a printer drives the nozzle into the bed. So a kept
file says which kind of machine it was kept for -- Choose File the Machine's kind, a
slice a printer, a toolpath a router -- and a stream refuses any other before
anything is sent. A file kept for a router is checked in GRBL's terms as well.
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from apothecary.api import app
from apothecary.cam import service as cam
from apothecary.cam.models import CutFor
from apothecary.firmware import devices, gcode, grbl

PORT = "/dev/ttyFAKE1"  # the scripted arduino-cli's unmatched board
DRY_RUN = (Path(__file__).parents[1] / "docs" / "validation" / "dry-run-square.gcode").read_bytes()
A_CUT = b"G21 G90\nM3 S12000\nG4 P2\nG0 X-10 Y-10\nG1 Z-1 F200\nG1 X-50 F800\nG0 Z0\nM5\nM30\n"


def _a_machine(monkeypatch, simulated):
    """The simulated board on PORT, identified as a Machine's first poll does, armed."""
    monkeypatch.setenv("APOTHECARY_SIMULATED_SPEED", "0")
    links = gcode.PrinterLinks(factory=simulated)
    monkeypatch.setattr(gcode, "_LINKS", links)
    devices.printer_status(PORT)
    links.control.arm(PORT)
    return links


def _sent(links):
    return [e["text"] for e in links.log_for(PORT).since(0)["entries"] if e["kind"] == "tx"]


def test_a_printer_s_file_is_never_sent_to_a_router(fake_arduino_cli, monkeypatch):
    """The bench's own dry run, kept for the printer it was written for."""
    links = _a_machine(monkeypatch, grbl.SimulatedRouter)
    kept = devices.save_print_file("dry-run-square.gcode", DRY_RUN, machine="printer")
    assert kept.problems == []
    with pytest.raises(ValueError, match="was kept for a printer, and .* holds a router"):
        devices.start_print(PORT, kept.id)
    assert "G28" not in _sent(links) and devices.print_job(PORT) is None
    links.stop_all()


def test_a_router_s_file_is_never_sent_to_a_printer(fake_arduino_cli, monkeypatch):
    links = _a_machine(monkeypatch, gcode.SimulatedPrinter)
    kept = devices.save_print_file("pocket.nc", A_CUT, machine="router")
    assert kept.problems == []
    with pytest.raises(ValueError, match="was kept for a router, and .* holds a printer"):
        devices.start_print(PORT, kept.id)
    assert "M3 S12000" not in _sent(links) and devices.print_job(PORT) is None
    links.stop_all()


@pytest.mark.parametrize("simulated", [gcode.SimulatedPrinter, grbl.SimulatedRouter])
def test_a_file_kept_for_no_kind_is_sent_to_none(fake_arduino_cli, monkeypatch, simulated):
    links = _a_machine(monkeypatch, simulated)
    kept = devices.save_print_file("square.gcode", b"G90\nG1 X10 F600\n")
    assert kept.machine is None
    with pytest.raises(ValueError, match="says no kind of machine it is for: choose it again"):
        devices.start_print(PORT, kept.id)
    links.stop_all()


def test_a_board_that_has_not_said_what_it_is_is_sent_no_file(fake_arduino_cli, monkeypatch):
    monkeypatch.setenv("APOTHECARY_SIMULATED_SPEED", "0")
    links = gcode.PrinterLinks(factory=gcode.SimulatedPrinter)
    monkeypatch.setattr(gcode, "_LINKS", links)
    links.open(PORT, 115200)  # held, and never asked what it is
    links.control.arm(PORT)
    kept = devices.save_print_file("square.gcode", b"G1 X1 F100\n", machine="printer")
    with pytest.raises(ValueError, match="has not said what kind of machine it drives"):
        devices.start_print(PORT, kept.id)
    links.stop_all()


def test_a_file_is_sent_to_the_kind_it_was_kept_for(fake_arduino_cli, monkeypatch):
    links = _a_machine(monkeypatch, grbl.SimulatedRouter)
    kept = devices.save_print_file("pocket.nc", A_CUT, machine="router")
    job = devices.start_print(PORT, kept.id)
    job.thread.join(10)
    assert job.stage == "done", job.error
    links.stop_all()


def test_a_router_s_file_is_checked_in_grbl_s_terms():
    _, problems = gcode.check_gcode(DRY_RUN.decode(), "router")
    dwells = [p for p in problems if "G4 P500 dwells 500 s on GRBL, whose P is seconds" in p]
    assert len(dwells) == DRY_RUN.decode().count("G4 P500")
    assert any("M117 is not a GRBL code" in p for p in problems)
    assert any("M84 is not a GRBL code" in p for p in problems)
    assert gcode.check_gcode(DRY_RUN.decode(), "printer")[1] == []
    assert gcode.check_gcode(A_CUT.decode(), "router")[1] == []
    _, odd = gcode.check_gcode("G29\nG04 P90\nM03 S1000\nG04 P30\n", "router")
    assert odd == [
        "line 1: G29 is a printer's bed probe, not a GRBL code",
        "line 2: G04 P90 dwells 90 s on GRBL, whose P is seconds; a printer's file counts it in milliseconds",
    ]


def test_the_app_s_own_toolpath_is_kept_for_the_router_and_checks_clean(fake_arduino_cli):
    record = cam.cut_into("router_coupon", CutFor(name="cnc_router"))
    kept = devices.print_file(record.file_id)
    assert kept.machine == "router" and kept.problems == []


def test_a_file_a_slice_or_a_toolpath_made_before_files_said_their_kind_says_it(
    fake_arduino_cli,
):
    for folder, kind in (("slices", "printer"), ("cuts", "router")):
        kept = devices.save_print_file(f"{kind}.gcode", b"G1 X1 F100\n")
        (devices.state_dir() / folder).mkdir(exist_ok=True)
        (devices.state_dir() / folder / f"{kept.id}.json").write_text("{}")
        assert devices.print_file(kept.id).machine == kind
        assert {f.id: f.machine for f in devices.print_files()}[kept.id] == kind


def test_choose_file_keeps_a_file_for_the_machine_it_was_chosen_in(fake_arduino_cli):
    c = TestClient(app)
    cut = c.post(
        "/firmware/printers/prints",
        params={"name": "pocket.nc", "machine": "router"},
        content=A_CUT,
    )
    assert (
        cut.status_code == 201
        and cut.json()["machine"] == "router"
        and cut.json()["problems"] == []
    )
    dry = c.post(
        "/firmware/printers/prints",
        params={"name": "dry.gcode", "machine": "router"},
        content=DRY_RUN,
    )
    assert any("M117 is not a GRBL code" in p for p in dry.json()["problems"])
    odd = c.post(
        "/firmware/printers/prints",
        params={"name": "x.gcode", "machine": "lathe"},
        content=b"G1 X1\n",
    )
    assert odd.status_code == 422
