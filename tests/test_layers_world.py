"""The layers in the world (apothecary/static/layers_world.js): which reason hides a drawn
thing and when it shows again, which grid is wanted where, the rows the Layers window
has, what a change to the pick scope draws again and says, and the order in which the
world is put as the layers say. Node runs the module as the page imports it, with a pick
scope of its own and plain objects for what is drawn."""

from __future__ import annotations

import pytest
from page_modules import HAVE_NODE, run_module

pytestmark = pytest.mark.skipif(not HAVE_NODE, reason="node is not installed")

SCRIPT = """
import { hideFor, gridWanted, layerKinds, redrawsLevel, layersSaid, mountLayersWorld, BY_LAYER } from "/static/layers_world.js";
import { makePickScope, GRID, MEASURE, WALL, MACHINE_BUTTONS } from "/static/pick_scope.js";
const store = () => { const m = new Map(); return {
    getItem: (k) => (m.has(k) ? m.get(k) : null), setItem: (k, v) => m.set(k, v), removeItem: (k) => m.delete(k) }; };
const out = {};

// Each reason taken back on its own: shown only when none holds it.
const o = { userData: {}, visible: true };
const seen = [];
hideFor(o, BY_LAYER, true); seen.push(o.visible);
hideFor(o, "failure", true); seen.push(o.visible);
hideFor(o, BY_LAYER, false); seen.push(o.visible);
hideFor(o, "failure", false); seen.push(o.visible);
hideFor(o, "comparison", false); seen.push(o.visible);
out.hidden = { seen, reasons: [...o.userData.hiddenBy] };

const s = makePickScope({ storage: store() });
const at = (site, focusPath) => gridWanted(s, { site, universe: "apothecary", focusPath });
out.grid = { universe: at("apothecary", []), stepped: at("apothecary", ["dust_port_32"]), garage: at("garage", []), machine: at("garage", ["printer_1"]) };
s.setShown(GRID, false);
out.grid.hidden = [at("garage", []), at("garage", ["printer_1"]), at("apothecary", ["dust_port_32"])];

out.kinds = layerKinds({ children: [
    { shell: 2, category: "part", children: [{ shell: 0, category: "bolt", children: [] }] },
    { category: "wall", children: [] }, { shell: 1, children: [] }] });
out.noKinds = layerKinds(null);
out.redraws = [{ depth: 2 }, { reset: true }, { loaded: true }, { layer: GRID, shown: false }, { layer: "shell:1", selectable: false }, null].map(redrawsLevel);

const walls = () => "Select walls: on";
out.said = [
    { reset: true }, { depth: 1 }, { depth: 3 }, { layer: WALL, selectable: true },
    { layer: MEASURE, shown: true }, { layer: MEASURE, shown: false },
    { layer: "shell:2", only: true }, { layers: [GRID, MACHINE_BUTTONS], all: true },
    { layer: "category:bolt", shown: false }, { layer: "shell:0", shown: true },
    { layer: "shell:3", selectable: false }, { layer: "shell:3", selectable: true }, { loaded: true }, null,
].map((what) => layersSaid(what, { wallsSaid: walls }));

// The world put as the layers say, in its order, and a change answered.
const thing = () => ({ userData: {}, visible: true });
const meshes = { a: thing(), b: thing(), "a.inner": thing() };
const overlays = { a: thing() };
const volumes = { printer_1: thing() };
const grid = thing();
const nodes = { a: { shell: 1, category: "part" }, b: { category: "wall" }, "a.inner": { shell: 0, category: "bolt" } };
const calls = [];
const scope = makePickScope({ storage: store() });
let place = { site: "garage", focusPath: [] };
const world = mountLayersWorld({
    scope, meshes: () => meshes, overlays: () => overlays, volumes: () => volumes, nodeOf: (k) => nodes[k],
    grid: () => grid, place: () => place, universe: "apothecary",
    orbits: () => calls.push("orbits"), anchors: () => calls.push("anchors"), measure: () => calls.push("measure"),
    invalidate: () => calls.push("invalidate"), walls: () => calls.push("walls"), redraw: () => calls.push("redraw"),
    say: (words) => calls.push(`say: ${words}`), wallsSaid: walls,
});
const drawn = () => ({ a: meshes.a.visible, b: meshes.b.visible, inner: meshes["a.inner"].visible, outline: overlays.a.visible, volume: volumes.printer_1.visible, grid: grid.visible });
world.apply();
out.applied = { drawn: drawn(), calls: calls.splice(0) };
scope.onChange((what) => world.changed(what));
scope.setShown("shell:1", false);
out.shellHidden = { drawn: drawn(), calls: calls.splice(0) };
scope.setShown(GRID, false);
out.gridHidden = { drawn: drawn(), calls: calls.splice(0) };
scope.setDepth(2);
out.deeper = { calls: calls.splice(0) };
place = { site: "apothecary", focusPath: [] };
scope.reset();
out.universe = { drawn: drawn(), wanted: world.gridWanted(), calls: calls.splice(0) };
console.log(JSON.stringify(out));
"""


@pytest.fixture(scope="module")
def result(tmp_path_factory):
    return run_module(tmp_path_factory.mktemp("layers_world"), SCRIPT)


def test_a_thing_hidden_for_two_reasons_shows_only_once_both_let_go(result):
    assert result["hidden"]["seen"] == [False, False, False, True, True]
    assert result["hidden"]["reasons"] == []


def test_the_grid_is_wanted_where_there_is_a_floor_and_the_layer_is_shown(result):
    grid = result["grid"]
    assert grid["universe"] is False, "the universe's own level is a sphere: no floor"
    assert grid["stepped"] is True and grid["garage"] is True and grid["machine"] is True
    assert grid["hidden"] == [False, False, False]


def test_the_windows_rows_are_the_shells_and_categories_the_site_has(result):
    assert result["kinds"] == {"shells": [0, 1, 2], "categories": ["bolt", "part", "wall"]}
    assert result["noKinds"] == {"shells": [], "categories": []}


def test_a_depth_a_reset_and_a_scope_read_back_draw_the_level_again(result):
    assert result["redraws"] == [True, True, True, False, False, False]


def test_each_change_is_said_in_its_own_words(result):
    assert result["said"] == [
        "Layers: back to depth 1, every layer shown, every layer selectable but walls",
        "Depth: 1 level below this one, drawn and reached by a click",
        "Depth: 3 levels below this one, drawn and reached by a click",
        "Select walls: on",
        "Measure: on. A click in the world drops a point and selects nothing, a second reads "
        "the distance, a third starts again (Escape too); the selection reads its size",
        "Measure: off, a click selects again",
        "Shell 2 alone of its kind shown: the others hidden, and a click passes through them",
        "Every one shown: Alignment grid, Machine buttons",
        "bolt: hidden, and a click passes through it",
        "Shell 0: shown",
        "Shell 3: a click passes through it",
        "Shell 3: a click picks it",
        None,
        None,
    ]


def test_the_world_is_put_as_the_layers_say_pieces_first_then_the_rest_in_order(result):
    applied = result["applied"]
    assert applied["drawn"] == {
        "a": True, "b": True, "inner": True, "outline": True, "volume": True, "grid": True
    }
    assert applied["calls"] == ["orbits", "anchors", "measure", "invalidate"]


def test_a_shell_hidden_hides_its_pieces_and_their_outlines_and_nothing_else(result):
    hidden = result["shellHidden"]
    assert hidden["drawn"] == {
        "a": False, "b": True, "inner": True, "outline": False, "volume": True, "grid": True
    }
    assert hidden["calls"] == [
        "walls", "orbits", "anchors", "measure", "invalidate", "say: Shell 1: hidden, and a click passes through it"
    ]


def test_the_grid_hidden_hides_the_floor_and_the_build_volumes(result):
    drawn = result["gridHidden"]["drawn"]
    assert drawn["grid"] is False and drawn["volume"] is False and drawn["b"] is True


def test_a_depth_draws_the_level_again_before_the_layers_are_put(result):
    assert result["deeper"]["calls"] == [
        "walls", "redraw", "orbits", "anchors", "measure", "invalidate",
        "say: Depth: 2 levels below this one, drawn and reached by a click",
    ]


def test_a_reset_shows_everything_but_the_universes_own_level_has_no_grid(result):
    universe = result["universe"]
    assert universe["wanted"] is False and universe["drawn"]["grid"] is False
    assert universe["drawn"]["a"] is True and universe["drawn"]["volume"] is True
    assert universe["calls"][:2] == ["walls", "redraw"]
