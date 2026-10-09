/* Pinned: what a page pinned on this machine -- cameras, views, boards -- every
 * site's, each taken back from its row. A section of the Site panel, and the
 * pins half of the one list §6 of the draft record *Personal data stays on the
 * device* asks for: what a page placed or pinned is listed by the same page,
 * every site's, and taken back the same way. The pictures the browser kept are
 * the other half, in Pictures (widgets/picture_list.js), each forgotten from its
 * row there.
 *
 * Each row names its site and carries the one button that takes it back; a row
 * on another site is taken back from here without switching the site, and a pin
 * whose site or piece is gone is shown as such (GET /placed says so).
 *
 * mountPinned(root, { base, world, log }) renders into root; `world` is what the
 * page offers: siteName(), changed(site) (something pinned in that site was taken
 * back), unpinned(site, path) (a board's pin). log(text, kind) is the page's
 * status bar; kind "bad" is a refusal. The list is fetched when it mounts and
 * after each take-back; load() fetches it again.
 */

const MARKUP = `
<div class="panel-ui">
    <div id="pinned-list" class="pin-list"><span class="empty">none pinned</span></div>
</div>`;

export function mountPinned(root, { base = "", world = null, log = null } = {}) {
    root.innerHTML = MARKUP;
    const $ = (id) => root.querySelector(`#${CSS.escape(id)}`);
    const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
    const say = (text, kind = "") => { if (log) log(text, kind); else console.log(text); };
    const state = { cameras: [], views: [], boards: [] };

    async function api(path, opts = {}) {
        const r = await fetch(base + path, { headers: { "Content-Type": "application/json" }, ...opts });
        const body = await r.json().catch(() => ({}));
        if (!r.ok) throw new Error(typeof body.detail === "string" ? body.detail : (body.detail ? JSON.stringify(body.detail) : r.statusText));
        return body;
    }

    const at = (host) => host || "the floor";
    function row(kind, site, stale, text, button) {
        const here = world && world.siteName ? world.siteName() : "";
        return `<div class="pin-row ${kind}${site === here ? " here" : ""}${stale ? " stale" : ""}" data-site="${esc(site)}"><span>${text}</span>${button}</div>`;
    }
    function render() {
        const gone = (found) => (found ? "" : " · gone");
        const boardNote = (b) => (!b.site_known ? " · site gone" : !b.node_found ? " · piece gone" : "");
        const pins = state.cameras.map((c) => row("camera", c.site, !c.host_found,
            `📷 ${esc(c.label || "camera")} · ${esc(c.site)} › ${esc(at(c.path))}${gone(c.host_found)}`,
            `<button type="button" class="pinned-camera-unpin" data-id="${esc(c.id)}" title="Unpin this camera; its views stay">Unpin</button>`))
            + state.views.map((l) => row("view", l.site, !l.host_found,
                `🖼 ${esc(l.picture)} · ${esc(l.site)} › ${esc(at(l.host))}${gone(l.host_found)}`,
                `<button type="button" class="pinned-view-unpin" data-site="${esc(l.site)}" data-id="${esc(l.id)}" title="Unpin this view; its picture and any pieces made from it stay">Unpin</button>`))
            + state.boards.map((b) => row("board", b.site, !(b.site_known && b.node_found),
                `📌 ${esc(b.site)} › ${esc(b.path)} ← ${esc(b.identity)}${boardNote(b)}`,
                `<button type="button" class="pinned-board-unpin" data-site="${esc(b.site)}" data-path="${esc(b.path)}" title="Take this board's pin back">Unpin</button>`));
        $("pinned-list").innerHTML = pins || '<span class="empty">none pinned</span>';
    }

    async function load() {
        const placed = await api("/placed").catch((e) => { say(e.message, "bad"); return {}; });
        state.cameras = placed.cameras || [];
        state.views = placed.views || [];
        state.boards = placed.boards || [];
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

    $("pinned-list").addEventListener("click", async (ev) => {
        const b = ev.target.closest("button.pinned-camera-unpin, button.pinned-view-unpin, button.pinned-board-unpin");
        if (!b) return;
        try {
            if (b.classList.contains("pinned-camera-unpin")) await unpinCamera(b.dataset.id);
            else if (b.classList.contains("pinned-view-unpin")) await unpinView(b.dataset.site, b.dataset.id);
            else await unpinBoard(b.dataset.site, b.dataset.path);
        } catch (e) { say(e.message, "bad"); }
        await load();
    });

    load();

    return {
        state, load, unpinCamera, unpinView, unpinBoard,
        destroy() { root.innerHTML = ""; },
    };
}
