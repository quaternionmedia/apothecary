/* A loop's plots as SVG, from what the server answers: scales, ticks, paths and marks.
 *
 * Nothing here computes what the server computes (apothecary/loop_document.py's
 * `curves`): no transfer function, no margin, no fit. It maps numbers the answer gives
 * onto a plot -- a linear or a log axis, its ticks, a path through the points, a line
 * where the answer names a crossover or a peak, a measured point drawn as its trust
 * says -- and rounds a figure for showing as the document's Markdown view does
 * (`shown`, loop_document.format_value). The module is pure, so node runs it in
 * tests/test_loop_plots.py.
 *
 * plotSvg(spec) is one plot, an SVG with its legend under it: { name, title, width, height,
 *   x: { log, domain: [lo, hi], label, unit, ticks? }, y: { ... },
 *   series: [{ name, cls, xs, ys, label, dashed? }], rules: [{ y, label }],
 *   marks: [{ name, x, label, cls }], points: [{ x, y, trust, why }] }
 * Every drawn thing says what it was drawn from in data attributes, in the answer's own
 * numbers (`String(v)`, every digit): a series its name, how many points and the first
 * and last x; a mark its name and where; a point its trust. A test reads those, not
 * pixels.
 */

export const finite = (v) => typeof v === "number" && Number.isFinite(v);

const esc = (v) => String(v ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

// Pixels to a tenth: a path is as long as it needs to be and no longer.
const px = (v) => String(Math.round(v * 10) / 10);

/* The least and the most of the finite numbers in any of `arrays` (positive ones only
 * for a log axis), or null when there are none. */
export function extent(arrays, { positive = false } = {}) {
    let lo = Infinity, hi = -Infinity;
    for (const values of arrays) {
        for (const v of values || []) {
            if (!finite(v) || (positive && v <= 0)) continue;
            if (v < lo) lo = v;
            if (v > hi) hi = v;
        }
    }
    return lo <= hi ? [lo, hi] : null;
}

export function linearScale([d0, d1], [r0, r1]) {
    const span = d1 - d0 || 1;
    return (v) => r0 + ((v - d0) / span) * (r1 - r0);
}

export function logScale([d0, d1], [r0, r1]) {
    const a = Math.log10(d0), span = Math.log10(d1) - a || 1;
    return (v) => (v > 0 ? r0 + ((Math.log10(v) - a) / span) * (r1 - r0) : NaN);
}

/* A step of 1, 2 or 5 times a power of ten that cuts `span` into about `count`. */
export function niceStep(span, count = 5) {
    const raw = Math.abs(span) / Math.max(1, count);
    if (!(raw > 0)) return 1;
    const power = 10 ** Math.floor(Math.log10(raw));
    const f = raw / power;
    return (f <= 1 ? 1 : f <= 2 ? 2 : f <= 5 ? 5 : 10) * power;
}

/* Every multiple of `step` from `lo` to `hi`, written without a float's tail. */
export function stepTicks(lo, hi, step) {
    const out = [];
    const decimals = Math.max(0, -Math.floor(Math.log10(step)));
    for (let k = Math.ceil(lo / step - 1e-9); k * step <= hi + step * 1e-9; k++) {
        out.push(Number((k * step).toFixed(decimals)));
    }
    return out;
}

export function linearTicks(lo, hi, count = 5) {
    return stepTicks(lo, hi, niceStep(hi - lo, count));
}

/* A domain that holds [lo, hi], widened to the nice steps either side. */
export function linearDomain(lo, hi, count = 5) {
    if (lo === hi) { lo -= 1; hi += 1; }
    const step = niceStep(hi - lo, count);
    return [Math.floor(lo / step + 1e-9) * step, Math.ceil(hi / step - 1e-9) * step];
}

/* A log axis's domain: whole decades holding [lo, hi], at most `decades` of them down
 * from the top, so a curve that falls away to nothing does not squash the rest. */
export function logDomain(lo, hi, decades = 8) {
    let top = Math.ceil(Math.log10(hi) - 1e-9), bottom = Math.floor(Math.log10(lo) + 1e-9);
    if (top === bottom) top += 1;
    bottom = Math.max(bottom, top - decades);
    return [10 ** bottom, 10 ** top];
}

/* A log axis's ticks: each power of ten in [lo, hi], every other one or fewer when there
 * are more than `most`; over less than two decades, the 2s and 5s between as well. */
export function logTicks(lo, hi, most = 7) {
    const first = Math.ceil(Math.log10(lo) - 1e-9), last = Math.floor(Math.log10(hi) + 1e-9);
    const decades = [];
    for (let k = first; k <= last; k++) decades.push(k);
    if (decades.length >= 3) {
        const every = Math.ceil(decades.length / most);
        return decades.filter((k) => (k - first) % every === 0).map((k) => 10 ** k);
    }
    const out = [];
    for (let k = first - 1; k <= last; k++) {
        for (const m of [1, 2, 5]) {
            const v = m * 10 ** k;
            if (v >= lo * (1 - 1e-9) && v <= hi * (1 + 1e-9)) out.push(Number(v.toPrecision(12)));
        }
    }
    return out;
}

const SUPER = { "-": "⁻", 0: "⁰", 1: "¹", 2: "²", 3: "³", 4: "⁴", 5: "⁵", 6: "⁶", 7: "⁷", 8: "⁸", 9: "⁹" };

/* A tick's words: a power of ten as 10 with its exponent raised, from 0.01 to 1000 as
 * the number; otherwise the number as it is. */
export function tickLabel(v, log = false) {
    if (log) {
        const k = Math.log10(v);
        if (Math.abs(k - Math.round(k)) < 1e-9 && (k < -2 || k > 3)) {
            return "10" + String(Math.round(k)).split("").map((c) => SUPER[c]).join("");
        }
        return String(Number(v.toPrecision(6)));
    }
    return String(v);
}

/* `v` to `d` places as Python's format writes it: a value exactly half way between two
 * of the places shown goes to the even one, where JavaScript's toFixed goes up. */
export function fixed(v, d) {
    const a = Math.abs(v);
    let s = a.toFixed(d);
    const twice = a * 2 ** (d + 1); // an odd whole number exactly when `a` is a tie
    if (Number.isInteger(twice) && twice % 2 === 1 && Number(s.at(-1)) % 2 === 1) {
        const digits = String(BigInt(s.replace(".", "")) - 1n).padStart(d + 1, "0");
        s = d ? `${digits.slice(0, -d)}.${digits.slice(-d)}` : digits;
    }
    return (v < 0 || Object.is(v, -0) ? "-" : "") + s;
}

/* A figure rounded for showing, as the document's Markdown view rounds a float
 * (loop_document.format_value): a dash for none, yes or no, three places at most below
 * ten, one below a hundred, none above, and a power of ten for the very small and the
 * very large. A number is taken for a float: JSON says 5.0 as 5. */
export function shown(v) {
    if (v === null || v === undefined) return "—";
    if (typeof v === "boolean") return v ? "yes" : "no";
    if (typeof v === "string") return v;
    const a = Math.abs(v);
    if (a !== 0 && (a < 1e-3 || a >= 1e6)) {
        const [m, e] = v.toExponential(3).split("e");
        const exp = Number(e);
        return `${m}e${exp < 0 ? "-" : "+"}${String(Math.abs(exp)).padStart(2, "0")}`;
    }
    if (a >= 100) return fixed(v, 0);
    if (a >= 10) return fixed(v, 1);
    return fixed(v, 3).replace(/0+$/, "").replace(/\.$/, "");
}

/* A path through the points, in pixels; a point that is not a number, or outside the
 * plot (`inside`), breaks it, and the next one begins it again. */
export function pathOf(xs, ys, sx, sy, inside = () => true) {
    let d = "", pen = false;
    const n = Math.min(xs.length, ys.length);
    for (let i = 0; i < n; i++) {
        const x = xs[i], y = ys[i];
        const ok = finite(x) && finite(y) && inside(x, y);
        const X = ok ? sx(x) : NaN, Y = ok ? sy(y) : NaN;
        if (!ok || !Number.isFinite(X) || !Number.isFinite(Y)) { pen = false; continue; }
        d += `${pen ? "L" : "M"}${px(X)} ${px(Y)}`;
        pen = true;
    }
    return d;
}

// How a measured point looks by its trust: a good one filled, a fair one filled faintly,
// a poor one hollow and broken, an unknown one a hollow square -- never alike.
export const TRUST_SHAPES = {
    good: (x, y) => `<circle cx="${px(x)}" cy="${px(y)}" r="3.5" fill="currentColor" stroke="currentColor"/>`,
    fair: (x, y) => `<circle cx="${px(x)}" cy="${px(y)}" r="3.5" fill="currentColor" fill-opacity="0.45" stroke="currentColor"/>`,
    poor: (x, y) => `<circle cx="${px(x)}" cy="${px(y)}" r="3.5" fill="none" stroke="currentColor" stroke-dasharray="2 1.5"/>`,
    unknown: (x, y) => `<rect x="${px(x - 3)}" y="${px(y - 3)}" width="6" height="6" fill="none" stroke="currentColor"/>`,
};

const PAD = { left: 46, right: 10, top: 10, bottom: 30 };

export function plotSvg({ name, title = "", width = 360, height = 200, x, y, series = [], rules = [], marks = [], points = [] }) {
    const left = PAD.left, right = width - PAD.right, top = PAD.top, bottom = height - PAD.bottom;
    const sx = (x.log ? logScale : linearScale)(x.domain, [left, right]);
    const sy = (y.log ? logScale : linearScale)(y.domain, [bottom, top]);
    const within = (v, [lo, hi]) => v >= lo * (1 - 1e-9) - (lo === 0 ? 1e-12 : 0) && v <= hi * (1 + 1e-9) + (hi === 0 ? 1e-12 : 0);
    const inside = (vx, vy) => within(vx, x.domain) && within(vy, y.domain);
    const xticks = x.ticks || (x.log ? logTicks(...x.domain) : linearTicks(...x.domain));
    const yticks = y.ticks || (y.log ? logTicks(...y.domain, 6) : linearTicks(...y.domain));
    const parts = [];
    parts.push(`<rect class="frame" x="${left}" y="${top}" width="${px(right - left)}" height="${px(bottom - top)}"/>`);
    parts.push(`<g class="axis x" data-ticks="${esc(xticks.join(" "))}">` + xticks.map((t) => {
        const X = px(sx(t));
        return `<line class="grid" x1="${X}" y1="${top}" x2="${X}" y2="${bottom}"/><text x="${X}" y="${bottom + 13}" text-anchor="middle">${esc(tickLabel(t, x.log))}</text>`;
    }).join("") + `<text class="axis-label" x="${px((left + right) / 2)}" y="${height - 3}" text-anchor="middle">${esc(x.label)}${x.unit ? ` (${esc(x.unit)})` : ""}</text></g>`);
    parts.push(`<g class="axis y" data-ticks="${esc(yticks.join(" "))}">` + yticks.map((t) => {
        const Y = px(sy(t));
        return `<line class="grid" x1="${left}" y1="${Y}" x2="${px(right)}" y2="${Y}"/><text x="${left - 4}" y="${Y}" dy="0.32em" text-anchor="end">${esc(tickLabel(t, y.log))}</text>`;
    }).join("") + `<text class="axis-label" transform="translate(11 ${px((top + bottom) / 2)}) rotate(-90)" text-anchor="middle">${esc(y.label)}${y.unit ? ` (${esc(y.unit)})` : ""}</text></g>`);
    for (const r of rules) {
        if (!within(r.y, y.domain)) continue;
        const Y = px(sy(r.y));
        parts.push(`<g class="rule" data-rule="${esc(r.y)}"><line x1="${left}" y1="${Y}" x2="${px(right)}" y2="${Y}"/><text x="${px(right - 2)}" y="${Y}" dy="-0.3em" text-anchor="end">${esc(r.label || "")}</text></g>`);
    }
    for (const s of series) {
        const n = Math.min(s.xs.length, s.ys.length);
        parts.push(`<path class="series s-${esc(s.cls || s.name)}${s.dashed ? " dashed" : ""}" data-series="${esc(s.name)}" data-n="${n}" data-from="${esc(String(s.xs[0]))}" data-to="${esc(String(s.xs[n - 1]))}" d="${pathOf(s.xs, s.ys, sx, sy, inside)}"/>`);
    }
    // Each mark's words on a row of their own from the top, on the side of its line with
    // the more room.
    marks.filter((m) => finite(m.x) && within(m.x, x.domain)).forEach((m, i) => {
        const at = sx(m.x), X = px(at), toLeft = at > (left + right) / 2;
        parts.push(`<g class="mark s-${esc(m.cls || "")}" data-mark="${esc(m.name)}" data-at="${esc(String(m.x))}"><line x1="${X}" y1="${top}" x2="${X}" y2="${bottom}"/><text x="${X}" y="${top + 10 + 11 * i}" dx="${toLeft ? -3 : 3}" text-anchor="${toLeft ? "end" : "start"}">${esc(m.label || "")}</text></g>`);
    });
    for (const p of points) {
        if (!finite(p.x) || !finite(p.y) || !inside(p.x, p.y)) continue;
        const shape = TRUST_SHAPES[p.trust] || TRUST_SHAPES.unknown;
        parts.push(`<g class="point trust-${esc(p.trust)}" data-trust="${esc(p.trust)}" data-at="${esc(String(p.x))}"><title>${esc(`${p.trust}: ${p.why || ""}`)}</title>${shape(sx(p.x), sy(p.y))}</g>`);
    }
    const legend = series.filter((s) => s.label).map((s) =>
        `<span class="key s-${esc(s.cls || s.name)}${s.dashed ? " dashed" : ""}">${esc(s.label)}</span>`).join("");
    return `<figure class="loops-figure"><svg class="loops-plot" data-plot="${esc(name)}" viewBox="0 0 ${width} ${height}" width="100%" role="img" aria-label="${esc(title)}" xmlns="http://www.w3.org/2000/svg">${parts.join("")}</svg><figcaption class="loops-legend">${legend}</figcaption></figure>`;
}
