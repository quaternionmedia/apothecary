"""A machine renamed (apothecary/renames.py, PUT /sites/{name}/machines/{path}/name): its
node's name and path changed, kept across a rebuild of the site, every record kept under
its old path moved to the new one, and what the program names by its own words read at
the new name. Refused while the bench is at work, for a name that is no node's, and for
one a node beside it has."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from apothecary import journeys, renames, sites
from apothecary.api import app
from apothecary.example_hierarchy import create_example_site, validate_garage_layout
from apothecary.firmware import devices
from apothecary.hierarchy import find_node_by_path
from apothecary.site_store import SiteStore
from apothecary.state_folder import state_dir

client = TestClient(app)

BOARD = "printer_1.frame_system.mainboard"


@pytest.fixture(autouse=True)
def garage(tmp_path, monkeypatch):
    monkeypatch.setenv("APOTHECARY_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setattr(devices, "_STATE", None)  # the pins of this state folder
    sites.store.reset("garage")
    yield sites.store.get("garage")
    sites.store.reset("garage")


def _write(relative: str, data: dict) -> Path:
    path = state_dir() / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def _read(relative: str) -> dict:
    return json.loads((state_dir() / relative).read_text(encoding="utf-8"))


def _kept_under_printer_1() -> None:
    """A record of each kind kept under printer_1, as the bench keeps them."""
    devices.get_state().set_binding("garage", BOARD, "A106ZTEU", kind="printer")
    devices.get_state().set_binding("garage", "cnc_router.frame_system.controller", "CH340")
    _write(
        "plans/garage/printer_1.json", {"site": "garage", "path": "printer_1", "kind": "printer"}
    )
    _write("filaments/garage/printer_1.json", {"site": "garage", "printer": "printer_1"})
    _write("first-layer-offset/garage/printer_1.json", {"site": "garage", "printer": "printer_1"})
    printer = {"site": "garage", "node": "printer_1", "part": "ender3"}
    _write("corrections/garage/printer_1/pla.json", {"printer": printer})
    _write("bed/mounts.json", {"garage/printer_1": {"screw": "M4"}, "theatre/printer_1": {}})
    _write("bed/positions.json", {"garage/printer_1": {"screws": {}}})
    at = {"part": "ender3", "name": "printer_1", "site": "garage", "path": "printer_1"}
    _write("slices/s1.json", {"printer": at})
    _write("slices/s2.json", {"printer": {**at, "site": "theatre"}})
    _write("jobs/j1.json", {"site": "garage", "machine": {"path": BOARD}})
    _write("cabinet/bed_shims/d1.json", {"machine": {**at, "kind": "printer"}})


def test_a_machine_renamed_takes_its_records_and_keeps_its_name(garage):
    _kept_under_printer_1()
    r = client.put("/sites/garage/machines/printer_1/name", json={"name": "big_ender"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert (body["path"], body["was"], body["failed"]) == ("big_ender", "printer_1", [])
    assert "the board pinned to big_ender.frame_system.mainboard" in body["moved"]
    assert "1 slice records" in body["moved"] and "1 jobs" in body["moved"]
    assert "1 drawers" in body["moved"]

    # The node, here and as the site is built again.
    assert find_node_by_path(garage, "big_ender") is not None
    assert find_node_by_path(garage, "printer_1") is None
    # As a server starting builds it, and as Reset builds it again.
    started = SiteStore({"garage": (create_example_site, validate_garage_layout)}).get("garage")
    assert find_node_by_path(started, "big_ender.frame_system.mainboard") is not None
    assert validate_garage_layout(started).violations == validate_garage_layout(garage).violations
    sites.store.reset("garage")
    rebuilt = sites.store.get("garage")
    assert find_node_by_path(rebuilt, "big_ender.frame_system.mainboard") is not None
    assert client.get("/sites/garage/machines/big_ender").status_code == 200
    assert client.get("/sites/garage/machines/printer_1").status_code == 404

    # Every record under its old path, under the new one; another site's left alone.
    pins = {b.path: b.identity for b in devices.get_state().bindings("garage")}
    assert pins == {
        "big_ender.frame_system.mainboard": "A106ZTEU",
        "cnc_router.frame_system.controller": "CH340",
    }
    assert _read("plans/garage/big_ender.json")["path"] == "big_ender"
    assert _read("filaments/garage/big_ender.json")["printer"] == "big_ender"
    assert _read("first-layer-offset/garage/big_ender.json")["printer"] == "big_ender"
    assert _read("corrections/garage/big_ender/pla.json")["printer"]["node"] == "big_ender"
    for gone in ("plans", "filaments", "first-layer-offset"):
        assert not (state_dir() / gone / "garage" / "printer_1.json").exists()
    assert not (state_dir() / "corrections" / "garage" / "printer_1").exists()
    assert set(_read("bed/mounts.json")) == {"garage/big_ender", "theatre/printer_1"}
    assert set(_read("bed/positions.json")) == {"garage/big_ender"}
    assert _read("slices/s1.json")["printer"] | {"part": None} == {
        "part": None,
        "name": "big_ender",
        "site": "garage",
        "path": "big_ender",
    }
    assert _read("slices/s2.json")["printer"]["path"] == "printer_1"
    assert _read("jobs/j1.json")["machine"]["path"] == "big_ender.frame_system.mainboard"
    drawer = _read("cabinet/bed_shims/d1.json")["machine"]
    assert (drawer["path"], drawer["name"]) == ("big_ender", "big_ender")

    # What the program names by its own words, at the name it has now.
    assert renames.current("garage", BOARD) == "big_ender.frame_system.mainboard"
    assert renames.written("garage", "big_ender.frame_system") == "printer_1.frame_system"
    staged = {j["id"]: j["staged_on"] for j in journeys.manifest()}
    assert ["machine", "big_ender"] in staged["level"]
    from apothecary.firmware.deck_control import MACHINES

    assert (MACHINES[0].name, MACHINES[0].node) == (
        "big_ender",
        "big_ender.frame_system.mainboard",
    )

    # Back to the program's own name: nothing is kept renamed.
    back = client.put("/sites/garage/machines/big_ender/name", json={"name": "printer_1"})
    assert back.status_code == 200 and back.json()["path"] == "printer_1", back.text
    assert renames.names("garage") == {}
    assert _read("jobs/j1.json")["machine"]["path"] == BOARD


@pytest.mark.parametrize(
    "name, said",
    [
        ("big.ender", "is no node's name"),
        ("", "at least 1 character"),
        ("cnc_router", "has a cnc_router beside printer_1 already"),
    ],
)
def test_a_name_that_is_no_nodes_or_is_taken_is_refused_and_nothing_moves(name, said):
    _kept_under_printer_1()
    r = client.put("/sites/garage/machines/printer_1/name", json={"name": name})
    assert r.status_code == 422 and said in r.text, r.text
    assert renames.names("garage") == {}
    assert _read("jobs/j1.json")["machine"]["path"] == BOARD


def test_a_rename_is_refused_while_the_bench_is_at_work(monkeypatch):
    _kept_under_printer_1()
    monkeypatch.setattr(
        devices, "at_work", lambda links=None: ["/dev/ttyUSB0: a print is printing"]
    )
    r = client.put("/sites/garage/machines/printer_1/name", json={"name": "big_ender"})
    assert r.status_code == 409 and "while the bench is at work" in r.text, r.text
    assert renames.names("garage") == {}
    assert {b.path for b in devices.get_state().bindings("garage")} >= {BOARD}


def test_only_a_machine_is_renamed_here():
    assert (
        client.put("/sites/garage/machines/workbench/name", json={"name": "bench"}).status_code
        == 400
    )
    assert client.put("/sites/garage/machines/nope/name", json={"name": "x"}).status_code == 404
