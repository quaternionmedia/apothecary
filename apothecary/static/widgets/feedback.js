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
 * Under the piece chosen: a print's features to read, a row each as its slice's plan names
 * them (or its box), with Keep -- its printer's next turn of its tuning -- and Take turn
 * and Undo turn for that printer, the filament and process the piece used; each fault seen,
 * none to bad, with Keep look -- the printer's next look; a cut's sizes in one field, with
 * Keep -- the router's tool allowance; a note, with Keep note; and what the drawer holds,
 * in the order it was filed, an undone filing struck through. Nothing here sends anything
 * to a machine.
 *
 * mountFeedback(root, { base, say }) -> handle
 *   show(part, { drawer, job })   this part's cabinet, the drawer named (or that job's) chosen
 *   verb(action)                   feedback:measure, feedback:note, feedback:tune-apply,
 *                                  feedback:tune-undo: { said } or { refused }
 *   part()                         the part shown, or null
 *   redraw()                       its rows again, as the window comes to the front
 *   pairs()                        each control by the ring verb it is, for the addresses
 * `say(text, kind)` is the page's status line, "error" for a refusal.
 */

import { esc } from "/static/board_text.js";
import { mm as mmText, stamp } from "/static/format.js";
import { setReason } from "/static/can.js";
import * as tuning from "/static/tuning.js";

export const VERBS = ["feedback:measure", "feedback:note", "feedback:tune-apply", "feedback:tune-undo"];

export function mountFeedback(root, { base = "", say = null } = {}) {
    // part: shown; pieces: every part's drawers then its loose kept files, the part shown's
    // first ({ key, part, label, drawer?, record?, made });
    // chosen: the key of the piece chosen; whole: the drawer chosen, whole, as the server said it.
    const st = { part: null, pieces: [], chosen: null, whole: null, faults: null, asking: 0, want: null };

    root.innerHTML = `<div class="cards feedback"><div class="card wide" id="feedback-card">
        <div class="k"><span id="feedback-title">Feedback</span></div>
        <p class="s" id="feedback-empty"></p>
        <div class="row" id="feedback-piece-row" hidden><label for="feedback-piece">piece</label>
            <select id="feedback-piece" title="Each piece made of the part, the newest first, then each kept slice or toolpath of it made elsewhere: the drawer its feedback is filed in"></select>
            <span class="s" id="feedback-piece-said"></span>
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
        if (p && p.drawer) {
            try { st.whole = await api(`${at()}/drawers/${encodeURIComponent(p.drawer.id)}`); }
            catch (e) { render(`drawer ${p.drawer.id}: ${e.message}`); return; }
        }
        render();
    }
    // The drawer the piece chosen is filed in: its own, else one opened for its kept file.
    async function drawerOf() {
        const p = piece();
        if (!p) throw new Error(`choose a piece of ${st.part}`);
        if (p.drawer) return p.drawer.id;
        const opened = await post(`${at()}/drawers`, { file_id: p.record.file_id });
        st.want = { drawer: opened.id };
        p.drawer = opened; p.key = `drawer:${opened.id}`; st.chosen = p.key; st.whole = opened;
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
        renderMeasure(shown ? r : null);
        renderSeen(shown && printed() ? r : null);
        renderFiled();
    }
    function drawerSaid(d) {
        const bits = [];
        if (d.variant) bits.push(`variant ${d.variant.slice(0, 8)}`);
        const params = Object.entries(d.params || {});
        if (params.length) bits.push(params.slice(0, 4).map(([k, v]) => `${k} ${v}`).join(", ") + (params.length > 4 ? "…" : ""));
        if (d.job) bits.push(`job ${d.job.outcome}${d.job.reason ? ` (${d.job.reason})` : ""}`);
        if (d.stl_sha256) bits.push(`STL ${d.stl_sha256.slice(0, 10)}`);
        return bits.join(" · ");
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
            const features = tuning.planOf(r);
            if (box.dataset.for !== st.chosen) {
                box.dataset.for = st.chosen;
                box.innerHTML = features.map((f) => `<label class="measure-row" title="${esc(f.words)}: ${f.jaw} jaws">${esc(f.name)} <span class="s">${mmText(f.nominal)}</span>
                    <input class="measure-read" data-feature="${esc(f.name)}" size="9" spellcheck="false" placeholder="${f.nominal}" title="What ${esc(f.name)} reads, mm: ${esc(f.words)}, ${f.jaw} jaws; repeats a space apart"></label>`).join(" ");
                changed();
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
                + (held.length ? ` · ${where.path || where.name} holds ${held.map(([k, h]) => `${k} ${h.unit === "%" ? `${h.value}%` : signed(h.value)}`).join(", ")}` : "");
            return;
        }
        const names = (r.features || []).map((f) => f.name);
        $("feedback-measure").placeholder = `${names.join(" × ")} mm`;
        const kept = st.whole && st.whole.allowance;
        $("feedback-measure-said").textContent = `of ${(r.features || []).map((f) => `${f.name} ${mmText(f.size).replace(" mm", "")}`).join(" × ")} mm designed`
            + (kept ? ` · ${kept.router}'s tool ${signed(kept.value)} mm` : "");
    }
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
        $("feedback-seen-said").textContent = looks.length
            ? `${looks.length} look${looks.length > 1 ? "s" : ""} filed of this piece`
            : `what the piece shows${applies ? `, for ${applies.filament}` : ""}`;
    }
    function renderFiled() {
        const list = $("feedback-filed"), filed = (st.whole && st.whole.filed) || [];
        list.hidden = !filed.length;
        list.innerHTML = filed.map((f) => `<li class="${f.undone ? "undone" : ""}" title="${f.undone ? `undone ${stamp(f.undone)}` : esc(f.kind)}">${stamp(f.at)} · ${esc(f.kind)}${f.made ? ` (${esc(f.made)})` : ""}: ${esc(f.said)}</li>`).join("");
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
        if (!Object.keys(read.readings).length) return refuse(`measure: read one of ${tuning.planOf(r).map((f) => f.name).join(", ")}, in mm`);
        const answer = await filed("measured", { readings: read.readings }, "measure");
        if (answer.refused) return answer;
        for (const field of $("feedback-measure-plan").querySelectorAll("input.measure-read")) field.value = "";
        return tell(`${answer.turn} filed in ${st.part}'s drawer, for ${answer.machine.path}: ${answer.said}`);
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
        const names = printed() ? tuning.planOf(r).map((f) => f.name) : (r.features || []).map((f) => f.name);
        return tell(printed()
            ? `read the piece: ${names.join(", ")}, each in mm in its row, then Keep`
            : `type what the piece measures, ${names.join(" × ")} in mm, then Keep`);
    }

    $("feedback-piece").onchange = () => choose($("feedback-piece").value || null);
    $("feedback-measure-keep").onclick = () => keepMeasured();
    $("feedback-seen-keep").onclick = () => keepSeen();
    $("feedback-note-keep").onclick = () => keepNote();
    $("feedback-note").addEventListener("keydown", (ev) => { if (ev.key === "Enter") { ev.preventDefault(); keepNote(); } });
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
            return null;
        },
        part: () => st.part,
        drawer: () => (st.whole ? st.whole.id : null),
        redraw: () => load(),
        pairs() {
            const out = [[$("feedback-measure-keep"), "feedback:measure"], [$("feedback-measure"), "feedback:measure"],
                [$("feedback-seen-keep"), "feedback:measure"], [$("feedback-note"), "feedback:note"], [$("feedback-note-keep"), "feedback:note"],
                [$("feedback-tune-apply"), "feedback:tune-apply"], [$("feedback-tune-undo"), "feedback:tune-undo"]];
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
