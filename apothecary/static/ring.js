/* The ring, drawn in the browser.
 *
 * The options come from the server (`POST /menu/resolve`, built by
 * apothecary/menu.py); this file only draws them and turns a press into a
 * choice. What it holds to is rad's "the menu addresses nine cells":
 *
 *     7 8 9        up-left     up    up-right
 *     4 5 6   =    left       BACK   right
 *     1 2 3        down-left  down   down-right
 *
 * Eight cells hold options, cell 5 holds none and backs out. The i-th option
 * of a ring sits in cell PLACEMENT[i], cardinals first, so a four-item ring is
 * at up, right, down and left. The ring on screen is a *rendering* of the
 * cells: eight fixed 45-degree compass wedges, up = cell 8, clockwise
 * 8 9 6 3 2 1 4 7. A wedge with nothing in it is drawn faint and cannot be
 * chosen.
 *
 * A digit chooses its cell from anywhere. The digits pressed to reach an
 * option through nested rings are its ADDRESS ("86" = cell 8, then cell 6),
 * and given the same context the same address always reaches the same option.
 * Every intent that leaves here carries its address, and the page writes the
 * same digits onto the buttons it already has, so the numbering is visible
 * where the control is.
 *
 * Plain ES module, no build step; its one import is keys.js, how a key is named
 * and when a shortcut may act. The pure parts (angle to
 * slot, nearest cell in a direction, addresses) are exported so a test can
 * compare them with the Python resolver's; the same four are on
 * window.apothecaryRing.
 */

import { comboOf, matches, mayAct, typing } from "./keys.js";

export const PLACEMENT = [8, 6, 2, 4, 9, 3, 1, 7];
export const COMPASS = [8, 9, 6, 3, 2, 1, 4, 7]; // compass slot (up, clockwise) -> cell
export const GEOMETRY = {
    startDeg: -90,
    clockwise: true,
    r0: 36,           // the hub: inside it a press backs out
    r1: 108,          // the outer edge of the wedges
    cancelScale: 1.35, // beyond r1 * this there is nothing to choose: cancel
    chordMs: 150,     // two arrows this close together are one corner
};
export const BACK = 5;

// Cell -> grid column and row, the only thing the arrow rule needs.
const CELL_XY = {
    7: [0, 0], 8: [1, 0], 9: [2, 0],
    4: [0, 1], 5: [1, 1], 6: [2, 1],
    1: [0, 2], 2: [1, 2], 3: [2, 2],
};
const DIRECTION = { up: [0, -1], down: [0, 1], left: [-1, 0], right: [1, 0] };
const CORNER = { "up,left": 7, "left,up": 7, "up,right": 9, "right,up": 9,
                 "down,left": 1, "left,down": 1, "down,right": 3, "right,down": 3 };
const ARROW_KEYS = { ArrowUp: "up", ArrowDown: "down", ArrowLeft: "left", ArrowRight: "right" };

// rad's polar rule, unchanged: item i is centred at startDeg + i * (360 / n).
export function angleToIndex(thetaDeg, n = 8) {
    const norm = ((((thetaDeg - GEOMETRY.startDeg) % 360) + 360) % 360);
    return Math.round(norm / (360 / n)) % n;
}

// Screen angle (0 = right, 90 = down, -90 = up) to the compass cell under it.
export function cellAtAngle(thetaDeg) {
    return COMPASS[angleToIndex(thetaDeg, 8)];
}

/* The nearest occupied cell in a direction. The exact rule, shared with
 * menu.py's nearest(): from cell c pressing direction d, a candidate is an
 * occupied cell k != c whose displacement from c has a positive dot product
 * with d; the best sits most squarely in the arrow's line -- least offset
 * across d, then least far along it, then the lowest number. Nothing in that
 * direction: stay. Nothing highlighted yet: the first arrow starts from the
 * centre.
 *
 * "Nearest in the direction" and not "walk the row": in a four-item ring the
 * corners are empty, and walking left from cell 8 reaches nothing. From 8,
 * Left reaches 4.
 */
export function nearest(from, direction, occupied) {
    const d = DIRECTION[direction];
    if (!d) return from ?? null;
    const c = from == null ? BACK : Number(from);
    const [cx, cy] = CELL_XY[c] || CELL_XY[BACK];
    let best = null;
    let bestScore = null;
    for (const raw of occupied || []) {
        const k = Number(raw);
        if (k === c || !CELL_XY[k] || k === BACK) continue;
        const [kx, ky] = CELL_XY[k];
        const dx = kx - cx, dy = ky - cy;
        const along = dx * d[0] + dy * d[1];
        if (along <= 0) continue;
        const across = Math.abs(dx * d[1]) + Math.abs(dy * d[0]);
        const score = [across, along, k];
        if (bestScore === null || score[0] < bestScore[0]
            || (score[0] === bestScore[0] && (score[1] < bestScore[1]
            || (score[1] === bestScore[1] && score[2] < bestScore[2])))) {
            best = k;
            bestScore = score;
        }
    }
    return best ?? (from ?? null);
}

// Give every option its cell (the server sends one; a stub might not) and
// carry the same down through its children.
export function withCells(options) {
    return (options || []).map((option, i) => ({
        ...option,
        cell: Number.isInteger(option.cell) ? option.cell : PLACEMENT[i],
        children: option.children ? withCells(option.children) : undefined,
    }));
}

// Every action a ring can produce, and the digits that reach it. The first
// time an action turns up wins, as every_action() in tests/ring_helpers.py does.
export function addresses(ring) {
    const found = {};
    const walk = (options, prefix) => {
        for (const option of withCells(options)) {
            const digits = prefix + option.cell;
            if (option.action && !(option.action in found)) found[option.action] = digits;
            if (option.children) walk(option.children, digits);
        }
    };
    walk(ring && ring.options, "");
    return found;
}

/* The address of one option: by the action it carries, or by a path of ids
 * (or labels) down through nested rings. Null when the ring has no such thing.
 */
export function addressOf(ring, target) {
    if (!ring) return null;
    if (!Array.isArray(target)) return addresses(ring)[target] ?? null;
    let options = withCells(ring.options);
    let digits = "";
    for (const step of target) {
        const option = options.find((o) => o.id === step || o.label === step);
        if (!option) return null;
        digits += option.cell;
        options = option.children || [];
    }
    return digits;
}

/* Write the address onto the page's own controls, where they already are.
 * `pairs` is [[element, action], ...]; an action not on the ring leaves its
 * element as it was. Ids and classes are never touched.
 */
export function annotate(ring, pairs) {
    const map = addresses(ring);
    let count = 0;
    for (const [el, action] of pairs) {
        if (!el || !action) continue;
        const digits = map[action];
        if (!digits) {
            delete el.dataset.address;
            if (el.title) el.title = el.title.replace(/ · ⌗\d+$/, "");
            continue;
        }
        el.dataset.address = digits;
        const title = (el.title || "").replace(/ · ⌗\d+$/, "");
        el.title = title ? `${title} · ⌗${digits}` : `⌗${digits}`;
        count += 1;
    }
    return count;
}

/* `picture` is what the page knows about pictures and cameras where the ring
 * stands (apothecary/menu.py's PictureContext), or a promise of it. */
export async function resolveRing({ base = "", context, site, device, picture }) {
    const body = { context };
    if (site) body.site = site;
    if (device) body.device = device;
    const told = await picture;
    if (told) body.picture = told;
    const r = await fetch(`${base}/menu/resolve`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
    });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(typeof data.detail === "string" ? data.detail : r.statusText);
    return { title: data.title ?? null, options: withCells(data.options) };
}

// ---------------------------------------------------------------------------
// Drawing
// ---------------------------------------------------------------------------

const STYLE = `
.apothecary-ring { position: fixed; inset: 0; z-index: 1000; outline: none; touch-action: none; }
.apothecary-ring svg { position: absolute; overflow: visible; font-family: system-ui, -apple-system, "Segoe UI", sans-serif; }
.apothecary-ring .wedge { fill: #2a2f2a; stroke: #0f120f; stroke-width: 1.5; cursor: pointer; }
.apothecary-ring .wedge.empty { fill: #1b1e1b; opacity: 0.35; cursor: default; }
.apothecary-ring .wedge.disabled { opacity: 0.5; cursor: not-allowed; }
.apothecary-ring .wedge.destructive { fill: #3a2020; }
.apothecary-ring .wedge.hot { fill: #4c6a4c; }
.apothecary-ring .wedge.destructive.hot { fill: #7a2a2a; }
.apothecary-ring .wedge.marked { fill: #23384a; stroke: #6fb3e8; }
.apothecary-ring .wedge.marked.hot { fill: #33557a; }
.apothecary-ring .wedge.armed, .apothecary-ring .wedge.armed.hot { fill: #8a3a1a; stroke: #ffb27a; }
.apothecary-ring .label.armed { fill: #ffe0c8; font-weight: 600; }
.apothecary-ring .hub { fill: #141614; stroke: #3a443a; stroke-width: 1.5; cursor: pointer; }
.apothecary-ring text { fill: #d8e0d8; pointer-events: none; user-select: none; }
.apothecary-ring .label { font-size: 12px; text-anchor: middle; }
.apothecary-ring .digit { font-size: 10px; fill: #b8a273; text-anchor: middle; }
.apothecary-ring .digit-key { fill: #222722; stroke: #4c4532; stroke-width: 1; pointer-events: none; }
.apothecary-ring .empty-digit { opacity: 0.35; }
.apothecary-ring .hub-digit { font-size: 11px; fill: #66746a; text-anchor: middle; }
.apothecary-ring .title { font-size: 10px; fill: #9aa89a; text-anchor: middle; }
.apothecary-ring .address { font-size: 10px; fill: #ffcc66; text-anchor: middle; }
`;

function ensureStyle() {
    if (document.getElementById("apothecary-ring-style")) return;
    const style = document.createElement("style");
    style.id = "apothecary-ring-style";
    style.textContent = STYLE;
    document.head.appendChild(style);
}

const rad = (deg) => (deg * Math.PI) / 180;
const polar = (r, deg) => [r * Math.cos(rad(deg)), r * Math.sin(rad(deg))];

// One annulus sector: the wedge for compass slot `slot`, 45 degrees wide.
function wedgePath(slot, r0, r1) {
    const centre = GEOMETRY.startDeg + slot * 45;
    const a0 = centre - 22.5, a1 = centre + 22.5;
    const [x0, y0] = polar(r0 + 3, a0), [x1, y1] = polar(r1, a0);
    const [x2, y2] = polar(r1, a1), [x3, y3] = polar(r0 + 3, a1);
    return `M${x0.toFixed(2)},${y0.toFixed(2)} L${x1.toFixed(2)},${y1.toFixed(2)} `
        + `A${r1},${r1} 0 0 1 ${x2.toFixed(2)},${y2.toFixed(2)} L${x3.toFixed(2)},${y3.toFixed(2)} `
        + `A${r0 + 3},${r0 + 3} 0 0 0 ${x0.toFixed(2)},${y0.toFixed(2)} Z`;
}

const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

// ---------------------------------------------------------------------------
// The ring itself: one open at a time
// ---------------------------------------------------------------------------

let current = null;

export function isOpen() {
    return current !== null;
}

export function close() {
    if (current) current.close(false);
}

/* Open the ring. Resolves the options from the server, draws them at `at`
 * (or the viewport's centre), and calls onIntent once when something is
 * chosen; onClose when it goes away for any reason. With `into`, the id or
 * label of an option with children, the ring opens entered down to it, as if
 * its digits had been pressed.
 */
export async function openRing({ base = "", context, site, device, picture, at = null, into = null, onIntent, onClose }) {
    close();
    const ring = await resolveRing({ base, context, site, device, picture });
    if (current) current.close(false); // somebody opened another while we fetched
    const instance = new RingInstance({ ring, context, site, device, at, onIntent, onClose });
    current = instance;
    instance.mount();
    if (into) instance.enter(into);
    return instance;
}

class RingInstance {
    constructor({ ring, context, site, device, at, onIntent, onClose }) {
        this.root = ring;
        this.context = context;
        this.site = site;
        this.device = device;
        this.at = at;
        this.onIntent = onIntent;
        this.onClose = onClose;
        this.stack = [{ ring, digit: "" }]; // the rings entered so far, top last
        this.address = "";
        this.highlight = null;
        this.lastArrow = null;
        this.armed = null; // a cell chosen once that asks to be chosen again
        this.previousFocus = document.activeElement;
        this.done = false;
    }

    get ring() { return this.stack[this.stack.length - 1].ring; }
    get byCell() {
        const map = {};
        for (const option of this.ring.options) map[option.cell] = option;
        return map;
    }
    get occupied() { return this.ring.options.map((o) => o.cell); }

    mount() {
        ensureStyle();
        const rc = GEOMETRY.r1 * GEOMETRY.cancelScale;
        const size = Math.ceil(rc * 2 + 8);
        const pad = GEOMETRY.r1 + 8;
        // Where the ring is asked to open, shifted inward so the whole ring is
        // on screen; never shrunk.
        const want = this.at || { x: window.innerWidth / 2, y: window.innerHeight / 2 };
        this.cx = Math.min(Math.max(want.x, pad), Math.max(pad, window.innerWidth - pad));
        this.cy = Math.min(Math.max(want.y, pad), Math.max(pad, window.innerHeight - pad));

        const el = document.createElement("div");
        el.className = "apothecary-ring";
        el.id = "ring-overlay";
        el.tabIndex = -1;
        el.setAttribute("role", "menu");
        el.innerHTML = `<svg id="ring-svg" width="${size}" height="${size}" viewBox="${-size / 2} ${-size / 2} ${size} ${size}" style="left:${this.cx - size / 2}px;top:${this.cy - size / 2}px"></svg>`;
        this.el = el;
        this.svg = el.firstElementChild;
        document.body.appendChild(el);
        this.draw();

        this.onMove = (e) => this.pointerMove(e);
        this.onDown = (e) => this.pointerDown(e);
        this.onKey = (e) => this.keyDown(e);
        this.onMenu = (e) => e.preventDefault();
        el.addEventListener("pointermove", this.onMove);
        el.addEventListener("pointerdown", this.onDown);
        el.addEventListener("contextmenu", this.onMenu);
        window.addEventListener("keydown", this.onKey, true);
        el.focus({ preventScroll: true });
    }

    draw() {
        const { r0, r1 } = GEOMETRY;
        const byCell = this.byCell;
        const parts = [];
        for (let slot = 0; slot < 8; slot++) {
            const cell = COMPASS[slot];
            const option = byCell[cell];
            const centre = GEOMETRY.startDeg + slot * 45;
            // The cell's digit at the inner end of its spoke, by the hub, on a key of
            // its own; its label further out, clear of it -- on the two level spokes
            // begun just past the key and running outward, where a centred label would
            // reach back over it.
            const [dx, dy] = polar(r0 + 14, centre);
            const level = Math.abs(Math.cos(rad(centre))) > 0.9;
            const [lx, ly] = polar(level ? r0 + 29 : r0 + (r1 - r0) * 0.61, centre);
            const anchor = level ? ` style="text-anchor: ${Math.cos(rad(centre)) > 0 ? "start" : "end"}"` : "";
            const cls = ["wedge"];
            if (!option) cls.push("empty");
            else {
                if (option.enabled === false) cls.push("disabled");
                if (option.destructive) cls.push("destructive");
                if (option.marked) cls.push("marked");  // the one chosen elsewhere (a picture chosen in Pictures)
                if (this.highlight === cell) cls.push("hot");
                if (this.armed === cell) cls.push("armed");
            }
            const armed = option && this.armed === cell;
            const label = option ? (option.marked ? "• " : "") + esc(option.label) + (option.children ? " ›" : "") : "";
            // A cell that cannot be undone, chosen once, says what choosing it again does.
            const words = armed
                ? `<text class="label armed"${anchor} x="${lx.toFixed(1)}" y="${(ly - 2).toFixed(1)}">again to<tspan x="${lx.toFixed(1)}" dy="13">${esc(option.label.toLowerCase())}</tspan></text>`
                : `<text class="label"${anchor} x="${lx.toFixed(1)}" y="${(ly + 4).toFixed(1)}">${label}</text>`;
            parts.push(
                `<path id="ring-cell-${cell}" class="${cls.join(" ")}" data-cell="${cell}" role="menuitem"`
                + ` aria-label="${option ? esc(armed ? `again to ${option.label.toLowerCase()}` : option.label) : "empty"}"`
                + (option && option.marked ? ' aria-current="true"' : "")
                + `${option ? "" : ' aria-disabled="true"'} d="${wedgePath(slot, r0, r1)}"></path>`
                + (option ? words : "")
                + `<circle class="digit-key${option ? "" : " empty-digit"}" cx="${dx.toFixed(1)}" cy="${dy.toFixed(1)}" r="8.5"></circle>`
                + `<text class="digit${option ? "" : " empty-digit"}" x="${dx.toFixed(1)}" y="${(dy + 4).toFixed(1)}">${cell}</text>`
            );
        }
        const title = this.ring.title || "";
        parts.push(
            `<circle class="hub" data-cell="5" r="${r0}"></circle>`
            + `<text class="hub-digit" x="0" y="${title ? -6 : 4}">5</text>`
            + (title ? `<text class="title" x="0" y="8">${esc(title)}</text>` : "")
            + (this.address ? `<text class="address" x="0" y="${r0 + 14}">⌗${this.address}</text>` : "")
        );
        this.svg.innerHTML = parts.join("");
        if (this.highlight != null) this.el.setAttribute("aria-activedescendant", `ring-cell-${this.highlight}`);
        else this.el.removeAttribute("aria-activedescendant");
    }

    setHighlight(cell) {
        if (cell === this.highlight) return;
        this.highlight = cell;
        this.draw();
    }

    // Pointer position relative to the hub, as rad measures it.
    polarOf(e) {
        const dx = e.clientX - this.cx, dy = e.clientY - this.cy;
        return { r: Math.hypot(dx, dy), theta: (Math.atan2(dy, dx) * 180) / Math.PI };
    }

    pointerMove(e) {
        const { r, theta } = this.polarOf(e);
        if (r <= GEOMETRY.r0 || r > GEOMETRY.r1 * GEOMETRY.cancelScale) { this.setHighlight(null); return; }
        const cell = cellAtAngle(theta);
        this.setHighlight(this.byCell[cell] ? cell : null);
    }

    pointerDown(e) {
        if (e.button !== 0) { e.preventDefault(); return; }
        e.preventDefault();
        const { r, theta } = this.polarOf(e);
        if (r <= GEOMETRY.r0) { this.back(); return; }
        if (r > GEOMETRY.r1 * GEOMETRY.cancelScale) { this.close(false); return; }
        const cell = cellAtAngle(theta);
        if (this.byCell[cell]) this.commit(cell);
    }

    keyDown(e) {
        if (this.done) return;
        // Nothing else on the page sees a key while the ring is up: the viewer
        // steps out on Backspace, and here Backspace is the hub.
        e.stopImmediatePropagation();
        const key = e.key;
        if (/^[1-9]$/.test(key)) {
            e.preventDefault();
            const cell = Number(key);
            if (cell === BACK) this.back();
            else if (this.byCell[cell]) this.commit(cell);
            return;
        }
        if (key in ARROW_KEYS) {
            e.preventDefault();
            this.arrow(ARROW_KEYS[key]);
            return;
        }
        if (key === "Backspace") { e.preventDefault(); this.back(); return; }
        if (key === "Escape") { e.preventDefault(); this.close(false); return; }
        if (key === "Enter" || key === " ") {
            e.preventDefault();
            if (this.highlight != null && this.byCell[this.highlight]) this.commit(this.highlight);
        }
    }

    // An arrow moves to the nearest occupied cell that way. Two arrows at
    // right angles inside the chord window are the corner between them --
    // a shortcut over walking there, never the only route.
    arrow(direction) {
        const now = performance.now();
        const last = this.lastArrow;
        if (last && now - last.t <= GEOMETRY.chordMs) {
            const corner = CORNER[`${last.direction},${direction}`];
            if (corner && this.byCell[corner]) {
                this.lastArrow = null;
                this.setHighlight(corner);
                return;
            }
        }
        this.lastArrow = { direction, t: now };
        this.setHighlight(nearest(this.highlight, direction, this.occupied));
    }

    commit(cell) {
        const option = this.byCell[cell];
        if (!option || option.enabled === false) return;
        // Not undoable: chosen once it asks, its wedge saying "again to ..."; chosen
        // again, it is done. Choosing any other cell lets the question go.
        if (option.twice && this.armed !== cell) {
            this.armed = cell;
            this.highlight = cell;
            this.draw();
            return;
        }
        this.armed = null;
        this.address += String(cell);
        if (option.children) {
            this.stack.push({ ring: { title: option.label, options: option.children }, digit: String(cell) });
            this.highlight = null;
            this.lastArrow = null;
            this.draw();
            return;
        }
        const intent = {
            action: option.action,
            option_id: option.id,
            address: this.address,
            context: this.context,
            label: option.label,
            confirmed: !!option.twice, // asked twice, in the ring itself
            site: this.site,
            device: this.device,
            at: { x: this.cx, y: this.cy }, // where the ring stood, for one that follows from it
        };
        this.close(true);
        window.dispatchEvent(new CustomEvent("apothecary:intent", { detail: intent }));
        if (this.onIntent) this.onIntent(intent);
    }

    /* Down to the option `target` names -- an id or a label, wherever it is in
     * this ring's tree -- as if its digits had been pressed from the top: the
     * ring then shows that option's children, and the address so far is theirs.
     * False, and nothing pressed, when there is no such option or it is a leaf.
     */
    enter(target) {
        const find = (options, trail) => {
            for (const option of options) {
                const here = [...trail, option];
                if (option.id === target || option.label === target) return option.children ? here : null;
                const deeper = option.children ? find(option.children, here) : null;
                if (deeper) return deeper;
            }
            return null;
        };
        const path = find(this.root.options, []);
        if (!path) return false;
        while (this.stack.length > 1) this.back();
        for (const option of path) this.commit(option.cell);
        return true;
    }

    // One level out; at the top, away.
    back() {
        if (this.stack.length <= 1) { this.close(false); return; }
        this.armed = null;
        this.stack.pop();
        this.address = this.address.slice(0, -1);
        this.highlight = null;
        this.lastArrow = null;
        this.draw();
    }

    close(committed) {
        if (this.done) return;
        this.done = true;
        window.removeEventListener("keydown", this.onKey, true);
        this.el.remove();
        if (current === this) current = null;
        const previous = this.previousFocus;
        if (previous && previous.isConnected && typeof previous.focus === "function") {
            try { previous.focus({ preventScroll: true }); } catch (e) { /* gone */ }
        }
        if (this.onClose) this.onClose(committed);
    }
}

// ---------------------------------------------------------------------------
// The invokers: the right button with a modifier, a long press, two keys, a button
// ---------------------------------------------------------------------------

// The modifiers a right-click can be held with to open the ring, by the name a
// person chooses them by, and the event's flag for each.
export const MODIFIERS = { ctrl: "ctrlKey", alt: "altKey", shift: "shiftKey", meta: "metaKey" };
export { comboOf };

const STILL_PX = 4;       // a press let go within this of where it was pressed is still
const LONG_PRESS_MS = 500; // a still touch held this long is the ring
const MAC = typeof navigator !== "undefined" && /Mac|iPhone|iPad/.test(navigator.platform || navigator.userAgent || "");

/* Bind the ways in. `whatFor(event, { opening, canvas })` is the page's: given a
 * pointer event (or null for a key and the button) it says what the ring opens on
 * -- {context, site, device, at} -- or null where the spot is the browser's.
 * Asked with `opening` false it only says whose the spot is: "world" (the canvas,
 * a badge: the browser's menu never shows there, and a plain right-click is the
 * camera's), "page" (a Contents row, a Machine: a plain right-click is the
 * browser's), or null. With `canvas` it answers the canvas ring, whatever is
 * selected.
 *
 * The ring opens at the pointer on a still press and release of the right button
 * held with `modifier` (ctrl, alt, shift or meta; on macOS Ctrl+click is a
 * right-click), heard before anything under it -- the view's controls never see
 * the press, so it never turns the view -- and by touch on a still long press, in
 * the world and on a row. Pressed elsewhere, or moved, it opens nothing. `key`
 * opens the ring on the selection and `canvasKey` the canvas ring, each a shortcut
 * as keys.js names one, matched by the key or its position, and never while the
 * focus takes the key (keys.js's mayAct). `onResolved(ring, spec)` fires after
 * every resolve, for annotating the page. The keys and the modifier change at once
 * with `configure({ key, canvasKey, modifier })`.
 */
export function installRing({ base = "", whatFor, onIntent, onResolved, onError, button = "#ring-open", key = "m", canvasKey = "Shift+m", modifier = "ctrl" }) {
    const bound = { key, canvasKey, modifier: MODIFIERS[modifier] ? modifier : "ctrl" };
    const open = async (spec, at) => {
        if (!spec) return null;
        try {
            const instance = await openRing({
                base,
                context: spec.context,
                site: spec.site,
                device: spec.device,
                picture: spec.picture,
                at: at ?? spec.at ?? null,
                into: spec.into ?? null,
                onIntent,
                onClose: spec.onClose,
            });
            if (onResolved) onResolved(instance.root, spec);
            return instance;
        } catch (err) {
            if (onError) onError(err); else console.error(err);
            return null;
        }
    };
    const middle = () => ({ x: window.innerWidth / 2, y: window.innerHeight / 2 });
    const fromKeyboard = () => open(whatFor(null), middle());

    window.addEventListener("keydown", (e) => {
        if (isOpen() || !mayAct(e)) return;
        const canvas = matches(e, bound.canvasKey);
        if (!canvas && !matches(e, bound.key)) return;
        e.preventDefault();
        open(whatFor(null, { canvas }), middle());
    });

    // The ring's press: the right button held with the modifier (or, on macOS, Ctrl
    // and the left button), on a spot of the page's; a touch, in the world or on a row.
    const held = (e) => !!e[MODIFIERS[bound.modifier]];
    function ringPress(e) {
        if (e.pointerType === "touch") return e.isPrimary ? "touch" : null;
        if (!held(e)) return null;
        if (e.button === 2) return "click";
        if (e.button === 0 && MAC && bound.modifier === "ctrl") return "click";
        return null;
    }
    let pressed = null;
    // How far a press has gone: one that wandered and came back is a drag, not a click.
    const moved = (e, p) => Math.max(p.far || 0, Math.hypot(e.clientX - p.x, e.clientY - p.y)) > STILL_PX;
    const letGo = () => { if (pressed && pressed.timer) clearTimeout(pressed.timer); pressed = null; };
    document.addEventListener("pointerdown", (e) => {
        letGo();
        if (isOpen()) return;
        const kind = ringPress(e);
        if (!kind) return;
        const spot = whatFor(e, { opening: false });
        if (!spot) return;
        if (kind === "touch") {
            // A touch is the view's until it has stood still long enough; a Machine's
            // text is the browser's to select.
            if (spot !== "world" && !e.target.closest(".contents-item")) return;
            pressed = { kind, id: e.pointerId, x: e.clientX, y: e.clientY, event: e, fired: false };
            const p = pressed;
            p.timer = setTimeout(() => {
                if (pressed !== p) return;
                p.fired = true;
                open(whatFor(p.event), { x: p.x, y: p.y });
            }, LONG_PRESS_MS);
            return;
        }
        // Heard first, so the view's controls never take it for a turn.
        e.preventDefault();
        e.stopImmediatePropagation();
        pressed = { kind, id: e.pointerId, x: e.clientX, y: e.clientY, event: e };
    }, true);
    document.addEventListener("pointermove", (e) => {
        if (!pressed || e.pointerId !== pressed.id) return;
        pressed.far = Math.max(pressed.far || 0, Math.hypot(e.clientX - pressed.x, e.clientY - pressed.y));
        if (pressed.kind === "touch" && !pressed.fired && moved(e, pressed)) letGo();
    }, true);
    document.addEventListener("pointerup", (e) => {
        if (!pressed || e.pointerId !== pressed.id) return;
        const p = pressed;
        pressed = null;
        if (p.timer) clearTimeout(p.timer);
        if (p.kind === "touch") {
            // The ring opened under the finger: lifting it is no tap.
            if (p.fired) { e.preventDefault(); e.stopImmediatePropagation(); }
            return;
        }
        e.stopImmediatePropagation();
        if (moved(e, p)) return;
        open(whatFor(p.event), { x: p.x, y: p.y });
    }, true);
    document.addEventListener("pointercancel", () => letGo(), true);
    // The browser's own menu: never over the world, nor where the ring was asked for
    // (the modifier held, or a long press under way); anywhere else it is the browser's.
    document.addEventListener("contextmenu", (e) => {
        if (isOpen()) { e.preventDefault(); return; }
        if (typing(e.target)) return;
        const spot = whatFor(e, { opening: false });
        if (!spot) return;
        if (spot === "world" || held(e) || (MAC && bound.modifier === "ctrl" && e.ctrlKey) || (pressed && pressed.kind === "touch")) e.preventDefault();
    });
    const btn = typeof button === "string" ? document.querySelector(button) : button;
    if (btn) btn.addEventListener("click", () => { if (isOpen()) close(); else fromKeyboard(); });

    const api = {
        open: (spec, at) => open(spec, at),
        /* The keys and the modifier, changed: at once, for the next press. */
        configure({ key: nextKey, canvasKey: nextCanvasKey, modifier: nextModifier } = {}) {
            if (typeof nextKey === "string" && nextKey) bound.key = nextKey;
            if (typeof nextCanvasKey === "string" && nextCanvasKey) bound.canvasKey = nextCanvasKey;
            if (MODIFIERS[nextModifier]) bound.modifier = nextModifier;
            return { ...bound };
        },
        bound: () => ({ ...bound }),
        comboOf,
        close,
        isOpen,
        nearest,
        addressOf,
        addresses,
        angleToIndex,
        cellAtAngle,
        annotate,
        resolve: (spec) => resolveRing({ base, ...spec }),
        current: () => current,
        /* Whether an arrow pressed now would make a corner with the last one. */
        chordOpen: () => !!(current && current.lastArrow && performance.now() - current.lastArrow.t <= GEOMETRY.chordMs),
        PLACEMENT,
        COMPASS,
        GEOMETRY,
    };
    window.apothecaryRing = api;
    return api;
}
