"""A machine's frame (api.machine_frame): where its work happens in the site, in mm --
its bed's origin and height, its working volume and whose figure that is, the way each
axis homes, and the part's bed and axes -- built by one function that both the board
view's answer (GET /firmware/printers/where) and the site's tree serve, so no two
drawings of one machine stand in two frames.
"""

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from apothecary import sites
from apothecary.api import _assembly_tree, app, machine_frame
from apothecary.firmware import gcode, grbl
from apothecary.firmware.models import GRBL, PrinterStatus
from apothecary.hierarchy import Assembly
from apothecary.models.bounds import BoundingBox3D
from apothecary.models.vectors import Vector3D
from apothecary.projects.parts import ender3

PORT = "/dev/ttyFAKE1"  # the scripted arduino-cli's unmatched board
BOARD = "printer_1.frame_system.mainboard"
CONTROLLER = "cnc_router.frame_system.controller"
# The AnoleX's own settings, as its controller answered $$: X homes to its minimum ($23
# bit 0), Y and Z to their maximum; its Z travels 130 mm, not the maker's 80.
ANOLEX = {23: 1, 130: 400.0, 131: 600.0, 132: 130.0}


@pytest.fixture
def garage():
    sites.store.reset("garage")
    yield sites.store.get("garage")
    sites.store.reset("garage")


@pytest.fixture
def router_links(monkeypatch):
    """The seam's link registry over the simulated router, its moves instant."""
    monkeypatch.setenv("APOTHECARY_SIMULATED_SPEED", "0")
    links = gcode.PrinterLinks(factory=grbl.SimulatedRouter)
    monkeypatch.setattr(gcode, "_LINKS", links)
    yield links
    links.stop_all()


def _router_poll(mpos: dict, settings: dict | None) -> PrinterStatus:
    """A router's poll as grbl's status builds it: with the controller's settings read,
    its homing, its tool in the volume and its travel; without them, none of the three."""
    return PrinterStatus(
        port=PORT,
        polled_at=datetime.now(timezone.utc),
        dialect=GRBL,
        position=mpos,
        homing=grbl.homing_from(settings, grbl.HomingProof(assumed=True)) if settings else None,
        tool_position=grbl.in_volume(mpos, settings),
        travel=grbl.travel_of(settings) if settings else None,
    )


def _node(tree: dict, name: str) -> dict:
    return next(n for n in tree["children"] if n["name"] == name)


def test_the_ender_s_frame_is_its_bed_where_the_site_stands_it(garage):
    """printer_1 is an Ender 3 drawn as it is: its volume starts where the model says,
    95 mm up, and its bed carries Y under a nozzle standing at the volume's front."""
    node = _node(_assembly_tree(garage), "printer_1")
    frame, at = node["frame"], node["position"]
    assert frame["position"] == [at["x"], at["y"], at["z"]]
    assert frame["origin"] == [90.0, 100.0, 95.0] and frame["origin_from"] == "node"
    assert frame["bed_origin"] == [at["x"] + 90.0, at["y"] + 100.0, at["z"] + 95.0]
    assert frame["bed_z"] == at["z"] + 95.0
    assert frame["volume"] == [220.0, 220.0, 250.0] == frame["site_volume"]
    assert frame["volume_from"] == "site" and frame["homing"] is None
    assert frame["bed_moves_y"] == 0.0
    assert frame["kinematics"] == {
        "rest": ender3.KINEMATICS["rest"],
        "range": ender3.KINEMATICS["range"],
    }
    # Nothing but a machine has a frame: its mainboard, a piece inside it, has none.
    inside = _node(_node(node, "frame_system"), "mainboard")
    assert inside["frame"] is None


def test_a_router_s_frame_takes_its_controller_s_travel_and_the_way_each_axis_homes(garage):
    """Once the controller has said its settings, the volume is its travel and each axis
    homes the way $23 says; the tool placed by the frame alone stands where the server's
    in_volume puts it. Before, the site's figure, and no homing: nothing to place a tool by."""
    router = next(c for c in garage.children if c.name == "cnc_router")
    mpos = {"x": 168.074, "y": -126.1, "z": -73.266}

    before = machine_frame(router, router.position, controller=_router_poll(mpos, None))
    assert before["volume"] == [400.0, 600.0, 80.0] and before["volume_from"] == "site"
    assert before["homing"] is None

    said = machine_frame(router, router.position, controller=_router_poll(mpos, ANOLEX))
    assert said["volume"] == [400.0, 600.0, 130.0] and said["volume_from"] == "controller"
    assert said["site_volume"] == [400.0, 600.0, 80.0]
    assert said["homing"] == {"x": "min", "y": "max", "z": "max"}
    # The table is the site's either way: where the volume starts is no controller's word.
    assert said["origin"] == before["origin"] == [115.0, 165.0, 100.0]
    assert said["bed_moves_y"] == 300.0

    # An axis homed to its minimum counts up from that switch, and is where it says; one
    # homed to its maximum counts down from it, and is its position plus its travel.
    placed = {
        k: round(mpos[k] + (0.0 if said["homing"][k] == "min" else said["volume"][i]), 3)
        for i, k in enumerate("xyz")
    }
    assert placed == grbl.in_volume(mpos, ANOLEX) == {"x": 168.074, "y": 473.9, "z": 56.734}
    # Counted as if every axis homed to its maximum, the tool would stand a whole X
    # travel off: what a page guessing the way would draw.
    assert grbl.in_volume(mpos, {**ANOLEX, 23: 0})["x"] - placed["x"] == pytest.approx(400.0)


def test_a_block_s_volume_is_centred_on_its_footprint_and_stands_on_its_base():
    """A printer drawn as a block says how big its volume is, not where: centred on its
    footprint, on the top of its base (its frame_system's footprint)."""
    base = Assembly(
        name="frame_system",
        footprint=BoundingBox3D(min_point=Vector3D(), max_point=Vector3D(x=300, y=300, z=60)),
    )
    block = Assembly(
        name="printer_2",
        position=Vector3D(x=1000, y=500, z=0),
        footprint=BoundingBox3D(min_point=Vector3D(), max_point=Vector3D(x=300, y=300, z=400)),
        build_volume=Vector3D(x=200, y=180, z=150),
        children=[base],
    )
    frame = machine_frame(block, block.position)
    assert frame["origin"] == [50.0, 60.0, 60.0] and frame["origin_from"] == "footprint"
    assert frame["bed_origin"] == [1050.0, 560.0, 60.0] and frame["bed_z"] == 60.0
    assert frame["bed_moves_y"] is None and frame["kinematics"] is None
    assert machine_frame(Assembly(name="shelf"), Vector3D()) is None


def test_the_board_view_and_the_tree_serve_one_frame_wherever_the_machine_is_moved(
    fake_arduino_cli, garage
):
    """The where answer and the site's tree carry the same frame for printer_1, and both
    follow it when the layout moves it."""
    c = TestClient(app)
    c.put(f"/sites/garage/nodes/{BOARD}/device", json={"identity": PORT})
    try:
        where = c.get("/firmware/printers/where", params={"port": PORT}).json()
        tree = c.get("/sites/garage").json()["tree"]
        assert where["printer"]["frame"] == _node(tree, "printer_1")["frame"]
        assert where["board"]["frame"] is None  # a mainboard is no machine
        was = where["printer"]["frame"]["bed_origin"]

        at = _node(tree, "printer_1")["position"]
        moved = {"x": at["x"] + 100.0, "y": at["y"] - 50.0, "z": at["z"]}
        tree = c.post("/sites/garage/layout", json={"positions": {"printer_1": moved}}).json()[
            "tree"
        ]
        where = c.get("/firmware/printers/where", params={"port": PORT}).json()
        assert where["printer"]["frame"] == _node(tree, "printer_1")["frame"]
        assert where["printer"]["frame"]["bed_origin"] == [was[0] + 100.0, was[1] - 50.0, was[2]]
    finally:
        c.delete(f"/sites/garage/nodes/{BOARD}/device")


def test_the_board_view_takes_the_controller_s_word_from_the_port_s_last_poll(
    fake_arduino_cli, fresh_task_runner, router_links, garage
):
    """The router's where answer, after a poll has read its controller's settings: the
    simulated controller's travel and its homing, every axis to its maximum. Asking for
    it sends nothing to the port."""
    c = TestClient(app)
    c.put(f"/sites/garage/nodes/{CONTROLLER}/device", json={"identity": PORT})
    try:
        st = c.get("/firmware/printers/status", params={"port": PORT}).json()
        assert st["travel"] == {"x": 400.0, "y": 600.0, "z": 80.0}
        sent = router_links.log_for(PORT).next_index
        frame = c.get("/firmware/printers/where", params={"port": PORT}).json()["printer"]["frame"]
        assert frame["volume"] == [400.0, 600.0, 80.0] and frame["volume_from"] == "controller"
        assert frame["homing"] == {"x": "max", "y": "max", "z": "max"}
        assert frame["origin"] == [115.0, 165.0, 100.0] and frame["bed_moves_y"] == 300.0
        assert router_links.log_for(PORT).next_index == sent  # the port was asked nothing
        # The tree has no controller's word: the site's figure, labelled so.
        tree_frame = _node(c.get("/sites/garage").json()["tree"], "cnc_router")["frame"]
        assert tree_frame["volume_from"] == "site" and tree_frame["homing"] is None
        assert {k: v for k, v in tree_frame.items() if k not in ("volume_from", "homing")} == {
            k: v for k, v in frame.items() if k not in ("volume_from", "homing")
        }
    finally:
        c.delete(f"/sites/garage/nodes/{CONTROLLER}/device")
