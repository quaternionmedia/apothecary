/* A SCAD text's top-level assignments, read as the server reads them, and a value
 * written back into one (the part-iteration plan's "parameters and text, tied
 * together", docs/plans/part-iteration-2026-10-12.md).
 *
 * The text is the truth: a control moves its parameter by rewriting the value in
 * the text, and a value typed in the text moves its control. The page rewrites
 * lines itself, at once, so this module and the server's
 * (apothecary/projects/parts/assignments.py, whose docstring is the grammar) must
 * agree on what a top-level assignment is, where its value stands, and how a value
 * is written. tests/assignment_cases.json holds the cases both are held to: the
 * unit suite runs them through the server's module, the browser suite through this
 * one.
 *
 * Offsets are a JavaScript string's, UTF-16 code units, which is what the server
 * answers (`from`, `to`) and what CodeMirror counts.
 *
 *   parseAssignments(text) -> [{ name, expression, computed, value, value_known,
 *       line, from, to, comment, caption, group, parameter, min, max, step,
 *       options: [{ value, label }], unit, set: true }]
 *   lastOf(assignments) -> { name: its last assignment }, the one OpenSCAD uses
 *   literalValue(text) -> the literal it is, or throws Unparsed (an expression)
 *   literalText(value) -> the value as a SCAD literal, as the server writes one
 *   valueChanges(text, values) -> [{ from, to, insert }] writing each value into its
 *       name's last assignment, or appending `name = value;` at the end
 *   writeValues(text, values) -> the text with those changes made
 *   customizerComment(comment) -> { min, max, step, options } its comment tells
 */

export class Unparsed extends Error {}

const NAME = /\$?[A-Za-z_][A-Za-z0-9_]*/y;
const NUMBER = /[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?/y;
const WHOLE = /^[+-]?\d+$/;
const GROUP = /^\s*\[\s*([^\]]+?)\s*\]\s*$/;
const DEFINES = new Set(["module", "function"]);
export const HIDDEN = "Hidden";

// Python's str.isspace, for the characters a SCAD text holds.
const SPACE = /\s/;
const isSpace = (ch) => ch !== undefined && SPACE.test(ch);

function matchAt(pattern, text, at) {
    pattern.lastIndex = at;
    const found = pattern.exec(text);
    return found ? { text: found[0], end: at + found[0].length } : null;
}

// --- literals --------------------------------------------------------------------------

function literal(text, at = 0) {
    const n = text.length;
    while (at < n && isSpace(text[at])) at += 1;
    if (at >= n) throw new Unparsed("nothing");
    const ch = text[at];
    if (ch === '"') {
        const out = [];
        const escapes = { n: "\n", t: "\t", r: "\r", '"': '"', "\\": "\\" };
        let i = at + 1;
        while (i < n && text[i] !== '"') {
            if (text[i] === "\\" && i + 1 < n) {
                const next = text[i + 1];
                if (next in escapes) { out.push(escapes[next]); i += 2; continue; }
                if (next === "x" && i + 3 < n) { out.push(String.fromCodePoint(parseInt(text.slice(i + 2, i + 4), 16))); i += 4; continue; }
                if (next === "u" && i + 5 < n) { out.push(String.fromCodePoint(parseInt(text.slice(i + 2, i + 6), 16))); i += 6; continue; }
            }
            out.push(text[i]);
            i += 1;
        }
        if (i >= n) throw new Unparsed("an unclosed string");
        return [out.join(""), i + 1];
    }
    if (ch === "[") {
        const items = [];
        let i = at + 1;
        for (;;) {
            while (i < n && isSpace(text[i])) i += 1;
            if (i < n && text[i] === "]") return [items, i + 1];
            const [value, end] = literal(text, i);
            items.push(value);
            i = end;
            while (i < n && isSpace(text[i])) i += 1;
            if (i < n && text[i] === ",") { i += 1; continue; }
            if (i < n && text[i] === "]") return [items, i + 1];
            throw new Unparsed("not a vector of literals");
        }
    }
    const word = matchAt(NAME, text, at);
    if (word) {
        const keyword = { true: true, false: false, undef: null };
        if (word.text in keyword) return [keyword[word.text], word.end];
        throw new Unparsed(`a name: ${word.text}`);
    }
    const number = matchAt(NUMBER, text, at);
    if (number) return [Number(number.text), number.end];
    throw new Unparsed(`not a literal at ${JSON.stringify(text.slice(at, at + 10))}`);
}

export function literalValue(text) {
    const [value, end] = literal(text);
    if (text.slice(end).trim()) throw new Unparsed("more after the literal: an expression");
    return value;
}

// A number as Python's repr writes a float: fixed from 1e-4 up to 1e16, else with an
// exponent of at least two digits; the digits the shortest that read back the same,
// as JavaScript's are.
function pythonFloat(x) {
    const [mantissa, exp] = x.toExponential().split("e");
    const e = Number(exp);
    const negative = mantissa.startsWith("-");
    const digits = mantissa.replace("-", "").replace(".", "");
    const sign = negative ? "-" : "";
    if (e < -4 || e >= 16) {
        const m = digits.length > 1 ? `${digits[0]}.${digits.slice(1)}` : digits;
        return `${sign}${m}e${e < 0 ? "-" : "+"}${String(Math.abs(e)).padStart(2, "0")}`;
    }
    let fixed;
    if (e < 0) fixed = `0.${"0".repeat(-e - 1)}${digits}`;
    else if (digits.length > e + 1) fixed = `${digits.slice(0, e + 1)}.${digits.slice(e + 1)}`;
    else fixed = `${digits}${"0".repeat(e + 1 - digits.length)}.0`;
    return `${sign}${fixed}`;
}

export function literalText(value) {
    if (typeof value === "boolean") return value ? "true" : "false";
    if (value === null || value === undefined) return "undef";
    if (typeof value === "number") {
        if (!Number.isFinite(value)) throw new Error(`${value} has no OpenSCAD literal`);
        if (Number.isInteger(value) && Math.abs(value) < 1e15) return String(value);
        return pythonFloat(value);
    }
    if (typeof value === "string") return `"${value.replace(/\\/g, "\\\\").replace(/"/g, '\\"')}"`;
    if (Array.isArray(value)) return `[${value.map(literalText).join(", ")}]`;
    throw new Error(`no OpenSCAD literal for ${JSON.stringify(value)}`);
}

// --- the customizer's comment ------------------------------------------------------------

const isNumber = (s) => { NUMBER.lastIndex = 0; const m = NUMBER.exec(s); return Boolean(m) && m.index === 0 && m[0].length === s.length; };

export function customizerComment(comment) {
    if (!comment) return {};
    const text = comment.trim();
    if (isNumber(text)) return { step: Number(text) };
    if (!(text.startsWith("[") && text.endsWith("]")) || text.split("[").length - 1 !== 1) return {};
    const inner = text.slice(1, -1).trim();
    if (!inner) return {};
    const colons = inner.split(":").length - 1;
    if (!inner.includes(",") && (colons === 1 || colons === 2)) {
        const bits = inner.split(":").map((b) => b.trim());
        if (bits.every(isNumber)) {
            const numbers = bits.map(Number);
            if (numbers.length === 2) return { min: numbers[0], max: numbers[1] };
            return { min: numbers[0], step: numbers[1], max: numbers[2] };
        }
    }
    if (!inner.includes(",") && !inner.includes(":") && isNumber(inner)) return { min: 0, max: Number(inner) };
    const options = [];
    for (const raw of inner.split(",")) {
        const part = raw.trim();
        if (!part) return {};
        const colon = part.indexOf(":");
        const value = (colon < 0 ? part : part.slice(0, colon)).trim();
        const label = colon < 0 ? "" : part.slice(colon + 1);
        let parsed = value;
        if (value) {
            try { parsed = literalValue(value); } catch (err) { if (!(err instanceof Unparsed)) throw err; parsed = value; }
        }
        options.push({ value: parsed, label: label.trim() || value });
    }
    return { options };
}

// --- a unit, as customizer.unit_of reads one ----------------------------------------------

const UNIT = "[^\\s\\[\\]:,]{1,12}";
const CAPTION_UNIT = new RegExp(`^(?<text>.*?)\\s*\\[(?<unit>${UNIT})\\]\\s*$`, "s");
const A_NUMBER = /^[-+]?(\d+\.?\d*|\.\d+)$/;
const escapeRe = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

function unitOf(name, caption, text) {
    if (typeof caption === "string") {
        const found = CAPTION_UNIT.exec(caption);
        if (found && !A_NUMBER.test(found.groups.unit)) return [found.groups.unit, found.groups.text.trim() || null];
    }
    if (text) {
        const own = new RegExp(`^[ \\t]*${escapeRe(name)}[ \\t]*=[^;\\n]*;[ \\t]*//[ \\t]*(?<unit>${UNIT})[ \\t]*$`, "m").exec(text);
        if (own && !A_NUMBER.test(own.groups.unit)) return [own.groups.unit, caption];
    }
    return [null, caption];
}

// --- the scan ------------------------------------------------------------------------------

function skipSpaceAndComments(text, i, groups) {
    const n = text.length;
    while (i < n) {
        if (isSpace(text[i])) i += 1;
        else if (text.startsWith("//", i)) {
            const end = text.indexOf("\n", i);
            i = end < 0 ? n : end + 1;
        } else if (text.startsWith("/*", i)) {
            const end = text.indexOf("*/", i + 2);
            const close = end < 0 ? n : end + 2;
            const group = end >= 0 ? GROUP.exec(text.slice(i + 2, close - 2)) : null;
            if (group) groups.push([i, group[1]]);
            i = close;
        } else break;
    }
    return i;
}

// From `i`, the end of the statement there and where its `;` at depth 0 is (null when
// it ended otherwise).
function statementEnd(text, i) {
    const n = text.length;
    let depth = 0;
    if (/^(include|use)\s*</.test(text.slice(i))) {
        const close = text.indexOf(">", i);
        return [close < 0 ? n : close + 1, null];
    }
    while (i < n) {
        const ch = text[i];
        if (text.startsWith("//", i)) {
            const end = text.indexOf("\n", i);
            i = end < 0 ? n : end + 1;
            continue;
        }
        if (text.startsWith("/*", i)) {
            const end = text.indexOf("*/", i + 2);
            i = end < 0 ? n : end + 2;
            continue;
        }
        if (ch === '"') {
            i += 1;
            while (i < n && text[i] !== '"') i += text[i] === "\\" ? 2 : 1;
            i += 1;
            continue;
        }
        if ("([{".includes(ch)) depth += 1;
        else if (")]}".includes(ch)) {
            depth -= 1;
            if (ch === "}" && depth <= 0) return [i + 1, null];
        } else if (ch === ";" && depth <= 0) return [i + 1, i];
        i += 1;
    }
    return [n, null];
}

const lineOf = (text, at) => text.slice(0, at).split("\n").length;

function trailingComment(text, after) {
    const n = text.length;
    let i = after;
    while (i < n && (text[i] === " " || text[i] === "\t")) i += 1;
    if (text.startsWith("//", i)) {
        const end = text.indexOf("\n", i);
        return text.slice(i + 2, end < 0 ? n : end).trim();
    }
    return null;
}

function captionAbove(text, start) {
    const lineStart = text.lastIndexOf("\n", start - 1) + 1;
    if (lineStart === 0) return null;
    const aboveEnd = lineStart - 1;
    const aboveStart = aboveEnd > 0 ? text.lastIndexOf("\n", aboveEnd - 1) + 1 : 0;
    const above = text.slice(aboveStart, aboveEnd).trim();
    if (above.startsWith("//")) return above.slice(2).trim() || null;
    return null;
}

export function parseAssignments(text) {
    const found = [];
    const groups = [];
    let defined = false;
    let i = 0;
    const n = text.length;
    for (;;) {
        i = skipSpaceAndComments(text, i, groups);
        if (i >= n) break;
        const word = matchAt(NAME, text, i);
        if (word && DEFINES.has(word.text)) defined = true;
        let assigned = null;
        if (word) {
            let j = word.end;
            while (j < n && " \t\r\n".includes(text[j])) j += 1;
            if (j < n && text[j] === "=" && !text.startsWith("==", j)) assigned = [word.text, j + 1];
        }
        const [end, semicolon] = statementEnd(text, i);
        if (assigned && semicolon !== null) {
            const [name, afterEq] = assigned;
            let start = afterEq;
            while (start < semicolon && isSpace(text[start])) start += 1;
            let stop = semicolon;
            while (stop > start && isSpace(text[stop - 1])) stop -= 1;
            const expression = text.slice(start, stop);
            let value = null, computed = false;
            try { value = literalValue(expression); } catch (err) { if (!(err instanceof Unparsed)) throw err; computed = true; }
            const group = groups.length ? groups[groups.length - 1][1] : null;
            const comment = trailingComment(text, semicolon + 1);
            const told = customizerComment(comment);
            const [unit, caption] = unitOf(name, captionAbove(text, i), text);
            found.push({
                name,
                expression,
                computed,
                value,
                value_known: !computed,
                line: lineOf(text, i),
                from: start,
                to: stop,
                comment,
                caption,
                group,
                parameter: !defined && group !== HIDDEN,
                min: told.min ?? null,
                max: told.max ?? null,
                step: told.step ?? null,
                options: told.options ?? [],
                unit,
                set: true,
            });
        }
        if (end <= i) break;
        i = end;
    }
    return found;
}

export function lastOf(assignments) {
    const out = {};
    for (const a of assignments) out[a.name] = a;
    return out;
}

export function valueChanges(text, values) {
    const at = lastOf(parseAssignments(text));
    const changes = [];
    const appended = [];
    for (const [name, value] of Object.entries(values)) {
        if (!/^\$?[A-Za-z_][A-Za-z0-9_]*$/.test(name)) throw new Error(`${JSON.stringify(name)} is not a SCAD name`);
        const written = literalText(value);
        if (at[name]) changes.push({ from: at[name].from, to: at[name].to, insert: written });
        else appended.push(`${name} = ${written};`);
    }
    changes.sort((a, b) => a.from - b.from);
    if (appended.length) {
        const lead = text && !text.endsWith("\n") ? "\n" : "";
        changes.push({ from: text.length, to: text.length, insert: `${lead}${appended.join("\n")}\n` });
    }
    return changes;
}

export function writeValues(text, values) {
    let out = text;
    for (const c of [...valueChanges(text, values)].sort((a, b) => b.from - a.from)) out = out.slice(0, c.from) + c.insert + out.slice(c.to);
    return out;
}
