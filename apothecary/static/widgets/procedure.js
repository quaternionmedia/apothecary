/* Procedure: a site's procedures, each step fired through the family's hub on GO.
 *
 * The procedure chosen (GET
 * /sites/{s}/procedures/{p}): each step in order with its discipline, its node and its
 * notes, how it stands, why, and the outcome of its last fire per member. GO is on a
 * step standing by, and on one refused or failed, which may be fired again; Start over
 * counts what came before no more. A refusal is the member's own words, so a machine's
 * says to arm its control, which a person does in the Machine window: GO never does.
 *
 * The window leads to where each step's work is. A step's node is a door: pressed, the
 * page opens the node's window, a machine's or a board's Machine, a camera's Pictures.
 * A step fired opens the section its member works in, where that Machine is open: a
 * machine's home or run the Status, a board's flash the Flashing, its expect the Log.
 * A refused or failed step keeps the member's words, with the node's door right after
 * them. A member's name is a door too, in the Members window (widgets/family.js), which
 * asks this window where each leads: doorOf(member, how).
 *
 * GO and Start over are the canvas ring's Site › Procedure too: the page hands each to
 * act(), and GO there fires the step this window offers it on, the first.
 *
 * mountProcedure(root, { base, siteName, log, open }) renders into root; open(node,
 * section) is the page's door (without a section, the node's window; with one, that
 * section of the node's Machine where it is open, and nothing where it is not). load()
 * asks again, and shown() and close() start and stop asking every LOOK_MS while the
 * window is shown.
 */

const LOOK_MS = 2000;

// The section of a node's Machine a member's verb works in.
const SECTION = { machine: "machine-status", flash: "machine-flashing", expect: "machine-log" };

const MARKUP = `
<div class="procedure-ui">
    <div class="row procedure-head">
        <select class="procedure-choice" aria-label="The procedure"></select>
        <span class="grow"></span>
        <button type="button" class="procedure-again" title="Count what came before no more: it stays in the log">Start over</button>
    </div>
    <ol class="procedure-steps"></ol>
    <div class="procedure-none note"></div>
</div>`;

export function mountProcedure(root, { base = "", siteName, log = null, open = null } = {}) {
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

    const steps = () => (board ? board.steps : []);
    const names_ = (step, who) => !!(step.family && step.family[who]);
    // The node a member works on next: that of the first step naming it not yet done,
    // else of the last that names it. Null where no step names it.
    function nodeOf(who) {
        const next = steps().find((step) => names_(step, who) && step.status !== "done")
            || [...steps()].reverse().find((step) => names_(step, who));
        if (!next) return null;
        const action = Object.values(next.family[who] || {}).find((a) => a && typeof a === "object" && a.node);
        return next.node || (action && action.node) || null;
    }
    // Where a member's name leads (the Members window draws it): a member beside the hub
    // to its page, one hosted here to the window of its next node; a pull member nowhere.
    function doorOf(who, how) {
        if (how.via === "push" && how.url) return { url: how.url, title: `opens ${how.url} in a new tab` };
        const node = how.via === "local" && open ? nodeOf(who) : null;
        return node ? { node, title: `opens ${node}'s window, the node its next step names` } : null;
    }

    // The step's own line says its first error, so an outcome says only another's.
    const outcomeWords = (o, why) => {
        if (o.member === null || o.member === undefined) return "";
        const answered = o.status === null || o.status === undefined ? (o.done ? "no answer" : "not read yet") : `answered ${o.status}`;
        const ms = o.ms === null || o.ms === undefined ? "" : ` in ${o.ms} ms`;
        const error = o.error && o.error !== why ? ` · <span class="bad">${esc(o.error)}</span>` : "";
        return `<li class="procedure-outcome"><span class="who">${esc(o.member)}</span> ${esc(answered)}${esc(ms)}${error}</li>`;
    };

    // The step's node: a door to its window where the page gives one, else its address.
    const nodeDoor = (node) => (open
        ? `<button type="button" class="procedure-node" data-node="${esc(node)}" title="Opens ${esc(node)}'s window: a machine's or a board's Machine, a camera's Pictures">${esc(node)}</button>`
        : esc(node));

    function renderStep(step) {
        const where = [step.discipline ? esc(step.discipline) : "", step.node ? nodeDoor(step.node) : ""].filter(Boolean).join(" · ");
        const meta = where ? `<div class="meta">${where}</div>` : "";
        const outcomes = (step.outcomes || []).map((o) => outcomeWords(o, step.why)).join("");
        const go = step.can_go ? `<button type="button" class="procedure-go" data-number="${esc(step.number)}"${busy ? " disabled" : ""}>GO</button>` : "";
        // Refused or failed, the member's words come first and the node's door right after.
        const stuck = step.status === "refused" || step.status === "failed";
        return `<li class="procedure-step is-${esc(slug(step.status))}" data-number="${esc(step.number)}">
            <div class="row"><span class="number">${esc(step.number)}</span><span class="grow name">${esc(step.name)}</span><span class="procedure-status">${esc(step.status)}</span>${go}</div>
            ${stuck ? "" : meta}
            ${step.notes ? `<div class="note">${esc(step.notes)}</div>` : ""}
            ${step.why ? `<div class="procedure-why">${esc(step.why)}</div>` : ""}
            ${stuck ? meta : ""}
            ${outcomes ? `<ul class="procedure-outcomes">${outcomes}</ul>` : ""}
        </li>`;
    }

    function render() {
        const words = JSON.stringify([names, name, board, busy]);
        if (words === drawn) return;
        drawn = words;
        $(".procedure-choice").innerHTML = names.map((n) => `<option value="${esc(n)}"${n === name ? " selected" : ""}>${esc(n)}</option>`).join("");
        $(".procedure-head").hidden = !names.length;
        $(".procedure-none").textContent = names.length ? "" : `no procedure under ${siteName()} yet`;
        $(".procedure-steps").innerHTML = steps().map(renderStep).join("");
    }

    async function load() {
        try {
            const listed = await api(siteUrl());
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

    // The section a step's member works in: a machine's verbs the Status, a board's
    // flash the Flashing and its expect the Log; a person's own step has none.
    function sectionOf(step) {
        const family = step.family || {};
        if (family.machine) return SECTION.machine;
        for (const verb of Object.keys(family.board || {})) if (SECTION[verb]) return SECTION[verb];
        return null;
    }

    // What came of it, in the status bar: a refused step was not fired. A step
    // delivered opens the section its member works in, where its Machine is open.
    const go = (number) => post(`${chosenUrl()}/steps/${encodeURIComponent(number)}/go`, (now) => {
        const step = now.steps.find((s) => s.number === number);
        const stuck = step.status === "refused" || step.status === "failed";
        const section = stuck ? null : sectionOf(step);
        if (section && open && step.node) open(step.node, section);
        return [`Step ${number}: ${step.status}`, stuck ? "bad" : ""];
    });

    const again = () => post(`${chosenUrl()}/again`, () => [`${name} starts over`]);

    const procedure = $(".procedure-ui");
    procedure.addEventListener("click", (event) => {
        const fires = event.target.closest(".procedure-go");
        if (fires) go(fires.dataset.number);
        else if (event.target.closest(".procedure-again")) again();
        else if (event.target.closest(".procedure-node")) open(event.target.closest(".procedure-node").dataset.node);
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

    return { load, shown, close, go, act, doorOf };
}
