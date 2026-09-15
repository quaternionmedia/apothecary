"""API tests for the job queue / capacity-checked assignment endpoints (prototype)."""

import pytest
from fastapi.testclient import TestClient

from apothecary.api import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_garage_site():
    client.post("/sites/garage/reset")
    yield


def _create_job(name="small_bracket", x=50, y=50, z=20):
    return client.post(
        "/sites/garage/jobs", json={"name": name, "required_volume": {"x": x, "y": y, "z": z}}
    )


def test_create_job():
    response = _create_job()
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "small_bracket"
    assert data["status"] == "queued"
    assert data["assigned_printer"] is None
    assert data["compatible_printers"] == ["printer_1", "printer_2", "printer_3"]


def test_create_job_duplicate_name_is_409():
    _create_job()
    response = _create_job()
    assert response.status_code == 409


def test_create_job_unknown_site_is_404():
    response = client.post(
        "/sites/nope/jobs", json={"name": "j", "required_volume": {"x": 1, "y": 1, "z": 1}}
    )
    assert response.status_code == 404


def test_list_jobs():
    _create_job("job_a")
    _create_job("job_b")
    response = client.get("/sites/garage/jobs")
    assert response.status_code == 200
    names = [j["name"] for j in response.json()]
    assert names == ["job_a", "job_b"]


def test_job_too_large_has_no_compatible_printers():
    response = _create_job("too_tall", x=50, y=50, z=300)
    assert response.json()["compatible_printers"] == []


def test_assign_job_to_idle_compatible_printer():
    _create_job()
    response = client.post("/sites/garage/jobs/small_bracket/assign", json={"printer": "printer_1"})
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "assigned"
    assert data["assigned_printer"] == "printer_1"

    site = client.get("/sites/garage").json()
    printer_1 = next(s for s in site["structures"] if s["name"] == "printer_1")
    assert printer_1["status"] == "printing"


def test_assign_job_that_does_not_fit_is_422():
    _create_job("too_tall", x=50, y=50, z=300)
    response = client.post("/sites/garage/jobs/too_tall/assign", json={"printer": "printer_1"})
    assert response.status_code == 422


def test_assign_job_to_busy_printer_is_409():
    _create_job("job_a")
    _create_job("job_b")
    client.post("/sites/garage/jobs/job_a/assign", json={"printer": "printer_1"})
    response = client.post("/sites/garage/jobs/job_b/assign", json={"printer": "printer_1"})
    assert response.status_code == 409


def test_assign_unknown_job_is_404():
    response = client.post("/sites/garage/jobs/nope/assign", json={"printer": "printer_1"})
    assert response.status_code == 404


def test_assign_unknown_printer_is_404():
    _create_job()
    response = client.post(
        "/sites/garage/jobs/small_bracket/assign", json={"printer": "not_a_printer"}
    )
    assert response.status_code == 404


def test_assign_to_workbench_is_404_not_a_printer():
    _create_job()
    response = client.post(
        "/sites/garage/jobs/small_bracket/assign", json={"printer": "workbench"}
    )
    assert response.status_code == 404


def test_complete_job_frees_the_printer():
    _create_job()
    client.post("/sites/garage/jobs/small_bracket/assign", json={"printer": "printer_1"})
    response = client.post("/sites/garage/jobs/small_bracket/complete")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "done"
    assert data["assigned_printer"] == "printer_1"  # kept as a record

    site = client.get("/sites/garage").json()
    printer_1 = next(s for s in site["structures"] if s["name"] == "printer_1")
    assert printer_1["status"] == "idle"


def test_complete_unknown_job_is_404():
    response = client.post("/sites/garage/jobs/nope/complete")
    assert response.status_code == 404


def test_reset_site_clears_job_queue():
    _create_job()
    client.post("/sites/garage/jobs/small_bracket/assign", json={"printer": "printer_1"})
    client.post("/sites/garage/reset")
    response = client.get("/sites/garage/jobs")
    assert response.json() == []
