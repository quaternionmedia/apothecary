/* Models: image models through qmcp, always optional, asked only when a person asks.
 *
 * Three parts, top to bottom. qmcp: whether it is configured and answering, in
 * one sentence (GET /vision, asked again each time the window is shown and after
 * each Ask). Origins: the plain reader and each of qmcp's models, each with its
 * switch (PUT /vision/origins/{origin}); a model is "not checked" until
 * `apothecary vision check` has passed for it, and a guess from one is shown and
 * used for nothing. Ask: the shape chosen on a picture's mat (POST
 * .../shapes/{i}/ask) -- the plain reader's colour read off its pixels, and each
 * model's colour, material and label beside it, with whether they agree -- and a
 * person's word on each property, typed or picked from its words and said with
 * Enter (PUT .../observations/{property}), which comes first and marks a guess
 * overruled.
 *
 * Ask and a person's word are the canvas ring's Pictures › Models too (Ask, Colour ›
 * a word, Material › a word): the page hands each to act().
 *
 * mountModels(root, { base, world, log }) renders into root; `world` is what the
 * page offers: siteName(), and chosen() -- { view, index, word, picture, host }
 * for the shape chosen on a mat, or null. log(text, kind) is the page's status
 * bar. load() asks GET /vision again; follow() reads the chosen shape again and
 * what is kept about it; act(verb) does a ring cell's verb: "ask", or
 * "say:<property>:<word>".
 */

const MARKUP = `
<div class="models-ui">
    <div class="k">qmcp</div>
    <div class="models-state"><span class="empty">asking…</span></div>
    <div class="models-note note"></div>
    <div class="k">Origins</div>
    <ul class="models-origins"><li class="empty">–</li></ul>
    <div class="k">Ask about a shape</div>
    <div class="models-chosen"></div>
    <div class="row models-asks"></div>
    <div class="models-said note"></div>
    <div class="models-rows"></div>
</div>`;

const ASKED = ["colour", "material", "label"];

export function mountModels(root, { base = "", world = null, log = null } = {}) {
    root.innerHTML = MARKUP;
    const $ = (sel) => root.querySelector(sel);
    const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
    const say = (text, kind = "") => { if (log) log(text, kind); };
    let status = null, chosen = null, rows = [], busy = false, alive = true;

    async function api(path, opts = {}) {
        const r = await fetch(base + path, { headers: { "Content-Type": "application/json" }, ...opts });
        const body = await r.json().catch(() => ({}));
        if (!r.ok) throw new Error(typeof body.detail === "string" ? body.detail : (body.detail ? JSON.stringify(body.detail) : r.statusText));
        return body;
    }
    const shapeUrl = () => `/sites/${encodeURIComponent(world.siteName())}/views/${encodeURIComponent(chosen.view)}/shapes/${chosen.index}`;

    // What each state of qmcp means for a person: what still works, and the way on.
    const NOTES = {
        "not configured": "Apothecary reads without it: the plain reader still reads a colour. APOTHECARY_QMCP names a qmcp on this machine; apothecary serve --demo has a simulated one.",
        "refused": "Nothing is sent there. A qmcp is asked only on this machine.",
        "not reachable": "Nothing is asked of it; apothecary reads without it.",
        "not answering": "Nothing is asked of it; apothecary reads without it. It is asked again each time this window is shown, and after each Ask.",
        "no model": "qmcp is up and has no vision model: every guess comes back unread.",
        "answering": "Its models answer only when asked here, and every guess is a guess: none is trusted until apothecary vision check has passed for it.",
    };

    function renderStatus() {
        if (!status) return;
        const good = status.state === "answering";
        $(".models-state").innerHTML = `<span class="dot ${good ? "ok" : status.state === "not configured" ? "off" : "warn"}"></span>${esc(status.says)}`;
        $(".models-note").textContent = NOTES[status.state] || "";
        $(".models-origins").innerHTML = status.origins.map((o) => `<li>
            <label class="grow" title="${o.on ? "Switch it off: it is not asked, and what it said leaves every view" : "Switch it on again"}">
                <input type="checkbox" class="models-switch" data-origin="${esc(o.origin)}" aria-label="${esc(o.origin)} switched on"${o.on ? " checked" : ""}>
                <span class="origin">${esc(o.origin)}</span></label>
            <span class="meta">${esc(o.what)}${o.answers ? ` · answers ${esc(o.answers.join(", "))}` : ""}${o.origin.startsWith("qmcp/") ? ' · <span class="warn">not checked</span>' : ""}</span>
        </li>`).join("");
    }

    function renderChosen() {
        const asks = $(".models-asks");
        if (!chosen) {
            $(".models-chosen").innerHTML = '<span class="empty">Choose a shape on a picture\'s mat to ask about it.</span>';
            asks.innerHTML = "";
            $(".models-rows").innerHTML = "";
            return;
        }
        const where = chosen.host === "" ? "the floor" : chosen.host;
        $(".models-chosen").innerHTML = `Shape ${chosen.index}, a ${esc(chosen.word)}, in ${esc(chosen.picture)} at ${esc(where)}`;
        // With no model to ask, Ask reads the colour off the pixels and says so.
        const modelless = status && status.state !== "answering";
        const title = modelless
            ? `Read the shape's colour off its pixels. No model to ask: ${status.says}`
            : "Read the shape's colour off its pixels, and ask qmcp's models its colour, its material (among the materials a camera can tell apart) and what it is (among the names of the things in this site)";
        asks.innerHTML = `<button type="button" class="models-ask" title="${esc(title)}"${busy ? " disabled" : ""}>${modelless ? "Read its colour" : "Ask"}</button>`;
    }

    // A colour's swatch: its measured sRGB, or the basic word itself, which CSS names too.
    const COLOUR_WORDS = new Set(["black", "white", "grey", "red", "orange", "yellow", "green", "blue", "purple", "pink", "brown"]);
    const swatch = (word, rgb) => {
        const fill = rgb || (COLOUR_WORDS.has(word) ? word : null);
        return fill ? `<span class="swatch" style="background:${esc(fill)}"></span>` : "";
    };

    function cell(seen, { guess = false } = {}) {
        if (!seen) return '<span class="empty">–</span>';
        if (seen.value === null) return `<span class="unread${seen.overruled ? " overruled" : ""}" title="${esc(seen.origin)}">unread: ${esc(seen.why)}</span>${seen.overruled ? ' <span class="meta">overruled by a person</span>' : ""}`;
        const sure = seen.confidence === null ? "" : ` · ${Number(seen.confidence).toFixed(2)}`;
        const agrees = guess && seen.agrees !== undefined ? (seen.agrees ? ' · <span class="ok">agrees</span>' : ' · <span class="bad">disagrees</span>') : "";
        const trust = guess ? ' · <span class="warn">not checked</span>' : "";
        const overruled = seen.overruled ? ' <span class="meta">overruled by a person</span>' : "";
        const rgb = seen.rgb ? ` <span class="meta">${esc(seen.rgb)}</span>` : "";
        return `<span class="${seen.overruled ? "overruled" : ""}" title="${esc(seen.origin)}">${swatch(seen.value, seen.rgb)}${esc(seen.value)}${rgb}${sure}${trust}${agrees}</span>${overruled}`;
    }

    // A person's word: typed, or picked from the property's words, and said with Enter.
    function sayer(row) {
        const list = row.words ? `models-words-${row.property}` : "";
        const words = row.words ? `<datalist id="${list}">${row.words.map((w) => `<option value="${esc(w)}">`).join("")}</datalist>` : "";
        return `<input class="models-word" data-property="${row.property}"${list ? ` list="${list}"` : ""} placeholder="${row.words ? "pick or type, Enter" : "type, Enter"}" aria-label="A person's ${row.property}: Enter says it" title="A person's word comes first, over every guess: Enter says it" spellcheck="false">${words}`;
    }

    function renderRows() {
        if (!chosen) return;
        const body = rows.map((row) => {
            // A guess names its model when more than one answered; its tooltip always does.
            const named = row.guesses.length > 1;
            const guesses = row.guesses.length ? row.guesses.map((g) => `<div>${cell(g, { guess: true })}${named ? ` <span class="meta">${esc(g.origin.replace(/^qmcp\//, ""))}</span>` : ""}</div>`).join("") : '<span class="empty">–</span>';
            const hidden = row.hidden ? `<div class="meta">${row.hidden === 1 ? "1 guess" : `${row.hidden} guesses`} not shown: switched off</div>` : "";
            return `<tr data-property="${row.property}">
                <th>${esc(row.property)}</th>
                <td>${cell(row.reading)}</td>
                <td>${guesses}${hidden}</td>
                <td>${row.person ? `<div>${cell(row.person)}</div>` : ""}<div>${sayer(row)}</div></td>
            </tr>`;
        }).join("");
        $(".models-rows").innerHTML = `<table class="models-table"><thead><tr><th></th><th title="Read off the shape's own pixels, on this machine">Read</th><th title="Each model's guess, with how sure it says it is; its model is in its tooltip">Guessed</th><th title="A person's word comes first, over every guess">A person</th></tr></thead><tbody>${body}</tbody></table>`;
    }

    async function load() {
        try { status = await api("/vision"); } catch (e) { $(".models-state").innerHTML = `<span class="bad">${esc(e.message)}</span>`; return; }
        if (alive) { renderStatus(); renderChosen(); }
    }

    async function follow() {
        const now = world && world.chosen ? world.chosen() : null;
        const same = now && chosen && now.view === chosen.view && now.index === chosen.index;
        chosen = now;
        if (!same) { rows = []; $(".models-said").textContent = ""; }
        renderChosen();
        if (!chosen) return;
        try { rows = (await api(`${shapeUrl()}/observations`)).rows; } catch (e) { rows = []; $(".models-said").textContent = e.message; }
        renderRows();
    }

    async function ask(asked = ASKED) {
        if (!chosen) { say("choose a shape on a picture's mat first, then Ask", "bad"); return; }
        if (busy) return;
        busy = true; renderChosen();
        $(".models-said").textContent = `asking about shape ${chosen.index}…`;
        try {
            const answer = await api(`${shapeUrl()}/ask`, { method: "POST", body: JSON.stringify({ asked }) });
            rows = answer.about.rows;
            $(".models-said").textContent = answer.said;
            say(answer.said, "ok");
        } catch (e) {
            $(".models-said").textContent = e.message;
            say(e.message, "bad");
        } finally {
            busy = false; renderChosen(); renderRows();
        }
        load();
    }

    async function speak(prop, word = null) {
        if (!chosen) { say("choose a shape on a picture's mat first", "bad"); return; }
        const field = root.querySelector(`.models-word[data-property="${prop}"]`);
        const value = (word ?? (field ? field.value : "")).trim();
        if (!value) { $(".models-said").textContent = `type a ${prop} first`; return; }
        try {
            const answer = await api(`${shapeUrl()}/observations/${prop}`, { method: "PUT", body: JSON.stringify({ value }) });
            rows = answer.about.rows;
            $(".models-said").textContent = answer.said;
            say(answer.said, "ok");
            renderRows();
        } catch (e) { $(".models-said").textContent = e.message; say(e.message, "bad"); }
    }

    async function toggle(origin, on) {
        try {
            status = await api(`/vision/origins/${origin.split("/").map(encodeURIComponent).join("/")}`, { method: "PUT", body: JSON.stringify({ on }) });
            renderStatus();
            say(`${origin} is switched ${on ? "on" : "off"}`, "ok");
            await follow();
        } catch (e) { say(e.message, "bad"); await load(); }
    }

    const models = $(".models-ui");
    models.addEventListener("click", (event) => {
        if (event.target.closest(".models-ask")) ask();
    });
    models.addEventListener("change", (event) => {
        const box = event.target.closest(".models-switch");
        if (box) toggle(box.dataset.origin, box.checked);
    });
    models.addEventListener("keydown", (event) => {
        const field = event.target.closest("input.models-word");
        if (field && event.key === "Enter") speak(field.dataset.property);
    });

    renderChosen();
    load();
    follow();
    // A ring cell's verb: "ask", or "say:<property>:<word>".
    function act(verb) {
        if (verb === "ask") return ask();
        const [what, prop, ...word] = verb.split(":");
        if (what === "say" && prop && word.length) return speak(prop, word.join(":"));
        say(`Models cannot do ${verb}`, "bad");
        return null;
    }

    return {
        load,
        follow,
        ask,
        act,
        status: () => status,
        rows: () => rows,
        destroy() { alive = false; root.innerHTML = ""; },
    };
}
