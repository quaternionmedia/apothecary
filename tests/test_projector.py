"""A projector aimed at a machine's bed (apothecary/projector.py): four points of the
bed and the four pixels lighting them fix one mapping each way, a bed that carries Y
carries its points with it, a set that fixes no mapping is refused saying why, and a
machine's calibration is kept in the state folder. Over HTTP (routes/projector.py): the
calibration kept and refused, and what the projector draws -- the file streaming or
planned, in the bed's millimetres, the tool where a poll put it, and the band -- read
from the polls kept, never by asking a port."""

from __future__ import annotations

import json
import math
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
    # Calibrated where that poll says the bed stands, which a bed that carries Y needs, on
    # the bed plane and at a second plane.
    lens = Pinhole()
    assert _marked(pinned, lens).status_code == 200
    assert _marked(pinned, lens, height=20.0).status_code == 200
    real = pinned.get("/sites/garage/machines/printer_1/projector").json()
    for where in (
        "",
        "calibration",
        "calibration.upper",
        "plane",
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
    assert _keys(shown["plane"]["wanted"]) == set(real["plane"]["wanted"])
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


# --- a height: a second plane, held against a pinhole projector whose answers are computed
# --- here, apart from the code under test -------------------------------------------------


class Pinhole:
    """A projector's lens at ``eye`` in the room, aimed at ``target``: a point (x, y, z) of
    the room lands at the pixel its ray through the lens meets the output, worked out from
    the geometry, never from a mapping the code under test returns."""

    def __init__(self, eye=(150.0, -420.0, 1800.0), target=(110.0, 110.0, 0.0), focal=2600.0):
        def sub(a, b):
            return [p - q for p, q in zip(a, b, strict=True)]

        def unit(a):
            n = math.sqrt(sum(v * v for v in a))
            return [v / n for v in a]

        def cross(a, b):
            return [
                a[1] * b[2] - a[2] * b[1],
                a[2] * b[0] - a[0] * b[2],
                a[0] * b[1] - a[1] * b[0],
            ]

        self.eye, self.focal = eye, focal
        self.forward = unit(sub(target, eye))
        self.right = unit(cross(self.forward, [0.0, 1.0, 0.0]))
        self.down = cross(self.forward, self.right)

    def pixel(self, x, y, z=0.0):
        d = [x - self.eye[0], y - self.eye[1], z - self.eye[2]]
        along = sum(a * b for a, b in zip(d, self.forward, strict=True))
        across = sum(a * b for a, b in zip(d, self.right, strict=True))
        down = sum(a * b for a, b in zip(d, self.down, strict=True))
        return (960 + self.focal * across / along, 540 + self.focal * down / along)

    def calibration(self, height=None, offset=0.0, bed=None, **noise):
        marked = projector.starting_points(VOLUME) if bed is None else bed
        lit = [self.pixel(x, y + offset) for x, y in marked]
        first = projector.checked("garage", "printer_1", marked, lit, OUTPUT, bed_offset=offset)
        if height is None:
            return first
        up = [self.pixel(x, y + offset, height) for x, y in marked]
        return projector.checked_upper(first, up, OUTPUT, height, bed_offset=offset)


PROBES = [(0.0, 0.0), (110.0, 110.0), (220.0, 40.0), (35.0, 200.0), (210.0, 210.0)]


@pytest.mark.parametrize("height", [10.0, 25.0, 60.0])
def test_a_plane_at_any_height_is_the_pinhole_s_between_at_and_beyond_the_two(height):
    """Two planes of one pinhole projector fix every plane over the bed, exactly: the plane
    at z is the interpolation of the two, up to REACH times the second's height."""
    lens = Pinhole()
    calibration = lens.calibration(height)
    for z in [0.0, height / 4, height / 2, height, 1.5 * height, projector.REACH * height]:
        matrix = projector.mapping_at(calibration, z)
        for x, y in PROBES:
            assert apply(matrix, x, y) == pytest.approx(lens.pixel(x, y, z), abs=1e-6), (z, x, y)


def test_the_two_planes_are_each_true_where_they_were_marked_whatever_a_hand_got_wrong():
    lens = Pinhole()
    marked = projector.starting_points(VOLUME)
    first = projector.checked(
        "garage", "printer_1", marked, [lens.pixel(x, y) for x, y in marked], OUTPUT
    )
    off = [(u + dx, v + dy) for (u, v), (dx, dy) in zip(
        [lens.pixel(x, y, 30.0) for x, y in marked], [(2, -1), (-1, 2), (1, 1), (-2, 0)],
        strict=True,
    )]
    both = projector.checked_upper(first, off, OUTPUT, 30.0)
    for (x, y), (u, v) in zip(marked, off, strict=True):
        assert apply(projector.mapping_at(both, 30.0), x, y) == pytest.approx((u, v), abs=1e-6)
    for (x, y), (u, v) in zip(marked, first.pixels, strict=True):
        assert apply(projector.mapping_at(both, 0.0), x, y) == pytest.approx((u, v), abs=1e-6)


def test_a_second_plane_marked_on_another_canvas_is_scaled_to_the_first_s_output():
    lens = Pinhole()
    marked = projector.starting_points(VOLUME)
    first = projector.checked(
        "garage", "printer_1", marked, [lens.pixel(x, y) for x, y in marked], OUTPUT
    )
    half = [(lens.pixel(x, y, 20.0)[0] / 2, lens.pixel(x, y, 20.0)[1] / 2) for x, y in marked]
    both = projector.checked_upper(first, half, (960, 540), 20.0)
    got = apply(projector.mapping_at(both, 20.0), 110.0, 110.0)
    assert got == pytest.approx(lens.pixel(110.0, 110.0, 20.0), abs=1e-6)


def test_a_bed_that_carries_y_has_both_planes_in_the_room():
    """Each plane marked with the bed standing where it stood then: the planes are of the
    room, so the offsets may differ."""
    lens = Pinhole()
    marked = projector.starting_points(VOLUME)
    first = projector.checked(
        "garage", "printer_1", marked,
        [lens.pixel(x, y - 30.0) for x, y in marked], OUTPUT, bed_offset=-30.0,
    )
    up = [lens.pixel(x, y + 10.0, 15.0) for x, y in marked]
    both = projector.checked_upper(first, up, OUTPUT, 15.0, bed_offset=10.0)
    got = apply(projector.mapping_at(both, 7.5), 50.0, 70.0)
    assert got == pytest.approx(lens.pixel(50.0, 70.0, 7.5), abs=1e-6)


def test_a_second_plane_with_other_points_than_the_first_s_fixes_the_same_planes():
    lens = Pinhole()
    block = [(60.0, 60.0), (160.0, 60.0), (160.0, 160.0), (60.0, 160.0)]
    first = lens.calibration()
    up = [lens.pixel(x, y, 18.0) for x, y in block]
    both = projector.checked_upper(first, up, OUTPUT, 18.0, bed=block)
    assert apply(projector.mapping_at(both, 9.0), 200.0, 30.0) == pytest.approx(
        lens.pixel(200.0, 30.0, 9.0), abs=1e-6
    )


def test_a_second_plane_is_refused_saying_why():
    lens = Pinhole()
    first = lens.calibration()
    marked = first.bed
    up = [lens.pixel(x, y, 20.0) for x, y in marked]
    # The same height: a plane under a millimetre above the bed is the bed plane.
    with pytest.raises(projector.Refused, match="fix no height"):
        projector.checked_upper(first, up, OUTPUT, 0.4)
    with pytest.raises(projector.Refused, match="finite number"):
        projector.checked_upper(first, up, OUTPUT, float("nan"))
    with pytest.raises(projector.Refused, match="past 500"):
        projector.checked_upper(first, up, OUTPUT, 900.0)
    # Points that fix no mapping, and pixels off the output.
    line = [(40.0, 40.0), (80.0, 40.0), (120.0, 40.0), (40.0, 90.0)]
    with pytest.raises(projector.Refused, match="second plane fixes no mapping.*on one line"):
        projector.checked_upper(first, up, OUTPUT, 20.0, bed=line)
    with pytest.raises(projector.Refused, match="outside the 1920 by 1080"):
        projector.checked_upper(first, [*up[:3], (5000.0, 5.0)], OUTPUT, 20.0)
    # Marked where the bed plane's were: no height told.
    with pytest.raises(projector.Refused, match="pixels are the bed plane's"):
        projector.checked_upper(first, first.pixels, OUTPUT, 20.0)
    # Corners marked in another order than the first's are not of one plane over the bed.
    with pytest.raises(projector.Refused, match="does not agree with the bed plane's"):
        projector.checked_upper(first, up[::-1], OUTPUT, 20.0)


def test_a_height_is_refused_below_the_bed_with_one_plane_and_beyond_the_reach():
    lens = Pinhole()
    one = lens.calibration()
    assert projector.mapping_at(one, 0.0) == projector.mapping(one)
    with pytest.raises(projector.Refused, match="only the bed plane is calibrated"):
        projector.mapping_at(one, 5.0)
    two = lens.calibration(20.0)
    with pytest.raises(projector.Refused, match="below the bed plane"):
        projector.mapping_at(two, -1.0)
    projector.mapping_at(two, 40.0)  # twice the second plane's: the reach
    with pytest.raises(projector.Refused, match="past 2 times the second plane's 20 mm"):
        projector.mapping_at(two, 40.5)
    with pytest.raises(projector.Refused, match="finite"):
        projector.mapping_at(two, float("inf"))


def test_a_plane_at_the_projector_s_lens_is_refused_not_drawn_inside_out():
    """A projector 100 mm over the bed, tilted: a point in front of the bed that a plane 40 mm
    up still lights is behind the lens plane at 80 mm, where a pinhole's picture is inside
    out, and the plane is refused there (the volume's own corners are asked)."""
    lens = Pinhole(eye=(110.0, -50.0, 100.0), target=(110.0, 110.0, 0.0), focal=60.0)
    calibration = lens.calibration(40.0)
    front = [(110.0, -80.0)]
    projector.mapping_at(calibration, 40.0, over=front)
    with pytest.raises(projector.Refused, match="reaches the projector's lens plane over 110, -80"):
        projector.mapping_at(calibration, 80.0, over=front)
    projector.mapping_at(calibration, 80.0)  # no point asked: the bed's own are well in front


def test_a_calibration_with_a_second_plane_is_kept_and_read_again(garage):
    lens = Pinhole()
    both = lens.calibration(20.0)
    projector.save(both)
    kept = projector.load("garage", "printer_1")
    assert kept.upper is not None and kept.upper.height == 20.0 and kept == both
    # A first calibration marked again forgets the second plane: the projector may have moved.
    projector.save(lens.calibration())
    assert projector.load("garage", "printer_1").upper is None


# --- over HTTP: a height, and the plane the picture is drawn for ------------------------------

AT = "/sites/garage/machines/printer_1/projector"
HOME = {"position": {"x": 0.0, "y": 0.0, "z": 0.0}, "tool_position": {"x": 0.0, "y": 0.0, "z": 0.0}}


def _marked(c, lens, height=None, path="printer_1"):
    """The machine's four points marked on a pinhole projector's output at ``height`` mm
    above the bed (the bed plane with none), kept as a page's drag keeps them."""
    at = f"/sites/garage/machines/{path}/projector"
    got = c.get(at).json()
    kept = got["calibration"] if height is not None else None
    bed = kept["bed"] if kept else got["starting_points"]
    up = 0.0 if height is None else height
    offset = got["moving"]["bed_offset"] or 0.0  # the bed stands where its poll says
    lit = [list(lens.pixel(x, y + offset, up)) for x, y in bed]
    if height is None:
        return c.put(at, json={"bed": bed, "pixels": lit, "size": list(OUTPUT)})
    return c.put(
        f"{at}/upper", json={"pixels": lit, "size": list(OUTPUT), "height": height}
    )


def test_with_one_calibration_the_plane_is_the_bed_s_and_the_answer_says_so(pinned):
    _poll(**HOME)
    lens = Pinhole()
    assert _marked(pinned, lens).status_code == 200
    got = pinned.get(AT).json()
    plane = got["plane"]
    assert plane["z"] == 0.0 and plane["for"] == "the bed plane" and plane["how"] == "bed plane only"
    assert plane["mapping"] == got["mapping"] and plane["heights"] == [0.0]
    assert plane["line"].startswith("drawn for the bed plane -- bed plane only") and got["upper_mapping"] is None
    assert got["calibration"]["upper"] is None
    # A height asked for needs a second plane, and is refused saying so.
    asked = pinned.get(AT, params={"height": 12})
    assert asked.status_code == 422 and "only the bed plane is calibrated" in asked.json()["detail"]
    assert pinned.get(AT, params={"height": 0}).status_code == 200


def test_a_second_plane_is_kept_over_http_and_a_height_asked_is_drawn_for(pinned):
    _poll(**HOME)
    lens = Pinhole()
    refused = _marked(pinned, lens, height=20.0)
    assert refused.status_code == 409 and "no calibration of the bed plane" in refused.text
    assert _marked(pinned, lens).status_code == 200
    got = _marked(pinned, lens, height=20.0)
    assert got.status_code == 200, got.text
    got = got.json()
    assert got["calibration"]["upper"]["height"] == 20.0 and got["plane"]["heights"] == [0.0, 20.0]
    # Nothing is drawn for a height: the bed plane, and the band's line says so.
    assert got["plane"]["z"] == 0.0 and got["plane"]["how"] == "measured at the bed plane"
    assert got["plane"]["line"] == (
        "drawn for the bed plane (measured at the bed plane; planes calibrated at 0 and 20 mm)"
    )
    for z in (5.0, 20.0, 31.0, 40.0):
        asked = pinned.get(AT, params={"height": z}).json()["plane"]
        assert asked["z"] == z and asked["for"] == "the height asked"
        for x, y in PROBES:
            assert apply(asked["mapping"], x, y) == pytest.approx(lens.pixel(x, y, z), abs=1e-3)
    assert pinned.get(AT, params={"height": 5}).json()["plane"]["how"] == (
        "between the two calibrated planes"
    )
    assert pinned.get(AT, params={"height": 31}).json()["plane"]["said"][0].startswith(
        "31 mm is past the second plane's 20 mm"
    )
    beyond = pinned.get(AT, params={"height": 41})
    assert beyond.status_code == 422 and "past 2 times the second plane's 20 mm" in beyond.text
    assert pinned.get(AT, params={"height": -3}).status_code == 422
    # The second plane's own mapping is of the pixels marked on it.
    assert apply(got["upper_mapping"], 20.0, 20.0) == pytest.approx(lens.pixel(20.0, 20.0, 20.0))
    # Marked again at the same height as the bed: refused, and the second plane kept is the old.
    same = pinned.put(
        f"{AT}/upper", json={"pixels": got["calibration"]["pixels"], "size": list(OUTPUT), "height": 20}
    )
    assert same.status_code == 422 and "pixels are the bed plane's" in same.json()["detail"]
    low = pinned.put(f"{AT}/upper", json={"pixels": got["calibration"]["pixels"], "size": list(OUTPUT), "height": 0.2})
    assert low.status_code == 422 and "fix no height" in low.json()["detail"]
    assert projector.load("garage", "printer_1").upper.height == 20.0
    # Forgotten alone, the bed plane's calibration stays; marked again, the bed plane's drops it.
    assert pinned.delete(f"{AT}/upper").json() == {"forgotten": True}
    assert pinned.delete(f"{AT}/upper").json() == {"forgotten": False}
    assert projector.load("garage", "printer_1").upper is None
    assert _marked(pinned, lens, height=20.0).status_code == 200
    assert _marked(pinned, lens).status_code == 200
    assert projector.load("garage", "printer_1").upper is None


def test_the_streaming_layer_s_own_height_is_what_a_printer_is_drawn_for(pinned):
    """A print's current layer stands where the file says (its own Z): with a second plane
    marked the picture is drawn for that height, the band says which layer, and with none it
    is drawn on the bed plane and says what that leaves displaced."""
    kept = devices.save_print_file("square.gcode", SQUARE.encode(), "printer")
    job = {"kind": "print", "file_id": kept.id, "name": "square.gcode", "stage": "printing"}
    job.update(sent=7, total=11, progress=7 / 11, running=True)
    _poll(state="printing", job=job, **HOME)
    lens = Pinhole()
    assert _marked(pinned, lens).status_code == 200
    one = pinned.get(AT).json()
    layer = [g for g in one["picture"]["toolpath"]["groups"] if g["label"] == "layer 1"]
    assert layer and one["moving"]["current"] == 1
    assert one["plane"]["z"] == 0.0 and one["plane"]["how"] == "bed plane only"
    assert one["plane"]["wanted"]["for"] == "layer 1" and one["plane"]["wanted"]["z"] > 0
    assert "layer 1 stands" in one["plane"]["said"][0]
    z = one["plane"]["wanted"]["z"]
    assert _marked(pinned, lens, height=20.0).status_code == 200
    two = pinned.get(AT).json()
    assert two["plane"]["z"] == z and two["plane"]["for"] == "layer 1"
    assert two["plane"]["how"] == "between the two calibrated planes"
    assert f"drawn for layer 1, {z:g} mm above the bed" in two["plane"]["line"]
    for x, y in PROBES:
        assert apply(two["plane"]["mapping"], x, y) == pytest.approx(lens.pixel(x, y, z), abs=1e-3)
    # What a poll moves carries the plane, so the page that takes only that stays right.
    from apothecary.routes.projector import moved

    assert moved("garage", "printer_1")["plane"] == two["plane"]


def test_a_router_is_drawn_for_its_stock_s_top_where_its_controller_puts_the_work_zero(
    fake_arduino_cli, garage
):
    c = TestClient(app)
    c.put(f"/sites/garage/nodes/{CONTROLLER}/device", json={"identity": PORT})
    at = "/sites/garage/machines/cnc_router/projector"
    try:
        kept = devices.save_print_file("slot.nc", SLOT.encode(), "router")
        machine_plans.save("garage", "cnc_router", "router", "router_coupon", kept.id)
        poll = dict(
            dialect=GRBL,
            position={"x": -300.0, "y": -400.0, "z": -10.0},
            tool_position={"x": 100.0, "y": 200.0, "z": 70.0},
        )
        _poll(**poll, work_origin={"x": 100.0, "y": 150.0, "z": 12.0})
        lens = Pinhole(eye=(200.0, -300.0, 1800.0), target=(200.0, 300.0, 0.0))
        assert _marked(c, lens, path="cnc_router").status_code == 200
        assert _marked(c, lens, height=20.0, path="cnc_router").status_code == 200
        plane = c.get(at).json()["plane"]
        assert plane["for"] == "the stock's top" and plane["z"] == 12.0
        assert plane["how"] == "between the two calibrated planes"
        offset = c.get(at).json()["moving"]["bed_offset"]
        for x, y in PROBES:
            lit = lens.pixel(x, y + offset, 12.0)
            assert apply(plane["mapping"], x, y + offset) == pytest.approx(lit, abs=1e-3)
        # A work zero past twice the second plane's height: drawn on the bed plane, saying why.
        _poll(**poll, work_origin={"x": 100.0, "y": 150.0, "z": 55.0})
        far = c.get(at).json()["plane"]
        assert far["z"] == 0.0 and far["how"] == "bed plane: the height is refused"
        assert far["wanted"] == {"z": 55.0, "for": "the stock's top"}
        assert "past 2 times the second plane's 20 mm" in far["said"][0]
        # No work zero said: nothing to draw for, the bed plane.
        _poll(**poll)
        none = c.get(at).json()["plane"]
        assert none["wanted"] is None and none["z"] == 0.0
    finally:
        c.delete(f"/sites/garage/nodes/{CONTROLLER}/device")


# --- a printer plan's footprint -----------------------------------------------------------


def test_a_printer_plan_s_part_is_outlined_on_the_bed_before_it_is_sliced(garage):
    """No file yet: the part's declared bounds, centred on the bed as the slicer arranges one
    part, and said to be planned; a plan naming no part, and a router's, outline nothing."""
    from apothecary.projects.parts.skeleton import ROOT
    from apothecary.projects.registry import part_named

    c = TestClient(app)
    assert c.get(AT).json()["picture"]["footprint"] is None
    machine_plans.save("garage", "printer_1", "printer", None, None)
    assert c.get(AT).json()["picture"]["footprint"] is None
    machine_plans.save("garage", "printer_1", "printer", "calibration_cube", None)
    got = c.get(AT).json()["picture"]
    box = part_named("calibration_cube", ROOT).get_bounds()
    sx, sy = box.max_point.x - box.min_point.x, box.max_point.y - box.min_point.y
    footprint = got["footprint"]
    assert footprint["source"] == "plan" and footprint["part"] == "calibration_cube"
    assert footprint["size"] == [sx, sy] and sx > 0 and sy > 0
    xs = [p[0] for p in footprint["points"]]
    ys = [p[1] for p in footprint["points"]]
    # Centred on the 220 by 220 bed, a closed rectangle.
    assert (min(xs) + max(xs)) / 2 == pytest.approx(110.0, abs=0.01)
    assert (min(ys) + max(ys)) / 2 == pytest.approx(110.0, abs=0.01)
    assert footprint["points"][0] == footprint["points"][-1] and len(footprint["points"]) == 5
    assert any(
        line.startswith("planned footprint of calibration_cube") and "not sliced yet" in line
        for line in got["said"]
    ), got["said"]
    # A piece of the site named by its path is the part it was made from.
    machine_plans.save("garage", "printer_1", "printer", "no_such_part", None)
    gone = c.get(AT).json()["picture"]
    assert gone["footprint"] is None and any("no_such_part" in line for line in gone["said"])
    # A router's plan is drawn as its cuts: no footprint.
    machine_plans.save("garage", "cnc_router", "router", "router_coupon", None)
    assert c.get("/sites/garage/machines/cnc_router/projector").json()["picture"]["footprint"] is None


def test_once_a_file_exists_the_footprint_is_its_first_layer_s_outline(garage):
    kept = devices.save_print_file("square.gcode", SQUARE.encode(), "printer")
    c = TestClient(app)
    before = None
    machine_plans.save("garage", "printer_1", "printer", "calibration_cube", None)
    before = c.get(AT).json()["picture"]
    machine_plans.save("garage", "printer_1", "printer", "calibration_cube", kept.id)
    after = c.get(AT).json()["picture"]
    footprint = after["footprint"]
    assert before["footprint"]["source"] == "plan" and footprint["source"] == "toolpath"
    # The first layer's square, as the file lays it, closed; no word of a plan said.
    assert sorted(map(tuple, footprint["points"][:-1])) == [
        (10.0, 10.0), (10.0, 40.0), (60.0, 10.0), (60.0, 40.0)
    ]
    assert footprint["points"][0] == footprint["points"][-1]
    assert not any("planned footprint" in line for line in after["said"])
    assert before["key"] != after["key"]
