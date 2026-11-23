"""A part's cabinet (apothecary/cabinet.py, routes/cabinet.py): a drawer for each piece
made of it, opened as its job begins or as something is first filed of its file, and what
is said of the piece filed there -- calipers' readings, faults seen, notes -- each naming
the printer's turn or look, or the router's allowance, it made. Through the routes, with
a fake OrcaSlicer."""

from __future__ import annotations

import time
from datetime import datetime, timezone

import pytest
from click.testing import CliRunner
from fastapi.testclient import TestClient

from apothecary import cabinet, jobs, sites
from apothecary.api import app
from apothecary.cam import service as cam_service
from apothecary.cam.models import CutFor
from apothecary.cli import cli
from apothecary.firmware import devices
from apothecary.slicer import service
from apothecary.slicer.profiles import load_part

client = TestClient(app)

WHERE = {"site": "garage", "printer": "printer_1"}
CUBE = "calibration_cube"
ROUTER = CutFor(name="cnc_router", site="garage", path="cnc_router", port="/dev/ttySIM")


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


def _slice(part: str = CUBE) -> dict:
    r = client.post("/slicer/slice", json={"part": part, **WHERE})
    assert r.status_code == 202, r.text
    task = r.json()
    deadline = time.monotonic() + 20
    while task["status"] == "running" and time.monotonic() < deadline:
        time.sleep(0.05)
        task = client.get(f"/slicer/tasks/{task['id']}").json()
    assert task["status"] == "succeeded", task["lines"]
    return task["slice"]["record"]


def _job(file_id: str, name: str, *, kind: str = "print", outcome: str = "running") -> jobs.Job:
    started = datetime(2026, 11, 20, 12, 0, tzinfo=timezone.utc)
    return jobs.Job(
        id=jobs.new_id(started, "/dev/ttyFAKE0"),
        kind=kind,
        machine=jobs.JobMachine(
            kind="printer" if kind == "print" else "router", port="/dev/ttyFAKE0"
        ),
        site="garage",
        input=jobs.JobInput(name=name, sha256="ab" * 32, file_id=file_id),
        started_at=started,
        finished_at=None if outcome == "running" else started,
        outcome=outcome,
    )


def test_a_slice_s_drawer_keeps_what_made_it_and_what_is_filed(fake_orcaslicer, built):
    """Opened for a kept slice, the drawer names the file, the printer, the filament and
    process, the STL's hash; a reading files the printer's turn, a look its look, a note
    itself, each in order, and the drawer's line counts them."""
    record = _slice()
    assert len(record["stl_sha256"]) == 64
    r = client.post(f"/cabinet/{CUBE}/drawers", json={"file_id": record["file_id"]})
    assert r.status_code == 200, r.text
    drawer = r.json()
    assert (drawer["made"], drawer["file"]["file_id"], drawer["machine"]["path"]) == (
        "print",
        record["file_id"],
        "printer_1",
    )
    assert (
        drawer["filament"] == "Creality Generic PLA"
        and drawer["stl_sha256"] == record["stl_sha256"]
    )
    assert drawer["slice"]["file_id"] == record["file_id"] and drawer["tuning"] is None
    # Asked again, the same drawer: one piece, one drawer.
    again = client.post(f"/cabinet/{CUBE}/drawers", json={"file_id": record["file_id"]}).json()
    assert again["id"] == drawer["id"]

    at = f"/cabinet/{CUBE}/drawers/{drawer['id']}"
    r = client.post(f"{at}/measured", json={"readings": {"x": 10.1}})
    assert r.status_code == 200, r.text
    assert (
        r.json()["turn"] == "turn-1"
        and r.json()["tuning"]["document"]["turns"][0]["id"] == "turn-1"
    )
    r = client.post(
        f"{at}/seen", json={"seen": {"stringing": 2}, "where": {"stringing": "the top"}}
    )
    assert r.status_code == 200, r.text
    assert r.json()["look"] == "look-1"
    r = client.post(f"{at}/note", json={"note": "a little rough on the top face"})
    assert r.status_code == 200, r.text
    filed = r.json()["filed"]
    assert [(f["id"], f["kind"], f["made"]) for f in filed] == [
        ("filed-1", "measured", "turn-1"),
        ("filed-2", "look", "look-1"),
        ("filed-3", "note", None),
    ]
    assert filed[0]["readings"] == {"x": [10.1]}
    assert filed[1]["seen"] == [{"fault": "stringing", "severity": 2, "where": "the top"}]
    assert r.json()["said"] == f"noted on {drawer['id']}"
    listed = client.get(f"/cabinet/{CUBE}").json()["drawers"]
    assert [d["id"] for d in listed] == [drawer["id"]] and "slice" not in listed[0]
    assert listed[0]["line"] == "print on printer_1 (Creality Generic PLA): no job here; 3 filed"
    assert client.get("/cabinet").json() == {"parts": [CUBE]}


def test_take_turn_and_undo_turn_from_the_drawer_and_an_undone_filing_says_so(
    fake_orcaslicer, built
):
    record = _slice()
    drawer = client.post(f"/cabinet/{CUBE}/drawers", json={"file_id": record["file_id"]}).json()
    at = f"/cabinet/{CUBE}/drawers/{drawer['id']}"
    assert client.post(f"{at}/seen", json={"seen": {"stringing": 2}}).status_code == 200
    r = client.post(f"{at}/tune/apply")
    assert r.status_code == 200, r.text
    assert [c["setting"] for c in r.json()["applied"]] == ["filament_retraction_length"]
    assert (
        r.json()["said"] == "Taken for printer_1's next slices: filament_retraction_length 4.5 mm"
    )
    r = client.post(f"{at}/tune/undo")
    assert r.status_code == 200, r.text
    assert r.json()["undone"] == "look-1" and r.json()["filed"][0]["undone"] is not None
    assert r.json()["said"] == "look-1 undone" and r.json()["line"].endswith("no job here")
    # Nothing left to undo: said, and the filing stays as it was.
    r = client.post(f"{at}/tune/undo")
    assert r.status_code == 422
    assert client.post(f"{at}/tune/sideways").status_code == 404


def test_the_slicer_s_own_routes_file_into_the_part_s_drawer_too(fake_orcaslicer, built):
    record = _slice()
    r = client.post(f"/slicer/slices/{record['file_id']}/measured", json={"readings": {"x": 10.1}})
    assert r.status_code == 200, r.text
    where = r.json()["drawer"]
    assert where["part"] == CUBE
    r = client.post(f"/slicer/slices/{record['file_id']}/seen", json={"seen": {"ringing": 3}})
    assert r.json()["drawer"] == where
    applies = {
        **WHERE,
        "filament": "Creality Generic PLA",
        "process": "0.20mm Standard @Creality Ender3",
    }
    assert client.post("/slicer/tuning/undo", json=applies).json()["undone"] == "look-1"
    drawer = client.get(f"/cabinet/{CUBE}/drawers/{where['id']}").json()
    assert [(f["made"], f["undone"] is None) for f in drawer["filed"]] == [
        ("turn-1", True),
        ("look-1", False),
    ]


def test_a_piece_is_measured_from_its_drawer_after_its_file_is_forgotten(fake_orcaslicer, built):
    record = _slice()
    drawer = client.post(f"/cabinet/{CUBE}/drawers", json={"file_id": record["file_id"]}).json()
    assert devices.delete_print_file(record["file_id"])
    assert client.get(f"/slicer/slices/{record['file_id']}").status_code == 404
    r = client.post(
        f"/cabinet/{CUBE}/drawers/{drawer['id']}/measured", json={"readings": {"x": 10.1}}
    )
    assert r.status_code == 200, r.text
    assert r.json()["filed"][0]["made"] == "turn-1"


def test_a_job_opens_its_piece_s_drawer_and_its_end_says_how_it_ended(fake_orcaslicer, built):
    record = _slice()
    began = _job(record["file_id"], record["name"])
    cabinet.job_told(began)
    (drawer,) = cabinet.drawers(CUBE)
    assert drawer.job.id == began.id and drawer.job.outcome == "running"
    assert drawer.file.sha256 == "ab" * 32
    cabinet.job_told(began.model_copy(update={"outcome": "done", "finished_at": began.started_at}))
    (drawer,) = cabinet.drawers(CUBE)
    assert drawer.job.outcome == "done"
    found = client.get("/cabinet", params={"job": began.id}).json()["drawer"]
    assert found == {"part": CUBE, "id": drawer.id}
    assert client.get("/cabinet", params={"job": "nothing"}).json()["drawer"] is None
    # Filed by its file, the piece goes into that drawer.
    r = client.post(f"/slicer/slices/{record['file_id']}/seen", json={"seen": {"stringing": 1}})
    assert r.json()["drawer"]["id"] == drawer.id
    # A filing on the drawer as it was read before the job ended keeps the end told.
    stale = cabinet.for_slice(service.get_record(record["file_id"]))
    assert cabinet.noted(stale.model_copy(update={"job": None}), "rough top").job.outcome == "done"
    # The same file printed again is another piece, in a drawer of its own.
    second = _job(record["file_id"], record["name"]).model_copy(update={"id": began.id + "-2"})
    cabinet.job_told(second)
    assert [d.job.id for d in cabinet.drawers(CUBE)] == [second.id, began.id]
    # A tune, or a file nothing sliced, opens nothing.
    cabinet.job_told(_job(record["file_id"], record["name"], kind="tune"))
    cabinet.job_told(_job("nothing", "nothing.gcode"))
    assert len(cabinet.drawers(CUBE)) == 2


def test_a_print_that_stopped_says_its_layer_and_a_fault_seen_is_placed_there(
    fake_orcaslicer, built
):
    """A print cancelled part way says, in its drawer, the layer its last line sent was
    in, of the file's layers; a fault seen on the piece is filed on that layer unless
    placed elsewhere. A drawer kept before the cabinet said it is told when read."""
    from apothecary.firmware.gcode import strip_gcode

    record = _slice()
    text = (devices.prints_dir() / f"{record['file_id']}.gcode").read_text(encoding="utf-8")
    lines = text.splitlines()
    first = next(i for i, line in enumerate(lines) if line.startswith(";LAYER_CHANGE"))
    start = sum(1 for line in lines[:first] if strip_gcode(line))
    total = sum(1 for line in lines if strip_gcode(line))
    layers = text.count(";LAYER_CHANGE")
    assert cabinet.stopped_at(text, start, total).said() == (
        f"in its start, before the first of {layers} layers"
    )
    assert cabinet.stopped_at(text, start + 1, total).layer == 1
    assert cabinet.stopped_at(text, total, total).layer == layers
    assert cabinet.stopped_at("G28\nG1 X1\n", 1, 2) is None  # a file that marks no layers

    began = _job(record["file_id"], record["name"])
    cabinet.job_told(began)
    ended = began.model_copy(
        update={
            "outcome": "cancelled",
            "finished_at": began.started_at,
            "detail": {"sent": start + 2, "total": total},
        }
    )
    jobs.end(ended)
    (drawer,) = cabinet.drawers(CUBE)
    assert drawer.job.stopped.said() == f"on layer 1 of {layers}"
    r = client.post(
        f"/cabinet/{CUBE}/drawers/{drawer.id}/seen",
        json={"seen": {"first_layer": 3, "stringing": 1}, "where": {"stringing": "the top"}},
    )
    assert r.status_code == 200, r.text
    seen = {s["fault"]: s["where"] for s in r.json()["filed"][-1]["seen"]}
    assert seen == {"first_layer": f"on layer 1 of {layers}", "stringing": "the top"}

    # Kept before the cabinet said where it stopped: told when read, and kept so.
    old = drawer.model_copy(update={"job": drawer.job.model_copy(update={"stopped": None})})
    cabinet._write(old)
    assert cabinet.get(CUBE, drawer.id).job.stopped.layer == 1
    # A print that finished says no layer.
    done = _job(record["file_id"], record["name"]).model_copy(update={"id": began.id + "-2"})
    cabinet.job_told(done)
    jobs.end(done.model_copy(update={"outcome": "done", "finished_at": done.started_at}))
    assert cabinet.drawers(CUBE)[0].job.stopped is None


def test_a_cut_s_drawer_is_measured_by_its_sizes_and_keeps_the_router_s_allowance():
    record = cam_service.cut_into("router_emoji", ROUTER)
    r = client.post("/cabinet/router_emoji/drawers", json={"file_id": record.file_id})
    assert r.status_code == 200, r.text
    drawer = r.json()
    assert (drawer["made"], drawer["machine"]["kind"], drawer["allowance"]) == (
        "cut",
        "router",
        None,
    )
    at = f"/cabinet/router_emoji/drawers/{drawer['id']}"
    r = client.post(f"{at}/measured", json={"readings": {"face": 59.9, "eye": None}})
    assert r.status_code == 200, r.text
    assert r.json()["said"].endswith("tool_allowance +0.000 -> +0.100 mm")
    assert r.json()["allowance"]["value"] == 0.1
    assert r.json()["filed"][0]["readings"] == {"face": [59.9]}
    assert client.post(f"{at}/seen", json={"seen": {"stringing": 1}}).status_code == 422
    assert client.post(f"{at}/tune/apply").status_code == 422
    # The cam route files there as well.
    r = client.post(f"/cam/cuts/{record.file_id}/measured", json={"sizes": {"face": 59.95}})
    assert r.status_code == 200 and r.json()["drawer"]["id"] == drawer["id"]


def test_what_cannot_be_filed_is_said_and_nothing_kept(fake_orcaslicer, built):
    record = _slice()
    assert (
        client.post("/cabinet/print_coupon/drawers", json={"file_id": record["file_id"]}).json()[
            "detail"
        ]
        == f"{record['file_id']} made {CUBE}, not print_coupon"
    )
    assert client.post(f"/cabinet/{CUBE}/drawers", json={"file_id": "nothing"}).status_code == 404
    assert client.get(f"/cabinet/{CUBE}/drawers/20261120T120000.000").status_code == 404
    assert client.get("/cabinet/..%2Fjobs").status_code in (404, 422)
    drawer = client.post(f"/cabinet/{CUBE}/drawers", json={"file_id": record["file_id"]}).json()
    at = f"/cabinet/{CUBE}/drawers/{drawer['id']}"
    assert (
        client.post(f"{at}/note", json={"note": "  "}).json()["detail"] == "a note says something"
    )
    r = client.post(f"{at}/measured", json={"readings": {"x": 0}})
    assert r.status_code == 422 and "each over 0 mm" in r.json()["detail"]
    assert client.get(at).json()["filed"] == []


def test_the_cabinet_at_the_command_line_lists_drawers_and_shows_one(fake_orcaslicer, built):
    record = _slice()
    drawer = client.post(f"/cabinet/{CUBE}/drawers", json={"file_id": record["file_id"]}).json()
    client.post(f"/cabinet/{CUBE}/drawers/{drawer['id']}/note", json={"note": "first piece"})
    out = CliRunner().invoke(cli, ["cabinet"])
    assert out.exit_code == 0, out.output
    assert out.output.splitlines() == [f"{CUBE}: 1 drawer"]
    out = CliRunner().invoke(cli, ["cabinet", CUBE])
    assert out.exit_code == 0, out.output
    assert out.output.splitlines() == [
        f"{drawer['id']}  print on printer_1 (Creality Generic PLA): no job here; 1 filed"
    ]
    out = CliRunner().invoke(cli, ["cabinet", CUBE, drawer["id"]])
    assert out.exit_code == 0, out.output
    lines = out.output.splitlines()
    assert (
        lines[0]
        == f"{CUBE} {drawer['id']}: print on printer_1 (Creality Generic PLA): no job here; 1 filed"
    )
    assert f"file: {record['name']} ({record['file_id']})" in lines
    assert lines[-1].endswith("note: first piece")
    out = CliRunner().invoke(cli, ["cabinet", CUBE, "20261120T120000.000"])
    assert out.exit_code != 0 and f"{CUBE} has no drawer 20261120T120000.000" in out.output


def test_a_reading_is_checked_against_its_design_and_kept_in_the_piece_s_dimensions(
    fake_orcaslicer, built
):
    """A printed cube's dimensions are its box's, each designed 10 mm, checked within the
    0.1 mm its print settings declare. A reading files its check -- designed, the mean
    read, the deviation, the tolerance and whose -- and the dimension carries it as its
    newest reading. The piece read again is a check alone, no second turn; Undo turn takes
    the first filing's reading back out of the dimensions."""
    record = _slice()
    drawer = client.post(f"/cabinet/{CUBE}/drawers", json={"file_id": record["file_id"]}).json()
    assert drawer["dimensions"]["drawer"] == drawer["id"]
    at = f"/cabinet/{CUBE}/drawers/{drawer['id']}"
    dims = client.get(f"/cabinet/{CUBE}/dimensions", params={"drawer": drawer["id"]}).json()
    assert [(d["name"], d["designed"], d["frame"], d["reading"]) for d in dims["dimensions"]] == [
        ("x", 10.0, "box", None),
        ("y", 10.0, "box", None),
        ("z", 10.0, "box", None),
    ]
    assert dims["tolerance"] == {
        "value": 0.1,
        "source": "part",
        "said": f"{CUBE}'s print settings",
    }
    assert (dims["made"], dims["machine"], dims["file_id"]) == (
        "print",
        "printer_1",
        record["file_id"],
    )
    assert dims["size"] == record["size"] == [10.0, 10.0, 10.0]

    r = client.post(f"{at}/measured", json={"readings": {"x": [10.04, 10.06]}})
    assert r.status_code == 200, r.text
    assert r.json()["turn"] == "turn-1"
    (check,) = r.json()["filed"][0]["checked"]
    assert check == {
        "name": "x",
        "designed": 10.0,
        "measured": 10.05,
        "deviation": pytest.approx(0.05),
        "tolerance": 0.1,
        "tolerance_from": "part",
        "within": True,
    }
    x = r.json()["dimensions"]["dimensions"][0]
    assert x["reading"]["filed"] == "filed-1" and x["reading"]["checked"]["within"] is True
    assert x["reading"]["read"] == [10.04, 10.06] and x["reading"]["made"] == "turn-1"

    # Read again: kept as a check, the printer's tuning unmoved.
    r = client.post(f"{at}/measured", json={"readings": {"y": 10.25}})
    assert r.status_code == 200, r.text
    assert r.json()["turn"] is None
    assert [t["id"] for t in r.json()["tuning"]["document"]["turns"]] == ["turn-1"]
    assert r.json()["said"] == (
        "y 10.25 mm against 10.00 designed, +0.25: outside ± 0.10: kept as a check of the "
        "piece, and no turn: turn-1 already reads it for printer_1's tuning"
    )
    (filed,) = r.json()["filed"][1:]
    assert (filed["kind"], filed["made"], filed["said"]) == ("measured", None, r.json()["said"])
    y = r.json()["dimensions"]["dimensions"][1]
    assert y["reading"]["checked"]["within"] is False and y["reading"]["filed"] == "filed-2"

    # Undo turn: the first filing struck, its reading no longer the dimension's.
    assert client.post(f"{at}/tune/undo").status_code == 200
    names = {d["name"]: d["reading"] for d in client.get(at).json()["dimensions"]["dimensions"]}
    assert names["x"] is None and names["y"]["filed"] == "filed-2"


def test_the_tolerance_is_the_part_s_else_the_printer_s_profile_s_else_a_default(monkeypatch):
    """The part's declared tolerance first; else what the printer's profile holds under
    measured; else PrintSettings' own, said to be a default. A cut piece's is a default."""
    from apothecary.slicer import profiles
    from apothecary.slicer.models import Made, Setting, SlicedFor, SliceRecord

    def record(declared=None):
        settings = [Setting(name="layer_height", value="0.2", origin="printer", source="p")]
        if declared is not None:
            settings.append(
                Setting(name="tolerance", value=declared, origin="declared", source="part x")
            )
        return SliceRecord(
            file_id="f1",
            name="x.gcode",
            at=datetime(2026, 11, 22, tzinfo=timezone.utc),
            slicer="orcaslicer",
            made=Made(kind="part", name="footpedal"),
            printer=SlicedFor(part="ender3", name="printer_1", site="garage", path="printer_1"),
            settings=settings,
            size=[30.0, 20.0, 10.0],
        )

    said = cabinet.tolerance_of("footpedal", record(0.15))
    assert (said.value, said.source, said.said) == (0.15, "part", "footpedal's print settings")
    said = cabinet.tolerance_of("footpedal", record())
    assert (said.value, said.source) == (cabinet.DEFAULT_TOLERANCE, "default")
    assert said.said == (
        "a default, 0.2 mm: neither footpedal's print settings nor printer_1's profile states one"
    )
    real = profiles.load_profile

    def held(name):
        profile = real(name)
        profile.measured["tolerance"] = profiles.Measured(
            value=0.25, unit="mm", source="a bench's cube", used="a printed piece's check"
        )
        return profile

    monkeypatch.setattr(profiles, "load_profile", held)
    said = cabinet.tolerance_of("footpedal", record())
    assert (said.value, said.source, said.said) == (
        0.25,
        "printer",
        "printer_1's profile, parts/ender3/slicer.json",
    )
    assert cabinet.tolerance_of("footpedal", record(0.15)).source == "part"
    cut = cabinet.tolerance_of("router_emoji", None)
    assert (cut.source, cut.said) == (
        "default",
        "a default, 0.2 mm: nothing states one for a cut piece",
    )


def test_a_piece_s_dimensions_are_the_drawer_named_the_file_named_or_the_newest(
    fake_orcaslicer, built
):
    """Nothing made: none, and why. A kept slice no drawer holds: its dimensions as
    designed. A drawer: the newest, or the one named; a file of another part refused."""
    none = client.get(f"/cabinet/{CUBE}/dimensions").json()
    assert none["dimensions"] == [] and none["why"] == (
        f"nothing made of {CUBE} yet: its print or its cut opens a drawer in Part › Feedback"
    )
    record = _slice()
    kept = client.get(f"/cabinet/{CUBE}/dimensions").json()
    assert (kept["drawer"], kept["file_id"]) == (None, record["file_id"])
    assert [d["name"] for d in kept["dimensions"]] == ["x", "y", "z"]
    by_file = client.get(f"/cabinet/{CUBE}/dimensions", params={"file": record["file_id"]})
    assert by_file.json() == kept
    drawer = client.post(f"/cabinet/{CUBE}/drawers", json={"file_id": record["file_id"]}).json()
    assert client.get(f"/cabinet/{CUBE}/dimensions").json()["drawer"] == drawer["id"]
    assert (
        client.get(f"/cabinet/{CUBE}/dimensions", params={"file": record["file_id"]}).json()[
            "drawer"
        ]
        == drawer["id"]
    )
    other = client.get("/cabinet/print_coupon/dimensions", params={"file": record["file_id"]})
    assert other.status_code == 422
    assert other.json()["detail"] == f"{record['file_id']} made {CUBE}, not print_coupon"
    missing = client.get(f"/cabinet/{CUBE}/dimensions", params={"drawer": "20261120T120000.000"})
    assert missing.status_code == 404


def test_a_cut_piece_s_sizes_are_checked_with_a_default_tolerance():
    record = cam_service.cut_into("router_emoji", ROUTER)
    drawer = client.post("/cabinet/router_emoji/drawers", json={"file_id": record.file_id}).json()
    dims = drawer["dimensions"]
    assert dims["made"] == "cut" and dims["tolerance"]["source"] == "default"
    face = next(d for d in dims["dimensions"] if d["name"] == "face")
    assert face["frame"] == "none" and face["reading"] is None
    r = client.post(
        f"/cabinet/router_emoji/drawers/{drawer['id']}/measured",
        json={"readings": {"face": face["designed"] - 0.1, "eye": None}},
    )
    assert r.status_code == 200, r.text
    (check,) = r.json()["filed"][0]["checked"]
    assert check["name"] == "face" and check["deviation"] == pytest.approx(-0.1)
    face = next(d for d in r.json()["dimensions"]["dimensions"] if d["name"] == "face")
    assert face["reading"]["checked"]["within"] is True


def test_a_part_s_plan_gives_its_dimensions_in_its_own_frame(fake_orcaslicer, built):
    """The print coupon names its plan: its dimensions are the plan's features, in the
    order to read them, each with the line its jaws close along in the part's own frame."""
    record = _slice("print_coupon")
    dims = client.get("/cabinet/print_coupon/dimensions").json()
    assert dims["file_id"] == record["file_id"] and dims["drawer"] is None
    names = [d["name"] for d in dims["dimensions"]]
    assert names[:3] == ["plate_x", "plate_y", "a_x"] and len(names) == len(
        record["plan"]["features"]
    )
    first, planned = dims["dimensions"][0], record["plan"]["features"][0]
    assert first["frame"] == "part"
    assert (first["at"], first["faces"], first["axis"]) == (
        planned["at"],
        planned["faces"],
        planned["axis"],
    )
    assert first["designed"] == planned["nominal"]


def test_a_printed_shim_s_thickness_is_a_dimension_of_its_piece(fake_orcaslicer, built):
    """bed_shims names each shim's thickness: a slice of it at its defaults gives three
    heights in the part's frame, and a shim read files the printer's turn, checked within
    the default tolerance, since the part's print settings state none."""
    record = _slice("bed_shims")
    drawer = client.post("/cabinet/bed_shims/drawers", json={"file_id": record["file_id"]}).json()
    dims = drawer["dimensions"]
    assert [(d["name"], d["kind"], d["frame"], d["designed"]) for d in dims["dimensions"]] == [
        ("shim_fl", "height", "part", 0.5),
        ("shim_br", "height", "part", 0.5),
        ("shim_bl", "height", "part", 0.5),
    ]
    assert dims["tolerance"]["source"] == "default"
    r = client.post(
        f"/cabinet/bed_shims/drawers/{drawer['id']}/measured", json={"readings": {"shim_br": 0.56}}
    )
    assert r.status_code == 200, r.text
    assert r.json()["turn"] == "turn-1"
    (check,) = r.json()["filed"][0]["checked"]
    assert (check["name"], check["within"]) == ("shim_br", True)
    assert check["deviation"] == pytest.approx(0.06)
