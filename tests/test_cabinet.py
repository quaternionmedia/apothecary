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
