/* The camera, and the pictures on this machine: the photo workflow from the
 * browser.
 *
 * The browser's cameras are listed (their names once the browser has been
 * allowed to use them), one is shown live, and a frame of it is kept on
 * this machine as a picture -- nothing leaves it. A kept picture is looked
 * at (POST /photos: the plain finder, an arrangement built from what it
 * found) and the arrangement opens in the world. The first sanity check of
 * a camera is to record its own surroundings: capture, look, see what the
 * finder made of the room. A camera is placed at a node of the site and
 * drawn there from then on, in every browser.
 *
 * Several pictures are gathered at once (POST /photos/gather): which are of
 * one thing, what the machine could not decide and would like a person to
 * say -- answered here with the same five sentences the answers file uses,
 * a person's word winning outright -- and the whole gathering built as one
 * arrangement the world opens.
 *
 * What the browser put on this machine, it can take back from here: a
 * picture chosen from a file picker is kept under uploads/ (a camera's frame
 * under captures/), each kept picture has a forget button, a purge forgets
 * every kept one -- never the pictures a person named -- and the cameras
 * placed in the world and the boards pinned to pieces are listed, every site's,
 * each with the button that takes it back (a pin whose site or piece is gone
 * is shown as such: this is the one place it can be seen).
 *
 * mountCamera(root, { base, world }) renders into root; `world` is what the
 * page offers: siteName(), selectedPath(), openSite(name), placed(),
 * refreshCameras(), unpinned(path).
 */

const MARKUP = `
<div class="camera">
    <div class="row">
        <select id="cam-pick" title="The browser's cameras"><option value="">— no camera —</option></select>
        <button type="button" id="cam-allow" title="Ask the browser to use its cameras; their names appear once allowed, and the chosen one shows here">Allow cameras</button>
        <button type="button" id="cam-refresh" title="List the cameras again">⟳</button>
    </div>
    <video id="cam-preview" autoplay muted playsinline hidden></video>
    <div class="note" id="cam-note">No camera in use. Allow cameras, then pick one.</div>
    <div class="row">
        <label>name <input id="cam-name" value="surroundings" size="12" title="What the arrangement built from the next capture is called"></label>
        <label>width <input id="cam-width" type="number" min="1" step="10" placeholder="mm across" size="7" title="How wide the whole picture is in the real world, in millimetres; without it, nothing has a real size"></label>
        <button type="button" id="cam-capture" title="Keep a frame of the camera as a picture on this machine">📷 Capture</button>
        <button type="button" id="cam-look" class="warm" title="Capture, look at it, and open what was found in the world: the camera's own surroundings, as the finder sees them">👁 Look</button>
    </div>
    <div class="row">
        <span class="note" id="cam-place-note">not placed in the world</span>
        <span class="grow"></span>
        <button type="button" id="cam-place" title="Stand this camera at the selected piece: the world draws it there">📍 Place at selected</button>
        <button type="button" id="cam-unplace" title="Take this camera out of the world">Unplace</button>
    </div>
    <div class="k">Pictures on this machine</div>
    <div id="pic-list" class="pics"><span class="empty">none yet</span></div>
    <div class="row">
        <label><input type="checkbox" id="pic-all"> all</label>
        <button type="button" id="pic-refresh" title="List the pictures again">⟳</button>
        <span class="grow"></span>
        <button type="button" id="pic-gather" title="Which of the ticked pictures are of the same thing, and what the machine would ask you">Gather</button>
        <button type="button" id="pic-open" class="warm" title="Build one arrangement out of the ticked pictures and open it in the world">Open as one</button>
    </div>
    <div class="row">
        <label class="grow">add <input type="file" id="pic-file" accept="image/png,image/jpeg,image/gif,image/webp,image/bmp,image/tiff" multiple title="Add pictures from this browser: kept under uploads/ in the picture folder, on this machine, as you named them"></label>
        <button type="button" id="pic-purge" title="Forget every picture the browser put here -- captures and uploads. The folder's own pictures stay">Purge kept</button>
    </div>
    <div id="gather-out"></div>
    <textarea id="gather-answers" rows="3" placeholder="What you know, one sentence a line: 'a and b are the same thing', 'a and b are parts of one thing', 'a and b are not related', 'a is not worth using', 'a is worth using anyway'" title="Your word wins outright, and it carries"></textarea>
    <div class="k">Cameras in the world</div>
    <div id="cam-placed" class="kept"><span class="empty">none placed</span></div>
    <div class="k">Boards pinned to pieces <button type="button" id="pin-refresh" title="List the pins again">⟳</button></div>
    <div id="pin-list" class="kept"><span class="empty">none pinned</span></div>
</div>`;

export function mountCamera(root, { base = "", world = null, log = null } = {}) {
    root.innerHTML = MARKUP;
    const $ = (id) => root.querySelector(`#${CSS.escape(id)}`);
    const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
    const say = (text, kind = "") => { const n = $("cam-note"); n.textContent = text; n.className = "note " + kind; if (log) log(text); };
    const state = { cameras: [], stream: null, chosen: "", pictures: [], gathered: null, answers: "", placed: [], pins: [] };

    async function api(path, opts = {}) {
        const r = await fetch(base + path, { headers: { "Content-Type": "application/json" }, ...opts });
        const body = await r.json().catch(() => ({}));
        if (!r.ok) throw new Error(typeof body.detail === "string" ? body.detail : (body.detail ? JSON.stringify(body.detail) : r.statusText));
        return body;
    }

    // --- the cameras ----------------------------------------------------------------
    async function listCameras() {
        if (!navigator.mediaDevices || !navigator.mediaDevices.enumerateDevices) { say("this browser has no cameras to offer", "bad"); return; }
        const all = await navigator.mediaDevices.enumerateDevices();
        state.cameras = all.filter((d) => d.kind === "videoinput");
        const sel = $("cam-pick");
        sel.innerHTML = state.cameras.length
            ? state.cameras.map((c, i) => `<option value="${esc(c.deviceId)}">${esc(c.label || `camera ${i + 1} (allow to see its name)`)}</option>`).join("")
            : '<option value="">— no camera —</option>';
        if (state.chosen && state.cameras.some((c) => c.deviceId === state.chosen)) sel.value = state.chosen;
        renderPlacement();
    }
    function stopStream() {
        if (state.stream) { for (const t of state.stream.getTracks()) t.stop(); state.stream = null; }
        $("cam-preview").srcObject = null;
        $("cam-preview").hidden = true;
    }
    async function useCamera(deviceId) {
        stopStream();
        state.chosen = deviceId || "";
        if (!deviceId) { say("No camera in use."); renderPlacement(); return; }
        try {
            state.stream = await navigator.mediaDevices.getUserMedia({ video: { deviceId: { exact: deviceId } }, audio: false });
            $("cam-preview").srcObject = state.stream;
            $("cam-preview").hidden = false;
            await listCameras();  // names arrive once a camera is in use
            const cam = state.cameras.find((c) => c.deviceId === deviceId);
            say(`${cam && cam.label ? cam.label : "camera"} is live. Capture keeps a frame here; Look opens what the finder makes of it.`);
        } catch (e) { say(`camera: ${e.message}`, "bad"); }
        renderPlacement();
    }
    $("cam-allow").onclick = async () => {
        try {
            const probe = await navigator.mediaDevices.getUserMedia({ video: true, audio: false });
            for (const t of probe.getTracks()) t.stop();
            await listCameras();
            const first = state.cameras[0];
            if (first && !state.chosen) { $("cam-pick").value = first.deviceId; await useCamera(first.deviceId); }
        } catch (e) { say(`the browser did not allow it: ${e.message}`, "bad"); }
    };
    $("cam-refresh").onclick = listCameras;
    $("cam-pick").addEventListener("change", () => useCamera($("cam-pick").value));

    function frame() {
        const video = $("cam-preview");
        if (!state.stream || !video.videoWidth) return Promise.reject(new Error("no camera is live"));
        const canvas = document.createElement("canvas");
        canvas.width = video.videoWidth; canvas.height = video.videoHeight;
        canvas.getContext("2d").drawImage(video, 0, 0);
        return new Promise((resolve, reject) => canvas.toBlob((b) => (b ? resolve(b) : reject(new Error("no frame"))), "image/png"));
    }
    async function capture() {
        const blob = await frame();
        const name = ($("cam-name").value.trim() || "capture");
        const r = await fetch(`${base}/photos/pictures?name=${encodeURIComponent(name)}`, { method: "POST", body: blob, headers: { "Content-Type": "image/png" } });
        const kept = await r.json().catch(() => ({}));
        if (!r.ok) throw new Error(kept.detail || r.statusText);
        say(`kept ${kept.name} (${Math.round(kept.size / 1024)} kB) on this machine`);
        await loadPictures();
        return kept;
    }
    $("cam-capture").onclick = async () => { try { await capture(); } catch (e) { say(e.message, "bad"); } };
    $("cam-look").onclick = async () => {
        try {
            const kept = await capture();
            const name = ($("cam-name").value.trim() || "capture").replace(/[^A-Za-z0-9_-]+/g, "_");
            const width = Number($("cam-width").value) || null;
            const album = await api("/photos", { method: "POST", body: JSON.stringify({ picture: kept.path, name, width_mm: width }) });
            const pieces = Object.keys(album.pieces || {}).length;
            say(`${name}: ${pieces} piece(s) found${album.sized ? "" : " (no real size: give a width)"}; opening it in the world`);
            if (world && world.openSite) world.openSite(name);
        } catch (e) { say(e.message, "bad"); }
    };

    // --- the camera in the world ----------------------------------------------------------
    function renderPlacement() {
        const placed = world && world.placed ? world.placed() : [];
        const mine = placed.find((c) => c.id === state.chosen);
        $("cam-place-note").textContent = !state.chosen ? "no camera chosen" : (mine ? `placed at ${mine.path} in ${mine.site}` : "not placed in the world");
        $("cam-place").disabled = !state.chosen || !(world && world.selectedPath && world.selectedPath());
        $("cam-unplace").disabled = !mine;
        loadPlaced();
    }
    // Every camera placed in the world, whatever site it stands in and whichever
    // browser placed it -- each one taken back from here.
    async function loadPlaced() {
        try { state.placed = await api("/cameras"); } catch (e) { state.placed = []; }
        renderPlaced();
    }
    function renderPlaced() {
        const list = $("cam-placed");
        if (!state.placed.length) { list.innerHTML = '<span class="empty">none placed</span>'; return; }
        const here = world && world.siteName ? world.siteName() : "";
        list.innerHTML = state.placed.map((c) => `<div class="kept-row${c.site === here ? " here" : ""}${c.id === state.chosen ? " mine" : ""}"><span title="${esc(c.id)}">📷 ${esc(c.label || "camera")} · ${esc(c.site)} › ${esc(c.path)}${c.id === state.chosen ? " · this browser's" : ""}</span><button type="button" class="cam-unplace-one" data-id="${esc(c.id)}" title="Take this camera out of the world">Unplace</button></div>`).join("");
    }
    async function unplace(id) {
        await api(`/cameras/${encodeURIComponent(id)}`, { method: "DELETE" });
        if (world && world.refreshCameras) await world.refreshCameras(); else await loadPlaced();
    }
    $("cam-placed").addEventListener("click", async (ev) => {
        const b = ev.target.closest("button.cam-unplace-one"); if (!b) return;
        try { await unplace(b.dataset.id); say("camera taken out of the world"); } catch (e) { say(e.message, "bad"); }
    });
    $("cam-place").onclick = async () => {
        const path = world && world.selectedPath ? world.selectedPath() : null;
        if (!state.chosen || !path) { say("choose a camera and select a piece to stand it at", "bad"); return; }
        const cam = state.cameras.find((c) => c.deviceId === state.chosen);
        try {
            await api(`/cameras/${encodeURIComponent(state.chosen)}`, { method: "PUT", body: JSON.stringify({ label: (cam && cam.label) || "camera", site: world.siteName(), path }) });
            say(`camera placed at ${path}`);
            if (world.refreshCameras) await world.refreshCameras();
            renderPlacement();
        } catch (e) { say(e.message, "bad"); }
    };
    $("cam-unplace").onclick = async () => {
        try {
            await unplace(state.chosen);
            say("camera taken out of the world");
            renderPlacement();
        } catch (e) { say(e.message, "bad"); }
    };

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
    $("pic-refresh").onclick = loadPictures;
    async function forget(path) {
        await api(`/photos/pictures/${path.split("/").map(encodeURIComponent).join("/")}`, { method: "DELETE" });
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
        say(`forgot ${gone.forgotten.length} kept picture(s); ${gone.left} of the folder's own stay`);
        await loadPictures();
        return gone;
    }
    $("pic-purge").onclick = () => purge().catch((e) => say(e.message, "bad"));
    $("pic-all").addEventListener("change", () => { for (const i of root.querySelectorAll("#pic-list input[type=checkbox]")) i.checked = $("pic-all").checked; });
    async function gather(build) {
        const pictures = ticked();
        if (pictures.length < 2) { say("tick at least two pictures to gather", "bad"); return; }
        const out = $("gather-out");
        out.innerHTML = '<span class="empty">gathering…</span>';
        try {
            const name = "gathered_" + new Date().toISOString().slice(0, 16).replace(/[-:T]/g, "");
            state.gathered = await api("/photos/gather", { method: "POST", body: JSON.stringify({ pictures, answers: $("gather-answers").value, build, name }) });
            renderGathering();
            if (build && state.gathered.site && world && world.openSite) { say(`opening ${state.gathered.site} in the world`); world.openSite(state.gathered.site); }
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
        gather(false);
    });
    $("pic-gather").onclick = () => gather(false);
    $("pic-open").onclick = () => gather(true);

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

    listCameras().catch(() => {});
    loadPictures();
    renderPlacement();
    loadPins();

    // A verb chosen on the ring goes through the same button a click would.
    const BUTTON_FOR = { allow: "cam-allow", capture: "cam-capture", look: "cam-look", place: "cam-place", unplace: "cam-unplace", gather: "pic-gather", open: "pic-open", add: "pic-file", purge: "pic-purge" };
    function act(verb) {
        const btn = $(BUTTON_FOR[verb]);
        if (!btn) return false;
        if (btn.disabled) { say(`${verb}: not now (${$("cam-place-note").textContent})`, "bad"); return true; }
        btn.click();
        return true;
    }

    const handle = {
        state, listCameras, useCamera, capture, loadPictures, gather, renderPlacement, act,
        addFiles, forget, purge, unplace, loadPlaced, loadPins, unpin,
        chosen: () => state.chosen,
        live: () => !!state.stream,
        destroy() { stopStream(); root.innerHTML = ""; },
    };
    return handle;
}
