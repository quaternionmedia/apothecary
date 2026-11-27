"""Typing in an open ring: rad's own vectors, replayed against the Python and the page.

rad's *typing in an open ring finds an item* is held by the ``search`` suite of its
``conformance/vectors.json``. The file is copied here byte for byte
(``tests/conformance/rad/``, with the commit it came from), and both implementations
replay it: ``apothecary/menu.py``'s ``search`` and ``type_query``, and
``apothecary/static/ring.js``'s ``search`` and ``typeQuery`` under node. The page's ring
pressing an address is held by ``tests/e2e/test_ring_search.py``.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from page_modules import HAVE_NODE, run_module
from ring_helpers import rad_ring

from apothecary.menu import (
    BACK,
    SEARCH_SEP,
    Context,
    NoSuchCell,
    Pointing,
    Query,
    Ring,
    Shortcut,
    resolve,
    search,
    search_keys,
    tokens,
    type_query,
)

RAD = Path(__file__).parent / "conformance" / "rad"
SOURCE = json.loads((RAD / "source.json").read_text(encoding="utf-8"))
VECTORS_BYTES = (RAD / "vectors.json").read_bytes()
VECTORS = json.loads(VECTORS_BYTES)
CASES = [c for c in VECTORS["cases"] if "search" in c]


def test_the_vectors_are_rads_at_the_commit_named():
    """A copy, never an edit: its hash and coordinate are the ones its source names."""
    assert hashlib.sha256(VECTORS_BYTES).hexdigest() == SOURCE["sha256"], (
        "tests/conformance/rad/vectors.json is not the file source.json names; copy it from "
        f"{SOURCE['repository']} at {SOURCE['commit']} rather than editing it"
    )
    assert VECTORS["version"] == SOURCE["coordinate"]
    assert set(SOURCE["replayed"]) == {"search"}


def test_there_are_vectors_of_every_kind_to_replay():
    kinds = {kind for c in CASES for kind in ("find", "type", "walk") if c["search"].get(kind)}
    assert kinds == {"find", "type", "walk"}
    assert sum(len(c["search"].get("find", [])) for c in CASES) >= 15


def python_failures(vectors: dict) -> list:
    """Every find, type and walk case the Python does not agree with: [] when it agrees."""
    failures = []
    for case in (c for c in vectors["cases"] if "search" in c):
        suite = case["search"]
        ring = rad_ring(vectors, suite["menu"])
        for k in suite.get("find", []):
            got = search(ring, k["query"])
            pairs = [[r.id, r.address] for r in got]
            if pairs != k["expect"]:
                failures.append(f"{case['name']}: {k['query']!r} -> {pairs}")
            elif "expectEnabled" in k and [r.enabled for r in got] != k["expectEnabled"]:
                failures.append(
                    f"{case['name']}: {k['query']!r} enabled {[r.enabled for r in got]}"
                )
        for k in suite.get("type", []):
            query, text, passed, chosen = Query(), "", [], None
            for key in k["keys"]:
                read = type_query(ring, query, key)
                query, text = read.query, read.text
                passed.append(read.passed)
                chosen = read.chosen or chosen
            got = [chosen.id, chosen.address] if chosen else None
            if (text, passed, got) != (k["expectText"], k["expectPassed"], k.get("expectChosen")):
                failures.append(f"{case['name']}: {k['keys']} -> {text!r} {passed} {got}")
        for k in suite.get("walk", []):
            # The cells pressed, through the rings they open, as Ring.at reads each: what a
            # press reaches is the only part of rad's machine the Python holds.
            stack, effects, committed, is_open = [ring], [], None, True
            for digit in k["address"]:
                cell = int(digit)
                if cell == BACK:
                    if len(stack) > 1:
                        stack.pop()
                        effects.append("back")
                    else:
                        effects.append("cancel")
                        is_open = False
                    continue
                try:
                    option = stack[-1].at(cell)
                except NoSuchCell:
                    continue
                if option.children:
                    stack.append(Ring(title=option.label, options=option.children))
                    effects.append("submenu")
                else:
                    effects.append("commit")
                    committed, is_open = option.id, False
            depth_ok = k.get("expectDepth") is None or len(stack) == k["expectDepth"]
            if (effects, committed, is_open) != (
                k["expectEffects"],
                k["expectCommitted"],
                k["expectOpen"],
            ) or not depth_ok:
                failures.append(
                    f"{case['name']}: ⌗{k['address']} -> {effects} {committed} {is_open} {len(stack)}"
                )
    return failures


def test_the_python_agrees_with_every_search_vector():
    assert python_failures(VECTORS) == []


def test_a_wrong_vector_is_seen_to_fail():
    """The replay is not green by accident: one expectation moved, one failure."""
    broken = json.loads(VECTORS_BYTES)
    case = next(c for c in broken["cases"] if "search" in c and c["search"].get("find"))
    case["search"]["find"][0]["expect"] = list(reversed(case["search"]["find"][0]["expect"]))
    assert len(python_failures(broken)) == 1


PAGE_REPLAY = """
import { search, typeQuery } from "/static/ring.js";
const V = %(vectors)s;
const options = (items) => items.map((it) => ({
    id: it.id, label: it.label, enabled: it.enabled !== false, destructive: !!it.destructive,
    ...(it.children ? { action: null, children: options(it.children) } : { action: "rad:" + it.id }),
}));
const failures = [];
let finds = 0, types = 0;
for (const c of V.cases.filter((c) => c.search)) {
    const ring = { title: V.menus[c.search.menu].title, options: options(V.menus[c.search.menu].items) };
    for (const k of c.search.find || []) {
        finds += 1;
        const got = search(ring, k.query);
        const pairs = got.map((r) => [r.id, r.address]);
        if (JSON.stringify(pairs) !== JSON.stringify(k.expect)) failures.push(`${c.name}: ${k.query} -> ${JSON.stringify(pairs)}`);
        else if (k.expectEnabled && JSON.stringify(got.map((r) => r.enabled)) !== JSON.stringify(k.expectEnabled)) failures.push(`${c.name}: ${k.query} enabled`);
    }
    for (const k of c.search.type || []) {
        types += 1;
        let state = { typed: "", pick: null }, text = "", chosen = null;
        const passed = [];
        for (const key of k.keys) {
            const r = typeQuery(ring, state, key);
            state = r.state; text = r.text; passed.push(r.passed); chosen = r.chosen || chosen;
        }
        const got = JSON.stringify([text, passed, chosen ? [chosen.id, chosen.address] : null]);
        if (got !== JSON.stringify([k.expectText, k.expectPassed, k.expectChosen ?? null])) failures.push(`${c.name}: ${JSON.stringify(k.keys)} -> ${got}`);
    }
}
console.log(JSON.stringify({ failures, finds, types }));
"""


@pytest.mark.skipif(not HAVE_NODE, reason="node is not installed")
def test_the_page_agrees_with_every_search_vector(tmp_path):
    """ring.js's search and typeQuery, imported as the page imports them, under node."""
    got = run_module(tmp_path, PAGE_REPLAY % {"vectors": VECTORS_BYTES.decode("utf-8")})
    assert got["failures"] == []
    finds = sum(len(c["search"].get("find", [])) for c in CASES)
    types = sum(len(c["search"].get("type", [])) for c in CASES)
    assert (got["finds"], got["types"]) == (finds, types)


@pytest.mark.skipif(not HAVE_NODE, reason="node is not installed")
def test_the_page_and_the_python_find_alike_on_the_garages_rings(tmp_path):
    """Beyond the vectors' one tree: the garage's own canvas ring, searched by both, for
    every two letters its labels begin with -- the same results in the same order."""
    from apothecary.example_hierarchy import create_example_site

    ring = resolve(Context(pointing=Pointing.CANVAS, targets=[]), create_example_site())
    labels = set()

    def gather(options):
        for option in options:
            labels.update(t[:2] for t in tokens(option.label) if t.isalpha())
            gather(option.children or [])

    gather(ring.options)
    queries = sorted(labels)
    assert len(queries) > 30
    python = {q: [[r.id, r.address] for r in search(ring, q)] for q in queries}
    body = (
        'import { search } from "/static/ring.js";\n'
        f"const ring = {ring.model_dump_json()};\n"
        f"const queries = {json.dumps(queries)};\n"
        "console.log(JSON.stringify(Object.fromEntries(queries.map((q) => [q, search(ring, q).map((r) => [r.id, r.address])]))));\n"
    )
    assert run_module(tmp_path, body) == python


def test_a_result_shows_the_keys_from_a_closed_ring_and_the_pages_own_keys_after():
    ring = rad_ring(VECTORS, "workshop")
    shortcuts = [Shortcut(key="Shift+f", does="Fit the level", label="Shift+F")]
    found = search_keys(ring, "fit", opener="Shift+M", shortcuts=shortcuts)
    assert [(r.path, r.keys) for r in found] == [
        (f"View{SEARCH_SEP}Fit", "Shift+M 4 8"),
        (f"View{SEARCH_SEP}Fit{SEARCH_SEP}All", "Shift+M 4 8 8"),
        (f"View{SEARCH_SEP}Fit{SEARCH_SEP}Selected", "Shift+M 4 8 6"),
        ("Fit the level", "Shift+F"),
    ]
    assert found[-1].shortcut == "Shift+f" and found[-1].address is None
    # Told no opening key, a result's keys are its address alone.
    assert search_keys(ring, "bed on")[0].keys == "8 2"


def test_the_route_searches_the_ring_resolve_answers():
    """POST /menu/search: the same body as /menu/resolve, a query, the opening key and the
    page's keys; the answer is resolve's ring searched."""
    from apothecary.api import app
    from apothecary.routes.menu import ResolveRequest, resolve_ring

    client = TestClient(app)
    body = {"context": {"pointing": "canvas", "targets": []}, "site": "garage"}
    ring = resolve_ring(ResolveRequest.model_validate(body))
    assert client.post("/menu/resolve", json=body).json() == ring.model_dump(mode="json")
    answer = client.post(
        "/menu/search",
        json={
            **body,
            "query": "fit",
            "opener": "Shift+M",
            "shortcuts": [{"key": "f", "does": "Fit the selection"}],
        },
    )
    assert answer.status_code == 200, answer.text
    got = answer.json()
    want = search_keys(ring, "fit", "Shift+M", [Shortcut(key="f", does="Fit the selection")])
    assert got == [r.model_dump(mode="json") for r in want]
    assert got[0]["keys"].startswith("Shift+M ") and got[-1]["keys"] == "f"


# --- beyond rad's vectors: what apothecary adds to the rule, held here --------------------


def _garage_rings() -> dict:
    """The garage's canvas ring, printer_1's ring with its board pinned, and that board's
    own device ring: the deepest trees the page searches."""
    from apothecary.example_hierarchy import create_example_site
    from apothecary.menu import Device

    site = create_example_site()
    printer = Device(port="/dev/ttyUSB0", printer=True, armed=False, bound=True)
    return {
        "canvas": resolve(Context(pointing=Pointing.CANVAS, targets=[]), site),
        "printer_1": resolve(
            Context(pointing=Pointing.NODE, targets=["printer_1"]), site, device=printer
        ),
        "device": resolve(
            Context(pointing=Pointing.DEVICE, targets=[printer.port]), site, device=printer
        ),
    }


@pytest.mark.skipif(not HAVE_NODE, reason="node is not installed")
def test_the_page_and_the_python_find_alike_on_every_ring_of_the_garages_printer(tmp_path):
    """The same results in the same order from menu.py and ring.js, on each of the
    garage's rings, for every two letters any of its labels begins with."""
    rings = _garage_rings()
    queries = set()

    def gather(options):
        for option in options:
            queries.update(t[:2] for t in tokens(option.label) if t.isalpha())
            gather(option.children or [])

    for ring in rings.values():
        gather(ring.options)
    queries = sorted(queries)
    assert len(queries) > 60
    python = {
        name: {q: [[r.id, r.address] for r in search(ring, q)] for q in queries}
        for name, ring in rings.items()
    }
    assert sum(len(v) for found in python.values() for v in found.values()) > 1000
    body = (
        'import { search } from "/static/ring.js";\n'
        f"const rings = {json.dumps({name: ring.model_dump(mode='json') for name, ring in rings.items()})};\n"
        f"const queries = {json.dumps(queries)};\n"
        "console.log(JSON.stringify(Object.fromEntries(Object.entries(rings).map(([name, ring]) =>"
        " [name, Object.fromEntries(queries.map((q) => [q, search(ring, q).map((r) => [r.id, r.address])]))]))));\n"
    )
    assert run_module(tmp_path, body) == python


PAGE_KEYS = """
import { found, keysOf, queryText, typeQuery } from "/static/ring.js";
const ring = %(ring)s;
const shortcuts = [
    { key: "f", does: "Fit the selection", label: "f" },
    { key: "Shift+f", does: "Fit the level", label: "Shift+F" },
    { key: "?", does: "Show or hide the hint bar", label: "?" },
];
const all = found(ring, "fit", shortcuts);
let state = { typed: "", pick: null };
const texts = [];
for (const key of ["f", "i", "t", "Tab", "Tab", "Tab", "Tab", "Tab"]) {
    const r = typeQuery(ring, state, key, shortcuts);
    state = r.state;
    texts.push(r.text);
}
const chosen = typeQuery(ring, state, "Enter", shortcuts).chosen;
console.log(JSON.stringify({
    found: all.map((r) => [r.path, keysOf(r, "m")]),
    bare: keysOf(all[0]),
    texts,
    chosen: [chosen.shortcut, chosen.path, keysOf(chosen, "m")],
    hint: found(ring, "hint", shortcuts).map((r) => r.shortcut),
    nothing: found(ring, "", shortcuts).length,
}));
"""


@pytest.mark.skipif(not HAVE_NODE, reason="node is not installed")
def test_the_pages_own_keys_come_after_the_rings_options_and_tab_and_enter_reach_them(tmp_path):
    """A page key is found by what it does, after every option of the ring, shows its own
    key and not the ring's opener, and is reached by Tab and chosen by Enter as an option
    is; an empty query finds nothing, page keys included."""
    ring = rad_ring(VECTORS, "workshop").model_dump(mode="json")
    got = run_module(tmp_path, PAGE_KEYS % {"ring": json.dumps(ring)})
    assert got["found"] == [
        ["View › Fit", "m 4 8"],
        ["View › Fit › All", "m 4 8 8"],
        ["View › Fit › Selected", "m 4 8 6"],
        ["Fit the selection", "f"],
        ["Fit the level", "Shift+F"],
    ]
    assert got["bare"] == "4 8"
    assert got["texts"] == [
        "f",
        "fi",
        "fit",
        "View › Fit",
        "View › Fit › All",
        "View › Fit › Selected",
        "Fit the selection",
        "Fit the level",
    ]
    assert got["chosen"] == ["Shift+f", "Fit the level", "Shift+F"]
    assert got["hint"] == ["?"]
    assert got["nothing"] == 0


SETTINGS_KEYS = """
import { FIXED, SETTINGS, makeSettings, pageShortcuts } from "/static/widgets/settings.js";
const store = makeSettings({ storageKey: "test.ring-search" });
const before = pageShortcuts(store);
store.set("ringKey", "k");
const after = pageShortcuts(store);
console.log(JSON.stringify({
    before, after,
    fixed: FIXED,
    keys: SETTINGS.filter((s) => s.kind === "key").map((s) => [s.id, s.label, s.def]),
    viaStore: store.shortcuts(),
    label: store.keyLabel("Shift+m"),
}));
"""


@pytest.mark.skipif(not HAVE_NODE, reason="node is not installed")
def test_every_key_the_viewer_holds_is_one_page_key_by_what_it_does(tmp_path):
    """settings.js's pageShortcuts: each thing a key does once, with every key that does
    it; every shortcut the Settings window sets and every key the page holds whatever the
    settings say, and the projector's, which act on its own page, not; a shortcut moved
    in Settings found at its new key."""
    got = run_module(tmp_path, SETTINGS_KEYS)
    before = got["before"]
    does = [s["does"] for s in before]
    assert len(does) == len(set(does)), does
    listed = {key for s in before for key in s["label"].split(" or ")}
    first = {s["key"] for s in before}
    every = set(got["fixed"]) | {d for i, _, d in got["keys"] if not i.startswith("projector")}
    assert first <= every
    # Every key is reached, as a person reads it: the first of its entry, or among its label.
    by_does = {s["does"]: s for s in before}
    for combo, what in got["fixed"].items():
        assert by_does[what]["key"] == combo or combo in [
            k for k in got["fixed"] if got["fixed"][k] == what
        ]
    for setting, label, default in got["keys"]:
        if setting.startswith("projector"):
            assert label not in does
        else:
            assert by_does[label]["key"] == default
    assert by_does["The world alone, or every window back"]["label"] == "~ or `"
    assert by_does["Open the canvas ring"]["label"] == "Shift+M"
    assert {s["does"]: s["key"] for s in got["after"]}["Open the ring"] == "k"
    assert got["viaStore"] == got["after"]
    assert got["label"] == "Shift+M"
    assert listed


PRESSED = """
import { comboOf, matches, pressCombo } from "/static/keys.js";
import { FIXED, SETTINGS } from "/static/widgets/settings.js";
// keys.js presses through the DOM's KeyboardEvent; node has Event and EventTarget only.
globalThis.KeyboardEvent = class extends Event {
    constructor(type, { bubbles, cancelable, composed, ...keys } = {}) {
        super(type, { bubbles, cancelable, composed });
        Object.assign(this, { isComposing: false, ...keys });
    }
};
const combos = [...Object.keys(FIXED), ...SETTINGS.filter((s) => s.kind === "key").map((s) => s.def)];
const heard = [];
const target = new EventTarget();
target.addEventListener("keydown", (e) => heard.push(["down", e.key, comboOf(e)]));
target.addEventListener("keyup", (e) => heard.push(["up", e.key, comboOf(e)]));
const wrong = [];
for (const combo of combos) {
    heard.length = 0;
    let event = null;
    const catcher = (e) => { event = e; };
    target.addEventListener("keydown", catcher, { once: true });
    pressCombo(combo, target);
    if (heard.length !== 2 || heard[0][0] !== "down" || heard[1][0] !== "up") wrong.push([combo, "not down then up"]);
    else if (!matches(event, combo)) wrong.push([combo, `heard as ${comboOf(event)}`]);
}
console.log(JSON.stringify({ count: combos.length, wrong, nothing: pressCombo("", target) }));
"""


@pytest.mark.skipif(not HAVE_NODE, reason="node is not installed")
def test_every_page_key_pressed_by_a_search_is_heard_as_that_key(tmp_path):
    """keys.js's pressCombo, for every key the page holds and every shortcut's default: a
    key down and up that keys.js's own `matches` reads as that key, as the page's handlers
    read it."""
    got = run_module(tmp_path, PRESSED)
    assert got["count"] > 30
    assert got["wrong"] == []
    assert got["nothing"] is False


DRAWN = """
import { ringMarkup, shownResults, RESULTS_SHOWN, withCells } from "/static/ring.js";
const ring = { title: "workshop", options: withCells(%(options)s) };
const results = Array.from({ length: 8 }, (_, i) => ({ id: "r" + i, path: "Path " + i, keys: "m " + i, enabled: i !== 3, why: i === 3 ? "not now" : null }));
const drawn = (pick) => ringMarkup({ ring, query: { text: "p", results, pick } });
const lines = (markup) => [...markup.matchAll(/<text class="found([^"]*)" data-found="([^"]+)"/g)].map((m) => [m[2], m[1].trim()]);
const bare = ringMarkup({ ring });
const typed = drawn(null);
console.log(JSON.stringify({
    shown: RESULTS_SHOWN,
    windows: [null, 0, 4, 5, 6, 7, 8].map((p) => shownResults(8, p)),
    few: shownResults(2, 1),
    none: shownResults(0, null),
    first: lines(typed),
    sixth: lines(drawn(5)),
    nothing: ringMarkup({ ring, query: { text: "zz", results: [], pick: null } }).includes("nothing found"),
    seatsNothing: typed.startsWith(bare) && typed.slice(bare.length).startsWith('<text class="query"'),
    noQuery: ringMarkup({ ring, query: { text: "", results, pick: null } }) === bare,
}));
"""


@pytest.mark.skipif(not HAVE_NODE, reason="node is not installed")
def test_the_results_written_under_the_ring_follow_tab_and_seat_nothing(tmp_path):
    """ringMarkup with a query: the first five results, the first lit until Tab moves on;
    once Tab is past the fifth, the five ending at the one it is on, that one lit; a greyed
    one drawn off; nothing found said; and the ring itself drawn exactly as without a query
    (a search seats nothing), the query and its results only after it."""
    ring = rad_ring(VECTORS, "workshop").model_dump(mode="json")
    got = run_module(tmp_path, DRAWN % {"options": json.dumps(ring["options"])})
    assert got["shown"] == 5
    assert got["windows"] == [[0, 5], [0, 5], [0, 5], [1, 6], [2, 7], [3, 8], [0, 5]]
    assert (got["few"], got["none"]) == ([0, 2], [0, 0])
    assert got["first"] == [["r0", "hot"], ["r1", ""], ["r2", ""], ["r3", "off"], ["r4", ""]]
    assert got["sixth"] == [["r1", ""], ["r2", ""], ["r3", "off"], ["r4", ""], ["r5", "hot"]]
    assert got["nothing"] and got["seatsNothing"] and got["noQuery"]
