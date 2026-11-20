/* How a number is written on the page: one form each, for every drawer.
 *
 * A temperature, a time of day, a stretch of time, a position and a size are each
 * written here once, so the Machine's cards, the Print window, the Loops window and the
 * Deck read alike (tests/test_format_js.py holds each form). Pure functions; nothing
 * here fetches, listens or keeps state.
 *
 *   degrees(v)           "23.1°"        one reading, one decimal
 *   heater(actual, set)  "23.1/200°"    a heater: what it reads over what it is set to
 *   clock(when)          "11:53:53"     a time of day, 24 hours, in the person's zone
 *   stamp(when)          "2026-11-18 12:06:32"   a day and its time
 *   span(seconds)        "0:46", "4:52", "1:02:09"   how long, as a clock counts it
 *   mm(v)                "101.5 mm"     millimetres, at most three decimals, none trailing
 *   dims(a, b, c)        "46 × 46 × 101.5 mm"
 *   xyz(p)               "X0.0 Y0.0 Z0.00"   a position
 *   sentence(text)       "Poll: refused"  a status line starts a sentence
 *   viaRing(label, at)   "Home all (⌗494)"   how a status line names a ring cell it was asked by
 */

const two = (n) => String(n).padStart(2, "0");
const date = (when) => (when instanceof Date ? when : new Date(when));

export const degrees = (v) => (v == null || !Number.isFinite(v) ? "—" : `${v.toFixed(1)}°`);

export const heater = (actual, target) => {
    if (actual == null || !Number.isFinite(actual)) return "—";
    return `${actual.toFixed(1)}/${target == null ? "—" : Math.round(target)}°`;
};

export function clock(when) {
    const d = date(when);
    return Number.isNaN(d.getTime()) ? "—" : `${two(d.getHours())}:${two(d.getMinutes())}:${two(d.getSeconds())}`;
}

export function stamp(when) {
    const d = date(when);
    return Number.isNaN(d.getTime()) ? "—" : `${d.getFullYear()}-${two(d.getMonth() + 1)}-${two(d.getDate())} ${clock(d)}`;
}

export function span(seconds) {
    if (seconds == null || !Number.isFinite(seconds)) return "—";
    const s = Math.max(0, Math.round(seconds)), h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60);
    return h ? `${h}:${two(m)}:${two(s % 60)}` : `${m}:${two(s % 60)}`;
}

const trimmed = (v) => String(Number(v.toFixed(3)));
export const mm = (v) => (v == null || !Number.isFinite(v) ? "—" : `${trimmed(v)} mm`);
export const dims = (...sides) => `${sides.map((v) => (v == null || !Number.isFinite(v) ? "—" : trimmed(v))).join(" × ")} mm`;

export const xyz = (p) => `X${p.x.toFixed(1)} Y${p.y.toFixed(1)} Z${p.z.toFixed(2)}`;

// A status line says which cell of the ring it was asked by, in one form: the label, the address.
export const viaRing = (label, address) => `${label} (⌗${address})`;

// A line of the status bar starts a sentence: a lower-case word of its own ("poll:", "jog X1:")
// is capitalised; a name carrying a digit, an underscore or a capital (printer_1, ttyUSB0) is left as it is.
export const sentence = (text) => {
    const t = String(text ?? "");
    return /^[a-z]/.test(t) && !/^[^\s:]*[_\dA-Z]/.test(t) ? t[0].toUpperCase() + t.slice(1) : t;
};
