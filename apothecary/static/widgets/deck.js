/* Deck: the Stream Deck + as apothecary has drawn it (firmware/deck.py), and what it
 * has heard. Its eight keys and its strip are the images last sent to it, since a
 * deck cannot be asked what it shows; its four knobs and the events heard are listed
 * under them. A simulated deck is pressed, turned and tapped from here, each a
 * POST of the event a real deck would report; a real deck is pressed by hand, and
 * its controls are off.
 *
 * Its knobs, the layout that jogs the garage's machines, are the server's (deck_knobs.js):
 * the window starts and stops them and chooses the machine they move and their step,
 * as the deck's own keys do, and shows what the deck, a Control pad or the ring chose.
 *
 * mountDeck(root, { base, log }) renders into `root` and returns { shown(), close(),
 * load(), state(), destroy() }. shown() loads the first deck found and follows it
 * every 1.5 s while the window is in front; close() stops. Listing a deck opens
 * nothing (GET /firmware/decks); following one opens it (GET /firmware/decks/{id}).
 */

import { esc } from "/static/board_text.js";
import { armedWords, choose, knobsOf, turn } from "/static/deck_knobs.js";

const KEYS = 8, KNOBS = 4, STRIP = [800, 100], EVERY_MS = 1500;

const MARKUP = `
<div class="deck-ui">
    <div class="deck-head"><span class="deck-name meta">looking for a Stream Deck +…</span></div>
    <div class="deck-control"></div>
    <div class="deck-keys"></div>
    <div class="deck-strip"></div>
    <div class="deck-knobs"></div>
    <div class="note deck-note"></div>
    <div class="k">Heard</div>
    <ol class="deck-events"><li class="empty">nothing heard yet</li></ol>
</div>`;

const heard = (e) => {
    const v = e.value;
    if (e.kind === "key") return `key ${e.index} ${v ? "pressed" : "released"}`;
    if (e.kind === "knob-turn") return `knob ${e.index} turned ${v > 0 ? "+" : "−"}${Math.abs(v)}`;
    if (e.kind === "knob-press") return `knob ${e.index} ${v ? "pressed" : "released"}`;
    return `strip ${v.kind} at ${v.x}, ${v.y}${v.x_out != null ? ` to ${v.x_out}, ${v.y_out}` : ""}`;
};

export function mountDeck(root, { base = "", log = null } = {}) {
    root.innerHTML = MARKUP;
    const $ = (sel) => root.querySelector(sel);
    let alive = true, timer = null, deck = null, last = 0, drawn = null, lines = [], problem = null, knobs = null;
    const say = (text, kind = "") => { if (log) log(text, kind); };

    async function api(path, opts = {}) {
        const r = await fetch(base + path, { headers: { "Content-Type": "application/json" }, ...opts });
        const body = await r.json().catch(() => ({}));
        if (!r.ok) throw new Error(typeof body.detail === "string" ? body.detail : (body.detail ? JSON.stringify(body.detail) : r.statusText));
        return body;
    }
    const post = (path, data) => api(path, { method: "POST", body: JSON.stringify(data) });

    $(".deck-keys").innerHTML = Array.from({ length: KEYS }, (_, i) =>
        `<button type="button" class="deck-key" data-key="${i}" title="Key ${i}: pressed and released as a deck reports it"><img alt="" hidden><span class="deck-none">–</span></button>`).join("");
    $(".deck-strip").innerHTML = `<button type="button" class="deck-strip-tap" title="The touch strip: tapped where it is pressed"><img alt="" hidden><span class="deck-none">–</span></button>`;
    $(".deck-knobs").innerHTML = Array.from({ length: KNOBS }, (_, i) =>
        `<div class="deck-knob" data-knob="${i}">${[-1, 1].map((d) => `<button type="button" class="deck-turn" data-dir="${d}" title="Knob ${i} turned one step ${d > 0 ? "clockwise" : "counter-clockwise"}">${d > 0 ? "↻" : "↺"}</button>`).join("")}<button type="button" class="deck-press" title="Knob ${i} pressed and released">●</button></div>`).join("");

    function picture(button, url, drawnNow) {
        const img = button.querySelector("img");
        img.hidden = !drawnNow;
        button.querySelector(".deck-none").hidden = drawnNow;
        if (drawnNow) img.src = url;
    }

    // The knobs: off, or the machine they move, their step and its control.
    function renderKnobs() {
        const box = $(".deck-control");
        if (!deck || !knobs) { box.innerHTML = ""; return; }
        const on = !!knobs.running;
        const run = `<button type="button" class="deck-run" title="${on ? "Stop the knobs: the keys and strip stay as drawn" : "Start the knobs: the layout that jogs the garage's machines"}. ⌗ Panels › Machine › Knobs › On / off">${on ? "■ Knobs" : "▶ Knobs"}</button>`;
        if (!on) { box.innerHTML = `<div class="row">${run}<span class="meta">knobs off</span></div>`; return; }
        const machines = knobs.machines.map((m) => `<button type="button" class="deck-machine" data-machine="${esc(m)}" aria-pressed="${m === knobs.machine}" title="The knobs move ${esc(m)}, as its key on the deck chooses it. ⌗ Panels › Machine › Knobs › Machine">${esc(m)}</button>`).join("");
        const steps = knobs.steps_mm.map((mm) => `<button type="button" class="deck-step" data-mm="${mm}" aria-pressed="${mm === knobs.step_mm}" title="A knob's step moves ${mm} mm, as the deck's STEP key cycles it. ⌗ Panels › Machine › Knobs › Step">${mm}</button>`).join("");
        box.innerHTML = `<div class="row">${run}${machines}</div><div class="row"><span class="meta">step</span>${steps}<span class="meta">mm</span></div>`
            + `<div class="meta deck-knobs-said">${esc(knobs.machine)} · ${esc(armedWords(knobs))} · ${esc(knobs.said)}</div>`;
    }

    function render() {
        renderKnobs();
        const inputs = !!(deck && deck.simulated);
        for (const b of root.querySelectorAll(".deck-key, .deck-strip-tap, .deck-turn, .deck-press")) b.disabled = !inputs;
        if (!deck) return;
        $(".deck-name").textContent = `${deck.model} · ${deck.id} · ${deck.vid}:${deck.pid}${deck.simulated ? " · simulated" : ""}${deck.serial ? ` · S/N ${deck.serial}` : ""}`;
        const keys = (drawn && drawn.keys_drawn) || {};
        // An image is fetched again when what was drawn on it changes, whoever drew it.
        const stamp = (d) => (d ? encodeURIComponent([d.text, d.small, d.colour].join("|")) : "");
        const at = `${base}/firmware/decks/${encodeURIComponent(deck.id)}`;
        root.querySelectorAll(".deck-key").forEach((b, i) => picture(b, `${at}/keys/${i}/image?v=${stamp(keys[i])}`, !!keys[i]));
        picture($(".deck-strip-tap"), `${at}/strip/image?v=${stamp(drawn && drawn.strip_drawn)}`, !!(drawn && drawn.strip_drawn));
        $(".deck-note").textContent = problem
            ? problem
            : inputs
            ? "a simulated deck: press a key, turn or press a knob, tap the strip; each is the event a real deck reports"
            : "a real deck is pressed by hand; what it shows is what was last sent to it from here";
        $(".deck-events").innerHTML = lines.length ? lines.map((t) => `<li>${esc(t)}</li>`).join("") : '<li class="empty">nothing heard yet</li>';
    }

    // One refresh at a time: a second asked for while one is under way runs once more when
    // it ends, so what was posted since is read, and no event is read twice.
    let busy = null, again = false;
    function load() {
        if (busy) { again = true; return busy; }
        busy = (async () => {
            try { do { again = false; await refresh(); } while (again && alive); }
            finally { busy = null; }
            return deck;
        })();
        return busy;
    }
    async function refresh() {
        const found = await api("/firmware/decks");
        if (!alive) return null;
        if (!found.decks.length) {
            deck = null;
            $(".deck-name").textContent = found.problem ? `no Stream Deck +: ${found.problem}` : "no Stream Deck + found";
            render();
            return null;
        }
        deck = found.decks[0];
        try {
            drawn = await api(`/firmware/decks/${encodeURIComponent(deck.id)}`);
            deck = { ...deck, serial: drawn.serial };
            const news = await api(`/firmware/decks/${encodeURIComponent(deck.id)}/events?since=${last}`);
            for (const e of news.events) if (e.seq > last) lines = [heard(e), ...lines].slice(0, 12);
            last = Math.max(last, news.last);
            knobs = await knobsOf(base, deck.id);
            problem = null;
        } catch (e) {
            // Said once, and shown in the window for as long as it lasts.
            if (e.message !== problem) say(`Deck: ${e.message}`, "bad");
            problem = e.message;
        }
        render();
        return deck;
    }

    const schedule = () => { clearTimeout(timer); if (alive) timer = setTimeout(async () => { try { await load(); } catch (e) { /* the next beat tries again */ } schedule(); }, EVERY_MS); };

    async function give(kind, index, value) {
        try { await post(`/firmware/decks/${encodeURIComponent(deck.id)}/events`, { kind, index, value }); }
        catch (e) { say(`Deck: ${e.message}`, "bad"); return; }
        await load();
    }
    // A choice of the knobs, made on the server; the deck, the Control pads and this window
    // all follow it.
    async function steer(change) {
        try { knobs = await change(); } catch (e) { say(`Knobs: ${e.message}`, "bad"); }
        await load();
    }
    root.addEventListener("click", async (ev) => {
        const b = ev.target.closest("button");
        if (b && deck && b.classList.contains("deck-run")) {
            await steer(async () => { await turn(base, deck.id, !(knobs && knobs.running)); return knobsOf(base, deck.id); });
            return;
        }
        if (b && deck && b.classList.contains("deck-machine")) { await steer(() => choose(base, deck.id, { machine: b.dataset.machine })); return; }
        if (b && deck && b.classList.contains("deck-step")) { await steer(() => choose(base, deck.id, { step_mm: Number(b.dataset.mm) })); return; }
        if (!b || !deck || !deck.simulated) return;
        if (b.classList.contains("deck-key")) { const i = +b.dataset.key; await give("key", i, true); await give("key", i, false); }
        else if (b.classList.contains("deck-turn")) await give("knob-turn", +b.closest(".deck-knob").dataset.knob, +b.dataset.dir);
        else if (b.classList.contains("deck-press")) { const i = +b.closest(".deck-knob").dataset.knob; await give("knob-press", i, true); await give("knob-press", i, false); }
        else if (b.classList.contains("deck-strip-tap")) {
            const box = b.getBoundingClientRect();
            await give("touch", 0, { kind: "short", x: Math.round((ev.clientX - box.left) / box.width * STRIP[0]), y: Math.round((ev.clientY - box.top) / box.height * STRIP[1]) });
        }
    });

    return {
        load, state: () => ({ deck, drawn, last }),
        shown() { alive = true; load().catch((e) => { $(".deck-name").textContent = e.message; }); schedule(); },
        close() { clearTimeout(timer); },
        destroy() { alive = false; clearTimeout(timer); root.innerHTML = ""; },
    };
}
