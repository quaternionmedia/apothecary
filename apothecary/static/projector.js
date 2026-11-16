/* The projector's page: what a projector aimed at a machine's bed draws there, on a
 * black page of one canvas, for a second display. Black wherever nothing is drawn: a
 * projector lights what it draws.
 *
 * Everything drawn is the server's one answer (GET /surfaces/projector?site=&path=, which
 * is routes/projector.py's), drawn in the bed's millimetres through the mapping its
 * calibration fixes, scaled from the output it was calibrated for to this canvas: the
 * bed's outline, the toolpath about to be made (the layer or pass a job is in brighter),
 * a router plan's cuts, the tool where a poll put it, and the band -- the lines the
 * server wrote, in the canvas's own pixels along its foot. What a bed that carries Y
 * carries rides it, by where the last poll says the bed stands.
 *
 * The answer is kept current by the surfaces' one stream (GET /surfaces/events?names=
 * projector): a change of this machine's says what moves, taken as it is, and its
 * picture's key, asked again when it is another. The machine is followed as the world
 * follows one it draws (boards.js watch, live only while the server holds its link):
 * this page's polls are what move it when nothing else polls. It asks no port anything
 * itself.
 *
 * Calibration: C, or ?calibrate, or no calibration kept. Four markers stand for four
 * points of the bed (its calibration's, else the server's starting points); each is
 * dragged until its cross lights its point of the bed, and dropped, the four kept
 * (PUT .../projector) with this canvas's size; a grid every 10 mm of the bed is drawn
 * through the mapping kept, so how true it is shows. A refusal is said in the band.
 * A click goes full screen, which only a gesture may ask.
 */

import { mountBoards } from "/static/boards.js";

// A machine is polled this often while followed, as the world polls one it draws.
export const POLL_MS = 2000;
// The calibration's grid: a line every GRID_MM of the bed, every fifth a shade brighter.
export const GRID_MM = 10;
// How near a marker a press must be to take hold of it, in CSS pixels.
const GRAB_PX = 40;
export const INK = {
    bed: "#3c3c3c",
    path: "#2f5a33",
    now: "#6fdb75",
    cuts: "#ffcc66",
    tool: "#ff8080",
    grid: "#262626",
    gridBold: "#4a4a4a",
    marker: "#ffffff",
    band: "#d8d8d8",
    said: "#ffcc66",
    refused: "#ff8080",
};

// --- what is drawn, as numbers: no canvas needed ------------------------------------------

// Where (x, y) lands through a mapping (apothecary/homography.py's apply).
export function apply(m, x, y) {
    const w = m[2][0] * x + m[2][1] * y + m[2][2];
    return [(m[0][0] * x + m[0][1] * y + m[0][2]) / w, (m[1][0] * x + m[1][1] * y + m[1][2]) / w];
}

// A point of the frame on this canvas: the output's pixel, scaled to the canvas.
export function toCanvas(answer, width, height, x, y) {
    const [u, v] = apply(answer.mapping, x, y);
    return [(u * width) / answer.size[0], (v * height) / answer.size[1]];
}

// Whether where the bed stands is known, so what is on it can be drawn.
export function bedKnown(answer) {
    return typeof answer.moving.bed_offset === "number";
}

// A point of the bed in the frame, the bed standing where the poll says.
export function onBed(answer, x, y) {
    return [x, y + answer.moving.bed_offset];
}

// The grid over the volume's floor, in the bed's millimetres: [x0, y0, x1, y1, bold].
export function gridLines(volume, pitch = GRID_MM) {
    const [vx, vy] = volume;
    const out = [];
    const along = (span, line) => {
        const n = Math.ceil(span / pitch - 1e-6);
        for (let i = 0; i <= n; i++) out.push([...line(Math.min(i * pitch, span)), i % 5 === 0]);
    };
    along(vx, (x) => [x, 0, x, vy]);
    along(vy, (y) => [0, y, vx, y]);
    return out;
}

// What a change of the stream is to this page: "again" when it is this machine's and its
// picture is another than the one drawn, "moved" when only what moves has, else null.
export function take(answer, change, key) {
    if (!change || change.surface !== "projector" || change.key !== key) return null;
    if (!answer || !change.body || change.body.key !== answer.picture.key) return "again";
    return "moved";
}

// Where the markers stand on a canvas: the calibration's pixels, scaled from its output
// to the canvas; with none, the canvas set in by a quarter, the bed's front left at the
// canvas's bottom left, its order the bed points' (front left, front right, back right,
// back left).
export function startingMarkers(answer, width, height) {
    const kept = answer && answer.calibration;
    if (kept) return kept.pixels.map(([u, v]) => [(u * width) / kept.size[0], (v * height) / kept.size[1]]);
    return [
        [width / 4, (3 * height) / 4],
        [(3 * width) / 4, (3 * height) / 4],
        [(3 * width) / 4, height / 4],
        [width / 4, height / 4],
    ];
}

// The four bed points the markers stand for.
export function markedPoints(answer) {
    return answer.calibration ? answer.calibration.bed : answer.starting_points;
}

// The body a calibration is kept with: the four bed points, the markers' pixels within the
// canvas, and the canvas's size.
export function calibrationBody(answer, markers, width, height) {
    const within = (v, most) => Math.round(Math.min(Math.max(v, 0), most) * 100) / 100;
    return {
        bed: markedPoints(answer),
        pixels: markers.map(([u, v]) => [within(u, width), within(v, height)]),
        size: [width, height],
    };
}

// --- the page ------------------------------------------------------------------------------

export function mountProjector({ canvas, base = "", site, path, calibrate = false }) {
    const key = `${site}/${path}`;
    const ctx = canvas.getContext("2d");
    const at = `${base}/sites/${encodeURIComponent(site)}/machines/${encodeURIComponent(path)}/projector`;
    const state = {
        answer: null, error: null, refused: null, calibrating: calibrate, markers: null,
        held: null, dragged: false, port: null, live: false, asking: null, askAgain: false,
        drawn: { segments: 0, cuts: 0, tool: false, grid: 0 },
    };
    const who = { projector: key };
    const dpr = () => window.devicePixelRatio || 1;

    function fit() {
        const width = Math.max(1, Math.round(canvas.clientWidth * dpr()));
        const height = Math.max(1, Math.round(canvas.clientHeight * dpr()));
        if (canvas.width === width && canvas.height === height) return;
        canvas.width = width;
        canvas.height = height;
        if (state.answer && state.held === null) state.markers = startingMarkers(state.answer, width, height);
        draw();
    }

    // --- the answer, through the surfaces ------------------------------------------------
    async function ask() {
        const r = await fetch(`${base}/surfaces/projector?site=${encodeURIComponent(site)}&path=${encodeURIComponent(path)}`);
        const body = await r.json().catch(() => ({}));
        if (!r.ok) throw new Error(typeof body.detail === "string" ? body.detail : r.statusText);
        state.answer = body.snapshot;
        state.error = null;
        if (!state.answer.calibration) state.calibrating = true;
        if (state.held === null) state.markers = startingMarkers(state.answer, canvas.width, canvas.height);
        draw();
    }
    function again() {
        if (state.asking) { state.askAgain = true; return state.asking; }
        state.asking = ask()
            .catch((e) => { state.error = e.message; draw(); })
            .finally(() => {
                state.asking = null;
                if (state.askAgain) { state.askAgain = false; again(); }
            });
        return state.asking;
    }
    function heard(change) {
        const what = take(state.answer, change, key);
        if (what === "again") again();
        else if (what === "moved") { state.answer.moving = change.body.moving; draw(); }
    }
    // Each time the stream opens -- and again after it dropped -- the answer is asked
    // afresh, so a change missed meanwhile is not.
    const stream = new EventSource(`${base}/surfaces/events?names=projector`);
    stream.addEventListener("surfaces", again);
    stream.addEventListener("missed", again);
    stream.addEventListener("change", (e) => heard(JSON.parse(e.data)));

    // --- the machine, followed as the world follows one ---------------------------------
    const boards = mountBoards({ base, site: () => site });
    function followLive() {
        if (!state.port) return;
        const live = boards.isHeld(state.port);
        if (live === state.live) return;
        state.live = live;
        boards.setWatch(state.port, who, { live });
    }
    async function follow() {
        await boards.scan();
        const row = Object.values(boards.rows).find((r) => r.device && r.device.printer && (r.path === path || r.path.startsWith(`${path}.`)));
        if (!row) return;
        state.port = row.device.port;
        const kind = row.device.printer.machine === "router" ? "router" : "printer";
        boards.watch(state.port, who, { kind, interval: POLL_MS, live: false });
        followLive();
    }
    window.addEventListener("apothecary:board", followLive);

    // --- drawing ----------------------------------------------------------------------------
    function stroke(points, colour, width) {
        ctx.strokeStyle = colour;
        ctx.lineWidth = width;
        ctx.beginPath();
        for (let i = 0; i < points.length; i++) {
            const [x, y] = points[i];
            if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
        }
        ctx.stroke();
    }
    function segments(a, flat, first, count, colour, width) {
        const { width: w, height: h } = canvas;
        ctx.strokeStyle = colour;
        ctx.lineWidth = width;
        ctx.beginPath();
        for (let i = first; i < first + count; i++) {
            const k = i * 4;
            ctx.moveTo(...toCanvas(a, w, h, ...onBed(a, flat[k], flat[k + 1])));
            ctx.lineTo(...toCanvas(a, w, h, ...onBed(a, flat[k + 2], flat[k + 3])));
        }
        ctx.stroke();
        return count;
    }
    function drawBed(a, line) {
        const { width: w, height: h } = canvas;
        const bed = (p) => toCanvas(a, w, h, ...onBed(a, p[0], p[1]));
        const outline = a.picture.bed.outline;
        stroke([...outline, outline[0]].map(bed), INK.bed, line);
        if (state.calibrating) {
            const grid = gridLines(a.frame.volume);
            for (const [x0, y0, x1, y1, bold] of grid) stroke([bed([x0, y0]), bed([x1, y1])], bold ? INK.gridBold : INK.grid, line);
            state.drawn.grid = grid.length;
        }
        const path = a.picture.toolpath;
        if (path) {
            const all = path.segments.length / 4;
            state.drawn.segments = segments(a, path.segments, 0, all, INK.path, line);
            const now = a.moving.current !== null ? path.groups[a.moving.current] : null;
            if (now) segments(a, path.segments, now.first, now.count, INK.now, line * 2);
        }
        const cuts = a.picture.cuts;
        if (cuts && cuts.shapes) {
            for (const shape of cuts.shapes) stroke(shape.points.map(bed), INK.cuts, line);
            state.drawn.cuts = cuts.shapes.length;
        }
    }
    function drawTool(a, line) {
        if (!a.moving.tool) return;
        const { width: w, height: h } = canvas;
        const [x, y] = a.moving.tool;
        const r = 12 * line;
        const [cx, cy] = toCanvas(a, w, h, x, y);
        stroke([[cx - r, cy], [cx + r, cy]], INK.tool, line);
        stroke([[cx, cy - r], [cx, cy + r]], INK.tool, line);
        state.drawn.tool = true;
    }
    function drawMarkers(a, line) {
        const points = markedPoints(a);
        const r = 18 * dpr();
        stroke([...state.markers, state.markers[0]], INK.gridBold, line);
        ctx.font = `${Math.round(14 * dpr())}px sans-serif`;
        ctx.fillStyle = INK.marker;
        state.markers.forEach(([x, y], i) => {
            stroke([[x - r, y], [x + r, y]], INK.marker, line);
            stroke([[x, y - r], [x, y + r]], INK.marker, line);
            ctx.beginPath();
            ctx.arc(x, y, r * 0.6, 0, 2 * Math.PI);
            ctx.stroke();
            ctx.fillText(`${points[i][0]}, ${points[i][1]} mm`, x + r, y - r);
        });
    }
    function drawBand(a) {
        const size = Math.max(12, Math.round(canvas.height / 40));
        const lines = [];
        if (state.error) lines.push([state.error, INK.refused]);
        if (state.refused) lines.push([state.refused, INK.refused]);
        if (a) {
            for (const text of a.moving.status.lines) lines.push([text, INK.band]);
            for (const text of [...a.moving.said, ...a.picture.said]) lines.push([text, INK.said]);
        }
        ctx.font = `${size}px sans-serif`;
        lines.forEach(([text, colour], i) => {
            ctx.fillStyle = colour;
            ctx.fillText(text, size, canvas.height - size * (lines.length - i));
        });
        state.band = lines.map(([text]) => text);
    }
    function draw() {
        const a = state.answer;
        const line = Math.max(1, canvas.width / 960);
        state.drawn = { segments: 0, cuts: 0, tool: false, grid: 0 };
        ctx.fillStyle = "#000";
        ctx.fillRect(0, 0, canvas.width, canvas.height);
        if (a && a.mapping) {
            if (bedKnown(a)) drawBed(a, line);
            drawTool(a, line);
        }
        if (a && state.calibrating && state.markers) drawMarkers(a, line);
        canvas.classList.toggle("calibrating", state.calibrating);
        drawBand(a);
    }

    // --- calibrating: four markers dragged and dropped ----------------------------------------
    async function keep() {
        const body = calibrationBody(state.answer, state.markers, canvas.width, canvas.height);
        const r = await fetch(at, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
        const said = await r.json().catch(() => ({}));
        if (!r.ok) { state.refused = typeof said.detail === "string" ? said.detail : r.statusText; draw(); return false; }
        state.refused = null;
        state.answer = said;
        draw();
        return true;
    }
    const pointAt = (e) => {
        const box = canvas.getBoundingClientRect();
        return [(e.clientX - box.left) * dpr(), (e.clientY - box.top) * dpr()];
    };
    canvas.addEventListener("pointerdown", (e) => {
        state.dragged = false;
        if (!state.calibrating || !state.markers) return;
        const [x, y] = pointAt(e);
        const near = state.markers.map(([mx, my], i) => [Math.hypot(mx - x, my - y), i]).sort((p, q) => p[0] - q[0])[0];
        if (near[0] > GRAB_PX * dpr()) return;
        state.held = near[1];
        canvas.setPointerCapture(e.pointerId);
    });
    canvas.addEventListener("pointermove", (e) => {
        if (state.held === null) return;
        state.markers[state.held] = pointAt(e);
        state.dragged = true;
        draw();
    });
    canvas.addEventListener("pointerup", () => {
        if (state.held === null) return;
        state.held = null;
        if (state.dragged) keep();
    });
    canvas.addEventListener("click", () => {
        if (state.dragged || document.fullscreenElement) return;
        const asked = document.documentElement.requestFullscreen && document.documentElement.requestFullscreen();
        if (asked && asked.catch) asked.catch(() => {});
    });
    window.addEventListener("keydown", (e) => {
        if (e.key === "c" || e.key === "C") state.calibrating = !state.calibrating;
        else if (e.key === "Escape") state.calibrating = false;
        else return;
        if (state.answer && state.held === null) state.markers = startingMarkers(state.answer, canvas.width, canvas.height);
        draw();
    });
    window.addEventListener("resize", fit);

    fit();
    follow().catch(() => {});

    return {
        // What is drawn, for the page's tests: no pixel is read back.
        stats() {
            return {
                key: state.answer ? state.answer.picture.key : null,
                calibrated: !!(state.answer && state.answer.mapping),
                calibrating: state.calibrating,
                markers: state.markers ? state.markers.map((p) => [...p]) : null,
                drawn: { ...state.drawn },
                band: [...(state.band || [])],
                port: state.port,
                live: state.live,
                size: [canvas.width, canvas.height],
            };
        },
        answer: () => state.answer,
        ask: again,
        keep,
        destroy() {
            stream.close();
            if (state.port) boards.unwatch(state.port, who);
            boards.destroy();
            window.removeEventListener("apothecary:board", followLive);
            window.removeEventListener("resize", fit);
        },
    };
}
