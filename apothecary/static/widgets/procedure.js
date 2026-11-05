/* Procedure: a site's procedures, each step fired through the family's hub on GO.
 *
 * Who the family is (GET /family/), and the procedure chosen (GET
 * /sites/{s}/procedures/{p}): each step in order with its discipline, its node and its
 * notes, how it stands, why, and the outcome of its last fire per member. GO is on a
 * step standing by, and on one refused or failed, which may be fired again; Start over
 * counts what came before no more. A refusal is the member's own words, so a machine's
 * says to arm its control, which a person does in the Machine window: GO never does.
 *
 * GO and Start over are the canvas ring's Site › Procedure too: the page hands each to
 * act(), and GO there fires the step this window offers it on, the first.
 *
 * mountProcedure(root, { base, siteName, log }) renders into root. load() asks again,
 * and shown() and close() start and stop asking every LOOK_MS while the window is shown.
 */

const LOOK_MS = 2000;

const REACHED = { local: "hosted here", push: "beside the hub", pull: "read by a page" };

const MARKUP = `
<div class="procedure-ui">
    <div class="k">The family</div>
    <div class="procedure-family"><span class="empty">asking…</span></div>
    <div class="row procedure-head">
        <select class="procedure-choice" aria-label="The procedure"></select>
        <span class="grow"></span>
        <button type="button" class="procedure-again" title="Count what came before no more: it stays in the log">Start over</button>
    </div>
    <ol class="procedure-steps"></ol>
    <div class="procedure-none note"></div>
</div>`;

export function mountProcedure(root, { base = "", siteName, log = null } = {}) {
    root.innerHTML = MARKUP;
    const $ = (sel) => root.querySelector(sel);
    const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
    const say = (text, kind = "") => { if (log) log(text, kind); };
    const slug = (status) => status.replace(/\s+/g, "-");
    let names = [], name = null, board = null, drawn = "", busy = false, timer = null;

    async function api(path, opts = {}) {
        const r = await fetch(base + path, { headers: { "Content-Type": "application/json" }, ...opts });
        const body = await r.json().catch(() => ({}));
        if (!r.ok) throw new Error(typeof body.detail === "string" ? body.detail : r.statusText);
        return body;
    }
    const siteUrl = () => `/sites/${encodeURIComponent(siteName())}/procedures`;
    const chosenUrl = () => `${siteUrl()}/${encodeURIComponent(name)}`;

    function renderFamily(members) {
        const rows = Object.entries(members).sort(([a], [b]) => a.localeCompare(b));
        $(".procedure-family").innerHTML = rows.map(([who, how]) =>
            `<span class="procedure-member" title="${esc(REACHED[how.via] || how.via)}"><span class="dot ${how.via === "pull" ? "off" : "ok"}"></span>${esc(who)}</span>`).join("");
    }

    // The step's own line says its first error, so an outcome says only another's.
    const outcomeWords = (o, why) => {
        if (o.member === null || o.member === undefined) return "";
        const answered = o.status === null || o.status === undefined ? (o.done ? "no answer" : "not read yet") : `answered ${o.status}`;
        const ms = o.ms === null || o.ms === undefined ? "" : ` in ${o.ms} ms`;
        const error = o.error && o.error !== why ? ` · <span class="bad">${esc(o.error)}</span>` : "";
        return `<li class="procedure-outcome"><span class="who">${esc(o.member)}</span> ${esc(answered)}${esc(ms)}${error}</li>`;
    };

    function renderStep(step) {
        const where = [step.discipline, step.node].filter(Boolean).map(esc).join(" · ");
        const outcomes = (step.outcomes || []).map((o) => outcomeWords(o, step.why)).join("");
        const go = step.can_go ? `<button type="button" class="procedure-go" data-number="${esc(step.number)}"${busy ? " disabled" : ""}>GO</button>` : "";
        return `<li class="procedure-step is-${esc(slug(step.status))}" data-number="${esc(step.number)}">
            <div class="row"><span class="number">${esc(step.number)}</span><span class="grow name">${esc(step.name)}</span><span class="procedure-status">${esc(step.status)}</span>${go}</div>
            <div class="meta">${where}</div>
            ${step.notes ? `<div class="note">${esc(step.notes)}</div>` : ""}
            ${step.why ? `<div class="procedure-why">${esc(step.why)}</div>` : ""}
            ${outcomes ? `<ul class="procedure-outcomes">${outcomes}</ul>` : ""}
        </li>`;
    }

    function render() {
        const words = JSON.stringify([names, name, board, busy]);
        if (words === drawn) return;
        drawn = words;
        $(".procedure-choice").innerHTML = names.map((n) => `<option value="${esc(n)}"${n === name ? " selected" : ""}>${esc(n)}</option>`).join("");
        $(".procedure-head").hidden = !names.length;
        $(".procedure-none").textContent = names.length ? "" : `No procedure under ${siteName()} yet: docs/family.md says how one is written.`;
        $(".procedure-steps").innerHTML = board ? board.steps.map(renderStep).join("") : "";
    }

    async function load() {
        try {
            const [family, listed] = await Promise.all([api("/family/"), api(siteUrl())]);
            renderFamily(family.members);
            names = listed.procedures;
            if (!names.includes(name)) name = names[0] ?? null;
            board = name ? await api(chosenUrl()) : null;
        } catch (err) {
            say(`Procedure: ${err.message}`, "bad");
        }
        render();
    }

    async function post(path, said) {
        if (busy) return;
        busy = true;
        render();
        try {
            board = await api(path, { method: "POST" });
            say(...said(board));
        } catch (err) {
            say(`Procedure: ${err.message}`, "bad");
        }
        busy = false;
        render();
        load();
    }

    // What came of it, in the status bar: a refused step was not fired.
    const go = (number) => post(`${chosenUrl()}/steps/${encodeURIComponent(number)}/go`, (now) => {
        const { status } = now.steps.find((step) => step.number === number);
        return [`Step ${number}: ${status}`, status === "refused" || status === "failed" ? "bad" : ""];
    });

    const again = () => post(`${chosenUrl()}/again`, () => [`${name} starts over`]);

    const procedure = $(".procedure-ui");
    procedure.addEventListener("click", (event) => {
        const fires = event.target.closest(".procedure-go");
        if (fires) go(fires.dataset.number);
        else if (event.target.closest(".procedure-again")) again();
    });
    procedure.addEventListener("change", (event) => {
        const chosen = event.target.closest(".procedure-choice");
        if (chosen) { name = chosen.value; board = null; load(); }
    });

    // A ring cell's verb, on the procedure chosen: what it did, or why not, is said.
    async function act(verb) {
        await load();
        if (!board) { say(`No procedure under ${siteName()}`, "bad"); return; }
        if (verb === "again") { await again(); return; }
        const next = board.steps.find((step) => step.can_go);
        if (next) await go(next.number);
        else say("No step stands by", "bad");
    }

    function close() {
        clearInterval(timer);
        timer = null;
    }

    function shown() {
        close();
        timer = setInterval(load, LOOK_MS);
        return load();
    }

    return { load, shown, close, go, act };
}
