/* Loops: the heater loops of the printer whose Machine is open (docs/control-loops.md,
 * "The Loops window"). A window of the Machine's group, closed until asked for.
 *
 * For the loop chosen -- hotend 0 or the bed -- it shows what the board holds (its gains
 * as M503 read them back, and when), the controller designed beside them and the rule it
 * was designed by; the experiment to run, its ceiling and its longest time typed by a
 * person every time, its progress as the server tells it; the newest kept experiment's
 * plots and figures; and Set on machine, the designed gains sent and read back. Nothing
 * here saves to the board's memory: the server refuses that unless asked by name, and
 * this window never asks.
 *
 * Everything it shows is the server's: the rules (GET /firmware/loops/rules), what each
 * experiment takes (GET /firmware/loops/kinds), whether one of the figures typed would
 * start (POST /firmware/printers/loops/can-start: the machine's verdict, then the plan's),
 * the document of a kept experiment (POST .../loops/document) and its curves (POST
 * .../loops/curves). The page computes nothing the server computes -- no margin, no fit,
 * no transfer function: loop_plots.js maps the answer's numbers onto plots and rounds a
 * figure as the document's Markdown view does. An experiment's progress comes from the
 * surfaces' stream (GET /surfaces/events?names=tune,control_loop); where the stream is not
 * open, from GET .../loops/job, once a second while one runs.
 *
 * Every button names its command in data-can and is greyed through can.js from the
 * server's answer (`can` on the board's status: tune.read, tune.start, tune.cancel,
 * tune.set), Start from the can-start answer for the figures typed. Each act is a cell of
 * Panels › Machine › Loops, and a button's title says the cell's address (addressOf).
 *
 * mountLoops(root, { base, machine, say, addressOf }) -> { load(), act(verb, as), state() }
 *   machine(): { port, name } of the open Machine, or null; say(text, kind): the page's
 *   status line; addressOf(action): the ring's address of an action, or null.
 *   act(verb, { label, tail }): a cell of the ring -- read, start, cancel, set,
 *   loop:<heater>, kind:<kind>, rule:<rule>:<kind> -- done as its control does, what it
 *   did or why it was refused said on the status line after the cell's label.
 */

import { applyCan, verdictOf } from "/static/can.js";
import { clock, heater, sentence, span } from "/static/format.js";
import { plotSvg, extent, logDomain, linearDomain, stepTicks, shown, finite } from "/static/loop_plots.js";

const esc = (v) => String(v ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const LOOPS = [["hotend", "Hotend 0"], ["bed", "Bed"]];
const POLL_MS = 1000;  // the job asked for this often while one runs and the stream is not open
const BASIS = { measured: "measured", identified: "identified", computed: "computed" };

export function mountLoops(root, { base = "", machine = () => null, say = () => {}, addressOf = () => null } = {}) {
    root.classList.add("loops-window");
    const st = {
        port: null, name: null, heater: "hotend", kind: "step",
        rules: null, rule: null, ruleKind: null, kinds: null, kindsAnswer: null,
        typed: {},          // what a person typed, by kind and heater; the ceiling and the longest time by heater
        can: null,          // the server's `can` for the port
        verdict: null,      // can-start's answer for the figures typed
        asking: null,       // the figures can-start is being asked about
        read: null,         // the last read of the board's gains, this port's
        job: null,          // the port's experiment, as last told
        heard: 0, via: null,
        experiment: null, doc: null, curves: null, docError: null, readBoard: null,
        set: null, said: null, loaded: false,
    };

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
    const post = (path, data) => api(path, { method: "POST", body: JSON.stringify(data) });
    const taught = (action) => { const at = addressOf(action); return at ? ` · ⌗${at}` : ""; };
    const loopLabel = () => (st.heater === "bed" ? "the bed" : "hotend 0");

    root.innerHTML = `<div class="loops-columns"><div class="loops-left"><div class="loops-head">
    <span class="loops-machine" aria-live="polite">—</span>
    <label>Loop <select class="loops-loop" aria-label="Loop">${LOOPS.map(([v, l]) => `<option value="${v}">${l}</option>`).join("")}</select></label>
    <label>Rule <select class="loops-rule" aria-label="Rule"></select></label>
</div>
<div class="loops-said" aria-live="polite"></div>
<section class="loops-gains" aria-label="The board and the design">
    <div class="loops-gains-table"></div>
    <div class="loops-acts">
        <button type="button" class="loops-read" data-can="tune.read">Read</button>
        <button type="button" class="loops-set" data-can="tune.set">Set on machine</button>
    </div>
    <div class="loops-set-said"></div>
</section>
<section class="loops-experiment" aria-label="An experiment">
    <div class="loops-form">
        <label>Experiment <select class="loops-kind" aria-label="Experiment"></select></label>
        <span class="loops-params"></span>
        <label>Ceiling <input type="number" class="loops-ceiling" inputmode="decimal" min="0" step="1" placeholder="°C, every time" aria-label="Ceiling (°C)"> °C</label>
        <label>Longest time <input type="number" class="loops-longest" inputmode="decimal" min="0" step="1" placeholder="s, every time" aria-label="Longest time (s)"> s</label>
    </div>
    <div class="loops-plan"></div>
    <div class="loops-acts">
        <button type="button" class="loops-start" data-can="tune.start">Start</button>
        <button type="button" class="loops-cancel" data-can="tune.cancel">Cancel</button>
        <progress class="loops-progress" max="1" value="0"></progress>
        <span class="loops-stage"></span>
    </div>
    <div class="loops-job"></div>
</section></div>
<div class="loops-right"><section class="loops-plots" aria-label="Plots"></section>
<section class="loops-figures" aria-label="Figures"></section></div></div>`;
    const $ = (cls) => root.querySelector(`.${cls}`);

    // `kind` "note" is a plain line (a state, not a failure); "error" is red.
    function tell(text, kind = "success") {
        text = sentence(text);
        st.said = text;
        const el = $("loops-said");
        el.textContent = text || "";
        el.classList.toggle("bad", kind === "error");
    }

    // --- what the server would refuse now: greyed, with its reason (can.js) --------------
    function figures() {
        const kind = (st.kinds || []).find((k) => k.kind === st.kind);
        const typed = st.typed[`${st.kind}:${st.heater}`] || {};
        const limits = st.typed[st.heater] || {};
        const out = { port: st.port, heater: st.heater, index: 0, kind: st.kind };
        const num = (v) => (v === undefined || v === null || String(v).trim() === "" ? null : Number(v));
        for (const p of kind ? kind.parameters : []) out[p.name] = num(typed[p.name] ?? p.start[st.heater]);
        // An autotune is read as the board says its lines, on no period of the job's.
        if (st.kind !== "autotune") out.sample_period_s = num(typed.sample_period_s ?? (st.kindsAnswer ? st.kindsAnswer.sample_period_s : null));
        out.ceiling_c = num(limits.ceiling_c);
        out.max_duration_s = num(limits.max_duration_s);
        for (const k of Object.keys(out)) if (out[k] === null || Number.isNaN(out[k])) delete out[k];
        return out;
    }
    const running = () => !!(st.job && st.job.running && st.job.port === st.port);
    const VERBS = ["tune.read", "tune.start", "tune.cancel", "tune.set"];
    const NO_MACHINE = "Open a printer's Machine: Loops works on the printer whose Machine is open";
    function localCan() {
        const out = { ...(st.can || {}) };
        if (!st.port) {
            for (const verb of VERBS) out[verb] = { ok: false, kind: "offline", why: "no printer's Machine is open: Loops works on the printer whose Machine is open" };
            return out;
        }
        if (!st.can) {
            for (const verb of VERBS) out[verb] = { ok: false, kind: "offline", why: `the server has not yet said what ${st.port} would take now` };
        }
        if (st.verdict && st.verdict.key === askKey()) out["tune.start"] = st.verdict.answer;
        else out["tune.start"] = { ok: false, kind: "plan", why: st.asking ? "the server is being asked whether these figures would start" : "the server has not yet said whether these figures would start" };
        // An experiment from here is this page's own news, fresher than the poll the
        // server's answer was read from.
        if (running()) out["tune.cancel"] = { ok: true, why: null, kind: null };
        if (!designed()) out["tune.set"] = { ok: false, kind: "idle", why: st.doc ? "the document designs no controller: it identified no plant" : "no controller is designed yet: a kept experiment's plant is what a rule designs for" };
        return out;
    }
    // Each button's own tip and the address of the ring's cell that does what it does,
    // composed with the server's reason by can.js.
    const BUTTONS = [
        ["loops-read", "loops:read", () => `The gains the board holds, read back (M503, report-only), for ${loopLabel()}`],
        ["loops-set", "loops:set", () => "The designed gains sent to the board (M301 or M304) and read back -- set, not saved"],
        ["loops-start", "loops:start", () => "Start the experiment, as planned above"],
        ["loops-cancel", "loops:cancel", () => "End the experiment: the heater turned off and read back"],
    ];
    function renderCan() {
        // The refusal on the window's line goes once the act it refused would be taken.
        const refused = st.refusedVerb && verdictOf(localCan(), st.refusedVerb);
        if (refused && (refused.ok || refused.why !== st.refusedWhy)) { st.refusedVerb = null; tell(""); }
        for (const [cls, action, tip] of BUTTONS) {
            const b = $(cls), at = addressOf(action);
            if (at) b.dataset.address = at; else delete b.dataset.address;
            b.dataset.tip = tip();
        }
        applyCan(root, localCan());
    }
    // The figures typed asked of the server: again when they, the port's answer for a
    // start, or the experiment running change, never on a timer.
    function askKey() {
        return JSON.stringify([figures(), st.can && st.can["tune.start"], running()]);
    }
    function askStart() {
        if (!st.port || !st.kinds) return;
        const key = askKey();
        if (st.asking === key || (st.verdict && st.verdict.key === key)) return;
        st.asking = key;
        post("/firmware/printers/loops/can-start", figures())
            .then((answer) => { if (st.asking === key) { st.verdict = { key, answer }; st.asking = null; renderPlan(); renderCan(); } })
            .catch((e) => { if (st.asking === key) { st.verdict = { key, answer: { ok: false, kind: "plan", why: e.message, plan: null } }; st.asking = null; renderPlan(); renderCan(); } });
        renderCan();
    }
    function takeCan(can) {
        if (!can) return;
        st.can = can;
        askStart();
        renderCan();
    }
    async function askCan() {
        if (!st.port) return;
        try { takeCan((await api(`/firmware/printers/info?port=${encodeURIComponent(st.port)}`)).can); } catch (e) { /* the next poll says it */ }
    }

    // --- the head: which machine, which loop, which rule ---------------------------------
    function renderHead() {
        $("loops-machine").textContent = !st.port ? "No printer's Machine is open" : st.name && st.name !== st.port ? `${st.name} · ${st.port}` : st.port;
        // With no Machine open Loops has nothing to say but how to give it one: a state, not a failure.
        if (!st.port && !st.said) tell(NO_MACHINE, "note");
        else if (st.port && st.said === NO_MACHINE) tell("");
        $("loops-loop").value = st.heater;
        $("loops-loop").title = `Which loop: hotend 0 or the bed${taught(`loops:loop:${st.heater}`)}`;
        const rule = $("loops-rule");
        if (st.rules && !rule.options.length) {
            rule.innerHTML = st.rules.map((r) => `<optgroup label="${esc(r.title)}">${r.kinds.map((k) => `<option value="${esc(r.name)}:${esc(k)}" title="${esc(`${r.source}. ${r.assumes}`)}">${esc(r.title)}, ${esc(k.toUpperCase())}</option>`).join("")}</optgroup>`).join("");
        }
        if (st.rule) rule.value = `${st.rule}:${st.ruleKind}`;
        rule.title = `The rule the controller is designed by, and its kind${taught(`loops:rule:${st.rule}:${st.ruleKind}`)}`;
    }

    // --- the board and the design ------------------------------------------------------------
    function designed() { return st.doc && st.doc.controller && st.doc.controller.designed; }
    function onBoard() {
        const doc = st.doc && st.doc.controller && st.doc.controller.on_machine;
        if (doc) return { kp: doc.kp, ki: doc.ki, kd: doc.kd, at: readAt(), from: "the document's read" };
        const label = st.heater === "bed" ? "bed" : "hotend 0";
        const got = st.read && st.read.port === st.port && st.read.gains[label];
        return got ? { kp: got.kp, ki: got.ki, kd: got.kd, at: st.read.read_at, from: "Read" } : null;
    }
    function readAt() {
        const read = st.doc && (st.doc.experiments || []).find((e) => e.kind === "read");
        return read ? read.started_at : st.read ? st.read.read_at : null;
    }
    const when = (iso) => (iso ? clock(iso) : "—");
    function ruleTitle(g) {
        if (!g) return "";
        if (g.rule === "firmware_autotune") return "the firmware's own autotune";
        const r = (st.rules || []).find((x) => x.name === g.rule);
        return r ? `${r.title}, ${st.doc && st.ruleKind ? st.ruleKind.toUpperCase() : ""}` : g.rule || "";
    }
    function renderGains() {
        const board = onBoard(), d = designed();
        const cell = (g, k) => (g ? `<td data-gain="${k}" data-value="${esc(String(g[k]))}">${esc(shown(g[k]))}</td>` : "<td>—</td>");
        const units = { kp: "power per °C", ki: "power per °C·s", kd: "power·s per °C" };
        $("loops-gains-table").innerHTML = `<table class="loops-table"><thead><tr><th scope="col"></th>
<th scope="col" data-col="board">On the board${board ? ` <span class="loops-when" title="When the board answered M503">read ${esc(when(board.at))}</span>` : ""}</th>
<th scope="col" data-col="designed">Designed${d ? ` <span class="loops-rule-said">${esc(ruleTitle(d))}</span>` : ""}</th></tr></thead>
<tbody>${["kp", "ki", "kd"].map((k) => `<tr><th scope="row" title="${esc(units[k])}">${k[0].toUpperCase()}${k.slice(1)}</th>${cell(board, k)}${cell(d, k)}</tr>`).join("")}</tbody></table>
${board ? "" : `<p class="loops-note">The board's gains are not read yet: Read asks it (M503, report-only).</p>`}`;
        const s = st.set;
        $("loops-set-said").innerHTML = s && s.port === st.port
            ? `<span>Sent <code>${esc(s.sent)}</code>; read back ${s.read_back ? `<code>P${esc(shown(s.read_back.kp))} I${esc(shown(s.read_back.ki))} D${esc(shown(s.read_back.kd))}</code>` : "nothing for this loop"}:</span> <span class="${s.matches ? "ok" : "bad"}" data-matches="${s.matches}">${s.matches ? "the board holds what was sent" : "the board does not hold what was sent"}</span>; set, not saved.`
            : "";
    }

    // --- the experiment --------------------------------------------------------------------
    function renderForm() {
        const kinds = st.kinds || [];
        const sel = $("loops-kind");
        if (kinds.length && sel.options.length !== kinds.length) sel.innerHTML = kinds.map((k) => `<option value="${esc(k.kind)}">${esc(k.label)}</option>`).join("");
        sel.value = st.kind;
        sel.title = `Which experiment${taught(`loops:kind:${st.kind}`)}`;
        const kind = kinds.find((k) => k.kind === st.kind);
        const typed = st.typed[`${st.kind}:${st.heater}`] || {};
        const period = st.kindsAnswer ? st.kindsAnswer.sample_period_s : 1;
        const params = [...(kind ? kind.parameters : []), ...(st.kind === "autotune" ? [] : [{ name: "sample_period_s", label: "Sample period", unit: "s", start: { hotend: period, bed: period } }])];
        $("loops-params").innerHTML = params.map((p) => {
            const value = typed[p.name] ?? p.start[st.heater];
            return `<label>${esc(p.label)} <input type="number" class="loops-param" data-param="${esc(p.name)}" inputmode="decimal" step="any" value="${esc(value)}" aria-label="${esc(p.label)}${p.unit ? ` (${esc(p.unit)})` : ""}">${p.unit ? ` ${esc(p.unit)}` : ""}</label>`;
        }).join("");
        const limits = st.typed[st.heater] || {};
        $("loops-ceiling").value = limits.ceiling_c ?? "";
        $("loops-longest").value = limits.max_duration_s ?? "";
        const cap = st.kindsAnswer ? st.kindsAnswer.caps[st.heater] : null;
        $("loops-ceiling").title = `No reading may pass it; at most ${cap ?? "the cap"} °C for ${loopLabel()}. Typed every time: the server takes none by default`;
        $("loops-longest").title = `The experiment ends when this has passed, at most ${st.kindsAnswer ? st.kindsAnswer.max_duration_s : "7200"} s. Typed every time: the server takes none by default`;
    }
    function renderPlan() {
        const v = st.verdict && st.verdict.answer;
        const el = $("loops-plan");
        const plan = v && v.plan;
        if (!plan) { el.innerHTML = v && !v.ok ? `<span class="loops-why" data-kind="${esc(v.kind)}">${esc(v.why)}</span>` : ""; return; }
        el.innerHTML = plan.autotune
            ? `Sends <code>${esc(plan.autotune)}</code> and watches it; ends by ${esc(plan.max_duration_s)} s or at a reading over ${esc(plan.ceiling_c)} °C.`
            : `Sets ${plan.changes.map(([t, target]) => `${esc(target)} °C at ${esc(t)} s`).join(", ")}; ends at ${esc(plan.end_s)} s, by ${esc(plan.max_duration_s)} s at the latest, or at a reading over ${esc(plan.ceiling_c)} °C. Reads every ${esc(plan.sample_period_s)} s.`;
    }
    function renderJob() {
        const j = st.job && st.job.port === st.port ? st.job : null;
        root.dataset.heard = String(st.heard);
        root.dataset.via = st.via || "";
        const bar = $("loops-progress");
        bar.value = j && finite(j.progress) ? j.progress : 0;
        bar.hidden = !j;
        $("loops-stage").textContent = j ? `${j.what}: ${j.stage}${j.running ? `, ${Math.round((j.progress || 0) * 100)} %` : ""}` : "";
        const el = $("loops-job");
        if (!j) { el.innerHTML = ""; return; }
        const line = [];
        if (j.reading !== null && j.reading !== undefined) line.push(`reading ${esc(heater(j.reading, j.target))}, power ${esc(j.power ?? "—")}`);
        line.push(`${esc(span(j.elapsed_s))} of ${esc(span(j.max_duration_s))} at the longest, ceiling ${esc(j.ceiling_c)}°`);
        if (!j.running) {
            line.push(`<span class="${j.outcome === "done" ? "ok" : "bad"}" data-outcome="${esc(j.outcome)}">${esc(j.outcome)}${j.error ? `: ${esc(j.error)}` : ""}</span>`);
            if (j.heater_off) line.push(`<span data-heater-off>${esc(j.heater_off)}</span>`);
        }
        el.innerHTML = line.join("; ");
    }

    // --- the newest kept experiment: its plots and its figures -----------------------------
    function series(name, cls, xs, ys, label, dashed = false) { return xs && ys ? { name, cls, xs, ys, label, dashed } : null; }
    function renderPlots() {
        const el = $("loops-plots");
        const c = st.curves;
        if (!st.experiment) { el.innerHTML = `<p class="loops-note">No experiment of ${loopLabel()} is kept for this machine: start one above, and its plots and figures are here.</p>`; return; }
        if (st.docError) { el.innerHTML = `<p class="loops-note bad" data-error>The server could not make the document of ${esc(st.experiment)}: ${esc(st.docError)}</p>`; return; }
        if (!c) { el.innerHTML = `<p class="loops-note">Asking the server for ${esc(st.experiment)}'s document…</p>`; return; }
        const out = [];
        const kind = st.doc ? (st.doc.experiments[0] || {}).kind : null;
        if (!st.doc.plant) {
            out.push(`<p class="loops-note bad" data-no-plant>The server identified no plant from ${esc(st.experiment)}${kind === "autotune" ? ": an autotune's gains are the firmware's own, read off its relay" : ": its document carries none"}, so there are no curves of a loop to draw.</p>`);
        }
        const step = c.step;
        if (step) {
            const s = [series("target", "target", step.t, step.target, "target", true), series("measured", "measured", step.t, step.measured, "measured"),
                series("model_designed", "designed", step.model_designed_t, step.model_designed, "model, designed"),
                series("model_on_machine", "on-machine", step.model_on_machine_t, step.model_on_machine, "model, board's gains")].filter(Boolean);
            const [lo, hi] = extent(s.map((x) => x.ys)) || [0, 1];
            out.push(plotSvg({ name: "step", title: "The measured temperature beside the model's step through the same targets",
                x: { domain: linearDomain(...(extent([step.t]) || [0, 1])), label: "time", unit: "s" }, y: { domain: linearDomain(lo, hi), label: "temperature", unit: "°C" }, series: s }));
        }
        const bode = c.bode || {}, names = Object.keys(bode), m = c.margins || {};
        if (names.length) {
            const any = bode[names[0]];
            const xdom = logDomain(any.w[0], any.w[any.w.length - 1], 12);
            const label = (n) => (n === "designed" ? "designed" : "board's gains");
            const cls = (n) => (n === "designed" ? "designed" : "on-machine");
            const points = c.frequency || [];
            const magnitudes = [any.plant_mag, ...names.map((n) => bode[n].loop_mag), points.map((p) => p.magnitude)];
            const mag = extent(magnitudes, { positive: true }) || [0.1, 10];
            out.push(plotSvg({ name: "magnitude", title: "The open loop's magnitude over frequency",
                x: { log: true, domain: xdom, label: "ω", unit: "rad/s" }, y: { log: true, domain: logDomain(mag[0], mag[1], 8), label: "|L|, |G|" },
                series: [series("plant_mag", "plant", any.w, any.plant_mag, "plant"), ...names.map((n) => series(`loop_mag_${n}`, cls(n), bode[n].w, bode[n].loop_mag, `open loop, ${label(n)}`))],
                rules: [{ y: 1, label: "1" }],
                marks: names.flatMap((n) => [
                    { name: `gain_crossover_${n}`, x: m[n] && m[n].gain_crossover, cls: cls(n), label: `ωc ${shown(m[n] && m[n].gain_crossover)}` },
                    { name: `phase_crossover_${n}`, x: m[n] && m[n].phase_crossover, cls: cls(n), label: `GM ${shown(m[n] && m[n].gain_margin)}×` },
                ]),
                points: points.map((p) => ({ x: p.frequency, y: p.magnitude, trust: p.trust, why: p.why })) }));
            const phases = [any.plant_phase, ...names.map((n) => bode[n].loop_phase), points.map((p) => p.phase_deg)];
            const [plo, phi] = extent(phases) || [-180, 0];
            const pdom = [Math.max(-540, Math.floor(plo / 90) * 90), Math.min(90, Math.ceil(phi / 90) * 90)];
            out.push(plotSvg({ name: "phase", title: "The open loop's phase over frequency",
                x: { log: true, domain: xdom, label: "ω", unit: "rad/s" }, y: { domain: pdom, ticks: stepTicks(pdom[0], pdom[1], 90), label: "phase", unit: "°" },
                series: [series("plant_phase", "plant", any.w, any.plant_phase, "plant"), ...names.map((n) => series(`loop_phase_${n}`, cls(n), bode[n].w, bode[n].loop_phase, `open loop, ${label(n)}`))],
                rules: [{ y: -180, label: "-180°" }],
                marks: names.flatMap((n) => [
                    { name: `gain_crossover_${n}`, x: m[n] && m[n].gain_crossover, cls: cls(n), label: `PM ${shown(m[n] && m[n].phase_margin)}°` },
                    { name: `phase_crossover_${n}`, x: m[n] && m[n].phase_crossover, cls: cls(n), label: `ω180 ${shown(m[n] && m[n].phase_crossover)}` },
                ]),
                points: points.map((p) => ({ x: p.frequency, y: p.phase_deg, trust: p.trust, why: p.why })) }));
            const sens = extent(names.flatMap((n) => [bode[n].s_mag, bode[n].t_mag]), { positive: true }) || [0.1, 10];
            out.push(plotSvg({ name: "sensitivity", title: "The sensitivity and the complementary sensitivity over frequency",
                x: { log: true, domain: xdom, label: "ω", unit: "rad/s" }, y: { log: true, domain: logDomain(sens[0], sens[1], 4), label: "|S|, |T|" },
                series: names.flatMap((n) => [series(`s_mag_${n}`, cls(n), bode[n].w, bode[n].s_mag, `S, ${label(n)}`), series(`t_mag_${n}`, cls(n), bode[n].w, bode[n].t_mag, `T, ${label(n)}`, true)]),
                rules: [{ y: 1, label: "1" }],
                marks: names.flatMap((n) => [
                    { name: `ms_${n}`, x: m[n] && m[n].ms_at, cls: cls(n), label: `Ms ${shown(m[n] && m[n].ms)}` },
                    { name: `mt_${n}`, x: m[n] && m[n].mt_at, cls: cls(n), label: `Mt ${shown(m[n] && m[n].mt)}` },
                ]) }));
            if (points.length) out.push(`<p class="loops-note">Measured points of the plant: filled is good, faint is fair, hollow and broken is poor, a hollow square is unknown; each one's why is its tip.</p>`);
        }
        out.push(`<p class="loops-note">Drawn from the server's curves of ${esc(st.experiment)}; the model's step is its PID run every ${esc(c.model_pid_dt)} s, a stand-in for the board's own rate.</p>`);
        el.innerHTML = out.join("");
    }
    function renderFigures() {
        const el = $("loops-figures");
        const doc = st.doc;
        if (!doc) { el.innerHTML = ""; return; }
        el.innerHTML = (doc.groups || []).map((g) => `<table class="loops-table loops-group" data-group="${esc(g.id)}"><caption>${esc(g.title)}</caption>
<thead><tr><th scope="col">Figure</th><th scope="col">Value</th><th scope="col">Basis</th><th scope="col">From</th></tr></thead><tbody>
${g.figures.map((f) => `<tr data-figure="${esc(`${g.id}.${f.key}`)}" data-value="${esc(String(f.value))}"${f.note ? ` title="${esc(f.note)}"` : ""}><th scope="row">${esc(f.label)}</th><td class="loops-value">${esc(f.value === null ? shown(null) : `${shown(f.value)} ${f.unit || ""}`.trim())}</td><td class="loops-basis" data-basis="${esc(f.basis)}">${esc(BASIS[f.basis] || f.basis)}</td><td class="loops-source">${esc(f.source)}</td></tr>`).join("")}
</tbody></table>`).join("") + (doc.machine && doc.machine.simulated ? `<p class="loops-note">A simulated machine's numbers are the simulator's and no heater's.</p>` : "");
    }

    async function loadKept() {
        st.experiment = null;
        if (!st.port) return;
        try {
            const kept = await api(`/firmware/printers/loops/experiments?port=${encodeURIComponent(st.port)}`);
            // The newest of the loop that ran to its end, else the newest: one cancelled at
            // its first reading does not hide the one before it.
            const ofLoop = kept.filter((e) => ((e.parameters || {}).heater || "hotend") === st.heater);
            const mine = ofLoop.find((e) => e.outcome === "done") || ofLoop[0];
            st.experiment = mine ? mine.id : null;
        } catch (e) { tell(`The kept experiments were not listed: ${e.message}`, "error"); }
    }
    let docAsked = 0;
    async function loadDocument() {
        const asked = ++docAsked;
        st.doc = st.curves = st.docError = null;
        renderPlots(); renderFigures(); renderGains(); renderCan();
        if (!st.experiment) return;
        const readBoard = !!(st.read && st.read.port === st.port) && !!(verdictOf(st.can, "tune.read") || { ok: true }).ok;
        const body = { experiment_id: st.experiment, rule: st.rule, kind: st.ruleKind, read_board: readBoard };
        try {
            let doc, curves;
            try {
                doc = await post("/firmware/printers/loops/document", body);
                curves = await post("/firmware/printers/loops/curves", body);
            } catch (e) {
                if (!readBoard) throw e;
                // The board would not be read now (a job holds its port): the document without it.
                body.read_board = false;
                doc = await post("/firmware/printers/loops/document", body);
                curves = await post("/firmware/printers/loops/curves", body);
                tell(`The board's gains were not read again for the document: ${e.message}`, "error");
            }
            if (asked !== docAsked) return;
            st.doc = doc; st.curves = curves; st.readBoard = body.read_board;
        } catch (e) {
            if (asked !== docAsked) return;
            st.docError = e.message;
        }
        renderPlots(); renderFigures(); renderGains(); renderCan();
    }
    async function keptAgain() {
        await loadKept();
        await loadDocument();
    }

    // --- following the experiment: the stream, else the job asked once a second ----------
    let tellings = null, polling = null;
    function heardLoop(change) {
        if (change.surface === "tune" && change.key === st.port) {
            const was = running();
            st.job = change.body; st.heard += 1; st.via = "stream";
            renderJob(); askStart();
            if (was && !running()) askCan();
        } else if (change.surface === "control_loop" && change.body && change.key !== st.experiment) {
            // An experiment kept: of this machine's loop (its document says so, or it is the
            // one this port ran), the kept ones listed again and the newest shown.
            const d = change.body.document;
            const ours = d ? d.machine && d.machine.port === st.port && d.loop && d.loop.heater === st.heater
                : !!(st.job && change.key === st.job.experiment_id);
            if (ours) keptAgain();
        }
    }
    function catchUp() { if (st.port) followJob(); }
    function streamFaltered() { if (running()) pollJob(); }
    function follow() {
        if (tellings || typeof EventSource === "undefined") return;
        tellings = new EventSource(`${base}/surfaces/events?names=tune,control_loop`);
        tellings.addEventListener("change", (e) => heardLoop(JSON.parse(e.data)));
        tellings.addEventListener("surfaces", catchUp);
        tellings.addEventListener("missed", catchUp);
        tellings.addEventListener("error", streamFaltered);
    }
    const streamOpen = () => !!(tellings && tellings.readyState === EventSource.OPEN);
    async function followJob() {
        if (!st.port) return;
        try {
            const j = await api(`/firmware/printers/loops/job?port=${encodeURIComponent(st.port)}`);
            const was = running();
            st.job = j.stage === null ? null : j;
            renderJob(); askStart();
            if (was && !running()) { askCan(); keptAgain(); }
        } catch (e) { /* the next look says it */ }
    }
    function pollJob() {
        if (polling) return;
        st.via = "poll";
        polling = setInterval(() => {
            if (streamOpen() || !running()) { clearInterval(polling); polling = null; if (!running()) keptAgain(); return; }
            followJob();
        }, POLL_MS);
    }

    // --- acts ---------------------------------------------------------------------------------
    // Each says what it did, or the server's reason it was refused, in the window and on
    // the page's status line; a refused act's reason is the one its greyed button shows.
    function refusedNow(verb) {
        const v = verdictOf(localCan(), verb);
        return v && !v.ok ? v.why : null;
    }
    async function doRead() {
        const why = refusedNow("tune.read");
        if (why) return { refused: why };
        try {
            st.read = { ...(await post("/firmware/printers/loops/read", { port: st.port })), port: st.port };
            renderGains();
            const label = st.heater === "bed" ? "bed" : "hotend 0";
            const g = st.read.gains[label];
            await loadDocument();
            return { said: g ? `${label} holds P${shown(g.kp)} I${shown(g.ki)} D${shown(g.kd)}, read at ${when(st.read.read_at)}` : `the board said no gains for ${label}` };
        } catch (e) { return { refused: e.message }; } finally { askCan(); }
    }
    async function doStart() {
        const why = refusedNow("tune.start");
        if (why) return { refused: why };
        try {
            st.job = await post("/firmware/printers/loops/start", figures());
            renderJob(); askStart();
            if (!streamOpen()) pollJob();
            return { said: `${st.job.what} started: its progress is told here as it runs` };
        } catch (e) { return { refused: e.message }; } finally { askCan(); }
    }
    async function doCancel() {
        const why = refusedNow("tune.cancel");
        if (why) return { refused: why };
        try {
            st.job = await post("/firmware/printers/loops/cancel", { port: st.port });
            renderJob();
            return { said: `${st.job.what}: cancelling, the heater turned off and read back` };
        } catch (e) { return { refused: e.message }; } finally { askCan(); }
    }
    async function doSet() {
        const why = refusedNow("tune.set");
        if (why) return { refused: why };
        const g = designed();
        try {
            st.set = { ...(await post("/firmware/printers/loops/set", { port: st.port, heater: st.heater, index: 0, kp: g.kp, ki: g.ki, kd: g.kd })), port: st.port };
            renderGains();
            // What the board holds now, read again (M503), and the document with it.
            st.read = { ...(await post("/firmware/printers/loops/read", { port: st.port })), port: st.port };
            await loadDocument();
            return { said: `${st.set.sent} sent; ${st.set.matches ? "the board holds what was sent" : "the board does not hold what was sent"} -- set, not saved` };
        } catch (e) { return { refused: e.message }; } finally { askCan(); }
    }
    async function chooseLoop(heater) {
        if (!LOOPS.some(([v]) => v === heater)) return { refused: `no loop ${heater}: hotend 0 or the bed` };
        st.heater = heater;
        renderHead(); renderForm(); askStart();
        await keptAgain();
        return { said: `${loopLabel()}${st.experiment ? `: ${st.experiment}` : ": no experiment kept"}` };
    }
    function chooseKind(kind) {
        if (!(st.kinds || []).some((k) => k.kind === kind)) return { refused: `no experiment ${kind}` };
        st.kind = kind;
        renderForm(); askStart(); renderCan();
        return { said: `${(st.kinds.find((k) => k.kind === kind) || {}).label} of ${loopLabel()}` };
    }
    async function chooseRule(name, kind) {
        const r = (st.rules || []).find((x) => x.name === name);
        if (!r || !r.kinds.includes(kind)) return { refused: `no rule ${name} giving ${kind}` };
        st.rule = name; st.ruleKind = kind;
        renderHead();
        await loadDocument();
        return st.docError ? { refused: st.docError } : { said: `designed by ${r.title}, ${kind.toUpperCase()}` };
    }
    async function act(verb, { label = "", tail = "" } = {}) {
        if (loading) await loading;
        let done;
        if (verb === "read") done = await doRead();
        else if (verb === "start") done = await doStart();
        else if (verb === "cancel") done = await doCancel();
        else if (verb === "set") done = await doSet();
        else if (verb.startsWith("loop:")) done = await chooseLoop(verb.slice(5));
        else if (verb.startsWith("kind:")) done = chooseKind(verb.slice(5));
        else if (verb.startsWith("rule:")) { const [, name, kind] = verb.split(":"); done = await chooseRule(name, kind); }
        else done = { refused: `Loops has no act ${verb}` };
        const head = label || "Loops";
        // A refusal stays until the act it refused would go, or is refused for another
        // reason, or another act goes: it is not left standing after what stopped it has ended.
        st.refusedVerb = done.refused && ["read", "start", "cancel", "set"].includes(verb) ? `tune.${verb}` : null;
        st.refusedWhy = done.refused || null;
        if (done.refused) { tell(done.refused, st.port ? "error" : "note"); say(`${head}: ${done.refused}${tail}`, "error"); }
        else { tell(done.said); say(`${head}: ${done.said}${tail}`, "success"); }
        return done;
    }

    function onLoopsClick(event) {
        const b = event.target.closest && event.target.closest("button");
        if (!b || b.disabled) return;
        const verb = { "loops-read": "read", "loops-start": "start", "loops-cancel": "cancel", "loops-set": "set" }[[...b.classList].find((c) => c.startsWith("loops-"))];
        if (verb) act(verb, { label: b.textContent.trim() });
    }
    function onLoopsChange(event) {
        const t = event.target;
        if (t.classList.contains("loops-loop")) act(`loop:${t.value}`, { label: "Loop" });
        else if (t.classList.contains("loops-kind")) act(`kind:${t.value}`, { label: "Experiment" });
        else if (t.classList.contains("loops-rule")) act(`rule:${t.value}`, { label: "Rule" });
    }
    // A figure typed is kept as typed, and the server asked about the figures as they stand.
    function onLoopsInput(event) {
        const t = event.target;
        if (t.classList.contains("loops-param")) (st.typed[`${st.kind}:${st.heater}`] ||= {})[t.dataset.param] = t.value;
        else if (t.classList.contains("loops-ceiling")) (st.typed[st.heater] ||= {}).ceiling_c = t.value;
        else if (t.classList.contains("loops-longest")) (st.typed[st.heater] ||= {}).max_duration_s = t.value;
        else return;
        askStart();
    }
    root.addEventListener("click", onLoopsClick);
    root.addEventListener("change", onLoopsChange);
    root.addEventListener("input", onLoopsInput);

    // The open Machine, followed: its board's answers carry `can`, and another Machine
    // opened is another printer's loops.
    function onLoopsBoard(event) {
        const d = event.detail;
        if (!root.isConnected) return;
        const m = machine();
        if ((m ? m.port : null) !== st.port) { load(); return; }
        if (!st.port || d.port !== st.port) return;
        if (d.what === "status" && d.status) takeCan(d.status.can);
        else if (d.what === "info" && d.info) takeCan(d.info.can);
    }
    window.addEventListener("apothecary:board", onLoopsBoard);

    // One look at the open Machine at a time; an act waits for the one under way.
    let loading = null;
    function load() {
        const mine = (loading || Promise.resolve()).catch(() => {}).then(look)
            .finally(() => { if (loading === mine) loading = null; });
        loading = mine;
        return mine;
    }
    async function look() {
        const m = machine();
        const port = m && m.port ? m.port : null;
        const moved = port !== st.port || !st.loaded;
        st.port = port; st.name = m ? m.name || port : null;
        if (moved) { st.can = null; st.verdict = null; st.asking = null; st.job = null; st.set = null; }
        follow();
        if (!st.rules) {
            try {
                const [rules, kinds] = [await api("/firmware/loops/rules"), await api("/firmware/loops/kinds")];
                st.rules = rules.rules; st.rule = st.rule || rules.default.rule; st.ruleKind = st.ruleKind || rules.default.kind;
                st.kinds = kinds.kinds; st.kindsAnswer = kinds;
            } catch (e) { tell(`The server's rules and experiments were not read: ${e.message}`, "error"); }
        }
        st.loaded = true;
        renderHead(); renderForm(); renderJob(); renderCan();
        if (!moved) return;
        if (st.port) { await askCan(); await followJob(); }
        await keptAgain();
    }

    load();
    return {
        load,
        act,
        refresh: () => { renderHead(); renderForm(); renderCan(); },
        state: () => ({ port: st.port, heater: st.heater, kind: st.kind, rule: st.rule, ruleKind: st.ruleKind, experiment: st.experiment, heard: st.heard, via: st.via, job: st.job, verdict: st.verdict && st.verdict.answer, readBoard: st.readBoard, set: st.set, said: st.said }),
    };
}
