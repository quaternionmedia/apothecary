/* The first layer: how a slice levels the bed at its start and how its first layer holds,
 * in one set of words. The Print window's levelling and adhesion rows (widgets/machine.js),
 * and Part › Feedback's tries on a print that stopped and its drawer's made row
 * (widgets/feedback.js), all say them from here (docs/slicer.md, docs/cabinet.md).
 *
 * Pure, no DOM, so node holds it (tests/test_first_layer_js.py), which checks the choices
 * against the server's: slicer/compose.py LEVELLINGS and slicer/profiles.py ADHESIONS.
 *
 *   LEVELLING, ADHESION   each row's choices in its order, { value, name, detail }; "" is
 *                         the part's own: what it declares, else the printer's profile's
 *   TRIES                 a try on a print that stopped ("probe", "brim", "raft"): the row
 *                         it chooses in and its choice there
 *   words(choice)         a choice in words, "probe first: G29 once the bed is hot"
 *   options(choices)      a row's <option>s
 *   offsetWords(mm)       a first-layer offset as the nozzle's move: "0.05 mm lower", "as
 *                         the probe puts it" (slicer/first_layer_offset.py words)
 *   offsetOptions(choices, kept)
 *                         the first layer row's <option>s: each choice, and the one kept
 *                         where it is none of them
 *   made(settings)        how a kept slice was made, from its settings: { levelling,
 *                         skirt, adhesion }, each in words, null where it recorded none;
 *                         a first-layer offset other than 0 is said after its levelling
 *   tryRefused(how, settings, declared, part)
 *                         why a try is not offered on a piece sliced with `settings` of
 *                         `part`, which declares `declared`; null where it is
 *   own(row, resolved)    a row's first choice said as what it comes to, from
 *                         GET /slicer/first-layer: "the part's own: probe first", "the
 *                         printer's: home only"; null where that is not known
 */

export const LEVELLING = [
    { value: "", name: "the part's own", detail: null },
    { value: "probe-each-print", name: "probe first", detail: "G29 once the bed is hot" },
    { value: "home", name: "home only", detail: "no levelling" },
];
// A start a slice may be made with that the row does not offer: a profile's or a part's.
const STORED_MESH = { value: "stored-mesh", name: "the stored mesh", detail: "M420 S1 after G28" };

const brim = (mm) => ({ name: "brim", detail: `${mm} mm round each piece` });
const raft = (layers) => ({ name: "raft", detail: `${layers} layers under each piece` });

// What each choice sets over what the part declares: the server's ADHESIONS.
const SETS = {
    brim: { brim_width: 5, raft_layers: 0 },
    raft: { raft_layers: 3, brim_width: 0 },
    none: { brim_width: 0, raft_layers: 0 },
};
export const ADHESION = [
    { value: "", name: "the part's own", detail: null },
    { value: "brim", ...brim(SETS.brim.brim_width), sets: SETS.brim },
    { value: "raft", ...raft(SETS.raft.raft_layers), sets: SETS.raft },
    { value: "none", name: "neither brim nor raft", detail: null, sets: SETS.none },
];

const choice = (choices, value) => choices.find((c) => c.value === value);
export const TRIES = {
    probe: { row: "levelling", choice: choice(LEVELLING, "probe-each-print") },
    brim: { row: "adhesion", choice: choice(ADHESION, "brim") },
    raft: { row: "adhesion", choice: choice(ADHESION, "raft") },
};

export function words(c) {
    return c.detail ? `${c.name}: ${c.detail}` : c.name;
}

export function options(choices) {
    return choices.map((c) => `<option value="${c.value}">${words(c)}</option>`).join("");
}

export function offsetWords(mm) {
    const v = Number(mm);
    if (!Number.isFinite(v) || Math.abs(v) < 1e-9) return "as the probe puts it";
    return `${Math.abs(v).toFixed(2)} mm ${v < 0 ? "lower" : "higher"}`;
}

export function offsetOptions(choices, kept) {
    const all = [...(choices || [])];
    if (kept != null && !all.some((c) => Math.abs(c - kept) < 1e-9)) all.push(Number(kept));
    all.sort((a, b) => a - b);
    return all.map((v) => `<option value="${String(v)}">${offsetWords(v)}</option>`).join("");
}

// A slice record's settings by name, each its value.
function named(settings) {
    return Object.fromEntries((settings || []).map((s) => [s.name, s.value]));
}

// The levelling a slice's start was composed with, a choice, or null where it says none.
function levelledBy(values) {
    if (!("start" in values)) return null;
    const pieces = [].concat(values.start || []);
    if (pieces.includes("probe-each-print")) return choice(LEVELLING, "probe-each-print");
    if (pieces.includes("stored-mesh")) return STORED_MESH;
    return choice(LEVELLING, "home");
}

// The brim a slice set, in mm, 0 for none; null where it set none (the printer's own).
function brimOf(values) {
    if (!("brim_type" in values)) return null;
    return values.brim_type === "no_brim" ? 0 : Number(values.brim_width);
}

export function made(settings) {
    const values = named(settings);
    const levelled = levelledBy(values);
    const offset = Number(values.z_offset);
    const lifted = Number.isFinite(offset) && offset !== 0 ? `, the nozzle ${offsetWords(offset)}` : "";
    const skirt = "skirt_loops" in values
        ? (Number(values.skirt_loops) ? `${values.skirt_loops} loops of skirt` : "no skirt")
        : "the printer's own skirt";
    // The brim's type and the raft are recorded only where the part declares them or the
    // slice asks; the brim's width is the printer's profile's otherwise.
    const width = brimOf(values);
    const layers = "raft_layers" in values ? Number(values.raft_layers) : null;
    let adhesion = null;
    if (width === 0 && layers === 0) adhesion = words(choice(ADHESION, "none"));
    else {
        const said = [];
        if (width !== null) said.push(width ? words(brim(width)) : "no brim");
        if (layers) said.push(words(raft(layers)));
        if (said.length) adhesion = said.join(", ");
    }
    return { levelling: levelled ? words(levelled) + lifted : null, skirt, adhesion };
}

// What a part declares of how its first layer holds, in a few words: the raft before the
// brim, as the slicer lays them.
function held(r) {
    const layers = Number(r.raft_layers || 0), width = r.brim_width;
    if (layers > 0) return `raft of ${layers} layers`;
    if (width != null && Number(width) > 0) return `brim ${Number(width)} mm`;
    if (width != null && r.raft_layers != null) return words(choice(ADHESION, "none"));
    return width != null ? "no brim" : "no raft";
}

export function own(row, resolved) {
    const r = resolved && resolved[row];
    if (!r) return null;
    const whose = r.by === "part" ? "the part's own" : "the printer's";
    if (row === "adhesion") return r.by === "part" ? `${whose}: ${held(r)}` : "the printer's own";
    const c = choice(LEVELLING, r.value) || (r.value === STORED_MESH.value ? STORED_MESH : null);
    return c ? `${whose}: ${c.name}` : whose;
}

// A try is not offered where the part declares against it -- a brim on a part that declares
// none -- or where the piece was sliced with what the try chooses already: it would slice
// the piece again as it was made.
export function tryRefused(how, settings, declared = {}, part = "the part") {
    const tried = TRIES[how];
    if (!tried) return null;
    if (how === "brim" && declared && declared.brim_width === 0) return `${part} declares no brim`;
    const values = named(settings), c = tried.choice;
    const already = how === "probe" ? levelledBy(values) === c
        : how === "brim" ? brimOf(values) === c.sets.brim_width
        : "raft_layers" in values && Number(values.raft_layers) === c.sets.raft_layers;
    if (!already) return null;
    const declares = how === "probe" && declared && declared.levelling === c.value;
    return `this piece was made with ${words(c)}${declares ? `, as ${part} declares` : ""}`;
}
