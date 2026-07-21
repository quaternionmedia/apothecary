"""Tests for the Job model, capacity check, and JobStore (prototype, unratified)."""

import pytest

from apothecary.example_hierarchy import Job, JobStore, create_example_site, job_fits_printer
from apothecary.models.vectors import Vector3D


def _printer(site, name="printer_1"):
    return next(s for s in site.structures if s.name == name)


def test_job_fits_printer_within_build_volume():
    site = create_example_site()
    job = Job(name="small_bracket", required_volume=Vector3D(x=50, y=50, z=20))
    assert job_fits_printer(job, _printer(site)) is True


def test_job_does_not_fit_printer_when_any_axis_too_large():
    site = create_example_site()
    printer = _printer(site)
    # printer_1's build volume is 220x220x250
    too_tall = Job(name="tall_thing", required_volume=Vector3D(x=50, y=50, z=300))
    assert job_fits_printer(too_tall, printer) is False


def test_job_does_not_fit_structure_with_no_build_volume():
    site = create_example_site()
    workbench = _printer(site, "workbench")
    job = Job(name="anything", required_volume=Vector3D(x=1, y=1, z=1))
    assert job_fits_printer(job, workbench) is False


def test_job_store_add_and_list():
    store = JobStore()
    job = Job(name="job_a", required_volume=Vector3D(x=10, y=10, z=10))
    store.add("garage", job)
    assert store.list_for_site("garage") == [job]


def test_job_store_rejects_duplicate_names():
    store = JobStore()
    store.add("garage", Job(name="job_a", required_volume=Vector3D(x=1, y=1, z=1)))
    with pytest.raises(ValueError):
        store.add("garage", Job(name="job_a", required_volume=Vector3D(x=2, y=2, z=2)))


def test_job_store_get_missing_raises_keyerror():
    store = JobStore()
    with pytest.raises(KeyError):
        store.get("garage", "nope")


def test_job_store_separates_by_site_name():
    store = JobStore()
    store.add("garage", Job(name="job_a", required_volume=Vector3D(x=1, y=1, z=1)))
    assert store.list_for_site("other_site") == []
