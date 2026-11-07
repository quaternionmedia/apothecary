"""The router's own bed reading: a table map, Z probed with the touch plate at each
point of a grid over the working area, kept and drawn as the Ender's mesh is.

Against the simulated router (``grbl.SimulatedRouter``), its moves instant: nothing
here opens a port. The plate it answers a probe with is flat, 20 mm under the tool
wherever the tool stands, so the map it gives is flat and every touch is at one
height; what is held here is the sequence sent and its bounds, what is kept of the
touches, and where the record is listed.
"""

from __future__ import annotations

import threading
import time
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from apothecary.api import app
from apothecary.firmware import devices, dialects, gcode, grbl, occupants
from apothecary.firmware.models import LevelingRecord, TableGrid
from apothecary.firmware.toolchains import PortHeld, ToolchainError

PORT = "/dev/ttyFAKE1"  # the scripted arduino-cli's unmatched board
TRAVEL = {"x": 400.0, "y": 600.0, "z": 80.0}  # the simulated router's, as its $$ says
# After homing the tool stands at the pull-off from the switches, 3 mm down from the
# top of Z; from there the probe may go the rest of the travel, 77 mm.
TOP = -3.0
DEPTH = "77.00"
PLATE = -23.0  # the simulated plate, 20 mm under a tool at the top


@pytest.fixture
def router_links(monkeypatch):
    """The seam's link registry over the simulated router, its moves instant."""
    monkeypatch.setenv("APOTHECARY_SIMULATED_SPEED", "0")
    links = gcode.PrinterLinks(factory=grbl.SimulatedRouter)
    monkeypatch.setattr(gcode, "_LINKS", links)
    yield links
    links.stop_all()


def _sent(links, port=PORT):
    return [e["text"] for e in links.log_for(port).since(0)["entries"] if e["kind"] == "tx"]


def _no_stage(word, points=None):
    pass


# --- the grid, inside the travel ---------------------------------------------------------


def test_the_grid_lies_inside_the_travel_row_by_row_from_the_front_left():
    """Machine coordinates run negative from the home corner at the back right, so
    the front-left point of the working area is the most negative in both axes; the
    rows run front to back and each row left to right, as Marlin prints its mesh."""
    grid = grbl.table_grid(TRAVEL, rows=3, cols=3, inset=20)
    assert [[(p["x"], p["y"]) for p in row] for row in grid] == [
        [(-380.0, -580.0), (-200.0, -580.0), (-20.0, -580.0)],
        [(-380.0, -300.0), (-200.0, -300.0), (-20.0, -300.0)],
        [(-380.0, -20.0), (-200.0, -20.0), (-20.0, -20.0)],
    ]
    for row in grbl.table_grid(TRAVEL, rows=5, cols=4, inset=0.5):
        for p in row:
            assert -TRAVEL["x"] < p["x"] < 0 and -TRAVEL["y"] < p["y"] < 0
    # An inset that leaves no room between the points is refused, before anything moves.
    with pytest.raises(ValueError, match="inset"):
        grbl.table_grid(TRAVEL, rows=3, cols=3, inset=200)
    with pytest.raises(ValueError, match="inset"):
        grbl.table_grid(TRAVEL, rows=3, cols=3, inset=-1)
    # So is a grid with a side of one point: a line is no map.
    with pytest.raises(ValueError, match="two"):
        grbl.table_grid(TRAVEL, rows=1, cols=3, inset=20)


def test_a_move_in_machine_coordinates_is_bounded_as_every_move_is():
    """A table map moves in machine coordinates (``G53 G0``), the one frame the
    working area is fixed in whatever work zero a person set; the allowlist takes
    such a move in any axis, bounded by the longest travel as a jog is."""
    assert grbl.normalise_control("g53 g0 x-380 y-580") == "G53 G0 X-380 Y-580"
    assert grbl.normalise_control("G53 G0 Z-3.000") == "G53 G0 Z-3.000"
    assert grbl.normalise_control("G53 G0 Z0") == "G53 G0 Z0"  # the pad's Top of Z, still
    with pytest.raises(gcode.OutOfBounds, match="beyond 600"):
        grbl.normalise_control("G53 G0 X-700 Y-20")
    with pytest.raises(ValueError, match="not an allowed"):
        grbl.normalise_control("G53 G1 X-10 F500")


def test_the_simulated_router_takes_a_g53_move_in_every_axis_and_alarms_past_its_travel(
    router_links,
):
    link = router_links.open(PORT, 115200)
    assert grbl.control_router(link, "G10 L20 P1 X0 Y0 Z0") == ["ok"]  # a work zero, mid-table
    assert grbl.control_router(link, "G53 G0 X-380 Y-580 Z-3") == ["ok"]
    assert grbl.poll_router(link).position == {"x": -380.0, "y": -580.0, "z": -3.0}
    # In machine coordinates whatever the work zero: the work position reads the offset.
    assert grbl.poll_router(link).work_position == {"x": -180.0, "y": -280.0, "z": 37.0}
    with pytest.raises(ToolchainError, match="ALARM:2"):
        grbl.control_router(link, "G53 G0 X-401")


# --- the map, over a link ------------------------------------------------------------------


def test_a_table_map_probes_each_point_from_the_top_of_z_within_the_bounds(router_links):
    """The spindle off, homed, then at each point: a rapid there in machine coordinates
    at the top of Z, a probe down as far as the travel allows at a feed under the cap,
    the lift back to the top; the touches as rows from the front; the controller's own
    word on the last touch (``$#``) kept with the lines, and the parser left absolute."""
    link = router_links.open(PORT, 115200)
    grbl.control_router(link, "M3 S8000")  # a spindle left on is turned off first
    stages = []
    reading = grbl.probe_table(
        link, grid=TableGrid(), stage=lambda word, points=None: stages.append((word, points))
    )
    assert reading.method == "G38.2"
    assert reading.mesh == [[PLATE] * 3] * 3
    assert reading.stats["rows"] == 3 and reading.stats["cols"] == 3
    assert reading.stats["range"] == 0.0 and reading.stats["mean"] == PLATE
    # Where the grid lies, from the working area's front-left corner (mpos + travel): what
    # the marks draw the relief over.
    assert reading.area == {"min": {"x": 20.0, "y": 20.0}, "max": {"x": 380.0, "y": 580.0}}
    assert reading.leveling_on is None and reading.probe_offset is None
    assert reading.subdivided is None and reading.bed_c is None

    sent = _sent(router_links)[1:]  # after the M3 above
    assert sent[:5] == ["$$", "M5", "$H", "?", "G91"]  # the `?`: where the top of Z is
    sent = [ln for ln in sent if ln != "?"]
    assert sent[-3:] == ["G53 G0 Z-3.000", "$#", "G90"]
    probed = sent[4:-2]
    assert len(probed) == 27
    for move, probe, lift in zip(probed[0::3], probed[1::3], probed[2::3], strict=True):
        assert move.startswith("G53 G0 X") and lift == "G53 G0 Z-3.000"
        assert probe == f"G38.2 Z-{DEPTH} F200"
    assert probed[0] == "G53 G0 X-380.000 Y-580.000" and probed[-3] == "G53 G0 X-20.000 Y-20.000"
    # Every line passes the dialect's own allowlist and bounds, as a typed line would.
    for line in sent:
        if line in grbl.QUERY_CODES:
            grbl.normalise_query(line)
        else:
            grbl.normalise_control(line)
    assert float(DEPTH) <= grbl.PROBE_MAX_MM and 200 <= grbl.PROBE_FEED_MAX
    assert float(DEPTH) == TOP + TRAVEL["z"]  # no deeper than the bottom of the travel

    assert stages[0] == ("homing", None) and stages[-1] == ("reading", {"done": 9, "total": 9})
    assert stages[1:-1] == [("probing", {"done": k, "total": 9}) for k in range(9)]
    assert reading.lines.count("[PRB:-20.000,-20.000,-23.000:1]") == 2  # the touch, and $#'s
    assert sum(ln.startswith("[PRB:") for ln in reading.lines) == 10
    st = grbl.poll_router(link)
    assert st.position == {"x": -20.0, "y": -20.0, "z": TOP} and not st.spindle.on


def test_a_point_the_probe_does_not_reach_stops_the_map_and_says_why(router_links):
    class DeepPlate(grbl.SimulatedRouter):
        PLATE = 100.0  # under the bottom of the travel: no touch within the move

    router_links.factory = DeepPlate
    link = router_links.open(PORT, 115200)
    link.annotate = grbl.explain  # as a link opened through the devices layer has it
    with pytest.raises(ToolchainError, match="ALARM:5 \\(probe fail: the probe did not touch"):
        grbl.probe_table(link, grid=TableGrid(), stage=_no_stage)
    assert grbl.poll_router(link).state == "alarm"
    assert _sent(router_links).count("G38.2 Z-77.00 F200") == 1  # stopped at the first


def test_a_controller_that_does_not_say_its_travel_is_not_mapped(router_links):
    class Mute(grbl.SimulatedRouter):
        def __init__(self, port, baud):
            super().__init__(port, baud)
            del self.settings[131]

    router_links.factory = Mute
    link = router_links.open(PORT, 115200)
    with pytest.raises(ToolchainError, match="travel"):
        grbl.probe_table(link, grid=TableGrid(), stage=_no_stage)
    assert _sent(router_links) == ["$$"]  # nothing moved


# --- the reading: the router's, by dialect, kept and listed as a printer's is -----------


def test_the_dialect_chooses_the_reading():
    assert dialects.MARLIN.bed_reading is gcode.read_bed
    assert dialects.GRBL.bed_reading is grbl.probe_table
    assert dialects.MARLIN.stored_mesh == "M420 V" and dialects.GRBL.stored_mesh is None
    # The request's bound on the probe's feed is the dialect's own, said once each.
    feed_bound = next(m.le for m in TableGrid.model_fields["feed"].metadata if hasattr(m, "le"))
    assert feed_bound == grbl.PROBE_FEED_MAX


def test_a_table_map_is_the_router_s_reading_kept_and_listed_as_a_printer_s_is(
    fake_arduino_cli, router_links
):
    """Started as a bed reading is, with the latch armed; while it runs the port is a
    table map's; kept as a record of the router's -- its board's key and kind, the
    grid as the mesh, the probe as the method, the touches in the lines -- and listed
    for its port by the route the world draws from; a stored mesh is never asked of
    it."""
    gate = threading.Event()

    class SlowProbe(grbl.SimulatedRouter):
        def write(self, data):
            if b"G38.2" in data:
                gate.wait(5)  # a probe takes a while; the test says when it touches
            super().write(data)

    router_links.factory = SlowProbe
    devices.identify_printer(PORT)
    assert devices.dialect_of(PORT) == "grbl"
    with pytest.raises(gcode.ControlNotArmed):
        devices.start_leveling(PORT, probe=True)
    with pytest.raises(ToolchainError, match="a stored mesh is a printer's"):
        devices.start_leveling(PORT, probe=False)
    assert "M420 V" not in _sent(router_links)
    router_links.control.arm(PORT)
    job = devices.start_leveling(PORT, probe=True, note="before surfacing the spoilboard")
    for _ in range(500):
        if job.stage == "probing":
            break
        time.sleep(0.01)
    snap = job.snapshot()
    assert snap["kind"] == "leveling" and snap["running"] is True
    assert snap["stage"] == "probing" and snap["points"] == {"done": 0, "total": 9}
    # The port is the map's: polls say so without touching it, queries and controls are
    # refused, another map is refused.
    st = devices.printer_status(PORT)
    assert st.job["kind"] == "leveling" and st.job["points"]["total"] == 9
    with pytest.raises(PortHeld, match="a table map holds the port"):
        devices.printer_query(PORT, "$G")
    with pytest.raises(PortHeld, match="a table map holds the port"):
        devices.printer_control(PORT, "$H")
    with pytest.raises(PortHeld, match="already probing"):
        devices.start_leveling(PORT, probe=True)
    gate.set()
    job.thread.join(10)
    assert job.stage == "saved" and job.error is None, job.error

    rec = job.record
    board = occupants.on_port(PORT)
    assert board.key == "FAKESERIAL1" and board.kind == "router"  # the scripted port's bridge
    assert (rec.board, rec.machine, rec.port) == (board.key, "router", PORT)
    assert rec.firmware == "Grbl 1.3a" and rec.method == "G38.2"
    assert rec.note == "before surfacing the spoilboard"
    assert rec.mesh == [[PLATE] * 3] * 3 and rec.stats["range"] == 0.0
    assert rec.area == {"min": {"x": 20.0, "y": 20.0}, "max": {"x": 380.0, "y": 580.0}}
    assert sum(ln.startswith("[PRB:") for ln in rec.lines) == 10
    assert [r.id for r in devices.leveling_records(PORT)] == [rec.id]
    assert devices.leveling_record(rec.id) == rec

    c = TestClient(app)
    listed = c.get("/firmware/printers/leveling", params={"port": PORT}).json()
    assert [r["id"] for r in listed] == [rec.id]
    assert listed[0]["area"]["max"] == {"x": 380.0, "y": 580.0} and "lines" not in listed[0]
    assert c.get(f"/firmware/printers/leveling/{rec.id}").json()["method"] == "G38.2"
    # The route starts one too, with a grid of its own; the status says how far it is.
    r = c.post(
        "/firmware/printers/level",
        json={"port": PORT, "grid": {"rows": 2, "cols": 2, "inset": 50}},
    )
    assert r.status_code == 202, r.text
    assert r.json()["kind"] == "leveling" and r.json()["points"]["total"] == 4
    devices.leveling_job(PORT).thread.join(10)
    status = c.get("/firmware/printers/level", params={"port": PORT}).json()
    assert status["running"] is False and status["stage"] == "saved"
    second = devices.leveling_record(status["record_id"])
    assert second.stats == {**second.stats, "rows": 2, "cols": 2}
    assert second.area == {"min": {"x": 50.0, "y": 50.0}, "max": {"x": 350.0, "y": 550.0}}
    assert [r.id for r in devices.leveling_records(PORT)] == [second.id, rec.id]
    # A stored mesh is a printer's: refused at the route too, and nothing Marlin is sent.
    r = c.post("/firmware/printers/level", json={"port": PORT, "probe": False})
    assert r.status_code == 503 and "a stored mesh is a printer's" in r.json()["detail"]
    assert "M420 V" not in _sent(router_links)


def test_a_printer_s_reading_is_never_the_router_s_whatever_key_it_is_under(
    fake_arduino_cli, router_links
):
    """A reading is the board's of the kind that took it: a printer's bed reading kept
    under the very key the router answers to (a bridge's ``usb:`` key is one make's)
    is not listed for the router, nor one kept before readings named their board;
    the router's own map is, alone."""
    devices.identify_printer(PORT)
    board = occupants.on_port(PORT)
    assert board.kind == "router"
    for name, kept in (
        ("printer", {"board": board.key, "machine": "printer"}),
        ("nobody", {"board": None, "machine": None}),
    ):
        devices._save_leveling(
            LevelingRecord(
                id=f"20260920T132512.468-{name}",
                port=PORT,
                at=datetime(2026, 9, 20, 13, 25, tzinfo=timezone.utc),
                method="read",
                mesh=[[0.0, 0.4], [0.1, 0.5]],
                stats=gcode.mesh_stats([[0.0, 0.4], [0.1, 0.5]]),
                firmware="Grbl 1.3a",  # even naming the router's firmware
                **kept,
            )
        )
    assert devices.leveling_records(PORT) == []
    router_links.control.arm(PORT)
    job = devices.start_leveling(PORT, probe=True)
    job.thread.join(10)
    assert job.stage == "saved", job.error
    assert [r.id for r in devices.leveling_records(PORT)] == [job.record.id]
    listed = TestClient(app).get("/firmware/printers/leveling", params={"port": PORT}).json()
    assert [r["machine"] for r in listed] == ["router"]


def test_a_link_held_on_a_board_known_as_neither_kind_takes_no_reading(
    fake_arduino_cli, router_links
):
    """A port is asked what it is before a reading, when nothing holds its link; a
    link already held on a port whose board nothing has identified is neither a
    printer's nor a router's, and no reading of either kind is started on it."""
    router_links.open(PORT, 115200)
    assert occupants.on_port(PORT) is None  # a simulated port is on no port list
    router_links.control.arm(PORT)
    with pytest.raises(ToolchainError, match="holds no board known as either"):
        devices.start_leveling(PORT, probe=True)
    assert not {"$H", "G38.2", "G28", "G29"} & {ln.split(" ")[0] for ln in _sent(router_links)}


def test_a_grid_is_bounded_before_the_port(fake_arduino_cli, router_links):
    devices.identify_printer(PORT)
    router_links.control.arm(PORT)
    c = TestClient(app)
    for grid in ({"rows": 1}, {"cols": 10}, {"inset": -5}, {"feed": 900}):
        r = c.post("/firmware/printers/level", json={"port": PORT, "grid": grid})
        assert r.status_code == 422, (grid, r.text)
    assert not [ln for ln in _sent(router_links) if ln.startswith(("$H", "G38.2", "G53"))]
