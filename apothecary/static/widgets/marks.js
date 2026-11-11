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
 * A photograph of a whiteboard (a view pinned at one, squared to it) shows under
 * Corners with the whiteboard's four corners as handles on it (GET .../corners). A
 * handle dragged, or nudged with the arrow keys and set with Enter, is a person's
 * word on that corner (PUT .../corners): the photograph is squared again, and the
 * view searched again, until a piece is made from it.
 *
 * A whiteboard's photograph has its whiteboard's history under When (GET
 * /sites/{s}/whiteboards/{w}/timeline): every photograph, word and piece made as a
 * tick on one strip, and a slider that scrubs it. A moment scrubbed to is the
 * whiteboard as it stood then: the newest photograph pinned by then, drawn in the
 * world, with the words given by then (?as_of=). Under it, what changed since the
 * photograph before, a row each, and Take on each row that changes a piece or
 * carries a note's words (POST .../again); and Place, which places the moment at
 * the place selected in the world (POST .../place).
 *
 * A mark's kind is the canvas ring's Panels › Pictures › Marks too (Diagram,
 * Writing, Unsure, Nothing), on the mark chosen here, and so are Earlier and Later,
 * which step the slider to the event before or after, and Place: the page hands
 * each to act().
 *
 * mountMarks(root, { base, world, log }) renders into root; `world` is what the
 * page offers: siteName(), views() -- each { id, picture, host, finder, squared, source }, the one
 * drawn at the selected place first -- changed(), called after a word that moved a
 * view's shapes, draw(host, view), which draws a view at its place, and place(), the
 * place selected in the world (a structure, or "" for the floor). log(text, kind) is
 * the page's status bar. Every read of a view's marks is handed to overlay(view,
 * read), which the page wears over its picture in the world. load() reads the views
 * and the chosen view's marks again; focusNote(view, mark) brings a note's box in front;
 * act("say:<kind>") says the chosen mark is that kind; act("earlier"), act("later")
 * and act("place") are the slider's steps and Place.
 */

const MARKUP = `
<div class="marks-ui">
    <div class="row"><select class="marks-view" aria-label="The picture whose marks are listed"></select></div>
    <div class="marks-said note"></div>
    <div class="marks-time"></div>
    <div class="marks-corners"></div>
    <div class="k">Marks</div>
    <ul class="marks-list"><li class="empty">–</li></ul>
    <div class="k">Notes</div>
    <ul class="marks-notes"><li class="empty">–</li></ul>
</div>`;

const KINDS = ["diagram", "writing", "unsure", "nothing"];
const CORNERS = ["top-left", "top-right", "bottom-right", "bottom-left"];
// How far one press of an arrow key moves a corner, as a fraction of the photograph.
const NUDGE = 0.002;

export function mountMarks(root, { base = "", world = null, log = null } = {}) {
    root.innerHTML = MARKUP;
    const $ = (sel) => root.querySelector(sel);
    const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
    const say = (text, kind = "") => { if (log) log(text, kind); };
    let views = [], viewId = null, read = null, chosen = null, alive = true;
    let corners = null, dragging = null;
    // A whiteboard's history: its timeline, the slider's place on it (per mille of
    // its span; 1000 is now), and what changed since the photograph before.
    let line = null, when = 1000, rows = [], scrubbing = null;

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
            ? views.map((v) => `<option value="${esc(v.id)}"${v.id === viewId ? " selected" : ""}>${esc(v.source || v.picture)} · ${esc(v.host === "" ? "the floor" : v.host ?? "nowhere")}</option>`).join("")
            : '<option value="">no picture pinned here yet</option>';
        pick.disabled = !views.length;
    }

    function render() {
        wear();
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

    // The whiteboard's photograph with its corners as handles; the quadrilateral
    // between them is what is squared.
    function renderCorners() {
        const held = $(".marks-corners");
        if (!corners) { held.innerHTML = ""; return; }
        const src = `${base}/photos/pictures/file?path=${encodeURIComponent(corners.source)}&px=768`;
        const pts = corners.corners.map(([x, y]) => `${(x * 100).toFixed(2)},${(y * 100).toFixed(2)}`).join(" ");
        const said = corners.made
            ? `${corners.made} piece(s) are made from it as squared: drop them to move its corners`
            : corners.by === "you" ? "placed by you; drag a corner, or nudge it with the arrow keys and Enter" : "found; drag a corner the finder got wrong, or nudge it with the arrow keys and Enter";
        held.innerHTML = `<div class="k">Corners</div>
            <div class="marks-photo" style="aspect-ratio:${corners.pixel_width} / ${corners.pixel_height}">
                <img src="${esc(src)}" alt="The photograph the picture was squared from">
                <svg viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true"><polygon points="${pts}"></polygon></svg>
                ${corners.corners.map(([x, y], i) => `<button type="button" class="marks-corner" data-handle="${i}" style="left:${(x * 100).toFixed(2)}%;top:${(y * 100).toFixed(2)}%" aria-label="The whiteboard's ${CORNERS[i]} corner"${corners.made ? " disabled" : ""}></button>`).join("")}
            </div>
            <div class="note marks-corners-said">${esc(said)}</div>`;
    }

    const STEPS = 1000;
    const ms = (iso) => new Date(iso).getTime();
    const clock = (iso) => new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
    // The moment the slider stands at: null at its end, which is now.
    function moment() {
        if (!line || !line.since || when >= STEPS) return null;
        const t0 = ms(line.since), t1 = ms(line.until);
        return new Date(t0 + ((t1 - t0) * when) / STEPS).toISOString();
    }
    function stepOf(iso) {
        const t0 = ms(line.since), t1 = ms(line.until);
        return t1 > t0 ? Math.round(((ms(iso) - t0) / (t1 - t0)) * STEPS) : STEPS;
    }
    function layerAt(at) {
        const shot = line.photographs;
        if (!shot.length) return null;
        if (!at) return shot[shot.length - 1];
        const by = shot.filter((p) => ms(p.taken_at) <= ms(at));
        return by.length ? by[by.length - 1] : shot[0];
    }

    function renderTime() {
        const held = $(".marks-time");
        if (!line || !line.events.length) { held.innerHTML = ""; return; }
        const at = moment();
        const layer = layerAt(at);
        const number = line.photographs.findIndex((p) => p.id === layer.id) + 1;
        const upto = line.events.filter((e) => !at || ms(e.at) <= ms(at));
        const count = (kind) => upto.filter((e) => e.kind === kind).length;
        const ticks = line.events.map((e) => {
            const x = stepOf(e.at);
            const tall = e.kind === "photograph" ? 24 : e.kind === "made" ? 14 : 9;
            return `<line class="tick ${esc(e.kind)}" x1="${x}" x2="${x}" y1="${24 - tall}" y2="24"><title>${esc(clock(e.at))}: ${esc(e.says)}</title></line>`;
        }).join("");
        const taking = rows.filter((r) => r.takeable);
        held.innerHTML = `<div class="k">When</div>
            <svg class="marks-strip" viewBox="0 0 ${STEPS} 24" preserveAspectRatio="none" aria-hidden="true">${ticks}<line class="now" x1="${when}" x2="${when}" y1="0" y2="24"></line></svg>
            <input type="range" class="marks-when" min="0" max="${STEPS}" step="1" value="${when}" aria-label="When: scrub the whiteboard's history">
            <div class="note marks-when-said">${at ? `As of ${esc(clock(at))}` : "Now"}: photograph ${number} of ${line.photographs.length} · ${count("word") + count("note")} word(s) given · ${count("made")} piece(s) made</div>
            ${number > 1 ? `<div class="k">Since photograph ${number - 1}</div>
            <ul class="marks-rows">${rows.length ? rows.map((r) => `<li class="marks-change" data-row="${r.number}">
                <span class="origin">${esc(r.change)}</span><span class="meta grow">${esc(r.kind)}: ${esc(r.says)}</span>
                ${r.takeable ? `<button type="button" class="marks-take" data-row="${r.number}" title="Take this change: ${esc(r.says)}">Take</button>` : ""}
            </li>`).join("") : '<li class="empty">nothing changed</li>'}</ul>
            ${taking.length ? "" : '<div class="note">No row here changes a piece: make the earlier photograph\'s shapes first, and a change to them can be taken.</div>'}` : ""}
            <div class="row"><button type="button" class="marks-place" title="Pin this moment's picture, with its words, at the place selected in the world">Place this moment at the selected place</button></div>`;
    }

    async function loadTime() {
        const view = views.find((v) => v.id === viewId);
        if (!view || !view.squared) { line = null; rows = []; renderTime(); return; }
        try { line = await api(`/sites/${encodeURIComponent(world.siteName())}/whiteboards/${encodeURIComponent(view.host)}/timeline`); }
        catch (e) { line = null; say(`its whiteboard's history could not be read: ${e.message}`, "bad"); }
        await loadRows();
        renderTime();
    }

    async function loadRows() {
        rows = [];
        if (!line) return;
        const at = line.photographs.findIndex((p) => p.id === viewId);
        if (at < 1) return;
        try { rows = (await api(`${viewUrl()}/again?since=${encodeURIComponent(line.photographs[at - 1].id)}`)).rows; }
        catch (e) { say(`what changed since the photograph before could not be read: ${e.message}`, "bad"); }
    }

    // The slider moved: the photograph of that moment drawn and listed, and its
    // words as of then.
    async function scrubTo(step) {
        when = Math.max(0, Math.min(STEPS, step));
        const layer = layerAt(moment());
        if (layer && layer.id !== viewId) {
            viewId = layer.id;
            renderViews();
            const view = views.find((v) => v.id === viewId);
            if (world && world.draw && view) world.draw(view.host, viewId);
            await loadRows();
        }
        renderTime();
        clearTimeout(scrubbing);
        scrubbing = setTimeout(readMarks, 120);
    }

    async function readMarks() {
        const at = moment();
        try { read = await api(`${viewUrl()}/marks${at ? `?as_of=${encodeURIComponent(at)}` : ""}`); }
        catch (e) { read = null; say(`its marks could not be read: ${e.message}`, "bad"); }
        if (read && !read.marks.some((m) => m.id === chosen)) chosen = null;
        render();
    }

    // What is read of a view's marks is worn over its picture in the world too.
    function wear() { if (world && world.overlay && viewId) world.overlay(viewId, read); }

    function step(by) {
        if (!line || !line.events.length) { say("no whiteboard's history here: choose a photograph of a whiteboard in Marks", "bad"); return false; }
        const stops = [...new Set(line.events.map((e) => stepOf(e.at)))].sort((a, b) => a - b);
        const next = by < 0 ? [...stops].reverse().find((s) => s < when) : stops.find((s) => s > when);
        const to = next === undefined ? (by < 0 ? 0 : STEPS) : next;
        scrubTo(to === stops[stops.length - 1] && by > 0 ? STEPS : to);
        const at = moment();
        say(at ? `the whiteboard as of ${clock(at)}` : "the whiteboard now");
        return true;
    }

    async function take(number) {
        const at = line.photographs.findIndex((p) => p.id === viewId);
        try {
            const done = await api(`${viewUrl()}/again`, { method: "POST", body: JSON.stringify({ since: line.photographs[at - 1].id, take: [number] }) });
            say(`taken: ${done.made.length ? `${done.made.join(", ")} made` : ""}${done.made.length && done.dropped.length ? "; " : ""}${done.dropped.length ? `${done.dropped.join(", ")} dropped` : ""}${!done.made.length && !done.dropped.length ? "its words carried" : ""}`);
            if (world && world.changed) await world.changed();
            await loadTime();
            readMarks();
        } catch (e) { say(`row ${number}: ${e.message}`, "bad"); }
    }

    async function place() {
        const host = world && world.place ? world.place() : null;
        if (host === null || host === undefined) { say("select a place in the world first: a structure, or the floor", "bad"); return false; }
        const at = moment();
        try {
            const placed = await api(`${viewUrl()}/place`, { method: "POST", body: JSON.stringify({ host, as_of: at }) });
            say(`${at ? `the whiteboard as of ${clock(at)}` : "the whiteboard now"} placed at ${host === "" ? "the floor" : host}: ${placed.shapes.length} shape(s) there to make`);
            if (world && world.changed) await world.changed();
            return true;
        } catch (e) { say(`placing it: ${e.message}`, "bad"); return false; }
    }

    async function loadCorners() {
        const view = views.find((v) => v.id === viewId);
        corners = null;
        if (view && view.squared) {
            try { corners = await api(`${viewUrl()}/corners`); }
            catch (e) { say(`its corners could not be read: ${e.message}`, "bad"); }
        }
        renderCorners();
    }

    async function setCorners() {
        try {
            const seen = await api(`${viewUrl()}/corners`, { method: "PUT", body: JSON.stringify({ corners: corners.corners }) });
            say(`the whiteboard squared again with your corners${seen.finder ? `: ${seen.shapes.length} shape${seen.shapes.length === 1 ? "" : "s"} found in it` : ""}`);
            // A new picture: the views, the marks and the corners read again.
            if (world && world.changed) await world.changed();
            load();
        } catch (e) { say(`its corners: ${e.message}`, "bad"); loadCorners(); }
    }

    async function load() {
        if (!alive) return;
        views = world ? world.views() : [];
        if (!views.some((v) => v.id === viewId)) viewId = views.length ? views[0].id : null;
        renderViews();
        if (!viewId) { read = null; corners = null; line = null; render(); renderCorners(); renderTime(); return; }
        loadCorners();
        await loadTime();
        const at = moment();
        try { read = await api(`${viewUrl()}/marks${at ? `?as_of=${encodeURIComponent(at)}` : ""}`); }
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
        if (pick) { viewId = pick.value || null; chosen = null; when = STEPS; load(); return; }
        const kind = ev.target.closest(".marks-kind");
        if (kind) sayKind(kind.dataset.mark, kind.value);
    });
    marks.addEventListener("click", (ev) => {
        const taking = ev.target.closest(".marks-take");
        if (taking) { take(Number(taking.dataset.row)); return; }
        if (ev.target.closest(".marks-place")) { place(); return; }
        const pick = ev.target.closest(".marks-choose");
        if (!pick) return;
        chosen = chosen === pick.dataset.mark ? null : pick.dataset.mark;
        render();
    });
    marks.addEventListener("keydown", (ev) => {
        const corner = ev.target.closest(".marks-corner");
        if (corner) { nudgeCorner(corner, ev); return; }
        const words = ev.target.closest(".marks-words");
        if (!words || ev.key !== "Enter") return;
        ev.preventDefault();
        const text = words.value.trim();
        if (text) sayWords(words.dataset.mark, text);
    });

    // A corner dragged on the photograph: where the pointer is, as a fraction of it.
    function placeCorner(i, x, y) {
        corners.corners[i] = [Math.min(1, Math.max(0, x)), Math.min(1, Math.max(0, y))];
        const handle = root.querySelector(`.marks-corner[data-handle="${i}"]`);
        if (handle) { handle.style.left = `${(corners.corners[i][0] * 100).toFixed(2)}%`; handle.style.top = `${(corners.corners[i][1] * 100).toFixed(2)}%`; }
        const outline = root.querySelector(".marks-photo polygon");
        if (outline) outline.setAttribute("points", corners.corners.map(([cx, cy]) => `${(cx * 100).toFixed(2)},${(cy * 100).toFixed(2)}`).join(" "));
    }
    function grabCorner(ev) {
        const handle = ev.target.closest(".marks-corner");
        if (!handle || handle.disabled || !corners) return;
        ev.preventDefault();
        dragging = Number(handle.dataset.handle);
        handle.setPointerCapture(ev.pointerId);
    }
    function dragCorner(ev) {
        if (dragging === null) return;
        const box = root.querySelector(".marks-photo").getBoundingClientRect();
        placeCorner(dragging, (ev.clientX - box.left) / box.width, (ev.clientY - box.top) / box.height);
    }
    function dropCorner() {
        if (dragging === null) return;
        dragging = null;
        setCorners();
    }
    function nudgeCorner(handle, ev) {
        if (!corners || handle.disabled) return;
        const steps = { ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1] };
        const i = Number(handle.dataset.handle);
        if (ev.key === "Enter") { ev.preventDefault(); setCorners(); return; }
        if (!steps[ev.key]) return;
        ev.preventDefault();
        const [dx, dy] = steps[ev.key];
        placeCorner(i, corners.corners[i][0] + dx * NUDGE, corners.corners[i][1] + dy * NUDGE);
    }
    marks.addEventListener("input", (ev) => {
        const slider = ev.target.closest(".marks-when");
        if (slider) scrubTo(Number(slider.value));
    });
    marks.addEventListener("pointerdown", grabCorner);
    marks.addEventListener("pointermove", dragCorner);
    marks.addEventListener("pointerup", dropCorner);

    // Read as it is mounted: the first time the window is in front of a person.
    load();

    return {
        load,
        chosen: () => chosen,
        /* A note's box in front, a note's badge in the world having been pressed:
         * its picture's marks listed, if another's were. */
        async focusNote(view, markId) {
            if (view !== viewId) { viewId = view; when = STEPS; await load(); }
            const box = root.querySelector(`.marks-words[data-mark="${markId}"]`);
            if (box) { box.focus(); box.scrollIntoView({ block: "nearest" }); }
            say(`${markId}: type what it says, and Enter`);
        },
        act(verb) {
            if (verb === "earlier") return step(-1);
            if (verb === "later") return step(1);
            if (verb === "place") { place(); return true; }
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
