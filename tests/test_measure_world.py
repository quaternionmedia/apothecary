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
    assert first["lines"][0].startswith("point 1 (vertex) on cube at 5.00, -5.00, 5.00 mm")
    second = result["second"]
    assert [p["kind"] for p in second["points"]] == ["vertex", "surface"]
    assert second["points"][1]["site"] == pytest.approx([0, -5, 0], abs=1e-6)
    assert second["lines"][0].startswith("7.07 mm between point 1 (vertex)")
    assert second["labels"] == 1 and second["rods"] == 1
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
