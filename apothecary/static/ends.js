// The ends a person joins, and the adapter between them, as the page sends and shows them
// (docs/connections.md, The adapter between two ends). An end is a part at its numbers:
// a preset chosen, and what a person typed over it. The server reads each end's interface,
// derives the adapter, checks each fit and refuses with its reason (POST
// /parts/{adapter}/between): nothing here computes a fit, a diameter or an adapter's
// numbers. Pure, so node runs it (tests/test_ends_js.py), held against the server's own
// words for the same end (apothecary.adapters.End.label).

const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);

// The one adapter part the server generates between two ends (apothecary.adapters.ADAPTER).
export const ADAPTER = 'hose_adapter';

// A set of numbers as one string, whatever order its names came in: whether what is drawn
// is still what was last checked.
export function paramsKey(params) {
    return JSON.stringify(Object.entries(params ?? {}).sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0)));
}

// What choosing a preset stages: the part's defaults with the preset's numbers over them.
export function presetStaged(defaults, preset) {
    return { ...(defaults ?? {}), ...(preset?.params ?? {}) };
}

// An end as the server takes it: the part, the preset it started from, and each number
// staged that is not that preset's (or, with none, the part's default) -- what a person
// set, which the server's words name.
export function endOf(part, staged, defaults, presetName = null, presets = {}) {
    const preset = presetName && presets?.[presetName] ? presetName : null;
    const base = preset ? presetStaged(defaults, presets[preset]) : (defaults ?? {});
    const params = {};
    for (const [name, value] of Object.entries(staged ?? {})) {
        if (!same(value, base[name])) params[name] = value;
    }
    return preset ? { part, preset, params } : { part, params };
}

// The body of POST /parts/{adapter}/between: the two ends, and the adapter's own numbers
// where they are to be checked against them rather than derived.
export function betweenBody(a, b, params = null) {
    return params ? { a, b, params } : { a, b };
}

// An end in the server's words: part@preset, its interface where it is known, then each
// number a person set over the preset.
export function label(end, interfaceName = null) {
    const named = end.part + (end.preset ? `@${end.preset}` : '') + (interfaceName ? `.${interfaceName}` : '');
    const given = Object.entries(end.params ?? {}).map(([k, v]) => `${k}=${String(v)}`).join(', ');
    return given ? `${named} (${given})` : named;
}
