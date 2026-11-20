"""A piece the router cut, measured: checked against what was designed, and fed back as
the router's tool allowance, which its next toolpaths take (apothecary/cam/measured.py).
The piece is the 😮 of parts/router_emoji: its face cut around from outside, its eyes
and mouth bored inside."""

from __future__ import annotations

import json
import math
import re

import pytest
from fastapi.testclient import TestClient

from apothecary import sites
from apothecary.api import app
from apothecary.cam import measured, service, toolpath
from apothecary.cam.models import CutFor, Cuts, Disc, Hole, Stock
from apothecary.firmware import devices
from apothecary.projects.parts.router_emoji import DEFAULT as EMOJI
from apothecary.projects.parts.router_emoji import Params
from apothecary.state_folder import state_dir

ROUTER = CutFor(name="cnc_router", site="garage", path="cnc_router", port="/dev/ttySIM")

client = TestClient(app)


@pytest.fixture(autouse=True)
def state(tmp_path, monkeypatch):
    monkeypatch.setenv("APOTHECARY_STATE_DIR", str(tmp_path / "state"))
    sites.store.reset("garage")
    yield tmp_path / "state"
    sites.store.reset("garage")


def _kept_file():
    return state_dir() / "corrections" / "garage" / "cnc_router.json"


def _radii(lines, x, y):
    """How far from (x, y) each feed move across the lines ends, and passes nearest
    halfway along: a circle's points, and its chords' middles, which fall inside it."""
    points = []
    for line in lines:
        m = re.match(r"G1 X(-?[\d.]+) Y(-?[\d.]+)", line)
        if m:
            points.append((float(m.group(1)), float(m.group(2))))
    middles = [
        ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2) for a, b in zip(points, points[1:], strict=False)
    ]
    return [math.hypot(px - x, py - y) for px, py in points + middles]


# --- the piece ---------------------------------------------------------------------


def test_the_emoji_names_an_eye_and_the_mouth_inside_and_its_face_outside():
    """Its eyes and mouth are bored first, the face cut around last; each is named, so
    its toolpath says what a person measures, an eye once though there are two."""
    written = toolpath.write(EMOJI.cuts(), "router_emoji")
    assert [(o.kind, o.cut) for o in written.operations] == [
        ("hole", True),
        ("hole", True),
        ("hole", True),
        ("disc", True),
    ]
    assert [(f.name, f.side, f.size) for f in written.features] == [
        ("eye", "inside", 10.0),
        ("mouth", "inside", 20.0),
        ("face", "outside", 60.0),
    ]
    assert written.messages == []
    with pytest.raises(ValueError, match="mm of face between the eyes"):
        Params(face_diameter=40, eye_diameter=12)


@pytest.mark.parametrize("allowance", [0.0, 0.12, -0.08])
def test_a_tool_cutting_its_diameter_and_allowance_wide_leaves_each_size_designed(allowance):
    """Every offset is the tool's radius with the allowance: a tool that cuts that wide
    leaves the face and the holes their sizes, the circles' chords within SAG of them."""
    cuts = Cuts(
        stock=Stock(x=100, y=100, thickness=6),
        operations=[
            Hole(x=50, y=50, diameter=20, depth=2, name="mouth"),
            Disc(x=50, y=50, diameter=80, depth=2, name="face"),
        ],
    )
    written = toolpath.write(cuts, allowance=allowance)
    cutter = (cuts.tool.diameter + allowance) / 2
    hole_end = next(i for i, ln in enumerate(written.lines) if ln.startswith("(op 2/2"))
    hole = [r + cutter for r in _radii(written.lines[:hole_end], 50, 50)]
    face = [r - cutter for r in _radii(written.lines[hole_end:], 50, 50)]
    assert (
        max(hole) == pytest.approx(10, abs=0.002) and min(hole) > 10 - toolpath.SAG - 0.001
    )  # rounded to 3 places
    assert max(face) == pytest.approx(40, abs=0.002) and min(face) > 40 - toolpath.SAG - 0.001
    said = [ln for ln in written.lines if ln.startswith("(allowance")]
    assert said == (
        []
        if not allowance
        else [f"(allowance: {allowance:+.3f} mm on the tool's diameter, measured)"]
    )


# --- measured, kept, taken ---------------------------------------------------------


def test_measured_inside_and_out_the_tool_s_share_is_kept_and_the_scale_said():
    """Eye +0.12, mouth +0.14, face -0.16: the holes big and the face small by the tool,
    and a little more of each by a scale of -0.04%. +0.136 mm is kept for the router's
    6 mm tool; the scale is said and not applied; the next toolpath takes the allowance."""
    record = service.cut_into("router_emoji", ROUTER)
    assert record.allowance is None
    kept = measured.measure(record, {"eye": 10.12, "mouth": 20.14, "face": 59.84})
    assert (kept.value, kept.tool, kept.setting) == (0.136, 6.0, "tool_allowance")
    newest = kept.measurements[-1]
    assert newest.used == 0.0 and newest.scale == pytest.approx(-0.0004)
    assert [(m.name, m.side) for m in newest.sizes] == [
        ("eye", "inside"),
        ("mouth", "inside"),
        ("face", "outside"),
    ]
    assert measured.said(newest) == (
        "router_emoji measured eye +0.12, mouth +0.14, face -0.16 mm against what was "
        "designed; scale -0.04%, the steps per millimetre's, not applied; "
        "tool_allowance +0.000 -> +0.136 mm"
    )
    assert json.loads(_kept_file().read_text())["value"] == 0.136
    after = service.cut_into("router_emoji", ROUTER)
    assert after.allowance is not None
    assert (after.allowance.value, after.allowance.origin) == (0.136, "measured")
    assert after.allowance.source.startswith("garage's cnc_router, measured: router_emoji")
    text = (devices.prints_dir() / f"{after.file_id}.gcode").read_text()  # the file kept
    assert "(allowance: +0.136 mm on the tool's diameter, measured)" in text
    # Measured again from that toolpath, inside alone: the error is the tool's, from +0.136.
    again = measured.measure(after, {"eye": 10.02})
    assert again.value == 0.156 and again.measurements[-1].used == 0.136
    assert again.measurements[-1].scale is None and len(again.measurements) == 2


def test_a_toolpath_for_the_router_s_controller_keeps_it_for_the_router():
    """The page writes a toolpath for the node the router's board is pinned to, its
    controller: the allowance is the router's, and a toolpath for either takes it."""
    controller = ROUTER.model_copy(update={"path": "cnc_router.frame_system.controller"})
    record = service.cut_into("router_emoji", controller)
    assert measured.measure(record, {"face": 59.9}).router == "cnc_router"
    assert json.loads(_kept_file().read_text())["router"] == "cnc_router"
    assert service.cut_into("router_emoji", controller).allowance.value == 0.1
    assert service.cut_into("router_emoji", ROUTER).allowance.value == 0.1


def test_outside_alone_the_error_is_the_tool_s_the_other_way():
    record = service.cut_into("router_emoji", ROUTER)
    assert measured.measure(record, {"face": 59.9}).value == 0.1


def test_the_coupon_measured_by_its_pocket_and_its_plate():
    """The coupon names its pocket and its plate: 40.1 inside and 119.9 outside is a
    tenth of tool and no scale."""
    record = service.cut_into("router_coupon", ROUTER)
    assert [f.name for f in record.features] == ["pocket", "plate"]
    kept = measured.measure(record, {"pocket": 40.1, "plate": 119.9})
    assert kept.value == 0.1 and kept.measurements[-1].scale == pytest.approx(0.0)


@pytest.mark.parametrize(
    "sizes, says",
    [
        ({"face": 63.6}, "more than 5% off: not this toolpath's piece"),
        ({"nose": 4.0}, "router_emoji has no 'nose' to measure: it names eye, mouth, face"),
        ({}, "measure one of eye, mouth, face"),
        ({"eye": None}, "measure one of eye, mouth, face"),
        ({"eye": -10.0}, "eye -10.0 mm is no size"),
        # Each within 5%, and an allowance of 0.9 mm: the tool chosen, not its running out.
        ({"eye": 10.45, "mouth": 20.9, "face": 59.1}, "is past 0.5 mm"),
    ],
)
def test_a_measurement_that_is_not_of_the_piece_is_refused_and_nothing_kept(sizes, says):
    record = service.cut_into("router_emoji", ROUTER)
    with pytest.raises(measured.Refused, match=re.escape(says)):
        measured.measure(record, sizes)
    assert not _kept_file().exists()


def test_a_router_of_no_site_or_a_piece_that_names_nothing_keeps_nothing():
    nowhere = service.cut_into("router_emoji", CutFor(name="cnc_router", port="/dev/ttySIM"))
    with pytest.raises(measured.Refused, match="a router of no site"):
        measured.measure(nowhere, {"face": 60})
    record = service.cut_into("router_emoji", ROUTER)
    unnamed = record.model_copy(update={"features": []})
    with pytest.raises(measured.Refused, match="names nothing to measure: cut parts/router_emoji"):
        measured.measure(unnamed, {"face": 60})
    assert not _kept_file().exists()


def test_an_allowance_is_its_tool_s_and_another_tool_takes_none():
    """Kept for the 6 mm end mill: a toolpath with a 3 mm one takes none and says why;
    measured from that one, the router's allowance is the 3 mm tool's from then on."""
    measured.measure(service.cut_into("router_emoji", ROUTER), {"face": 59.9})
    allowance, said = measured.applied("garage", "cnc_router", 3.0)
    assert allowance is None
    assert (
        said
        == "cnc_router's allowance was measured with a 6 mm tool: this toolpath's 3 mm tool takes none"
    )
    record = service.cut_into("router_emoji", ROUTER)
    small = record.model_copy(
        update={"tool": record.tool.model_copy(update={"diameter": 3.0}), "allowance": None}
    )
    kept = measured.measure(small, {"face": 59.96})
    assert (kept.tool, kept.value, len(kept.measurements)) == (3.0, 0.04, 1)


# --- the routes --------------------------------------------------------------------


def test_the_routes_keep_a_measurement_read_it_back_and_refuse_one_off():
    record = client.post(
        "/cam/cut", json={"part": "router_emoji", "site": "garage", "router": "cnc_router"}
    )
    assert record.status_code == 200, record.text
    body = record.json()
    assert [f["name"] for f in body["features"]] == ["eye", "mouth", "face"]
    assert body["allowance"] is None
    file_id = body["file_id"]
    assert client.get(
        "/cam/corrections", params={"site": "garage", "router": "cnc_router"}
    ).json() == {"correction": None}
    r = client.post(f"/cam/cuts/{file_id}/measured", json={"sizes": {"face": 70}})
    assert r.status_code == 422 and "more than 5% off" in r.json()["detail"]
    r = client.post(f"/cam/cuts/{file_id}/measured", json={"sizes": {"face": 59.9, "eye": None}})
    assert r.status_code == 200, r.text
    assert r.json()["said"].endswith("tool_allowance +0.000 -> +0.100 mm")
    read = client.get("/cam/corrections", params={"site": "garage", "router": "cnc_router"})
    assert read.json()["correction"]["value"] == 0.1
    assert (
        client.post("/cam/cuts/nothing/measured", json={"sizes": {"face": 60}}).status_code == 404
    )
    again = client.post(
        "/cam/cut", json={"part": "router_emoji", "site": "garage", "router": "cnc_router"}
    ).json()
    assert again["allowance"]["value"] == 0.1 and again["allowance"]["origin"] == "measured"
