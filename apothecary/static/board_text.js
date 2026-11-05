/* How a board's state is written: once, for every drawer.
 *
 * The world's badge, the badge on Site's tree, Selected's Device line and the
 * Machine's cards write a board's state from here, so they agree: one heater, one
 * printer line, one summary of a board (a printer's poll, or a devkit's sketch
 * against what it was heard saying). Pure functions of what they are given;
 * nothing here fetches, listens or keeps state (boards.js does that).
 */

import { KINDS, STATE_CLS, kindOf } from "/static/machine_words.js";

export const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

// One heater: what it reads over what it is set to; "—" when there is none.
export function heaterText(h) {
    return h ? `${h.actual.toFixed(1)}/${h.target.toFixed(0)}°` : "—";
}

// The two readings, rounded, as a badge carries them: "210°/60°".
export function readingsText(st) {
    const t = st && st.hotends && st.hotends[0] ? st.hotends[0].actual.toFixed(0) : "?";
    const b = st && st.bed ? st.bed.actual.toFixed(0) : "?";
    return `${t}°/${b}°`;
}

// What a printer is doing, in one word: offline, printing, heating, idle.
export function stateWord(st) {
    if (!st) return null;
    if (st.state === "offline") return "offline";
    if (st.state === "printing") return "printing";
    return st.heating ? "heating" : st.state;
}

// A board as a person would name it: its firmware and machine, its chip, or its USB name.
export function boardLabel(d) {
    if (!d) return "";
    if (d.printer) return (d.printer.firmware_name || "printer").replace(/\s*\(.*$/, "") + (d.printer.machine_type ? ` · ${d.printer.machine_type}` : "");
    if (d.chip) return `${d.chip}${d.mac ? " · " + d.mac : ""}`;
    return d.board_name || `${d.vid ?? "?"}:${d.pid ?? "?"}`;
}

// The temperatures of a poll: "T 210.1/210° · B 60.0/60°".
export function tempsText(st) {
    if (!st || !st.hotends) return "";
    return `T ${heaterText(st.hotends[0])}${st.bed ? " · B " + heaterText(st.bed) : ""}`;
}

// A position as the page writes one, wherever it writes one.
export const xyz = (p) => `X${p.x.toFixed(1)} Y${p.y.toFixed(1)} Z${p.z.toFixed(2)}`;
// The same as markup, for a card that may wrap it: between its axes, never inside a
// number, where a minus sign would otherwise end a line and the number start the next.
export const xyzHtml = (p) => xyz(p).split(" ").map((axis) => `<span class="nb">${axis}</span>`).join(" ");

// A router's poll as one line: its state and the controller's word, the tool in the
// work zero, the spindle, and the alarm when it is in one.
export function routerLine(st) {
    if (!st) return "not polled yet";
    if (st.state === "offline") return `offline${st.raw && st.raw[0] ? " " + st.raw[0] : ""}`;
    let line = st.state + (st.machine_state ? ` (${st.machine_state})` : "");
    const p = st.work_position || st.position;
    if (p) line += ` · ${xyz(p)}`;
    if (st.spindle) line += st.spindle.on ? ` · spindle ${st.spindle.rpm.toFixed(0)} rpm` : " · spindle off";
    if (st.alarm != null) line += ` · alarm ${st.alarm}`;
    return line;
}

// A printer's poll as one line: state, temperatures, where the head is, how far a
// print on its card is, and the filament when it has run out.
export function printerLine(st) {
    if (!st) return "not polled yet";
    if (st.state === "offline") return `offline${st.raw && st.raw[0] ? " " + st.raw[0] : ""}`;
    let line = `${stateWord(st)} · ${tempsText(st)}`;
    if (st.position) line += ` · X${st.position.x.toFixed(0)} Y${st.position.y.toFixed(0)} Z${st.position.z.toFixed(1)}`;
    if (st.sd_printing && st.sd_progress != null) line += ` · ${(st.sd_progress * 100).toFixed(1)}%`;
    if (st.filament_present === false) line += " · filament out";
    return line;
}

// What a devkit should run against what it was heard saying, and what has
// changed since it was flashed. `expected` is the server's expected-firmware
// view; `observed` the sketch name its hello banner gave, or null.
export function sketchWords(expected, observed) {
    const rec = expected && expected.record;
    // Which build the board should run, named with its toolchain (esp32_blink@rust-esp32);
    // what it is heard saying is the sketch's name alone, which either build says.
    const should = rec ? (rec.sketch_id || rec.sketch || `raw images: ${(rec.images || []).join(", ")}`) : null;
    const drift = [];
    if (expected && expected.source_changed) drift.push("sketch source edited since this upload");
    if (expected && expected.build_changed) drift.push("a newer build exists that was never uploaded");
    if (expected && expected.sketch_missing) drift.push("that sketch no longer exists under parts/");
    const verdict = !observed || !rec || !rec.sketch ? "unknown" : (observed === rec.sketch ? "match" : "mismatch");
    let short;
    if (observed && should) short = verdict === "match" ? `runs ${should} ✓` : `runs ${observed}, should run ${should}`;
    else if (observed) short = `runs ${observed}`;
    else if (should) short = `should run ${should}`;
    else short = "nothing flashed from apothecary";
    return { should, observed: observed || null, verdict, drift, short, rec };
}

// A router's one reading at a glance, as a printer's is its temperatures: its
// spindle's speed while it turns; none otherwise, and its state word says enough.
export function spindleText(st) {
    return st && st.spindle && st.spindle.on ? `${st.spindle.rpm.toFixed(0)} rpm` : null;
}

// One board, summed up for the drawers that show it small: the badges and
// Selected's line. `board` is boards.js's board (device, status, expected,
// observed). Answers { kind, icon, state, short, line, cls, title }: for a G-code
// machine, the kind's icon, its state word, one reading (a printer's temperatures,
// a router's spindle), the job's progress, and the class the state word wears.
export function boardSummary(board) {
    const d = board && board.device;
    if (!d) return { kind: "none", icon: "⌁", state: "off", short: "not connected", line: "not connected", cls: "off", title: "not connected" };
    const label = boardLabel(d);
    const kind = kindOf(d);
    if (kind !== "devkit") {
        const st = board.status, words = KINDS[kind];
        const word = kind === "router" ? (st ? st.state : null) : stateWord(st);
        const offline = !!(st && st.state === "offline");
        const parts = [];
        if (kind === "printer" && st && st.sd_printing && st.sd_progress != null) parts.push(`${(st.sd_progress * 100).toFixed(0)}%`);
        if (st && st.job) parts.push(st.job.kind === words.job ? `${st.job.kind} ${(st.job.progress * 100).toFixed(0)}%` : `${st.job.kind}: ${st.job.stage}`);
        const line = kind === "router" ? routerLine(st) : printerLine(st);
        return {
            kind, icon: words.icon, state: word || "not polled",
            readings: st && !offline ? (kind === "router" ? spindleText(st) : readingsText(st)) : null,
            temps: kind === "printer" && st && !offline ? tempsText(st) : null,
            extra: parts, job: !!(st && st.job),
            short: st ? (offline ? "offline" : word) : "not polled yet",
            line,
            cls: STATE_CLS[word] || "",
            title: `${label} on ${d.port} — ${line}`,
        };
    }
    const words = sketchWords(board.expected, board.observed);
    return {
        kind: "devkit", icon: KINDS.devkit.icon, state: words.short, short: words.short, line: words.short, words,
        cls: words.verdict === "mismatch" ? "mismatch" : "", extra: [], job: false,
        title: `${label} on ${d.port} — ${words.short}${words.drift.length ? " (" + words.drift.join("; ") + ")" : ""}`,
    };
}
