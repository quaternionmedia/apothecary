/* Part › Feedback: what was made of a part, a drawer for each piece, and what is said of a
 * piece, filed in its drawer (apothecary/cabinet.py, /cabinet; docs/cabinet.md).
 *
 * The part is the one a piece's ring's Part › View › Feedback opened it on, a print's or a
 * cut's end, or ⊞ Windows › Feedback with a part's piece selected; show(part, { drawer,
 * job }) chooses it, and among its pieces the drawer of that id or of that job. A part's pieces
 * are its drawers, the newest first, then each kept slice or toolpath of it that no
 * drawer holds yet -- a piece printed or cut elsewhere -- whose drawer is opened when
 * something is first filed of it. The pieces drop-down holds the part's first, then every
 * other part's that has a drawer or a kept file, a group each: a piece of another part
 * chosen there is that part's cabinet shown, which is how a part standing in no site is
 * reached.
 *
 * A print that stopped -- cancelled, or failed -- says the layer it stopped on, of the file's
 * layers, and offers what to try: Probe first, Brim and Raft each slice the piece again, as
 * its printer's Print window would with that chosen (`retry`, the page's), and say it in
 * that window's words (first_layer.js), as the made row says how the piece was made. A
 * fault seen on it is filed on that layer.
 *
 * Under the piece chosen: a print's features to read, a row each as the piece's dimensions
 * name them (GET /cabinet/{part}/dimensions, its slice's plan or its box), each with its
 * designed size and its newest reading checked against it, with Keep (or Enter in a row)
 * -- its printer's next turn of its tuning -- and Take turn
 * and Undo turn for that printer, the filament and process the piece used; each fault seen,
 * none to bad, with Keep look -- the printer's next look; a cut's sizes in one field, with
 * Keep -- the router's tool allowance; a note, with Keep note; and what the drawer holds,
 * in the order it was filed, an undone filing struck through. Nothing here sends anything
 * to a machine.
 *
 * mountFeedback(root, { base, say, retry }) -> handle
 *   show(part, { drawer, job })   this part's cabinet, the drawer named (or that job's) chosen
 *   verb(action)                   feedback:measure, feedback:note, feedback:tune-apply,
 *                                  feedback:tune-undo, feedback:try-probe, feedback:try-brim,
 *                                  feedback:try-raft: { said } or { refused }
 *   pick(name)                     the row of the dimension `name` of the piece chosen marked
 *                                  and its field given the caret, as a dimension clicked in
 *                                  the world does: { said } or { refused }
 *   part()                         the part shown, or null
 *   dimensions()                   the piece chosen's dimensions, as the server said them, or
 *                                  null: what the world's Measure layer marks on the part
 *   redraw()                       its rows again, as the window comes to the front
 *   pairs()                        each control by the ring verb it is, for the addresses
 * `say(text, kind)` is the page's status line, "error" for a refusal. `retry(drawer, how)`
 * slices the drawer's piece again for the printer that made it, `how` "probe" (probe first),
 * "brim" or "raft": { said } or { refused }. Each piece chosen, and
 * again after each filing, it says so on the window as "apothecary:feedback-shown"
 * ({ part, drawer }), so what reads the same dimensions reads them again.
 */

import { esc } from "/static/board_text.js";
import { mm as mmText, stamp } from "/static/format.js";
import { setReason } from "/static/can.js";
import * as tuning from "/static/tuning.js";
import { TRIES, made as madeOf, tryRefused, words } from "/static/first_layer.js";

export const VERBS = [
    "feedback:measure", "feedback:note", "feedback:tune-apply", "feedback:tune-undo",
    "feedback:try-probe", "feedback:try-brim", "feedback:try-raft",
];
// What a print that stopped offers to try, each slicing the piece again with it chosen.
const tryTip = (how) => `Slice this piece again for its printer with ${words(TRIES[how].choice)}. Nothing is sent`;
// How a print that did not finish ended (cabinet.STOPPED).
const STOPPED = ["cancelled", "failed"];

// Where a print stopped, in words (cabinet.Stopped.said).
export function stoppedSaid(s) {
    if (!s) return "where is not known: its file is no longer kept";
    if (s.layer === 0) return `in its start, before the first of ${s.layers} layers`;
    return `on layer ${s.layer} of ${s.layers}${s.z != null ? `, ${s.z} mm` : ""}`;
}

export function mountFeedback(root, { base = "", say = null, retry = null } = {}) {
    // part: shown; pieces: every part's drawers then its loose kept files, the part shown's
    // first ({ key, part, label, drawer?, record?, made });
    // chosen: the key of the piece chosen; whole: the drawer chosen, whole, as the server said it.
    // dims: the piece chosen's dimensions (cabinet.dimensions), as the server said them.
    const st = { part: null, pieces: [], chosen: null, whole: null, dims: null, faults: null, asking: 0, want: null };

    root.innerHTML = `<div class="cards feedback"><div class="card wide" id="feedback-card">
        <div class="k"><span id="feedback-title">Feedback</span></div>
        <p class="s" id="feedback-empty"></p>
        <div class="row" id="feedback-piece-row" hidden><label for="feedback-piece">piece</label>
            <select id="feedback-piece" title="Each piece made of the part, the newest first, then each kept slice or toolpath of it made elsewhere: the drawer its feedback is filed in"></select>
            <span class="s" id="feedback-piece-said"></span>
        </div>
        <div class="row" id="feedback-made-row" hidden><label>made</label>
            <span class="s" id="feedback-made-said"></span>
        </div>
        <div class="row" id="feedback-stopped-row" hidden><label>stopped</label>
            <span class="s" id="feedback-stopped-said"></span>
            <button type="button" id="feedback-try-probe" title="${tryTip("probe")}">Probe first</button>
            <button type="button" id="feedback-try-brim" title="${tryTip("brim")}">Brim</button>
            <button type="button" id="feedback-try-raft" title="${tryTip("raft")}">Raft</button>
        </div>
        <div class="row" id="feedback-measure-row" hidden><label for="feedback-measure">measured</label>
            <input id="feedback-measure" size="16" spellcheck="false" title="What the piece this toolpath cut measures, in millimetres, each feature it names in order, any left out as -">
            <button type="button" id="feedback-measure-keep" title="Check what was read against what was made and file it: a printer's next turn of its tuning, said and not applied; a router's tool allowance. Nothing is sent to the machine">Keep</button>
            <button type="button" id="feedback-tune-apply" title="Take the last turn's changes into the next slices of the printer that made this piece">Take turn</button>
            <button type="button" id="feedback-tune-undo" title="Drop the last turn, and what it applied">Undo turn</button>
            <span class="s" id="feedback-measure-said"></span>
        </div>
        <div class="row" id="feedback-measure-plan" hidden></div>
        <div class="row" id="feedback-seen-row" hidden><label for="feedback-seen-keep">seen</label>
            <span id="feedback-seen-faults" class="seen-faults"></span>
            <button type="button" id="feedback-seen-keep" title="File what the piece shows as its printer's next look: the one setting's change it implies is said, and Take turn takes it into the next slices. Nothing is sent to the machine">Keep look</button>
            <span class="s" id="feedback-seen-said"></span>
        </div>
        <div class="row" id="feedback-note-row" hidden><label for="feedback-note">note</label>
            <input id="feedback-note" size="28" maxlength="2000" spellcheck="true" placeholder="what the piece is like" title="A note on the piece, filed in its drawer: it changes no machine's settings">
            <button type="button" id="feedback-note-keep" title="File the note in the piece's drawer">Keep note</button>
        </div>
        <div class="row s" id="feedback-tune-history" hidden></div>
        <ol id="feedback-filed" class="feedback-filed" hidden></ol>
    </div></div>`;
    const $ = (id) => root.querySelector(`#${id}`);

    async function api(path, opts = {}) {
        const r = await fetch(base + path, { headers: { "Content-Type": "application/json" }, ...opts });
        const body = await r.json().catch(() => ({}));
        if (!r.ok) {
            const d = body.detail;
            throw new Error(typeof d === "string" ? d : Array.isArray(d)
                ? d.map((e) => `${(e.loc || []).filter((p) => p !== "body").join(".")}: ${e.msg}`).join("; ")
                : r.statusText);
        }
        return body;
    }
    const post = (path, data) => api(path, { method: "POST", body: JSON.stringify(data || {}) });
    const tell = (text) => { if (say) say(text, "success"); return { said: text }; };
    const refuse = (text) => { if (say) say(text, "error"); return { refused: text }; };
    const at = () => `/cabinet/${encodeURIComponent(st.part)}`;
    const signed = (v) => `${v >= 0 ? "+" : ""}${v.toFixed(3)}`;

    // ---- the part's pieces ---------------------------------------------------------------
    async function load() {
        const asked = ++st.asking;
        let parts = [], slices = [], cuts = [];
        try {
            [parts, slices, cuts] = await Promise.all([
                api("/cabinet").then((a) => a.parts),
                api("/slicer/slices").catch(() => []),
                api("/cam/cuts").catch(() => []),
            ]);
        } catch (e) { if (asked === st.asking) { st.pieces = []; render(`the cabinet: ${e.message}`); } return; }
        const named = new Set([...parts, ...slices.filter((r) => r.made.kind === "part").map((r) => r.made.name), ...cuts.map((r) => r.part)]);
        if (st.part) named.add(st.part);
        const order = [...named].sort((a, b) => (a === st.part ? -1 : b === st.part ? 1 : a.localeCompare(b)));
        let drawers;
        try { drawers = await Promise.all(order.map((part) => (parts.includes(part) ? api(`/cabinet/${encodeURIComponent(part)}`).then((a) => a.drawers) : []))); }
        catch (e) { if (asked === st.asking) { st.pieces = []; render(`the cabinet: ${e.message}`); } return; }
        if (asked !== st.asking) return;
        st.pieces = order.flatMap((part, i) => {
            const held = new Set(drawers[i].map((d) => d.file.file_id));
            return [
                ...drawers[i].map((d) => ({ key: `drawer:${d.id}`, part, drawer: d, made: d.made, label: `${stamp(d.at)} · ${d.line}` })),
                ...slices.filter((r) => r.made.kind === "part" && r.made.name === part && !held.has(r.file_id))
                    .map((r) => ({ key: `file:${r.file_id}`, part, record: r, made: "print", label: `${stamp(r.at)} · ${r.name}, sliced for ${r.printer.name}: not printed from here` })),
                ...cuts.filter((r) => r.part === part && !held.has(r.file_id))
                    .map((r) => ({ key: `file:${r.file_id}`, part, record: r, made: "cut", label: `${stamp(r.at)} · ${r.name}, a toolpath for ${r.router.name}: not cut from here` })),
            ];
        });
        const want = st.want;
        st.want = null;
        const wanted = want && st.pieces.find((p) => p.drawer && (p.drawer.id === want.drawer || (want.job && p.drawer.job && p.drawer.job.id === want.job)));
        const kept = st.pieces.find((p) => p.key === st.chosen);
        const first = st.pieces.find((p) => p.part === st.part);
        st.chosen = (wanted || kept || first || {}).key || null;
        await choose(st.chosen);
    }
    const piece = () => st.pieces.find((p) => p.key === st.chosen) || null;
    async function choose(key) {
        st.chosen = key;
        const p = piece();
        // A piece of another part chosen: that part's cabinet is the one shown.
        if (p) st.part = p.part;
        st.whole = null;
        st.dims = null;
        if (p && p.drawer) {
            try { st.whole = await api(`${at()}/drawers/${encodeURIComponent(p.drawer.id)}`); }
            catch (e) { render(`drawer ${p.drawer.id}: ${e.message}`); return; }
            st.dims = st.whole.dimensions || null;
        } else if (p && p.record) {
            try { st.dims = await api(`${at()}/dimensions?file=${encodeURIComponent(p.record.file_id)}`); }
            catch (e) { render(`${p.record.name}: ${e.message}`); return; }
        }
        render();
        shown();
    }
    // The piece chosen, or its drawer filed in: what reads its dimensions reads them again.
    function shown() {
        window.dispatchEvent(new CustomEvent("apothecary:feedback-shown", { detail: { part: st.part, drawer: st.whole ? st.whole.id : null } }));
    }
    const dims = () => (st.dims && st.dims.dimensions) || [];
    // The drawer the piece chosen is filed in: its own, else one opened for its kept file.
    async function drawerOf() {
        const p = piece();
        if (!p) throw new Error(`choose a piece of ${st.part}`);
        if (p.drawer) return p.drawer.id;
        const opened = await post(`${at()}/drawers`, { file_id: p.record.file_id });
        st.want = { drawer: opened.id };
        p.drawer = opened; p.key = `drawer:${opened.id}`; st.chosen = p.key; st.whole = opened; st.dims = opened.dimensions || st.dims;
        return opened.id;
    }
    // What made the piece chosen: its slice's record or its toolpath's.
    function record() {
        const p = piece();
        if (!p) return null;
        if (st.whole) return st.whole.slice || st.whole.cut;
        return p.record || null;
    }
    const printed = () => { const p = piece(); return !!p && p.made === "print"; };

    // ---- drawing -------------------------------------------------------------------------
    function render(problem = null) {
        const p = piece(), r = record();
        $("feedback-title").textContent = st.part ? `Feedback · ${st.part}` : "Feedback";
        const mine = st.pieces.filter((x) => x.part === st.part);
        const empty = !st.part
            ? `Choose a part: a piece's ring, Part › View › Feedback, opens what was made of it here, and so does a print's or a cut's end${st.pieces.length ? "; or choose a piece of any part under piece" : ""}.`
            : !mine.length ? `Nothing made of ${st.part} yet: its print or its cut opens a drawer here, and a kept slice or toolpath of it is listed to file what a piece made elsewhere shows.` : "";
        $("feedback-empty").textContent = problem || empty;
        $("feedback-empty").hidden = !(problem || empty);
        $("feedback-piece-row").hidden = !st.pieces.length;
        const sel = $("feedback-piece");
        const groups = [...new Set(st.pieces.map((x) => x.part))];
        const options = (st.chosen ? "" : `<option value="">— a piece of any part —</option>`)
            + groups.map((part) => `<optgroup label="${esc(part)}">${st.pieces.filter((x) => x.part === part)
                .map((x) => `<option value="${esc(x.key)}">${esc(x.label)}</option>`).join("")}</optgroup>`).join("");
        if (sel.dataset.drawn !== options) { sel.innerHTML = options; sel.dataset.drawn = options; }
        if (sel.value !== (st.chosen || "")) sel.value = st.chosen || "";
        $("feedback-piece-said").textContent = st.whole ? drawerSaid(st.whole) : p && p.record ? "no drawer yet: one is opened as something is filed" : "";
        const shown = !!(p && r);
        $("feedback-measure-row").hidden = !shown;
        $("feedback-note-row").hidden = !shown;
        renderMade(st.whole);
        renderStopped(shown && printed() ? st.whole : null);
        renderMeasure(shown ? r : null);
        renderSeen(shown && printed() ? r : null);
        renderFiled();
    }
    function drawerSaid(d) {
        const bits = [];
        if (d.variant) bits.push(`variant ${d.variant.slice(0, 8)}`);
        const params = Object.entries(d.params || {});
        if (params.length) bits.push(params.slice(0, 4).map(([k, v]) => `${k} ${v}`).join(", ") + (params.length > 4 ? "…" : ""));
        if (d.job) bits.push(`job ${d.job.outcome}${STOPPED.includes(d.job.outcome) ? ` ${stoppedSaid(d.job.stopped)}` : ""}${d.job.reason ? ` (${d.job.reason})` : ""}`);
        if (d.stl_sha256) bits.push(`STL ${d.stl_sha256.slice(0, 10)}`);
        return bits.join(" · ");
    }
    // How the piece was made, from its slice's record and its job: its values -- a
    // variant's, the drawer's own, or the part's own -- how its start levelled, its skirt,
    // brim and raft, in the Print window's words (first_layer.made), and what the board
    // said of its levelling as the print began (devices.levelled_by). A cut says its
    // values alone.
    function madeSaid(d) {
        const bits = [];
        const params = Object.keys(d.params || {}).length;
        bits.push(d.variant ? `variant ${d.variant.slice(0, 8)}` : params ? "the values drawn" : "the part's own values");
        if (!d.slice) return bits.join(" · ");
        const how = madeOf(d.slice.settings);
        bits.push(...[how.levelling, how.skirt, how.adhesion].filter(Boolean));
        const said = d.job && d.job.levelled;
        if (said) {
            const heard = [];
            if (said.leveling_on != null) heard.push(`levelling ${said.leveling_on ? "on" : "OFF"}`);
            if (said.probe_offset) heard.push(`probe offset Z ${said.probe_offset.z}`);
            if (said.mesh_range != null) heard.push(`mesh range ${mmText(said.mesh_range)}`);
            if (said.area) heard.push(`probed x ${said.area.min.x}..${said.area.max.x}, y ${said.area.min.y}..${said.area.max.y}`);
            bits.push(`the board said: ${heard.join(", ")}`);
        } else if (d.job && how.levelling) bits.push("the board said nothing of its levelling");
        return bits.join(" · ");
    }
    function renderMade(d) {
        $("feedback-made-row").hidden = !d;
        $("feedback-made-said").textContent = d ? madeSaid(d) : "";
    }
    // Why a try is not offered on the drawer `d`'s piece (first_layer.tryRefused), or null.
    const refusedTry = (d, how) => tryRefused(how, d.slice && d.slice.settings, d.declared, d.part);
    // A print that stopped: where, and what to try, each slicing the piece again.
    function stoppedOf(d) { return d && d.job && STOPPED.includes(d.job.outcome) ? d.job : null; }
    function renderStopped(d) {
        const job = stoppedOf(d);
        $("feedback-stopped-row").hidden = !job;
        if (!job) return;
        $("feedback-stopped-said").textContent = `${job.outcome} ${stoppedSaid(job.stopped)}; a fault seen is filed there. Try, sliced again:`;
        for (const how of Object.keys(TRIES)) setReason($(`feedback-try-${how}`), refusedTry(d, how), tryTip(how));
    }
    async function tryAgain(how) {
        const job = stoppedOf(st.whole);
        if (!job) return refuse(`try ${how}: ${st.whole ? "this piece's print did not stop part way" : "choose a print that stopped"}`);
        const why = refusedTry(st.whole, how);
        if (why) return refuse(`try ${how}: ${why}`);
        if (!retry) return refuse(`try ${how}: nothing here slices a piece again`);
        const answer = await retry(st.whole, how);
        return answer.refused ? refuse(`try ${how}: ${answer.refused}`) : tell(`${st.part} sliced again with ${words(TRIES[how].choice)}: ${answer.said}`);
    }
    // A print's rows: a feature each, as its plan names it; a cut's one field of its sizes.
    function renderMeasure(r) {
        const printer = !!r && printed();
        const box = $("feedback-measure-plan");
        box.hidden = !printer;
        $("feedback-measure").hidden = !r || printer;
        $("feedback-tune-apply").hidden = $("feedback-tune-undo").hidden = !printer;
        $("feedback-tune-history").hidden = true;
        if (!r) { box.dataset.for = ""; return; }
        if (printer) {
            const features = dims(), tolerance = st.dims && st.dims.tolerance;
            const rows = `${st.chosen}|${features.map((f) => f.name).join(",")}`;
            if (box.dataset.for !== rows) {
                box.dataset.for = rows;
                box.innerHTML = features.map((f) => `<label class="measure-row" data-feature="${esc(f.name)}" title="${esc(f.words)}: ${f.jaw} jaws">${esc(f.name)} <span class="s">${mmText(f.designed)}</span>
                    <input class="measure-read" data-feature="${esc(f.name)}" size="9" spellcheck="false" placeholder="${f.designed}" title="What ${esc(f.name)} reads, mm: ${esc(f.words)}, ${f.jaw} jaws; repeats a space apart; Enter keeps"><span class="measure-check s"></span></label>`).join(" ");
                changed();
            }
            for (const f of features) {
                const check = box.querySelector(`.measure-row[data-feature="${CSS.escape(f.name)}"] .measure-check`);
                if (check) checkSaid(check, f, tolerance);
            }
            const entry = st.whole && st.whole.tuning;
            const apply = tuning.canApply(entry), undo = tuning.canUndo(entry);
            const drawn = !!st.whole;
            setReason($("feedback-tune-apply"), !drawn ? "nothing is filed of this piece yet" : apply.ok ? null : apply.why, apply.ok ? apply.why : "Take the last turn's changes into the next slices of the printer that made this piece");
            setReason($("feedback-tune-undo"), !drawn ? "nothing is filed of this piece yet" : undo.ok ? null : undo.why, undo.ok ? undo.why : "Drop the last turn, and what it applied");
            const lines = tuning.historyLines(entry), history = $("feedback-tune-history");
            history.hidden = !lines.length;
            history.textContent = lines.join("\n");
            const held = entry ? Object.entries(entry.document.settings) : [];
            const where = (st.whole && st.whole.machine) || r.printer;
            $("feedback-measure-said").textContent = `of ${features.length} features ${r.plan ? "its plan names" : "of its box"}`
                + (tolerance ? ` · tolerance ± ${tolerance.value.toFixed(2)} mm, ${tolerance.source === "default" ? "a default" : tolerance.said}` : "")
                + (held.length ? ` · ${where.path || where.name} holds ${held.map(([k, h]) => `${k} ${h.unit === "%" ? `${h.value}%` : signed(h.value)}`).join(", ")}` : "");
            $("feedback-measure-said").title = tolerance ? `Each reading is checked within ± ${tolerance.value} mm of its design: ${tolerance.said}` : "";
            return;
        }
        const names = (r.features || []).map((f) => f.name);
        $("feedback-measure").placeholder = `${names.join(" × ")} mm`;
        const kept = st.whole && st.whole.allowance;
        $("feedback-measure-said").textContent = `of ${(r.features || []).map((f) => `${f.name} ${mmText(f.size).replace(" mm", "")}`).join(" × ")} mm designed`
            + (kept ? ` · ${kept.router}'s tool ${signed(kept.value)} mm` : "");
    }
    // A dimension's newest reading beside its row: what was read, how far from its design,
    // within its tolerance or outside it.
    function checkSaid(el, f, tolerance) {
        const reading = f.reading, c = reading && reading.checked;
        el.classList.toggle("within", !!c && c.within);
        el.classList.toggle("outside", !!c && !c.within);
        if (!c) { el.textContent = ""; el.title = ""; return; }
        el.textContent = `${c.measured.toFixed(2)} ${signed2(c.deviation)} ${c.within ? "✓" : "✗"}`;
        el.title = `Read ${stamp(reading.at)} (${reading.filed}${reading.made ? `, ${reading.made}` : ""}): ${c.measured.toFixed(3)} mm against ${c.designed} designed, ${signed2(c.deviation)} mm, ${c.within ? "within" : "outside"} ± ${c.tolerance} mm`
            + (tolerance && c.tolerance_from === tolerance.source ? ` (${tolerance.said})` : ` (${c.tolerance_from === "default" ? "a default" : `${c.tolerance_from}'s`})`);
    }
    const signed2 = (v) => `${v >= 0 ? "+" : ""}${v.toFixed(2)}`;
    function renderSeen(r) {
        const row = $("feedback-seen-row");
        row.hidden = !r;
        if (!r) return;
        if (!st.faults) {
            api("/slicer/faults").then((a) => { st.faults = a.faults; render(); }).catch(() => {});
            return;
        }
        const box = $("feedback-seen-faults");
        if (box.dataset.for !== st.chosen) {
            box.dataset.for = st.chosen;
            box.innerHTML = st.faults.map((f) => `<label class="seen-fault" title="${esc(f.name)}: ${esc(f.looks_like)}">${esc(f.name)}
                <select class="seen-read" data-fault="${esc(f.id)}">${["none", "slight", "clear", "bad"].map((w, i) => `<option value="${i}">${w}</option>`).join("")}</select></label>`).join(" ");
            changed();
        }
        const applies = tuning.appliesOf(r);
        const looks = (st.whole && st.whole.filed.filter((f) => f.kind === "look" && !f.undone)) || [];
        const job = stoppedOf(st.whole);
        $("feedback-seen-said").textContent = (looks.length
            ? `${looks.length} look${looks.length > 1 ? "s" : ""} filed of this piece`
            : `what the piece shows${applies ? `, for ${applies.filament}` : ""}`)
            + (job && job.stopped ? `; filed ${stoppedSaid(job.stopped)}` : "");
    }
    function renderFiled() {
        const list = $("feedback-filed"), filed = (st.whole && st.whole.filed) || [];
        list.hidden = !filed.length;
        // A measured filing's checks under it, each within its tolerance or outside it; a
        // check alone already says them in its line.
        const checks = (f) => (f.made && f.checked && f.checked.length ? `<div class="feedback-checks">${f.checked.map((c) => (
            `<div class="${c.within ? "within" : "outside"}">${esc(c.name)} ${c.measured.toFixed(2)} mm against ${c.designed.toFixed(2)} designed, ${signed2(c.deviation)}: ${c.within ? "within" : "outside"} ± ${c.tolerance.toFixed(2)}${c.tolerance_from === "default" ? " (a default)" : ""}</div>`
        )).join("")}</div>` : "");
        list.innerHTML = filed.map((f) => `<li class="${f.undone ? "undone" : ""}" title="${f.undone ? `undone ${stamp(f.undone)}` : esc(f.kind)}">${stamp(f.at)} · ${esc(f.kind)}${f.made ? ` (${esc(f.made)})` : ""}: ${esc(f.said)}${checks(f)}</li>`).join("");
    }
    // New rows: the ring writes its addresses on them again.
    function changed() { if (window.apothecaryRing && window.apothecaryRing.refreshAddresses) window.apothecaryRing.refreshAddresses(); }

    // ---- filing --------------------------------------------------------------------------
    function measuredSizes(text, count) {
        const words = String(text || "").trim().split(/\s*(?:×|x|\*|,|\s)\s*/i).filter(Boolean);
        if (!words.length || words.length > count) return null;
        const sizes = words.map((w) => (w === "-" ? null : Number(w)));
        if (sizes.some((v) => v !== null && !(Number.isFinite(v) && v > 0))) return null;
        while (sizes.length < count) sizes.push(null);
        return sizes;
    }
    function planReads() {
        const out = {};
        for (const field of $("feedback-measure-plan").querySelectorAll("input.measure-read")) {
            const read = tuning.parseReads(field.value);
            if (read === null) return { bad: field.dataset.feature };
            if (read.length) out[field.dataset.feature] = read;
        }
        return { readings: out };
    }
    const typedSomething = () => printed()
        ? [...$("feedback-measure-plan").querySelectorAll("input.measure-read")].some((f) => f.value.trim())
        : !!$("feedback-measure").value.trim();
    const seenSomething = () => printed()
        && [...$("feedback-seen-faults").querySelectorAll("select.seen-read")].some((el) => el.value !== "0");
    const noPiece = (what) => refuse(`${what}: ${st.part ? `choose a piece of ${st.part}` : "choose a part: a piece's ring, Part › View › Feedback"}`);

    async function filed(path, body, what) {
        let id, answer;
        try { id = await drawerOf(); answer = await post(`${at()}/drawers/${encodeURIComponent(id)}/${path}`, body); }
        catch (e) { return refuse(`${what}: ${e.message}`); }
        st.whole = answer;
        st.dims = answer.dimensions || st.dims;
        await load();
        return answer;
    }
    async function keepMeasured() {
        const r = record();
        if (!r) return noPiece("measure");
        if (!printed()) {
            const names = (r.features || []).map((f) => f.name);
            const sizes = measuredSizes($("feedback-measure").value, names.length);
            if (!sizes) return refuse(`measure: type what the piece measures, ${names.join(" × ")} in mm (- for one not measured)`);
            const answer = await filed("measured", { readings: Object.fromEntries(names.map((n, i) => [n, sizes[i]])) }, "measure");
            if (answer.refused) return answer;
            $("feedback-measure").value = "";
            return tell(`${answer.said}: filed in ${st.part}'s drawer, and kept for ${answer.allowance.router}, whose next toolpaths take it`);
        }
        const read = planReads();
        if (read.bad) return refuse(`measure: ${read.bad} is not sizes in mm, a space apart`);
        if (!Object.keys(read.readings).length) return refuse(`measure: read one of ${dims().map((f) => f.name).join(", ")}, in mm`);
        const answer = await filed("measured", { readings: read.readings }, "measure");
        if (answer.refused) return answer;
        for (const field of $("feedback-measure-plan").querySelectorAll("input.measure-read")) field.value = "";
        // A reading of a piece the printer's last turn already reads is a check alone.
        return tell(`${answer.turn ?? "a check"} filed in ${st.part}'s drawer, for ${answer.machine.path}: ${answer.said}`);
    }
    async function keepSeen() {
        if (!record() || !printed()) return noPiece("seen");
        const choices = [...$("feedback-seen-faults").querySelectorAll("select.seen-read")].map((el) => [el.dataset.fault, el.value]);
        const answer = await filed("seen", { seen: tuning.seenOf(choices) }, "seen");
        if (answer.refused) return answer;
        for (const el of $("feedback-seen-faults").querySelectorAll("select.seen-read")) el.value = "0";
        return tell(`${answer.look} filed in ${st.part}'s drawer, for ${answer.machine.path}: ${answer.said}`);
    }
    async function keepNote() {
        if (!record()) return noPiece("note");
        const note = $("feedback-note").value.trim();
        if (!note) { $("feedback-note").focus(); return tell(`type a note on the piece, then Keep note`); }
        const answer = await filed("note", { note }, "note");
        if (answer.refused) return answer;
        $("feedback-note").value = "";
        return tell(`Noted in ${st.part}'s drawer ${answer.id}`);
    }
    async function tune(verb) {
        const said = verb === "apply" ? "Take turn" : "Undo turn";
        if (!record() || !printed()) return noPiece(said);
        if (!st.whole) return refuse(`${said}: nothing is filed of this piece yet`);
        const entry = st.whole.tuning;
        const can = verb === "apply" ? tuning.canApply(entry) : tuning.canUndo(entry);
        if (!can.ok) return refuse(`${said}: ${can.why}`);
        let answer;
        try { answer = await post(`${at()}/drawers/${encodeURIComponent(st.whole.id)}/tune/${verb}`); }
        catch (e) { return refuse(`${said}: ${e.message}`); }
        st.whole = answer;
        await load();
        const where = answer.machine.path;
        return tell(verb === "apply"
            ? `Taken for ${where}'s next slices: ${answer.applied.map((c) => `${c.setting} ${tuning.settingText(c.after, c.unit)}`).join(", ")}`
            : `${answer.undone} undone: ${where}'s next slices take what the turns before it applied`);
    }
    // Feedback › Measure: what is read filed, as Keep does; a fault chosen under seen and
    // nothing read, the look filed, as Keep look does; with neither, the first field.
    function measureVerb() {
        if (typedSomething()) return keepMeasured();
        if (seenSomething()) return keepSeen();
        const r = record();
        if (!r) return noPiece("measure");
        const first = printed() ? $("feedback-measure-plan").querySelector("input.measure-read") : $("feedback-measure");
        if (first) first.focus();
        const names = printed() ? dims().map((f) => f.name) : (r.features || []).map((f) => f.name);
        return tell(printed()
            ? `read the piece: ${names.join(", ")}, each in mm in its row, then Keep`
            : `type what the piece measures, ${names.join(" × ")} in mm, then Keep`);
    }

    // A dimension of the piece chosen picked, as a click on it in the world does: its row
    // marked, its field given the caret, and what it is said.
    function pick(name) {
        const box = $("feedback-measure-plan");
        const f = dims().find((d) => d.name === name);
        for (const row of box.querySelectorAll(".measure-row")) row.classList.toggle("picked", row.dataset.feature === name);
        const p = piece();
        if (!p) return noPiece(`measure ${name}`);
        if (!f) return refuse(`${name}: ${p.label} names ${dims().map((d) => d.name).join(", ") || "nothing to measure"}${st.dims && st.dims.why ? ` (${st.dims.why})` : ""}`);
        const field = box.querySelector(`input.measure-read[data-feature="${CSS.escape(name)}"]`);
        if (field) { field.focus(); field.scrollIntoView({ block: "nearest" }); }
        const c = f.reading && f.reading.checked;
        const was = c ? `; last read ${c.measured.toFixed(2)} mm, ${signed2(c.deviation)}, ${c.within ? "within" : "outside"} ± ${c.tolerance.toFixed(2)}` : "";
        return tell(`${name}, ${f.words}: designed ${mmText(f.designed)}${was}. Type what calipers read of ${st.part}'s piece in its row under measured, then Enter`);
    }

    // Enter in a dimension's row keeps what is typed in the rows, as Keep does.
    function keepOnEnter(ev) {
        if (ev.key === "Enter" && ev.target.matches("input.measure-read")) { ev.preventDefault(); keepMeasured(); }
    }
    $("feedback-measure-plan").addEventListener("keydown", keepOnEnter);
    $("feedback-piece").onchange = () => choose($("feedback-piece").value || null);
    $("feedback-measure-keep").onclick = () => keepMeasured();
    $("feedback-seen-keep").onclick = () => keepSeen();
    $("feedback-note-keep").onclick = () => keepNote();
    $("feedback-note").addEventListener("keydown", (ev) => { if (ev.key === "Enter") { ev.preventDefault(); keepNote(); } });
    $("feedback-try-probe").onclick = () => tryAgain("probe");
    $("feedback-try-brim").onclick = () => tryAgain("brim");
    $("feedback-try-raft").onclick = () => tryAgain("raft");
    $("feedback-tune-apply").onclick = () => tune("apply");
    $("feedback-tune-undo").onclick = () => tune("undo");
    // A slice or a toolpath kept, a job begun or ended (widgets/machine.js): the pieces listed
    // again, so a piece just made is there to choose and its drawer says how its job ended.
    const again = () => { if (st.part || st.pieces.length) load(); };
    window.addEventListener("apothecary:sliced", again);
    window.addEventListener("apothecary:jobs-changed", again);
    render();

    return {
        async show(part, { drawer = null, job = null } = {}) {
            if (part !== st.part) { st.part = part || null; st.chosen = null; st.whole = null; }
            st.want = drawer || job ? { drawer, job } : null;
            await load();
            return piece();
        },
        async verb(action) {
            if (action === "feedback:measure") return measureVerb();
            if (action === "feedback:note") return keepNote();
            if (action === "feedback:tune-apply") return tune("apply");
            if (action === "feedback:tune-undo") return tune("undo");
            if (action === "feedback:try-probe") return tryAgain("probe");
            if (action === "feedback:try-brim") return tryAgain("brim");
            if (action === "feedback:try-raft") return tryAgain("raft");
            return null;
        },
        pick,
        part: () => st.part,
        drawer: () => (st.whole ? st.whole.id : null),
        dimensions: () => st.dims,
        redraw: () => load(),
        pairs() {
            const out = [[$("feedback-measure-keep"), "feedback:measure"], [$("feedback-measure"), "feedback:measure"],
                [$("feedback-seen-keep"), "feedback:measure"], [$("feedback-note"), "feedback:note"], [$("feedback-note-keep"), "feedback:note"],
                [$("feedback-tune-apply"), "feedback:tune-apply"], [$("feedback-tune-undo"), "feedback:tune-undo"],
                [$("feedback-try-probe"), "feedback:try-probe"], [$("feedback-try-brim"), "feedback:try-brim"],
                [$("feedback-try-raft"), "feedback:try-raft"]];
            for (const el of root.querySelectorAll("input.measure-read, select.seen-read")) out.push([el, "feedback:measure"]);
            return out;
        },
        destroy() {
            window.removeEventListener("apothecary:sliced", again);
            window.removeEventListener("apothecary:jobs-changed", again);
            root.innerHTML = "";
        },
    };
}
