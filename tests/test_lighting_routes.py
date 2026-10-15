"""The lighting routes: a rig's summary, its live state, and writes that are checked.

A synthetic rig is registered under a throwaway site name, so these run without
the venue's files and do not touch the real registry.
"""

from __future__ import annotations

import base64

import pytest
from fastapi.testclient import TestClient

from apothecary.api import app
from apothecary.lighting import FixtureType, LightingRig, Patch
from apothecary.routes import lighting as routes

client = TestClient(app)
SITE = "test_rig_site"


@pytest.fixture
def rig_site(monkeypatch):
    rig = LightingRig(
        types={
            "ColorSource_SPOT_5ch": FixtureType(name="ColorSource_SPOT_5ch", params=["Intens", "Red", "Green", "Blue", "Shutter_Strobe"]),
            "Virtual_Layer_Ver_1.0": FixtureType(name="Virtual_Layer_Ver_1.0", params=["Intens", "Pan"]),
        },
        patches=[
            Patch(channel=1, fixture_type="ColorSource_SPOT_5ch", label="Front", universe=1, addresses=[1, 2, 3, 4, 5]),
            Patch(channel=9, fixture_type="Virtual_Layer_Ver_1.0", label="Layer"),
        ],
    )
    monkeypatch.setitem(routes.RIG_LOADERS, SITE, lambda: rig)
    monkeypatch.setattr(routes, "_states", {})
    yield rig


def test_unknown_site_has_no_rig_and_says_so():
    assert client.get("/sites/nowhere/lighting").json()["rig"] is None
    assert client.get("/sites/nowhere/lighting/state").status_code == 404


def test_rig_summary_lists_patches_universes_and_checks(rig_site):
    body = client.get(f"/sites/{SITE}/lighting").json()
    assert [p["channel"] for p in body["rig"]["patches"]] == [1, 9]
    assert body["universes"] == [1]
    assert body["unplaced"] == 2
    assert body["violations"] == []


def test_put_levels_then_read_them_back(rig_site):
    put = client.put(f"/sites/{SITE}/lighting/state", json={"levels": {"9": {"Pan": 0.25}}})
    assert put.status_code == 200
    state = client.get(f"/sites/{SITE}/lighting/state").json()
    assert state["channels"]["9"] == {"Pan": 0.25}
    assert state["seq"] == 1


def test_put_dmx_slots_decodes_addressed_channel(rig_site):
    slots = bytes([255, 0, 0, 0, 0]) + bytes(507)
    body = {"dmx": {"1": base64.b64encode(slots).decode()}}
    state = client.put(f"/sites/{SITE}/lighting/state", json=body).json()
    assert state["channels"]["1"]["Intens"] == 1.0
    assert state["channels"]["1"]["Red"] == 0.0


@pytest.mark.parametrize(
    "body",
    [
        {"levels": {"42": {"Intens": 0.5}}},  # channel not in the rig
        {"levels": {"1": {"Intens": 2.0}}},  # outside 0-1
        {"dmx": {"7": base64.b64encode(bytes(4)).decode()}},  # universe not in the rig
        {"dmx": {"1": "not base64!"}},
        {"dmx": {"1": base64.b64encode(bytes(513)).decode()}},  # too many slots
    ],
)
def test_bad_writes_are_refused_with_400(rig_site, body):
    assert client.put(f"/sites/{SITE}/lighting/state", json=body).status_code == 400


def test_console_feeds_start_only_when_asked(rig_site, monkeypatch):
    started = []
    monkeypatch.setattr(routes.SacnReceiver, "start", lambda self: started.append(self.universes))
    monkeypatch.setattr(routes.OscReceiver, "start", lambda self: started.append("osc"))
    monkeypatch.delenv(routes.CONSOLE_OSC_ENV, raising=False)
    monkeypatch.setattr(routes, "_receivers", [])
    monkeypatch.setattr(routes, "RIG_LOADERS", {SITE: routes.RIG_LOADERS[SITE]})  # not the real venue
    monkeypatch.delenv(routes.CONSOLE_SACN_ENV, raising=False)
    routes.start_console_feeds()
    assert started == []
    monkeypatch.setenv(routes.CONSOLE_SACN_ENV, "1")
    routes.start_console_feeds()
    assert started == [frozenset({1})]
    routes.stop_console_feeds()
    started.clear()
    monkeypatch.setenv(routes.CONSOLE_OSC_ENV, "1")
    routes.start_console_feeds()
    assert started == [frozenset({1}), "osc"]
