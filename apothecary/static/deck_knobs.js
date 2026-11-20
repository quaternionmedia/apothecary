/* The Stream Deck +'s knobs as the page reads and steers them: the server's layout on a
 * deck (firmware/deck_control.py) -- whether it runs, the machine its knobs move, their
 * step, the screen its strip shows and that machine's control. There is one such state,
 * the server's, and the Deck window, each Machine's Control pad and the ring's Panels ›
 * Tools › Deck each read and change it, so each shows what the others did. Each answer
 * carries `can`, what the deck's routes would refuse now (firmware/can.py), which greys
 * the window's controls and a pad's Knobs here (can.js). Nothing here moves a machine:
 * the knobs do, through the control latch.
 */

import { span } from "/static/format.js";

async function call(base, path, opts = {}) {
    const r = await fetch(base + path, { headers: { "Content-Type": "application/json" }, ...opts });
    const body = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(typeof body.detail === "string" ? body.detail : (body.detail ? JSON.stringify(body.detail) : r.statusText));
    return body;
}
const at = (deck) => `/firmware/decks/${encodeURIComponent(deck)}/control`;

// Every layout running, one per deck; with `port`, each one's answer says whether its
// knobs could be pointed at the machine whose board is there (`can.here`).
export const running = async (base = "", port = null) =>
    (await call(base, `/firmware/decks/control${port ? `?port=${encodeURIComponent(port)}` : ""}`)).controls;
// One deck's: { running: false, can } when its knobs are off.
export const knobsOf = (base, deck) => call(base, at(deck));
export const turn = (base, deck, on) => call(base, at(deck), { method: "POST", body: JSON.stringify({ on }) });
// { machine }, { port }, { step_mm } or { screen }: what the knobs move, their step, or the
// screen the strip shows (its name, "next" or "previous").
export const choose = (base, deck, choice) => call(base, at(deck), { method: "PUT", body: JSON.stringify(choice) });

// The screen the strip shows, and where it is in their order: "progress (2/3)".
export const screenWords = (knobs) => `${knobs.screen} (${knobs.screens.indexOf(knobs.screen) + 1}/${knobs.screens.length})`;

// The control the knobs' machine has left, as its strip says it.
export const armedWords = (knobs) => (knobs.armed_s > 0
    ? `armed ${span(knobs.armed_s)}`
    : "disarmed: arm it in its Machine, or long press its key twice");

// What the deck's routes would refuse now, for the ring's Panels › Tools › Deck: the
// answer of the deck `steer` acts on (the first found; firmware/can.py deck_can), with
// `here` for the open Machine's port; with no deck found, each refused for that, in
// steer's words. Empty when the server could not be asked: the ring is then told nothing.
const KNOBS_VERBS = ["knobs.start", "knobs.stop", "knobs.machine", "knobs.step", "knobs.screen", "here"];
export async function knobsCan(base, port = null) {
    try {
        const { decks } = await call(base, "/firmware/decks");
        if (!decks.length) {
            return Object.fromEntries(KNOBS_VERBS.map((verb) => [verb, { ok: false, kind: "found", why: "no Stream Deck + found" }]));
        }
        const { can } = await call(base, `${at(decks[0].id)}${port ? `?port=${encodeURIComponent(port)}` : ""}`);
        const out = { ...(can || {}) };
        if (!port) out.here = { ok: false, kind: "machine", why: "no Machine is open: Here is the open Machine's machine" };
        return out;
    } catch (e) {
        return {};
    }
}

// A verb of Panels › Tools › Deck -- "knobs", "machine:<name>", "step:<mm>", "here" or
// "screen:<name>" -- on the first deck found; `port` is the open Machine's, which "here"
// points the knobs at. Answers what came of it.
export async function steer(base, verb, { port = null } = {}) {
    const { decks } = await call(base, "/firmware/decks");
    if (!decks.length) throw new Error("no Stream Deck + found");
    const deck = decks[0].id;
    if (verb === "knobs") {
        const now = await knobsOf(base, deck);
        await turn(base, deck, !now.running);
        return now.running ? `knobs off on ${deck}` : `knobs on ${deck}`;
    }
    let chosen;
    if (verb === "here") {
        if (!port) throw new Error("no Machine is open: Here is the open Machine's machine");
        chosen = await choose(base, deck, { port });
    } else if (verb.startsWith("machine:")) {
        chosen = await choose(base, deck, { machine: verb.slice("machine:".length) });
    } else if (verb.startsWith("step:")) {
        chosen = await choose(base, deck, { step_mm: Number(verb.slice("step:".length)) });
    } else if (verb.startsWith("screen:")) {
        chosen = await choose(base, deck, { screen: verb.slice("screen:".length) });
        return `${deck}'s strip shows ${screenWords(chosen)}`;
    } else {
        throw new Error(`not a verb of the knobs: ${verb}`);
    }
    return `knobs on ${chosen.machine}, step ${chosen.step_mm} mm`;
}
