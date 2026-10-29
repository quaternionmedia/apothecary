"""The bench as a carlos.patch: apothecary/wiring/ and its routes."""

from __future__ import annotations

import json
import re

import pytest
from fastapi.testclient import TestClient

from apothecary.api import app
from apothecary.example_hierarchy import create_example_site
from apothecary.firmware.models import DeviceInfo, ExpectedFirmware, FlashRecord, NodeBinding
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
        assert catalogue.usb_jack(entry["id"]) == "usb"
    assert set(catalogue.PARTS.values()) | {catalogue.HOST} == set(catalogue.entries())


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
    assert set(body) == {"site", "patch", "evidence", "unplaced"}
    assert {"module": MAINBOARD, "jack": "usb"} in [
        c["source"] for c in body["patch"]["connections"]
    ]
    known = next(e for e in body["evidence"] if e["module"] == MAINBOARD)
    assert known["connected"] and known["port"] == "/dev/ttyFAKE1"
    alone = client.get("/sites/garage/wiring/patch").json()
    assert alone == body["patch"]
    _carlos_rules_hold(alone)
    assert client.get("/sites/nowhere/wiring").status_code == 404
