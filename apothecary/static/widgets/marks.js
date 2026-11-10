/* Marks: a whiteboard's marks, sorted, and a person's word on any.
 *
 * A picture pinned as a view is read as marks (GET /sites/{s}/views/{id}/marks):
 * each a diagram's, writing, unsure or nothing, with why and how sure, and each
 * line of writing a note with what it is about. A mark's kind is a drop-down: a
 * person's choice there is their word (PUT .../marks/{mark}), which wins, and a
 * view the outline finder searched is read again with it, so its shapes follow.
 * A note's words are typed and said with Enter (PUT .../notes/{mark}); a size
 * typed for a note beside a line is offered as the line's length. Nothing here
 * reads handwriting.
 *
 * A mark's kind is the canvas ring's Panels › Pictures › Marks too (Diagram,
 * Writing, Unsure, Nothing), on the mark chosen here: the page hands each to act().
 *
 * mountMarks(root, { base, world, log }) renders into root; `world` is what the
 * page offers: siteName(), views() -- each { id, picture, host, finder }, the one
 * drawn at the selected place first -- and changed(), called after a word that
 * moved a view's shapes. log(text, kind) is the page's status bar. load() reads
 * the views and the chosen view's marks again; act("say:<kind>") says the chosen
 * mark is that kind.
 */

const MARKUP = `
<div class="marks-ui">
    <div class="row"><select class="marks-view" aria-label="The picture whose marks are listed"></select></div>
    <div class="marks-said note"></div>
    <div class="k">Marks</div>
    <ul class="marks-list"><li class="empty">–</li></ul>
    <div class="k">Notes</div>
    <ul class="marks-notes"><li class="empty">–</li></ul>
</div>`;

const KINDS = ["diagram", "writing", "unsure", "nothing"];

export function mountMarks(root, { base = "", world = null, log = null } = {}) {
    root.innerHTML = MARKUP;
    const $ = (sel) => root.querySelector(sel);
    const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
    const say = (text, kind = "") => { if (log) log(text, kind); };
    let views = [], viewId = null, read = null, chosen = null, alive = true;

    async function api(path, opts = {}) {
        const r = await fetch(base + path, { headers: { "Content-Type": "application/json" }, ...opts });
        const body = await r.json().catch(() => ({}));
        if (!r.ok) throw new Error(typeof body.detail === "string" ? body.detail : (body.detail ? JSON.stringify(body.detail) : r.statusText));
        return body;
    }
    const viewUrl = () => `/sites/${encodeURIComponent(world.siteName())}/views/${encodeURIComponent(viewId)}`;

    function renderViews() {
        const pick = $(".marks-view");
        pick.innerHTML = views.length
            ? views.map((v) => `<option value="${esc(v.id)}"${v.id === viewId ? " selected" : ""}>${esc(v.picture)} · ${esc(v.host === "" ? "the floor" : v.host ?? "nowhere")}</option>`).join("")
            : '<option value="">no picture pinned here yet</option>';
        pick.disabled = !views.length;
    }

    function render() {
        const list = $(".marks-list"), notes = $(".marks-notes");
        if (!read) {
            list.innerHTML = notes.innerHTML = '<li class="empty">–</li>';
            $(".marks-said").textContent = "";
            return;
        }
        $(".marks-said").textContent = read.finder === "outline"
            ? "A word here is read back by this picture's shapes."
            : "This picture's shapes are another finder's: Find shapes › outline reads its marks as shapes.";
        list.innerHTML = read.marks.length ? read.marks.map((m) => `<li class="marks-row${m.id === chosen ? " chosen" : ""}" data-mark="${esc(m.id)}">
            <button type="button" class="marks-choose" data-mark="${esc(m.id)}" title="Choose this mark: the ring's Marks cells say what it is" aria-pressed="${m.id === chosen}">${esc(m.id)}</button>
            <span class="swatch" style="background:${esc(m.rgb || "transparent")}" title="${esc(m.colour)}: read and kept, it decides nothing"></span>
            <select class="marks-kind" data-mark="${esc(m.id)}" aria-label="What ${esc(m.id)} is">
                ${KINDS.map((k) => `<option value="${k}"${m.kind === k ? " selected" : ""}>${k}</option>`).join("")}
            </select>
            <span class="meta">${m.by === "sorter" ? `${Number(m.sure).toFixed(2)} · ${esc(m.why)}` : `${esc(m.by)} said so; the sorter said ${esc(m.guess)}`}${m.inside ? ` · inside ${esc(m.inside)}` : ""}</span>
        </li>`).join("") : '<li class="empty">nothing on it a marker\'s stroke would be</li>';
        notes.innerHTML = read.notes.length ? read.notes.map((n) => `<li class="marks-note-row" data-mark="${esc(n.id)}">
            <span class="origin">${esc(n.id)}</span>
            <span class="meta">${n.about ? `${esc(n.lies)} ${esc(n.about)}` : "about nothing near it"}</span>
            <input class="marks-words grow" data-mark="${esc(n.id)}" value="${esc(n.words || "")}" placeholder="type what it says, Enter" aria-label="What ${esc(n.id)} says">
            ${n.offer ? `<div class="marks-offer note">if ${esc(n.offer.of)} is ${Number(n.offer.millimetres)} mm long, this picture is ${Number(n.offer.picture_mm)} mm across</div>` : ""}
        </li>`).join("") : '<li class="empty">no writing on it</li>';
    }

    async function load() {
        if (!alive) return;
        views = world ? world.views() : [];
        if (!views.some((v) => v.id === viewId)) viewId = views.length ? views[0].id : null;
        renderViews();
        if (!viewId) { read = null; render(); return; }
        try { read = await api(`${viewUrl()}/marks`); }
        catch (e) { read = null; say(`its marks could not be read: ${e.message}`, "bad"); }
        if (read && !read.marks.some((m) => m.id === chosen)) chosen = null;
        render();
    }

    async function sayKind(markId, kind) {
        try {
            read = await api(`${viewUrl()}/marks/${encodeURIComponent(markId)}`, { method: "PUT", body: JSON.stringify({ kind }) });
            render();
            const shapes = read.seen ? read.seen.shapes.length : null;
            say(`${markId} is ${kind}, as you said${read.finder === "outline" && shapes !== null ? `: ${shapes} shape${shapes === 1 ? "" : "s"} in the picture now` : ""}`);
            if (world && world.changed) world.changed();
        } catch (e) { say(`${markId}: ${e.message}`, "bad"); load(); }
    }

    async function sayWords(markId, text) {
        try {
            read = await api(`${viewUrl()}/notes/${encodeURIComponent(markId)}`, { method: "PUT", body: JSON.stringify({ text }) });
            render();
            say(`${markId} says "${text}", as you typed`);
        } catch (e) { say(`${markId}: ${e.message}`, "bad"); }
    }

    // Named for the census, which keys a place by what it listens on.
    const marks = root;
    marks.addEventListener("change", (ev) => {
        const pick = ev.target.closest(".marks-view");
        if (pick) { viewId = pick.value || null; chosen = null; load(); return; }
        const kind = ev.target.closest(".marks-kind");
        if (kind) sayKind(kind.dataset.mark, kind.value);
    });
    marks.addEventListener("click", (ev) => {
        const pick = ev.target.closest(".marks-choose");
        if (!pick) return;
        chosen = chosen === pick.dataset.mark ? null : pick.dataset.mark;
        render();
    });
    marks.addEventListener("keydown", (ev) => {
        const words = ev.target.closest(".marks-words");
        if (!words || ev.key !== "Enter") return;
        ev.preventDefault();
        const text = words.value.trim();
        if (text) sayWords(words.dataset.mark, text);
    });

    // Read as it is mounted: the first time the window is in front of a person.
    load();

    return {
        load,
        chosen: () => chosen,
        act(verb) {
            if (!verb.startsWith("say:")) return false;
            const kind = verb.slice("say:".length);
            if (!KINDS.includes(kind)) return false;
            if (!chosen) { say("choose a mark in Marks first: its number, at the start of its row", "bad"); return false; }
            sayKind(chosen, kind);
            return true;
        },
        destroy() { alive = false; root.innerHTML = ""; },
    };
}
