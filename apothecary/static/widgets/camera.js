/* What is left of the camera panel until gathering leaves core (the pictures
 * plan's Phase 1): the pictures on this machine, ticked and gathered into a
 * report, and what a person says about them. A report only: nothing is built
 * or opened from it.
 *
 * What a page placed, pinned or kept -- cameras, views, boards, kept pictures,
 * every site's -- is listed and taken back in Kept (widgets/kept.js), the one
 * list §6 of the draft record *Personal data stays on the device* asks for. A
 * picture chosen from the file picker here is kept under uploads/ and pinned
 * nowhere; Kept forgets it.
 *
 * Several pictures are gathered at once (POST /photos/gather): which are of
 * one thing, what the machine could not decide and would like a person to
 * say -- answered here with the same five sentences the answers file uses.
 *
 * mountCamera(root, { base, world, log }) renders into root; `world` is what
 * the page offers: kept() (a picture was kept here, so Kept lists it).
 * log(text, kind) is the page's status bar, the only place a message is
 * written; kind "bad" is a refusal.
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
    </div>
    <div id="gather-out"></div>
    <textarea id="gather-answers" rows="3" placeholder="What you know, one sentence a line: 'a and b are the same thing', 'a and b are parts of one thing', 'a and b are not related', 'a is not worth using', 'a is worth using anyway'" title="Your word wins outright, and it carries"></textarea>
</div>`;

export function mountCamera(root, { base = "", world = null, log = null } = {}) {
    root.innerHTML = MARKUP;
    const $ = (id) => root.querySelector(`#${CSS.escape(id)}`);
    const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
    // Every message is said once, where the page says everything: its status
    // bar. A refusal is kind "bad", and the page shows it as an error.
    const say = (text, kind = "") => { if (log) log(text, kind); else console.log(text); };
    const state = { pictures: [], gathered: null, answers: "" };

    async function api(path, opts = {}) {
        const r = await fetch(base + path, { headers: { "Content-Type": "application/json" }, ...opts });
        const body = await r.json().catch(() => ({}));
        if (!r.ok) throw new Error(typeof body.detail === "string" ? body.detail : (body.detail ? JSON.stringify(body.detail) : r.statusText));
        return body;
    }

    // --- the pictures on this machine, and gathering them -------------------------------
    function ticked() { return [...root.querySelectorAll("#pic-list input[type=checkbox]:checked")].map((i) => i.value); }
    const HOW_KEPT = { capture: " · captured", upload: " · added" };
    function renderPictures() {
        const list = $("pic-list");
        if (!state.pictures.length) { list.innerHTML = '<span class="empty">no pictures in the folder yet — capture one, add some, or put some there</span>'; return; }
        list.innerHTML = state.pictures.map((p) => `<label class="pic" title="${esc(p.path)} · ${Math.round(p.size / 1024)} kB"><input type="checkbox" value="${esc(p.path)}"><img src="${base}/photos/pictures/file?path=${encodeURIComponent(p.path)}" alt="${esc(p.name)}" loading="lazy"><span>${esc(p.name)}${HOW_KEPT[p.kept] || ""}</span></label>`).join("");
    }
    async function loadPictures() {
        try { state.pictures = await api("/photos/pictures"); } catch (e) { state.pictures = []; say(e.message, "bad"); }
        renderPictures();
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
        const next = kept.length ? ": Picture › Folder pins one at a place as a view" : "";
        say(`added ${kept.length} picture(s) on this machine${next}` + (refused.length ? ` — refused: ${refused.join("; ")}` : ""), refused.length ? "bad" : "");
        await loadPictures();
        if (world && world.kept) world.kept();
        return kept;
    }
    $("pic-file").addEventListener("change", async (ev) => { await addFiles(ev.target.files); ev.target.value = ""; });
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

    loadPictures();

    // A verb chosen on the ring goes through the same button a click would.
    const BUTTON_FOR = { gather: "pic-gather" };
    function act(verb) {
        const btn = $(BUTTON_FOR[verb]);
        if (!btn) return false;
        btn.click();
        return true;
    }

    const handle = {
        state, loadPictures, gather, act, addFiles,
        destroy() { root.innerHTML = ""; },
    };
    return handle;
}
