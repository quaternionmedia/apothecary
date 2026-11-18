"""A part's motion: the table the page plays, sampled from the wrapper's own pose function.

``apothecary/motion.py`` samples what a part declares (``BasePart.motion``) into
``motion/1``; ``GET /parts/{name}/motion`` answers it. These tests hold the arithmetic of
the table -- its samples, the page's way between two of them and how far that strays --
to answers known without it, and hold every registered part's table to its wrapper's
own pose function at the samples.
"""

from __future__ import annotations

import json
import math
import typing

import pytest
from fastapi.testclient import TestClient

from apothecary.api import app
from apothecary.gap_geometry import Pose
from apothecary.motion import (
    FORMAT,
    MOST_ROWS,
    Gap,
    Mark,
    Motion,
    Piece,
    bracket,
    interpolate,
    interpolation_error,
    nearest,
    table,
)
from apothecary.projects.parts.skeleton import ROOT
from apothecary.projects.registry import load_part, scan_projects

E = 1.5  # how far the toy's piece orbits off the axis


def orbiting(step: float = 10.0, k: float = -0.25, reach: float = 20.0) -> Motion:
    """A piece whose centre goes round a circle of radius E and turns k of a degree per
    degree of orbit: a rolling rotor without the stator."""
    return Motion(
        param="orbit",
        label="orbit",
        unit="deg",
        lo=0.0,
        hi=360.0,
        step=step,
        cyclic=True,
        piece_param="piece",
        still=Piece("still", "what stands"),
        moving=(Piece("disc", "the disc", reach=reach),),
        pose=lambda v: {
            "disc": Pose(E * math.cos(math.radians(v)), E * math.sin(math.radians(v)), k * v)
        },
        gaps=(
            Gap(
                "toy",
                "the toy's gap",
                1.0,
                lambda v: [Mark(1.0 + math.cos(math.radians(v)), (0.0, 0.0), (1.0, 0.0))],
            ),
        ),
    )


class TestTheSamples:
    def test_they_run_from_end_to_end_at_the_step_or_a_little_less(self):
        assert orbiting(10).samples() == [10.0 * k for k in range(37)]
        uneven = orbiting(7).samples()
        assert uneven[0] == 0 and uneven[-1] == 360
        assert all(0 < b - a <= 7 for a, b in zip(uneven, uneven[1:], strict=False))

    def test_a_motion_that_would_take_too_many_rows_is_refused(self):
        with pytest.raises(ValueError, match="rows"):
            orbiting(step=360 / MOST_ROWS / 2)
        with pytest.raises(ValueError, match="named once"):
            Motion(
                param="v",
                label="v",
                unit="deg",
                lo=0,
                hi=1,
                step=0.5,
                piece_param="piece",
                still=Piece("a", "a"),
                moving=(Piece("a", "a again"),),
                pose=lambda v: {},
            )


class TestBetweenTwoRows:
    samples = [0.0, 10.0, 20.0, 30.0]
    rows = [[0, 0, 0], [10, 0, -5], [10, 10, -10], [0, 10, -15]]

    def test_at_a_sample_it_is_that_row_and_between_it_is_in_proportion(self):
        for s, row in zip(self.samples, self.rows, strict=True):
            assert interpolate(self.samples, self.rows, s) == pytest.approx(row)
        assert interpolate(self.samples, self.rows, 15) == pytest.approx([10, 5, -7.5])
        assert interpolate(self.samples, self.rows, 2.5) == pytest.approx([2.5, 0, -1.25])

    def test_outside_the_samples_it_holds_at_the_end(self):
        assert interpolate(self.samples, self.rows, -4) == pytest.approx(self.rows[0])
        assert interpolate(self.samples, self.rows, 99) == pytest.approx(self.rows[-1])
        assert bracket(self.samples, 30) == (2, 1.0)

    def test_the_nearest_row_is_the_one_whose_gaps_are_shown(self):
        assert [nearest(self.samples, v) for v in (0, 4.9, 5.1, 25, 29, 30, 31)] == [
            0,
            0,
            1,
            2,
            3,
            3,
            3,
        ]

    def test_how_far_it_strays_is_the_orbits_sagitta_when_the_turn_is_in_proportion(self):
        """A centre on a circle of radius E taken in proportion across a step of d degrees
        falls short of the circle by E (1 - cos(d / 2)) at the middle; the turn, linear in
        the orbit, is exact, so no point of the piece strays more."""
        for step in (5.0, 10.0, 30.0):
            error, _ = interpolation_error(orbiting(step))
            assert error == pytest.approx(E * (1 - math.cos(math.radians(step / 2))), rel=1e-9)

    def test_a_turn_not_in_proportion_strays_by_its_chord_at_the_pieces_reach(self):
        """A turn that goes as the square of the value is off at the middle of a step from
        a to b by (b - a)^2 / 4 degrees, which moves a point at the piece's reach by its
        chord."""
        motion = Motion(
            param="v",
            label="v",
            unit="deg",
            lo=0.0,
            hi=4.0,
            step=1.0,
            piece_param="piece",
            still=Piece("still", "still"),
            moving=(Piece("arm", "arm", reach=50.0),),
            pose=lambda v: {"arm": Pose(0.0, 0.0, v * v)},
        )
        error, _ = interpolation_error(motion)
        assert error == pytest.approx(2 * 50.0 * math.sin(math.radians(0.25) / 2), rel=1e-9)


class TestTheTable:
    def test_it_says_its_format_its_samples_each_pose_and_each_gap(self):
        motion = orbiting(30)
        made = table(motion, {"orbit": 45, "piece": "all", "size": 3})
        assert made["format"] == FORMAT
        assert made["param"] == "orbit" and made["range"] == [0, 360] and made["cyclic"]
        assert made["samples"] == motion.samples()
        # The pieces are drawn with the part's values but the motion's and the piece's own.
        assert made["params"] == {"size": 3}
        (disc,) = made["pieces"]
        assert disc["piece"] == "disc" and disc["drawn"] and disc["reach"] == 20.0
        for v, row in zip(made["samples"], disc["poses"], strict=True):
            want = motion.pose(v)["disc"]
            assert row == pytest.approx([want.x, want.y, want.turn], abs=1e-9)
        assert disc["per_cycle"] == pytest.approx(-90.0)
        (gap,) = made["gaps"]
        assert gap["least"] == pytest.approx([1 + math.cos(math.radians(v)) for v in made["samples"]], abs=1e-6)
        assert gap["marks"][0] == [{"gap": 2.0, "on": [0.0, 0.0], "to": [1.0, 0.0]}]
        assert made["interpolation"]["error_mm"] == pytest.approx(E * (1 - math.cos(math.radians(15))), abs=1e-6)
        json.dumps(made)  # it is one JSON document


# ---- the parts that declare one -----------------------------------------------------------


def _parts_with_motion():
    found = {}
    for item in scan_projects(ROOT):
        if item.kind == "part" and item.has_part:
            part = load_part(item)
            if part.has_motion:
                found[item.name] = part
    return [pytest.param(part, id=name) for name, part in sorted(found.items())]


PARTS = _parts_with_motion()


def test_the_parts_that_declare_a_motion_are_these_and_no_machine_is_among_them():
    """A machine's pieces ride its axes (``kinematics``); a motion is a part's own."""
    names = sorted(p.values[0].name for p in PARTS)
    assert names == ["flexure_rotor", "rolling_rotor"]
    for item in scan_projects(ROOT):
        if item.kind == "part" and item.has_part:
            part = load_part(item)
            assert not (part.has_motion and part.kinematics), part.name


@pytest.fixture(scope="module", params=PARTS)
def declared(request):
    part = request.param
    values = part.params_model().model_dump()
    motion = part.motion(values)
    return part, motion, table(motion, values)


def test_the_table_is_the_wrappers_own_pose_function_at_the_samples(declared):
    part, motion, made = declared
    assert made["samples"] == pytest.approx(motion.samples(), abs=1e-9)
    for piece in made["pieces"]:
        for v, row in zip(made["samples"], piece["poses"], strict=True):
            want = motion.pose(v)[piece["piece"]]
            assert row == pytest.approx([want.x, want.y, want.turn], abs=1e-8), (piece["piece"], v)
        # The turn goes on from row to row, never wrapped, so the page's way between two
        # rows turns the short way.
        turns = [row[2] for row in piece["poses"]]
        assert all(abs(b - a) < 90 for a, b in zip(turns, turns[1:], strict=False))
    for bent in made["bent"]:
        (b,) = [x for x in motion.bent if x.name == bent["name"]]
        for v, shapes in zip(made["samples"], bent["outlines"], strict=True):
            for got, want in zip(shapes, b.outlines(v), strict=True):
                assert len(got) == len(want)
                assert max(math.dist(g, w) for g, w in zip(got, want, strict=True)) < 1e-5


def test_each_piece_is_one_the_scad_draws_alone(declared):
    part, motion, made = declared
    options = typing.get_args(part.params_model.model_fields[made["piece_param"]].annotation)
    drawn = [made["still"]["piece"]] + [p["piece"] for p in made["pieces"] if p["drawn"]]
    assert set(drawn) <= set(options) and "all" in options
    assert made["param"] in part.params_model.model_fields
    assert made["param"] not in made["params"] and made["piece_param"] not in made["params"]


def test_the_page_strays_less_than_a_hundredth_between_two_rows_and_the_table_says_how_far(declared):
    part, motion, made = declared
    error, at = interpolation_error(motion)
    assert made["interpolation"]["error_mm"] == pytest.approx(error, abs=1e-6)
    assert error < 0.01, (part.name, error, at)


def test_a_cycle_ends_where_it_began_but_for_its_turn(declared):
    """What the page adds each time a cyclic motion goes round again is exact: the last
    row is the first, turned by ``per_cycle``."""
    part, motion, made = declared
    if not made["cyclic"]:
        assert all(p["per_cycle"] == 0 for p in made["pieces"])
        return
    for piece in made["pieces"]:
        first, last = piece["poses"][0], piece["poses"][-1]
        assert last[:2] == pytest.approx(first[:2], abs=1e-9)
        assert last[2] - first[2] == pytest.approx(piece["per_cycle"], abs=1e-9)
    # A gap comes round again within the polygons' sagitta: a rotor turned back by its
    # roll stands its corners elsewhere against the track.
    for gap in made["gaps"]:
        assert gap["least"][-1] == pytest.approx(gap["least"][0], abs=0.01)


def test_each_gap_is_said_least_first_and_its_points_are_its_value_apart(declared):
    part, motion, made = declared
    assert made["gaps"]
    for gap in made["gaps"]:
        for least, marks in zip(gap["least"], gap["marks"], strict=True):
            assert marks[0]["gap"] == least
            assert [m["gap"] for m in marks] == sorted(m["gap"] for m in marks)
            for m in marks:
                assert math.dist(m["on"], m["to"]) == pytest.approx(abs(m["gap"]), abs=1e-5)


def test_what_is_drawn_bought_is_what_the_part_lists_bought(declared):
    """Each insert the motion draws is of a kind the part lists, and as many as it lists."""
    part, motion, made = declared
    drawn: typing.Dict[str, int] = {}
    for holder in [made["still"], *made["pieces"]]:
        for insert in holder["inserts"]:
            drawn[insert["name"]] = drawn.get(insert["name"], 0) + 1
    listed = {b.name: b for b in part.bought(part.params_model().model_dump())}
    for name, count in drawn.items():
        assert name in listed and listed[name].count == count, name
        diameters = {
            i["diameter"] for h in [made["still"], *made["pieces"]] for i in h["inserts"] if i["name"] == name
        }
        assert diameters == {listed[name].diameter}


def test_each_moving_piece_drawn_alone_at_rest_stands_on_the_axis(declared, tmp_path):
    """The page turns a piece about the part's axis through the piece's own origin, so
    the SCAD must draw it there: each moving piece of these parts is symmetric about its
    own centre, so drawn alone, as it rests, its box is centred on the axis. (A piece
    that is not symmetric would need its own outline here; none of these is.)"""
    from apothecary.meshes import bounds, read_mesh
    from apothecary.projects.parts.stl_renderer import REST, get_renderer, render_part

    part, motion, made = declared
    if not get_renderer().is_available:
        pytest.skip("OpenSCAD not installed")
    coarse = {k: v for k, v in {"facets": 48, "profile": 240}.items() if k in part.params_model.model_fields}
    for piece in [p for p in made["pieces"] if p["drawn"]]:
        values = part.validate_overrides({**coarse, made["piece_param"]: piece["piece"]})
        result = render_part(part, tmp_path / f"{piece['piece']}.stl", params=part.scad_overrides(values), timeout=180, pose=REST)
        assert result.success, result.stderr
        lo, hi = bounds(read_mesh(result.stl_path))
        assert (lo[0] + hi[0]) / 2 == pytest.approx(0.0, abs=0.05), piece["piece"]
        assert (lo[1] + hi[1]) / 2 == pytest.approx(0.0, abs=0.05), piece["piece"]
        assert hi[0] - lo[0] <= 2 * piece["reach"] + 0.05


# ---- the route --------------------------------------------------------------------------


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


def test_the_route_answers_a_part_with_a_motion_and_refuses_one_without(client):
    answer = client.get("/parts/rolling_rotor/motion")
    assert answer.status_code == 200, answer.text
    assert answer.json()["format"] == FORMAT
    swung = client.get("/parts/flexure_rotor/motion", params={"params": json.dumps({"stop": 6})})
    assert swung.status_code == 200 and swung.json()["range"] == [-6, 6]
    assert client.get("/parts/calibration_cube/motion").status_code == 404
    refused = client.get("/parts/rolling_rotor/motion", params={"params": json.dumps({"bore": 1})})
    assert refused.status_code == 422
    unknown = client.get("/parts/rolling_rotor/motion", params={"params": json.dumps({"bores": 1})})
    assert unknown.status_code == 422 and "bores" in unknown.json()["detail"]
    assert client.get("/parts/rolling_rotor/motion", params={"params": "[1]"}).status_code == 400


def test_a_parts_metadata_says_its_motion_and_its_bought_list(client):
    rolling = client.get("/parts/rolling_rotor").json()
    assert rolling["motion"] == {
        "param": "orbit",
        "label": "orbit",
        "unit": "deg",
        "range": [0.0, 360.0],
        "step": 2.0,
        "cyclic": True,
    }
    assert [b["name"] for b in rolling["bought"]] == ["output pin", "bearing"]
    cube = client.get("/parts/calibration_cube").json()
    assert cube["motion"] is None and cube["bought"] == []
    # A machine's pieces still ride its axes, as they did.
    ender = client.get("/parts/ender3").json()
    assert ender["motion"] is None and ender["kinematics"]["param"] == "piece"
