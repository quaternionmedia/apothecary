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
 * Plain ES module, no build step, no dependencies. The pure parts (angle to
 * slot, nearest cell in a direction, addresses) are exported so a test can
 * compare them with the Python resolver's; the same four are on
 * window.apothecaryRing.
 */

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
// time an action turns up wins, as every_action() in menu.py does.
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
 * element as it was. Ids and classes are never touched: the census keys on
 * them.
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

export async function resolveRing({ base = "", context, site, device }) {
    const body = { context };
    if (site) body.site = site;
    if (device) body.device = device;
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
.apothecary-ring .hub { fill: #141614; stroke: #3a443a; stroke-width: 1.5; cursor: pointer; }
.apothecary-ring text { fill: #d8e0d8; pointer-events: none; user-select: none; }
.apothecary-ring .label { font-size: 12px; text-anchor: middle; }
.apothecary-ring .digit { font-size: 9px; fill: #9aa89a; text-anchor: middle; }
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
 * chosen; onClose when it goes away for any reason.
 */
export async function openRing({ base = "", context, site, device, at = null, onIntent, onClose }) {
    close();
    const ring = await resolveRing({ base, context, site, device });
    if (current) current.close(false); // somebody opened another while we fetched
    const instance = new RingInstance({ ring, context, site, device, at, onIntent, onClose });
    current = instance;
    instance.mount();
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
            const [lx, ly] = polar((r0 + r1) / 2 + 2, centre);
            const [dx, dy] = polar(r1 - 11, centre);
            const cls = ["wedge"];
            if (!option) cls.push("empty");
            else {
                if (option.enabled === false) cls.push("disabled");
                if (option.destructive) cls.push("destructive");
                if (this.highlight === cell) cls.push("hot");
            }
            const label = option ? esc(option.label) + (option.children ? " ›" : "") : "";
            parts.push(
                `<path class="${cls.join(" ")}" data-cell="${cell}" role="menuitem"`
                + ` aria-label="${option ? esc(option.label) : "empty"}"`
                + `${option ? "" : ' aria-disabled="true"'} d="${wedgePath(slot, r0, r1)}"></path>`
                + (option ? `<text class="label" x="${lx.toFixed(1)}" y="${(ly + 4).toFixed(1)}">${label}</text>` : "")
                + `<text class="digit${option ? "" : " empty-digit"}" x="${dx.toFixed(1)}" y="${(dy + 3).toFixed(1)}">${cell}</text>`
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
            site: this.site,
            device: this.device,
        };
        this.close(true);
        window.dispatchEvent(new CustomEvent("apothecary:intent", { detail: intent }));
        if (this.onIntent) this.onIntent(intent);
    }

    // One level out; at the top, away.
    back() {
        if (this.stack.length <= 1) { this.close(false); return; }
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
// The invokers: right-click, the m key, and a button
// ---------------------------------------------------------------------------

const TYPING = (el) => !!el && (el.matches("input, textarea, select, [contenteditable]"));

/* Bind the three ways in. `whatFor(event)` is the page's: given a contextmenu
 * event (or null for the key and the button) it says what the ring opens on --
 * {context, site, device, at} -- or null to leave the browser's own menu alone.
 * `onResolved(ring, spec)` fires after every resolve, for annotating the page.
 */
export function installRing({ base = "", whatFor, onIntent, onResolved, onError, button = "#ring-open", key = "m" }) {
    const open = async (spec, at) => {
        if (!spec) return null;
        try {
            const instance = await openRing({
                base,
                context: spec.context,
                site: spec.site,
                device: spec.device,
                at: at ?? spec.at ?? null,
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
    const fromKeyboard = () => open(whatFor(null), { x: window.innerWidth / 2, y: window.innerHeight / 2 });

    window.addEventListener("keydown", (e) => {
        if (e.key !== key || e.ctrlKey || e.metaKey || e.altKey || isOpen()) return;
        if (TYPING(document.activeElement)) return;
        e.preventDefault();
        fromKeyboard();
    });
    document.addEventListener("contextmenu", (e) => {
        if (isOpen() || TYPING(e.target)) return;
        const spec = whatFor(e);
        if (!spec) return;
        e.preventDefault();
        open(spec, { x: e.clientX, y: e.clientY });
    });
    const btn = typeof button === "string" ? document.querySelector(button) : button;
    if (btn) btn.addEventListener("click", () => { if (isOpen()) close(); else fromKeyboard(); });

    const api = {
        open: (spec, at) => open(spec, at),
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
        PLACEMENT,
        COMPASS,
        GEOMETRY,
    };
    window.apothecaryRing = api;
    return api;
}

export default { openRing, installRing, nearest, addressOf, addresses, angleToIndex, annotate, resolveRing };
