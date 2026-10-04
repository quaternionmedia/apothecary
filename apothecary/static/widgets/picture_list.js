/* Pictures: every picture under the picture root -- the folder's own, and the
 * ones the browser kept under captures/ and uploads/ -- newest first, each with
 * the places it is pinned at as a view and Pin here; Forget on a kept one, and
 * Purge kept. The gathering is a section of it until gathering leaves core (the
 * pictures plan's Phase 1).
 *
 * Pin here pins a picture as a view at the selection -- a host, a root
 * structure with a footprint that is not a made piece, or the floor -- as
 * Picture › Folder does. The ring's Folder holds the seven newest; Pin here is
 * on every row, the older pictures included. With nothing selected that can
 * hold a picture it is disabled, and says why.
 *
 * A row's views are the places it is pinned at. One in this site is clicked to
 * select that place and draw that view, as Picture › Views does; one in another
 * site is named and not drawn, since no verb switches the site.
 *
 * The kept pictures are the other half of the one list §6 of the draft record
 * *Personal data stays on the device* asks for (the pins are Site's Pinned): a
 * picture the browser kept is forgotten from its row, its views unpinned, every
 * site's. The folder's own pictures are a person's: only a person removes them.
 * A picture chosen in the file picker is kept under uploads/ and pinned nowhere;
 * Pin here pins it.
 *
 * Several pictures are gathered at once (POST /photos/gather): which are of one
 * thing, what the machine could not decide and would like a person to say --
 * answered here with the same five sentences the answers file uses. A report
 * only: nothing is built or opened from it.
 *
 * mountPictureList(root, { base, world, log }) renders into root; `world` is
 * what the page offers: siteName(); place() -> { host, why } (where Pin here
 * pins: "" the floor; null, with why, when nothing selected can hold a picture);
 * pin(path, host) (pinned there as a view and drawn); showView(id) (its place
 * selected and the view drawn); purge() (Pictures › Purge); changed() (a picture
 * was forgotten, so the world's marks follow). log(text, kind) is the page's
 * status bar, the only place a message is written; kind "bad" is a refusal. The
 * list is fetched when it mounts and after each change; load() fetches it again,
 * and placeChanged() says again where Pin here pins.
 */

const MARKUP = `
<div class="panel-ui">
    <div id="pictures-where" class="note"></div>
    <div id="pictures-list" class="pin-list pictures-list"><span class="empty">no pictures yet</span></div>
    <div class="row">
        <label class="grow">add <input type="file" id="pic-file" accept="image/png,image/jpeg,image/gif,image/webp,image/bmp,image/tiff" multiple title="Add pictures from this browser: kept under uploads/ in the picture folder, on this machine, as you named them, and pinned nowhere until Pin here pins one"></label>
        <button type="button" id="pictures-purge" title="Forget every picture the browser put here -- captures and uploads -- after asking once. The folder's own pictures stay">Purge kept</button>
    </div>
    <details id="pictures-gather" class="fold">
        <summary>Gather</summary>
        <div id="pic-list" class="pics"><span class="empty">none yet</span></div>
        <div class="row">
            <label><input type="checkbox" id="pic-all"> all</label>
            <span class="grow"></span>
            <button type="button" id="pic-gather" title="Which of the ticked pictures are of the same thing, and what the machine would ask you">Gather</button>
        </div>
        <div id="gather-out"></div>
        <textarea id="gather-answers" rows="3" placeholder="What you know, one sentence a line: 'a and b are the same thing', 'a and b are parts of one thing', 'a and b are not related', 'a is not worth using', 'a is worth using anyway'" title="Your word wins outright, and it carries"></textarea>
    </details>
</div>`;

const HOW_KEPT = { capture: "captured", upload: "added" };

export function mountPictureList(root, { base = "", world = null, log = null } = {}) {
    root.innerHTML = MARKUP;
    const $ = (id) => root.querySelector(`#${CSS.escape(id)}`);
    const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
    // Every message is said once, where the page says everything: its status
    // bar. A refusal is kind "bad", and the page shows it as an error.
    const say = (text, kind = "") => { if (log) log(text, kind); else console.log(text); };
    const state = { pictures: [], views: [], gathered: null };

    async function api(path, opts = {}) {
        const r = await fetch(base + path, { headers: { "Content-Type": "application/json" }, ...opts });
        const body = await r.json().catch(() => ({}));
        if (!r.ok) throw new Error(typeof body.detail === "string" ? body.detail : (body.detail ? JSON.stringify(body.detail) : r.statusText));
        return body;
    }
    const at = (host) => (host ? host : "the floor");
    const segs = (path) => path.split("/").map(encodeURIComponent).join("/");
    const place = () => (world && world.place ? world.place() : { host: null, why: "nothing to pin at" });

    // --- the list ------------------------------------------------------------------------
    // Where Pin here pins, said once above the rows; each row's button follows.
    function renderPlace() {
        const where = place();
        $("pictures-where").textContent = where.host === null ? where.why : `Pin here pins at ${at(where.host)}`;
        for (const b of root.querySelectorAll(".pictures-pin")) {
            b.disabled = where.host === null;
            b.title = where.host === null ? where.why : `Pin this picture at ${at(where.host)} as a view`;
        }
    }
    function viewsHtml(path) {
        const here = world && world.siteName ? world.siteName() : "";
        return state.views.filter((v) => v.picture === path).map((v) => (v.site === here
            ? `<span class="picture-view here" data-view="${esc(v.id)}" title="Select ${esc(at(v.host))} and draw this view">${esc(at(v.host))}</span>`
            : `<span class="picture-view" title="Pinned in ${esc(v.site)}: open that site to draw it">${esc(v.site)} › ${esc(at(v.host))}</span>`)).join("");
    }
    function render() {
        const list = $("pictures-list");
        if (!state.pictures.length) {
            list.innerHTML = '<span class="empty">no pictures in the folder yet: take one with a pinned camera, drop one on the world, add some here, or put some in the folder</span>';
        } else {
            list.innerHTML = state.pictures.map((p) => {
                const views = viewsHtml(p.path);
                return `<div class="pin-row picture-row" data-path="${esc(p.path)}">`
                    + `<img src="${base}/photos/pictures/file?path=${encodeURIComponent(p.path)}&px=64" alt="" loading="lazy">`
                    + `<div class="picture-what"><span class="picture-name" title="${esc(p.path)} · ${Math.round(p.size / 1024)} kB">${esc(p.path)}${p.kept ? ` · ${HOW_KEPT[p.kept] || "kept"}` : ""}</span>`
                    + `<span class="picture-views">${views || '<span class="empty">pinned nowhere</span>'}</span></div>`
                    + `<button type="button" class="pictures-pin" data-path="${esc(p.path)}">Pin here</button>`
                    + (p.kept ? `<button type="button" class="pictures-forget" data-path="${esc(p.path)}" title="Forget this picture; its views are unpinned, every site's">Forget</button>` : "")
                    + "</div>";
            }).join("");
        }
        for (const pin of root.querySelectorAll(".pictures-pin")) pin.addEventListener("click", () => pinHere(pin.dataset.path).catch((e) => say(e.message, "bad")));
        for (const forgetBtn of root.querySelectorAll(".pictures-forget")) forgetBtn.addEventListener("click", () => forget(forgetBtn.dataset.path).catch((e) => say(e.message, "bad")));
        for (const chip of root.querySelectorAll(".picture-view.here")) chip.addEventListener("click", () => showView(chip.dataset.view));
        renderPlace();
        renderGatherList();
    }
    async function load() {
        const [pictures, placed] = await Promise.all([
            api("/photos/pictures").catch((e) => { say(e.message, "bad"); return []; }),
            api("/placed").catch(() => ({})),
        ]);
        state.pictures = pictures;
        state.views = placed.views || [];
        render();
        return state;
    }

    // Pin here: the picture pinned as a view at the selected host or the floor.
    async function pinHere(path) {
        const where = place();
        if (where.host === null) { say(where.why, "bad"); return null; }
        const view = await world.pin(path, where.host);
        await load();
        return view;
    }
    function showView(id) {
        if (world && world.showView) world.showView(id);
    }
    async function forget(path) {
        await api(`/photos/pictures/${segs(path)}`, { method: "DELETE" });
        say(`forgot ${path}; its views are unpinned, every site's; pieces made from it stay`);
        if (world && world.changed) await world.changed();
        await load();
    }
    // Purge kept: the ring's Pictures › Purge, which asks once.
    async function purge() {
        const gone = world && world.purge ? await world.purge() : null;
        await load();
        return gone;
    }
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
        // Kept and pinned nowhere: the next step is pinning one at a place as a view.
        const next = kept.length ? ": Pin here pins one at the selected place as a view" : "";
        say(`added ${kept.length} picture(s) on this machine${next}` + (refused.length ? ` — refused: ${refused.join("; ")}` : ""), refused.length ? "bad" : "");
        await load();
        return kept;
    }
    $("pic-file").addEventListener("change", async (ev) => { await addFiles(ev.target.files); ev.target.value = ""; });
    $("pictures-purge").onclick = () => purge().catch((e) => say(e.message, "bad"));

    // --- the gathering, until it leaves core -----------------------------------------------
    function ticked() { return [...root.querySelectorAll("#pic-list input[type=checkbox]:checked")].map((i) => i.value); }
    function renderGatherList() {
        const list = $("pic-list");
        const was = new Set(ticked());
        if (!state.pictures.length) { list.innerHTML = '<span class="empty">no pictures to gather</span>'; return; }
        list.innerHTML = state.pictures.map((p) => `<label class="pic" title="${esc(p.path)} · ${Math.round(p.size / 1024)} kB"><input type="checkbox" value="${esc(p.path)}"${was.has(p.path) ? " checked" : ""}><img src="${base}/photos/pictures/file?path=${encodeURIComponent(p.path)}&px=256" alt="${esc(p.name)}" loading="lazy"><span>${esc(p.name)}${p.kept ? ` · ${HOW_KEPT[p.kept] || "kept"}` : ""}</span></label>`).join("");
    }
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

    // A verb chosen on the ring goes through the same button a click would; the
    // gathering's section opens to show what it does.
    const BUTTON_FOR = { gather: "pic-gather" };
    function act(verb) {
        const btn = $(BUTTON_FOR[verb]);
        if (!btn) return false;
        $("pictures-gather").open = true;
        btn.click();
        return true;
    }

    load();

    return {
        state, load, pinHere, forget, purge, addFiles, gather, act,
        placeChanged: renderPlace,
        destroy() { root.innerHTML = ""; },
    };
}
