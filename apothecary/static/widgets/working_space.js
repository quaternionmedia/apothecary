/* Working space: a site as every kind of evidence has it (apothecary/evidence/,
 * GET /sites/{s}/evidence), and a printer's timeline in it.
 *
 * Opened on the site (Panels › Site › Working space) it lists every subject the
 * log has said of: each property's value, how it is known (its origin and whether
 * its sources agree) and whether its source is still heard or the value is last
 * known. Opened on a printer (Working space, on the printer's ring) it is that
 * printer's hour: its state as a strip, its heaters' temperatures as lines, and a
 * row for each camera that looks at it, the frames kept with its polls. Every
 * mark and every row opens its evidence underneath: a poll's lines, a frame.
 *
 * While it is open on a printer it watches the printer's board (boards.js, its
 * one poller) and keeps a frame set with its polls: a frame from each of the
 * printer's cameras whose device is this browser's, when the printer's state
 * changes and at every 5 % of its progress, never closer together than ten
 * seconds, each posted with the poll's id (POST /photos/pictures?site=&camera=
 * &poll=). A camera whose device is another browser's, or none, is named once
 * and left out.
 *
 * mountWorkingSpace(root, { base, boards, pictures, siteName, log }):
 *   boards: the page's board model (boards.js);
 *   pictures: the page's camera verbs (pictures.js), for frameOf(name) and isMine(id);
 *   siteName(): the site shown; log(text, kind): the status bar, "bad" a refusal.
 * Answers { open(path), close(), refresh(), subject() }.
 */

const KEEP_EVERY = 0.05;        // a frame set at every 5 % of progress
const KEEP_APART_MS = 10000;    // and never two closer together than this
const POLL_MS = 2000;           // the printer's poll while the window is open on it
const REFRESH_MS = 5000;        // the document asked for again
const WHO = "working-space";
const W = 600, STRIP = 14, LINES = 70;

const MARKUP = `
<div class="panel-ui working-space">
    <div class="ws-head"><strong class="ws-title"></strong> <span class="ws-said muted"></span></div>
    <div class="ws-timeline"></div>
    <table class="ws-subjects"><tbody></tbody></table>
    <div class="ws-evidence"></div>
</div>`;

export function mountWorkingSpace(root, { base = "", boards, pictures, siteName, log = null } = {}) {
    root.innerHTML = MARKUP;
    const q = (sel) => root.querySelector(sel);
    const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
    const say = (text, kind = "") => { if (log) log(text, kind); };
    const state = { path: null, watch: null, doc: null, kept: { at: 0, state: null, step: null }, timer: null, unwatch: null, told: new Set(), keeping: false };

    async function api(path, opts = {}) {
        const r = await fetch(base + path, { headers: { "Content-Type": "application/json" }, ...opts });
        const body = await r.json().catch(() => ({}));
        if (!r.ok) throw new Error(typeof body.detail === "string" ? body.detail : r.statusText);
        return body;
    }
    const site = () => siteName();
    const siteUrl = () => `/sites/${encodeURIComponent(site())}`;
    const subject = () => (state.path ? `${site()}:${state.path}` : null);

    // --- keeping a frame set with a poll ------------------------------------------------
    function due(st, now) {
        if (!st || !st.poll || now - state.kept.at < KEEP_APART_MS) return false;
        const step = st.sd_progress == null ? null : Math.floor(st.sd_progress / KEEP_EVERY);
        return !state.kept.at || st.state !== state.kept.state || step !== state.kept.step;
    }
    async function keepSet(st) {
        const now = Date.now();
        if (state.keeping || !state.watch || !due(st, now)) return;
        state.keeping = true;
        state.kept = { at: now, state: st.state, step: st.sd_progress == null ? null : Math.floor(st.sd_progress / KEEP_EVERY) };
        const kept = [], refused = [];
        try {
            for (const cam of state.watch.cameras) {
                if (!cam.device_id || !pictures.isMine(cam.device_id)) {
                    if (!state.told.has(cam.name)) {
                        state.told.add(cam.name);
                        say(`${cam.name} looks at ${state.path}, and its device is ${cam.device_id ? "another browser's" : "not chosen"}: its frames are not kept here`, "bad");
                    }
                    continue;
                }
                try {
                    const blob = await pictures.frameOf(cam.name);
                    const params = new URLSearchParams({ name: cam.name, site: site(), camera: cam.name, poll: st.poll });
                    await api(`/photos/pictures?${params}`, { method: "POST", body: blob, headers: { "Content-Type": blob.type } });
                    kept.push(cam.name);
                } catch (e) { refused.push(`${cam.name}: ${e.message}`); }
            }
        } finally { state.keeping = false; }
        if (kept.length || refused.length) {
            say(`${state.path} ${st.state}: ${kept.length ? `a frame from ${kept.join(", ")} kept with poll ${st.poll}` : "no frame kept"}${refused.length ? ` -- ${refused.join("; ")}` : ""}`, refused.length && !kept.length ? "bad" : "");
            refresh();
        }
    }
    function onBoard(ev) {
        const d = ev.detail || {};
        if (!state.watch || d.port !== state.watch.port || d.what !== "status" || !d.status) return;
        keepSet(d.status).catch((e) => say(`frames not kept: ${e.message}`, "bad"));
    }
    window.addEventListener("apothecary:board", onBoard);

    // --- drawing ------------------------------------------------------------------------
    const time = (iso) => new Date(iso).getTime();
    const hhmm = (iso) => new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
    function value(p) {
        if (p.value === null || p.value === undefined) return `unread: ${esc(p.why)}`;
        if (typeof p.value === "object") return Object.entries(p.value).map(([k, v]) => `${esc(k)} ${esc(v)}`).join(" · ");
        if (p.unit === "fraction") return `${Math.round(p.value * 100)} %`;
        return `${esc(p.value)}${p.unit ? ` ${esc(p.unit)}` : ""}`;
    }
    function timeline(doc) {
        const s = subject();
        if (!s) return "";
        const t0 = time(doc.since), t1 = time(doc.at), span = Math.max(1, t1 - t0);
        const x = (iso) => Math.max(0, Math.min(W, ((time(iso) - t0) / span) * W));
        // The state, as a strip: each span between two changes in its own shade.
        const props = (doc.subjects.find((e) => e.subject === s) || { properties: [] }).properties;
        const now = props.find((p) => p.property === "state");
        const moves = doc.transitions.filter((t) => t.subject === s && t.property === "state");
        const bands = [];
        let from = doc.since, was = moves.length ? moves[0].from : now ? now.value : null;
        for (const m of moves) { bands.push([from, m.at, was, m.before]); from = m.at; was = m.to; }
        if (was !== null) bands.push([from, doc.at, was, now ? now.evidence : []]);
        const strip = bands.map(([a, b, v, ev]) => {
            const poll = (ev || []).find((r) => r.kind === "poll");
            return `<rect class="ws-state ws-${esc(v)}" x="${x(a)}" y="0" width="${Math.max(1, x(b) - x(a))}" height="${STRIP}"${poll ? ` data-poll="${esc(poll.id)}"` : ""}><title>${esc(v)} from ${hhmm(a)}</title></rect>`;
        }).join("");
        // The heaters, as lines over the same hour.
        const lines = [["hotend0", "ws-hotend"], ["bed", "ws-bed"]].map(([name, cls]) => {
            const pts = doc.series[`${s}#heater:${name}|temperature`] || [];
            if (!pts.length) return "";
            const most = 300, y = (v) => STRIP + 4 + LINES - (Math.max(0, Math.min(most, v)) / most) * LINES;
            const d = pts.map(([at, v], i) => `${i ? "L" : "M"}${x(at).toFixed(1)},${y(v).toFixed(1)}`).join(" ") + ` L${W},${y(pts[pts.length - 1][1]).toFixed(1)}`;
            const marks = pts.map(([at, v, poll]) => `<circle cx="${x(at).toFixed(1)}" cy="${y(v).toFixed(1)}" r="2.5" class="${cls}"${poll ? ` data-poll="${esc(poll)}"` : ""}><title>${esc(name)} ${esc(v)} °C at ${hhmm(at)}</title></circle>`).join("");
            return `<path d="${d}" class="${cls}" fill="none"/>${marks}`;
        }).join("");
        const svg = `<svg class="ws-chart" viewBox="0 0 ${W} ${STRIP + LINES + 8}" preserveAspectRatio="none" role="img" aria-label="${esc(state.path)}'s state and temperatures">${strip}${lines}</svg>`;
        // A row per camera that looks at it: the frames kept with its polls.
        const cams = (state.watch ? state.watch.cameras.map((c) => c.name) : []);
        for (const f of doc.frames) if (f.subjects.includes(s) && !cams.includes(f.camera)) cams.push(f.camera);
        const rows = cams.map((cam) => {
            const frames = doc.frames.filter((f) => f.camera === cam && f.subjects.includes(s));
            const thumbs = frames.map((f) => `<img class="ws-frame" loading="lazy" alt="${esc(cam)} at ${hhmm(f.at)}" title="${esc(cam)} at ${hhmm(f.at)}, poll ${esc(f.poll)}" style="left:${Math.max(4, Math.min(96, (x(f.at) / W) * 100)).toFixed(2)}%" src="${base}/photos/pictures/file?px=256&path=${encodeURIComponent(f.id)}" data-frame="${esc(f.id)}" data-poll="${esc(f.poll)}">`).join("");
            return `<div class="ws-camera-row" data-camera="${esc(cam)}"><span class="ws-camera-name">${esc(cam)}</span><div class="ws-frames">${thumbs || '<span class="muted">no frame kept yet</span>'}</div></div>`;
        }).join("");
        const size = doc.frame_sizes[s];
        const taken = size && size.bytes < 1e6 ? `${Math.ceil(size.bytes / 1e3)} kB` : size ? `${(size.bytes / 1e6).toFixed(1)} MB` : "";
        const budget = size ? `<div class="muted ws-budget">${size.frames} frame${size.frames === 1 ? "" : "s"} kept: ${taken} of ${(size.budget / 1e9).toFixed(1)} GB</div>` : "";
        return `${svg}<div class="ws-axis muted"><span>${hhmm(doc.since)}</span><span>${hhmm(doc.at)}</span></div>${rows}${budget}`;
    }
    function table(doc) {
        const s = subject();
        const shown = doc.subjects.filter((e) => !s || e.subject === s || e.subject.startsWith(`${s}#`) || e.subject.startsWith(`${s}.`));
        return shown.map((e) => `<tr class="ws-subject"><th colspan="4">${esc(e.subject)}</th></tr>` + e.properties.map((p) => {
            const poll = (p.evidence || []).find((r) => r.kind === "poll");
            const heard = p.current ? "heard" : `last known ${hhmm(p.at)}`;
            return `<tr class="ws-property${p.current ? "" : " ws-stale"}"${poll ? ` data-poll="${esc(poll.id)}"` : ""} title="${esc(p.origin.kind)} by ${esc(p.origin.by)}"><td>${esc(p.property)}</td><td>${value(p)}</td><td>${esc(p.origin.kind)}, ${esc(p.standing)}</td><td>${heard}</td></tr>`;
        }).join("")).join("") || `<tr><td class="muted">nothing is said of ${esc(s || site())} yet: a printer pinned here says it once it is polled</td></tr>`;
    }
    function render() {
        const doc = state.doc;
        q(".ws-title").textContent = state.path ? `${site()} › ${state.path}` : site();
        if (!doc) return;
        q(".ws-said").textContent = `${doc.observations} observation${doc.observations === 1 ? "" : "s"} in the hour${doc.unreadable ? `, ${doc.unreadable} line(s) unreadable` : ""}`;
        q(".ws-timeline").innerHTML = timeline(doc);
        q(".ws-subjects tbody").innerHTML = table(doc);
    }

    // --- evidence, opened from a mark or a row ---------------------------------------------
    async function openPoll(id) {
        const poll = await api(`/evidence/polls/${encodeURIComponent(id)}?space=${encodeURIComponent(site())}`);
        q(".ws-evidence").innerHTML = `<div class="ws-opened"><strong>poll ${esc(poll.id)}</strong> · ${esc(poll.port)} · ${esc(poll.state)} at ${hhmm(poll.polled_at)}<pre>${esc((poll.raw || []).join("\n"))}</pre></div>`;
    }
    function openFrame(path, poll) {
        q(".ws-evidence").innerHTML = `<div class="ws-opened"><strong>${esc(path)}</strong> · kept with <a href="#" data-poll="${esc(poll)}">poll ${esc(poll)}</a><img class="ws-frame-large" alt="${esc(path)}" src="${base}/photos/pictures/file?px=1024&path=${encodeURIComponent(path)}"></div>`;
    }
    root.addEventListener("click", (ev) => {
        const frame = ev.target.closest("[data-frame]");
        if (frame) { openFrame(frame.dataset.frame, frame.dataset.poll); return; }
        const poll = ev.target.closest("[data-poll]");
        if (poll && poll.dataset.poll) { ev.preventDefault(); openPoll(poll.dataset.poll).catch((e) => say(`poll ${poll.dataset.poll}: ${e.message}`, "bad")); }
    });

    // --- opening and refreshing ----------------------------------------------------------
    async function refresh() {
        try { state.doc = await api(`${siteUrl()}/evidence`); render(); }
        catch (e) { q(".ws-said").textContent = `not read: ${e.message}`; }
    }
    function stop() {
        clearInterval(state.timer); state.timer = null;
        if (state.unwatch) { state.unwatch(); state.unwatch = null; }
    }
    async function open(path = null) {
        stop();
        state.path = path; state.watch = null; state.told = new Set();
        state.kept = { at: 0, state: null, step: null };
        q(".ws-evidence").innerHTML = "";
        render();
        if (path) {
            try {
                state.watch = await api(`${siteUrl()}/evidence/printers/${encodeURIComponent(path)}`);
                if (state.watch.port) state.unwatch = boards.watch(state.watch.port, WHO, { kind: "printer", interval: POLL_MS });
                else say(`${path} has no board answering on a port: its timeline is what the log already holds`, "bad");
            } catch (e) { say(`${path}: ${e.message}`, "bad"); }
        }
        await refresh();
        state.timer = setInterval(refresh, REFRESH_MS);
        return state.watch;
    }

    return {
        open, refresh,
        close: stop,
        subject: () => state.path,
        destroy() { stop(); window.removeEventListener("apothecary:board", onBoard); },
    };
}
