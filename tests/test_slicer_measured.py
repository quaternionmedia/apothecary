"""A part a printer made, measured: checked against what was sliced, and fed back as
the printer's correction, which its next slices take (apothecary/slicer/measured.py)."""

from __future__ import annotations

import time
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from apothecary import sites
from apothecary.api import app
from apothecary.slicer import measured, service
from apothecary.slicer.models import Made, Setting, SlicedFor, SliceRecord

client = TestClient(app)


def _box_stl(x: float, y: float, z: float) -> bytes:
    """An ASCII STL whose points span a box of x by y by z mm from the origin."""
    facets = (
        ((0, 0, 0), (x, 0, 0), (x, y, 0)),
        ((0, 0, z), (0, y, z), (x, y, z)),
    )
    lines = ["solid box"]
    for facet in facets:
        lines += ["facet normal 0 0 0", "outer loop"]
        lines += [f"vertex {a} {b} {c}" for a, b, c in facet]
        lines += ["endloop", "endfacet"]
    return ("\n".join(lines + ["endsolid box"]) + "\n").encode()


@pytest.fixture(autouse=True)
def garage(tmp_path, monkeypatch):
    monkeypatch.setenv("APOTHECARY_STATE_DIR", str(tmp_path / "state"))
    sites.store.reset("garage")
    yield sites.store.get("garage")
    sites.store.reset("garage")


@pytest.fixture
def cube_built(monkeypatch):
    """The calibration cube's STL is a 10 mm box, built at once."""
    real = service.part_target

    def part_target(name, site=None, path=None):
        target = real(name, site=site, path=path)
        target.stl = lambda log: _box_stl(10, 10, 10)
        return target

    monkeypatch.setattr(service, "part_target", part_target)


def _slice(body: dict) -> dict:
    r = client.post("/slicer/slice", json=body)
    assert r.status_code == 202, r.text
    task = r.json()
    deadline = time.monotonic() + 20
    while task["status"] == "running" and time.monotonic() < deadline:
        time.sleep(0.05)
        task = client.get(f"/slicer/tasks/{task['id']}").json()
    assert task["status"] == "succeeded", task["lines"]
    return task["slice"]["record"]


def _setting(record: dict, name: str) -> dict:
    return next(s for s in record["settings"] if s["name"] == name)


def test_a_part_measured_is_fed_back_into_the_printers_next_slice(fake_orcaslicer, cube_built):
    first = _slice({"part": "calibration_cube", "site": "garage", "printer": "printer_1"})
    assert first["size"] == [10.0, 10.0, 10.0]
    assert _setting(first, "xy_contour_compensation")["value"] in ("0", 0)
    assert _setting(first, "xy_contour_compensation")["origin"] == "printer"

    # Two walls over by a tenth between them: each wall moved in by half of it.
    r = client.post(
        f"/slicer/slices/{first['file_id']}/measured", json={"x": 10.12, "y": 10.08, "z": 9.98}
    )
    assert r.status_code == 200, r.text
    answer = r.json()
    assert answer["correction"]["value"] == -0.05
    assert answer["said"] == (
        "calibration_cube measured X +0.12, Y +0.08, Z -0.02 mm against what was sliced; "
        "xy_contour_compensation +0.000 -> -0.050 mm"
    )
    kept = client.get("/slicer/corrections", params={"site": "garage", "printer": "printer_1"})
    (measurement,) = kept.json()["correction"]["measurements"]
    assert measurement["measured"] == [10.12, 10.08, 9.98] and measurement["used"] == 0.0

    # The next slice for printer_1 takes it, as the printer's measured value.
    second = _slice({"part": "calibration_cube", "site": "garage", "printer": "printer_1"})
    fed = _setting(second, "xy_contour_compensation")
    assert (fed["value"], fed["origin"]) == ("-0.05", "measured")
    assert fed["source"].startswith(
        "garage's printer_1, measured: calibration_cube measured X +0.12"
    )

    # Measured again from that slice: the correction moves from what it was made with.
    r = client.post(f"/slicer/slices/{second['file_id']}/measured", json={"x": 10.02, "y": 10.0})
    assert r.status_code == 200, r.text
    assert r.json()["correction"]["value"] == -0.055
    assert len(r.json()["correction"]["measurements"]) == 2


def test_a_measurement_that_is_not_of_the_slices_part_keeps_nothing(fake_orcaslicer, cube_built):
    record = _slice({"part": "calibration_cube", "site": "garage", "printer": "printer_1"})
    url = f"/slicer/slices/{record['file_id']}/measured"
    off = client.post(url, json={"x": 10.6, "y": 10.0})
    assert off.status_code == 422 and "more than 5% off" in off.json()["detail"]
    z_alone = client.post(url, json={"z": 10.0})
    assert z_alone.status_code == 422 and "measure X or Y" in z_alone.json()["detail"]
    assert client.post(url, json={"x": -1}).status_code == 422
    assert client.post("/slicer/slices/nothing-such/measured", json={"x": 10}).status_code == 404
    kept = client.get("/slicer/corrections", params={"site": "garage", "printer": "printer_1"})
    assert kept.json() == {"correction": None}


def test_a_slice_for_a_printer_of_no_site_keeps_no_correction(fake_orcaslicer, cube_built):
    record = _slice({"part": "calibration_cube", "printer": "ender3"})
    r = client.post(f"/slicer/slices/{record['file_id']}/measured", json={"x": 10.1})
    assert r.status_code == 422 and "a printer of no site" in r.json()["detail"]


def test_a_correction_past_what_moving_the_walls_corrects_is_refused():
    """A part a hundred millimetres wide, made with the walls already moved in by 0.3 mm
    and measured a millimetre over: half a millimetre more is past what a contour
    corrects, and nothing is kept."""
    record = SliceRecord(
        file_id="f1",
        name="bar.gcode",
        at=datetime.now(timezone.utc),
        slicer="orcaslicer",
        made=Made(kind="part", name="bar"),
        printer=SlicedFor(part="ender3", name="printer_1", site="garage", path="printer_1"),
        settings=[
            Setting(name="xy_contour_compensation", value="-0.3", origin="measured", source="kept")
        ],
        size=[100.0, 20.0, 5.0],
    )
    with pytest.raises(measured.Refused, match="past 0.5 mm"):
        measured.measure(record, [101.0, None, None])
    assert measured.load("garage", "printer_1") is None
