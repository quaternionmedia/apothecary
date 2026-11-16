/* Deck: the Stream Deck + as apothecary has drawn it (firmware/deck.py), and what it
 * has heard. Its eight keys and its strip are the images last sent to it, since a
 * deck cannot be asked what it shows; its four knobs and the events heard are listed
 * under them. A simulated deck is pressed, turned and tapped from here, each a
 * POST of the event a real deck would report; a real deck is pressed by hand, and
 * its controls are off. What is heard is shown where it happened as well as listed: a
 * key or a knob held is marked for as long as it is down, and a press, a turn's
 * direction and a touch's place on the strip are lit for a moment after each.
 *
 * Its knobs, the layout that jogs the garage's machines, are the server's (deck_knobs.js):
 * the window starts and stops them and chooses the machine they move and their step,
 * as the deck's own keys do, and shows what the deck, a Control pad or the ring chose.
 *
 * mountDeck(root, { base, log }) renders into `root` and returns { shown(), close(),
 * load(), state(), destroy() }. shown() loads the first deck found and follows it
 * every 1.5 s while the window is in front, asking for its events four times a second;
 * close() stops. Listing a deck opens
 * nothing (GET /firmware/decks); following one opens it (GET /firmware/decks/{id}).
 */

import { esc } from "/static/board_text.js";
import { armedWords, choose, knobsOf, turn } from "/static/deck_knobs.js";

const SWIPE_PX = 200; // of the strip's 800: what the server reads as a swipe (deck_screens.py)
const KEYS = 8, KNOBS = 4, STRIP = [800, 100], EVERY_MS = 1500, HEAR_MS = 250, LIT_MS = 1200, KEPT = 200;

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
    let alive = true, timer = null, ear = null, deck = null, last = 0, drawn = null, lines = [], problem = null, knobs = null;
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
    $(".deck-strip").innerHTML = `<button type="button" class="deck-strip-tap" title="The touch strip: tapped where it is pressed; dragged a quarter of its length or more it is a swipe, which changes the screen the layout shows"><img alt="" hidden><span class="deck-none">–</span><span class="deck-touch" hidden></span></button>`;
    $(".deck-knobs").innerHTML = Array.from({ length: KNOBS }, (_, i) =>
        `<div class="deck-knob" data-knob="${i}">${[-1, 1].map((d) => `<button type="button" class="deck-turn" data-dir="${d}" title="Knob ${i} turned one step ${d > 0 ? "clockwise" : "counter-clockwise"}">${d > 0 ? "↻" : "↺"}</button>`).join("")}<button type="button" class="deck-press" title="Knob ${i} pressed and released">●</button></div>`).join("");

    // What was heard, shown where it happened. An event older than a few seconds (the
    // history a window opened late is given) marks what is still held and lights nothing.
    function lit(el) {
        el.classList.add("deck-heard");
        clearTimeout(el.litTimer);
        el.litTimer = setTimeout(() => { el.classList.remove("deck-heard"); if (el.classList.contains("deck-touch")) el.hidden = true; }, LIT_MS);
    }
    function show(e) {
        const fresh = Date.now() / 1000 - e.at < 3, v = e.value;
        if (e.kind === "touch") {
            if (!fresh) return;
            const dot = $(".deck-touch"), to = v.x_out != null ? v.x_out : v.x;
            dot.style.left = `${Math.min(v.x, to) / STRIP[0] * 100}%`;
            dot.style.top = `${v.y / STRIP[1] * 100}%`;
            dot.style.width = v.x_out != null ? `${Math.abs(to - v.x) / STRIP[0] * 100}%` : "";
            dot.hidden = false;
            lit(dot);
            return;
        }
        const el = e.kind === "key"
            ? root.querySelector(`.deck-key[data-key="${e.index}"]`)
            : root.querySelector(`.deck-knob[data-knob="${e.index}"] ${e.kind === "knob-press" ? ".deck-press" : `.deck-turn[data-dir="${v > 0 ? 1 : -1}"]`}`);
        if (!el) return;
        if (e.kind !== "knob-turn") el.classList.toggle("deck-down", !!v);
        if (fresh) lit(el);
    }
    function take(news) {
        let any = false;
        for (const e of news.events) if (e.seq > last) { lines = [heard(e), ...lines].slice(0, KEPT); show(e); any = true; }
        last = Math.max(last, news.last);
        return any;
    }
    function renderHeard() {
        $(".deck-events").innerHTML = lines.length ? lines.map((t) => `<li>${esc(t)}</li>`).join("") : '<li class="empty">nothing heard yet</li>';
    }

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
            + `<div class="meta deck-knobs-said">${esc(knobs.machine)} · ${esc(armedWords(knobs))} · ${esc(knobs.said)}</div>`
            + `<div class="meta deck-screen">strip screen: ${esc(knobs.screen)} (${knobs.screens.indexOf(knobs.screen) + 1}/${knobs.screens.length}) · a swipe along the strip walks ${knobs.screens.map(esc).join(", ")}</div>`;
    }

    function render() {
        renderKnobs();
        const inputs = !!(deck && deck.simulated);
        for (const b of root.querySelectorAll(".deck-key, .deck-strip-tap, .deck-turn, .deck-press")) b.disabled = !inputs;
        if (!deck) return;
        $(".deck-name").textContent = `${deck.model} · ${deck.id} · ${deck.vid}:${deck.pid}${deck.simulated ? " · simulated" : ""}${deck.serial ? ` · S/N ${deck.serial}` : ""}${drawn && drawn.mended ? ` · lost and found ${drawn.mended}×` : ""}`;
        const keys = (drawn && drawn.keys_drawn) || {};
        // An image is fetched again when what was drawn on it changes, whoever drew it.
        const stamp = (d) => (d ? encodeURIComponent([d.text, d.small, d.colour].join("|")) : "");
        const at = `${base}/firmware/decks/${encodeURIComponent(deck.id)}`;
        root.querySelectorAll(".deck-key").forEach((b, i) => picture(b, `${at}/keys/${i}/image?v=${stamp(keys[i])}`, !!keys[i]));
        picture($(".deck-strip-tap"), `${at}/strip/image?v=${stamp(drawn && drawn.strip_drawn)}`, !!(drawn && drawn.strip_drawn));
        $(".deck-note").textContent = problem
            ? problem
            : drawn && drawn.alive === false
            ? "the deck is not answering on USB: it is looked for, and drawn again as it was when it is back"
            : inputs
            ? "a simulated deck: press a key, turn or press a knob, tap the strip; each is the event a real deck reports"
            : "a real deck is pressed by hand; what it shows is what was last sent to it from here";
        renderHeard();
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
            take(await api(`/firmware/decks/${encodeURIComponent(deck.id)}/events?since=${last}`));
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

    // Between refreshes the events alone are asked for, so a press shows as it is made.
    const hear = () => {
        clearTimeout(ear);
        if (alive) ear = setTimeout(async () => {
            if (deck && !problem && !busy) {
                try { if (take(await api(`/firmware/decks/${encodeURIComponent(deck.id)}/events?since=${last}`))) renderHeard(); }
                catch (e) { /* the next refresh says what is wrong */ }
            }
            hear();
        }, HEAR_MS);
    };

    // What a simulated deck is given goes in the order it was clicked, one click's events
    // together: a press and its release are never parted by the next click's.
    let giving = Promise.resolve();
    function give(...events) {
        giving = giving.then(async () => {
            for (const [kind, index, value] of events) {
                try { await post(`/firmware/decks/${encodeURIComponent(deck.id)}/events`, { kind, index, value }); }
                catch (e) { say(`Deck: ${e.message}`, "bad"); return; }
            }
            await load();
        });
        return giving;
    }
    // A choice of the knobs, made on the server; the deck, the Control pads and this window
    // all follow it.
    async function steer(change) {
        try { knobs = await change(); } catch (e) { say(`Knobs: ${e.message}`, "bad"); }
        await load();
    }
    // A drag along the strip is a swipe: the event a real deck reports for a finger drawn
    // across it, from where it went down to where it came up. Its click is not a tap.
    let down = null, swiped = false;
    const strip = $(".deck-strip-tap");
    const place = (ev) => {
        const box = strip.getBoundingClientRect();
        return { x: Math.round((ev.clientX - box.left) / box.width * STRIP[0]), y: Math.round((ev.clientY - box.top) / box.height * STRIP[1]) };
    };
    function startSwipe(ev) { swiped = false; down = deck && deck.simulated ? place(ev) : null; }
    async function endSwipe(ev) {
        const from = down; down = null;
        if (!from || !deck || !deck.simulated) return;
        const to = place(ev);
        if (Math.abs(to.x - from.x) < SWIPE_PX) return;
        swiped = true;
        await give(["touch", 0, { kind: "drag", x: from.x, y: from.y, x_out: Math.max(0, Math.min(STRIP[0], to.x)), y_out: Math.max(0, Math.min(STRIP[1], to.y)) }]);
    }
    strip.addEventListener("pointerdown", startSwipe);
    strip.addEventListener("pointerup", endSwipe);
    root.addEventListener("click", async (ev) => {
        const b = ev.target.closest("button");
        if (b && deck && b.classList.contains("deck-run")) {
            await steer(async () => { await turn(base, deck.id, !(knobs && knobs.running)); return knobsOf(base, deck.id); });
            return;
        }
        if (b && deck && b.classList.contains("deck-machine")) { await steer(() => choose(base, deck.id, { machine: b.dataset.machine })); return; }
        if (b && deck && b.classList.contains("deck-step")) { await steer(() => choose(base, deck.id, { step_mm: Number(b.dataset.mm) })); return; }
        if (!b || !deck || !deck.simulated) return;
        if (b.classList.contains("deck-key")) { const i = +b.dataset.key; await give(["key", i, true], ["key", i, false]); }
        else if (b.classList.contains("deck-turn")) await give(["knob-turn", +b.closest(".deck-knob").dataset.knob, +b.dataset.dir]);
        else if (b.classList.contains("deck-press")) { const i = +b.closest(".deck-knob").dataset.knob; await give(["knob-press", i, true], ["knob-press", i, false]); }
        else if (b.classList.contains("deck-strip-tap")) {
            if (swiped) { swiped = false; return; }
            const box = b.getBoundingClientRect();
            await give(["touch", 0, { kind: "short", x: Math.round((ev.clientX - box.left) / box.width * STRIP[0]), y: Math.round((ev.clientY - box.top) / box.height * STRIP[1]) }]);
        }
    });

    return {
        load, state: () => ({ deck, drawn, last }),
        shown() { alive = true; load().catch((e) => { $(".deck-name").textContent = e.message; }); schedule(); hear(); },
        close() { clearTimeout(timer); clearTimeout(ear); },
        destroy() { alive = false; clearTimeout(timer); clearTimeout(ear); root.innerHTML = ""; },
    };
}
