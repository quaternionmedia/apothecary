"""A kept file is for one kind of machine, and is sent to that kind alone.

A printer's file on a router homes it with ``G28`` and waits out its millisecond
dwells as seconds; a router's on a printer drives the nozzle into the bed. So a kept
file says which kind of machine it was kept for -- Choose File the Machine's kind, a
slice a printer, a toolpath a router -- and a stream refuses any other before
anything is sent. A file kept for a router is checked in GRBL's terms as well.
"""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from apothecary import machine_plans
from apothecary.api import app
from apothecary.cam import service as cam
from apothecary.cam.models import CutFor
from apothecary.firmware import devices, dialects, gcode, grbl
from apothecary.firmware.models import PrintFile
from apothecary.slicer import service as slicer
from apothecary.state_folder import state_dir

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


def _a_description_that_says_no_kind(how: str) -> str:
    """A file kept for a printer, its description then saying no kind of machine: the
    word left out, or null. Its id."""
    kept = devices.save_print_file(f"{how}.gcode", b"G90\nG1 X10 F600\n", machine="printer")
    described = devices.prints_dir() / f"{kept.id}.json"
    said = json.loads(described.read_text(encoding="utf-8"))
    if how == "left-out":
        del said["machine"]
    else:
        said["machine"] = None
    described.write_text(json.dumps(said), encoding="utf-8")
    return kept.id


@pytest.mark.parametrize("how", ["left-out", "null"])
def test_a_description_that_says_no_kind_of_machine_is_no_kept_file(
    fake_arduino_cli, monkeypatch, how
):
    """A kept file says the kind of machine it was kept for. A description in the files'
    folder that does not is no kept file, as one that does not parse is none: not
    listed, not found by its id, not previewed, not planned and not sent; a slice's or
    a cut's record beside it says nothing of its kind."""
    links = _a_machine(monkeypatch, gcode.SimulatedPrinter)
    file_id = _a_description_that_says_no_kind(how)
    for folder in ("slices", "cuts"):
        (state_dir() / folder).mkdir(exist_ok=True)
        (state_dir() / folder / f"{file_id}.json").write_text("{}")
    assert (devices.prints_dir() / f"{file_id}.gcode").is_file()
    assert devices.print_files() == [] and devices.print_file(file_id) is None
    c = TestClient(app)
    assert c.get("/firmware/printers/prints").json() == []
    preview = c.get(f"/firmware/printers/prints/{file_id}/preview", params={"machine": "printer"})
    assert preview.status_code == 404
    with pytest.raises(ValueError, match="no file .* is kept"):
        machine_plans.save("garage", "printer_1", "printer", None, file_id)
    with pytest.raises(ValueError, match="no such print file"):
        devices.start_print(PORT, file_id)
    assert devices.print_job(PORT) is None
    links.stop_all()


def test_a_slice_s_record_stays_while_its_g_code_is_in_the_folder(fake_arduino_cli):
    """A slice's record goes with the file the Print card forgot. G-code still in the
    folder under a description that says no kind is no kept file, and is not forgotten:
    listing the slices leaves its record where it is, until the file is deleted."""
    file_id = _a_description_that_says_no_kind("left-out")
    record = slicer.slices_dir() / f"{file_id}.json"
    record.parent.mkdir(exist_ok=True)
    record.write_text("{}")
    assert slicer.records() == [] and slicer.get_record(file_id) is None
    assert record.is_file()
    assert devices.delete_print_file(file_id)
    assert slicer.records() == [] and not record.exists()


def test_a_file_is_kept_for_a_kind_of_machine_or_not_at_all(fake_arduino_cli):
    with pytest.raises(TypeError):
        devices.save_print_file("square.gcode", b"G90\nG1 X10 F600\n")
    with pytest.raises(ValueError, match="no kind of machine is called None"):
        devices.save_print_file("square.gcode", b"G90\nG1 X10 F600\n", machine=None)
    upload = TestClient(app).post(
        "/firmware/printers/prints", params={"name": "square.gcode"}, content=b"G1 X1\n"
    )
    assert upload.status_code == 422 and "machine" in upload.text
    assert devices.print_files() == []
    kept = devices.save_print_file("square.gcode", b"G90\nG1 X10 F600\n", machine="printer")
    whole = kept.model_dump()
    for without in ({k: v for k, v in whole.items() if k != "machine"}, {**whole, "machine": None}):
        with pytest.raises(ValueError, match="machine"):
            PrintFile(**without)


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
    _, problems = grbl.check_gcode(DRY_RUN.decode())
    dwells = [p for p in problems if "G4 P500 dwells 500 s on GRBL, whose P is seconds" in p]
    assert len(dwells) == DRY_RUN.decode().count("G4 P500")
    assert any("M117 is not a GRBL code" in p for p in problems)
    assert any("M84 is not a GRBL code" in p for p in problems)
    assert gcode.check_gcode(DRY_RUN.decode())[1] == []
    assert grbl.check_gcode(A_CUT.decode())[1] == []
    _, odd = grbl.check_gcode("G29\nG04 P90\nM03 S1000\nG04 P30\n")
    assert odd == [
        "line 1: G29 is a printer's bed probe, not a GRBL code",
        "line 2: G04 P90 dwells 90 s on GRBL, whose P is seconds; a printer's file counts it in milliseconds",
    ]


def test_the_spindle_bound_is_the_router_s_and_the_check_is_the_dialect_s():
    """GRBL's file rules live with GRBL: the spindle bound, the M codes it takes, the
    dwell in its unit. Marlin's check knows none of them, and a kept file is checked by
    the dialect of the kind it is kept for."""
    fast = "M3 S30000\nM5\n"
    assert grbl.check_gcode(fast) == (2, ["line 1: M3 asks for 30000 rpm, above 24000"])
    assert gcode.check_gcode(fast) == (2, [])
    assert dialects.by_machine("router").check_file is grbl.check_gcode
    assert dialects.by_machine("printer").check_file is gcode.check_gcode
    for no_dialect_s in ("laser", None):
        with pytest.raises(KeyError):
            dialects.by_machine(no_dialect_s)


def test_the_app_s_own_toolpath_is_kept_for_the_router_and_checks_clean(fake_arduino_cli):
    record = cam.cut_into("router_coupon", CutFor(name="cnc_router"))
    kept = devices.print_file(record.file_id)
    assert kept.machine == "router" and kept.problems == []


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
