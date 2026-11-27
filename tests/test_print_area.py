"""A printer's print area from its plate as kept (slicer/print_area.py): the rectangle
between the front-left and back-right corners Here kept, its slices' printable_area, with
its source; the profile's own where a corner is not kept or the two are no plate apart.
Through the routes, with a fake OrcaSlicer."""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from apothecary import bed_shims, sites
from apothecary.api import app
from apothecary.slicer import service
from apothecary.slicer.profiles import load_part

client = TestClient(app)

WHERE = {"site": "garage", "printer": "printer_1"}


def _box_stl(x: float, y: float, z: float) -> bytes:
    facets = (((0, 0, 0), (x, 0, 0), (x, y, 0)), ((0, 0, z), (0, y, z), (x, y, z)))
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
def built(monkeypatch):
    real = service.part_target

    def part_target(name, site=None, path=None, variant=None):
        target = real(name, site=site, path=path, variant=variant)
        b = load_part(name).get_bounds().size
        target.stl = lambda log: _box_stl(b.x, b.y, b.z)
        return target

    monkeypatch.setattr(service, "part_target", part_target)


def _slice(part: str = "calibration_cube") -> dict:
    r = client.post("/slicer/slice", json={"part": part, **WHERE})
    assert r.status_code == 202, r.text
    task = r.json()
    deadline = time.monotonic() + 20
    while task["status"] == "running" and time.monotonic() < deadline:
        time.sleep(0.05)
        task = client.get(f"/slicer/tasks/{task['id']}").json()
    assert task["status"] == "succeeded", task["lines"]
    return task["slice"]["record"]


def _area(record: dict) -> dict:
    return next(s for s in record["settings"] if s["name"] == "printable_area")


def test_the_plate_kept_is_the_print_area_of_the_printers_next_slices(fake_orcaslicer, built):
    first = _area(_slice())
    assert first["value"] == ["0x0", "220x0", "220x220", "0x220"]
    assert first["origin"] == "printer"

    bed_shims.keep_position("garage", "printer_1", "plate_front_left", 2.5, 4)
    # One corner alone is no plate: the profile's own still.
    assert _area(_slice())["value"] == first["value"]
    bed_shims.keep_position("garage", "printer_1", "plate_back_right", 298, 301.5)
    kept = _area(_slice())
    assert kept["value"] == ["2.5x4", "298x4", "298x301.5", "2.5x301.5"]
    assert kept["origin"] == "measured"
    assert "garage's printer_1: its plate kept with Here" in kept["source"]
    assert kept["note"] == "295.5 x 297.5 mm, over the profile's 0x0, 220x0, 220x220, 0x220"


def test_corners_no_plate_apart_leave_the_profiles_area(fake_orcaslicer, built):
    bed_shims.keep_position("garage", "printer_1", "plate_front_left", 100, 100)
    bed_shims.keep_position("garage", "printer_1", "plate_back_right", 120, 300)
    assert _area(_slice())["value"] == ["0x0", "220x0", "220x220", "0x220"]
    # Kept the wrong way round, the same.
    bed_shims.keep_position("garage", "printer_1", "plate_back_right", 20, 20)
    assert _area(_slice())["origin"] == "printer"
