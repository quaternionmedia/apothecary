"""A projector aimed at a machine's bed (apothecary/projector.py): four points of the
bed and the four pixels lighting them fix one mapping each way, a bed that carries Y
carries its points with it, a set that fixes no mapping is refused saying why, and a
machine's calibration is kept in the state folder. Over HTTP (routes/projector.py): the
calibration kept and refused, and what the projector draws -- the file streaming or
planned, in the bed's millimetres, the tool where a poll put it, and the band -- read
from the polls kept, never by asking a port."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from apothecary import machine_plans, projector, sites
from apothecary.api import app
from apothecary.firmware import devices
from apothecary.firmware.models import GRBL, PrinterStatus
from apothecary.homography import apply
from apothecary.state_folder import state_dir

# The Ender's volume, and a projector above it, its output leaning on the bed: the bed's
# front (its low Y) at the output's bottom.
VOLUME = [220.0, 220.0, 250.0]
OUTPUT = (1920, 1080)
LIT = [(400.0, 900.0), (1500.0, 880.0), (1400.0, 200.0), (500.0, 220.0)]


def _calibration(bed_offset: float = 0.0, site: str = "garage", path: str = "printer_1"):
    return projector.checked(
        site, path, projector.starting_points(VOLUME), LIT, OUTPUT, bed_offset=bed_offset
    )


def test_a_calibration_starts_from_the_volume_s_floor_set_in():
    assert projector.starting_points(VOLUME) == [(20, 20), (200, 20), (200, 200), (20, 200)]
    # A side shorter than five insets is set in by a fifth of it.
    assert projector.starting_points([50.0, 400.0, 10.0])[0] == (10.0, 20.0)


def test_a_bed_point_lands_on_its_pixel_and_a_pixel_returns_to_its_millimetres():
    calibration = _calibration()
    for (x, y), (u, v) in zip(calibration.bed, LIT, strict=True):
        assert projector.bed_to_projector(calibration, x, y) == pytest.approx((u, v))
        assert projector.projector_to_bed(calibration, u, v) == pytest.approx((x, y))
    for x, y in [(0.0, 0.0), (110.0, 110.0), (220.0, 37.5)]:
        lit = projector.bed_to_projector(calibration, x, y)
        assert projector.projector_to_bed(calibration, *lit) == pytest.approx((x, y))


def test_a_bed_that_carries_y_carries_its_points_with_it():
    """Marked with the bed standing 30 mm along Y: a point of the bed lands on its pixel
    with the bed standing there again, and where the room's point under it is lit with
    the bed standing anywhere else."""
    calibration = _calibration(bed_offset=30.0)
    for (x, y), (u, v) in zip(calibration.bed, LIT, strict=True):
        assert projector.bed_to_projector(calibration, x, y, bed_offset=30.0) == pytest.approx(
            (u, v)
        )
    moved = projector.bed_to_projector(calibration, 20.0, 20.0, bed_offset=-50.0)
    assert moved == pytest.approx(projector.bed_to_projector(calibration, 20.0, -60.0, 30.0))
    assert projector.projector_to_bed(calibration, *moved, bed_offset=-50.0) == pytest.approx(
        (20.0, 20.0)
    )


@pytest.mark.parametrize(
    "bed, pixels, said",
    [
        (
            [(20, 20), (110, 20), (200, 20), (20, 200)],
            LIT,
            "points 1, 2 and 3 of the four from lie on one line",
        ),
        (
            projector.starting_points(VOLUME),
            [(400, 900), (1500, 880), (400, 900), (500, 220)],
            "points 1, 2 and 3 of the four onto lie on one line",
        ),
        (projector.starting_points(VOLUME), LIT[:3], "four pixels of the output, not 3"),
        (projector.starting_points(VOLUME), [*LIT[:3], (2000, 10)], "outside the 1920 by 1080"),
        ([(20, 20), (200, 20), (200, float("nan")), (20, 200)], LIT, "two finite numbers"),
    ],
    ids=["three-bed-points-on-a-line", "two-pixels-the-same", "three", "off-the-output", "nan"],
)
def test_a_set_that_fixes_no_mapping_is_refused_saying_why(bed, pixels, said):
    with pytest.raises(projector.Refused, match=said):
        projector.checked("garage", "printer_1", bed, pixels, OUTPUT)


def test_an_output_of_no_size_and_a_name_of_another_shape_are_refused():
    bed = projector.starting_points(VOLUME)
    with pytest.raises(projector.Refused, match="two whole numbers of pixels"):
        projector.checked("garage", "printer_1", bed, LIT, (0, 1080))
    with pytest.raises(projector.Refused, match="no calibration can be kept"):
        projector.checked("garage", "../printer_1", bed, LIT, OUTPUT)


def test_a_calibration_is_kept_per_machine_in_the_state_folder():
    projector.clear("garage", "printer_1")
    projector.clear("garage", "cnc_router")
    assert projector.load("garage", "printer_1") is None
    kept = projector.save(_calibration(bed_offset=-12.5))
    projector.save(_calibration(path="cnc_router"))
    assert projector.load("garage", "printer_1") == kept
    on_disk = json.loads((state_dir() / projector.RECORDS).read_text(encoding="utf-8"))
    row = next(r for r in on_disk["projectors"] if r["path"] == "printer_1")
    assert row["format"] == projector.FORMAT and row["bed_offset"] == -12.5
    assert row["size"] == list(OUTPUT) and row["pixels"][0] == list(LIT[0])
    # Kept again, the machine has one calibration, the newer.
    again = projector.save(_calibration(bed_offset=4.0))
    assert [c.bed_offset for c in projector.records("garage") if c.path == "printer_1"] == [4.0]
    assert projector.load("garage", "printer_1") == again
    assert projector.clear("garage", "printer_1") and not projector.clear("garage", "printer_1")
    assert projector.load("garage", "cnc_router") is not None
    projector.clear("garage", "cnc_router")


# --- over HTTP: the calibration, and what the projector draws -----------------------------

PORT = "/dev/ttyFAKE1"  # the scripted arduino-cli's unmatched board
BOARD = "printer_1.frame_system.mainboard"
CONTROLLER = "cnc_router.frame_system.controller"
SQUARE = """G28
G90
M82
G1 Z0.2 F3000
G1 X10 Y10 F6000
;LAYER_CHANGE
G1 X60 Y10 E1 F1200
G1 X60 Y40 E2
G1 X10 Y40 E3
G1 X10 Y10 E4
G1 Z0.4
;LAYER_CHANGE
G1 X60 Y10 E5
"""
SLOT = """G21
G90
G0 Z5
G0 X10 Y10
G1 Z-1 F300
G1 X30 Y10 F800
G1 X30 Y20
G0 Z5
"""
PUT = {
    "bed": [list(p) for p in projector.starting_points(VOLUME)],
    "pixels": [list(p) for p in LIT],
    "size": list(OUTPUT),
}


@pytest.fixture
def garage(monkeypatch):
    """The garage as it is built, no poll of any port kept, and nothing asked of one: a
    poll here fails the test."""
    sites.store.reset("garage")
    monkeypatch.setattr(devices, "_LAST_STATUS", {})

    def asked(*args, **kwargs):
        raise AssertionError("the projector asked a port something")

    monkeypatch.setattr(devices, "printer_status", asked)
    for path in ("printer_1", "cnc_router"):
        projector.clear("garage", path)
        machine_plans.clear("garage", path)
    yield sites.store.get("garage")
    for path in ("printer_1", "cnc_router"):
        projector.clear("garage", path)
        machine_plans.clear("garage", path)
    sites.store.reset("garage")


@pytest.fixture
def pinned(fake_arduino_cli, garage):
    """The scripted board pinned to printer_1's mainboard."""
    c = TestClient(app)
    c.put(f"/sites/garage/nodes/{BOARD}/device", json={"identity": PORT})
    yield c
    c.delete(f"/sites/garage/nodes/{BOARD}/device")


def _poll(**fields) -> PrinterStatus:
    """A poll someone else made of the board on PORT, kept as any poll is."""
    return devices.notify_status(
        PrinterStatus(port=PORT, polled_at=datetime.now(timezone.utc), **fields)
    )


def test_a_machine_that_is_not_there_is_refused_saying_why(garage):
    c = TestClient(app)
    assert c.get("/sites/garage/machines/nothing/projector").status_code == 404
    shelf = c.get("/sites/garage/machines/workbench/projector")
    assert shelf.status_code == 400 and "no working volume" in shelf.json()["detail"]
    assert c.get("/sites/nowhere/machines/printer_1/projector").status_code == 404
    assert c.put("/sites/garage/machines/workbench/projector", json=PUT).status_code == 400


def test_an_uncalibrated_machine_answers_its_frame_and_says_what_it_does_not_know(garage):
    got = TestClient(app).get("/sites/garage/machines/printer_1/projector").json()
    assert got["format"] == "apothecary.projected/1" and got["kind"] == "printer"
    assert got["calibration"] is None and got["mapping"] is None and got["port"] is None
    assert got["frame"]["volume"] == VOLUME and got["frame"]["bed_moves_y"] == 0.0
    assert got["starting_points"] == [[20, 20], [200, 20], [200, 200], [20, 200]]
    picture = got["picture"]
    assert picture["bed"] == {
        "outline": [[0.0, 0.0], [220.0, 0.0], [220.0, 220.0], [0.0, 220.0]],
        "carries_y": True,
    }
    assert picture["toolpath"] is None and picture["source"] is None
    assert picture["said"] == [
        "nothing streams on this machine, and no plan names a file",
        "not calibrated: four points of the bed are marked on the projector's page (C there)",
    ]
    # No poll kept: no tool, no bed's place, and the band says so rather than guess.
    assert got["moving"] == {
        "tool": None,
        "bed_offset": None,
        "current": None,
        "status": {
            "state": None,
            "polled_at": None,
            "job": None,
            "needs": [],
            "lines": ["no poll kept: this machine's state is not known here"],
        },
        "said": ["the bed carries Y and no poll has said where it stands: nothing on it is drawn"],
    }


def test_a_bed_that_carries_y_is_calibrated_where_a_poll_says_it_stands(pinned):
    c = pinned
    refused = c.put("/sites/garage/machines/printer_1/projector", json=PUT)
    assert refused.status_code == 409 and "no poll has said where it stands" in refused.text
    _poll(position={"x": 50.0, "y": 80.0, "z": 0.2}, tool_position={"x": 50.0, "y": 80.0, "z": 0.2})
    got = c.put("/sites/garage/machines/printer_1/projector", json=PUT)
    assert got.status_code == 200, got.text
    got = got.json()
    kept = projector.load("garage", "printer_1")
    # The Ender's bed stands where the work's Y under the nozzle is 0: at Y 80 it has
    # moved 80 mm toward the front.
    assert kept.bed_offset == -80.0 and got["calibration"]["bed_offset"] == -80.0
    assert got["size"] == list(OUTPUT) and got["port"] == PORT
    for (x, y), (u, v) in zip(kept.bed, LIT, strict=True):
        assert apply(got["mapping"], x, y - 80.0) == pytest.approx((u, v))
    # The tool stands still over a bed that carries Y: at the work's Y 0, X where it was.
    assert got["moving"]["tool"] == [50.0, 0.0] and got["moving"]["bed_offset"] == -80.0
    assert got["moving"]["status"]["lines"] == ["idle"]


def test_a_set_that_fixes_no_mapping_is_refused_over_http_saying_why(pinned):
    _poll(position={"x": 0.0, "y": 0.0, "z": 0.0}, tool_position={"x": 0.0, "y": 0.0, "z": 0.0})
    on_a_line = {**PUT, "bed": [[20, 20], [110, 20], [200, 20], [20, 200]]}
    got = pinned.put("/sites/garage/machines/printer_1/projector", json=on_a_line)
    assert got.status_code == 422
    assert "points 1, 2 and 3 of the four from lie on one line" in got.json()["detail"]
    assert projector.load("garage", "printer_1") is None
    three = pinned.put("/sites/garage/machines/printer_1/projector", json={**PUT, "size": [0, 9]})
    assert three.status_code == 422 and projector.load("garage", "printer_1") is None


def test_the_file_streaming_is_drawn_in_the_bed_s_millimetres_with_its_band(pinned):
    """A print streaming: the moves that lay filament, seen from above, in the bed's
    millimetres, the travel left out; the layer the job is in by the lines it has sent;
    and the band, each figure the poll's."""
    kept = devices.save_print_file("square.gcode", SQUARE.encode(), "printer")
    job = {
        "kind": "print",
        "file_id": kept.id,
        "name": "square.gcode",
        "stage": "printing",
        "sent": 7,
        "total": 11,
        "progress": 7 / 11,
        "running": True,
    }
    _poll(
        state="printing",
        position={"x": 60.0, "y": 40.0, "z": 0.2},
        tool_position={"x": 60.0, "y": 40.0, "z": 0.2},
        job=job,
        todo=["home before moving"],
    )
    got = pinned.get("/sites/garage/machines/printer_1/projector").json()
    picture = got["picture"]
    assert picture["source"] == "job" and picture["file"] == {"id": kept.id, "name": "square.gcode"}
    toolpath = picture["toolpath"]
    # Layer 1's square, edge by edge, then layer 2's first edge: x0, y0, x1, y1 each.
    edges = [(10, 10, 60, 10), (60, 10, 60, 40), (60, 40, 10, 40), (10, 40, 10, 10)]
    assert toolpath["segments"] == [v for edge in [*edges, (10, 10, 60, 10)] for v in edge]
    assert toolpath["left_out"] == ["travel"] and toolpath["origin"] == {"x": 0, "y": 0, "z": 0}
    assert [(g["label"], g["first"], g["count"]) for g in toolpath["groups"]] == [
        ("before the first layer", 0, 0),
        ("layer 1", 0, 4),
        ("layer 2", 4, 1),
    ]
    moving = got["moving"]
    assert moving["current"] == 1 and moving["bed_offset"] == -40.0
    assert moving["status"]["lines"] == [
        "printing",
        "print · square.gcode · printing",
        "64% · line 7 of 11",
        "home before moving",
    ]
    assert moving["status"]["needs"] == ["home before moving"]
    # The plan's file is drawn when nothing streams.
    machine_plans.save("garage", "printer_1", "printer", None, kept.id)
    _poll(position={"x": 0.0, "y": 0.0, "z": 0.0}, tool_position={"x": 0.0, "y": 0.0, "z": 0.0})
    planned = pinned.get("/sites/garage/machines/printer_1/projector").json()
    assert planned["picture"]["source"] == "plan" and planned["moving"]["current"] is None
    assert planned["picture"]["key"] != picture["key"]


DOCS = Path(__file__).resolve().parents[1] / "docs"


def _keys(value) -> set:
    """The keys of a documented object, its "..." (what the docs leave out) not one."""
    return set(value) - {"..."}


def test_the_answer_docs_projector_md_shows_has_the_keys_a_real_answer_has(pinned):
    """docs/projector.md's answer is written by hand: each object of it carries the keys a
    real answer's does -- calibrated, a print streaming -- so a key renamed here turns
    this red rather than the docs quietly wrong."""
    shown = json.loads(
        re.search(
            r"```json\n(.*?)\n```", (DOCS / "projector.md").read_text(encoding="utf-8"), re.S
        )[1]
    )
    kept = devices.save_print_file("square.gcode", SQUARE.encode(), "printer")
    job = {"kind": "print", "file_id": kept.id, "name": "square.gcode", "stage": "printing"}
    job.update(sent=7, total=11, progress=7 / 11, running=True)
    _poll(
        state="printing",
        position={"x": 60.0, "y": 40.0, "z": 0.2},
        tool_position={"x": 60.0, "y": 40.0, "z": 0.2},
        job=job,
    )
    # Calibrated where that poll says the bed stands, which a bed that carries Y needs.
    assert pinned.put("/sites/garage/machines/printer_1/projector", json=PUT).status_code == 200
    real = pinned.get("/sites/garage/machines/printer_1/projector").json()
    for where in (
        "",
        "calibration",
        "picture",
        "picture.bed",
        "picture.file",
        "picture.toolpath",
        "moving",
        "moving.status",
    ):
        doc, got = shown, real
        for part in filter(None, where.split(".")):
            doc, got = doc[part], got[part]
        assert _keys(doc) == set(got), (
            f"{where or 'the answer'}: docs {sorted(_keys(doc))}, real {sorted(got)}"
        )
    assert _keys(shown["frame"]) <= set(real["frame"])
    assert _keys(shown["moving"]["status"]["job"]) <= set(real["moving"]["status"]["job"])
    projector.clear("garage", "printer_1")


def test_a_router_s_toolpath_and_cuts_stand_at_the_work_zero_its_controller_reports(
    fake_arduino_cli, garage
):
    c = TestClient(app)
    c.put(f"/sites/garage/nodes/{CONTROLLER}/device", json={"identity": PORT})
    try:
        kept = devices.save_print_file("slot.nc", SLOT.encode(), "router")
        machine_plans.save("garage", "cnc_router", "router", "router_coupon", kept.id)
        _poll(dialect=GRBL, position={"x": -300.0, "y": -400.0, "z": -10.0})
        unplaced = c.get("/sites/garage/machines/cnc_router/projector").json()
        assert unplaced["kind"] == "router" and unplaced["picture"]["toolpath"] is None
        assert "no poll has said where the work zero stands" in unplaced["picture"]["said"][0]
        assert unplaced["picture"]["cuts"]["why"] == "no poll has said where the work zero stands"
        assert unplaced["moving"]["tool"] is None  # its settings not read: no place for it
        _poll(
            dialect=GRBL,
            position={"x": -300.0, "y": -400.0, "z": -10.0},
            tool_position={"x": 100.0, "y": 200.0, "z": 70.0},
            work_origin={"x": 100.0, "y": 150.0, "z": 50.0},
        )
        got = c.get("/sites/garage/machines/cnc_router/projector").json()
        picture = got["picture"]
        # The plunge is straight down, nothing from above; the rapids are left out.
        assert picture["toolpath"]["segments"] == [110, 160, 130, 160, 130, 160, 130, 170]
        assert picture["toolpath"]["left_out"] == ["rapid"]
        cuts = picture["cuts"]
        assert cuts["part"] == "router_coupon" and cuts["why"] is None
        stock = cuts["shapes"][0]
        assert stock["what"] == "stock" and stock["points"][0] == [100.0, 150.0]
        assert len(cuts["shapes"]) > 1
        # The AnoleX's table carries Y: the tool stands at the work's Y 300, the table moved.
        assert got["moving"]["tool"] == [100.0, 300.0] and got["moving"]["bed_offset"] == 100.0
    finally:
        c.delete(f"/sites/garage/nodes/{CONTROLLER}/device")


def test_forgetting_a_calibration(pinned):
    _poll(position={"x": 0.0, "y": 0.0, "z": 0.0}, tool_position={"x": 0.0, "y": 0.0, "z": 0.0})
    at = "/sites/garage/machines/printer_1/projector"
    assert pinned.put(at, json=PUT).status_code == 200
    assert pinned.delete(at).json() == {"forgotten": True}
    assert pinned.delete(at).json() == {"forgotten": False}
    assert pinned.get(at).json()["calibration"] is None


def test_the_projector_s_listeners_are_kept_once_however_often_it_is_imported():
    """routes/projector.py listens to the polls and the jobs from its import: imported
    again (a reload), it is still one listener of each, not two."""
    said = subprocess.run(
        [
            sys.executable,
            "-c",
            "import importlib\n"
            "import apothecary.routes.projector as p\n"
            "from apothecary import jobs\n"
            "from apothecary.firmware import devices\n"
            "importlib.reload(p)\n"
            "importlib.reload(p)\n"
            "print(sum(f.__name__ == '_relay_poll' for f in devices.STATUS_LISTENERS),"
            " sum(f.__name__ == '_relay_job' for f in jobs.LISTENERS))\n",
        ],
        cwd=Path(__file__).resolve().parents[1],  # this checkout's apothecary, first on the path
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert said.returncode == 0, said.stderr[-2000:]
    assert said.stdout.split() == ["1", "1"]
