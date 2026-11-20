"""The pick scope (apothecary/static/pick_scope.js): how deep a click reaches and which
layers are shown and selectable. The module has no DOM, so node runs it here: its
defaults, the rule that selectable lies within shown, and what is kept.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "apothecary" / "static" / "pick_scope.js"
NODE = shutil.which("node") or str(Path.home() / ".local" / "bin" / "node")

pytestmark = pytest.mark.skipif(not Path(NODE).exists(), reason="node is not installed")

SCRIPT = """
import { makePickScope, WALL, GRID, MACHINE_BUTTONS, MEASURE, layersOf, kindOf } from "%(module)s";
const store = () => { const m = new Map(); return {
    getItem: (k) => (m.has(k) ? m.get(k) : null), setItem: (k, v) => m.set(k, v), removeItem: (k) => m.delete(k), m }; };
const out = {};
const piece = (shell, category) => ({ name: "p", shell, category });
const s = makePickScope({ storage: store() });
out.defaults = {
    depth: s.depth(),
    part: s.pickable(piece(0, "part")), outer: s.pickable(piece(3, "part")), wall: s.pickable(piece(null, "wall")),
    drawnWall: s.drawn(piece(null, "wall")), grid: s.isShown(GRID), buttons: s.isShown(MACHINE_BUTTONS),
    bare: s.pickable({ name: "x" }) && s.drawn({ name: "x" }) && s.pickable(null),
    json: s.toJSON(),
};
// Selectable within shown.
s.setShown("shell:3", false);
out.hidden = { selectable: s.isSelectable("shell:3"), pickable: s.pickable(piece(3, "part")), drawn: s.drawn(piece(3, "part")) };
s.setShown("shell:3", true);
out.reshown = s.pickable(piece(3, "part"));
s.setSelectable("shell:3", false);
out.passed = { drawn: s.drawn(piece(3, "part")), pickable: s.pickable(piece(3, "part")), inner: s.pickable(piece(0, "part")) };
s.setShown("shell:3", false);
s.setSelectable("shell:3", true);
out.tickedShows = { shown: s.isShown("shell:3"), selectable: s.isSelectable("shell:3") };
out.shownOnly = { refused: s.setSelectable(GRID, true), selectable: s.isSelectable(GRID) };
// Measure is a shown-only layer, off at first, and never kept.
const mm = makePickScope({ storage: store() });
out.measure = { first: mm.isShown(MEASURE), refused: mm.setSelectable(MEASURE, true), json: mm.toJSON() };
mm.setShown(MEASURE, true);
out.measure.on = mm.isShown(MEASURE); out.measure.keptOn = mm.toJSON();
mm.reset(); out.measure.reset = mm.isShown(MEASURE);
const kept2 = store(); const m2 = makePickScope({ storage: kept2 }); m2.setShown(MEASURE, true); m2.setDepth(2);
out.measure.after = makePickScope({ storage: kept2 }).isShown(MEASURE);
// Depth is clamped to a whole number of at least one.
out.depths = [s.setDepth(0), s.depth(), s.setDepth(2.9), s.depth(), s.setDepth(999), s.depth(), s.setDepth("x"), s.depth()];
// Told once of a change, and not of a no-change.
let told = 0; s.onChange(() => { told += 1; });
s.setDepth(s.depth()); s.setShown("shell:9", true);
s.setShown("shell:9", false); s.setShown("shell:9", false); s.setShown("shell:9", true);
out.told = told;
// Kept, and read back by another scope on the same storage; walls selectable is not kept.
const kept = store();
const a = makePickScope({ storage: kept });
a.setDepth(3); a.setShown("shell:1", false); a.setSelectable("category:part", false); a.setSelectable(WALL, true); a.setShown(GRID, false);
const b = makePickScope({ storage: kept });
out.kept = { json: b.toJSON(), wall: b.isSelectable(WALL), raw: kept.m.get("apothecary.pickScope") };
b.reset();
out.reset = { json: b.toJSON(), stored: kept.m.has("apothecary.pickScope") };
// A damaged store, and a store that throws, leave the defaults.
const bad = store(); bad.setItem("apothecary.pickScope", "{nope");
const c = makePickScope({ storage: bad });
const throwing = { getItem() { throw new Error("no"); }, setItem() { throw new Error("no"); }, removeItem() { throw new Error("no"); } };
const d = makePickScope({ storage: throwing }); d.setDepth(2);
out.damaged = { c: c.toJSON(), d: d.depth() };
out.layers = layersOf({ shell: 2, category: "part" });
// Only this and All: among a layer's kind, told once, selectable as it was chosen.
const site = { shells: [0, 1, 2], categories: ["bolt", "board"] };
out.kinds = [kindOf("shell:1", site), kindOf("category:board", site), kindOf(GRID, site),
    kindOf(MACHINE_BUTTONS, site), kindOf(MEASURE, site), kindOf("shell:7", site)];
const o = makePickScope({ storage: store() });
let heard = []; o.onChange((what) => heard.push(what));
o.setSelectable("shell:1", false);
out.only = { did: o.showOnly("shell:1", kindOf("shell:1", site)), again: o.showOnly("shell:1", kindOf("shell:1", site)),
    shown: [0, 1, 2].map((n) => o.isShown(`shell:${n}`)), selectable1: o.isSelectable("shell:1"),
    categories: o.isShown("category:bolt"), json: o.toJSON() };
out.all = { did: o.showAll(kindOf("shell:0", site)), again: o.showAll(kindOf("shell:0", site)),
    shown: [0, 1, 2].map((n) => o.isShown(`shell:${n}`)), selectable1: o.isSelectable("shell:1"),
    selectable0: o.isSelectable("shell:0") };
o.showOnly(GRID, kindOf(GRID, site));
out.world = { grid: o.isShown(GRID), buttons: o.isShown(MACHINE_BUTTONS), measure: o.isShown(MEASURE) };
out.heard = heard;
console.log(JSON.stringify(out));
"""


@pytest.fixture(scope="module")
def result(tmp_path_factory):
    folder = tmp_path_factory.mktemp("pick_scope")
    module = folder / "pick_scope.mjs"
    module.write_text(MODULE.read_text(encoding="utf-8"), encoding="utf-8")
    script = folder / "run.mjs"
    script.write_text(SCRIPT % {"module": module.as_uri()}, encoding="utf-8")
    done = subprocess.run(
        [NODE, str(script)], capture_output=True, text=True, timeout=60, check=False
    )
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


def test_the_defaults_are_what_the_page_did_before(result):
    d = result["defaults"]
    assert d["depth"] == 1
    assert d["part"] and d["outer"]
    assert not d["wall"]
    assert d["drawnWall"] and d["grid"] and d["buttons"] and d["bare"]
    assert d["json"] == {"depth": 1, "hidden": [], "unselectable": []}


def test_selectable_lies_within_shown(result):
    assert result["hidden"] == {"selectable": False, "pickable": False, "drawn": False}
    assert result["reshown"] is True
    assert result["passed"] == {"drawn": True, "pickable": False, "inner": True}
    assert result["tickedShows"] == {"shown": True, "selectable": True}
    assert result["shownOnly"] == {"refused": False, "selectable": False}


def test_depth_is_a_whole_number_from_one(result):
    assert result["depths"] == [False, 1, True, 2, True, 8, False, 8]


def test_a_change_is_told_once_and_a_no_change_not_at_all(result):
    assert result["told"] == 2


def test_what_differs_is_kept_and_walls_selectable_is_not(result):
    kept = result["kept"]
    assert kept["json"] == {
        "depth": 3,
        "hidden": ["grid", "shell:1"],
        "unselectable": ["category:part"],
    }
    assert kept["wall"] is False
    assert json.loads(kept["raw"]) == kept["json"]
    assert result["reset"] == {
        "json": {"depth": 1, "hidden": [], "unselectable": []},
        "stored": False,
    }


def test_storage_that_is_damaged_or_refused_leaves_the_defaults(result):
    assert result["damaged"] == {
        "c": {"depth": 1, "hidden": [], "unselectable": []},
        "d": 2,
    }
    assert result["layers"] == ["shell:2", "category:part"]


def test_measure_is_off_at_first_shown_only_and_never_kept(result):
    assert result["measure"] == {
        "first": False,
        "refused": False,
        "json": {"depth": 1, "hidden": [], "unselectable": []},
        "on": True,
        "keptOn": {"depth": 1, "hidden": [], "unselectable": []},
        "reset": False,
        "after": False,
    }


def test_only_this_and_all_act_among_a_layers_kind(result):
    """Only this shows one layer of its kind and hides the others; All shows every one;
    each told once, nothing done twice, and what was chosen selectable kept."""
    assert result["kinds"] == [
        ["shell:0", "shell:1", "shell:2"],
        ["category:bolt", "category:board"],
        ["grid", "machine-buttons"],
        ["grid", "machine-buttons"],
        ["measure"],
        ["shell:0", "shell:1", "shell:2", "shell:7"],
    ]
    assert result["only"] == {
        "did": True,
        "again": False,
        "shown": [False, True, False],
        "selectable1": False,
        "categories": True,
        "json": {"depth": 1, "hidden": ["shell:0", "shell:2"], "unselectable": ["shell:1"]},
    }
    assert result["all"] == {
        "did": True,
        "again": False,
        "shown": [True, True, True],
        "selectable1": False,
        "selectable0": True,
    }
    assert result["world"] == {"grid": True, "buttons": False, "measure": False}
    assert result["heard"] == [
        {"layer": "shell:1", "selectable": False},
        {"layer": "shell:1", "only": True},
        {"layers": ["shell:0", "shell:1", "shell:2"], "all": True},
        {"layer": "grid", "only": True},
    ]
