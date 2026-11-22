/* Tuning: what the Print window's measured row says of a printer's tuning (docs/print-tuning.md).
 *
 * Pure functions on the slice records and the print/tuning/1 documents the server
 * answers, no DOM, so each can be held under node (tests/test_tuning_js.py). The server
 * computes every figure (apothecary/slicer/tuning.py); this only reads them.
 *
 *   appliesOf(record)           the filament and process profiles the slice was made with
 *   parseReads(text)            "20.08 20.1" as [20.08, 20.1]; [] for nothing; null for
 *                               what is not sizes
 *   documentFor(docs, applies)  the document of those profiles among a printer's
 *   entries(doc)                its turns and looks in the order they were kept
 *   canApply(doc), canUndo(doc) { ok, why }: what Apply and Undo would be refused for: the
 *                               newest turn or look's
 *   turnLine(turn)              a turn in one line: the terms it determined, what it could
 *                               not separate, the changes it proposed and whether applied
 *   lookLine(look)              a look in one line: the faults seen, the change it proposes
 *   historyLines(doc, trends)   each turn's and look's line, then each setting's trend and
 *                               each fault's over the looks
 *   seenOf(choices)             the severities a look sends, from the seen row's choices
 */

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

export function entries(doc) {
    if (!doc) return [];
    return [...(doc.turns || []), ...(doc.looks || [])].sort((a, b) => (a.at < b.at ? -1 : a.at > b.at ? 1 : 0));
}

export function canApply(entry) {
    const doc = entry && entry.document, all = entries(doc);
    if (!all.length) return { ok: false, why: "no turn read or look kept yet: read or look at the piece and Keep" };
    const last = all[all.length - 1];
    if (last.applied.length) return { ok: false, why: `${last.id} is applied already: print and read the next piece` };
    const moves = last.proposed.filter((p) => p.applies && p.new !== null);
    if (!moves.length) return { ok: false, why: `${last.id} proposes no change` };
    return { ok: true, why: `take ${last.id}'s ${moves.map((p) => p.setting).join(", ")} into this printer's next slices` };
}

export function canUndo(entry) {
    const all = entries(entry && entry.document);
    if (!all.length) return { ok: false, why: "no turn or look to undo" };
    const last = all[all.length - 1];
    return { ok: true, why: `drop ${last.id}${last.applied.length ? ", and what it applied" : ""}` };
}

function termText(t) {
    if (t.value === null || t.value === undefined) return `${t.term} -`;
    if (t.unit === "mm") return `${t.term} ${t.value >= 0 ? "+" : ""}${t.value.toFixed(3)} ± ${(t.error || 0).toFixed(3)} mm`;
    return `${t.term} ${t.value >= 0 ? "+" : ""}${(t.value * 100).toFixed(2)} ± ${((t.error || 0) * 100).toFixed(2)} %`;
}

export function settingText(v, unit) {
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

const SEVERITY = ["none", "slight", "clear", "bad"];

function plainText(v, unit) {
    if (v === null || v === undefined) return "-";
    const n = `${+(+v).toFixed(4)}`;
    return unit === "%" ? `${n}%` : unit ? `${n} ${unit}` : n;
}

export function lookLine(look) {
    const seen = look.seen.filter((x) => x.severity > 0)
        .map((x) => `${x.fault.replace(/_/g, " ")} ${SEVERITY[x.severity]}${x.where ? ` (${x.where})` : ""}`);
    const moves = look.proposed.map((p) => `${p.setting} ${plainText(p.used, p.unit)} → ${plainText(p.new, p.unit)}${p.back ? " (put back)" : ""}`);
    let out = `${look.id}, ${look.slice.part}, seen: ` + (seen.length ? seen.join(", ") : "nothing wrong");
    out += `; proposed: ${moves.length ? moves.join("; ") : "nothing"}`;
    if (look.said && look.said.length) out += ` — ${look.said.join("; ")}`;
    if (look.applied.length) out += " (applied)";
    return out;
}

export function historyLines(entry) {
    if (!entry || !entry.document) return [];
    const lines = entries(entry.document).map((e) => (e.seen ? lookLine(e) : turnLine(e)));
    for (const [key, t] of Object.entries(entry.trends || {})) {
        if (t.state === "not determined") continue;
        lines.push(`${key}: ${t.state}${t.stop ? " (stop)" : ""} — ${t.said}`);
    }
    for (const [fault, said] of Object.entries(entry.faults || {})) lines.push(`${fault.replace(/_/g, " ")}: ${said}`);
    return lines;
}

/* The seen row's choices, [[fault, severity], ...], as a look sends them: every fault
   looked for, none included, so a fault that went away is said to have. */
export function seenOf(choices) {
    const out = {};
    for (const [fault, severity] of choices || []) {
        const n = Number(severity);
        if (Number.isInteger(n) && n >= 0 && n <= 3) out[fault] = n;
    }
    return out;
}
