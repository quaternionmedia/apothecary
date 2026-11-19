"""A filament loaded on a printer and its pieces looked at (slicer/filaments.py,
slicer/tuning.py's looks): the filament its next slices take and the tuning they take
with it, each fault seen kept as a look whose one change Apply takes into the next
slice, and Undo takes back out. Through the routes, with a fake OrcaSlicer."""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from apothecary import sites
from apothecary.api import app
from apothecary.slicer import service, tuning
from apothecary.slicer.profiles import load_part

client = TestClient(app)

WHERE = {"site": "garage", "printer": "printer_1"}
PROCESS = "0.20mm Standard @Creality Ender3"


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


def _setting(record: dict, name: str) -> dict:
    return next(s for s in record["settings"] if s["name"] == name)


def test_a_printer_lists_the_filaments_that_fit_it_and_slices_with_the_one_loaded(
    fake_orcaslicer, built
):
    r = client.get("/slicer/filaments", params=WHERE)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["chooses"] is True and body["loaded"] is None
    assert body["profile"] == "Creality Generic PLA"
    # Its profile's own first; a base that cannot be chosen and another machine's are not offered.
    assert [c["name"] for c in body["choices"]] == ["Creality Generic PLA", "Creality Generic PETG"]
    petg = body["choices"][1]
    assert (petg["type"], petg["nozzle_temperature"], petg["bed_temperature"]) == (
        "PETG",
        "255",
        "70",
    )

    # Until one is loaded, a slice says it takes the profile's own.
    first = _slice()
    assert _setting(first, "filament profile")["value"] == "Creality Generic PLA"
    assert "no filament loaded on printer_1 has been said" in _setting(first, "filament")["note"]

    refused = client.post(
        "/slicer/filaments/loaded", json={**WHERE, "filament": "Creality Generic PLA @K1"}
    )
    assert refused.status_code == 422 and "no filament ender3 can load" in refused.json()["detail"]
    r = client.post(
        "/slicer/filaments/loaded",
        json={**WHERE, "filament": "Creality Generic PETG", "note": "black spool"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["loaded"]["filament"] == "Creality Generic PETG" and r.json()["before"] == []

    second = _slice()
    assert _setting(second, "filament profile")["value"] == "Creality Generic PETG"
    assert _setting(second, "nozzle_temperature")["value"] == ["255"]
    note = _setting(second, "filament")["note"]
    assert "loaded on garage's printer_1" in note and "(black spool)" in note

    again = client.post(
        "/slicer/filaments/loaded", json={**WHERE, "filament": "Creality Generic PLA"}
    )
    assert [b["filament"] for b in again.json()["before"]] == ["Creality Generic PETG"]


def test_a_look_keeps_one_change_which_apply_takes_into_the_next_slice(fake_orcaslicer, built):
    first = _slice()
    assert _setting(first, "retraction_length")["value"] == ["4"]
    r = client.post(
        f"/slicer/slices/{first['file_id']}/seen",
        json={
            "seen": {"stringing": 2, "warping": 0},
            "where": {"stringing": "between the X and Y"},
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["look"] == "look-1"
    assert body["said"] == (
        "calibration_cube looked at: stringing clear (between the X and Y); proposed: "
        "filament_retraction_length 4 mm -> 4.5 mm"
    )
    look = body["document"]["looks"][0]
    assert look["slice"]["used"]["retraction_length"] == 4.0
    assert body["faults"] == {"stringing": "clear at look-1", "warping": "none at look-1"}

    # The same piece is looked at again only once its look is undone.
    twice = client.post(f"/slicer/slices/{first['file_id']}/seen", json={"seen": {"stringing": 1}})
    assert twice.status_code == 422 and "undo it to look again" in twice.json()["detail"]

    applies = {**WHERE, "filament": "Creality Generic PLA", "process": PROCESS}
    r = client.post("/slicer/tuning/apply", json=applies)
    assert r.status_code == 200, r.text
    assert [(c["setting"], c["before"], c["after"]) for c in r.json()["applied"]] == [
        ("filament_retraction_length", 4.0, 4.5)
    ]
    second = _slice()
    held = _setting(second, "filament_retraction_length")
    assert held["value"] == ["4.5"] and held["origin"] == "measured"
    assert "look-1 of its Creality Generic PLA tuning, seen on calibration_cube" in held["source"]

    # It shrank: the same lever again.
    r = client.post(f"/slicer/slices/{second['file_id']}/seen", json={"seen": {"stringing": 1}})
    assert r.status_code == 200, r.text
    assert r.json()["said"].endswith(
        "filament_retraction_length 4.5 mm -> 5 mm; stringing: clear -> slight after "
        "filament_retraction_length 4 mm -> 4.5 mm: it governs it"
    )
    # Undo drops that look; the next slice still takes look-1's change.
    r = client.post("/slicer/tuning/undo", json=applies)
    assert r.json()["undone"] == "look-2"
    r = client.post("/slicer/tuning/undo", json=applies)
    assert r.json()["undone"] == "look-1" and r.json()["document"]["settings"] == {}
    assert _setting(_slice(), "filament_retraction_length")["value"] == ["nil"]


def test_a_look_and_a_turn_share_the_document_and_its_order(fake_orcaslicer, built):
    first = _slice()
    r = client.post(f"/slicer/slices/{first['file_id']}/measured", json={"readings": {"x": 10.1}})
    assert r.status_code == 200, r.text
    r = client.post(f"/slicer/slices/{first['file_id']}/seen", json={"seen": {"ringing": 3}})
    assert r.status_code == 200, r.text
    doc = r.json()["document"]
    assert [t["id"] for t in doc["turns"]] == ["turn-1"] and [lk["id"] for lk in doc["looks"]] == [
        "look-1"
    ]
    applies = {**WHERE, "filament": "Creality Generic PLA", "process": PROCESS}
    # Apply takes the newest, the look.
    r = client.post("/slicer/tuning/apply", json=applies)
    assert [c["setting"] for c in r.json()["applied"]] == ["outer_wall_speed"]
    held = r.json()["document"]["settings"]["outer_wall_speed"]
    assert (held["value"], held["source"]) == (30.0, "look-1")
    # Read back whole, the document holds.
    valid = client.post("/slicer/tuning/validate", json=r.json()["document"])
    assert valid.status_code == 200 and valid.json()["looks"] == 1
    assert "look-1: calibration_cube" in tuning.render_markdown(
        tuning.TuningDocument.model_validate(r.json()["document"])
    )


@pytest.mark.parametrize(
    "seen, said",
    [
        ({}, "say what the piece shows"),
        ({"blobs": 2}, "no fault 'blobs'"),
        ({"stringing": 4}, "a severity is 0 (none) to 3 (bad)"),
    ],
)
def test_a_look_that_is_not_one_keeps_nothing(fake_orcaslicer, built, seen, said):
    record = _slice()
    r = client.post(f"/slicer/slices/{record['file_id']}/seen", json={"seen": seen})
    assert r.status_code == 422 and said in r.json()["detail"]
    assert client.get("/slicer/tuning", params=WHERE).json()["documents"] == []


def test_a_figure_of_a_look_that_rests_on_nothing_is_refused(fake_orcaslicer, built):
    record = _slice()
    doc = client.post(
        f"/slicer/slices/{record['file_id']}/seen", json={"seen": {"stringing": 2}}
    ).json()["document"]
    doc["looks"][0]["proposed"][0]["source"] = "look-9"
    assert client.post("/slicer/tuning/validate", json=doc).status_code == 422
    doc["looks"][0]["proposed"][0]["source"] = "look-1"
    doc["looks"][0]["seen"][0]["severity"] = 0
    r = client.post("/slicer/tuning/validate", json=doc)
    assert r.status_code == 422 and "which it did not see" in r.json()["detail"]


def test_the_faults_are_listed_for_the_page():
    body = client.get("/slicer/faults").json()
    assert body["severity"]["0"] == "none" and body["severity"]["3"].startswith("bad")
    stringing = body["faults"][0]
    assert (
        stringing["id"] == "stringing"
        and stringing["levers"][0]["setting"] == "filament_retraction_length"
    )
