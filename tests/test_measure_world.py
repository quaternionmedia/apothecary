"""The measurement layer in the world (apothecary/static/measure_world.js): where a size
says it comes from, what a click becomes -- a point snapped to a vertex near the pointer,
else on the surface, a third click starting again -- the readings written for the points
and the selection, and what Escape and the layer hidden let go. Node runs the module as the
page imports it, with three.js's own objects for the world and a stand-in for the page's
canvas."""

from __future__ import annotations

import pytest
from page_modules import HAVE_NODE, run_module

pytestmark = pytest.mark.skipif(not HAVE_NODE, reason="node is not installed")

# A page's canvas, as far as a label drawn on one needs it.
FAKE_DOCUMENT = """
globalThis.document = { createElement: () => ({ width: 0, height: 0, getContext: () => ({
    measureText: (text) => ({ width: 8 * text.length }), fillRect() {}, strokeRect() {}, fillText() {} }) }) };
"""

SCRIPT = (
    FAKE_DOCUMENT
    + """
import * as THREE from "three";
import { sourceOf, tokenOf, pointsAfter, readingsOf, mountMeasureWorld, SNAP_PX } from "/static/measure_world.js";
import { makePickScope, MEASURE } from "/static/pick_scope.js";
const out = {};

out.sources = [
    sourceOf({ placeholder: false }), sourceOf({ placeholder: false, moving: 1 }), sourceOf({ placeholder: false, moving: 3 }),
    sourceOf({ placeholder: true, footprint: {} }), sourceOf({ placeholder: true, envelope: {} }), sourceOf({ placeholder: true }),
];
out.tokens = out.sources.map(tokenOf);
out.after = [pointsAfter([], "a"), pointsAfter(["a"], "b"), pointsAfter(["a", "b"], "c")];

const box = (min, max) => ({ min, max });
const nodes = {
    cube: { world_bounds: box([0, 0, 0], [10, 10, 10]) },
    bench: { world_bounds: box([13, 0, 0], [20, 10, 10]) },
    turned: { turn: [0, 0, 90], footprint: box([0, 0, 0], [40, 10, 5]), site_ref: "garage", site_size: [4000, 3000, 2500] },
};
const plain = { nodeOf: (k) => nodes[k], envelopeOf: (n) => (n ? n.world_bounds || null : null), frameOf: () => null };
const point = (key, site, kind) => ({ key, site, kind });
out.one = readingsOf({ ...plain, points: [point("cube", [1, 2, 3], "vertex")], selection: null, selectedKey: null });
out.two = readingsOf({ ...plain, points: [point("cube", [0, 0, 0], "vertex"), point("bench", [13, 4, 0], "surface")], selection: null, selectedKey: null });
out.selected = readingsOf({
    ...plain, points: [], selectedKey: "turned",
    selection: { key: "turned", node: nodes.turned, size: { x: 40, y: 10, z: 5 }, source: "the drawn mesh, as loaded" },
    frameOf: () => ({ volume: [220, 220, 250], volume_from: "controller" }),
});
out.notDrawn = readingsOf({ ...plain, points: [], selection: null, selectedKey: "cube" });
// A part on the universe's sphere: laid out there, turned to face outward.
nodes.leaf = { shell: 1, turn: [0, 108.82, -129.84], footprint: box([0, 0, 0], [20, 10, 5]) };
const leafPoint = (site, own) => ({ key: "leaf", site, own, kind: "vertex" });
out.sphere = readingsOf({
    ...plain, points: [leafPoint([1500.123, -800, 900], [20, 10, 5]), leafPoint([1490, -790, 905], [0, 0, 5])], selectedKey: "leaf",
    selection: { key: "leaf", node: nodes.leaf, size: { x: 20, y: 10, z: 5 }, source: "the drawn mesh, as loaded" },
});

// A world of one cube, ten on a side, its middle at the origin, seen from its front right.
const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(45, 800 / 600, 0.1, 1000);
camera.position.set(30, 25, 40); camera.lookAt(0, 0, 0); camera.updateMatrixWorld();
const mesh = new THREE.Mesh(new THREE.BoxGeometry(10, 10, 10), new THREE.MeshBasicMaterial());
mesh.userData.key = "cube"; scene.add(mesh); mesh.updateMatrixWorld();
const canvas = { clientWidth: 800, clientHeight: 600, getBoundingClientRect: () => ({ left: 0, top: 0, width: 800, height: 600 }) };
const raycaster = new THREE.Raycaster();
const pick = (event) => {
    raycaster.setFromCamera(new THREE.Vector2((event.clientX / 800) * 2 - 1, -(event.clientY / 600) * 2 + 1), camera);
    return raycaster.intersectObjects([mesh], false);
};
const onScreen = (p) => { const s = p.clone().project(camera); return { clientX: ((s.x + 1) / 2) * 800, clientY: ((1 - s.y) / 2) * 600 }; };
const scope = makePickScope({ storage: { getItem: () => null, setItem() {}, removeItem() {} } });
const said = [];
const m = mountMeasureWorld({
    scope, scene: () => scene, camera: () => camera, canvas: () => canvas, pick,
    nodeOf: (k) => nodes[k], meshOf: (k) => (k === "cube" ? mesh : null), selected: () => null,
    envelopeOf: plain.envelopeOf, frameOf: () => null, fallbackColour: 0x4488cc,
    dispose: (o) => o.traverse((x) => { x.geometry?.dispose(); x.material?.dispose(); }),
    setStatus: (words, kind) => said.push([kind, words]), invalidate: () => {}, refresh: () => {},
});
const settle = () => new Promise((resolve) => setTimeout(resolve, 0));
out.off = { on: m.on(), cleared: m.clear() };
scope.setShown(MEASURE, true);
// The corner nearest the camera, clicked a few pixels off; the middle of the front face.
const corner = onScreen(new THREE.Vector3(5, 5, 5));
m.click({ clientX: corner.clientX - 3, clientY: corner.clientY + 4 });
await settle();
out.first = { points: m.points.map((p) => ({ kind: p.kind, key: p.key, site: p.site })), lines: [...m.lines], drawn: !!m.group };
const face = onScreen(new THREE.Vector3(0, 0, 5));
m.click(face);
await settle();
out.second = { points: m.points.map((p) => ({ kind: p.kind, site: p.site })), lines: [...m.lines], labels: m.labels.length, rods: m.rods.length };
m.click(face);
await settle();
out.third = m.points.length;
m.click({ clientX: 2, clientY: 2 });
out.missed = said[said.length - 1];
out.cleared = { cleared: m.clear(), points: m.points.length, said: said[said.length - 1] };
out.clearedAgain = m.clear();
m.click(face);
scope.setShown(MEASURE, false);
m.layersApplied();
await settle();
out.hidden = { points: m.points.length, drawn: !!m.group, lines: m.lines };
out.snapPx = SNAP_PX;
console.log(JSON.stringify(out));
"""
)


@pytest.fixture(scope="module")
def result(tmp_path_factory):
    return run_module(tmp_path_factory.mktemp("measure_world"), SCRIPT)


def test_a_size_says_where_it_comes_from(result):
    assert result["sources"] == [
        "the drawn mesh, as loaded",
        "the drawn mesh, as loaded, its 1 moving piece with it",
        "the drawn mesh, as loaded, its 3 moving pieces with it",
        "declared footprint",
        "envelope of its pieces",
        "a stand-in box, no size declared",
    ]
    assert result["tokens"] == ["mesh", "mesh", "mesh", "declared", "envelope", "a"]


def test_a_third_click_starts_again(result):
    assert result["after"] == [["a"], ["a", "b"], ["c"]]


def test_one_point_says_where_it_is_and_asks_for_a_second(result):
    assert result["one"] == [
        "point 1 (vertex) on cube at 1.00, 2.00, 3.00 mm; click a second point (Escape starts again)"
    ]


def test_two_points_on_two_pieces_read_the_distance_and_the_gap(result):
    distance, gap = result["two"]
    assert distance.startswith("13.60 mm between point 1 (vertex) on cube at 0.00, 0.00, 0.00 mm")
    assert "dx 13.00 mm, dy 4.00 mm, dz 0.00 mm" in distance
    assert distance.endswith("a vertex and a surface point)")
    assert gap.startswith("gap between cube and bench: 3.00 mm (clear distance between their declared bounds")


def test_the_selection_reads_its_size_its_turn_its_site_and_its_working_volume(result):
    size, site, declared, volume = result["selected"]
    assert size == (
        "turned measures x 40.00 mm × y 10.00 mm × z 5.00 mm along its own axes (the drawn mesh, as loaded); "
        "turned [0, 0, 90] degrees, its world box x 10.00 mm × y 40.00 mm × z 5.00 mm"
    )
    assert site.startswith("turned is the site garage in miniature")
    assert declared == (
        "turned declares x 40.00 mm × y 10.00 mm × z 5.00 mm (declared footprint); "
        "the mesh above is what is drawn, and the two can differ"
    )
    assert volume == "turned's working volume 220.00 mm × 220.00 mm × 250.00 mm (its frame, from the machine's controller)"
    assert result["notDrawn"] == ["cube is not drawn here, so there is nothing of it to measure"]


def test_off_the_layer_reads_nothing_and_escape_has_nothing_to_let_go(result):
    assert result["off"] == {"on": False, "cleared": False}


def test_a_click_near_a_corner_snaps_to_it_and_one_on_a_face_is_on_the_surface(result):
    first = result["first"]
    assert first["drawn"] is True
    assert first["points"] == [{"kind": "vertex", "key": "cube", "site": [5, -5, 5]}]
    # What the click read under it first, then where the point is.
    assert first["lines"][0].startswith("point 1 on cube: a flat face, its wall 10.00 mm thick")
    assert first["lines"][1].startswith("point 1 (vertex) on cube at 5.00, -5.00, 5.00 mm")
    second = result["second"]
    assert [p["kind"] for p in second["points"]] == ["vertex", "surface"]
    assert second["points"][1]["site"] == pytest.approx([0, -5, 0], abs=1e-6)
    assert second["lines"][0].startswith("7.07 mm between point 1 (vertex)")
    # The line between the points, and each point's wall: three lines, each labelled.
    assert second["labels"] == 3 and second["rods"] == 3
    assert result["third"] == 1
    assert result["snapPx"] == 12


def test_a_click_on_nothing_says_so_and_escape_lets_the_points_go(result):
    assert result["missed"] == ["error", "Measure: no piece under the pointer to measure from"]
    assert result["cleared"] == {
        "cleared": True,
        "points": 0,
        "said": ["success", "Measure: the points let go (Escape); click to drop a first"],
    }
    assert result["clearedAgain"] is False


def test_the_layer_hidden_lets_its_points_go_and_draws_nothing(result):
    assert result["hidden"] == {"points": 0, "drawn": False, "lines": []}


# ---- what a click reads under it ----------------------------------------------------

WORDS = """
import { featureWords, featureBrief, declaredWords, pairWords, hintAfter, inPartFrame, statusOf } from "/static/measure_world.js";
const out = {};
const hole = { kind: "round", sense: "hole", diameter: 32, radius: 16, flats: 31.9904, sides: 128, facets: 128, closed: true, arc: 360,
    vertices: 256, residual: 0.0001, axis: [0, 0, 1], middle: [0, 0, 15], length: 30, slope: 0, lean: 0, taper: false, ends: [32, 32],
    frame: "the part's own frame", wall: { thickness: 3 } };
out.hole = featureWords(hole);
out.fine = featureWords({ ...hole, diameter: 10, radius: 5, flats: 9.9998, sides: 360, facets: 360, vertices: 720, wall: null });
out.low = featureWords({ ...hole, diameter: 10, flats: 9.2388, sides: 8, facets: 8, vertices: 16, wall: null, frame: undefined });
out.arc = featureWords({ ...hole, sense: "boss", closed: false, arc: 90.2, facets: 8, diameter: 2, flats: 1.99, sides: 32, wall: null });
out.taper = featureWords({ ...hole, sense: "boss", taper: true, lean: -2.86, ends: [20, 18], length: 20, diameter: 19, flats: 19 });
out.flat = featureWords({ kind: "flat", normal: [0, 0, 1], wall: { thickness: 4, off: 0, parallel: true }, gap: null });
out.slot = featureWords({ kind: "flat", normal: [1, 0, 0], wall: { thickness: 5, off: 30, parallel: false }, gap: { width: 3, off: 0.1, parallel: true } });
out.open = featureWords({ kind: "flat", normal: [0, 0, 1], wall: { why: "the mesh is open there" }, gap: null });
out.unknown = featureWords({ kind: "unknown", why: "a sphere" });
out.none = featureWords(undefined);
const match = (apart) => ({ round: 2, match: { name: "port", type: "bolt_hole", source: "stub", cite: null, diameter: 32, where: "its hole", mesh: 32 + apart, apart } });
out.declared = [declaredWords(match(0.001)), declaredWords(match(0.12)), declaredWords(match(-0.5), { variant: true }),
    declaredWords({ round: 1, match: null }), declaredWords({ round: 0, match: null }), declaredWords(null)];
out.pairs = [pairWords({ edge: { length: 10, meet: 90 } }), pairWords({ edge: { length: 4, meet: null } }),
    pairWords({ angle: { angle: 30, between: 150, parallel: false } }), pairWords({ angle: { angle: 0, between: 180, parallel: true, facing: "apart" } }), pairWords({})];
out.hints = [hintAfter({ kind: "round" }), hintAfter({ kind: "flat" }), hintAfter({ kind: "unknown" }), hintAfter(null)];
out.briefs = [featureBrief(hole), featureBrief({ kind: "flat", wall: { thickness: 4 } }), featureBrief({ kind: "flat", wall: { why: "open" } }),
    featureBrief({ kind: "unknown", why: "a sphere" }), featureBrief(undefined)];
const corner = { kind: "flat", normal: [0, 0, 1], wall: { thickness: 10, off: 0, parallel: true, stepIn: { thickness: 2, at: [5, 5, 10], far: [5, 5, 8] } }, gap: null };
out.corner = [featureWords(corner), featureBrief(corner)];
const far = (key, site) => ({ key, site, kind: "vertex" });
out.statuses = [statusOf({ points: [far("a_long_part_name_of_the_garage", [0, 0, 0]), far("another_long_part_name_of_the_bench", [3, 4, 0])], pair: { edge: { length: 5, meet: 90 } } }),
    statusOf({ points: [far("a", [0, 0, 0]), far("b", [0, 0, 12])], pair: { angle: { angle: 90, between: 90, parallel: false } } }),
    statusOf({ points: [far("a", [0, 0, 0])] }), statusOf({ points: [] })];
// A round read in three.js's frame, its mesh centred on a box whose middle was (1, 2, 3) in the part's.
out.framed = inPartFrame({ axis: [0, 1, 0], middle: [0, 5, 0], across: [1, 0, 0], slope: 0.1, ends: [9, 11] }, [1, 2, 3]);
out.flipped = inPartFrame({ axis: [0, 0, 1], middle: [0, 0, 0], across: [1, 0, 0], slope: 0.1, ends: [9, 11] }, [0, 0, 0]);
console.log(JSON.stringify(out));
"""


@pytest.fixture(scope="module")
def words(tmp_path_factory):
    return run_module(tmp_path_factory.mktemp("measure_words"), WORDS)


def test_a_round_says_what_it_is_fitted_to_how_well_and_where_its_axis_runs(words):
    assert words["hole"] == (
        "a hole ⌀ 32.00 mm across its vertices (fitted to the drawn mesh: 256 vertices of the whole round, "
        "128 facets; 0.00 mm from the circle, root mean square); across its flats ⌀ 31.99 mm, a regular "
        "128-gon's, nearer what a printed hole takes; its axis (0.00, 0.00, 1.00) through (0.00, 0.00, 15.00) mm "
        "in the part's own frame; its wall 3.00 mm thick, cast from the click to the face beyond"
    )
    assert "across its flats" not in words["fine"], "flats that read as the vertices do are not said twice"
    assert "; across its flats ⌀ 9.24 mm, a regular 8-gon's, nearer what a printed hole takes" in words["low"]
    assert words["low"].endswith("in its mesh's frame")
    assert words["arc"].startswith("a boss ⌀ 2.00 mm across its vertices (fitted to the drawn mesh: 256 vertices of an arc of 90 degrees of it, 8 facets")
    assert "what calipers across two flats read" in words["arc"]
    assert (
        "; a taper, its faces leaning 2.9 degrees to its axis, ⌀ 20.00 mm at one end to ⌀ 18.00 mm at the other, "
        "20.00 mm apart: the figure above is its middle's"
    ) in words["taper"]


def test_a_flat_face_says_its_wall_and_any_gap_and_whether_they_are_parallel(words):
    assert words["flat"] == (
        "a flat face, its wall 4.00 mm thick (cast from the click along the face's inward normal to the face "
        "behind it, parallel to it; the drawn mesh)"
    )
    assert "30.0 degrees off parallel" in words["slot"]
    assert words["slot"].endswith("; across it a gap of 3.00 mm to the face that faces it, parallel")
    assert words["open"] == "a flat face, but no wall read behind it: the mesh is open there"
    assert words["unknown"] == "cannot tell a diameter or a wall here: a sphere"
    assert words["none"] is None


def test_the_declared_round_is_said_beside_the_mesh_with_how_far_apart(words):
    same, wider, narrower, none, no_rounds, nothing = words["declared"]
    assert same == (
        "declared: port, a bolt hole ⌀ 32.00 mm (its hole; the part's interface, source stub); "
        "the mesh reads ⌀ 32.00 mm there, the same"
    )
    assert wider.endswith("the mesh reads ⌀ 32.12 mm there, 0.12 mm wider")
    assert narrower.endswith("0.50 mm narrower; declared at the part's defaults, and the mesh drawn is a variant")
    assert none == "declared: none of its 1 round interface lies on this axis, this way round"
    assert no_rounds is None and nothing is None


def test_an_edge_and_an_angle_are_said_between_the_two_points(words):
    assert words["pairs"] == [
        ["an edge of the mesh from point 1 to point 2, 10.00 mm, between faces meeting at 90.0 degrees"],
        ["an edge of the mesh from point 1 to point 2, 4.00 mm, along the mesh's open boundary"],
        ["the faces at point 1 and point 2 stand at 30.0 degrees to each other (their normals 150.0 degrees apart)"],
        ["the faces at point 1 and point 2 are parallel, facing apart"],
        [],
    ]


def test_after_a_first_click_the_status_line_says_what_it_read_and_how_to_read_the_rest(words):
    assert words["briefs"] == [
        "a hole ⌀ 32.00 mm across its vertices",
        "a wall 4.00 mm thick",
        "a flat face, no wall behind it",
        "cannot tell",
        None,
    ]
    assert words["hints"] == [
        "a flat face reads its wall, a second click the distance",
        "a curved face reads its diameter, a second click the distance or the angle",
        "a curved face reads a diameter, a flat face a wall, a second click the distance",
        "a curved face reads a diameter, a flat face a wall, a second click the distance",
    ]


def test_a_round_read_in_threes_frame_is_said_in_the_parts_own(words):
    framed = words["framed"]
    assert framed["axis"] == [0, 0, 1] and framed["middle"] == [1, 2, 8]
    assert framed["slope"] == 0.1 and framed["ends"] == [9, 11]
    flipped = words["flipped"]
    assert flipped["axis"] == [0, 1, 0], "three.js's z is the site's -y, written the other way along"
    assert flipped["slope"] == -0.1 and flipped["ends"] == [11, 9]


CLICKS = (
    FAKE_DOCUMENT
    + """
import * as THREE from "three";
import { mountMeasureWorld } from "/static/measure_world.js";
import { layersSaid } from "/static/layers_world.js";
import { makePickScope, MEASURE } from "/static/pick_scope.js";
const out = {};
out.measureOn = `Measure: ${layersSaid({ layer: MEASURE, shown: true }, { wallsSaid: () => "" }).slice("Measure: ".length)}`;
// A tube as an STL draws it: a 32 mm bore in a 38 mm outside, 30 long, 128 facets, z up in
// the part's frame; turned into three.js's and centred on its box, as the page loads one.
const soup = [], ring = (r, k, z) => [r * Math.cos((2 * Math.PI * (k % 128)) / 128), r * Math.sin((2 * Math.PI * (k % 128)) / 128), z];
const quad = (a, b, c, d) => soup.push(...a, ...b, ...c, ...a, ...c, ...d);
for (let k = 0; k < 128; k++) {
    quad(ring(19, k, 0), ring(19, k + 1, 0), ring(19, k + 1, 30), ring(19, k, 30));
    quad(ring(16, k, 0), ring(16, k, 30), ring(16, k + 1, 30), ring(16, k + 1, 0));
    quad(ring(16, k, 30), ring(19, k, 30), ring(19, k + 1, 30), ring(16, k + 1, 30));
    quad(ring(16, k, 0), ring(16, k + 1, 0), ring(19, k + 1, 0), ring(19, k, 0));
}
const geometry = new THREE.BufferGeometry();
geometry.setAttribute("position", new THREE.Float32BufferAttribute(soup, 3));
const position = geometry.attributes.position;
for (let i = 0; i < position.count; i++) { const y = position.getY(i), z = position.getZ(i); position.setY(i, z); position.setZ(i, -y); }
geometry.computeBoundingBox();
const centre = geometry.boundingBox.getCenter(new THREE.Vector3());
geometry.center();
const port = new THREE.Mesh(geometry, new THREE.MeshBasicMaterial());
port.userData.key = "port"; port.userData.centredFrom = [centre.x, -centre.z, centre.y];
const cube = new THREE.Mesh(new THREE.BoxGeometry(10, 10, 10), new THREE.MeshBasicMaterial());
cube.userData.key = "cube"; cube.position.set(100, 0, 0);
const stand = new THREE.Mesh(new THREE.BoxGeometry(10, 10, 10), new THREE.MeshBasicMaterial());
stand.userData = { key: "stand", isPlaceholder: true }; stand.position.set(-100, 0, 0);
const scene = new THREE.Scene(); scene.add(port, cube, stand);
for (const o of [port, cube, stand]) o.updateMatrixWorld();
const camera = new THREE.PerspectiveCamera(45, 800 / 600, 0.1, 2000);
const look = (from, to) => { camera.position.set(...from); camera.lookAt(...to); camera.updateMatrixWorld(); };
const canvas = { clientWidth: 800, clientHeight: 600, getBoundingClientRect: () => ({ left: 0, top: 0, width: 800, height: 600 }) };
const raycaster = new THREE.Raycaster();
const pick = (event) => {
    raycaster.setFromCamera(new THREE.Vector2((event.clientX / 800) * 2 - 1, -(event.clientY / 600) * 2 + 1), camera);
    return raycaster.intersectObjects([port, cube, stand], false);
};
const onScreen = (p) => { const s = p.clone().project(camera); return { clientX: ((s.x + 1) / 2) * 800, clientY: ((1 - s.y) / 2) * 600 }; };
const nodes = { port: { part_ref: "dust_port" }, cube: {}, stand: {} };
const asked = [];
const scope = makePickScope({ storage: { getItem: () => null, setItem() {}, removeItem() {} } });
scope.setShown(MEASURE, true);
const said = [];
const m = mountMeasureWorld({
    scope, scene: () => scene, camera: () => camera, canvas: () => canvas, pick, raycaster: () => raycaster,
    nodeOf: (k) => nodes[k], meshOf: () => null, selected: () => null, envelopeOf: () => null, frameOf: () => null,
    fallbackColour: 0x4488cc, dispose: () => {}, setStatus: (words, kind) => said.push(words), invalidate: () => {}, refresh: () => {},
    interfacesOf: async (ref) => { asked.push(ref); return [{ name: "port", type: "socket", source: "stub", position: { x: 0, y: 0, z: 30 }, normal: { x: 0, y: 0, z: 1 }, diameter: 32, depth: 30 }]; },
});
const settle = () => new Promise((resolve) => setTimeout(resolve, 0));
// The far side of the bore, seen through its mouth.
look([0, 60, 40], [0, 0, -10]);
m.click(onScreen(new THREE.Vector3(0, 0, -15.95)));
await settle(); await settle();
const q = m.points[0];
out.bore = { kind: q.feature.kind, sense: q.feature.sense, diameter: q.feature.diameter, axis: q.feature.axis, middle: q.feature.middle,
    frame: q.feature.frame, lines: [...m.lines], said: said[0], asked, rods: m.rods.length, labels: m.labels.length };
// A stand-in box: nothing of the part to fit.
m.clear();
look([-70, 25, 40], [-100, 0, 0]);
m.click(onScreen(new THREE.Vector3(-100, 5, 0)));
await settle();
out.stand = m.lines[0];
out.standSaid = said[said.length - 1];
// Two corners along one edge of the cube, then two of its faces.
m.clear();
look([130, 25, 40], [100, 0, 0]);
m.click(onScreen(new THREE.Vector3(104.6, 5, 4.6)));
m.click(onScreen(new THREE.Vector3(95.4, 5, 4.6)));
await settle();
out.edge = { kinds: m.points.map((p) => p.kind), lines: [...m.lines], labels: m.labels.length, said: said[said.length - 1] };
// Each line drawn where it is seen, and again faint over everything; its labels on top.
const rod = m.rods[0], faint = rod.children[0];
out.drawn = { seen: rod.material.depthTest, faint: faint ? { depthTest: faint.material.depthTest, opacity: faint.material.opacity } : null,
    order: [rod.renderOrder, faint ? faint.renderOrder : null, m.labels[0].renderOrder], boxes: m.labelBoxes().length };
m.click(onScreen(new THREE.Vector3(100, 5, 0)));
m.click(onScreen(new THREE.Vector3(102, 1, 5)));
await settle();
out.angle = { kinds: m.points.map((p) => p.feature.kind), lines: [...m.lines], said: said[said.length - 1] };
console.log(JSON.stringify(out));
"""
)


@pytest.fixture(scope="module")
def clicks(tmp_path_factory):
    return run_module(tmp_path_factory.mktemp("measure_clicks"), CLICKS)


def test_a_click_on_a_bore_reads_its_diameter_in_the_parts_frame_beside_the_declared_socket(clicks):
    bore = clicks["bore"]
    assert bore["kind"] == "round" and bore["sense"] == "hole"
    assert bore["diameter"] == pytest.approx(32, abs=1e-3)
    assert bore["axis"] == pytest.approx([0, 0, 1], abs=1e-6)
    assert bore["middle"] == pytest.approx([0, 0, 15], abs=1e-3)
    assert bore["frame"] == "the part's own frame"
    assert bore["asked"] == ["dust_port"]
    first, declared, point = bore["lines"]
    assert first.startswith("point 1 on port: a hole ⌀ 32.00 mm across its vertices")
    assert "its wall 3.00 mm thick" in first
    assert declared == (
        "point 1 on port, declared: port, a socket ⌀ 32.00 mm (its bore at the mouth; the part's interface, "
        "source stub); the mesh reads ⌀ 32.00 mm there, the same"
    )
    assert point.startswith("point 1 (surface) on port at ")
    assert bore["said"] == (
        "Measure: point 1 on port: a hole ⌀ 32.00 mm across its vertices; "
        "a flat face reads its wall, a second click the distance (the rest in Layers)"
    )
    # The circle round the bore and the line across it, labelled.
    assert bore["rods"] == 48 + 1 and bore["labels"] == 1


def test_a_stand_in_box_cannot_be_told(clicks):
    assert clicks["stand"] == (
        "point 1 on stand: cannot tell a diameter or a wall here: a stand-in box is drawn here, not the part's mesh: "
        "there is no shape of it to fit"
    )
    assert clicks["standSaid"] == (
        "Measure: point 1 on stand: cannot tell; a curved face reads a diameter, a flat face a wall, "
        "a second click the distance (why in Layers)"
    )


def test_a_first_clicks_status_line_is_no_longer_than_measures_own(clicks):
    """The status line stands under the world: a line that wraps further makes the world
    shorter, and what a second click aims at moves under the pointer. What a first click
    says is no longer than the words Measure is turned on with, which the line held before."""
    for said in (clicks["bore"]["said"], clicks["standSaid"]):
        assert len(said) <= len(clicks["measureOn"]), said


def test_two_corners_along_an_edge_read_the_edge_and_two_faces_their_angle(clicks):
    edge = clicks["edge"]
    assert edge["kinds"] == ["vertex", "vertex"]
    distance, along = edge["lines"][:2]
    assert distance.startswith("10.00 mm between point 1 (vertex)")
    assert along == "an edge of the mesh from point 1 to point 2, 10.00 mm, between faces meeting at 90.0 degrees"
    angle = clicks["angle"]
    assert angle["kinds"] == ["flat", "flat"]
    assert "the faces at point 1 and point 2 stand at 90.0 degrees to each other (their normals 90.0 degrees apart)" in angle["lines"]
    assert any(line.startswith("point 2 on cube: a flat face, its wall 10.00 mm thick") for line in angle["lines"])


def test_on_the_universes_sphere_a_point_is_said_in_its_parts_frame_and_its_turn_is_not(result):
    """A part on the sphere stands where the layout put it, turned to face outward: its
    points are said in its part's own frame, the two points' components too, and its
    selection says its size and not the layout's turn."""
    distance, *_rest = result["sphere"]
    assert "at 20.00, 10.00, 5.00 mm in its part's own frame" in distance
    assert "1500" not in distance
    assert "dx -20.00 mm, dy -10.00 mm, dz 0.00 mm (its part's own frame;" in distance
    (selection,) = [line for line in result["sphere"] if line.startswith("leaf measures")]
    assert selection == (
        "leaf measures x 20.00 mm × y 10.00 mm × z 5.00 mm along its own axes "
        "(the drawn mesh, as loaded)"
    )


def test_by_a_faces_edge_the_wall_a_step_in_is_said_beside_it(words):
    said, brief = words["corner"]
    assert said.endswith(
        "; a step in toward the face's middle it reads 2.00 mm: by the face's edge the cast "
        "runs down a wall that meets the face there"
    )
    assert brief == "a wall 10.00 mm here, 2.00 mm a step in"


def test_two_points_are_said_short_on_the_status_line(words):
    edge, angle, one, none = words["statuses"]
    assert edge == "5.00 mm from point 1 to point 2, an edge of the mesh (the rest in Layers)"
    assert angle == "12.00 mm from point 1 to point 2, the faces at 90.0 degrees (the rest in Layers)"
    assert one == "point 1 on a; click a second point (Escape starts again)"
    assert none is None


def test_every_status_line_a_click_says_is_no_longer_than_measures_own(clicks):
    """The status line is one line under the world: what two points say is no longer than
    the words Measure is turned on with, as a first click's is, whatever the reading."""
    assert clicks["edge"]["said"].startswith("Measure: 10.00 mm from point 1 to point 2, an edge")
    assert clicks["angle"]["said"].endswith("from point 1 to point 2, the faces at 90.0 degrees (the rest in Layers)")
    for said in (clicks["edge"]["said"], clicks["angle"]["said"]):
        assert len(said) <= len(clicks["measureOn"]), said


def test_a_line_is_drawn_where_it_is_seen_and_faint_where_it_is_behind_something(clicks):
    """A rod is depth-tested, so a hole's circle seen through its part's outside is not
    drawn as if on it; a faint copy over everything says where it runs; the labels are
    drawn last, and where they were laid is what the name badges keep off."""
    drawn = clicks["drawn"]
    assert drawn["seen"] is True
    assert drawn["faint"]["depthTest"] is False and drawn["faint"]["opacity"] < 0.5
    rod, faint, label = drawn["order"]
    assert rod < faint < label
    assert drawn["boxes"] >= 1


# ---- a part's dimensions: marked, read, and picked by their labels --------------------

DIMENSIONS = (
    FAKE_DOCUMENT
    + """
import * as THREE from "three";
import { dimensionLabel, dimensionLines, drawnAs, partToMesh, pickAt, mountMeasureWorld } from "/static/measure_world.js";
import { makePickScope, MEASURE } from "/static/pick_scope.js";
const out = {};
const check = (measured, within) => ({ name: "x", designed: 10, measured, deviation: measured - 10, tolerance: 0.1, tolerance_from: "part", within });
const read = (measured, within) => ({ filed: "filed-1", at: "2026-11-22T10:00:00Z", made: "turn-1", read: [measured], checked: check(measured, within) });
const dims = {
    part: "cube", drawer: "20261122T100000.000", file_id: "f1", made: "print", machine: "printer_1",
    tolerance: { value: 0.1, source: "part", said: "cube's print settings" },
    dimensions: [
        { name: "x", words: "the part across X, at its widest", kind: "outside", designed: 10, frame: "box", reading: read(10.25, false) },
        // As it prints, 12 mm across Y: not the cube drawn here, whose y is 10 mm.
        { name: "y", words: "the part across Y, at its widest", kind: "outside", designed: 12, frame: "box", reading: null },
        { name: "z", words: "the part's height, bed face to top", kind: "height", designed: 10, frame: "box", reading: read(10.05, true) },
    ],
};
out.labels = [dimensionLabel("x", 10, "mesh"), dimensionLabel("x", 10, "mesh", dims.dimensions[0].reading)];
out.lines = dimensionLines("cube", dims, ["x", "y", "z"]);
out.apart = dimensionLines("cube", dims, ["x"])[1];
out.drawnAs = [drawnAs(10, 10.004), drawnAs(10, 10.05), drawnAs(106.593, 102)];
out.nothing = [dimensionLines("cube", null), dimensionLines("cube", { part: "cube", dimensions: [], why: "nothing made" })];
out.kept = dimensionLines("cube", { ...dims, drawer: null, tolerance: { value: 0.2, source: "default", said: "a default, 0.2 mm: nothing states one" },
    dimensions: dims.dimensions.map((d) => ({ ...d, reading: null })) }, ["x", "y", "z"]);
// A point of the part's frame put in its centred mesh, and read back as the layer reads one.
const local = partToMesh([5, -4, 8], [1, 2, 3]);
out.local = local;
out.back = [local[0] + 1, -local[2] + 2, local[1] + 3];
const picks = [{ name: "a", box: { l: 0, r: 10, t: 0, b: 10 } }, { name: "b", box: { l: 5, r: 20, t: 5, b: 20 } }];
out.picks = [pickAt(picks, 7, 7)?.name, pickAt(picks, 2, 2)?.name, pickAt(picks, 30, 30)];

// A cube, a part's piece, selected with Measure shown: its box lines are its dimensions.
const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(45, 800 / 600, 0.1, 1000);
camera.position.set(30, 25, 40); camera.lookAt(0, 0, 0); camera.updateMatrixWorld();
const mesh = new THREE.Mesh(new THREE.BoxGeometry(10, 10, 10), new THREE.MeshBasicMaterial());
mesh.userData.key = "cube"; scene.add(mesh); mesh.updateMatrixWorld();
const canvas = { clientWidth: 800, clientHeight: 600, getBoundingClientRect: () => ({ left: 0, top: 0, width: 800, height: 600 }) };
const nodes = { cube: { part_ref: "cube" } };
const scope = makePickScope({ storage: { getItem: () => null, setItem() {}, removeItem() {} } });
const asked = [], picked = [], said = [];
const m = mountMeasureWorld({
    scope, scene: () => scene, camera: () => camera, canvas: () => canvas, pick: () => [],
    nodeOf: (k) => nodes[k], meshOf: (k) => (k === "cube" ? mesh : null), selected: () => "cube",
    envelopeOf: () => null, frameOf: () => null, fallbackColour: 0x4488cc,
    dispose: (o) => o.traverse((x) => { x.geometry?.dispose(); x.material?.dispose(); }),
    setStatus: (words, kind) => said.push([kind, words]), invalidate: () => {}, refresh: () => {},
    dimensionsOf: (part) => { asked.push(part); return Promise.resolve(dims); },
    pickDimension: (p) => picked.push({ part: p.part, key: p.key, name: p.name, drawer: p.dims && p.dims.drawer }),
});
const settle = () => new Promise((resolve) => setTimeout(resolve, 0));
scope.setShown(MEASURE, true);
m.layersApplied();
await settle(); await settle();
out.asked = [...asked];
out.texts = m.labels.map((s) => s.userData.text);
out.inks = m.rods.map((r) => r.material.color.getHexString());
out.readings = m.lines.filter((l) => l.startsWith("cube's"));
m.place();
const x = m.picks.find((p) => p.name === "x");
out.pickable = m.picks.map((p) => p.name).sort();
m.click({ clientX: (x.box.l + x.box.r) / 2, clientY: (x.box.t + x.box.b) / 2 });
await settle();
out.picked = picked;
out.points = m.points.length;
// Forgotten (a filing in Part › Feedback), asked again.
m.forgetDimensions("cube");
await settle(); await settle();
out.askedAgain = asked.length;
// A part nothing was made of: its box lines as they were, no label a pick.
const bare = new THREE.Scene();
bare.add(mesh);
const m2 = mountMeasureWorld({
    scope, scene: () => bare, camera: () => camera, canvas: () => canvas, pick: () => [],
    nodeOf: (k) => nodes[k], meshOf: (k) => (k === "cube" ? mesh : null), selected: () => "cube",
    envelopeOf: () => null, frameOf: () => null, fallbackColour: 0x4488cc,
    dispose: (o) => o.traverse((x) => { x.geometry?.dispose(); x.material?.dispose(); }),
    setStatus: () => {}, invalidate: () => {}, refresh: () => {},
    dimensionsOf: () => Promise.resolve({ part: "cube", dimensions: [], why: "nothing made of cube yet" }),
});
m2.layersApplied();
await settle(); await settle();
m2.place();
out.unmade = { picks: m2.picks.length, texts: m2.labels.map((l) => l.userData.text).sort(), lines: m2.lines.filter((l) => l.startsWith("cube's")) };
// A part that names a plan: a feature's line through (x, 5, 5) of its own frame, across it
// from x 0 to x 10, on a cube whose box stood from 0 to 10 in that frame.
const planned = (size) => {
    const scene3 = new THREE.Scene();
    const coupon = new THREE.Mesh(new THREE.BoxGeometry(10, 10, 10), new THREE.MeshBasicMaterial());
    coupon.userData.centredFrom = [5, 5, 5];
    scene3.add(coupon); coupon.updateMatrixWorld();
    const plan = { ...dims, size, dimensions: [{ name: "a_x", words: "across a", kind: "outside", axis: "x", designed: 10, frame: "part", at: [0, 5, 5], faces: [0, 10], reading: null }] };
    const m3 = mountMeasureWorld({
        scope, scene: () => scene3, camera: () => camera, canvas: () => canvas, pick: () => [],
        nodeOf: (k) => nodes[k], meshOf: (k) => (k === "cube" ? coupon : null), selected: () => "cube",
        envelopeOf: () => null, frameOf: () => null, fallbackColour: 0x4488cc,
        dispose: (o) => o.traverse((x) => { x.geometry?.dispose(); x.material?.dispose(); }),
        setStatus: () => {}, invalidate: () => {}, refresh: () => {},
        dimensionsOf: () => Promise.resolve(plan),
    });
    return m3;
};
for (const [name, size] of [["asSliced", [10, 10, 10]], ["otherwise", [10, 12, 10]]]) {
    const m3 = planned(size);
    m3.layersApplied();
    await settle(); await settle();
    m3.place();
    const s3 = m3.labels.find((l) => l.userData.text.startsWith("a_x"));
    out[name] = { picks: m3.picks.map((p) => p.name), from: s3 ? s3.userData.from.toArray() : null, to: s3 ? s3.userData.to.toArray() : null,
        apart: m3.lines.filter((l) => l.includes("not drawn here")) };
}
// An answer slow to come, forgotten (a piece chosen in Part › Feedback) and asked again
// meanwhile: the newer answer stands when the older comes in after it.
{
    const scene4 = new THREE.Scene();
    const cube4 = new THREE.Mesh(new THREE.BoxGeometry(10, 10, 10), new THREE.MeshBasicMaterial());
    cube4.userData.key = "cube"; scene4.add(cube4); cube4.updateMatrixWorld();
    const late = [];
    let calls = 0;
    const m4 = mountMeasureWorld({
        scope, scene: () => scene4, camera: () => camera, canvas: () => canvas, pick: () => [],
        nodeOf: (k) => nodes[k], meshOf: (k) => (k === "cube" ? cube4 : null), selected: () => "cube",
        envelopeOf: () => null, frameOf: () => null, fallbackColour: 0x4488cc,
        dispose: (o) => o.traverse((x) => { x.geometry?.dispose(); x.material?.dispose(); }),
        setStatus: () => {}, invalidate: () => {}, refresh: () => {},
        dimensionsOf: () => (++calls === 1 ? new Promise((resolve) => late.push(resolve)) : Promise.resolve({ ...dims, drawer: "newer" })),
    });
    m4.layersApplied();
    await settle();
    m4.forgetDimensions("cube");
    await settle(); await settle();
    late[0]({ ...dims, drawer: "older" });
    await settle(); await settle();
    m4.place();
    out.race = { calls, piece: m4.lines.filter((l) => l.startsWith("cube's dimensions")) };
}
console.log(JSON.stringify(out));
"""
)


@pytest.fixture(scope="module")
def marked(tmp_path_factory):
    return run_module(tmp_path_factory.mktemp("measure_dimensions"), DIMENSIONS)


def test_a_dimension_s_label_says_its_size_and_its_newest_reading(marked):
    assert marked["labels"] == ["x 10.00 mm · mesh", "x 10.00 mm · mesh · read 10.25 +0.25"]


def test_the_readings_say_the_piece_its_tolerance_and_each_dimension_read(marked):
    assert marked["drawnAs"] == [True, False, False]
    assert marked["apart"] == (
        "cube's y, z: not drawn here, the part drawn not being as it was sliced (as it rests, "
        "or another variant); read in Part › Feedback"
    )
    assert marked["lines"] == [
        "cube's dimensions, as printed on printer_1: its piece 20261122T100000.000, each checked "
        "within ± 0.10 mm (part's: cube's print settings); a dimension's label clicked takes its "
        "reading in Part › Feedback",
        "cube's x, the part across X, at its widest: designed 10.00 mm, read 10.25 mm (filed-1, "
        "turn-1), +0.25 mm: outside ± 0.10",
        "cube's z, the part's height, bed face to top: designed 10.00 mm, read 10.05 mm (filed-1, "
        "turn-1), +0.05 mm: within ± 0.10",
    ]
    assert marked["nothing"] == [[], []]
    assert marked["kept"] == [
        "cube's dimensions, as printed on printer_1: its kept file f1, no drawer yet, each checked "
        "within ± 0.20 mm (a default, 0.2 mm: nothing states one); a dimension's label clicked "
        "takes its reading in Part › Feedback"
    ]


def test_a_point_of_the_part_s_frame_is_put_where_its_centred_mesh_reads_it_back(marked):
    assert marked["local"] == [4, 5, 6]
    assert marked["back"] == [5, -4, 8]
    assert marked["picks"] == ["b", "a", None]


def test_a_part_s_piece_wears_its_dimensions_coloured_by_whether_each_is_within(marked):
    """The cube's box lines are its x and z, whose sides are as long as designed: x read
    outside its tolerance in the page's --bad, z within in --ok, each label a pick; y, 12 mm
    as it prints and 10 drawn, is a plain line in the layer's own colour, no pick, and the
    readings say it is read in Part › Feedback alone."""
    assert marked["asked"] == ["cube"]
    assert sorted(marked["texts"]) == [
        "x 10.00 mm · mesh · read 10.25 +0.25",
        "y 10.00 mm · mesh",
        "z 10.00 mm · mesh · read 10.05 +0.05",
    ]
    assert sorted(set(marked["inks"])) == ["4488cc", "6fdb75", "ff8080"]
    assert len(marked["readings"]) == 4 and "cube's y: not drawn here" in marked["readings"][1]
    assert marked["pickable"] == ["x", "z"]


def test_a_dimension_s_label_clicked_picks_it_and_drops_no_point(marked):
    assert marked["picked"] == [
        {"part": "cube", "key": "cube", "name": "x", "drawer": "20261122T100000.000"}
    ]
    assert marked["points"] == 0
    assert marked["askedAgain"] == 2


def test_a_part_nothing_was_made_of_wears_its_box_lines_as_they_were(marked):
    assert marked["unmade"] == {
        "picks": 0,
        "texts": ["x 10.00 mm · mesh", "y 10.00 mm · mesh", "z 10.00 mm · mesh"],
        "lines": [],
    }


def test_a_plan_s_feature_is_drawn_along_its_line_where_the_part_is_drawn_as_sliced(marked):
    """In the part's own frame its line runs from (0, 5, 5) to (10, 5, 5): in the cube
    centred on that box, from x -5 to x 5 through the middle. Drawn in another box than the
    one sliced, the plan is not drawn, and the reading says so."""
    assert marked["asSliced"]["picks"] == ["a_x"]
    assert marked["asSliced"]["from"] == pytest.approx([-5, 0, 0])
    assert marked["asSliced"]["to"] == pytest.approx([5, 0, 0])
    assert marked["asSliced"]["apart"] == []
    assert marked["otherwise"]["picks"] == [] and marked["otherwise"]["from"] is None
    assert marked["otherwise"]["apart"] == [
        "cube's a_x: not drawn here, the part drawn not being as it was sliced (as it rests, "
        "or another variant); read in Part › Feedback"
    ]


def test_an_older_answer_come_late_leaves_the_newer_standing(marked):
    """Asked, forgotten as a piece is chosen in Part › Feedback, and asked again: the
    second answer comes first, and the first, come after it, is let go."""
    assert marked["race"]["calls"] == 2
    (line,) = marked["race"]["piece"]
    assert "its piece newer" in line, line
