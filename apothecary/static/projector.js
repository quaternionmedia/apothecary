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
 * Which plane is drawn for is the server's too (answer.plane): the bed's outline and a
 * printer's footprint lie through the bed plane's mapping, the toolpath, the cuts and the
 * tool through plane.mapping -- the layer's or the stock's height when a second plane is
 * calibrated, else the bed plane's -- and the band's line names it.
 *
 * Calibration: C, or ?calibrate, or no calibration kept. Four markers stand for four
 * points of the bed (its calibration's, else the server's starting points); each is
 * dragged until its cross lights its point of the bed, and dropped, the four kept
 * (PUT .../projector) with this canvas's size; a grid every 10 mm of the bed is drawn
 * through the mapping kept, so how true it is shows. A refusal is said in the band.
 * The second plane is marked the same way with a flat piece of known thickness on the
 * bed: ?upper=<mm> names its thickness (or one is kept), U marks it, the four kept with
 * PUT .../projector/upper and the grid drawn through the second plane's own mapping.
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
    footprint: "#3f7fa8",
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

// A point of the frame on this canvas: the output's pixel, scaled to the canvas, through the
// bed plane's mapping unless another is given (the plane's, the second plane's).
export function toCanvas(answer, width, height, x, y, mapping = answer.mapping) {
    const [u, v] = apply(mapping, x, y);
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

// The mapping of the plane the toolpath, the cuts and the tool are drawn for: the answer's
// plane, which is the bed plane's when one calibration is kept.
export function planeMapping(answer) {
    return (answer.plane && answer.plane.mapping) || answer.mapping;
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
export function startingMarkers(answer, width, height, upper = false) {
    const kept = answer && answer.calibration;
    if (kept && upper && kept.upper) return kept.upper.pixels.map(([u, v]) => [(u * width) / kept.size[0], (v * height) / kept.size[1]]);
    if (kept) return kept.pixels.map(([u, v]) => [(u * width) / kept.size[0], (v * height) / kept.size[1]]);
    return [
        [width / 4, (3 * height) / 4],
        [(3 * width) / 4, (3 * height) / 4],
        [(3 * width) / 4, height / 4],
        [width / 4, height / 4],
    ];
}

// The four bed points the markers stand for.
export function markedPoints(answer, upper = false) {
    if (upper && answer.calibration && answer.calibration.upper) return answer.calibration.upper.bed;
    return answer.calibration ? answer.calibration.bed : answer.starting_points;
}

// The body a second plane is kept with: the markers' pixels within the canvas, the canvas's
// size and the thickness of the piece they were marked on; the bed's points are the
// calibration's unless a second plane already holds others.
export function upperBody(answer, markers, width, height, mm) {
    const within = (v, most) => Math.round(Math.min(Math.max(v, 0), most) * 100) / 100;
    const kept = answer.calibration && answer.calibration.upper;
    const body = { pixels: markers.map(([u, v]) => [within(u, width), within(v, height)]), size: [width, height], height: mm };
    if (kept) body.bed = kept.bed;
    return body;
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

export function mountProjector({ canvas, base = "", site, path, calibrate = false, upper = null }) {
    const key = `${site}/${path}`;
    const ctx = canvas.getContext("2d");
    const at = `${base}/sites/${encodeURIComponent(site)}/machines/${encodeURIComponent(path)}/projector`;
    const state = {
        answer: null, error: null, refused: null, calibrating: calibrate, markers: null,
        upperMm: upper > 0 ? Number(upper) : null, upperMarking: upper > 0,
        held: null, dragged: false, port: null, live: false, asking: null, askAgain: false,
        drawn: { segments: 0, cuts: 0, tool: false, grid: 0, footprint: 0 },
    };
    const who = { projector: key };
    const dpr = () => window.devicePixelRatio || 1;
    // Whether the markers stand for the second plane: asked for, and the bed plane calibrated.
    const marking = () => !!(state.upperMarking && state.answer && state.answer.calibration);
    const upperHeight = () => state.upperMm || (state.answer && state.answer.calibration && state.answer.calibration.upper ? state.answer.calibration.upper.height : null);
    const markersFor = (a) => startingMarkers(a, canvas.width, canvas.height, marking());

    function fit() {
        const width = Math.max(1, Math.round(canvas.clientWidth * dpr()));
        const height = Math.max(1, Math.round(canvas.clientHeight * dpr()));
        if (canvas.width === width && canvas.height === height) return;
        canvas.width = width;
        canvas.height = height;
        if (state.answer && state.held === null) state.markers = markersFor(state.answer);
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
        if (state.held === null) state.markers = markersFor(state.answer);
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
        else if (what === "moved") {
            state.answer.moving = change.body.moving;
            if (change.body.plane) state.answer.plane = change.body.plane;
            draw();
        }
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
        const m = planeMapping(a);
        ctx.strokeStyle = colour;
        ctx.lineWidth = width;
        ctx.beginPath();
        for (let i = first; i < first + count; i++) {
            const k = i * 4;
            ctx.moveTo(...toCanvas(a, w, h, ...onBed(a, flat[k], flat[k + 1]), m));
            ctx.lineTo(...toCanvas(a, w, h, ...onBed(a, flat[k + 2], flat[k + 3]), m));
        }
        ctx.stroke();
        return count;
    }
    function drawBed(a, line) {
        const { width: w, height: h } = canvas;
        const through = (m) => (p) => toCanvas(a, w, h, ...onBed(a, p[0], p[1]), m);
        const bed = through(a.mapping);
        const plane = through(planeMapping(a));
        const outline = a.picture.bed.outline;
        stroke([...outline, outline[0]].map(bed), INK.bed, line);
        const footprint = a.picture.footprint;
        if (footprint) {
            stroke(footprint.points.map(bed), INK.footprint, line * 2);
            state.drawn.footprint = footprint.points.length;
        }
        if (state.calibrating) {
            // The second plane's grid lies through its own mapping, the bed plane's through the bed's.
            const grid = gridLines(a.frame.volume);
            const on = marking() && a.upper_mapping ? through(a.upper_mapping) : bed;
            for (const [x0, y0, x1, y1, bold] of grid) stroke([on([x0, y0]), on([x1, y1])], bold ? INK.gridBold : INK.grid, line);
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
            for (const shape of cuts.shapes) stroke(shape.points.map(plane), INK.cuts, line);
            state.drawn.cuts = cuts.shapes.length;
        }
    }
    function drawTool(a, line) {
        if (!a.moving.tool) return;
        const { width: w, height: h } = canvas;
        const [x, y] = a.moving.tool;
        const r = 12 * line;
        const [cx, cy] = toCanvas(a, w, h, x, y, planeMapping(a));
        stroke([[cx - r, cy], [cx + r, cy]], INK.tool, line);
        stroke([[cx, cy - r], [cx, cy + r]], INK.tool, line);
        state.drawn.tool = true;
    }
    function drawMarkers(a, line) {
        const points = markedPoints(a, marking());
        const mm = marking() ? ` @ ${upperHeight() === null ? "?" : upperHeight()} mm up` : "";
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
            ctx.fillText(`${points[i][0]}, ${points[i][1]} mm${mm}`, x + r, y - r);
        });
    }
    function drawBand(a) {
        const size = Math.max(12, Math.round(canvas.height / 40));
        const lines = [];
        if (state.error) lines.push([state.error, INK.refused]);
        if (state.refused) lines.push([state.refused, INK.refused]);
        if (a) {
            for (const text of a.moving.status.lines) lines.push([text, INK.band]);
            if (a.plane && a.plane.line) lines.push([a.plane.line, INK.band]);
            const said = [...(a.plane ? a.plane.said : []), ...a.moving.said, ...a.picture.said];
            if (marking() && upperHeight() === null) said.push("the second plane's thickness is not named: open the page with ?upper=<mm>");
            for (const text of said) lines.push([text, INK.said]);
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
        state.drawn = { segments: 0, cuts: 0, tool: false, grid: 0, footprint: 0 };
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
        const second = marking() && upperHeight() !== null;
        if (marking() && !second) { state.refused = "the second plane's thickness is not named: open the page with ?upper=<mm>"; draw(); return false; }
        const body = second
            ? upperBody(state.answer, state.markers, canvas.width, canvas.height, upperHeight())
            : calibrationBody(state.answer, state.markers, canvas.width, canvas.height);
        const r = await fetch(second ? `${at}/upper` : at, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
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
        if (e.key === "c" || e.key === "C") { state.calibrating = !state.calibrating; state.upperMarking = false; }
        else if (e.key === "u" || e.key === "U") { state.upperMarking = !state.upperMarking; state.calibrating = true; }
        else if (e.key === "Escape") state.calibrating = false;
        else return;
        if (state.answer && state.held === null) state.markers = markersFor(state.answer);
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
                marking: marking() ? "upper" : "bed",
                plane: state.answer && state.answer.plane ? { z: state.answer.plane.z, for: state.answer.plane.for, how: state.answer.plane.how } : null,
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
