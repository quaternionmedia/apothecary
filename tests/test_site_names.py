"""What is kept under a site's name is read for the site of that name and no other
(apothecary/site_names.py): a pin, a camera, a job or a procedure kept under a name
no site has is no site's, and an address under that name opens nothing.

Each test makes the state it reads, in a state folder of its own.
"""

import json
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from firmware_helpers import _isolate_firmware_state

from apothecary import api, jobs, sites
from apothecary.family import procedures
from apothecary.firmware import devices
from apothecary.site_names import UNIVERSE
from apothecary.state_folder import state_dir
from apothecary.vision import cameras

client = TestClient(api.app)

# The name no site has: the universe is ``apothecary``.
NO_SITE_S = "parts_library"

# A pin kept under it, on a node the universe has.
PIN = {
    "site": NO_SITE_S,
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


def test_a_pin_kept_under_a_name_no_site_has_is_no_site_s(fake_arduino_cli):
    """It is read as it is kept, the universe's node of the same path is not pinned by
    it, Pinned lists it as a pin of a site that is not known, and reading it writes
    nothing."""
    _kept(bindings=[PIN])
    before = _state_file().read_bytes()
    state = devices.get_state()
    assert state.bindings(UNIVERSE) == []
    assert [(b.site, b.path) for b in state.bindings()] == [(NO_SITE_S, "creality_v422")]
    rows = client.get(f"/sites/{UNIVERSE}/devices").json()["bindings"]
    assert [r["path"] for r in rows if r["binding_source"] == "manual"] == []
    (pinned,) = client.get("/firmware/pins").json()["pins"]
    assert (pinned["site"], pinned["site_known"]) == (NO_SITE_S, False)
    assert _state_file().read_bytes() == before


def test_a_camera_kept_under_a_name_no_site_has_stands_in_no_site():
    pose = {"position": {"x": 0, "y": 0, "z": 400}, "turn": 0.0, "tilt": 0.0}
    record = {
        "site": NO_SITE_S,
        "name": "camera_1",
        "pose": pose,
        "added": pose,
        "added_at": "2026-10-20T18:04:11Z",
    }
    path = state_dir() / cameras.RECORDS
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"cameras": [record]}), encoding="utf-8")
    assert cameras.records(UNIVERSE) == []
    assert [(c.site, c.name) for c in cameras.records()] == [(NO_SITE_S, "camera_1")]
    universe = sites.store.reset(UNIVERSE)
    try:
        assert "camera_1" not in {child.name for child in universe.children}
    finally:
        path.unlink()
        sites.store.reset(UNIVERSE)


def test_a_job_kept_under_a_name_no_site_has_is_no_site_s():
    at = datetime(2026, 10, 20, 18, 4, 11, tzinfo=timezone.utc)
    job = jobs.Job(
        id=jobs.new_id(at, "/dev/ttyUSB0"),
        kind="print",
        machine=jobs.JobMachine(kind="printer", port="/dev/ttyUSB0", path="creality_v422"),
        input=jobs.JobInput(name="bracket.gcode", size=120, sha256="ab" * 32),
        started_at=at,
        finished_at=at,
        outcome="done",
        site=NO_SITE_S,
    )
    folder = jobs.jobs_dir()
    folder.mkdir(parents=True)
    (folder / f"{job.id}.json").write_text(job.model_dump_json(), encoding="utf-8")
    assert jobs.list_jobs(site=UNIVERSE) == []
    assert [j.id for j in jobs.list_jobs(site=NO_SITE_S)] == [job.id]
    assert jobs.get(job.id).site == NO_SITE_S


def test_a_procedure_kept_under_a_name_no_site_has_is_no_site_s():
    step = {"number": "1", "name": "look", "discipline": "mechanical"}
    kept = state_dir() / "procedures" / NO_SITE_S / "check.json"
    kept.parent.mkdir(parents=True)
    kept.write_text(json.dumps({"steps": [step]}), encoding="utf-8")
    assert procedures.names(UNIVERSE) == []
    assert procedures.load(UNIVERSE, "check") is None
    assert procedures.names(NO_SITE_S) == ["check"]


def test_an_address_under_a_name_no_site_has_opens_nothing():
    for address in (
        f"/viewer/sites/{NO_SITE_S}",
        f"/viewer/sites/{NO_SITE_S}?focus=datum_core&machine=%2Fdev%2FttyUSB0",
    ):
        answer = client.get(address, follow_redirects=False)
        assert answer.status_code == 404 and "location" not in answer.headers


def test_a_parts_address_lands_in_the_universe_on_the_part():
    answer = client.get("/viewer/parts/datum-core", follow_redirects=False)
    assert (answer.status_code, answer.headers["location"]) == (
        307,
        f"/viewer/sites/{UNIVERSE}?focus=datum_core",
    )


def test_the_front_door_does_not_move():
    answer = client.get("/viewer", follow_redirects=False)
    assert answer.headers["location"] == "/viewer/sites/garage"


def test_a_name_no_site_has_is_an_arrangement_s_to_take():
    assert api._check_name(NO_SITE_S) == NO_SITE_S
