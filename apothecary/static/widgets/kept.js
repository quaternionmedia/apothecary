/* Kept: what a page placed, pinned or kept on this machine, every site's, each
 * taken back from its row. The one list §6 of the draft record *Personal data
 * stays on the device* asks for: what a page placed or pinned is listed by the
 * same page, every site's, and taken back the same way; a page forgets only
 * what the browser put there.
 *
 * A stub of the pictures plan's Phase 5: the cameras, views and boards pinned
 * (GET /placed) and the kept pictures (captures/ and uploads/ under the picture
 * root), each row naming its site and carrying the one button that takes it
 * back, and Purge. A row on another site is taken back from here without
 * switching the site. The folder's own pictures are a person's and are not
 * listed: only a person removes them.
 *
 * mountKept(root, { base, world, log }) renders into root; `world` is what the
 * page offers: siteName(), changed(site) (something pinned in that site was
 * taken back), unpinned(site, path) (a board's pin), picturesChanged().
 * log(text, kind) is the page's status bar; kind "bad" is a refusal.
 */

const MARKUP = `
<div class="camera kept-panel">
    <div id="kept-list">
        <div class="k">Pinned, every site's <button type="button" id="kept-refresh" title="List what is pinned and kept again">⟳</button></div>
        <div id="kept-pins" class="kept"><span class="empty">none pinned</span></div>
        <div class="k">Kept pictures</div>
        <div id="kept-pictures" class="kept"><span class="empty">none kept</span></div>
    </div>
    <div class="row">
        <span class="grow"></span>
        <button type="button" id="kept-purge" title="Forget every picture the browser put here -- captures and uploads. The folder's own pictures stay">Purge kept</button>
    </div>
</div>`;

export function mountKept(root, { base = "", world = null, log = null } = {}) {
    root.innerHTML = MARKUP;
    const $ = (id) => root.querySelector(`#${CSS.escape(id)}`);
    const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
    const say = (text, kind = "") => { if (log) log(text, kind); else console.log(text); };
    const state = { cameras: [], views: [], boards: [], pictures: [] };

    async function api(path, opts = {}) {
        const r = await fetch(base + path, { headers: { "Content-Type": "application/json" }, ...opts });
        const body = await r.json().catch(() => ({}));
        if (!r.ok) throw new Error(typeof body.detail === "string" ? body.detail : (body.detail ? JSON.stringify(body.detail) : r.statusText));
        return body;
    }

    const at = (host) => host || "the floor";
    const segs = (path) => path.split("/").map(encodeURIComponent).join("/");
    function row(kind, site, stale, text, button) {
        const here = world && world.siteName ? world.siteName() : "";
        return `<div class="kept-row ${kind}${site === here ? " here" : ""}${stale ? " stale" : ""}" data-site="${esc(site)}"><span>${text}</span>${button}</div>`;
    }
    function render() {
        const gone = (found) => (found ? "" : " · gone");
        const boardNote = (b) => (!b.site_known ? " · site gone" : !b.node_found ? " · piece gone" : "");
        const pins = state.cameras.map((c) => row("camera", c.site, !c.host_found,
            `📷 ${esc(c.label || "camera")} · ${esc(c.site)} › ${esc(at(c.path))}${gone(c.host_found)}`,
            `<button type="button" class="kept-camera-unpin" data-id="${esc(c.id)}" title="Unpin this camera; its views stay">Unpin</button>`))
            + state.views.map((l) => row("view", l.site, !l.host_found,
                `🖼 ${esc(l.picture)} · ${esc(l.site)} › ${esc(at(l.host))}${gone(l.host_found)}`,
                `<button type="button" class="kept-view-unpin" data-site="${esc(l.site)}" data-id="${esc(l.id)}" title="Unpin this view; its picture and any pieces made from it stay">Unpin</button>`))
            + state.boards.map((b) => row("board", b.site, !(b.site_known && b.node_found),
                `📌 ${esc(b.site)} › ${esc(b.path)} ← ${esc(b.identity)}${boardNote(b)}`,
                `<button type="button" class="kept-board-unpin" data-site="${esc(b.site)}" data-path="${esc(b.path)}" title="Take this board's pin back">Unpin</button>`));
        $("kept-pins").innerHTML = pins || '<span class="empty">none pinned</span>';
        const HOW = { capture: "captured", upload: "added" };
        $("kept-pictures").innerHTML = state.pictures.map((p) => `<div class="kept-row picture" data-path="${esc(p.path)}"><img src="${base}/photos/pictures/file?path=${encodeURIComponent(p.path)}&px=64" alt="" loading="lazy"><span title="${esc(p.path)}">${esc(p.path)} · ${HOW[p.kept] || "kept"}</span><button type="button" class="kept-forget" data-path="${esc(p.path)}" title="Forget this picture; its views are unpinned">Forget</button></div>`).join("")
            || '<span class="empty">none kept</span>';
    }

    async function load() {
        const [placed, pictures] = await Promise.all([
            api("/placed").catch((e) => { say(e.message, "bad"); return {}; }),
            api("/photos/pictures").catch((e) => { say(e.message, "bad"); return []; }),
        ]);
        state.cameras = placed.cameras || [];
        state.views = placed.views || [];
        state.boards = placed.boards || [];
        state.pictures = pictures.filter((p) => p.kept);
        render();
        return state;
    }

    // Each take-back names its own site: nothing here switches the site on screen.
    async function unpinCamera(id) {
        const cam = state.cameras.find((c) => c.id === id);
        await api(`/cameras/${encodeURIComponent(id)}`, { method: "DELETE" });
        say(`camera unpinned${cam ? ` from ${cam.site} › ${at(cam.path)}` : ""}; its views stay`);
        if (world && world.changed) await world.changed(cam ? cam.site : null);
    }
    async function unpinView(site, id) {
        await api(`/sites/${encodeURIComponent(site)}/views/${encodeURIComponent(id)}`, { method: "DELETE" });
        say(`view unpinned in ${site}; its picture and any pieces made from it stay`);
        if (world && world.changed) await world.changed(site);
    }
    async function unpinBoard(site, path) {
        await api(`/firmware/pins/${encodeURIComponent(site)}/${path.split(".").map(encodeURIComponent).join(".")}`, { method: "DELETE" });
        say(`${site} › ${path}: pin taken back`);
        if (world && world.unpinned) world.unpinned(site, path);
    }
    async function forget(path) {
        await api(`/photos/pictures/${segs(path)}`, { method: "DELETE" });
        say(`forgot ${path}; its views are unpinned`);
        if (world && world.changed) await world.changed(null);
        if (world && world.picturesChanged) world.picturesChanged();
    }
    async function purge() {
        const kept = state.pictures.length;
        if (!kept) { say("nothing kept from the browser to forget", "bad"); return null; }
        if (!confirm(`Forget every picture the browser put here? ${kept} kept picture(s) go; the folder's own stay.`)) return null;
        const gone = await api("/photos/pictures", { method: "DELETE" });
        say(`forgot ${gone.forgotten.length} kept picture(s); ${gone.left} of the folder's own stay`);
        if (world && world.changed) await world.changed(null);
        if (world && world.picturesChanged) world.picturesChanged();
        await load();
        return gone;
    }

    $("kept-list").addEventListener("click", async (ev) => {
        const b = ev.target.closest("button.kept-camera-unpin, button.kept-view-unpin, button.kept-board-unpin, button.kept-forget");
        if (!b) return;
        try {
            if (b.classList.contains("kept-camera-unpin")) await unpinCamera(b.dataset.id);
            else if (b.classList.contains("kept-view-unpin")) await unpinView(b.dataset.site, b.dataset.id);
            else if (b.classList.contains("kept-board-unpin")) await unpinBoard(b.dataset.site, b.dataset.path);
            else await forget(b.dataset.path);
        } catch (e) { say(e.message, "bad"); }
        await load();
    });
    $("kept-refresh").onclick = () => load();
    $("kept-purge").onclick = () => purge().catch((e) => say(e.message, "bad"));

    load();

    return {
        state, load, unpinCamera, unpinView, unpinBoard, forget, purge,
        destroy() { root.innerHTML = ""; },
    };
}
