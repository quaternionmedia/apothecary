/* Working space: a site as every kind of evidence has it (apothecary/evidence/,
 * GET /sites/{s}/evidence), and a printer's timeline in it.
 *
 * Its first line, under the title, always names the next step, with the button
 * that takes it: whichever door opened the window, it says what to do.
 *
 * Opened on the site (Panels › Site › Workspace, or ⊞ Windows › Working space) it
 * is a row per printer a board pinned here drives, each with what it is doing and
 * the button that opens its hour, then every subject the log has said of: each
 * property's value, how it is known and when. Opened on a printer (Camera ›
 * Workspace on its ring, or its row's button) it is that printer's hour: its
 * state as a strip and its heaters as lines, and a row for each camera that looks
 * at it, the frames kept with its polls. A camera row whose device is not this
 * browser's chooses one in place; a printer no camera looks at adds one above it.
 * Every mark, frame and row opens its evidence under the timeline: a frame, a
 * poll's lines.
 *
 * While it is open on a printer it watches the printer's board (boards.js, its
 * one poller) and keeps a frame set with its polls: a frame from each of the
 * printer's cameras whose device is this browser's, when the printer's state
 * changes, at every 5 % of its progress and when a camera is newly this
 * browser's, never closer together than ten seconds, each posted with the poll's
 * id (POST /photos/pictures?site=&camera=&poll=). Keep a set now keeps one with
 * the last poll.
 *
 * mountWorkingSpace(root, { base, boards, pictures, siteName, applySite, log }):
 *   boards: the page's board model (boards.js);
 *   pictures: the page's camera verbs (pictures.js): frameOf, isMine, permit,
 *     chooseDevice and the cameras this browser has (state.cameras);
 *   siteName(): the site shown; applySite(site): the world drawn again, a camera
 *     added; log(text, kind): the status bar, "bad" a refusal.
 * Answers { open(path), close(), shown(), refresh(), subject(), next() }. Closed,
 * it holds no printer and keeps nothing, and shown() opens it on the site again;
 * an open() overtaken by a later one, or by close(), stops where it is.
 */

const KEEP_EVERY = 0.05;        // a frame set at every 5 % of progress
const KEEP_APART_MS = 10000;    // and never two closer together than this
const POLL_MS = 2000;           // the printer's poll while the window is open on it
const REFRESH_MS = 5000;        // the document asked for again
const WHO = "working-space";
const W = 600, STRIP = 14, LINES = 70;

const MARKUP = `
<div class="panel-ui working-space">
    <div class="ws-head">
        <button type="button" class="ws-back" data-do="site" hidden></button>
        <strong class="ws-title"></strong> <span class="ws-said muted"></span>
    </div>
    <div class="ws-next" role="status"></div>
    <div class="ws-printers"></div>
    <div class="ws-timeline"></div>
    <div class="ws-evidence"></div>
    <table class="ws-subjects"><thead></thead><tbody></tbody></table>
</div>`;

// The first line's buttons, one template each, so the census counts each
// (apothecary/census.py reads controls from markup).
const LEAD_BUTTONS = {
    "add-camera": (label) => `<button type="button" class="ws-add-camera" data-do="add-camera">${label}</button>`,
    keep: () => `<button type="button" class="ws-keep" data-do="keep">Keep a set now</button>`,
};

export function mountWorkingSpace(root, { base = "", boards, pictures, siteName, applySite = null, log = null } = {}) {
    root.innerHTML = MARKUP;
    const q = (sel) => root.querySelector(sel);
    const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
    const say = (text, kind = "") => { if (log) log(text, kind); };
    const state = {
        path: null, watch: null, refused: null, printers: [], doc: null, last: null, next: "",
        kept: { at: 0, state: null, step: null, cameras: "" }, timer: null, unwatch: null, keeping: false,
        turn: 0, closed: false,
    };

    async function api(path, opts = {}) {
        const r = await fetch(base + path, { headers: { "Content-Type": "application/json" }, ...opts });
        const body = await r.json().catch(() => ({}));
        if (!r.ok) throw new Error(typeof body.detail === "string" ? body.detail : r.statusText);
        return body;
    }
    const site = () => siteName();
    const siteUrl = () => `/sites/${encodeURIComponent(site())}`;
    const printerUrl = (path) => `${siteUrl()}/evidence/printers/${encodeURIComponent(path)}`;
    const subject = () => (state.path ? `${site()}:${state.path}` : null);

    // --- this browser's cameras, as a camera row has them -------------------------------
    const mine = (cam) => !!(cam.device_id && pictures.isMine(cam.device_id));
    const ready = () => (state.watch ? state.watch.cameras.filter(mine) : []);
    const waiting = () => (state.watch ? state.watch.cameras.filter((c) => !mine(c)) : []);
    const labelOf = (id) => ((pictures.state.cameras || []).find((c) => c.id === id) || {}).label || "this browser's camera";

    // --- keeping a frame set with a poll ------------------------------------------------
    // Due when the state changed, at a new 5 % of progress, or when a camera is newly
    // this browser's, so it has a frame from the next poll on.
    const cameras = () => ready().map((c) => c.name).join(",");
    function due(st, now) {
        if (!st || !st.poll || !ready().length || now - state.kept.at < KEEP_APART_MS) return false;
        const step = st.sd_progress == null ? null : Math.floor(st.sd_progress / KEEP_EVERY);
        return !state.kept.at || st.state !== state.kept.state || step !== state.kept.step || cameras() !== state.kept.cameras;
    }
    async function keepSet(st, { now: asked = false } = {}) {
        const now = Date.now();
        if (state.keeping || !state.watch || !st || !st.poll || (!asked && !due(st, now))) return null;
        state.keeping = true;
        state.kept = { at: now, state: st.state, step: st.sd_progress == null ? null : Math.floor(st.sd_progress / KEEP_EVERY), cameras: cameras() };
        const kept = [], refused = [], turn = state.turn;
        try {
            for (const cam of ready()) {
                if (turn !== state.turn) break;  // closed, or opened on another, mid-set
                try {
                    const blob = await pictures.frameOf(cam.name);
                    const params = new URLSearchParams({ name: cam.name, site: site(), camera: cam.name, poll: st.poll });
                    await api(`/photos/pictures?${params}`, { method: "POST", body: blob, headers: { "Content-Type": blob.type } });
                    kept.push(cam.name);
                } catch (e) { refused.push(`${cam.name}: ${e.message}`); }
            }
        } finally { state.keeping = false; }
        if (turn !== state.turn) return { kept, refused };  // the window has moved on: not its line
        if (kept.length || refused.length) {
            const did = kept.length ? `a frame from ${kept.join(", ")} kept with the poll at ${hhmm(st.polled_at)}: click one to see it beside the poll's lines` : "no frame kept";
            say(`${state.path} ${st.state}: ${did}${refused.length ? ` -- ${refused.join("; ")}` : ""}`, refused.length && !kept.length ? "bad" : "");
            await refresh();
        }
        return { kept, refused };
    }
    function onBoard(ev) {
        const d = ev.detail || {};
        if (!state.watch || d.port !== state.watch.port || d.what !== "status" || !d.status) return;
        const first = !state.last;
        state.last = d.status;
        if (first) render();
        keepSet(d.status).catch((e) => say(`frames not kept: ${e.message}`, "bad"));
    }
    window.addEventListener("apothecary:board", onBoard);

    // --- words ---------------------------------------------------------------------------
    const time = (iso) => new Date(iso).getTime();
    const hhmm = (iso) => new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
    const degrees = (v) => (typeof v === "number" ? Math.round(v * 10) / 10 : esc(v));
    const size = (bytes) => (bytes < 1e6 ? `${Math.ceil(bytes / 1e3)} kB` : bytes < 1e9 ? `${(bytes / 1e6).toFixed(1)} MB` : `${(bytes / 1e9).toFixed(2)} GB`);
    // A subject as a person names it: garage:printer_1#heater:bed is printer_1's bed
    // heater; its id stays in the row's title.
    function named(id) {
        if (id.startsWith("usb:")) return `a board pinned nowhere (${id})`;
        const rest = id.slice(id.indexOf(":") + 1);
        const [where, part] = rest.split("#");
        const thing = where.includes(".") ? `${where.split(".")[0]} › ${where.split(".").pop().replace(/_/g, " ")}` : where;
        if (!part) return thing;
        const [kind, which = ""] = part.split(":");
        const what = kind === "heater" ? `${which.replace(/^hotend0$/, "hotend").replace(/^hotend(\d+)$/, "hotend $1")} heater`
            : kind === "endstop" ? `${which.replace(/_/g, " ")} endstop` : `${kind} ${which}`.trim();
        return `${thing} › ${what}`;
    }
    function value(p) {
        if (p.value === null || p.value === undefined) return `unread: ${esc(p.why)}`;
        if (p.value === true) return "yes";
        if (p.value === false) return "no";
        if (typeof p.value === "object") return Object.entries(p.value).map(([k, v]) => `${esc(k)} ${esc(v)}`).join(" · ");
        if (p.unit === "fraction") return `${Math.round(p.value * 100)} %`;
        if (p.unit === "°C") return `${degrees(p.value)} °C`;
        return `${esc(p.value)}${p.unit ? ` ${esc(p.unit)}` : ""}`;
    }
    function known(p) {
        const by = p.origin.kind === "measured" ? "measured by its poll" : esc(p.origin.kind);
        return p.standing === "disagreed" ? `${by}; <span class="ws-bad">its sources disagree</span>`
            : p.standing === "agreed" ? `${by}; its sources agree` : by;
    }
    const props = (doc, s) => (doc.subjects.find((e) => e.subject === s) || { properties: [] }).properties;
    const prop = (doc, s, name) => props(doc, s).find((p) => p.property === name);

    // --- the next step, said and offered ---------------------------------------------------
    function lead() {
        const path = state.path;
        if (!path) {
            if (!state.printers.length) return { text: `No printer is pinned in ${site()} yet: a printer's Device, on its ring, pins its board, and its polls are kept from then.` };
            return { text: "Choose a printer to see its hour: its state, its heaters, the frames its cameras keep, and what each value rests on." };
        }
        if (!state.watch) return { text: `${path} is not watched: ${state.refused || "its board is not known here"}.` };
        if (!state.watch.port) return { text: `${path}'s board is not answering: Device, on ${path}'s ring, pins it, and its polls are kept from then. What the log already holds is below.` };
        if (!state.watch.cameras.length) return { text: `No camera looks at ${path} yet: add one above it, and choose which of this browser's cameras it is.`, buttons: [["add-camera", `Add a camera above ${path}`]] };
        const need = waiting();
        if (need.length) {
            const one = need.length === 1;
            return { text: `${need.map((c) => c.name).join(", ")} ${one ? "has" : "have"} no device in this browser: choose one in ${one ? "its row" : "their rows"} below, and ${one ? "its" : "their"} frames are kept from here.`, buttons: [["add-camera", "Add another camera"]] };
        }
        if (!state.last) return { text: `Waiting for ${path}'s first poll: a frame set is kept with it.` };
        return {
            text: `Frames from ${ready().map((c) => c.name).join(", ")} are kept when ${path}'s state changes and at every 5 % of a print, while this window is open. Click a frame or a dot to see what it rests on.`,
            buttons: [["keep", "Keep a set now"], ["add-camera", "Add another camera"]],
        };
    }
    function drawLead() {
        const { text, buttons = [] } = lead();
        state.next = text;
        q(".ws-next").innerHTML = `<span>${esc(text)}</span>${buttons.map(([act, label]) => ` ${LEAD_BUTTONS[act](esc(label))}`).join("")}`;
    }

    // --- the site: a row per printer ----------------------------------------------------------
    function printers(doc) {
        if (state.path) return "";
        return state.printers.map((pr) => {
            const s = pr.subject;
            const st = doc ? prop(doc, s, "state") : null;
            const heat = doc ? [["hotend0", "hotend"], ["bed", "bed"]].map(([h, word]) => {
                const t = prop(doc, `${s}#heater:${h}`, "temperature");
                return t && t.value != null ? `${word} ${degrees(t.value)} °C` : "";
            }).filter(Boolean).join(" · ") : "";
            const heard = st ? (st.current ? "answering now" : `last heard ${hhmm(st.at)}`) : pr.port ? "not polled yet" : "its board is not answering";
            const cams = pr.cameras.length ? `${pr.cameras.length} camera${pr.cameras.length === 1 ? "" : "s"}` : "no camera";
            return `<div class="ws-printer" data-printer="${esc(pr.path)}"><strong>${esc(pr.path)}</strong> <span>${st ? esc(st.value) : ""}${heat ? ` · ${heat}` : ""}</span> <span class="muted">${heard} · ${cams}</span> <button type="button" class="ws-hour" data-do="hour" data-path="${esc(pr.path)}">${esc(pr.path)}'s hour ›</button></div>`;
        }).join("");
    }

    // --- a printer's hour ------------------------------------------------------------------------
    function timeline(doc) {
        const s = subject();
        if (!s) return "";
        const t0 = time(doc.since), t1 = time(doc.at), span = Math.max(1, t1 - t0);
        const x = (iso) => Math.max(0, Math.min(W, ((time(iso) - t0) / span) * W));
        // The state, as a strip: each span between two changes in its own shade.
        const now = prop(doc, s, "state");
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
        const legend = `<div class="ws-legend muted"><span><i class="ws-key ws-printing"></i>printing</span><span><i class="ws-key ws-idle"></i>idle</span><span><i class="ws-key ws-offline"></i>offline</span><span><i class="ws-key ws-line ws-hotend"></i>hotend</span><span><i class="ws-key ws-line ws-bed"></i>bed</span><span>a dot is a poll: click it for its lines</span></div>`;
        // A row per camera that looks at it: what it is in this browser, and the frames
        // kept with its polls.
        const watched = state.watch ? state.watch.cameras : [];
        const cams = watched.map((c) => c.name);
        for (const f of doc.frames) if (f.subjects.includes(s) && !cams.includes(f.camera)) cams.push(f.camera);
        const before = state.watch ? state.watch.frames.frames : 0;
        const rows = cams.map((cam) => {
            const frames = doc.frames.filter((f) => f.camera === cam && f.subjects.includes(s));
            const thumbs = frames.map((f) => `<img class="ws-frame" loading="lazy" alt="${esc(cam)} at ${hhmm(f.at)}" title="${esc(cam)} at ${hhmm(f.at)}: click to see it beside its poll" style="left:${Math.max(4, Math.min(96, (x(f.at) / W) * 100)).toFixed(2)}%" src="${base}/photos/pictures/file?px=256&path=${encodeURIComponent(f.id)}" data-frame="${esc(f.id)}" data-poll="${esc(f.poll)}">`).join("");
            const none = before ? "no frame kept this hour" : "no frame kept yet";
            return `<div class="ws-camera-row" data-camera="${esc(cam)}"><span class="ws-camera-name">${esc(cam)}${device(watched.find((c) => c.name === cam))}</span><div class="ws-frames">${thumbs || `<span class="muted">${none}</span>`}</div></div>`;
        }).join("");
        return `${svg}<div class="ws-axis muted"><span>${hhmm(doc.since)}</span><span>the last hour</span><span>${hhmm(doc.at)}</span></div>${legend}${rows}${budget()}`;
    }
    // What a camera is in this browser: its device, or the control that chooses one.
    function device(cam) {
        if (!cam) return `<span class="ws-device muted">no longer looks at it</span>`;
        if (mine(cam)) return `<span class="ws-device ws-ok">${esc(labelOf(cam.device_id))}</span>`;
        const here = pictures.state.cameras || [];
        const why = cam.device_id ? "another browser's camera" : "no device yet";
        if (!here.length) return `<span class="ws-device muted">${why}</span><button type="button" class="ws-permit" data-do="permit" data-camera="${esc(cam.name)}">Allow this browser's camera</button>`;
        const options = here.map((c) => `<option value="${esc(c.id)}">${esc(c.label)}</option>`).join("");
        return `<span class="ws-device muted">${why}</span><select class="ws-choose" data-camera="${esc(cam.name)}" aria-label="${esc(cam.name)}'s device"><option value="">choose its device…</option>${options}</select>`;
    }
    function budget() {
        if (!state.watch) return "";
        const f = state.watch.frames;
        const gb = f.budget / 1e9;
        return `<div class="ws-budget muted"><span>${f.frames ? `${f.frames} frame${f.frames === 1 ? "" : "s"} kept, ${size(f.bytes)}` : "no frame kept yet"} of a ${gb.toFixed(gb < 10 ? 1 : 0)} GB budget; past it, the oldest go first.</span> <label>Budget <input class="ws-gb" type="number" min="0.1" step="0.1" value="${gb}"> GB</label> <button type="button" class="ws-budget-set" data-do="budget">Set</button></div>`;
    }

    // --- every subject, and its values ------------------------------------------------------------
    function table(doc) {
        const s = subject();
        const shown = doc.subjects.filter((e) => !s || e.subject === s || e.subject.startsWith(`${s}#`) || e.subject.startsWith(`${s}.`));
        q(".ws-subjects thead").innerHTML = shown.length ? "<tr><th>what</th><th>value</th><th>how it is known</th><th>when</th></tr>" : "";
        return shown.map((e) => `<tr class="ws-subject" title="${esc(e.subject)}"><th colspan="4">${esc(named(e.subject))}</th></tr>` + e.properties.map((p) => {
            const poll = (p.evidence || []).find((r) => r.kind === "poll");
            const heard = p.current ? "now" : `last known ${hhmm(p.at)}`;
            return `<tr class="ws-property${p.current ? "" : " ws-stale"}"${poll ? ` data-poll="${esc(poll.id)}"` : ""} title="${esc(p.origin.kind)} by ${esc(p.origin.by.name)}${poll ? ": click for the poll's lines" : ""}"><td>${esc(p.property)}</td><td>${value(p)}</td><td>${known(p)}</td><td>${heard}</td></tr>`;
        }).join("")).join("") || `<tr><td class="muted">nothing is said of ${esc(s ? state.path : site())} yet: a printer pinned here says it once it is polled</td></tr>`;
    }
    function render() {
        const doc = state.doc;
        q(".ws-title").textContent = state.path ? `${site()} › ${state.path}` : site();
        const back = q(".ws-back");
        back.hidden = !state.path;
        back.textContent = `‹ ${site()}`;
        drawLead();
        q(".ws-printers").innerHTML = printers(doc);
        if (!doc) return;
        q(".ws-said").textContent = `${doc.observations} observation${doc.observations === 1 ? "" : "s"} in the last hour${doc.unreadable ? `, ${doc.unreadable} line(s) unreadable` : ""}`;
        // Not redrawn under a hand choosing a device or typing a budget.
        const busy = root.contains(document.activeElement) && document.activeElement.matches("select, input");
        if (!busy) q(".ws-timeline").innerHTML = timeline(doc);
        q(".ws-subjects tbody").innerHTML = table(doc);
    }

    // --- evidence, opened from a mark, a frame or a row -----------------------------------------
    function opened(html) {
        const pane = q(".ws-evidence");
        pane.innerHTML = `<div class="ws-opened"><button type="button" class="ws-close" data-do="close" aria-label="Close the evidence">×</button>${html}</div>`;
        pane.scrollIntoView({ block: "nearest" });
    }
    async function openPoll(id) {
        const poll = await api(`/evidence/polls/${encodeURIComponent(id)}?space=${encodeURIComponent(site())}`);
        opened(`<strong>The poll at ${hhmm(poll.polled_at)}</strong> · ${esc(poll.port)} · ${esc(poll.state)} · every line the printer sent<pre>${esc((poll.raw || []).join("\n"))}</pre>`);
        say(`the poll at ${hhmm(poll.polled_at)}: every line ${poll.port} sent, under the timeline; × closes it`);
    }
    function openFrame(path, poll) {
        const cam = (path.match(/--([^/]+?)\.[a-z]+$/) || [])[1] || "a camera";
        opened(`<strong>${esc(cam)}'s frame</strong> · kept with <a href="#" data-poll="${esc(poll)}">the poll it rests on</a><img class="ws-frame-large" alt="${esc(path)}" src="${base}/photos/pictures/file?px=1024&path=${encodeURIComponent(path)}">`);
        say(`${cam}'s frame, under the timeline: the poll it rests on shows every line the printer sent then`);
    }

    // --- what a person does here ------------------------------------------------------------------
    async function act(what, el) {
        if (what === "site") { await open(null); say(`the Working space of ${site()}: ${state.next}`); return; }
        if (what === "hour") { await open(el.dataset.path); say(`${state.path}'s hour in the Working space: ${state.next}`); return; }
        if (what === "close") { q(".ws-evidence").innerHTML = ""; return; }
        if (what === "keep") {
            const done = await keepSet(state.last, { now: true });
            if (!done) say(`no set kept: ${state.last ? "one is being kept" : `${state.path} has not been polled yet`}`, "bad");
            return;
        }
        if (what === "add-camera") {
            const answer = await api(`${siteUrl()}/cameras`, { method: "POST", body: JSON.stringify({ host: state.path }) });
            if (applySite && answer.site) await applySite(answer.site);
            await rewatch();
            const cam = answer.camera;
            say(cam.lands && cam.lands.host === state.path
                ? `added ${cam.name} above ${state.path}, looking straight down: choose its device in its row`
                : `added ${cam.name} outside ${state.path}: no room is left above it, so it is not one of ${state.path}'s cameras`);
            return;
        }
        if (what === "permit") {
            await pictures.permit("Allow this browser's camera");
            render();
            say(`this browser's cameras are allowed: choose ${el.dataset.camera}'s device in its row`);
            return;
        }
        if (what === "budget") {
            const gb = Number(q(".ws-gb").value);
            if (!(gb > 0)) { say("a budget is a number of gigabytes above nothing", "bad"); return; }
            state.watch = await api(`${printerUrl(state.path)}/budget`, { method: "PUT", body: JSON.stringify({ gb }) });
            document.activeElement.blur();
            render();
            say(`${state.path}'s frames now live under ${gb} GB: past it, the oldest are forgotten as the next are kept`);
        }
    }
    root.addEventListener("click", (ev) => {
        const button = ev.target.closest("[data-do]");
        if (button) { ev.preventDefault(); act(button.dataset.do, button).catch((e) => say(`${button.textContent.trim() || button.dataset.do}: ${e.message}`, "bad")); return; }
        const frame = ev.target.closest("[data-frame]");
        if (frame) { openFrame(frame.dataset.frame, frame.dataset.poll); return; }
        const poll = ev.target.closest("[data-poll]");
        if (poll && poll.dataset.poll) { ev.preventDefault(); openPoll(poll.dataset.poll).catch((e) => say(`poll ${poll.dataset.poll}: ${e.message}`, "bad")); }
    });
    root.addEventListener("change", (ev) => {
        const choose = ev.target.closest(".ws-choose");
        if (!choose || !choose.value) return;
        const name = choose.dataset.camera, id = choose.value;
        (async () => {
            await pictures.chooseDevice(name, id);
            choose.blur();
            await rewatch();
            say(`${name} is ${labelOf(id)}: ${state.next}`);
        })().catch((e) => say(`${name}'s device: ${e.message}`, "bad"));
    });

    // --- opening and refreshing ----------------------------------------------------------
    async function refresh() {
        try {
            if (!state.path) state.printers = (await api(`${siteUrl()}/evidence/printers`)).printers;
            state.doc = await api(`${siteUrl()}/evidence`);
            // What the printer's kept frames take, as the document has it now.
            const taken = state.watch && state.doc.frame_sizes[subject()];
            if (taken) state.watch.frames = { frames: taken.frames, bytes: taken.bytes, budget: taken.budget };
            render();
        } catch (e) { q(".ws-said").textContent = `not read: ${e.message}`; }
    }
    // What the printer is watched with, asked again: a camera added, a device chosen.
    async function rewatch() {
        const turn = state.turn;
        const watch = await api(printerUrl(state.path));
        if (turn !== state.turn) return;
        state.watch = watch;
        await refresh();
    }
    // Stopped, it holds no printer: a poll another window asks for keeps nothing here.
    function stop() {
        state.turn += 1;
        clearInterval(state.timer); state.timer = null;
        if (state.unwatch) { state.unwatch(); state.unwatch = null; }
        state.watch = null;
    }
    async function open(path = null) {
        stop();
        const turn = state.turn;
        state.closed = false;
        state.path = path; state.last = null; state.refused = null;
        state.kept = { at: 0, state: null, step: null, cameras: "" };
        q(".ws-evidence").innerHTML = "";
        q(".ws-timeline").innerHTML = "";
        render();
        if (path) {
            try {
                const watch = await api(printerUrl(path));
                if (turn !== state.turn) return null;
                state.watch = watch;
                if (watch.port) state.unwatch = boards.watch(watch.port, WHO, { kind: "printer", interval: POLL_MS });
            } catch (e) { if (turn === state.turn) state.refused = e.message; }
        }
        await refresh();
        if (turn !== state.turn) return null;
        state.timer = setInterval(refresh, REFRESH_MS);
        return state.watch;
    }
    function close() { stop(); state.closed = true; }

    return {
        open, close, refresh,
        shown: () => (state.closed ? open(null) : refresh()),
        subject: () => state.path,
        next: () => state.next,
        destroy() { stop(); window.removeEventListener("apothecary:board", onBoard); },
    };
}
