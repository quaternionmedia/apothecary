/* A button whose command the server would refuse now is greyed, and says why.
 *
 * The server answers it: `can` on a board's status and info is, per command,
 * { ok, why, kind } (firmware/can.py), read from the same checks the routes
 * raise from. A button names its command in `data-can="<verb>"` (jog, home,
 * home.X, print.start ...); applyCan(root, can) sets `disabled` and
 * `aria-disabled` on each that is refused and puts "Disabled: <why>. <its own tip>"
 * in its title, keeping its own tip in `data-tip` and putting it back when the
 * command is ok again.
 *
 * Nothing that stops is ever greyed: `estop` is always ok in the answer, and a button
 * of that verb is also left alone here whatever `can` says. A verb the answer does not
 * know leaves its button as it is. A verb with a dot falls back to the one before it
 * (`home.X` of a printer is its `home`).
 *
 * A button some other act holds disabled (a send in flight) says so with
 * `data-busy`; it is enabled again by `refreshDisabled` only when neither the act nor
 * the answer holds it.
 */

const NEVER = new Set(["estop"]);

export function verdictOf(can, verb) {
    if (!can || !verb) return null;
    if (can[verb]) return can[verb];
    const base = verb.split(".")[0];
    return can[base] || null;
}

export function refreshDisabled(btn) {
    const off = btn.dataset.busy === "1" || btn.dataset.canOff === "1";
    btn.disabled = off;
    if (btn.dataset.canOff === "1") btn.setAttribute("aria-disabled", "true");
    else btn.removeAttribute("aria-disabled");
}

// A title with the ring's address the page wrote after it (` · ⌗932`), or the address
// alone where the button had no title of its own (`⌗77`): the address is the page's,
// kept in `data-address`, and never part of the button's own tip.
export const ADDRESS_AT_END = /(?:^| · )⌗\d+$/;

function tipOf(btn) {
    if (btn.dataset.tip === undefined) btn.dataset.tip = (btn.getAttribute("title") || "").replace(ADDRESS_AT_END, "");
    return btn.dataset.tip;
}

// The title: the reason first while the button is refused, then its own tip, then the
// ring's address the page wrote after it (` · ⌗932`), which a retitle must keep.
function compose(btn) {
    const tip = btn.dataset.tip || "";
    let text = btn.dataset.canOff === "1" ? `Disabled: ${btn.dataset.canWhy}.${tip ? " " + tip : ""}` : tip;
    if (btn.dataset.address) text = text ? `${text} · ⌗${btn.dataset.address}` : `⌗${btn.dataset.address}`;
    if (text) btn.title = text; else btn.removeAttribute("title");
}

// A button's own tip, said anew (a kind's words, a chosen file): shown as it is while
// the button is allowed, and after the reason while it is not.
export function setTip(btn, text) {
    btn.dataset.tip = text || "";
    compose(btn);
}

// A button refused for a reason the page knows (`why`, or null), with its own tip: the
// one way a button is greyed and says why, whether the reason is the server's or the
// page's (a sketch not chosen, a task running).
export function setReason(btn, why, tip) {
    btn.dataset.tip = tip || "";
    if (why) { btn.dataset.canOff = "1"; btn.dataset.canWhy = why; }
    else { delete btn.dataset.canOff; delete btn.dataset.canWhy; }
    compose(btn);
    refreshDisabled(btn);
}

// `can.flash` of a port, asked once when the port is chosen (GET /firmware/printers/info)
// and kept until `forgetFlash`: no timer. `call(path)` is the page's fetch. Whoever asks
// while the answer is on its way is given the same answer when it comes (the Bench's
// upload and its raw flash ask of one port): true once there is a verdict to read, false
// when there was nothing new to ask or the asking failed.
const flashCan = new Map();
const flashAsking = new Map();
export const flashVerdict = (port) => flashCan.get(port) || null;
export const forgetFlash = (port) => flashCan.delete(port);
export function askFlash(call, port) {
    if (!port) return Promise.resolve(false);
    if (flashAsking.has(port)) return flashAsking.get(port);
    if (flashCan.has(port)) return Promise.resolve(false);
    flashCan.set(port, null);
    const asking = (async () => {
        try {
            const info = await call(`/firmware/printers/info?port=${encodeURIComponent(port)}`);
            const v = (info.can && info.can.flash) || null;
            flashCan.set(port, v);
            return !!v;
        } catch (e) {
            flashCan.delete(port);
            return false;
        } finally {
            flashAsking.delete(port);
        }
    })();
    flashAsking.set(port, asking);
    return asking;
}

// The verb of a line a pad sends (its data-cmd), the command the server's answer names it
// by (firmware/can.py can_now). Each dialect's stop is the one line never greyed. What else
// the server takes with the latch down -- its `always` (firmware/gcode.py, grbl.py), what
// only interrupts or turns something off -- is named by how a job holding the port treats
// it: an interrupt (a printer's break, a router's hold) goes while a job streams, a quick
// stop (Marlin's, a jog cancelled) and a card's pause do not, an off does. Everything else
// needs the latch, a held controller's RESUME included, since it moves the machine again.
// tests/test_can_js.py holds these lists to the server's lines, line by line.
export const STOP_LINES = new Set(["M112", "RESET"]);
export const INTERRUPT_LINES = new Set(["M108", "HOLD"]);
export const QUICKSTOP_LINES = new Set(["M410", "JOG-CANCEL"]);
export const OFF_LINES = new Set(["M104 S0", "M140 S0", "M107", "M5"]);
export function verbOfLine(cmd) {
    if (STOP_LINES.has(cmd)) return "estop";
    if (INTERRUPT_LINES.has(cmd)) return "interrupt";
    if (QUICKSTOP_LINES.has(cmd)) return "quickstop";
    if (cmd === "M25") return "card.pause";
    if (OFF_LINES.has(cmd)) return "off";
    if (cmd === "RESUME") return "resume";
    if (cmd === "HOME") return "home";
    const axis = /^HOME-([XYZ])$/.exec(cmd);
    if (axis) return `home.${axis[1]}`;
    if (/^G28/.test(cmd)) return "home";
    if (cmd === "$X") return "unlock";
    if (/^(M104|M140|M106) /.test(cmd)) return "heat";
    if (/^M3 /.test(cmd)) return "spindle";
    return "control";
}

export function applyCan(root, can) {
    for (const btn of root.querySelectorAll("[data-can]")) {
        const verb = btn.dataset.can;
        tipOf(btn);
        const verdict = NEVER.has(verb) ? null : verdictOf(can, verb);
        if (verdict && !verdict.ok) {
            btn.dataset.canOff = "1";
            btn.dataset.canKind = verdict.kind || "";
            btn.dataset.canWhy = verdict.why || "refused";
        } else {
            delete btn.dataset.canOff;
            delete btn.dataset.canKind;
            delete btn.dataset.canWhy;
        }
        compose(btn);
        refreshDisabled(btn);
    }
}

// What a latch that lapses with no event does to an answer read a moment ago: each
// command that was ok only because the latch was armed is refused once it is not, in the
// words the server refuses it with (firmware/can.py not_armed) when the port is given. The
// server's own `armed` verdicts, and every other reason, are left as they were said.
export const NEEDS_THE_LATCH = ["jog", "home", "home.X", "home.Y", "home.Z", "heat", "spindle", "unlock", "resume", "control", "print.start", "print.resume", "level.probe"];

export function withLatch(can, armed, port = null) {
    if (!can || armed) return can;
    const out = { ...can };
    const why = `${port ? `${port}: ` : ""}control is not armed -- arm it first`;
    for (const verb of NEEDS_THE_LATCH) {
        if (out[verb] && out[verb].ok) out[verb] = { ok: false, kind: "armed", why };
    }
    return out;
}
