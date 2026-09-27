/* What is left of the camera panel until the Kept panel: the pictures on this
 * machine, the gathering's report, and every pin a page made, every site's.
 *
 * The camera itself is pinned, shown live, looked and kept with from its
 * host's ring (Camera › Pin here, Live, Look, Keep; apothecary/static/pictures.js),
 * and a picture is pinned at a place by a drop, a paste or Picture › Add. What
 * stays here is what §6 of the draft record *Personal data stays on the device*
 * asks for: what the browser put on this machine, taken back from the list that
 * shows it. A picture chosen from the file picker is kept under uploads/ and
 * pinned nowhere; each kept picture has a forget button; a purge forgets every
 * kept one -- never the pictures a person named. The cameras, the looks and the
 * boards pinned, every site's, are listed each with the button that takes it
 * back (a pin whose site or piece is gone is shown as such: this is the one
 * place it can be seen).
 *
 * Several pictures are gathered at once (POST /photos/gather): which are of
 * one thing, what the machine could not decide and would like a person to
 * say -- answered here with the same five sentences the answers file uses. A
 * report only: nothing is built or opened from it.
 *
 * mountCamera(root, { base, world, log }) renders into root; `world` is what
 * the page offers: siteName(), refreshCameras() (the site's cameras and looks,
 * fetched again), unpinned(path). log(text, kind) is the page's status bar,
 * the only place a message is written; kind "bad" is a refusal.
 */

const MARKUP = `
<div class="camera">
    <div class="k">Pictures on this machine</div>
    <div id="pic-list" class="pics"><span class="empty">none yet</span></div>
    <div class="row">
        <label><input type="checkbox" id="pic-all"> all</label>
        <span class="grow"></span>
        <button type="button" id="pic-gather" title="Which of the ticked pictures are of the same thing, and what the machine would ask you">Gather</button>
    </div>
    <div class="row">
        <label class="grow">add <input type="file" id="pic-file" accept="image/png,image/jpeg,image/gif,image/webp,image/bmp,image/tiff" multiple title="Add pictures from this browser: kept under uploads/ in the picture folder, on this machine, as you named them, and pinned nowhere"></label>
        <button type="button" id="pic-purge" title="Forget every picture the browser put here -- captures and uploads. The folder's own pictures stay">Purge kept</button>
    </div>
    <div id="gather-out"></div>
    <textarea id="gather-answers" rows="3" placeholder="What you know, one sentence a line: 'a and b are the same thing', 'a and b are parts of one thing', 'a and b are not related', 'a is not worth using', 'a is worth using anyway'" title="Your word wins outright, and it carries"></textarea>
    <div class="k">Cameras and looks pinned in the world</div>
    <div id="cam-placed" class="kept"><span class="empty">none pinned</span></div>
    <div class="k">Boards pinned to pieces <button type="button" id="pin-refresh" title="List the pins again">⟳</button></div>
    <div id="pin-list" class="kept"><span class="empty">none pinned</span></div>
</div>`;

export function mountCamera(root, { base = "", world = null, log = null } = {}) {
    root.innerHTML = MARKUP;
    const $ = (id) => root.querySelector(`#${CSS.escape(id)}`);
    const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
    // Every message is said once, where the page says everything: its status
    // bar. A refusal is kind "bad", and the page shows it as an error.
    const say = (text, kind = "") => { if (log) log(text, kind); else console.log(text); };
    const state = { pictures: [], gathered: null, answers: "", placed: { cameras: [], looks: [] }, pins: [] };

    async function api(path, opts = {}) {
        const r = await fetch(base + path, { headers: { "Content-Type": "application/json" }, ...opts });
        const body = await r.json().catch(() => ({}));
        if (!r.ok) throw new Error(typeof body.detail === "string" ? body.detail : (body.detail ? JSON.stringify(body.detail) : r.statusText));
        return body;
    }

    // --- every camera and look pinned, every site's --------------------------------------
    // Each taken back from its row, whatever site it stands in and whichever
    // browser pinned it. Asked for when the panel is mounted and whenever the
    // world's pins are fetched again.
    async function loadPlaced() {
        try { const got = await api("/placed"); state.placed = { cameras: got.cameras || [], looks: got.looks || [] }; }
        catch (e) { state.placed = { cameras: [], looks: [] }; }
        renderPlaced();
    }
    const at = (host) => host || "the floor";
    function renderPlaced() {
        const list = $("cam-placed");
        const { cameras, looks } = state.placed;
        if (!cameras.length && !looks.length) { list.innerHTML = '<span class="empty">none pinned</span>'; return; }
        const here = world && world.siteName ? world.siteName() : "";
        const gone = (row) => (row.host_found ? "" : " · gone");
        list.innerHTML = cameras.map((c) => `<div class="kept-row${c.site === here ? " here" : ""}${c.host_found ? "" : " stale"}"><span title="${esc(c.id)}">📷 ${esc(c.label || "camera")} · ${esc(c.site)} › ${esc(at(c.path))}${gone(c)}</span><button type="button" class="cam-unplace-one" data-id="${esc(c.id)}" title="Unpin this camera">Unpin</button></div>`).join("")
            + looks.map((l) => `<div class="kept-row look${l.site === here ? " here" : ""}${l.host_found ? "" : " stale"}" data-look="${esc(l.id)}"><span title="${esc(l.id)}">🖼 ${esc(l.picture)} · ${esc(l.site)} › ${esc(at(l.host))}${gone(l)}</span><button type="button" class="look-unpin-one" data-site="${esc(l.site)}" data-id="${esc(l.id)}" title="Unpin this look; its picture and any pieces made from it stay">Unpin</button></div>`).join("");
    }
    $("cam-placed").addEventListener("click", async (ev) => {
        const b = ev.target.closest("button.cam-unplace-one, button.look-unpin-one"); if (!b) return;
        try {
            if (b.classList.contains("look-unpin-one")) {
                await api(`/sites/${encodeURIComponent(b.dataset.site)}/looks/${encodeURIComponent(b.dataset.id)}`, { method: "DELETE" });
                say("look unpinned; its picture and any pieces made from it stay");
            } else {
                await api(`/cameras/${encodeURIComponent(b.dataset.id)}`, { method: "DELETE" });
                say("camera unpinned; its looks stay");
            }
            if (world && world.refreshCameras) await world.refreshCameras();
            await loadPlaced();
        } catch (e) { say(e.message, "bad"); }
    });

    // --- the pictures on this machine, and gathering them -------------------------------
    function ticked() { return [...root.querySelectorAll("#pic-list input[type=checkbox]:checked")].map((i) => i.value); }
    const HOW_KEPT = { capture: " · captured", upload: " · added" };
    function renderPictures() {
        const list = $("pic-list");
        if (!state.pictures.length) { list.innerHTML = '<span class="empty">no pictures in the folder yet — capture one, add some, or put some there</span>'; return; }
        // A kept picture -- one the browser put here -- has a forget button; the
        // folder's own pictures are a person's, and only a person removes them.
        list.innerHTML = state.pictures.map((p) => `<label class="pic" title="${esc(p.path)} · ${Math.round(p.size / 1024)} kB"><input type="checkbox" value="${esc(p.path)}"><img src="${base}/photos/pictures/file?path=${encodeURIComponent(p.path)}" alt="${esc(p.name)}" loading="lazy"><span>${esc(p.name)}${HOW_KEPT[p.kept] || ""}</span>${p.kept ? `<button type="button" class="pic-forget" data-path="${esc(p.path)}" title="Forget this picture (${esc(p.path)})">✕</button>` : ""}</label>`).join("");
    }
    async function loadPictures() {
        try { state.pictures = await api("/photos/pictures"); } catch (e) { state.pictures = []; say(e.message, "bad"); }
        renderPictures();
    }
    async function forget(path) {
        await api(`/photos/pictures/${path.split("/").map(encodeURIComponent).join("/")}`, { method: "DELETE" });
        // Forgetting a kept picture unpins its looks: the world draws them no more.
        if (world && world.refreshCameras) world.refreshCameras();
        await loadPictures();
    }
    $("pic-list").addEventListener("click", async (ev) => {
        const b = ev.target.closest("button.pic-forget"); if (!b) return;
        ev.preventDefault();  // the button sits in the picture's label: not a tick
        try { await forget(b.dataset.path); say(`forgot ${b.dataset.path}`); } catch (e) { say(e.message, "bad"); }
    });
    // Files a person chose, kept under uploads/ as they named them: one request
    // per file, the bytes as the body, judged a picture on arrival by its bytes.
    async function addFiles(files) {
        const chosen = [...(files || [])];
        if (!chosen.length) return [];
        const kept = [], refused = [];
        for (const file of chosen) {
            if (file.size > 16 * 1024 * 1024) { refused.push(`${file.name}: larger than 16 MB`); continue; }
            try {
                const r = await fetch(`${base}/photos/pictures?name=${encodeURIComponent(file.name)}&kept=upload`, { method: "POST", body: file, headers: { "Content-Type": file.type || "application/octet-stream" } });
                const body = await r.json().catch(() => ({}));
                if (!r.ok) throw new Error(body.detail || r.statusText);
                kept.push(body);
            } catch (e) { refused.push(`${file.name}: ${e.message}`); }
        }
        say(`added ${kept.length} picture(s) on this machine` + (refused.length ? ` — refused: ${refused.join("; ")}` : ""), refused.length ? "bad" : "");
        await loadPictures();
        return kept;
    }
    $("pic-file").addEventListener("change", async (ev) => { await addFiles(ev.target.files); ev.target.value = ""; });
    async function purge() {
        const kept = state.pictures.filter((p) => p.kept);
        if (!kept.length) { say("nothing kept from the browser to forget", "bad"); return null; }
        const own = state.pictures.length - kept.length;
        if (!confirm(`Forget every picture the browser put here? ${kept.length} kept picture(s) go; the folder's own (${own}) stay.`)) return null;
        const gone = await api("/photos/pictures", { method: "DELETE" });
        if (world && world.refreshCameras) world.refreshCameras();
        say(`forgot ${gone.forgotten.length} kept picture(s); ${gone.left} of the folder's own stay`);
        await loadPictures();
        return gone;
    }
    $("pic-purge").onclick = () => purge().catch((e) => say(e.message, "bad"));
    $("pic-all").addEventListener("change", () => { for (const i of root.querySelectorAll("#pic-list input[type=checkbox]")) i.checked = $("pic-all").checked; });
    async function gather() {
        const pictures = ticked();
        if (pictures.length < 2) { say("tick at least two pictures to gather", "bad"); return; }
        const out = $("gather-out");
        out.innerHTML = '<span class="empty">gathering…</span>';
        try {
            const name = "gathered_" + new Date().toISOString().slice(0, 16).replace(/[-:T]/g, "");
            state.gathered = await api("/photos/gather", { method: "POST", body: JSON.stringify({ pictures, answers: $("gather-answers").value, build: false, name }) });
            renderGathering();
        } catch (e) { out.innerHTML = `<span class="bad">${esc(e.message)}</span>`; }
    }
    function renderGathering() {
        const g = state.gathered, out = $("gather-out");
        if (!g) { out.innerHTML = ""; return; }
        const groups = g.clusters.map((c) => `<div class="group ${esc(c.kind)}"><b>${esc(c.name)}</b> · ${esc(c.kind)}${c.contested ? " · contested" : ""} · ${c.pictures.map(esc).join(", ")}</div>`).join("");
        const aside = Object.entries(g.set_aside || {}).map(([p, why]) => `<div class="aside">${esc(p)}: ${esc(why)}</div>`).join("");
        const questions = g.questions.map((q, i) => `<div class="question" data-q="${i}"><div>${esc(q.sentence)} <span class="note">${esc(q.worth)}</span></div><div class="row">${q.answers.map((a) => `<button type="button" class="answer" data-answer="${esc(a)}">${esc(a.replace(`${q.left} and ${q.right} `, ""))}</button>`).join("")}</div></div>`).join("");
        out.innerHTML = `<div class="k">Groups</div>${groups || '<span class="empty">none</span>'}${aside}`
            + (g.questions.length ? `<div class="k">Worth your word (${g.questions.length}${g.withheld ? `, ${g.withheld} more held back` : ""})</div>${questions}` : `<div class="note">nothing left to ask</div>`)
            + `<details><summary>the report</summary><pre>${esc(g.report)}</pre></details>`;
    }
    $("gather-out").addEventListener("click", (ev) => {
        const b = ev.target.closest("button.answer"); if (!b) return;
        const box = $("gather-answers");
        box.value = (box.value.trim() ? box.value.trim() + "\n" : "") + b.dataset.answer + "\n";
        gather();
    });
    $("pic-gather").onclick = () => gather();

    // --- the boards pinned to pieces, every site's ---------------------------------------
    async function loadPins() {
        try { const got = await api("/firmware/pins"); state.pins = got.pins; state.pinsProblem = got.problem || null; }
        catch (e) { state.pins = []; state.pinsProblem = e.message; }
        renderPins();
    }
    function pinNote(p) {
        if (!p.site_known) return "site gone";
        if (!p.node_found) return "piece gone";
        if (p.device) return `${p.device.port}`;
        // No scan at all is not the same as a board that is unplugged.
        return state.pinsProblem ? `cannot look: ${state.pinsProblem}` : "not connected";
    }
    function renderPins() {
        const list = $("pin-list");
        if (!state.pins.length) { list.innerHTML = '<span class="empty">none pinned</span>'; return; }
        const here = world && world.siteName ? world.siteName() : "";
        list.innerHTML = state.pins.map((p) => `<div class="kept-row${p.site === here ? " here" : ""}${p.site_known && p.node_found ? "" : " stale"}"><span title="pinned ${esc(p.bound_at)}">📌 ${esc(p.site)} › ${esc(p.path)} ← ${esc(p.identity)} · ${esc(pinNote(p))}</span><button type="button" class="pin-unpin" data-site="${esc(p.site)}" data-path="${esc(p.path)}" title="Take this pin back">Unpin</button></div>`).join("");
    }
    async function unpin(site, path) {
        await api(`/firmware/pins/${encodeURIComponent(site)}/${path.split(".").map(encodeURIComponent).join(".")}`, { method: "DELETE" });
        if (world && world.unpinned && world.siteName && world.siteName() === site) world.unpinned(path);
        await loadPins();
    }
    $("pin-list").addEventListener("click", async (ev) => {
        const b = ev.target.closest("button.pin-unpin"); if (!b) return;
        try { await unpin(b.dataset.site, b.dataset.path); say(`${b.dataset.path}: pin taken back`); } catch (e) { say(e.message, "bad"); }
    });
    $("pin-refresh").onclick = loadPins;

    loadPictures();
    loadPlaced();
    loadPins();

    // A verb chosen on the ring goes through the same button a click would.
    const BUTTON_FOR = { gather: "pic-gather" };
    function act(verb) {
        const btn = $(BUTTON_FOR[verb]);
        if (!btn) return false;
        btn.click();
        return true;
    }

    const handle = {
        state, loadPictures, gather, act, addFiles, forget, purge, loadPlaced, loadPins, unpin,
        destroy() { root.innerHTML = ""; },
    };
    return handle;
}
