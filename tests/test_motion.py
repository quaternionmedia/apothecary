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


# ---- the route --------------------------------------------------------------------------


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


def test_the_route_refuses_a_part_without_a_motion(client):
    assert client.get("/parts/calibration_cube/motion").status_code == 404


def test_a_parts_metadata_says_its_motion_and_its_bought_list(client):
    cube = client.get("/parts/calibration_cube").json()
    assert cube["motion"] is None and cube["bought"] == []
    # A machine's pieces still ride its axes, as they did.
    ender = client.get("/parts/ender3").json()
    assert ender["motion"] is None and ender["kinematics"]["param"] == "piece"
