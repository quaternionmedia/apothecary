"""apothecary as the irl family's hub: hearth's check judges it from outside."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient
from hearth import conformance, coordinator

from apothecary.api import app
from apothecary.family import hub
from apothecary.version import __version__
from apothecary.wiring import carlos

# The version of hearth's vector set this suite replays: `uv run qm interop` reads
# this line, and compares it with what hearth publishes.
PINNED = "0.0.1"

# The member side's cases at that version, none of which a hub answers.
MEMBER_CASES = 14

PAGE = "a-page"

# The members the hub has with no table: those it hosts, and the one a page reads.
OWN = ["board", "camera", "machine"]


@pytest.fixture(autouse=True)
def a_state_folder(tmp_path, monkeypatch):
    monkeypatch.setenv("APOTHECARY_STATE_DIR", str(tmp_path))
    monkeypatch.delenv(carlos.CARLOS_ENV, raising=False)
    hub.close()
    yield tmp_path
    hub.close()


def _table(folder, **table) -> None:
    (folder / hub.TABLE).write_text(json.dumps(table), encoding="utf-8")


def test_the_hub_says_what_it_is():
    said = TestClient(app).get("/family/identity").json()
    assert (said["hub"], said["family"], said["contract"]) == ("apothecary", "irl", "family/1")
    assert said["version"] == __version__
    assert said["conformance"] == PINNED


def test_hearths_check_finds_a_hub_that_conforms(a_state_folder, served, capsys):
    """Every case of the hub's side, the pull member's among them, against a real port."""
    _table(a_state_folder, pull=[PAGE])
    report = conformance.check_hub(served, pull=PAGE)
    failed = [f for f in report.findings if not f.ok]
    assert report.status == 0 and not failed, failed
    with capsys.disabled():
        print(
            f"\nfamily/1 conformance: {len(report.findings)} applicable, all passing; "
            f"{MEMBER_CASES} not applicable",
        )


def test_the_table_is_read_from_the_state_folder_and_says_nothing_of_a_missing_one(a_state_folder):
    assert hub.members() == OWN
    _table(a_state_folder, members={"carlos": "http://127.0.0.1:4186"}, pull=[PAGE])
    assert hub.members() == sorted([*OWN, "a-page", "carlos"])
    (a_state_folder / hub.TABLE).write_text("not json", encoding="utf-8")
    assert hub.members() == OWN


def test_a_member_elsewhere_is_left_out_and_said(a_state_folder, caplog):
    _table(a_state_folder, members={"far": "http://192.168.1.4:9", "near": "http://localhost:9/"})
    assert hub.members() == sorted([*OWN, "near"])
    assert hub.running().members == {"near": "http://localhost:9"}
    assert "far" in caplog.text and "not on this machine" in caplog.text


def test_serve_carlos_makes_carlos_a_push_member(monkeypatch):
    monkeypatch.setenv(carlos.CARLOS_ENV, "http://127.0.0.1:4186")
    assert hub.running().members == {"carlos": "http://127.0.0.1:4186"}
    snapshot = TestClient(app).get("/family/").json()
    assert snapshot["members"]["carlos"]["via"] == "push"
    assert snapshot["last"] == []


def test_a_delivery_keeps_its_outcome_whatever_the_member_said(a_state_folder):
    """Nothing there to answer: recorded, never raised, and told apart from a refusal."""
    _table(a_state_folder, members={"carlos": "http://127.0.0.1:9"}, timeout=0.5)
    cue = {"number": "1", "name": "a hold", "fired_at": None}
    outcome = hub.deliver("carlos", cue, {"hold": {}})
    assert outcome["done"] and outcome["via"] == "push" and outcome["status"] is None
    with pytest.raises(carlos.CarlosError, match="did not answer"):
        carlos.answer_of(outcome, "http://127.0.0.1:9")
    assert TestClient(app).get("/family/").json()["last"][-1]["cue"] == cue


def test_a_member_the_table_does_not_hold_is_said_by_its_file():
    outcome = hub.deliver("nobody", {"number": "1", "name": "", "fired_at": None}, {})
    assert outcome["error"] == f"nobody is not a member in {hub.TABLE}"


def test_a_refused_hold_is_told_as_a_refusal():
    refused = {"done": True, "status": 422, "error": "not a rig"}
    with pytest.raises(carlos.CarlosError, match=r"refused the rig \(422\): not a rig"):
        carlos.answer_of(refused, "http://127.0.0.1:4186")
    assert carlos.answer_of({"done": True, "answer": {"ok": True}}, "") == {"ok": True}
    with pytest.raises(carlos.CarlosError, match="in time"):
        carlos.answer_of({"done": False}, "http://127.0.0.1:4186")


def test_the_pin_is_the_version_the_coordinator_replays():
    assert coordinator.CONFORMANCE == PINNED
