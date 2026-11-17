"""The measurement layer's arithmetic (apothecary/static/measure.js): a box's size along
its own axes and turned, the distance between two points and its components, the gap
between two boxes, and the vertex nearest a pointer. The module is pure, so node runs it
here.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "apothecary" / "static" / "measure.js"
NODE = shutil.which("node") or str(Path.home() / ".local" / "bin" / "node")

pytestmark = pytest.mark.skipif(not Path(NODE).exists(), reason="node is not installed")

SCRIPT = """
import * as m from "%(module)s";
const box = (min, max) => ({ min, max });
const out = {};
out.own = m.ownExtents(box([10, 20, 30], [40, 25, 31]));
out.scene = m.sizeFromSceneBox([30, 5, 7]);
const size = { x: 40, y: 10, z: 5 };
out.unturned = m.turnedExtents(size, null);
out.quarter = m.turnedExtents(size, [0, 0, 90]);
out.upright = m.turnedExtents(size, [90, 0, 0]);
out.sides = m.turnedExtents(size, [0, 0, 45]);
out.between = m.between([1, 2, 3], [4, 6, 15]);
const unit = box([0, 0, 0], [10, 10, 10]);
out.apart = m.gap(unit, box([13, 0, 0], [20, 10, 10]));
out.diagonal = m.gap(unit, box([13, 14, 0], [20, 20, 10]));
out.touching = m.gap(unit, box([10, 0, 0], [20, 10, 10]));
out.overlapping = m.gap(unit, box([5, 5, 5], [15, 15, 15]));
out.inside = m.gap(unit, box([2, 2, 2], [3, 3, 3]));
out.flushOverlap = m.gap(unit, box([10, 2, 2], [12, 3, 3]));
const points = [{ sx: 10, sy: 10, id: "a" }, { sx: 14, sy: 10, id: "b" }, { sx: 40, sy: 40, id: "c" }];
out.near = [m.nearestWithin(points, 13, 10, 8), m.nearestWithin(points, 100, 100, 8), m.nearestWithin(points, 12, 10, 8), m.nearestWithin([], 0, 0, 8)]
    .map((p) => (p ? p.id : null));
out.written = [m.length(12.3456), m.length(-0.001), m.length(0)];
console.log(JSON.stringify(out));
"""


@pytest.fixture(scope="module")
def result(tmp_path_factory):
    folder = tmp_path_factory.mktemp("measure")
    module = folder / "measure.mjs"
    module.write_text(MODULE.read_text(encoding="utf-8"), encoding="utf-8")
    script = folder / "run.mjs"
    script.write_text(SCRIPT % {"module": module.as_uri()}, encoding="utf-8")
    done = subprocess.run(
        [NODE, str(script)], capture_output=True, text=True, timeout=60, check=False
    )
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


def _close(got, want):
    assert got == pytest.approx(want, abs=1e-9)


def test_a_box_is_measured_along_its_own_axes(result):
    assert result["own"] == {"x": 30, "y": 5, "z": 1}
    assert result["scene"] == {"x": 30, "y": 7, "z": 5}


def test_a_turned_box_is_measured_in_its_own_frame_and_its_container_in_the_worlds(result):
    assert result["unturned"] == {"x": 40, "y": 10, "z": 5}
    for key, want in (("quarter", (10, 40, 5)), ("upright", (40, 5, 10))):
        for axis, v in zip("xyz", want, strict=True):
            _close(result[key][axis], v)
    # Turned 45 degrees about z, the container is (40 + 10) / sqrt(2) on both sides.
    _close(result["sides"]["x"], 50 / 2**0.5)
    _close(result["sides"]["y"], 50 / 2**0.5)
    _close(result["sides"]["z"], 5)


def test_two_points_give_their_components_and_the_straight_length(result):
    assert result["between"] == {"dx": 3, "dy": 4, "dz": 12, "length": 13}


def test_the_gap_between_boxes_is_clear_distance_and_zero_when_they_meet(result):
    assert result["apart"]["gap"] == 3 and not result["apart"]["overlap"]
    assert result["apart"]["axes"] == {"x": 3, "y": -10, "z": -10}
    assert result["diagonal"]["gap"] == 5  # 3 along x, 4 along y
    touching = result["touching"]
    assert touching["gap"] == 0 and touching["touching"] and not touching["overlap"]
    for key in ("overlapping", "inside"):
        assert result[key]["gap"] == 0 and result[key]["overlap"] and not result[key]["touching"]
    # Meeting at a face while the rest lies inside it: touching, not overlapping.
    assert result["flushOverlap"]["touching"] and not result["flushOverlap"]["overlap"]


def test_the_vertex_nearest_the_pointer_within_the_radius_is_chosen(result):
    assert result["near"] == ["b", None, "a", None]


def test_lengths_are_written_to_two_places(result):
    assert result["written"] == ["12.35 mm", "0.00 mm", "0.00 mm"]
