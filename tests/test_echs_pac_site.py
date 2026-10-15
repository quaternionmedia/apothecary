"""The ECHS-PAC venue as a site: its shell, its rig, and what happens without the files.

The venue's files are the school's, not the repository's, so the tests that need
them skip when they are absent; the one that checks absence always runs.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from apothecary import echs_pac_site as venue
from apothecary.api import app
from apothecary.hierarchy import check_no_overlaps

client = TestClient(app)
needs_venue = pytest.mark.skipif(not venue.venue_present(), reason="ECHS-PAC export not on this machine")


def test_absent_export_is_not_a_site_and_has_no_rig(monkeypatch, tmp_path):
    monkeypatch.setenv(venue.VENUE_DIR_ENV, str(tmp_path / "nowhere"))
    assert not venue.venue_present()
    assert venue.load_echs_rig() is None
    with pytest.raises(FileNotFoundError):
        venue.create_echs_pac_site()


@needs_venue
def test_site_has_shell_and_every_located_patch():
    site = venue.create_echs_pac_site()
    shell = [c for c in site.children if c.category == "architecture"]
    assert {c.name for c in shell} == {name for name, *_ in venue.SHELL}
    rig = venue.load_echs_rig()
    located = [p for p in rig.patches if p.location is not None]
    assert len(site.children) == len(shell) + len(located)
    assert {c.category for c in site.children} == {"architecture", "lighting", "scenic"}


@needs_venue
def test_shell_pieces_do_not_overlap_each_other():
    shell = [c for c in venue.create_echs_pac_site().children if c.category == "architecture"]
    assert check_no_overlaps(shell) == []


@needs_venue
def test_site_units_are_millimetres_and_the_rig_is_in_metres():
    site = venue.create_echs_pac_site()
    rig = venue.load_echs_rig()
    first = next(p for p in rig.patches if p.location is not None)
    node = next(c for c in site.children if c.name.startswith(f"ch{first.channel}_"))
    assert node.position.x == pytest.approx(first.location.x * 1000)
    assert node.position.y == pytest.approx(first.location.y * 1000)


@needs_venue
def test_venue_routes_answer_over_http():
    assert client.get("/sites/echs_pac").status_code == 200
    body = client.get("/sites/echs_pac/lighting").json()
    assert len(body["rig"]["patches"]) == 183
    assert body["violations"] == []
    state = client.get("/sites/echs_pac/lighting/state").json()
    assert state["seq"] == 0
