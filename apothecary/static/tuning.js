/* Tuning: what the Print window's measured row says of a printer's tuning (docs/print-tuning.md).
 *
 * Pure functions on the slice records and the print/tuning/1 documents the server
 * answers, no DOM, so each can be held under node (tests/test_tuning_js.py). The server
 * computes every figure (apothecary/slicer/tuning.py); this only reads them.
 *
 *   planOf(record)              what a person reads of the piece a slice made: its part's
 *                               plan, else its box (x and y across at the base, its height)
 *   appliesOf(record)           the filament and process profiles the slice was made with
 *   parseReads(text)            "20.08 20.1" as [20.08, 20.1]; [] for nothing; null for
 *                               what is not sizes
 *   documentFor(docs, applies)  the document of those profiles among a printer's
 *   canApply(doc), canUndo(doc) { ok, why }: what Apply and Undo turn would be refused for
 *   turnLine(turn)              a turn in one line: the terms it determined, what it could
 *                               not separate, the changes it proposed and whether applied
 *   historyLines(doc, trends)   each turn's line, then each setting's trend
 */

/* A plan's features from a slice record: its own, else the box it sliced. */
export function planOf(record) {
    if (record && record.plan && record.plan.features && record.plan.features.length) return record.plan.features;
    if (!record || !record.size) return [];
    const [x, y, z] = record.size;
    return [
        { name: "x", kind: "outside", axis: "x", level: "base", jaw: "outside", nominal: x, words: "the part across X, at its widest" },
        { name: "y", kind: "outside", axis: "y", level: "base", jaw: "outside", nominal: y, words: "the part across Y, at its widest" },
        { name: "z", kind: "height", axis: "z", level: "above", jaw: "outside", nominal: z, words: "the part's height, bed face to top" },
    ];
}

export function appliesOf(record) {
    const named = Object.fromEntries((record && record.settings || []).map((s) => [s.name, s.value]));
    const filament = named["filament profile"], process = named["process profile"];
    return filament && process ? { filament: String(filament), process: String(process) } : null;
}

export function parseReads(text) {
    const words = String(text || "").trim().split(/[\s,;]+/).filter(Boolean);
    const out = words.map(Number);
    return out.every((v) => Number.isFinite(v) && v > 0) ? out : null;
}

export function documentFor(docs, applies) {
    if (!applies) return null;
    const found = (docs || []).find((d) => d.document && d.document.applies_to
        && d.document.applies_to.filament === applies.filament && d.document.applies_to.process === applies.process);
    return found || null;
}

export function canApply(entry) {
    const doc = entry && entry.document;
    if (!doc || !doc.turns.length) return { ok: false, why: "no turn read yet: read the piece and Keep" };
    const last = doc.turns[doc.turns.length - 1];
    if (last.applied.length) return { ok: false, why: `${last.id} is applied already: print and read the next piece` };
    const moves = last.proposed.filter((p) => p.applies && p.new !== null);
    if (!moves.length) return { ok: false, why: `${last.id} proposes no change` };
    return { ok: true, why: `take ${last.id}'s ${moves.map((p) => p.setting).join(", ")} into this printer's next slices` };
}

export function canUndo(entry) {
    const doc = entry && entry.document;
    if (!doc || !doc.turns.length) return { ok: false, why: "no turn to undo" };
    const last = doc.turns[doc.turns.length - 1];
    return { ok: true, why: `drop ${last.id}${last.applied.length ? ", and what it applied" : ""}` };
}

function termText(t) {
    if (t.value === null || t.value === undefined) return `${t.term} -`;
    if (t.unit === "mm") return `${t.term} ${t.value >= 0 ? "+" : ""}${t.value.toFixed(3)} ± ${(t.error || 0).toFixed(3)} mm`;
    return `${t.term} ${t.value >= 0 ? "+" : ""}${(t.value * 100).toFixed(2)} ± ${((t.error || 0) * 100).toFixed(2)} %`;
}

function settingText(v, unit) {
    if (v === null || v === undefined) return "-";
    return unit === "%" ? `${+v.toFixed(3)}%` : `${v >= 0 ? "+" : ""}${v.toFixed(3)}`;
}

export function turnLine(turn) {
    const found = turn.terms.filter((t) => t.determined && t.basis === "solved" && t.term !== "scale_xy").map(termText);
    const loose = turn.terms.filter((t) => !t.determined && t.term !== "scale_xy").map((t) => t.term).sort();
    const moves = turn.proposed.filter((p) => p.new !== null)
        .map((p) => `${p.setting} ${settingText(p.used, p.unit)} → ${settingText(p.new, p.unit)}`);
    let out = `${turn.id}, ${turn.slice.part}: ` + (found.length ? found.join(", ") : "no term determined");
    if (loose.length) out += `; not separated: ${loose.join(", ")}`;
    out += `; proposed: ${moves.length ? moves.join("; ") : "nothing"}`;
    if (turn.applied.length) out += " (applied)";
    return out;
}

export function historyLines(entry) {
    if (!entry || !entry.document) return [];
    const lines = entry.document.turns.map(turnLine);
    for (const [key, t] of Object.entries(entry.trends || {})) {
        if (t.state === "not determined") continue;
        lines.push(`${key}: ${t.state}${t.stop ? " (stop)" : ""} — ${t.said}`);
    }
    return lines;
}
