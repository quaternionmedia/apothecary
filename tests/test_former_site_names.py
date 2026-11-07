"""A site that took another name keeps what was kept under the one before
(apothecary/site_names.py): the universe, ``apothecary``, was ``parts_library``.

Each test makes the state it reads, in a state folder of its own.
"""

import json
from datetime import datetime, timezone

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from firmware_helpers import _isolate_firmware_state

from apothecary import api, jobs
from apothecary.family import procedures
from apothecary.firmware import devices
from apothecary.site_names import FORMER, UNIVERSE, current, former
from apothecary.state_folder import state_dir
from apothecary.vision import cameras

client = TestClient(api.app)

# A pin as it was written while the universe was the parts library.
PIN = {
    "site": "parts_library",
    "path": "creality_v422",
    "identity": "A106ZTEU",
    "bound_at": "2026-10-20T18:04:11.120000Z",
}


@pytest.fixture(autouse=True)
def _a_state_folder_of_its_own(monkeypatch, tmp_path):
    _isolate_firmware_state(monkeypatch, tmp_path)


def _state_file():
    path = devices.state_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _kept(**state):
    _state_file().write_text(json.dumps(state), encoding="utf-8")


def test_the_names():
    assert FORMER == {"parts_library": UNIVERSE}
    assert current("parts_library") == UNIVERSE and current("garage") == "garage"
    assert former(UNIVERSE) == ["parts_library"] and former("garage") == []


def test_a_pin_kept_under_the_former_name_is_found_under_the_universe():
    _kept(bindings=[PIN])
    state = devices.get_state()
    (pin,) = state.bindings(UNIVERSE)
    assert (pin.site, pin.path, pin.identity) == (UNIVERSE, "creality_v422", "A106ZTEU")
    assert pin.bound_at == datetime(2026, 10, 20, 18, 4, 11, 120000, tzinfo=timezone.utc)
    assert state.bindings("parts_library") == []
    assert [b.site for b in state.bindings()] == [UNIVERSE]


def test_reading_a_pin_writes_nothing():
    _kept(bindings=[PIN])
    before = _state_file().read_bytes()
    devices.get_state().bindings(UNIVERSE)
    assert _state_file().read_bytes() == before


def test_the_pin_is_the_universes_node_and_every_view_of_pins_says_so(fake_arduino_cli):
    _kept(bindings=[PIN])
    rows = client.get(f"/sites/{UNIVERSE}/devices").json()["bindings"]
    row = next(r for r in rows if r["path"] == "creality_v422")
    assert row["binding_source"] == "manual"
    (pinned,) = client.get("/firmware/pins").json()["pins"]
    assert (pinned["site"], pinned["path"], pinned["identity"]) == (
        UNIVERSE,
        "creality_v422",
        "A106ZTEU",
    )
    assert pinned["site_known"] and pinned["node_found"]


def test_a_pin_written_again_is_written_under_the_universe_once():
    _kept(bindings=[PIN, {**PIN, "site": "garage", "path": "printer_1.frame_system.mainboard"}])
    devices.get_state().set_binding(UNIVERSE, "creality_v422", "A106ZTEU")
    kept = json.loads(_state_file().read_text())["bindings"]
    assert sorted((b["site"], b["path"]) for b in kept) == [
        (UNIVERSE, "creality_v422"),
        ("garage", "printer_1.frame_system.mainboard"),
    ]


def test_a_pin_kept_under_the_former_name_is_taken_back_by_the_name_it_has_now():
    _kept(bindings=[PIN])
    assert client.delete(f"/firmware/pins/{UNIVERSE}/creality_v422").status_code == 200
    assert devices.get_state().bindings() == []


def test_a_camera_kept_under_the_former_name_stands_in_the_universe():
    pose = {"position": {"x": 0, "y": 0, "z": 400}, "turn": 0.0, "tilt": 0.0}
    record = {
        "site": "parts_library",
        "name": "camera_1",
        "pose": pose,
        "added": pose,
        "added_at": "2026-10-20T18:04:11Z",
    }
    path = state_dir() / cameras.RECORDS
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"cameras": [record]}), encoding="utf-8")
    assert [c.name for c in cameras.records(UNIVERSE)] == ["camera_1"]
    assert cameras.records("parts_library") == []
    assert cameras.record(UNIVERSE, "camera_1").site == UNIVERSE
    # Stood in the site as it is built, as any camera of it is.
    universe = api._site_store.reset(UNIVERSE)
    try:
        assert "camera_1" in {child.name for child in universe.children}
    finally:
        path.unlink()
        api._site_store.reset(UNIVERSE)


def test_a_job_kept_under_the_former_name_is_the_universes():
    at = datetime(2026, 10, 20, 18, 4, 11, tzinfo=timezone.utc)
    job = jobs.Job(
        id=jobs.new_id(at, "/dev/ttyUSB0"),
        kind="print",
        machine=jobs.JobMachine(kind="printer", port="/dev/ttyUSB0", path="creality_v422"),
        input=jobs.JobInput(name="bracket.gcode", size=120, sha256="ab" * 32),
        started_at=at,
        finished_at=at,
        outcome="done",
        site="parts_library",
    )
    folder = jobs.jobs_dir()
    folder.mkdir(parents=True)
    (folder / f"{job.id}.json").write_text(job.model_dump_json(), encoding="utf-8")
    assert [j.id for j in jobs.list_jobs(site=UNIVERSE)] == [job.id]
    assert jobs.list_jobs(site="parts_library") == []
    assert jobs.get(job.id).site == UNIVERSE


def test_a_procedure_kept_under_the_former_name_is_the_universes_and_is_written_under_it():
    step = {"number": "1", "name": "look", "discipline": "mechanical"}
    was = state_dir() / "procedures" / "parts_library" / "check.json"
    was.parent.mkdir(parents=True)
    was.write_text(json.dumps({"steps": [step]}), encoding="utf-8")
    assert procedures.names(UNIVERSE) == ["check"]
    kept = procedures.load(UNIVERSE, "check")
    assert [s.name for s in kept.steps] == ["look"]
    procedures.save(UNIVERSE, "check", kept)
    assert (state_dir() / "procedures" / UNIVERSE / "check.json").is_file()
    assert procedures.names(UNIVERSE) == ["check"]


def test_the_former_address_goes_to_the_universe_with_its_query():
    answer = client.get(
        "/viewer/sites/parts_library?focus=datum_core&machine=%2Fdev%2FttyUSB0",
        follow_redirects=False,
    )
    assert answer.status_code == 307
    assert answer.headers["location"] == (
        f"/viewer/sites/{UNIVERSE}?focus=datum_core&machine=%2Fdev%2FttyUSB0"
    )
    bare = client.get("/viewer/sites/parts_library", follow_redirects=False)
    assert (bare.status_code, bare.headers["location"]) == (307, f"/viewer/sites/{UNIVERSE}")
    assert client.get("/viewer/sites/parts_library").status_code == 200


def test_a_parts_address_lands_in_the_universe_on_the_part():
    answer = client.get("/viewer/parts/datum-core", follow_redirects=False)
    assert (answer.status_code, answer.headers["location"]) == (
        307,
        f"/viewer/sites/{UNIVERSE}?focus=datum_core",
    )


def test_the_front_door_does_not_move():
    answer = client.get("/viewer", follow_redirects=False)
    assert answer.headers["location"] == "/viewer/sites/garage"


def test_an_arrangement_cannot_take_a_former_name():
    """Its address goes to the universe, and its pins would be read as the universe's."""
    with pytest.raises(HTTPException) as refused:
        api._check_name("parts_library")
    assert refused.value.status_code == 400 and UNIVERSE in refused.value.detail
