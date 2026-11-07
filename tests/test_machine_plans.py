"""A machine planned before its board is connected (apothecary/machine_plans.py).

A node drawn from a part that is a machine is a printer or a router with no board
pinned to it: its choices are answered by its node, a plan names the part it will make
and a kept file of its own kind, and the ring offers Slice and Toolpath to it. Each test
keeps its plans in a state folder of its own; nothing here touches a port.
"""

import pytest
from fastapi.testclient import TestClient
from firmware_helpers import _isolate_firmware_state

from apothecary import machine_plans
from apothecary.api import app
from apothecary.firmware import devices

client = TestClient(app)
A_CUT = b"G21 G90\nM3 S12000\nG0 X-10 Y-10\nG1 Z-1 F200\nM5\nM30\n"


@pytest.fixture(autouse=True)
def _a_state_folder_of_its_own(monkeypatch, tmp_path):
    _isolate_firmware_state(monkeypatch, tmp_path)


def test_a_machine_is_a_node_drawn_from_a_part_that_is_one():
    assert machine_plans.kind_of_part("ender3") == "printer"
    assert machine_plans.kind_of_part("anolex_4060_evo_ultra_2") == "router"
    assert machine_plans.kind_of_part("router_coupon") is None
    assert client.get("/sites/garage/machines").json() == [
        {"path": "printer_1", "kind": "printer", "part_ref": "ender3"},
        {"path": "cnc_router", "kind": "router", "part_ref": "anolex_4060_evo_ultra_2"},
    ]


def test_a_machine_with_no_board_answers_its_choices_by_its_node():
    answer = client.get("/sites/garage/machines/cnc_router").json()
    assert answer["machine"] == {
        "kind": "router",
        "port": "",
        "identity": None,
        "path": "cnc_router",
    }
    assert answer["site"] == "garage" and [op["kind"] for op in answer["operations"]] == ["cut"]
    paths = [p["path"] for p in answer["parts"]]
    assert "router_coupon" in paths and not any(p.startswith("cnc_router") for p in paths)
    assert answer["where"]["build_volume"] == [400.0, 600.0, 80.0] and answer["plan"] is None
    assert client.get("/sites/garage/machines/workbench").status_code == 400
    assert client.get("/sites/garage/machines/nowhere").status_code == 404


def test_a_plan_names_a_part_of_the_site_and_a_file_of_the_machine_s_kind():
    cut = devices.save_print_file("pocket.nc", A_CUT, machine="router")
    printed = devices.save_print_file("square.gcode", b"G1 X1 F600\n", machine="printer")
    plan = "/sites/garage/machines/cnc_router/plan"
    kept = client.put(plan, json={"part": "router_coupon", "file_id": cut.id})
    assert kept.status_code == 200, kept.text
    assert (kept.json()["part"], kept.json()["file_id"], kept.json()["kind"]) == (
        "router_coupon",
        cut.id,
        "router",
    )
    assert client.get("/sites/garage/machines/cnc_router").json()["plan"]["file_id"] == cut.id
    other = client.put(plan, json={"file_id": printed.id})
    assert other.status_code == 422 and "kept for a printer: a router's plan" in other.text
    assert client.put(plan, json={"file_id": "20260101T000000.000-nothing"}).status_code == 422
    assert client.put(plan, json={"part": "nowhere"}).status_code == 422
    assert client.put(plan, json={"part": "cnc_router"}).status_code == 422  # the machine itself
    assert client.delete(plan).json() == {"cleared": True}
    assert client.get("/sites/garage/machines/cnc_router").json()["plan"] is None


def test_the_ring_offers_toolpath_to_a_router_with_no_board():
    """The coupon's ring, with nothing pinned anywhere: Toolpath to the router, planned
    with no board connected. A printer with no board is offered on no ring: Print and
    Slice would stand on every part's, and its plan is made in its own Machine."""
    told = {
        "context": {"pointing": "node", "targets": ["router_coupon"]},
        "site": "garage",
    }
    ring = client.post("/menu/resolve", json=told).json()
    actions = {o["label"]: o["action"] for o in ring["options"]}
    assert actions.get("Toolpath") == "toolpath:piece:cnc_router"
    assert "Slice" not in actions and "Print" not in actions
