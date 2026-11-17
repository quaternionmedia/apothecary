"""The measurement layer's arithmetic (apothecary/static/measure.js): a box's size along
its own axes and turned, the distance between two points and its components, the gap
between two boxes, and the vertex nearest a pointer. The module is pure, so node runs it
here.

It is also the page's one copy of a node's turn: the rotation, a point turned, the same
rotation in three.js's frame and a turned box, each held against what the server makes
of the same turn (apothecary.orbitals.turned, Assembly.world_bounds).
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from apothecary.hierarchy import Assembly
from apothecary.models.bounds import BoundingBox3D
from apothecary.models.vectors import Vector3D
from apothecary.orbitals import turned

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
const turns = %(turns)s, vectors = %(vectors)s;
out.turned = turns.map((t) => vectors.map((v) => m.turned(t, v)));
out.inScene = turns.map((t) => m.turnRowsInScene(t));
out.boxes = turns.map((t) => m.turnedBounds(box([-5, -10, 0], [15, 10, 30]), t, [100, -200, 300]));
// A small part's three dimension lines end a few pixels apart: each label is put past its
// line's end, and none crowds another; a line seen end on puts its label below its end.
const small = [
    { x: 400, y: 300, dx: 30, dy: 2, w: 120, h: 20 },
    { x: 396, y: 296, dx: -20, dy: 12, w: 120, h: 20 },
    { x: 392, y: 288, dx: 0, dy: -25, w: 120, h: 20 },
    { x: 395, y: 292, dx: 0, dy: 0, w: 90, h: 20 },
];
out.laid = m.layLabels(small, { width: 800, height: 600, gap: 6 });
out.edge = m.layLabels([{ x: 790, y: 5, dx: 1, dy: -1, w: 120, h: 20 }], { width: 800, height: 600, gap: 6 });
out.small = small;
console.log(JSON.stringify(out));
"""

# Turns as the universe makes them ([0, polar, azimuth]) and turns about every axis at
# once, with vectors along each axis and one along none.
TURNS = [
    (0, 0, 0),
    (90, 0, 0),
    (0, 90, 0),
    (0, 0, 90),
    (30, 45, 60),
    (-20, 110, 200),
    (0, 43.049079800236335, 52.5232921501135),
    (12.5, -33, 271),
]
VECTORS = [(1, 0, 0), (0, 1, 0), (0, 0, 1), (3, -4, 5)]


def _scene(p):
    """frames.js's sceneAt: the site's (x, y, z) in three.js's frame."""
    return (p[0], p[2], -p[1])


@pytest.fixture(scope="module")
def result(tmp_path_factory):
    folder = tmp_path_factory.mktemp("measure")
    module = folder / "measure.mjs"
    module.write_text(MODULE.read_text(encoding="utf-8"), encoding="utf-8")
    script = folder / "run.mjs"
    script.write_text(
        SCRIPT
        % {"module": module.as_uri(), "turns": json.dumps(TURNS), "vectors": json.dumps(VECTORS)},
        encoding="utf-8",
    )
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


def test_a_point_is_turned_as_the_server_turns_it(result):
    for turn, got in zip(TURNS, result["turned"], strict=True):
        for vector, point in zip(VECTORS, got, strict=True):
            _close(point, turned(turn, vector))


def test_the_turn_in_threes_frame_turns_a_point_sceneat_put_there(result):
    for turn, rows in zip(TURNS, result["inScene"], strict=True):
        for vector in VECTORS:
            at = _scene(vector)
            got = [sum(r * v for r, v in zip(row, at, strict=True)) for row in rows]
            _close(got, _scene(turned(turn, vector)))


def test_a_turned_box_is_the_box_the_server_reports(result):
    footprint = BoundingBox3D(
        min_point=Vector3D(x=-5, y=-10, z=0), max_point=Vector3D(x=15, y=10, z=30)
    )
    for turn, got in zip(TURNS, result["boxes"], strict=True):
        node = Assembly(
            name="n",
            footprint=footprint,
            position=Vector3D(x=100, y=-200, z=300),
            turn=Vector3D(x=turn[0], y=turn[1], z=turn[2]),
        )
        want = node.world_bounds()
        _close(got["min"], [want.min_point.x, want.min_point.y, want.min_point.z])
        _close(got["max"], [want.max_point.x, want.max_point.y, want.max_point.z])


def _box(laid, label, gap=0):
    return (
        laid["cx"] - label["w"] / 2 - gap,
        laid["cy"] - label["h"] / 2 - gap,
        laid["cx"] + label["w"] / 2 + gap,
        laid["cy"] + label["h"] / 2 + gap,
    )


def test_a_measurements_labels_stand_past_their_lines_ends_and_clear_of_one_another(result):
    """Dimension lines that end a few pixels apart, as a small part's do: each label is
    beyond its line's far end, off the end itself, and no two labels come within the gap
    of each other."""
    small, laid = result["small"], result["laid"]
    boxes = [_box(at, label) for at, label in zip(laid, small, strict=True)]
    for a, b in [(i, j) for i in range(len(boxes)) for j in range(i + 1, len(boxes))]:
        x0, y0, x1, y1 = _box(laid[a], small[a], 3)
        u0, v0, u1, v1 = _box(laid[b], small[b], 3)
        assert x1 <= u0 or u1 <= x0 or y1 <= v0 or v1 <= y0, (a, b)
    for (x0, y0, x1, y1), label, at in zip(boxes, small, laid, strict=True):
        for end in small:
            assert not (x0 <= end["x"] <= x1 and y0 <= end["y"] <= y1), (label, end)
        if label["dx"] or label["dy"]:
            ahead = (at["cx"] - label["x"]) * label["dx"] + (at["cy"] - label["y"]) * label["dy"]
            assert ahead > 0, label
    assert laid[3]["cy"] > small[3]["y"]


def test_a_label_near_the_canvas_edge_stays_on_it(result):
    (at,) = result["edge"]
    assert 60 <= at["cx"] <= 800 - 60 and 10 <= at["cy"] <= 600 - 10
