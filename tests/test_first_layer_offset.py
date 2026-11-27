"""A printer's first-layer offset (slicer/first_layer_offset.py): kept in its Print window,
said by GET /slicer/first-layer, and taken by every slice made for it after as
OrcaSlicer's z_offset, with its source. Through the routes, with a fake OrcaSlicer."""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from apothecary import sites
from apothecary.api import app
from apothecary.slicer import first_layer_offset, service
from apothecary.slicer.profiles import load_part, load_profile

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


def _z_offset(record: dict) -> dict:
    return next(s for s in record["settings"] if s["name"] == "z_offset")


def test_a_kept_offset_is_what_the_printers_next_slices_take(fake_orcaslicer, built):
    asked = client.get("/slicer/first-layer", params={"part": "calibration_cube", **WHERE})
    assert asked.status_code == 200, asked.text
    offset = asked.json()["offset"]
    assert offset["named"] is True and offset["value"] == 0.0 and offset["kept"] is None
    assert offset["words"] == "as the probe puts it"
    assert (
        offset["choices"][0] == -0.5 and offset["choices"][-1] == 0.5 and 0.0 in offset["choices"]
    )
    assert -0.05 in offset["choices"] and len(offset["choices"]) == 21

    # Until one is kept, a slice's z_offset is 0, said as none kept.
    first = _z_offset(_slice())
    assert first["value"] == "0" and first["origin"] == "printer"
    assert "no first-layer offset kept for garage's printer_1 yet" in first["source"]

    r = client.post(
        "/slicer/first-layer/offset",
        json={**WHERE, "offset": -0.05, "note": "square's lines round and apart"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["value"] == -0.05 and body["words"] == "0.05 mm lower"
    assert body["kept"]["note"] == "square's lines round and apart"

    second = _z_offset(_slice())
    assert second["value"] == "-0.05" and second["origin"] == "measured"
    assert "first-layer-offset: garage's printer_1, kept" in second["source"]
    assert "(square's lines round and apart)" in second["source"]
    assert second["note"] == "the nozzle 0.05 mm lower than the probe puts it"

    # Kept again: the one before is kept with it, and the next slice takes the newest.
    again = client.post("/slicer/first-layer/offset", json={**WHERE, "offset": 0.1})
    assert again.status_code == 200 and again.json()["words"] == "0.10 mm higher"
    held = first_layer_offset.kept("garage", "printer_1")
    assert [b.offset for b in held.before] == [-0.05] and held.kept.offset == 0.1
    assert _z_offset(_slice())["value"] == "0.1"


@pytest.mark.parametrize(
    "offset, said",
    [
        (-0.6, "within 0.5 mm either way, not -0.6"),
        (0.51, "within 0.5 mm either way"),
        (0.055, "kept to a hundredth of a mm"),
    ],
)
def test_an_offset_out_of_its_bounds_is_refused_and_nothing_is_kept(offset, said):
    r = client.post("/slicer/first-layer/offset", json={**WHERE, "offset": offset})
    assert r.status_code == 422 and said in r.json()["detail"], r.text
    assert first_layer_offset.kept("garage", "printer_1") is None


def test_a_printer_whose_profile_names_no_offset_keeps_none_and_its_slices_are_untouched():
    profile = load_profile("ender3")
    without = profile.model_copy(
        update={"start": profile.start.model_copy(update={"modules": ["home"]})}
    )
    with pytest.raises(first_layer_offset.Refused, match="names no start piece"):
        first_layer_offset.keep(without, "garage", "printer_1", -0.05)
    assert first_layer_offset.applied(without, "garage", "printer_1", "orcaslicer") is without
    assert first_layer_offset.answer(without, "garage", "printer_1")["named"] is False
    # Another slicer's slice is not touched either.
    assert first_layer_offset.applied(profile, "garage", "printer_1", "another") is profile


def test_the_square_is_sliced_with_the_first_layer_a_shim_has(fake_orcaslicer, built):
    """first_layer_square declares the first layer bed_shims prints with: the bed probed
    first, no brim, no skirt; and one layer of it, so its slice takes the offset kept."""
    asked = client.get("/slicer/first-layer", params={"part": "first_layer_square", **WHERE})
    body = asked.json()
    assert body["levelling"] == {"value": "probe-each-print", "by": "part"}
    assert body["adhesion"] == {"by": "part", "brim_width": 0.0}
    assert (
        client.post("/slicer/first-layer/offset", json={**WHERE, "offset": -0.1}).status_code == 200
    )
    record = _slice("first_layer_square")
    shown = {s["name"]: s for s in record["settings"]}
    assert shown["start"]["value"] == ["home", "first-layer-offset", "probe-each-print"]
    assert shown["skirt_loops"]["value"] == "0" and shown["brim_type"]["value"] == "no_brim"
    assert shown["z_offset"]["value"] == "-0.1"
    assert record["size"][2] == pytest.approx(0.2)
