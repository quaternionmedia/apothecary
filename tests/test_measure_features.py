"""What a click on a mesh reads of the shape under it (apothecary/static/measure_features.js),
held against shapes built here with known answers: a hole and a boss of known radius and
facets, a low-facet hole read across its vertices and its flats, a hexagonal boss, a plate
of known thickness, a slot of known width, a wedge of known angle, an edge of a box, a hole
whose vertices are a little off, and the faces it cannot decide on -- a cone, a geodesic
ball, a face too narrow for the pointer -- which answer that they cannot tell, and why,
rather than a number. Node runs the module as the page imports it.

Every shape is a triangle soup, as an STL is, wound outward as OpenSCAD writes it."""

from __future__ import annotations

import math

import pytest
from page_modules import HAVE_NODE, run_module

pytestmark = pytest.mark.skipif(not HAVE_NODE, reason="node is not installed")

SHAPES = """
const soup = () => { const s = []; s.tri = (a, b, c) => s.push(...a, ...b, ...c); s.quad = (a, b, c, d) => { s.tri(a, b, c); s.tri(a, c, d); }; return s; };
// The k-th of n points round a circle of radius r at height z, nudged by up to `jitter`.
const ring = (r, k, n, z, jitter = 0) => {
    const t = (2 * Math.PI * (k % n)) / n;
    const j = jitter * Math.sin(k * 12.9898 + z * 78.233 + r * 37.719), i = jitter * Math.sin(k * 4.1414 + z * 17.17 + r * 9.21);
    return [(r + j) * Math.cos(t), (r + j) * Math.sin(t), z + i];
};
// A tube: a hole of radius ri in a boss of radius ro, n facets each, from z 0 to h.
const tube = (ri, ro, n, h, jitter = 0) => {
    const s = soup(), P = (r, k, z) => ring(r, k, n, z, jitter);
    for (let k = 0; k < n; k++) {
        s.quad(P(ro, k, 0), P(ro, k + 1, 0), P(ro, k + 1, h), P(ro, k, h));
        s.quad(P(ri, k, 0), P(ri, k, h), P(ri, k + 1, h), P(ri, k + 1, 0));
        s.quad(P(ri, k, h), P(ro, k, h), P(ro, k + 1, h), P(ri, k + 1, h));
        s.quad(P(ri, k, 0), P(ri, k + 1, 0), P(ro, k + 1, 0), P(ro, k, 0));
    }
    return s;
};
// A convex polygon, counter-clockwise, stood from z0 to z1.
const prism = (poly, z0, z1, s = soup()) => {
    const at = (p, z) => [p[0], p[1], z];
    poly.forEach((p, i) => { const q = poly[(i + 1) % poly.length]; s.quad(at(p, z0), at(q, z0), at(q, z1), at(p, z1)); });
    for (let i = 1; i + 1 < poly.length; i++) { s.tri(at(poly[0], z1), at(poly[i], z1), at(poly[i + 1], z1)); s.tri(at(poly[0], z0), at(poly[i + 1], z0), at(poly[i], z0)); }
    return s;
};
const regular = (r, n) => Array.from({ length: n }, (_, k) => [r * Math.cos((2 * Math.PI * k) / n), r * Math.sin((2 * Math.PI * k) / n)]);
const rect = (x0, y0, x1, y1) => [[x0, y0], [x1, y0], [x1, y1], [x0, y1]];
// The triangle whose middle is nearest p, of those facing n.
const faceAt = (s, p, n = null) => {
    let best = -1, bestD = Infinity;
    for (let t = 0; t < s.length / 9; t++) {
        const [a, b, c] = [0, 3, 6].map((o) => s.slice(9 * t + o, 9 * t + o + 3));
        const e1 = [0, 1, 2].map((i) => b[i] - a[i]), e2 = [0, 1, 2].map((i) => c[i] - a[i]);
        const cr = [e1[1] * e2[2] - e1[2] * e2[1], e1[2] * e2[0] - e1[0] * e2[2], e1[0] * e2[1] - e1[1] * e2[0]];
        const l = Math.hypot(...cr);
        if (!l || (n && (cr[0] * n[0] + cr[1] * n[1] + cr[2] * n[2]) / l < 0.99)) continue;
        const d = Math.hypot(...[0, 1, 2].map((i) => (a[i] + b[i] + c[i]) / 3 - p[i]));
        if (d < bestD) { bestD = d; best = t; }
    }
    return best;
};
const read = (s, p, n, opts) => f.featureAt(f.meshFrom(s, null), faceAt(s, p, n), p, opts);
"""

SCRIPT = (
    'import * as f from "/static/measure_features.js";\n'
    + SHAPES
    + """
const out = {};
const t = tube(8, 11, 64, 20);
out.hole = read(t, [8, 0.3, 10], [-1, 0, 0]);
out.boss = read(t, [11, 0.3, 10], [1, 0, 0]);
out.annulus = read(t, [9.5, 0, 20], [0, 0, 1]);
const solid = prism(regular(6, 48), -5, 5);
out.solid = read(solid, [6, 0.3, 0], [1, 0, 0]);
out.low = read(tube(5, 7, 8, 10), [4.8, 0.5, 5], [-0.92, -0.38, 0]);
out.hexagon = read(prism(regular(4, 6), 0, 10), [3.4, 1, 5], [0.87, 0.5, 0]);
out.plate = read(prism(rect(0, 0, 30, 20), 0, 4), [10, 10, 4], [0, 0, 1]);
const slot = soup(); prism(rect(0, 3, 5, 10), 0, 8, slot); prism(rect(8, 3, 13, 10), 0, 8, slot); prism(rect(0, 0, 13, 3), 0, 8, slot);
out.slot = read(slot, [5, 6, 4], [1, 0, 0]);
const th = (30 * Math.PI) / 180, L = 20;
const wedge = prism([[0, 0], [L, 0], [L * Math.cos(th), L * Math.sin(th)]], 0, 5);
out.wedgeBase = read(wedge, [10, 0, 2.5], [0, -1, 0]);
out.wedgeSlope = read(wedge, [8.66, 5, 2.5], [-Math.sin(th), Math.cos(th), 0]);
out.wedgeAngle = f.faceAngle(out.wedgeBase.normal, out.wedgeSlope.normal);
out.plateAngle = f.faceAngle([0, 0, 1], [0, 0, -1]);
out.squareAngle = f.faceAngle([0, 0, 1], [1, 0, 0]);
out.noisy = read(tube(8, 11, 64, 20, 0.002), [8, 0.3, 10], [-1, 0, 0]);
// A tapered boss: radius 10 at its base to 9 at its top, 20 above, 64 facets.
const taper = soup();
for (let k = 0; k < 64; k++) {
    taper.quad(ring(10, k, 64, 0), ring(10, k + 1, 64, 0), ring(9, k + 1, 64, 20), ring(9, k, 64, 20));
    taper.tri([0, 0, 20], ring(9, k, 64, 20), ring(9, k + 1, 64, 20));
    taper.tri([0, 0, 0], ring(10, k + 1, 64, 0), ring(10, k, 64, 0));
}
out.taper = read(taper, [9.5, 0.2, 10], null);
out.declaredTaper = f.declaredOn(out.taper, [
    { name: "end", type: "spigot", source: "drawn", position: { x: 0, y: 0, z: 0 }, normal: { x: 0, y: 0, z: 1 }, d_base: 20, d_tip: 18, length: 20 },
]);
// A fillet of radius 1 along a plate's edge, eight facets: the fillet is round, the flat
// beside it a wall.
const arc = []; for (let k = 0; k <= 8; k++) { const a = ((Math.PI / 2) * k) / 8; arc.push([19 + Math.cos(a), 4 + Math.sin(a)]); }
const rounded = prism([[0, 0], [20, 0], ...arc, [0, 5]], 0, 20);
out.fillet = read(rounded, [19 + Math.cos(0.5), 4 + Math.sin(0.5), 10], null);
out.besideFillet = read(rounded, [10, 5, 10], [0, 1, 0]);
// A cone, base radius 10, apex 10 above it: turns about no axis its faces stand across.
const cone = soup();
for (let k = 0; k < 32; k++) { cone.tri(ring(10, k, 32, 0), ring(10, k + 1, 32, 0), [0, 0, 10]); cone.tri([0, 0, 0], ring(10, k + 1, 32, 0), ring(10, k, 32, 0)); }
out.cone = read(cone, [5, 0.5, 5], null);
// A geodesic ball: an octahedron's faces cut in 36, pushed out to radius 10.
const ball = soup(), corners = [[1, 0, 0], [0, 1, 0], [0, 0, 1], [-1, 0, 0], [0, -1, 0], [0, 0, -1]];
const outward = (p) => { const l = Math.hypot(...p); return p.map((v) => (10 * v) / l); };
for (const [a, b, c] of [[0, 1, 2], [1, 3, 2], [3, 4, 2], [4, 0, 2], [1, 0, 5], [3, 1, 5], [4, 3, 5], [0, 4, 5]]) {
    const P = (i, j) => outward([0, 1, 2].map((d) => corners[a][d] + ((corners[b][d] - corners[a][d]) * i) / 6 + ((corners[c][d] - corners[a][d]) * j) / 6));
    for (let i = 0; i < 6; i++) for (let j = 0; i + j < 6; j++) { ball.tri(P(i, j), P(i + 1, j), P(i, j + 1)); if (i + j + 1 < 6) ball.tri(P(i + 1, j), P(i + 1, j + 1), P(i, j + 1)); }
}
out.ball = read(ball, outward([0.5, 0.3, 0.6]), null);
// A chamfer 0.28 mm across along a plate's edge: too narrow for a pointer half a mm wide.
const c = 0.2, chamfered = prism([[0, 0], [20, 0], [20, 5 - c], [20 - c, 5], [0, 5]], 0, 20);
out.farChamfer = read(chamfered, [20 - c / 2, 5 - c / 2, 10], [0.707, 0.707, 0], { pixel: 0.5 });
out.nearChamfer = read(chamfered, [20 - c / 2, 5 - c / 2, 10], [0.707, 0.707, 0], { pixel: 0.01 });
out.noFace = f.featureAt(f.meshFrom(chamfered, null), -1, [0, 0, 0]);
// An open mesh: a single square, nothing behind it.
const sheet = soup(); sheet.quad([0, 0, 0], [10, 0, 0], [10, 10, 0], [0, 10, 0]);
out.sheet = read(sheet, [5, 5, 0], [0, 0, 1]);
// Edges of a box ten on a side: along one, along a face's diagonal, and across the box.
const cube = prism(rect(0, 0, 10, 10), 0, 10), cubeMesh = f.meshFrom(cube, null);
const vertex = (p) => { for (let i = 0; i < cube.length / 3; i++) if (Math.hypot(cube[3 * i] - p[0], cube[3 * i + 1] - p[1], cube[3 * i + 2] - p[2]) < 1e-9) return i; return -1; };
out.edges = [[[0, 0, 0], [10, 0, 0]], [[0, 0, 10], [10, 10, 10]], [[0, 0, 0], [10, 10, 10]], [[10, 10, 0], [10, 10, 10]]]
    .map(([a, b]) => f.edgeBetween(cubeMesh, vertex(a), vertex(b)));
// A long edge cut in three by vertices on it, as a mesh often has it: a side and a top,
// each three quads.
const strip = soup();
for (const [x0, x1] of [[0, 5], [5, 12], [12, 20]]) {
    strip.quad([x0, 0, 0], [x1, 0, 0], [x1, 0, 2], [x0, 0, 2]);
    strip.quad([x0, 0, 2], [x1, 0, 2], [x1, 4, 2], [x0, 4, 2]);
}
const stripMesh = f.meshFrom(strip, null), at = (p) => { for (let i = 0; i < strip.length / 3; i++) if (Math.hypot(strip[3 * i] - p[0], strip[3 * i + 1] - p[1], strip[3 * i + 2] - p[2]) < 1e-9) return i; return -1; };
out.longEdge = f.edgeBetween(stripMesh, at([0, 0, 2]), at([20, 0, 2]));
// Indexed, as a mesh three.js built is: the same hole read the same.
const positions = [], index = [], ids = new Map();
for (let i = 0; i < t.length / 3; i++) {
    const key = `${t[3 * i]},${t[3 * i + 1]},${t[3 * i + 2]}`;
    if (!ids.has(key)) { ids.set(key, positions.length / 3); positions.push(t[3 * i], t[3 * i + 1], t[3 * i + 2]); }
    index.push(ids.get(key));
}
out.indexed = f.featureAt(f.meshFrom(positions, index), faceAt(t, [8, 0.3, 10], [-1, 0, 0]), [8, 0.3, 10]);
// The declared interfaces of a part with this hole, in the same frame.
const declared = [
    { name: "port", type: "socket", source: "stub", position: { x: 0, y: 0, z: 20 }, normal: { x: 0, y: 0, z: 1 }, diameter: 16, depth: 20 },
    { name: "collar", type: "spigot", source: "drawn", position: { x: 0, y: 0, z: 0 }, normal: { x: 0, y: 0, z: -1 }, d_base: 22, d_tip: 22, length: 20 },
    { name: "beside", type: "bolt_hole", source: "drawn", position: { x: 30, y: 0, z: 0 }, normal: { x: 0, y: 0, z: 1 }, diameter: 16 },
    { name: "across", type: "bolt_hole", source: "drawn", position: { x: 0, y: 0, z: 10 }, normal: { x: 1, y: 0, z: 0 }, diameter: 16 },
    { name: "flat", type: "slot", source: "stub", position: { x: 0, y: 0, z: 0 }, normal: { x: 0, y: 0, z: 1 }, width: 3, length: 9 },
];
out.declaredHole = f.declaredOn(out.hole, declared);
out.declaredBoss = f.declaredOn(out.boss, declared);
out.declaredNone = f.declaredOn(out.hole, declared.filter((i) => i.name !== "port"));
out.declaredFlat = f.declaredOn(out.plate, declared);
console.log(JSON.stringify(out));
"""
)


@pytest.fixture(scope="module")
def result(tmp_path_factory):
    return run_module(tmp_path_factory.mktemp("measure_features"), SCRIPT)


def _round(reading, sense, diameter, sides):
    assert reading["kind"] == "round", reading
    assert reading["sense"] == sense
    assert reading["diameter"] == pytest.approx(diameter, abs=1e-9)
    assert reading["sides"] == sides
    assert reading["flats"] == pytest.approx(diameter * math.cos(math.pi / sides), abs=1e-9)


def test_a_hole_reads_its_diameter_across_its_vertices_and_its_axis(result):
    hole = result["hole"]
    _round(hole, "hole", 16, 64)
    assert hole["facets"] == 64 and hole["closed"] is True and hole["arc"] == 360
    assert hole["vertices"] == 128
    assert hole["residual"] < 1e-9
    assert hole["axis"] == pytest.approx([0, 0, 1], abs=1e-9)
    assert hole["middle"] == pytest.approx([0, 0, 10], abs=1e-9)
    assert hole["length"] == pytest.approx(20, abs=1e-9)


def test_a_holes_wall_is_cast_from_the_click_into_what_it_is_made_of(result):
    assert result["hole"]["wall"]["thickness"] == pytest.approx(3, abs=0.02)
    assert result["hole"]["taper"] is False and result["hole"]["slope"] == pytest.approx(0, abs=1e-9)


def test_a_taper_reads_its_diameter_at_each_end_and_how_far_its_faces_lean(result):
    taper = result["taper"]
    assert taper["kind"] == "round" and taper["sense"] == "boss" and taper["taper"] is True
    assert taper["diameter"] == pytest.approx(19, abs=1e-6)
    assert taper["ends"] == pytest.approx([20, 18], abs=1e-6)
    assert abs(taper["lean"]) == pytest.approx(math.degrees(math.atan(1 / 20)), abs=1e-6)
    assert taper["residual"] < 1e-6
    match = result["declaredTaper"]["match"]
    assert match["name"] == "end" and match["mesh"] == pytest.approx(20, abs=1e-6)
    assert match["apart"] == pytest.approx(0, abs=1e-6)


def test_the_outside_of_the_same_tube_is_a_boss(result):
    _round(result["boss"], "boss", 22, 64)
    _round(result["solid"], "boss", 12, 48)


def test_a_low_facet_hole_reads_across_its_flats_too(result):
    low = result["low"]
    _round(low, "hole", 10, 8)
    assert low["flats"] == pytest.approx(9.2388, abs=1e-4)


def test_a_hexagonal_boss_is_round_and_a_box_is_not(result):
    _round(result["hexagon"], "boss", 8, 6)
    assert result["hexagon"]["flats"] == pytest.approx(6.9282, abs=1e-4)
    assert result["plate"]["kind"] == "flat"


def test_a_plates_face_reads_its_thickness_to_the_parallel_face_behind_it(result):
    plate = result["plate"]
    assert plate["normal"] == [0, 0, 1]
    assert plate["wall"]["thickness"] == pytest.approx(4, abs=1e-9)
    assert plate["wall"]["far"] == pytest.approx([10, 10, 0], abs=1e-9)
    assert plate["wall"]["parallel"] is True and plate["wall"]["off"] == pytest.approx(0, abs=1e-6)
    assert plate["gap"] is None
    # A tube's end reads its length, the face at its other end.
    assert result["annulus"]["kind"] == "flat"
    assert result["annulus"]["wall"]["thickness"] == pytest.approx(20, abs=1e-9)


def test_a_slots_side_reads_its_wall_and_the_slots_width(result):
    slot = result["slot"]
    assert slot["kind"] == "flat"
    assert slot["wall"]["thickness"] == pytest.approx(5, abs=1e-9)
    assert slot["gap"]["width"] == pytest.approx(3, abs=1e-9)
    assert slot["gap"]["parallel"] is True


def test_a_wedge_reads_its_angle_and_a_wall_across_it_is_not_parallel(result):
    assert result["wedgeBase"]["kind"] == "flat" and result["wedgeSlope"]["kind"] == "flat"
    angle = result["wedgeAngle"]
    assert angle["angle"] == pytest.approx(30, abs=1e-9)
    assert angle["between"] == pytest.approx(150, abs=1e-9)
    assert angle["parallel"] is False
    wall = result["wedgeBase"]["wall"]
    assert wall["thickness"] == pytest.approx(10 * math.tan(math.radians(30)), abs=1e-9)
    assert wall["parallel"] is False and wall["off"] == pytest.approx(30, abs=1e-9)
    assert result["plateAngle"]["parallel"] is True and result["plateAngle"]["angle"] == pytest.approx(0)
    assert result["squareAngle"]["angle"] == pytest.approx(90)


def test_a_hole_whose_vertices_are_a_little_off_reads_near_its_diameter_and_says_how_far(
    result,
):
    noisy = result["noisy"]
    assert noisy["kind"] == "round" and noisy["sense"] == "hole"
    assert noisy["diameter"] == pytest.approx(16, abs=0.005)
    assert 1e-4 < noisy["residual"] < 0.002
    assert noisy["facets"] == 64


def test_a_fillet_is_a_round_arc_and_the_flat_beside_it_a_wall(result):
    fillet = result["fillet"]
    assert fillet["kind"] == "round" and fillet["sense"] == "boss"
    assert fillet["diameter"] == pytest.approx(2, abs=1e-9)
    assert fillet["closed"] is False and fillet["facets"] == 8
    assert fillet["arc"] == pytest.approx(90, abs=1e-6)
    assert fillet["middle"][:2] == pytest.approx([19, 4], abs=1e-9)
    beside = result["besideFillet"]
    assert beside["kind"] == "flat" and beside["wall"]["thickness"] == pytest.approx(5, abs=1e-9)


@pytest.mark.parametrize("shape", ["cone", "ball"])
def test_faces_turning_about_no_one_axis_cannot_be_told(result, shape):
    reading = result[shape]
    assert reading["kind"] == "unknown", reading
    assert "turn about no one axis" in reading["why"]
    assert "diameter" not in reading


def test_a_face_too_narrow_for_the_pointer_cannot_be_told_until_it_is_nearer(result):
    far = result["farChamfer"]
    assert far["kind"] == "unknown"
    assert "too small to tell which face was meant" in far["why"] and "0.28 mm across" in far["why"]
    near = result["nearChamfer"]
    assert near["kind"] == "flat" and near["wall"]["parallel"] is False
    assert result["noFace"] == {"kind": "unknown", "why": "the click met no face of the mesh"}


def test_an_open_mesh_has_no_wall_behind_its_face(result):
    sheet = result["sheet"]
    assert sheet["kind"] == "flat"
    assert "thickness" not in sheet["wall"]
    assert "the mesh is open there" in sheet["wall"]["why"]


def test_an_edge_is_two_vertices_joined_along_a_crease(result):
    along, diagonal, across, upright = result["edges"]
    assert along["length"] == pytest.approx(10) and along["meet"] == pytest.approx(90)
    assert along["boundary"] is False
    assert upright["length"] == pytest.approx(10)
    assert diagonal is None, "a face's diagonal joins two triangles in one plane: no edge"
    assert across is None
    long = result["longEdge"]
    assert long["length"] == pytest.approx(20) and long["pieces"] == 3
    assert long["meet"] == pytest.approx(90)


def test_an_indexed_mesh_reads_as_its_soup_does(result):
    _round(result["indexed"], "hole", 16, 64)


def test_the_declared_hole_on_the_same_axis_is_found_beside_the_reading(result):
    hole = result["declaredHole"]
    assert hole["round"] == 4
    assert hole["match"]["name"] == "port" and hole["match"]["type"] == "socket"
    assert hole["match"]["diameter"] == 16 and hole["match"]["apart"] == pytest.approx(0, abs=1e-9)
    assert hole["match"]["source"] == "stub"
    boss = result["declaredBoss"]["match"]
    assert boss["name"] == "collar" and boss["apart"] == pytest.approx(0, abs=1e-9)
    # Off the axis, across it, or the other way round: not this round's.
    assert result["declaredNone"] == {"round": 3, "match": None}
    assert result["declaredFlat"] == {"round": 0, "match": None}
