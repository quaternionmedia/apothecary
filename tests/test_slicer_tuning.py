"""A printer tuned from what its prints measure (apothecary/slicer/tuning.py): a piece
printed from a kept slice, read, solved into the printer's errors, each setting's change
proposed, applied to its next slices, and the next piece read again.

The printer here is the error model itself: its readings are made from planted terms,
moved by the settings as the relations say. That holds the loop's code and its
arithmetic, and says nothing of a printer or a filament."""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from apothecary import print_tuning as pt
from apothecary import sites
from apothecary.api import app
from apothecary.projects.parts.print_coupon import DEFAULT as COUPON
from apothecary.slicer import service, tuning
from apothecary.slicer.models import Made, Setting, SlicedFor, SliceRecord
from apothecary.slicer.profiles import load_part
from apothecary.state_folder import state_dir

client = TestClient(app)

PLA = {"filament": "Creality Generic PLA", "process": "0.20mm Standard @Creality Ender3"}
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
    """Each part's STL is a box of its declared bounds, built at once."""
    real = service.part_target

    def part_target(name, site=None, path=None, variant=None):
        target = real(name, site=site, path=path, variant=variant)
        b = load_part(name).get_bounds().size
        target.stl = lambda log: _box_stl(b.x, b.y, b.z)
        return target

    monkeypatch.setattr(service, "part_target", part_target)


def _slice(part: str) -> dict:
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


# A printer whose errors at no correction are these: the model's own, planted.
TRUE = {
    "scale_x": 0.004,
    "scale_y": 0.004,
    "scale_z": 0.0,
    "contour": 0.08,
    "hole": 0.1,
    "foot": 0.12,
    "first": -0.06,
}
NEUTRAL = {
    "xy_contour_compensation": 0.0,
    "xy_hole_compensation": 0.0,
    "elefant_foot_compensation": 0.0,
    "filament_shrink": 100.0,
    "filament_shrinkage_compensation_z": 100.0,
}


def _printer_reads(record: dict, true: dict = TRUE) -> dict:
    """What the planted printer's piece reads, printed with the settings ``record`` used:
    each term moved by its setting as its relation says, and each feature its nominal
    plus what the moved terms give. Read twice, a hundredth apart."""
    TRUE = true  # noqa: N806 -- the planted printer this reading is of
    used = {k: tuning._number(_setting(record, k)["value"]) for k in NEUTRAL}
    terms = dict(TRUE)
    for setting in tuning.SETTINGS:
        if setting.key not in used:
            continue
        rel = pt.RELATIONS[setting.relation]
        names = ("scale_x", "scale_y") if setting.term == "scale_xy" else (setting.term,)
        for name in names:
            terms[name] = rel.after(TRUE[name], NEUTRAL[setting.key], used[setting.key])
    out = {}
    for f in COUPON.measures().features:
        value = f.nominal + pt.predicted(f.feature(), terms)
        out[f.name] = [round(value - 0.005, 4), round(value + 0.005, 4)]
    out["fin"] = [0.5, 0.51]
    return out


def test_a_coupon_is_read_solved_applied_and_read_again(fake_orcaslicer, built):
    first = _slice("print_coupon")
    assert [f["name"] for f in first["plan"]["features"]][:3] == ["plate_x", "plate_y", "a_x"]
    # What OrcaSlicer filled where the profiles left the shrinkage out, as its G-code says.
    shrink = _setting(first, "filament_shrink")
    assert shrink["value"] == "100%" and "G-code's configuration" in shrink["source"]
    assert _setting(first, "elefant_foot_compensation")["value"] == "0"

    r = client.post(
        f"/slicer/slices/{first['file_id']}/measured",
        json={"readings": _printer_reads(first), "resolution": 0.01},
    )
    assert r.status_code == 200, r.text
    answer = r.json()
    assert answer["turn"] == "turn-1"
    turn = answer["document"]["turns"][0]
    terms = {t["term"]: t for t in turn["terms"]}
    for name, value in TRUE.items():
        assert terms[name]["determined"] and terms[name]["value"] == pytest.approx(value, abs=1e-3)
    proposed = {p["setting"]: p for p in turn["proposed"]}
    # Half of each error a turn: the walls in by 0.04, the holes and the foot out, the
    # XY shrinkage to 100.2 %; the first layer said, not applied.
    assert proposed["xy_contour_compensation"]["new"] == pytest.approx(-0.04, abs=1e-3)
    assert proposed["xy_hole_compensation"]["new"] == pytest.approx(0.05, abs=1e-3)
    assert proposed["elefant_foot_compensation"]["new"] == pytest.approx(0.06, abs=1e-3)
    assert proposed["filament_shrink"]["new"] == pytest.approx(100.2, abs=1e-2)
    assert proposed["filament_shrinkage_compensation_z"]["new"] is None
    assert proposed["z_offset"]["new"] is None and not proposed["z_offset"]["applies"]
    assert "first-layer-offset, a stub" in proposed["z_offset"]["why"]
    assert turn["walls"][0]["feature"] == "fin"
    assert answer["document"]["settings"] == {}  # nothing applied yet

    applied = client.post("/slicer/tuning/apply", json={**WHERE, **PLA})
    assert applied.status_code == 200, applied.text
    assert {c["setting"] for c in applied.json()["applied"]} == {
        "xy_contour_compensation",
        "xy_hole_compensation",
        "elefant_foot_compensation",
        "filament_shrink",
    }
    again = client.post("/slicer/tuning/apply", json={**WHERE, **PLA})
    assert again.status_code == 422 and "applied already" in again.json()["detail"]

    # The next slice for printer_1 takes them, each with where it came from.
    second = _slice("print_coupon")
    walls = _setting(second, "xy_contour_compensation")
    assert walls["origin"] == "measured" and float(walls["value"]) == pytest.approx(-0.04)
    assert "turn-1 of its Creality Generic PLA tuning" in walls["source"]
    assert _setting(second, "filament_shrink")["value"] == ["100.2%"]

    # Read again: each error half what it was, and the trend says so.
    r = client.post(
        f"/slicer/slices/{second['file_id']}/measured", json={"readings": _printer_reads(second)}
    )
    assert r.status_code == 200, r.text
    doc = r.json()["document"]
    terms = {t["term"]: t for t in doc["turns"][1]["terms"]}
    assert terms["contour"]["value"] == pytest.approx(0.04, abs=1e-3)
    assert terms["hole"]["value"] == pytest.approx(0.05, abs=1e-3)
    assert r.json()["trends"]["xy_contour_compensation"]["state"] == "shrinking"

    # Undo drops turn-2; turn-1's changes are still what the next slices take.
    undone = client.post("/slicer/tuning/undo", json={**WHERE, **PLA})
    assert undone.json()["undone"] == "turn-2"
    assert set(undone.json()["document"]["settings"]) == set(proposed) - {
        "z_offset",
        "filament_shrinkage_compensation_z",
    }
    # Undo turn-1 too: nothing is held, and the next slice takes the profile's own.
    client.post("/slicer/tuning/undo", json={**WHERE, **PLA})
    third = _slice("print_coupon")
    assert _setting(third, "xy_contour_compensation")["origin"] == "printer"


def test_a_box_separates_nothing_and_proposes_nothing(fake_orcaslicer, built):
    record = _slice("calibration_cube")
    assert record["plan"] is None and record["size"] == [10.0, 10.0, 10.0]
    r = client.post(
        f"/slicer/slices/{record['file_id']}/measured",
        json={"readings": {"x": 10.12, "y": 10.08, "z": 9.98}},
    )
    assert r.status_code == 200, r.text
    turn = r.json()["document"]["turns"][0]
    assert not any(t["determined"] for t in turn["terms"])
    assert all(p["new"] is None for p in turn["proposed"])
    assert any(
        "cannot tell scale_x, scale_y, contour and foot apart" in s for s in turn["fit"]["said"]
    )
    assert r.json()["said"] == (
        "calibration_cube read at 3 features: no term determined; not separated: contour, "
        "first, foot, scale_x, scale_y, scale_z; proposed: nothing"
    )
    refused = client.post("/slicer/tuning/apply", json={**WHERE, **PLA})
    assert refused.status_code == 422 and "proposes no change" in refused.json()["detail"]
    # The same piece is read again only once its turn is undone.
    url = f"/slicer/slices/{record['file_id']}/measured"
    twice = client.post(url, json={"readings": {"x": 10.12}})
    assert twice.status_code == 422 and "undo it to read it again" in twice.json()["detail"]
    client.post("/slicer/tuning/undo", json={**WHERE, **PLA})
    # The earlier rule, stated as an assumption: the walls are half the mean.
    r = client.post(
        url,
        json={
            "readings": {"x": 10.12, "y": 10.08},
            "assume": {"scale_x": 0, "scale_y": 0, "foot": 0},
        },
    )
    assert r.status_code == 200, r.text
    (turn,) = r.json()["document"]["turns"]
    terms = {t["term"]: t for t in turn["terms"]}
    assert (
        terms["contour"]["value"] == pytest.approx(0.05) and terms["contour"]["basis"] == "solved"
    )
    assert terms["scale_x"]["basis"] == "assumed"
    walls = next(p for p in turn["proposed"] if p["setting"] == "xy_contour_compensation")
    assert walls["new"] == pytest.approx(-0.025)


def test_a_reading_that_is_not_of_the_piece_keeps_nothing(fake_orcaslicer, built):
    record = _slice("print_coupon")
    url = f"/slicer/slices/{record['file_id']}/measured"
    far = client.post(url, json={"readings": {"a_x": 22.5}})
    assert far.status_code == 422 and "further off than 1 mm" in far.json()["detail"]
    unknown = client.post(url, json={"readings": {"q": 3}})
    assert unknown.status_code == 422 and "has no 'q' to measure" in unknown.json()["detail"]
    assert client.post(url, json={"readings": {"a_x": -1}}).status_code == 422
    assert (
        client.post("/slicer/slices/nothing/measured", json={"readings": {"x": 1}}).status_code
        == 404
    )
    assert client.get("/slicer/tuning", params=WHERE).json() == {"documents": []}


def test_a_slice_for_a_printer_of_no_site_is_tuned_nowhere(fake_orcaslicer, built):
    r = client.post("/slicer/slice", json={"part": "calibration_cube", "printer": "ender3"})
    task = r.json()
    deadline = time.monotonic() + 20
    while task["status"] == "running" and time.monotonic() < deadline:
        time.sleep(0.05)
        task = client.get(f"/slicer/tasks/{task['id']}").json()
    record = task["slice"]["record"]
    r = client.post(f"/slicer/slices/{record['file_id']}/measured", json={"readings": {"x": 10.1}})
    assert r.status_code == 422 and "a printer of no site" in r.json()["detail"]


# ---- the older shape, read once ------------------------------------------------------------


def _older(value: float) -> dict:
    return {
        "site": "garage",
        "printer": "printer_1",
        "setting": "xy_contour_compensation",
        "value": value,
        "measurements": [
            {
                "at": "2026-11-10T12:00:00Z",
                "file_id": "f-older",
                "part": "calibration_cube",
                "sliced": [10.0, 10.0, 10.0],
                "measured": [10.12, 10.08, 9.98],
                "used": 0.0,
                "correction": value,
            }
        ],
    }


def test_a_correction_kept_in_the_older_shape_becomes_the_first_turn(fake_orcaslicer, built):
    old = state_dir() / "corrections" / "garage" / "printer_1.json"
    old.parent.mkdir(parents=True)
    old.write_text(json.dumps(_older(-0.05)))
    router = state_dir() / "corrections" / "garage" / "cnc_router.json"
    router.write_text(json.dumps({"router": "cnc_router", "setting": "tool_allowance"}))

    record = _slice("calibration_cube")
    taken = _setting(record, "xy_contour_compensation")
    assert (taken["value"], taken["origin"]) == ("-0.05", "measured")
    assert not old.exists() and router.exists()
    (doc,) = tuning.documents("garage", "printer_1")
    (turn,) = doc.turns
    assert turn.converted.startswith("the earlier correction of this printer")
    assert turn.assumed == tuning.EARLIER_ASSUMED
    assert turn.term("contour").value == pytest.approx(0.05)
    assert turn.term("first").determined is False  # one height: Z recorded, not applied
    assert [(c.before, c.after) for c in turn.applied] == [(0.0, -0.05)]
    assert doc.settings["xy_contour_compensation"].source == "turn-1"


# ---- the document's own checks -----------------------------------------------------------


def _record() -> SliceRecord:
    return SliceRecord(
        file_id="f1",
        name="print_coupon.gcode",
        at=datetime.now(timezone.utc),
        slicer="orcaslicer",
        made=Made(kind="part", name="print_coupon"),
        printer=SlicedFor(part="ender3", name="printer_1", site="garage", path="printer_1"),
        settings=[
            Setting(name="filament profile", value=PLA["filament"], origin="printer", source="p"),
            Setting(name="process profile", value=PLA["process"], origin="printer", source="p"),
            *(
                Setting(name=k, value=f"{v:g}", origin="printer", source="p")
                for k, v in {
                    **NEUTRAL,
                    "z_offset": 0.0,
                    "layer_height": 0.2,
                    "initial_layer_print_height": 0.2,
                }.items()
            ),
        ],
        size=[54.0, 36.0, 12.0],
        plan=COUPON.measures(),
    )


def _reads(record: SliceRecord, true: dict = TRUE) -> dict:
    return _printer_reads({"settings": [s.model_dump() for s in record.settings]}, true)


def test_x_and_y_that_differ_or_a_z_scale_under_a_layer_propose_nothing():
    record = _record()
    true = {**TRUE, "scale_x": 0.004, "scale_y": -0.004, "scale_z": 0.003}
    _, turn = tuning.add_turn(record, _reads(record, true))
    shrink = turn.proposal("filament_shrink")
    assert shrink.new is None and "steps per millimetre (M92)" in shrink.why
    assert turn.term("scale_x").value == pytest.approx(0.004, abs=1e-4)
    z = turn.proposal("filament_shrinkage_compensation_z")
    assert turn.term("scale_z").resolved
    assert z.new is None and "under half a 0.2 mm layer" in z.why


def _doc_with_a_turn() -> tuning.TuningDocument:
    record = _record()
    tuning.add_turn(record, _reads(record))
    doc, _ = tuning.apply("garage", "printer_1", tuning.AppliesTo(**PLA))
    return doc


def test_a_figure_resting_on_a_turn_the_document_lacks_is_refused():
    doc = _doc_with_a_turn()
    data = doc.model_dump(mode="json", by_alias=True)
    tuning.TuningDocument.model_validate(data)
    # The turn gone, and the setting it applied still held: refused.
    lacking = json.loads(json.dumps(data))
    lacking["turns"] = []
    with pytest.raises(ValueError, match="no turn of this document"):
        tuning.TuningDocument.model_validate(lacking)
    # A change the turn did not propose: refused.
    forged = json.loads(json.dumps(data))
    forged["turns"][0]["applied"][0]["after"] = 0.3
    forged["settings"]["xy_contour_compensation"]["value"] = 0.3
    with pytest.raises(ValueError, match="which it did not propose"):
        tuning.TuningDocument.model_validate(forged)
    # A term solved from no reading that moves it: refused.
    unread = json.loads(json.dumps(data))
    unread["turns"][0]["readings"] = [
        r for r in unread["turns"][0]["readings"] if r["kind"] != "inside"
    ]
    with pytest.raises(ValueError, match="solves hole from no reading"):
        tuning.TuningDocument.model_validate(unread)
    # A reading claiming another turn: refused.
    moved = json.loads(json.dumps(data))
    moved["turns"][0]["readings"][0]["source"] = "turn-9"
    with pytest.raises(ValueError, match="rests on 'turn-9'"):
        tuning.TuningDocument.model_validate(moved)
    r = client.post("/slicer/tuning/validate", json=lacking)
    assert r.status_code == 422 and "no turn of this document" in r.json()["detail"]
    assert client.post("/slicer/tuning/validate", json=data).json()["ok"] is True
