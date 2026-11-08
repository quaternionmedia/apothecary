/* The Stream Deck +'s knobs as the page reads and steers them: the server's layout on a
 * deck (firmware/deck_control.py) -- whether it runs, the machine its knobs move, their
 * step and that machine's control. There is one such state, the server's, and the Deck
 * window, each Machine's Control pad and the ring's Panels › Machine › Knobs each read
 * and change it, so each shows what the others did. Nothing here moves a machine: the
 * knobs do, through the control latch.
 */

async function call(base, path, opts = {}) {
    const r = await fetch(base + path, { headers: { "Content-Type": "application/json" }, ...opts });
    const body = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(typeof body.detail === "string" ? body.detail : (body.detail ? JSON.stringify(body.detail) : r.statusText));
    return body;
}
const at = (deck) => `/firmware/decks/${encodeURIComponent(deck)}/control`;

// Every layout running, one per deck.
export const running = async (base = "") => (await call(base, "/firmware/decks/control")).controls;
// One deck's: { running: false } when its knobs are off.
export const knobsOf = (base, deck) => call(base, at(deck));
export const turn = (base, deck, on) => call(base, at(deck), { method: "POST", body: JSON.stringify({ on }) });
// { machine }, { port } or { step_mm }: what the knobs move, or their step.
export const choose = (base, deck, choice) => call(base, at(deck), { method: "PUT", body: JSON.stringify(choice) });

// The control the knobs' machine has left, as its strip says it.
export const armedWords = (knobs) => (knobs.armed_s > 0
    ? `armed ${Math.floor(knobs.armed_s / 60)}:${String(Math.floor(knobs.armed_s % 60)).padStart(2, "0")}`
    : "disarmed: arm it in its Machine, or long press its key twice");

// A verb of Panels › Machine › Knobs -- "knobs", "machine:<name>", "step:<mm>" or "here" --
// on the first deck found; `port` is the open Machine's, which "here" points the knobs at.
// Answers what came of it.
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
    } else {
        throw new Error(`not a verb of the knobs: ${verb}`);
    }
    return `knobs on ${chosen.machine}, step ${chosen.step_mm} mm`;
}
