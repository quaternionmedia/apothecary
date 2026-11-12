/* Tour: the walkthrough a step at a time beside the live page, as the help a person
 * takes through the app (apothecary/tour.py, GET /tour). Each step is its page's as the
 * test that writes it recorded it -- heading, words, the picture taken after its
 * assertions, what it showed -- and the person says whether the page here does what it
 * shows: ✓ As shown, or ✗ Off with what is off (POST /tour/verdicts). A page no test
 * writes is read whole, at its link.
 *
 * Where a person is in the tour is this browser's, as a window's place is; what they
 * said is the server's, under its state folder (`apothecary tour` reads it back).
 *
 * Answers { open(), shown(), go(page, step), next(), back(), answer(verdict), act(verb), here() }.
 */

const KEY = "apothecary.tour";

const MARKUP = `
<div class="panel-ui tour">
    <div class="tour-head">
        <select class="tour-stops" aria-label="The walkthrough page"></select>
        <span class="tour-said muted"></span>
    </div>
    <div class="tour-next" role="status"></div>
    <div class="tour-step">
        <h3 class="tour-heading"></h3>
        <p class="tour-words"></p>
        <a class="tour-picture" target="_blank" rel="noopener" title="The picture, whole, in a tab of its own" hidden><img alt=""></a>
        <pre class="tour-shown" hidden></pre>
    </div>
    <div class="tour-answer muted"></div>
    <input type="text" class="tour-note" placeholder="What is off, if anything" aria-label="What is off">
    <div class="tour-buttons">
        <button type="button" class="tour-back" data-do="back">‹ Back</button>
        <button type="button" class="tour-as-shown" data-do="as shown">✓ As shown</button>
        <button type="button" class="tour-off" data-do="off">✗ Off</button>
        <button type="button" class="tour-forward" data-do="next">Next ›</button>
        <a class="tour-page" target="_blank" rel="noopener">its page</a>
    </div>
</div>`;

export function mountTour(root, { base = "", log = null } = {}) {
    root.innerHTML = MARKUP;
    const q = (sel) => root.querySelector(sel);
    const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
    const say = (text, kind = "") => { if (log) log(text, kind); };
    const state = { doc: null, at: 0, pos: 0 };

    async function api(path, opts = {}) {
        const r = await fetch(base + path, { headers: { "Content-Type": "application/json" }, ...opts });
        const body = await r.json().catch(() => ({}));
        if (!r.ok) throw new Error(typeof body.detail === "string" ? body.detail : r.statusText);
        return body;
    }

    // A page's words as its Markdown has them inline: code, strong, and links, which
    // resolve against the page's own folder, as they do on the page.
    const page = () => new URL(`${base}/walkthrough/`, location.href);
    function inline(text) {
        return esc(text)
            .replace(/`([^`]+)`/g, "<code>$1</code>")
            .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
            .replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, (_, t, u) => `<a href="${esc(new URL(u.replace(/&amp;/g, "&"), page()).href)}" target="_blank" rel="noopener">${t}</a>`);
    }

    const stop = () => state.doc.stops[state.at];
    const step = () => stop().steps[state.pos] || null;
    const stepId = () => (step() ? step().index : 0);
    const count = (s) => Math.max(s.steps.length, 1);
    const answered = (s) => Object.values(s.answers);

    function remember() {
        try { localStorage.setItem(KEY, JSON.stringify({ page: stop().page, pos: state.pos })); } catch (e) { /* kept for this visit only */ }
    }
    function remembered() {
        try { return JSON.parse(localStorage.getItem(KEY) || "null"); } catch (e) { return null; }
    }
    // Where to start: where this browser was, else the first step not yet answered.
    function startAt() {
        const was = remembered();
        const i = was ? state.doc.stops.findIndex((s) => s.page === was.page) : -1;
        if (i >= 0) { state.at = i; state.pos = Math.min(Math.max(was.pos | 0, 0), count(state.doc.stops[i]) - 1); return; }
        for (const [i, s] of state.doc.stops.entries()) {
            const ids = s.steps.length ? s.steps.map((t) => t.index) : [0];
            const first = ids.findIndex((id) => !s.answers[id]);
            if (first >= 0) { state.at = i; state.pos = first; return; }
        }
        state.at = 0; state.pos = 0;
    }

    function render() {
        const doc = state.doc;
        const steps = doc.stops.reduce((n, s) => n + count(s), 0);
        const all = doc.stops.flatMap(answered);
        const off = all.filter((r) => r.verdict === "off").length;
        q(".tour-said").textContent = `${all.length} of ${steps} steps answered, ${off} off · against ${doc.commit || "an unknown commit"}${doc.changed ? " with changes" : ""}`;
        q(".tour-stops").innerHTML = doc.stops.map((s, i) => {
            const mine = answered(s), bad = mine.filter((r) => r.verdict === "off").length;
            return `<option value="${i}"${i === state.at ? " selected" : ""}>${esc(s.number)} — ${esc(s.title)} · ${mine.length}/${count(s)}${bad ? ` · ${bad} off` : ""}</option>`;
        }).join("");
        const s = stop(), t = step();
        q(".tour-next").textContent = t
            ? `Step ${state.pos + 1} of ${s.steps.length} of page ${s.number}: do what it says here, beside this window, and say whether the page does what the picture shows.`
            : `Page ${s.number} is read whole, its checks run by the test command: read it at its link, and say whether it says what the app does.`;
        q(".tour-heading").textContent = t ? `${t.index}. ${t.heading}` : s.title;
        q(".tour-words").innerHTML = inline(t ? t.words : s.intro);
        const picture = q(".tour-picture");
        picture.hidden = !(t && t.picture);
        if (t && t.picture) {
            picture.href = `${base}/walkthrough/${t.picture}`;
            picture.querySelector("img").src = picture.href;
            picture.querySelector("img").alt = t.heading;
        }
        const shown = q(".tour-shown");
        shown.hidden = !(t && t.shown);
        shown.textContent = t && t.shown ? t.shown : "";
        const record = s.answers[stepId()];
        q(".tour-answer").textContent = !record ? "Not answered yet."
            : `${record.verdict === "off" ? `✗ Off: ${record.note}` : "✓ As shown"} -- said ${new Date(record.at).toLocaleString()} against ${record.commit || "an unknown commit"}.`;
        q(".tour-page").href = `${base}/walkthrough/${s.page}`;
        q(".tour-back").disabled = state.at === 0 && state.pos === 0;
        q(".tour-forward").disabled = state.at === doc.stops.length - 1 && state.pos >= count(s) - 1;
    }

    function go(at, pos = 0) {
        state.at = Math.min(Math.max(at, 0), state.doc.stops.length - 1);
        state.pos = Math.min(Math.max(pos, 0), count(stop()) - 1);
        remember();
        render();
    }
    function next() {
        if (state.pos < count(stop()) - 1) go(state.at, state.pos + 1);
        else if (state.at < state.doc.stops.length - 1) go(state.at + 1, 0);
    }
    function back() {
        if (state.pos > 0) go(state.at, state.pos - 1);
        else if (state.at > 0) go(state.at - 1, count(state.doc.stops[state.at - 1]) - 1);
    }
    async function answer(verdict) {
        const s = stop(), id = stepId(), note = q(".tour-note").value.trim();
        try {
            const record = await api("/tour/verdicts", { method: "POST", body: JSON.stringify({ page: s.page, step: id, verdict, note }) });
            s.answers[id] = record;
            q(".tour-note").value = "";
            say(`Page ${s.number}, ${id ? `step ${id}` : "read whole"}: ${verdict === "off" ? `off, ${note}` : "as shown"}`);
            next();
            return record;
        } catch (e) {
            say(`Page ${s.number}, ${id ? `step ${id}` : "read whole"}: not kept, ${e.message}`, "bad");
            q(".tour-answer").textContent = `Not kept: ${e.message}.`;
            return null;
        }
    }

    async function open() {
        try {
            state.doc = await api("/tour");
        } catch (e) {
            q(".tour-next").textContent = `The tour was not read: ${e.message}`;
            return null;
        }
        startAt();
        render();
        return here();
    }
    const here = () => (state.doc ? { page: stop().page, step: stepId() } : null);

    root.addEventListener("click", (e) => {
        const act = e.target.closest("[data-do]")?.dataset.do;
        if (!act || !state.doc) return;
        if (act === "next") next();
        else if (act === "back") back();
        else answer(act);
    });
    const tourPages = q(".tour-stops");
    tourPages.addEventListener("change", (e) => go(Number(e.target.value), 0));
    // The ring's cells under Panels › Windows › Tour, each as its button does; Its page
    // and Its picture open the walkthrough page, or the step's picture whole, in a tab
    // of its own, as the links do.
    function act(verb) {
        if (!state.doc) return null;
        if (verb === "back") return back();
        if (verb === "next") return next();
        if (verb === "page") return window.open(q(".tour-page").href, "_blank", "noopener");
        if (verb === "picture") return step()?.picture ? window.open(q(".tour-picture").href, "_blank", "noopener") : null;
        return answer(verb === "as-shown" ? "as shown" : verb);
    }

    return {
        open,
        shown: () => (state.doc ? render() : open()),
        go: (pageName, stepIndex = null) => {
            const at = state.doc.stops.findIndex((s) => s.page === pageName);
            if (at < 0) return null;
            const pos = stepIndex == null ? 0 : state.doc.stops[at].steps.findIndex((t) => t.index === stepIndex);
            go(at, Math.max(pos, 0));
            return here();
        },
        next, back, answer, act, here,
    };
}
