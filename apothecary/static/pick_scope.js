/* Pick scope: how deep a click in the world reaches, and which layers are shown and
 * which of those a click can select (docs/viewer.md, "Layers").
 *
 * A layer is a set of things the world draws, named by an id:
 *   shell:N          the parts of shell N of the universe's sphere (0 innermost)
 *   system:NAME      a site's pieces in a System (apothecary/facets.py), the walls the
 *                    Building System's
 *   category:NAME    the pieces of a category: a part's, or a word no System holds
 *   grid             the alignment grid: the floor grid and the machines' build volumes
 *   machine-buttons  the badges standing on a machine in the world
 *   bed-mesh         a machine's bed reading laid over its bed: a printer's bed mesh, a
 *                    router's table map (machine_marks.js)
 *   measure          the measurement layer: dimension lines on the selection, and a click
 *                    in the world drops a point to measure between rather than selecting
 * A piece is on its shell's layer, where it has one, and on its System's or its
 * category's, as the server sends it (node.layer). A Kind (kind:NAME) is no layer: a
 * heading over its categories', each shown or made selectable at once (setShownEach).
 * The grid, the machine buttons, the bed mesh and the measurement are only ever shown or
 * not: a click never picks the first three, and the last is a mode, so none has a
 * selectable tick.
 * Measure is off at first, and, like walls selectable, the session's: never kept.
 *
 * Depth is a separate number: how many levels below the level in view a click reaches
 * and the world draws. 1 is a level's own pieces.
 *
 * What differs from the defaults -- everything shown, everything selectable but
 * walls, depth 1 -- is what is kept, so a layer that appears later (a shell a
 * loaded site has) is on. A click selects only within the shown layers, so
 * selectable is always within shown: a layer hidden is not selectable, and ticking
 * selectable shows it. Walls selectable is the page's session's, never
 * kept, as the View menu's Select walls always was.
 *
 * A layer's ring (View › Layers) also shows one layer alone of its set, or every one of
 * its set (showOnly, showAll, setOf): the shells, the pieces' layers (Systems and
 * categories), or the world's own: the grid, the machine buttons and the bed mesh.
 *
 * Plain ES module, no dependencies and no listeners of its own: the page asks it
 * (pickable, drawn) and is told (onChange).
 */

export const PICK_SCOPE_KEY = "apothecary.pickScope";
export const DEPTH_MAX = 8;
export const WALL = "system:building";
export const GRID = "grid";
export const MACHINE_BUTTONS = "machine-buttons";
export const BED_MESH = "bed-mesh";
// Layers a click never picks: only their being shown is the person's to say.
export const MEASURE = "measure";
export const SHOWN_ONLY = new Set([GRID, MACHINE_BUTTONS, BED_MESH, MEASURE]);
// The world's own layers, one set: what Only this and All act among (setOf).
const WORLD_SET = [GRID, MACHINE_BUTTONS, BED_MESH];

export const shellLayer = (n) => `shell:${n}`;
export const categoryLayer = (name) => `category:${name}`;
const isPieceLayer = (id) => id.startsWith("system:") || id.startsWith("category:");

/* The layers a node is on: its shell's, when it is in one, and its System's or its
 * category's (node.layer). */
export function layersOf(node) {
    const out = [];
    if (!node) return out;
    if (Number.isInteger(node.shell)) out.push(shellLayer(node.shell));
    if (node.layer) out.push(node.layer);
    return out;
}

/* The one layer a row in a list names a node by: its shell's, else its own. */
export function layerOf(node) {
    return layersOf(node)[0] ?? null;
}

/* The layers of `id`'s set, `id` among them, which Only this and All act among: the
 * shells the site has, its pieces' layers (`layers`: its Systems and categories), or the
 * world's own -- the grid, the machines' buttons and their bed readings. The measurement
 * is a mode, a set of its own. */
export function setOf(id, { shells = [], layers = [] } = {}) {
    if (id.startsWith("shell:")) return [...new Set([...shells.map(shellLayer), id])];
    if (isPieceLayer(id)) return [...new Set([...layers.filter(isPieceLayer), id])];
    if (WORLD_SET.includes(id)) return [...WORLD_SET];
    return [id];
}

const clampDepth = (n) => {
    const v = Math.floor(Number(n));
    return Number.isFinite(v) ? Math.min(DEPTH_MAX, Math.max(1, v)) : 1;
};

export function makePickScope({ storage = null, storageKey = PICK_SCOPE_KEY } = {}) {
    const store = () => {
        if (storage) return storage;
        try { return globalThis.localStorage || null; } catch (e) { return null; }
    };
    let depth = 1;
    const hidden = new Set([MEASURE]);     // layers not shown
    const unselectable = new Set([WALL]);  // layers the person made a click pass through
    const listeners = new Set();

    function keep() {
        const kept = {};
        if (depth !== 1) kept.depth = depth;
        const away = [...hidden].filter((id) => id !== MEASURE).sort();
        if (away.length) kept.hidden = away;
        const passed = [...unselectable].filter((id) => id !== WALL).sort();
        if (passed.length) kept.unselectable = passed;
        try {
            const s = store();
            if (!s) return;
            if (Object.keys(kept).length) s.setItem(storageKey, JSON.stringify(kept));
            else s.removeItem(storageKey);
        } catch (e) { /* kept nowhere: the scope holds for this page's life */ }
    }
    function told(what) {
        keep();
        for (const fn of listeners) {
            try { fn(what, api); } catch (e) { console.error(e); }
        }
    }
    function fromJSON(value) {
        depth = 1;
        hidden.clear();
        hidden.add(MEASURE);
        unselectable.clear();
        unselectable.add(WALL);
        if (!value || typeof value !== "object") return;
        if (value.depth !== undefined) depth = clampDepth(value.depth);
        const ids = (list) => (Array.isArray(list) ? list.filter((x) => typeof x === "string" && x.length <= 80) : []);
        for (const id of ids(value.hidden)) hidden.add(id);  // measure is off whatever was kept
        for (const id of ids(value.unselectable)) if (!SHOWN_ONLY.has(id)) unselectable.add(id);
    }

    try {
        const s = store();
        const text = s && s.getItem(storageKey);
        if (text) fromJSON(JSON.parse(text));
    } catch (e) { fromJSON(null); }

    const api = {
        depth: () => depth,
        isShown: (id) => !hidden.has(id),
        isSelectable: (id) => !SHOWN_ONLY.has(id) && !hidden.has(id) && !unselectable.has(id),
        layerOf,
        layersOf,
        /* Whether a click may pick the node: every layer it is on is selectable. */
        pickable: (node) => layersOf(node).every((id) => api.isSelectable(id)),
        /* Whether the world draws the node: every layer it is on is shown. */
        drawn: (node) => layersOf(node).every((id) => !hidden.has(id)),
        /* Levels below the level in view, a whole number from 1 to DEPTH_MAX. */
        setDepth(n) {
            if (!Number.isFinite(Number(n))) return false;
            const v = clampDepth(n);
            if (v === depth) return false;
            depth = v;
            told({ depth: v });
            return true;
        },
        setShown(id, on) {
            if (!!on === !hidden.has(id)) return false;
            if (on) hidden.delete(id);
            else hidden.add(id);
            told({ layer: id, shown: !!on });
            return true;
        },
        /* Selectable implies shown: ticking it shows the layer, too. A layer only ever
         * shown or not has no such tick: refused. */
        setSelectable(id, on) {
            if (SHOWN_ONLY.has(id)) return false;
            if (!!on === api.isSelectable(id)) return false;
            if (on) { unselectable.delete(id); hidden.delete(id); } else unselectable.add(id);
            told({ layer: id, selectable: !!on });
            return true;
        },
        /* Every layer of `ids` shown, or every one hidden, at once, told once and said
         * as `as` (a Kind's heading over its categories). False when all were so. */
        setShownEach(ids, on, as = null) {
            const changing = ids.filter((id) => !!on === hidden.has(id));
            if (!changing.length) return false;
            for (const id of changing) { if (on) hidden.delete(id); else hidden.add(id); }
            told({ layer: as, layers: [...ids], shown: !!on });
            return true;
        },
        /* Every layer of `ids` selectable, or none, as setSelectable does each: told once. */
        setSelectableEach(ids, on, as = null) {
            const changing = ids.filter((id) => !SHOWN_ONLY.has(id) && !!on !== api.isSelectable(id));
            if (!changing.length) return false;
            for (const id of changing) { if (on) { unselectable.delete(id); hidden.delete(id); } else unselectable.add(id); }
            told({ layer: as, layers: [...ids], selectable: !!on });
            return true;
        },
        /* `id` shown and every other layer of `set` (setOf) hidden, at once: told once.
         * What was chosen selectable stays chosen. False when it was so already. */
        showOnly(id, set) {
            const others = set.filter((k) => k !== id);
            if (!hidden.has(id) && others.every((k) => hidden.has(k))) return false;
            hidden.delete(id);
            for (const k of others) hidden.add(k);
            told({ layer: id, only: true });
            return true;
        },
        /* Every layer of `set` shown, at once: told once. False when all were. */
        showAll(set) {
            if (set.every((k) => !hidden.has(k))) return false;
            for (const k of set) hidden.delete(k);
            told({ layers: [...set], all: true });
            return true;
        },
        /* Everything back to the defaults. */
        reset() {
            fromJSON(null);
            told({ reset: true });
        },
        onChange(fn) { listeners.add(fn); return () => listeners.delete(fn); },
        toJSON() {
            return {
                depth,
                hidden: [...hidden].filter((id) => id !== MEASURE).sort(),
                unselectable: [...unselectable].filter((id) => id !== WALL).sort(),
            };
        },
        fromJSON(value) { fromJSON(value); told({ loaded: true }); },
    };
    return api;
}
