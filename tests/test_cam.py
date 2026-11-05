"""The router's toolpath (apothecary/cam): a part's declared cuts written in GRBL's
dialect, kept and recorded, streamed as a cut that names its operation, and the
simulated router's trace measured against the design."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from apothecary import jobs
from apothecary.api import app, routers_in
from apothecary.cam import measure, service, toolpath
from apothecary.cam.models import CutFor, Cuts, Feeds, Hole, Outline, Pocket, Stock
from apothecary.firmware import devices, gcode, grbl
from apothecary.menu import Context, PartSeen, PictureContext, Pointing, resolve
from apothecary.projects.parts.router_coupon import DEFAULT as COUPON
from apothecary.projects.parts.router_coupon import Params

PORT = "/dev/ttyFAKE1"  # the scripted arduino-cli's unmatched board, a router over router_links
CONTROLLER = "cnc_router.frame_system.controller"


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


# --- the toolpath -----------------------------------------------------------------


def test_passes_take_the_step_down_and_the_last_reaches_the_depth():
    assert toolpath.passes(4.0, 2.0) == [-2.0, -4.0]
    assert toolpath.passes(5.0, 2.0) == [-2.0, -4.0, -5.0]
    assert toolpath.passes(1.0, 2.0) == [-1.0]


def test_the_coupons_toolpath_is_checked_clean_and_names_each_operation():
    cuts = COUPON.cuts()
    assert isinstance(cuts, Cuts) and cuts.stock.x == 140 and cuts.stock.y == 100
    written = toolpath.write(cuts, "router_coupon")
    total, problems = gcode.check_gcode(toolpath.text(written))
    assert problems == [] and total == len([ln for ln in written.lines if not ln.startswith("(")])
    assert [o.kind for o in written.operations] == ["pocket", "hole", "hole", "outline"]
    assert all(o.cut for o in written.operations)
    # Each operation's lines are announced for the cut that streams them.
    named = [ln for ln in written.lines if devices.OPERATION_RE.match(ln)]
    assert named[0].startswith("(op 1/4 pass 1/2: pocket 40 x 30 at 30,35 to z -2)")
    assert sum(o.passes for o in written.operations) == len(named)
    # The holes are smaller than the tool: bored to it, and said.
    assert written.messages == [
        "hole 3 mm at 110,36.667 is smaller than the 6 mm tool: bored to the tool",
        "hole 3 mm at 110,63.333 is smaller than the 6 mm tool: bored to the tool",
    ]
    # The spindle line is within the router's bounds, as a typed control would be.
    assert grbl.normalise_control("M3 S12000") == "M3 S12000"
    assert written.bounds is not None and written.bounds.min[2] == -10.5
    assert 0 < written.length_mm and 0 < written.time_s


def test_a_pocket_narrower_than_the_tool_is_left_out_and_said():
    cuts = Cuts(
        stock=Stock(x=50, y=50, thickness=10), operations=[Pocket(x=5, y=5, w=4, h=30, depth=2)]
    )
    written = toolpath.write(cuts)
    assert written.operations[0].cut is False and written.operations[0].lines == 0
    assert written.messages == ["pocket 4 x 30 at 5,5 is narrower than the 6 mm tool: not cut"]


def test_a_hole_wider_than_the_tool_is_bored_in_a_circle_of_its_size():
    cuts = Cuts(
        stock=Stock(x=50, y=50, thickness=10), operations=[Hole(x=25, y=25, diameter=10, depth=2)]
    )
    written = toolpath.write(cuts)
    assert written.messages == []
    moves = [ln for ln in written.lines if ln.startswith("G1 X")]
    assert len(moves) == toolpath.CIRCLE_SEGMENTS
    assert written.bounds is not None
    assert written.bounds.min[:2] == [20.0, 20.0] and written.bounds.max[:2] == [30.0, 30.0]


def test_an_outline_below_the_stock_stops_a_millimetre_into_the_spoilboard():
    cuts = Cuts(stock=Stock(x=50, y=50, thickness=10), operations=[Outline(w=40, h=40, depth=14)])
    written = toolpath.write(cuts)
    assert written.messages == [
        "outline depth 14 is below the stock's 10 mm: cut to 11, a millimetre into the spoilboard"
    ]
    assert written.bounds is not None and written.bounds.min[2] == -11.0


def test_feeds_are_bounded_by_the_router_s_figures():
    with pytest.raises(ValueError):
        Feeds(cut=grbl.FEED_MAX + 1)
    with pytest.raises(ValueError):
        Feeds(rpm=gcode.SPINDLE_MAX_RPM + 1)


# --- kept, recorded, offered --------------------------------------------------------


def test_the_toolpath_is_kept_as_a_cut_file_and_recorded_beside_it(tmp_path, monkeypatch):
    monkeypatch.setenv("APOTHECARY_STATE_DIR", str(tmp_path / "state"))
    record = service.cut_into("router_coupon", CutFor(name="cnc_router", site="garage", port=PORT))
    kept = next(f for f in devices.print_files() if f.id == record.file_id)
    assert kept.problems == [] and kept.lines == record.lines
    assert record.part == "router_coupon" and record.router.name == "cnc_router"
    assert [o.kind for o in record.operations] == ["pocket", "hole", "hole", "outline"]
    assert service.get_record(record.file_id) == record
    assert [r.file_id for r in service.records()] == [record.file_id]
    with pytest.raises(service.CamError, match="does not say how it is cut"):
        service.cut_into("calibration_cube", CutFor(name="cnc_router"))


def test_the_cut_route_takes_a_site_s_piece_and_refuses_a_part_without_cuts(
    tmp_path, monkeypatch, garage
):
    monkeypatch.setenv("APOTHECARY_STATE_DIR", str(tmp_path / "state"))
    with TestClient(app) as c:
        r = c.post(
            "/cam/cut",
            json={"part": "router_coupon", "site": "garage", "router": CONTROLLER, "port": PORT},
        )
        assert r.status_code == 200, r.text
        record = r.json()
        assert record["router"] == {
            "name": "cnc_router",
            "site": "garage",
            "path": CONTROLLER,
            "port": PORT,
        }
        assert len(record["messages"]) == 2
        assert c.get("/cam/cuts").json()[0]["file_id"] == record["file_id"]
        assert c.get(f"/cam/cuts/{record['file_id']}").status_code == 200
        r = c.post("/cam/cut", json={"part": "footpedal", "site": "garage", "port": PORT})
        assert r.status_code == 400 and "does not say how it is cut" in r.json()["detail"]
        r = c.post("/cam/cut", json={"part": "nowhere", "site": "garage", "port": PORT})
        assert r.status_code == 404


def test_the_ring_offers_toolpath_on_a_part_with_cuts_when_a_router_is_pinned(garage):
    seen = PictureContext(routers=["cnc_router"], part=PartSeen(cuts=True))
    ring = resolve(Context(pointing=Pointing.NODE, targets=["router_coupon"]), garage, picture=seen)
    (option,) = [o for o in ring.options if o.label == "Toolpath"]
    assert option.action == "toolpath:piece:cnc_router"
    # No router pinned, or a part that is not cut: no Toolpath.
    for picture in (
        PictureContext(part=PartSeen(cuts=True)),
        PictureContext(routers=["cnc_router"]),
    ):
        ring = resolve(
            Context(pointing=Pointing.NODE, targets=["router_coupon"]), garage, picture=picture
        )
        assert "Toolpath" not in [o.label for o in ring.options]


def test_the_coupon_s_cuts_follow_its_parameters():
    cuts = COUPON.cuts(Params(hole_diameter=8, holes=1, stock_margin=5).model_dump())
    assert cuts.stock.x == 130 and len(cuts.operations) == 3
    hole = cuts.operations[1]
    assert isinstance(hole, Hole) and hole.diameter == 8 and hole.y == 45


# --- streamed: the job names its operation, and the trace is measured --------------


def test_a_cut_names_the_operation_it_is_in_and_its_trace_measures_the_pocket(
    fake_arduino_cli, router_links, tmp_path, monkeypatch
):
    monkeypatch.setenv("APOTHECARY_STATE_DIR", str(tmp_path / "state"))
    record = service.cut_into("router_coupon", CutFor(name="cnc_router", port=PORT))
    devices.identify_printer(PORT)
    router_links.control.arm(PORT)
    # The work zero at the stock's front-left top corner, where the tool stands: the
    # toolpath's coordinates count from it, and the controller's soft limits hold.
    assert devices.printer_control(PORT, "G10 L20 P1 X0 Y0 Z0").lines == ["ok"]
    job = devices.start_print(PORT, record.file_id)
    assert job.op is jobs.CUT
    job.thread.join(10)
    assert job.error is None and job.stage == "done"
    assert job.snapshot()["operation"].startswith("op 4/4 pass 6/6: outline")
    trace = router_links.get(PORT)._t.trace
    cuts = COUPON.cuts()
    pocket = cuts.operations[0]
    as_cut = measure.extent(
        trace,
        z=-pocket.depth,
        tool_diameter=cuts.tool.diameter,
        within=(pocket.x - 1, pocket.y - 1, pocket.x + pocket.w + 1, pocket.y + pocket.h + 1),
    )
    assert measure.size(as_cut) == (pocket.w, pocket.h)
    hole = cuts.operations[1]
    bored = measure.extent(
        trace,
        z=-1.0,
        tool_diameter=cuts.tool.diameter,
        within=(hole.x - 5, hole.y - 5, hole.x + 5, hole.y + 5),
    )
    assert measure.size(bored) == (cuts.tool.diameter, cuts.tool.diameter)


def test_a_cut_past_the_travel_fails_in_the_controller_s_words(
    fake_arduino_cli, router_links, tmp_path, monkeypatch
):
    """Zeroed with no depth under the tool, the first plunge leaves the travel. The cut
    stops there, and its job says why in words, not in a code."""
    monkeypatch.setenv("APOTHECARY_STATE_DIR", str(tmp_path / "state"))
    record = service.cut_into("router_coupon", CutFor(name="cnc_router", port=PORT))
    devices.identify_printer(PORT)
    router_links.control.arm(PORT)
    assert devices.printer_control(PORT, "$J=G91 G21 Z-40 F1000").lines == ["ok"]  # the bottom of Z
    assert devices.printer_control(PORT, "G10 L20 P1 X0 Y0 Z0").lines == ["ok"]
    job = devices.start_print(PORT, record.file_id)
    job.thread.join(10)
    assert job.stage == "failed"
    assert job.record.outcome == "failed"
    assert job.record.reason.endswith(
        "G1 Z-2 F300 -> ALARM:2 (a move would go past the soft limits)"
    )
    # The host reset it, so the spindle is off and the controller says what it wants next.
    status = devices.printer_status(PORT)
    assert status.state == "alarm" and not status.spindle.on


def test_routers_in_names_the_router_a_board_answered_as(fake_arduino_cli, router_links, garage):
    from apothecary.api import printers_in

    assert routers_in("garage") == [] and "cnc_router" not in printers_in("garage")
    devices.identify_printer(PORT)
    devices.get_state().set_binding("garage", CONTROLLER, PORT)
    assert routers_in("garage") == ["cnc_router"]
    assert "cnc_router" not in printers_in("garage")
