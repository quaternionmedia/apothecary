"""The jobs over the API: ``GET /jobs``, ``GET /jobs/{id}`` and ``GET /jobs/choices``.

A print is the job (consolidation Phase 3): the hand-typed queue -- a name and a
volume posted to a site, assigned to an idle printer and marked done -- is gone
with its routes, and nothing typed by hand marks a printer busy. A job is started
by its machine's own route (the Print card's, for a print) and listed here.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from apothecary import jobs
from apothecary.api import _site_store, app
from apothecary.firmware import devices as firmware_devices
from apothecary.firmware.models import DeviceInfo, PrinterInfo
from apothecary.hierarchy import Structure
from apothecary.vision import views as viewing

client = TestClient(app)

PRINTER = "/dev/ttyFAKE1"  # the scripted arduino-cli's unmatched port, serial FAKESERIAL1
UNO = "/dev/ttyFAKE0"
BOARD = "printer_1.frame_system.mainboard"
AT = datetime(2026, 10, 3, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def reset_garage_site():
    _site_store.reset("garage")
    yield
    _site_store.reset("garage")


def _status(printer):
    site = client.get("/sites/garage").json()
    return next(s for s in site["structures"] if s["name"] == printer)["status"]


def test_the_hand_typed_jobs_routes_are_gone():
    body = {"name": "small_bracket", "required_volume": {"x": 50, "y": 50, "z": 20}}
    assert client.get("/sites/garage/jobs").status_code == 404
    assert client.post("/sites/garage/jobs", json=body).status_code == 404
    assert (
        client.post(
            "/sites/garage/jobs/small_bracket/assign", json={"printer": "printer_1"}
        ).status_code
        == 404
    )
    assert client.post("/sites/garage/jobs/small_bracket/complete").status_code == 404
    assert _status("printer_1") == "idle"
    paths = client.get("/openapi.json").json()["paths"]
    assert not [p for p in paths if p.startswith("/sites/{name}/jobs")]


def _ran(port, at, site=None, identity=None, path=None, outcome="done") -> jobs.Job:
    job = jobs.Job(
        id=jobs.new_id(at, port),
        kind="print",
        machine=jobs.JobMachine(kind="printer", port=port, identity=identity, path=path),
        site=site,
        input=jobs.JobInput(name="cube.gcode", size=40, sha256="cd" * 32, file_id="f1"),
        started_at=at,
        log=["> G28", "ok"],
    )
    jobs.begin(job, live=lambda: job)
    return jobs.end(
        job.model_copy(
            update={"outcome": outcome, "finished_at": at + timedelta(minutes=9), "progress": 1.0}
        )
    )


def test_jobs_are_listed_by_site_machine_and_kind(fake_arduino_cli):
    pinned = _ran(PRINTER, AT, site="garage", identity="FAKESERIAL1", path=BOARD)
    loose = _ran(UNO, AT + timedelta(hours=1))

    every = client.get("/jobs")
    assert every.status_code == 200
    assert [j["id"] for j in every.json()] == [loose.id, pinned.id]
    first = every.json()[0]
    assert "log" not in first
    assert first["input"] == {
        "name": "cube.gcode",
        "size": 40,
        "sha256": "cd" * 32,
        "file_id": "f1",
    }
    assert (first["kind"], first["outcome"], first["machine"]["port"]) == ("print", "done", UNO)
    assert [j["id"] for j in client.get("/jobs", params={"site": "garage"}).json()] == [pinned.id]
    # The port's board is looked up: FAKESERIAL1 is the board the scripted scan finds there.
    assert [j["id"] for j in client.get("/jobs", params={"machine": PRINTER}).json()] == [pinned.id]
    assert [j["id"] for j in client.get("/jobs", params={"kind": "print"}).json()] == [
        loose.id,
        pinned.id,
    ]
    refused = client.get("/jobs", params={"kind": "weld"})
    assert refused.status_code == 422 and "print" in refused.json()["detail"]
    assert client.get("/jobs", params={"machine": "not a port"}).status_code == 422

    one = client.get(f"/jobs/{pinned.id}")
    assert one.status_code == 200
    assert one.json()["log"] == ["> G28", "ok"] and one.json()["site"] == "garage"
    assert client.get("/jobs/nope").status_code == 404
    assert client.get("/jobs/..%2Ffirmware-state").status_code == 404


def test_the_openapi_shows_the_jobs_routes():
    paths = client.get("/openapi.json").json()["paths"]
    for path in ("/jobs", "/jobs/{job_id}", "/jobs/choices"):
        assert "get" in paths[path], path
    listed = paths["/jobs"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]
    assert listed["items"]["$ref"].endswith("/JobFacts")
    assert {p["name"] for p in paths["/jobs"]["get"]["parameters"]} == {"site", "machine", "kind"}


def test_the_choices_say_where_a_machine_stands_and_what_its_job_can_name(
    fake_arduino_cli, monkeypatch
):
    """A printer pinned in the garage offers print, and a print there can name the
    garage's parts and pieces: every node built from a part, and every piece made
    from a picture, but nothing of the printer itself. Pinned nowhere, it names none;
    a board that is no machine offers nothing."""
    firmware_devices.get_state().remember_device(
        DeviceInfo(
            port=PRINTER, serial_number="FAKESERIAL1", printer=PrinterInfo(firmware_name="Marlin")
        )
    )
    loose = client.get("/jobs/choices", params={"machine": PRINTER}).json()
    assert loose["machine"] == {
        "kind": "printer",
        "port": PRINTER,
        "identity": "FAKESERIAL1",
        "path": None,
    }
    assert loose["site"] is None and loose["parts"] == []
    assert loose["operations"] == [
        {"kind": "print", "label": "Print", "inputs": [".gcode", ".gco", ".g"]}
    ]

    garage = _site_store.get("garage")
    garage.children.append(Structure(name="bin_1"))  # as a piece made from a picture stands
    made = {"bin_1": SimpleNamespace(word="bin")}
    assert client.put(f"/sites/garage/nodes/{BOARD}/device", json={"identity": PRINTER}).is_success
    try:
        with monkeypatch.context() as patched:
            patched.setattr(
                viewing,
                "store",
                lambda: SimpleNamespace(made_at=lambda site: made if site == "garage" else {}),
            )
            here = client.get("/jobs/choices", params={"machine": PRINTER}).json()
    finally:
        client.delete(f"/sites/garage/nodes/{BOARD}/device")
    assert here["site"] == "garage" and here["machine"]["path"] == BOARD
    parts = {p["path"]: p["name"] for p in here["parts"]}
    assert parts["footpedal"] == "footpedal"
    assert parts["esp32_blink"] == "esp32_devkitc"
    assert parts["printer_2"] == "ender3"
    assert parts["bin_1"] == "bin"
    assert not [p for p in parts if p == "printer_1" or p.startswith("printer_1.")]
    assert list(parts) == sorted(parts)

    uno = client.get("/jobs/choices", params={"machine": UNO}).json()
    assert uno["machine"]["kind"] is None and uno["operations"] == []
    assert client.get("/jobs/choices", params={"machine": "nope"}).status_code == 422
