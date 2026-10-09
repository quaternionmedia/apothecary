/* Boards: one model of every board the page knows, and one poller per board.
 *
 * A board was drawn by six render functions and polled from four places, and
 * the drawings could disagree. Here it is one record per port -- the board as
 * detected, what it should run, its last poll, its link, what it was heard
 * saying, its log -- and everything that draws it (the world's badge, Site's
 * tree badge, Selected's Device line, its Machine) reads that record and redraws
 * on the one event this module sends: `apothecary:board`, whose detail says
 * which port (null for a scan) and what changed (`what`: scan, status, info,
 * device, observed, live, log, error).
 *
 * The scan is the site's bindings and the detected ports (GET
 * /sites/{name}/devices, or /firmware/devices on a page with no site), asked
 * for when a site loads and again by rescan(), the one way to look for boards
 * again; the model also rescans by itself, at most every so often, when a board
 * it is watching goes quiet, so a replugged board is found without anyone asking.
 *
 * A board is polled only while something watches it live -- its Machine,
 * open, with auto-poll on -- by one self-scheduled poller at the watcher's
 * interval: never two requests in flight for one board, and a one-shot poll
 * from a button shares the one in flight. A devkit watched live is listened
 * to instead: one serial stream per board, its lines in the board's log and
 * its hello banner as what it was heard saying. A devkit's Machine watches it
 * quiet until a person asks it to listen (its Listen), since opening the port
 * may reset the board. A printer is polled over the link the server holds,
 * never streamed: opening its port to listen would pulse DTR and reset it.
 *
 * Every request the model starts takes a number from one sequence, carried
 * in its event as `asked`; a host that changes something a poll reports (the
 * Machine's control latch) takes a number too (tick()), and knows an answer
 * asked for before its change is stale.
 */

const LOG_MAX = 5000;
const RETRY_MS = 5000;          // a stream that stopped is opened again this long after
const LOOK_AGAIN_MS = 10000;    // a watched board gone quiet is looked for at most this often
const HELLO = /apothecary\s+([A-Za-z0-9_.\-]+):\s*hello/;

export function mountBoards({ base = "", site = () => null } = {}) {
    const BASE = base;
    const all = new Map();  // port -> board
    let seq = 0, scanning = null, lookedAt = 0;

    const emit = (port, what, extra = {}) => window.dispatchEvent(new CustomEvent("apothecary:board", {
        detail: { port, what, board: port ? all.get(port) || null : null, ...extra },
    }));

    async function api(path, opts = {}) {
        const r = await fetch(BASE + path, { headers: { "Content-Type": "application/json" }, ...opts });
        const body = await r.json().catch(() => ({}));
        if (!r.ok) throw new Error(typeof body.detail === "string" ? body.detail : (body.detail ? JSON.stringify(body.detail) : r.statusText));
        return body;
    }
    const post = (path, body) => api(path, { method: "POST", body: JSON.stringify(body) });

    function board(port) {
        let b = all.get(port);
        if (!b) {
            b = {
                port, device: null, expected: null, status: null, info: null, observed: null, error: null,
                log: [], logNext: 0, logChain: Promise.resolve(),
                watchers: new Map(), timer: null, gen: 0, polling: null, stream: null, retry: null, live: false,
            };
            all.set(port, b);
        }
        return b;
    }

    // --- what is known of a board ------------------------------------------------------
    // A detected device's view ({ device, expected }), from a scan or an answer.
    function takeView(b, view) {
        if (!view) return;
        if (view.device) b.device = view.device;
        if (view.expected) b.expected = view.expected;
    }
    // Every row the port is bound to says the same as the board.
    function rowsOf(port) { return Object.values(model.rows).filter((row) => row.device && row.device.port === port); }
    function takeStatus(b, st, asked) {
        if (b.status && b.status.polled_at && st.polled_at && st.polled_at < b.status.polled_at) return;
        b.status = st; b.error = null;
        for (const row of rowsOf(b.port)) row.printer_status = st;
        emit(b.port, "status", { status: st, asked });
    }

    // --- the log: the server's comms log of a printer, a devkit's serial lines ------------
    function appendLog(b, entries) {
        b.log.push(...entries);
        const dropped = b.log.splice(0, Math.max(0, b.log.length - LOG_MAX));
        emit(b.port, "log", { entries, dropped });
    }
    function note(port, text, extra = {}) {
        if (!port) return;
        appendLog(board(port), [{ i: -1, t: new Date().toISOString(), kind: "sys", text, ...extra }]);
    }
    // One fetch at a time per board, and rows below the watermark dropped, so the
    // poller's pull and a button's can never double up.
    function pullLog(port) {
        const b = board(port);
        b.logChain = b.logChain.then(async () => {
            const data = await api(`/firmware/printers/log?port=${encodeURIComponent(port)}&since=${b.logNext}`);
            const fresh = data.entries.filter((e) => e.i >= b.logNext);
            if (fresh.length) appendLog(b, fresh);
            b.logNext = Math.max(b.logNext, data.next);
        }).catch(() => {});
        return b.logChain;
    }
    function clearLog(port) { const b = board(port); b.log = []; emit(port, "log", { entries: [], dropped: [], cleared: true }); }
    // A devkit's line, heard on its stream or in a listen.
    function heard(b, text) {
        appendLog(b, [{ i: -1, t: new Date().toISOString(), kind: "rx", text }]);
        const m = HELLO.exec(text);
        if (m && b.observed !== m[1]) { b.observed = m[1]; emit(b.port, "observed", { observed: m[1] }); }
    }

    // --- one poll, and the poller ----------------------------------------------------------
    async function loadInfo(port) {
        const b = board(port), asked = ++seq;
        const info = await api(`/firmware/printers/info?port=${encodeURIComponent(port)}`);
        b.info = info;
        takeView(b, info.device);
        if (info.last_status && !b.status) b.status = info.last_status;
        if (info.link) model.links.add(port); else model.links.delete(port);
        emit(port, "info", { info, asked });
        return info;
    }
    // One poll now, shared with any in flight. Resolves to the status; rejects
    // with what went wrong, which the board's error and its event say too.
    function poll(port) {
        const b = board(port);
        if (b.polling) return b.polling;
        const asked = ++seq;
        b.polling = (async () => {
            try {
                const st = await api(`/firmware/printers/status?port=${encodeURIComponent(port)}`);
                if (st.held) model.links.add(port); else model.links.delete(port);
                takeStatus(b, st, asked);
                // The link came or went (a failed poll drops it): the board card follows.
                if (!b.info || !!b.info.link !== !!st.held) await loadInfo(port).catch(() => {});
                return st;
            } catch (e) {
                b.error = e.message;
                emit(port, "error", { error: e.message });
                lookAgain(b);
                throw e;
            } finally {
                b.polling = null;
                pullLog(port);
            }
        })();
        return b.polling;
    }
    // The live watchers: a printer's poll interval is the shortest one asked for.
    const live = (b, kind) => [...b.watchers.values()].filter((w) => w.live && w.kind === kind);
    function interval(b) {
        const ms = live(b, "printer").map((w) => w.interval);
        return ms.length ? Math.min(...ms) : null;
    }
    // Self-scheduled, never overlapping: the next poll is asked for only once the
    // last has answered, and not while the page is hidden.
    function schedule(b) {
        clearTimeout(b.timer); b.timer = null;
        const gen = ++b.gen, ms = interval(b);
        if (ms === null || document.hidden) return;
        b.timer = setTimeout(async () => {
            if (gen !== b.gen) return;
            await poll(b.port).catch(() => {});
            if (gen === b.gen) schedule(b);
        }, ms);
    }

    // --- a devkit's serial stream ------------------------------------------------------------
    function openStream(b) {
        if (b.stream) return;
        clearTimeout(b.retry); b.retry = null;
        const es = new EventSource(`${BASE}/firmware/devices/stream?port=${encodeURIComponent(b.port)}&baud=115200`);
        b.stream = es;
        es.addEventListener("open", () => opened(b, es));
        es.onmessage = (ev) => heard(b, ev.data);
        es.addEventListener("close", () => streamStopped(b, es, "the stream stopped -- a task took the port?"));
        es.onerror = () => { if (es.readyState === EventSource.CLOSED) streamStopped(b, es, "disconnected"); };
    }
    // The browser's open and the server's own say the same thing: said once.
    function opened(b, es) {
        if (b.stream !== es || b.live) return;
        b.live = true;
        note(b.port, `listening to ${b.port} @ 115200 -- opening the port may have reset the board`);
        emit(b.port, "live", { live: true });
    }
    function closeStream(b) {
        clearTimeout(b.retry); b.retry = null;
        if (!b.stream) return;
        b.stream.close(); b.stream = null;
        if (b.live) { b.live = false; emit(b.port, "live", { live: false }); }
    }
    function streamStopped(b, es, why) {
        if (b.stream !== es) return;
        closeStream(b);
        if (!live(b, "devkit").length) return;
        note(b.port, `${why} -- listening again in ${RETRY_MS / 1000} s`);
        b.retry = setTimeout(() => { if (live(b, "devkit").length) openStream(b); }, RETRY_MS);
        lookAgain(b);
    }

    // --- watching: what makes a board polled or listened to -------------------------------------
    function follow(b, fresh = false) {
        if (live(b, "devkit").length) openStream(b); else closeStream(b);
        if (fresh && live(b, "printer").length) poll(b.port).catch(() => {}).finally(() => schedule(b));
        else schedule(b);
    }
    // `who` is the watcher (any object), `kind` what it takes the board for:
    // "printer" is polled, "devkit" listened to; `live` false keeps it watched
    // and quiet. A first live printer watcher polls at once.
    function watch(port, who, { kind = "printer", interval: ms = 2000, live: on = true } = {}) {
        const b = board(port);
        const was = live(b, kind).length;
        b.watchers.set(who, { kind, interval: ms, live: on });
        follow(b, !was && on);
        return () => unwatch(port, who);
    }
    function setWatch(port, who, patch) {
        const b = board(port), w = b.watchers.get(who);
        if (!w) return;
        const was = live(b, w.kind).length;
        Object.assign(w, patch);
        follow(b, !was && w.live);
    }
    function unwatch(port, who) {
        const b = all.get(port);
        if (!b || !b.watchers.delete(who)) return;
        follow(b);
    }
    // A watched board that went quiet may have been replugged on another port:
    // the model's own scan looks again, at most every LOOK_AGAIN_MS.
    function lookAgain(b) {
        if (!b.watchers.size || Date.now() - lookedAt < LOOK_AGAIN_MS) return;
        rescan();
    }

    // --- asking a board what it is ---------------------------------------------------------------
    // M115: is this a printer, and which firmware? Opens and keeps the link.
    async function identify(port) {
        const b = board(port);
        note(port, `asking ${port} M115 (no reset)`);
        try {
            const view = await post("/firmware/devices/identify", { port });
            takeView(b, view);
            model.links.add(port);
            for (const row of rowsOf(port)) { row.device = view.device; row.expected = view.expected; }
            const known = model.devices.find((v) => v.device.port === port);
            if (known) Object.assign(known, view);
            emit(port, "device", { device: view.device });
            await loadInfo(port).catch(() => {});
            return view;
        } finally { await pullLog(port); }
    }
    // A devkit's hello: listen a few seconds (the stream, if open, gives the port
    // up meanwhile and is opened again after) and keep what it said.
    async function listen(port, seconds = 6) {
        const b = board(port);
        closeStream(b);
        note(port, `listening ${seconds} s for the sketch's hello`);
        try {
            const r = await post("/firmware/devices/listen", { port, seconds });
            for (const line of r.lines) heard(b, line);
            if (r.running_sketch && b.observed !== r.running_sketch) { b.observed = r.running_sketch; emit(port, "observed", { observed: b.observed }); }
            note(port, r.running_sketch ? `heard ${r.running_sketch} say hello` : `no hello in ${r.seconds} s (${r.lines.length} lines)`);
            return r;
        } finally { follow(b); }
    }
    // The stream closed and opened again, for a devkit listened to: Reconnect.
    function restream(port) {
        const b = board(port);
        closeStream(b);
        follow(b);
    }
    // esptool's chip, MAC and flash size (it resets the board): the stream, if
    // open, gives the port up meanwhile and is opened again after.
    async function probe(port) {
        const b = board(port);
        closeStream(b);
        note(port, `probing ${port} with esptool (this resets the board)`);
        try {
            const view = await post("/firmware/devices/probe", { port });
            takeView(b, view);
            const known = model.devices.find((v) => v.device.port === port);
            if (known) Object.assign(known, view);
            note(port, view.device.chip ? `${view.device.chip} rev ${view.device.revision || "?"} · MAC ${view.device.mac || "?"} · flash ${view.device.flash_size || "?"}` : "esptool answered with no chip");
            emit(port, "device", { device: view.device });
            return view;
        } finally { follow(b); }
    }
    // A report code (M503, M119 ...) over the held link; its answer is in the log.
    async function query(port, command) {
        try { return await post("/firmware/printers/query", { port, command }); } finally { await pullLog(port); }
    }
    // The link verbs, each answered with what the board says afterwards.
    async function reconnect(port) {
        const b = board(port);
        try {
            const st = await post("/firmware/printers/reconnect", { port });
            takeStatus(b, st, ++seq);
            await loadInfo(port).catch(() => {});
            return st;
        } finally { await pullLog(port); }
    }
    async function reset(port) {
        try { const r = await post("/firmware/printers/reset", { port }); await loadInfo(port).catch(() => {}); return r; } finally { await pullLog(port); }
    }
    async function release(port) {
        const r = await post("/firmware/printers/release", { port });
        model.links.delete(port);
        await loadInfo(port).catch(() => {});
        return r;
    }

    // --- the scan ------------------------------------------------------------------------------------
    // The site's bindings and the detected ports: rows by path, the devices, and
    // any toolchain problem to show instead. One at a time; asked again while
    // one is in flight, that one answers.
    function scan({ fresh = false } = {}) {
        if (scanning) return scanning;
        model.scanning = true;
        const name = site();
        scanning = (async () => {
            try {
                const data = await api(name
                    ? `/sites/${encodeURIComponent(name)}/devices${fresh ? "?fresh=1" : ""}`
                    : `/firmware/devices${fresh ? "?fresh=1" : ""}`);
                model.rows = name ? Object.fromEntries(data.bindings.map((row) => [row.path, row])) : {};
                model.devices = data.devices || [];
                model.problem = data.problem || null;
                model.links = new Set(data.printers || []);
                for (const view of model.devices) takeView(board(view.device.port), view);
                for (const row of Object.values(model.rows)) {
                    if (!row.device) continue;
                    const b = board(row.device.port);
                    takeView(b, { device: row.device, expected: row.expected });
                    if (row.printer_status) takeStatus(b, row.printer_status, ++seq);
                }
            } catch (e) {
                model.rows = {}; model.devices = []; model.problem = e.message;
            } finally {
                model.loaded = true; model.scanning = false; scanning = null;
            }
            emit(null, "scan", { fresh });
            return model;
        })();
        return scanning;
    }
    // The one way to look for boards again: a fresh port scan.
    async function rescan() {
        lookedAt = Date.now();
        if (scanning) await scanning;
        return scan({ fresh: true });
    }
    // A pin made or taken back: the row the server answered with. A printer whose
    // link is held is polled once, so the node it drives follows it from now
    // (the pin itself talks to no printer).
    function setRow(path, row) {
        if (row && row.binding_source) model.rows[path] = row; else delete model.rows[path];
        const port = row && row.device && row.device.port;
        if (!port) return null;
        const b = board(port);
        takeView(b, { device: row.device, expected: row.expected });
        if (row.device.printer && model.links.has(port)) return poll(port).catch(() => null);
        return null;
    }
    function forget() {
        model.rows = {}; model.devices = []; model.problem = null; model.loaded = false;
    }

    // --- the page itself ---------------------------------------------------------------------------
    function onVisibility() { for (const b of all.values()) schedule(b); }
    document.addEventListener("visibilitychange", onVisibility);
    function onUnload() { for (const b of all.values()) { b.gen++; clearTimeout(b.timer); closeStream(b); } }
    window.addEventListener("beforeunload", onUnload);

    const model = {
        rows: {}, devices: [], problem: null, loaded: false, scanning: false, links: new Set(),
        board, boards: () => [...all.values()], scan, rescan, setRow, forget,
        poll, watch, setWatch, unwatch, loadInfo, identify, listen, probe, restream, query, reconnect, reset, release,
        pullLog, clearLog, note, tick: () => ++seq, api, post,
        isHeld: (port) => model.links.has(port),
        destroy() {
            onUnload();
            document.removeEventListener("visibilitychange", onVisibility);
            window.removeEventListener("beforeunload", onUnload);
            all.clear();
        },
    };
    return model;
}
