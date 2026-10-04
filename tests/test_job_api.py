"""The jobs over the API.

A print is the job (consolidation Phase 3): the hand-typed queue -- a name and a
volume posted to a site, assigned to an idle printer and marked done -- is gone
with its routes, and nothing typed by hand marks a printer busy.
"""

import pytest
from fastapi.testclient import TestClient

from apothecary.api import _site_store, app

client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_garage_site():
    _site_store.reset("garage")
    yield


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
