"""A site's procedures: steps fired through the family's hub, and what is kept of them."""

from __future__ import annotations

import time
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from apothecary.api import app
from apothecary.demo import BOARD, DEVKIT, PRINTER, SITE
from apothecary.evidence import log
from apothecary.evidence.observation import By, Observation, Origin
from apothecary.family import hub, procedures

NODE = f"{SITE}:{BOARD}"
HOME = {"machine": {"home": {"node": NODE}}}
ROUTE = f"/sites/{SITE}/procedures/bring-up"
FOREIGN = {"Origin": "https://example.org"}


def _step(number, name="a step", discipline="mechanical", **more):
    return {"number": number, "name": name, "discipline": discipline, **more}


@pytest.fixture
def client(family_bench):
    return TestClient(app, client=("127.0.0.1", 50000), base_url="http://127.0.0.1")


def _put(client, *steps, name=ROUTE):
    answer = client.put(name, json={"steps": list(steps)})
    assert answer.status_code == 200, answer.text
    return answer.json()


def _go(client, number):
    return client.post(f"{ROUTE}/steps/{number}/go")


def _stands(board, number):
    return next(step for step in board["steps"] if step["number"] == number)


def _settled(client, number, within=30.0):
    """A step, once what it fired has ended."""
    deadline = time.monotonic() + within
    while time.monotonic() < deadline:
        step = _stands(client.get(ROUTE).json(), number)
        if step["status"] != procedures.FIRED:
            return step
        time.sleep(0.02)
    raise AssertionError(f"step {number} is still fired after {within}s")


def test_a_step_stands_by_once_the_one_before_it_is_fired(client):
    board = _put(client, _step("1"), _step("2"))
    assert _stands(board, "1")["status"] == "standing by" and _stands(board, "1")["can_go"]
    second = _stands(board, "2")
    assert second["status"] == "waiting" and second["why"] == "waiting for step 1"
    assert not second["can_go"]


def test_a_persons_own_step_is_done_by_its_go_and_kept(client):
    _put(client, _step("1", "Fit the lead", node=f"{SITE}:esp32_blink"), _step("2"))
    board = _go(client, "1").json()
    assert _stands(board, "1")["status"] == "done"
    assert _stands(board, "2")["status"] == "standing by"
    kept = log.read(SITE, log.ACTIONS).records
    assert [(r["procedure"], r["step"], r["node"]) for r in kept] == [
        ("bring-up", "1", f"{SITE}:esp32_blink")
    ]


def test_a_go_for_a_step_not_standing_by_changes_nothing(client):
    _put(client, _step("1"), _step("2"))
    answer = _go(client, "2")
    assert answer.status_code == 409 and answer.json()["detail"] == "waiting for step 1"
    assert log.read(SITE, log.ACTIONS).records == []
    _go(client, "1")
    assert _go(client, "1").status_code == 409


def test_a_refused_step_says_why_holds_the_next_and_may_be_fired_again(client, family_bench):
    _put(client, _step("1", family=HOME), _step("2"))
    board = _go(client, "1").json()
    first = _stands(board, "1")
    assert first["status"] == "refused" and "arm its control first" in first["why"]
    assert first["can_go"] and _stands(board, "2")["status"] == "waiting"
    assert first["outcomes"][0]["via"] == "local" and first["outcomes"][0]["status"] == 422

    family_bench.control.arm(PRINTER)
    assert _go(client, "1").status_code == 200
    first = _settled(client, "1")
    assert first["status"] == "done" and first["outcomes"][0]["status"] == 202
    assert _stands(client.get(ROUTE).json(), "2")["status"] == "standing by"
    # Both fires are in the log: only the last counts.
    assert [r["status"] for r in log.read(SITE, log.ACTIONS).records] == [422, 202]


def test_a_member_the_hub_does_not_have_is_a_failure_never_a_pass(client):
    _put(client, _step("1", discipline="audio", family={"joe": {"say": {"text": "hello"}}}))
    first = _stands(_go(client, "1").json(), "1")
    assert first["status"] == "failed"
    assert first["why"] == f"joe is not a member in {hub.TABLE}"


def test_work_that_fails_after_its_answer_fails_its_step(client):
    expect = {"board": {"expect": {"port": DEVKIT, "hello": "footpedal"}}}
    _put(client, _step("1", discipline="firmware", family=expect), _step("2"))
    assert _stands(_go(client, "1").json(), "1")["outcomes"][0]["status"] == 202
    first = _settled(client, "1")
    assert first["status"] == "failed" and "not footpedal's" in first["why"]
    assert first["can_go"]
    assert _stands(client.get(ROUTE).json(), "2")["status"] == "waiting"


def test_a_page_member_stays_fired_until_a_page_reads_it(client):
    keep = {"camera": {"keep": {"frame": True}}}
    _put(client, _step("1", discipline="optical", family=keep), _step("2"))
    board = _go(client, "1").json()
    assert _stands(board, "1")["status"] == "fired"
    # Fired is enough for the next, which does not wait on a page.
    assert _stands(board, "2")["status"] == "standing by"
    assert client.get("/family/members/camera").json()["action"] == keep["camera"]
    assert _stands(client.get(ROUTE).json(), "1")["status"] == "done"


def _said(subject, prop, value):
    now = datetime.now(timezone.utc)
    origin = Origin(kind="measured", by=By(name="a test"))
    log.write(
        SITE,
        [
            Observation(
                subject=subject, property=prop, value=value, origin=origin, at=now, recorded_at=now
            )
        ],
    )


def test_a_step_waits_for_the_evidence_it_names(client):
    waits = {"subject": f"{SITE}:printer_1", "property": "state", "value": "idle"}
    _put(client, _step("1", waits=waits))
    first = _stands(client.get(ROUTE).json(), "1")
    assert first["status"] == "waiting" and "it is nothing yet" in first["why"]
    assert _go(client, "1").status_code == 409
    _said(f"{SITE}:printer_1", "state", "printing")
    assert "it is printing" in _stands(client.get(ROUTE).json(), "1")["why"]
    _said(f"{SITE}:printer_1", "state", "idle")
    assert _stands(client.get(ROUTE).json(), "1")["status"] == "standing by"


def test_homing_leaves_the_evidence_the_next_step_waits_on(client, family_bench):
    waits = {"subject": f"{SITE}:printer_1", "property": "state", "value": "idle"}
    family_bench.control.arm(PRINTER)
    _put(client, _step("1", family=HOME), _step("2", waits=waits))
    _go(client, "1")
    assert _settled(client, "1")["status"] == "done"
    assert _stands(client.get(ROUTE).json(), "2")["status"] == "standing by"


def test_again_starts_it_over_and_the_log_keeps_what_came_before(client):
    _put(client, _step("1"))
    _go(client, "1")
    board = client.post(f"{ROUTE}/again").json()
    assert _stands(board, "1")["status"] == "standing by" and _stands(board, "1")["outcomes"] == []
    assert len(log.read(SITE, log.ACTIONS).records) == 2


def test_a_restart_keeps_what_each_step_did(client):
    _put(client, _step("1"), _step("2", family={"joe": {"take": {}}}))
    _go(client, "1")
    _go(client, "2")
    hub.close()
    board = client.get(ROUTE).json()
    assert _stands(board, "1")["status"] == "done"
    assert _stands(board, "2")["status"] == "failed"


def test_the_site_lists_its_procedures(client):
    assert client.get(f"/sites/{SITE}/procedures").json()["procedures"] == []
    _put(client, _step("1"))
    assert client.get(f"/sites/{SITE}/procedures").json()["procedures"] == ["bring-up"]


@pytest.mark.parametrize(
    ("route", "status"),
    [
        (f"/sites/{SITE}/procedures/nothing", 404),
        ("/sites/nowhere/procedures/bring-up", 404),
        (f"/sites/{SITE}/procedures/..%2F..%2Fpasswd", 404),
        (f"/sites/{SITE}/procedures/.hidden", 422),
    ],
)
def test_what_is_not_there_is_not_found(client, route, status):
    assert client.get(route).status_code == status


@pytest.mark.parametrize(
    "steps",
    [
        [],
        [_step("1"), _step("1")],
        [_step("1", discipline="vibes")],
        [_step("1", unknown=True)],
        [_step("1", family={"machine": "home"})],
    ],
)
def test_a_procedure_that_would_not_stand_is_refused(client, steps):
    assert client.put(ROUTE, json={"steps": steps}).status_code == 422
    assert procedures.names(SITE) == []


def test_a_file_that_will_not_read_says_so(client):
    _put(client, _step("1"))
    procedures._file(SITE, "bring-up").write_text("{not a procedure", encoding="utf-8")
    answer = client.get(ROUTE)
    assert answer.status_code == 422 and "does not read" in answer.json()["detail"]
    assert client.post(f"{ROUTE}/steps/1/go").status_code == 422


def test_writing_leaves_nothing_beside_it(client):
    _put(client, _step("1"))
    folder = procedures._file(SITE, "bring-up").parent
    assert [path.name for path in folder.iterdir()] == ["bring-up.json"]


def test_a_page_from_elsewhere_fires_nothing(client):
    _put(client, _step("1"))
    assert client.post(f"{ROUTE}/steps/1/go", headers=FOREIGN).status_code == 403
    assert log.read(SITE, log.ACTIONS).records == []
