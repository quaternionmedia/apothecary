/* The machine: one printer, close up, wherever it is mounted.
 *
 * What the monitor page is made of -- the header's link verbs and the
 * control latch, the status cards, the temperature chart, the comms log
 * with its query box, the latched control pad, the bed reading, the
 * print from here -- as one module the monitor page mounts as its whole
 * body and the world mounts in a popup tethered to the printer. The same
 * markup, the same ids, the same chain, latch and confirms on both hosts;
 * the census reads this file as part of the pages that import it.
 *
 * mountMachine(root, { base, port, host, logRoot }) renders into `root`
 * and returns the handle the ring drives (carry, pairs, device) and the
 * tests read (state, ctl, level, print). `host` is "page" (the monitor:
 * a port picker, the control pad floating over the log, the URL kept in
 * step) or "popup" (the world: one port, everything inline, the log in
 * `logRoot` when one is given). destroy() stops the polling and frees
 * what the module put on the window.
 */

const MAX_HISTORY = 300;

const HEAD = `
<div class="machine-head">
    <span class="dot" id="dot"></span>
    <select id="port" aria-label="Printer port"><option value="">— pick a port —</option></select>
    <span id="ident" class="kv">—</span>
    <span class="grow"></span>
    <label class="auto"><input type="checkbox" id="auto" checked> auto-poll
        <select id="interval"><option value="1000">1 s</option><option value="2000" selected>2 s</option><option value="5000">5 s</option><option value="10000">10 s</option></select>
    </label>
    <button type="button" id="poll" title="One poll now (M105/M114/M27/M119)">⟳ Poll</button>
    <button type="button" id="reconnect" title="Release and reopen the serial link (no reset); the remedy for a wedged port">⇄ Reconnect</button>
    <button type="button" id="identify" title="Ask M115 again (no reset)">M115</button>
    <button type="button" id="reset" class="danger" title="Reboot the board with a DTR pulse — never mid-print">⏻ Reset board</button>
    <button type="button" id="release" title="Drop the held link so another program can open the port">Release</button>
    <label class="ctl" id="ctl-label" title="Arm the control latch: heaters, fan, homing, bounded jogs and SD pause/resume/abort become available in an overlay for 5 minutes of activity. Disarmed, nothing on this page can heat or move the machine.">
        <input type="checkbox" id="ctl"> ⚙ Control <span class="ttl" id="ctl-ttl"></span>
    </label>
    <button type="button" id="estop" title="M112: emergency stop. Always available, latch or not. Halts the board until it is reset.">⏹ E-STOP</button>
</div>`;

const CARDS = `
<div class="cards" id="cards">
    <div class="card"><div class="k">State</div><div class="v" id="c-state">—</div><div class="s" id="c-state-s"></div></div>
    <div class="card"><div class="k">Hotend</div><div class="v" id="c-hot">—</div><div class="s" id="c-hot-s"></div><div class="bar hotend"><i id="b-hot" style="width:0"></i></div></div>
    <div class="card"><div class="k">Bed</div><div class="v" id="c-bed">—</div><div class="s" id="c-bed-s"></div><div class="bar bed"><i id="b-bed" style="width:0"></i></div></div>
    <div class="card"><div class="k">Position</div><div class="v" id="c-pos">—</div><div class="s" id="c-pos-s"></div></div>
    <div class="card"><div class="k">SD print</div><div class="v" id="c-sd">—</div><div class="s" id="c-sd-s"></div><div class="bar sd"><i id="b-sd" style="width:0"></i></div></div>
    <div class="card"><div class="k">Endstops · filament</div><div class="chips" id="c-stops"><span class="empty">—</span></div></div>
    <div class="card wide"><div class="k">Board · link</div><div class="kv" id="c-board">—</div></div>
    <div class="card wide" id="level-card">
        <div class="k">Bed level <span class="s" id="level-note"></span></div>
        <div class="row">
            <button type="button" id="level-probe" class="warm" title="G28, G29, then read the mesh, the probe offset and the temperatures; saved as a record. Moves the machine: control must be armed. ⌗ Control › Level › Probe">▤ Probe bed</button>
            <button type="button" id="level-read" title="Read the stored mesh (M420 V), the probe offset and the temperatures without moving; saved as a record">Read mesh</button>
            <span class="job" id="level-job"></span>
            <span class="grow"></span>
            <button type="button" data-corner="FL" title="Move the nozzle to the front-left corner at paper height, for a tramming check">◣ FL</button>
            <button type="button" data-corner="FR" title="Front right, paper height">◢ FR</button>
            <button type="button" data-corner="BL" title="Back left, paper height">◤ BL</button>
            <button type="button" data-corner="BR" title="Back right, paper height">◥ BR</button>
        </div>
        <div id="mesh"></div>
        <div class="stats" id="level-stats"><span class="empty">no reading yet — Read mesh, or arm control and Probe bed</span></div>
        <div id="level-history"></div>
    </div>
    <div class="card wide" id="print-card">
        <div class="k">Print from here <span class="s" id="print-note" style="text-transform: none; letter-spacing: 0;">· no SD card needed: the file streams over the link, one line per ok</span></div>
        <div class="row">
            <input type="file" id="print-file" accept=".gcode,.gco,.g,.txt,text/plain" title="A sliced G-code file to keep on the host. It is checked (no EEPROM writes, no temperatures over the caps) and listed here; nothing is sent until Print">
            <select id="print-pick" title="The files kept on the host, newest first"><option value="">— no files kept —</option></select>
            <button type="button" id="print-delete" title="Forget the chosen file">✕</button>
            <span class="grow"></span>
            <button type="button" id="print-start" class="warm" title="Stream the chosen file to the printer. Heats and moves: control must be armed. ⌗ Control › Print › Send file">▶ Print</button>
            <button type="button" id="print-pause" title="Stop feeding lines; the printer finishes what it has queued">⏸ Pause</button>
            <button type="button" id="print-resume" title="Feed lines again (control must be armed)">▶ Resume</button>
            <button type="button" id="print-cancel" title="Stop feeding, then heaters off, fan off, motors free">■ Cancel</button>
        </div>
        <div class="row"><span id="print-progress" class="empty">nothing printing from here</span><span class="grow"></span><span class="job" id="print-job"></span></div>
        <div class="bar print"><i id="b-print" style="width:0"></i></div>
        <div id="print-history"></div>
    </div>
    <div class="card wide" id="view-card" hidden>
        <div class="k">Board in its printer <span class="s" id="view-note" style="text-transform: none; letter-spacing: 0;"></span></div>
        <div id="board-view" style="height: 240px; border-radius: 4px; overflow: hidden;"></div>
    </div>
</div>
<div class="chart">
    <div class="head"><span class="title">Temperature</span><span id="chart-span">no polls yet</span>
        <span class="legend"><span class="hotend">hotend</span><span class="bed">bed</span><span style="color:var(--ink-3)">dashed = target</span></span></div>
    <div class="wrap"><svg id="chart" viewBox="0 0 600 150" preserveAspectRatio="none"></svg><div class="tip" id="tip"></div></div>
</div>`;

const LOG = `
<div class="log-head">
    <span class="title">Comms log</span>
    <form id="qform" autocomplete="off">
        <input id="q" list="qcodes" aria-label="Report-only G-code to send" placeholder="report code — M503, M119, M20, M420 V …" spellcheck="false">
        <datalist id="qcodes"></datalist>
        <button type="submit">send</button>
    </form>
    <label><input type="checkbox" id="show-polls"> poll traffic</label>
    <label><input type="checkbox" id="follow" checked> follow</label>
    <button type="button" id="clear">clear</button>
    <button type="button" id="download" title="Download the comms log as text" aria-label="Download the comms log">⤓</button>
</div>
<pre id="log"><span class="empty">pick a port to see its comms</span></pre>`;

const CONTROL = `
<div id="control" hidden>
    <div class="head">🔓 Control armed <span class="ttl" id="ctl-ttl2"></span><span class="grow"></span>
        <span class="sent" id="ctl-sent"></span>
        <button type="button" id="ctl-disarm">🔒 Disarm</button>
    </div>
    <div class="body">
        <div class="grp">
            <div class="k">Heaters</div>
            <div class="row">hotend <input type="number" id="h-hot" min="0" max="300" step="5" value="200"> °C
                <button type="button" class="warm" data-cmd="M104 S{h-hot}">Set</button>
                <button type="button" data-cmd="M104 S0">Off</button></div>
            <div class="row">bed <input type="number" id="h-bed" min="0" max="130" step="5" value="60"> °C
                <button type="button" class="warm" data-cmd="M140 S{h-bed}">Set</button>
                <button type="button" data-cmd="M140 S0">Off</button></div>
            <div class="row">fan <input type="range" id="h-fan" min="0" max="255" step="5" value="255"> <span id="h-fan-v">255</span>
                <button type="button" data-cmd="M106 S{h-fan}">Set</button>
                <button type="button" data-cmd="M107">Off</button></div>
        </div>
        <div class="grp">
            <div class="k">Motion</div>
            <div class="row" style="align-items:flex-start">
                <div class="jog">
                    <span></span><button type="button" data-jog="Y+" title="Y+">▲</button><span></span>
                    <button type="button" data-jog="X-" title="X−">◀</button><button type="button" data-cmd="G28" title="Home all">⌂</button><button type="button" data-jog="X+" title="X+">▶</button>
                    <span></span><button type="button" data-jog="Y-" title="Y−">▼</button><span></span>
                </div>
                <div class="jogz"><button type="button" data-jog="Z+" title="Z+">Z▲</button><button type="button" data-jog="Z-" title="Z−">Z▼</button></div>
            </div>
            <div class="row steps">step <button type="button" data-step="0.1">0.1</button><button type="button" data-step="1">1</button><button type="button" data-step="10" class="on">10</button><button type="button" data-step="50">50</button> mm
                · F <input type="number" id="h-feed" min="60" max="12000" step="100" value="3000"></div>
            <div class="row"><button type="button" data-cmd="G28 X Y">Home XY</button><button type="button" data-cmd="G28 Z">Home Z</button><button type="button" data-cmd="M84">Motors off</button><button type="button" data-cmd="M410">Quickstop</button></div>
        </div>
        <div class="grp">
            <div class="k">SD print</div>
            <div class="row"><button type="button" data-cmd="M24">▶ Start / resume</button><button type="button" data-cmd="M25">⏸ Pause</button><button type="button" data-cmd="M524" data-confirm="Abort the SD print?">⏏ Abort</button></div>
        </div>
        <div class="grp">
            <div class="k">Leveling</div>
            <div class="row"><button type="button" data-cmd="M420 S1">Mesh on</button><button type="button" data-cmd="M420 S0">Mesh off</button><button type="button" data-cmd="M108">Break wait</button></div>
        </div>
    </div>
</div>`;

// Verb -> the one G-code line its button sends. Values are read at the
// moment of choosing, from the same boxes the buttons read.
const LINES = {
    "control:hotend-on": (m) => m.fillTemplate("M104 S{h-hot}"),
    "control:hotend-off": () => "M104 S0",
    "control:bed-on": (m) => m.fillTemplate("M140 S{h-bed}"),
    "control:bed-off": () => "M140 S0",
    "control:fan-on": (m) => m.fillTemplate("M106 S{h-fan}"),
    "control:fan-off": () => "M107",
    "control:home": () => "G28",
    "control:home-xy": () => "G28 X Y",
    "control:home-z": () => "G28 Z",
    "control:sd-resume": () => "M24",
    "control:sd-pause": () => "M25",
    "control:sd-abort": () => "M524",
    "control:motors-off": () => "M84",
    "control:break-wait": () => "M108",
    "control:mesh-on": () => "M420 S1",
    "control:mesh-off": () => "M420 S0",
    "control:quickstop": () => "M410",
};
const CONFIRM = { "control:sd-abort": "Abort the SD print?" };
// The same three verbs, carried to the print from here when one is running.
const HOST_VERBS = { "control:sd-resume": "resume", "control:sd-pause": "pause", "control:sd-abort": "cancel" };
// The buttons the machine has, each by the verb it is.
const BY_CMD = {
    "M104 S{h-hot}": "control:hotend-on", "M104 S0": "control:hotend-off",
    "M140 S{h-bed}": "control:bed-on", "M140 S0": "control:bed-off",
    "M106 S{h-fan}": "control:fan-on", "M107": "control:fan-off",
    "G28": "control:home", "G28 X Y": "control:home-xy", "G28 Z": "control:home-z",
    "M24": "control:sd-resume", "M25": "control:sd-pause", "M524": "control:sd-abort", "M84": "control:motors-off",
    "M410": "control:quickstop", "M108": "control:break-wait", "M420 S1": "control:mesh-on", "M420 S0": "control:mesh-off",
};

export function mountMachine(root, { base = "", port = "", host = "page", logRoot = null } = {}) {
    const BASE = base;
    root.classList.add("machine", `host-${host}`);
    root.innerHTML = HEAD + `<div class="machine-main"><section class="left">${CARDS}</section>` + (logRoot ? "" : `<section class="right">${LOG}</section>`) + `</div>` + CONTROL;
    if (logRoot) { logRoot.classList.add("machine-log", "right"); logRoot.innerHTML = LOG; }
    const $ = (id) => root.querySelector(`#${CSS.escape(id)}`) || (logRoot ? logRoot.querySelector(`#${CSS.escape(id)}`) : null);
    const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
    if (host === "popup") $("port").hidden = true;  // the popup is one printer's; the world chose it
    const state = { port, info: null, status: null, history: [], logNext: 0, entries: [], timer: null, gen: 0, inFlight: false, codesLoaded: false };
    const onWindow = [];  // [event, handler] pairs the module put on the window, taken off by destroy()
    const emit = (name, detail) => window.dispatchEvent(new CustomEvent(name, { detail }));

    // --- api ---------------------------------------------------------------------------
    async function api(path, opts = {}) {
        const r = await fetch(BASE + path, { headers: { "Content-Type": "application/json" }, ...opts });
        const body = await r.json().catch(() => ({}));
        if (!r.ok) throw new Error(typeof body.detail === "string" ? body.detail : (body.detail ? JSON.stringify(body.detail) : r.statusText));
        return body;
    }
    const post = (path, body) => api(path, { method: "POST", body: JSON.stringify(body) });

    async function loadPorts() {
        try {
            const data = await api("/firmware/devices");
            const opts = data.devices.map((v) => {
                const d = v.device, tag = d.printer ? (d.printer.firmware_name || "").replace(/\s*\(.*$/, "") : (d.chip || d.board_name || "unidentified");
                return `<option value="${esc(d.port)}">${esc(d.port)} · ${esc(tag)}</option>`;
            });
            $("port").innerHTML = '<option value="">— pick a port —</option>' + opts.join("");
            if (state.port) $("port").value = state.port;
        } catch (e) { logLine("sys", "device list: " + e.message); }
    }

    async function loadCodes() {
        if (state.codesLoaded) return;
        try {
            const codes = await api("/firmware/printers/queries");
            $("qcodes").innerHTML = codes.map((q) => `<option value="${esc(q.command)}">${esc(q.reports)}</option>`).join("");
            state.codesLoaded = true;
        } catch (e) { /* suggestions are optional */ }
    }

    // --- status ------------------------------------------------------------------------
    const heater = (h) => h ? `${h.actual.toFixed(1)}° <span class="s">/ ${h.target.toFixed(0)}°</span>` : "—";
    function renderStatus() {
        const st = state.status, info = state.info;
        const d = info && info.device ? info.device.device : null;
        const pr = d && d.printer;
        $("ident").innerHTML = pr ? `<b>${esc(pr.firmware_name)}</b>${pr.machine_type ? " · " + esc(pr.machine_type) : ""}` : (d ? `${esc(d.port)} — not identified as a printer` : (state.port ? "not detected" : "—"));
        if (!st) { $("c-state").textContent = "—"; $("c-state-s").textContent = ""; return; }
        const offline = st.state === "offline";
        $("dot").className = "dot " + (offline ? "bad" : "on");
        $("c-state").innerHTML = offline ? '<span class="bad">offline</span>' : (st.state === "printing" ? '<span class="ok">printing</span>' : (st.heating ? '<span class="warn">heating</span>' : "idle"));
        $("c-state-s").textContent = st.job ? (st.job.kind === "print" ? `print from here: ${st.job.stage} ${(st.job.progress * 100).toFixed(0)}%` : `${st.job.kind}: ${st.job.stage}`) : (offline ? (st.raw[0] || "") : `polled ${new Date(st.polled_at).toLocaleTimeString()}`);
        const hot = st.hotends[0];
        $("c-hot").innerHTML = heater(hot); $("c-hot-s").textContent = hot && hot.power != null ? `power ${hot.power}/127` : "";
        $("b-hot").style.width = hot && hot.target > 0 ? Math.min(100, hot.actual / hot.target * 100).toFixed(0) + "%" : "0";
        $("c-bed").innerHTML = heater(st.bed); $("c-bed-s").textContent = st.bed && st.bed.power != null ? `power ${st.bed.power}/127` : "";
        $("b-bed").style.width = st.bed && st.bed.target > 0 ? Math.min(100, st.bed.actual / st.bed.target * 100).toFixed(0) + "%" : "0";
        const p = st.position;
        $("c-pos").textContent = p ? `X${p.x.toFixed(1)} Y${p.y.toFixed(1)} Z${p.z.toFixed(2)}` : "—";
        $("c-pos-s").textContent = p ? `E ${p.e.toFixed(1)}` : "";
        if (st.sd_printing) {
            const pct = st.sd_progress != null ? (st.sd_progress * 100).toFixed(1) + "%" : "…";
            $("c-sd").textContent = pct; $("b-sd").style.width = st.sd_progress != null ? (st.sd_progress * 100).toFixed(1) + "%" : "0";
            $("c-sd-s").textContent = st.print_time_s != null ? `elapsed ${fmtDur(st.print_time_s)}` : "";
        } else { $("c-sd").textContent = "not printing"; $("c-sd-s").textContent = ""; $("b-sd").style.width = "0"; }
        const chips = Object.entries(st.endstops).map(([k, v]) => `<span class="chip ${v === "TRIGGERED" ? "hit" : ""}">${esc(k)} ${v === "TRIGGERED" ? "▮" : "▯"}</span>`);
        if (st.filament_present != null) chips.push(`<span class="chip ${st.filament_present ? "hit" : "bad"}">filament ${st.filament_present ? "present" : "OUT"}</span>`);
        $("c-stops").innerHTML = chips.join("") || '<span class="empty">—</span>';
        renderBoard();
    }
    function fmtDur(s) { const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60); return h ? `${h}h ${m}m` : `${m}m ${s % 60}s`; }

    function renderBoard() {
        const info = state.info; if (!info) { $("c-board").textContent = "—"; return; }
        const d = info.device ? info.device.device : null, pr = d && d.printer, link = info.link;
        const rows = [];
        if (d) rows.push(`<b>${esc(d.port)}</b> vid:pid ${esc(d.vid || "?")}:${esc(d.pid || "?")}${d.serial_number ? " · S/N " + esc(d.serial_number) : ""}`);
        if (pr) {
            rows.push(`firmware <b>${esc(pr.firmware_name)}</b>${pr.machine_type ? " · machine " + esc(pr.machine_type) : ""} · protocol ${esc(pr.protocol_version || "?")} · extruders ${pr.extruder_count}`);
            if (pr.uuid) rows.push(`uuid ${esc(pr.uuid)}`);
            const caps = Object.entries(pr.capabilities || {}).filter(([, v]) => v).map(([k]) => k);
            if (caps.length) rows.push(`caps ${esc(caps.join(", "))}`);
            if (pr.boot_lines && pr.boot_lines.length) rows.push(`boot ${esc(pr.boot_lines.slice(0, 3).join(" | "))}`);
        }
        rows.push(link
            ? `link <b class="ok">held</b> @ ${link.baud} baud via ${esc(link.engine)} since ${new Date(link.opened_at).toLocaleTimeString()} · engine ${esc(info.engine)}`
            : `link <b>not held</b> · engine ${esc(info.engine)} — the next poll opens it`);
        if (info.active_task) rows.push(`<span class="warn">task ${esc(info.active_task.title)} holds the toolchain — polls wait</span>`);
        $("c-board").innerHTML = rows.join("<br>");
    }

    // --- chart: temperatures over the last N polls, one °C axis ------------------------
    function renderChart() {
        const svg = $("chart"), H = state.history;
        $("chart-span").textContent = `last ${H.length} poll${H.length === 1 ? "" : "s"}`;
        if (H.length < 2) { svg.innerHTML = ""; return; }
        const W = 600, HT = 150, padL = 34, padR = 44, padT = 8, padB = 18;
        const vals = H.flatMap((h) => [h.hot, h.hotT, h.bed, h.bedT]).filter((v) => v != null);
        let lo = Math.min(...vals), hi = Math.max(...vals);
        if (hi - lo < 10) { hi = lo + 10; }
        lo = Math.floor(lo / 5) * 5; hi = Math.ceil(hi / 5) * 5;
        const x = (i) => padL + (i / (H.length - 1)) * (W - padL - padR);
        const y = (v) => padT + (1 - (v - lo) / (hi - lo)) * (HT - padT - padB);
        const path = (key) => H.map((h, i) => h[key] == null ? null : `${i && H[i - 1][key] != null ? "L" : "M"}${x(i).toFixed(1)},${y(h[key]).toFixed(1)}`).filter(Boolean).join(" ");
        const ticks = [lo, (lo + hi) / 2, hi];
        const grid = ticks.map((t) => `<line x1="${padL}" x2="${W - padR}" y1="${y(t).toFixed(1)}" y2="${y(t).toFixed(1)}" stroke="#2a302a" stroke-width="1"/><text x="${padL - 6}" y="${(y(t) + 3).toFixed(1)}" font-size="9" fill="#66746a" text-anchor="end">${t.toFixed(0)}°</text>`).join("");
        const last = H[H.length - 1];
        const endLabel = (v, cls) => v == null ? "" : `<text x="${W - padR + 6}" y="${(y(v) + 3).toFixed(1)}" font-size="9" fill="${cls === "hotend" ? "#e8b04a" : "#6fb3e8"}">${v.toFixed(0)}°</text>`;
        svg.innerHTML = grid
            + `<path d="${path("hotT")}" fill="none" stroke="#e8b04a" stroke-width="1" stroke-dasharray="3 3" opacity="0.7"/>`
            + `<path d="${path("bedT")}" fill="none" stroke="#6fb3e8" stroke-width="1" stroke-dasharray="3 3" opacity="0.7"/>`
            + `<path d="${path("hot")}" fill="none" stroke="#e8b04a" stroke-width="2" stroke-linejoin="round"/>`
            + `<path d="${path("bed")}" fill="none" stroke="#6fb3e8" stroke-width="2" stroke-linejoin="round"/>`
            + endLabel(last.hot, "hotend") + endLabel(last.bed, "bed")
            + `<line id="xh" x1="0" x2="0" y1="${padT}" y2="${HT - padB}" stroke="#66746a" stroke-width="1" style="display:none"/>`;
        svg.onmousemove = (ev) => {
            const rect = svg.getBoundingClientRect();
            const fx = (ev.clientX - rect.left) / rect.width * W;
            const i = Math.max(0, Math.min(H.length - 1, Math.round((fx - padL) / (W - padL - padR) * (H.length - 1))));
            const h = H[i], xh = $("xh");
            xh.setAttribute("x1", x(i)); xh.setAttribute("x2", x(i)); xh.style.display = "";
            const tip = $("tip");
            tip.style.display = "block";
            tip.innerHTML = `${new Date(h.t).toLocaleTimeString()}<br>hotend ${h.hot != null ? h.hot.toFixed(1) : "—"}° / ${h.hotT != null ? h.hotT.toFixed(0) : "—"}°<br>bed ${h.bed != null ? h.bed.toFixed(1) : "—"}° / ${h.bedT != null ? h.bedT.toFixed(0) : "—"}°`;
            const px = (x(i) / W) * rect.width;
            tip.style.left = Math.min(rect.width - 150, px + 10) + "px"; tip.style.top = "8px";
        };
        svg.onmouseleave = () => { $("tip").style.display = "none"; const xh = $("xh"); if (xh) xh.style.display = "none"; };
    }

    // --- log ---------------------------------------------------------------------------
    // Routine polls are tagged origin "poll" on the server; a person's
    // queries and M115s are not, so hiding poll traffic keeps them.
    function isPollTraffic(e, ctx) {
        if (e.kind === "tx") { ctx.inPoll = e.origin === "poll"; return ctx.inPoll; }
        if (e.kind === "rx") return e.origin === "poll";
        return false;
    }
    function renderLog() {
        const showPolls = $("show-polls").checked, log = $("log");
        const atBottom = log.scrollHeight - log.scrollTop - log.clientHeight < 40;
        const ctx = { inPoll: false };
        const rows = [];
        for (const e of state.entries) {
            const poll = isPollTraffic(e, ctx);
            if (poll && !showPolls) continue;
            const d = new Date(e.t);
            const t = isNaN(d) ? e.t.slice(11, 23) : d.toLocaleTimeString([], { hour12: false }) + "." + String(d.getMilliseconds()).padStart(3, "0");
            const cls = e.kind + (e.origin === "control" || e.origin === "print" ? " control" : "") + (/^\s*(ok\s+)?T:\s*-?\d/.test(e.text) ? " temp" : "") + (/^(Error:|!!)/.test(e.text) ? " err" : "");
            rows.push(`<span class="t">${t}</span> <span class="${cls}">${e.kind === "tx" ? "&gt; " : ""}${esc(e.text)}</span>`);
        }
        log.innerHTML = rows.length ? rows.join("\n") : '<span class="empty">nothing logged yet — poll or send a query</span>';
        if (atBottom && $("follow").checked) log.scrollTop = log.scrollHeight;
    }
    function logLine(kind, text) {
        state.entries.push({ i: -1, t: new Date().toISOString(), kind, text });
        renderLog();
    }
    // One fetch at a time, and rows below the watermark are dropped, so the
    // scheduled poll and a button's follow-up pull can never double up.
    let logChain = Promise.resolve();
    function pullLog() {
        const port = state.port, gen = state.gen;
        if (!port) return Promise.resolve();
        logChain = logChain.then(async () => {
            if (gen !== state.gen) return;
            const data = await api(`/firmware/printers/log?port=${encodeURIComponent(port)}&since=${state.logNext}`);
            if (gen !== state.gen) return;
            const fresh = data.entries.filter((e) => e.i >= state.logNext);
            if (fresh.length) {
                state.entries.push(...fresh);
                if (state.entries.length > 5000) state.entries.splice(0, state.entries.length - 5000);
                renderLog();
            }
            state.logNext = Math.max(state.logNext, data.next);
        }).catch(() => {});
        return logChain;
    }

    // --- polling: self-scheduled, never overlapping ------------------------------------
    function pushHistory(st) {
        if (st.state === "offline") return;
        const hot = st.hotends[0];
        state.history.push({ t: st.polled_at, hot: hot ? hot.actual : null, hotT: hot ? hot.target : null, bed: st.bed ? st.bed.actual : null, bedT: st.bed ? st.bed.target : null });
        if (state.history.length > MAX_HISTORY) state.history.shift();
    }
    async function pollOnce() {
        const port = state.port, gen = state.gen;
        if (!port || state.inFlight === gen) return;
        state.inFlight = gen;  // per generation: a new port's first poll is never skipped
        try {
            const st = await api(`/firmware/printers/status?port=${encodeURIComponent(port)}`);
            if (gen !== state.gen) return;  // the user switched ports meanwhile
            state.status = st; pushHistory(st); renderStatus(); renderChart();
            if (st.position) emit("apothecary:position", { position: st.position, source: "poll", port });
            emit("apothecary:status", st);
            emit("apothecary:printer-status", st);  // the world's rows, badges and marks read this
            if (st.control) applyControlState(st.control);
            const hadLink = !!(state.info && state.info.link);
            if (!state.info || hadLink !== !!st.held) {
                // The link came or went (a failed poll drops it): refresh the
                // board card; the port list only when we had no info at all.
                const first = !state.info;
                await loadInfo();
                if (first) loadPorts();
            }
        } catch (e) {
            if (gen !== state.gen) return;
            $("dot").className = "dot bad"; $("c-state").innerHTML = '<span class="bad">error</span>'; $("c-state-s").textContent = e.message;
        } finally { if (state.inFlight === gen) state.inFlight = false; }
        await pullLog();
    }
    function schedule() {
        clearTimeout(state.timer); state.timer = null;
        const gen = ++state.gen;
        if (!$("auto").checked || !state.port || document.hidden) return;
        state.timer = setTimeout(async () => { if (gen !== state.gen) return; await pollOnce(); if (gen === state.gen) schedule(); }, Number($("interval").value) || 2000);
    }
    async function loadInfo() {
        const port = state.port, gen = state.gen;
        if (!port) { state.info = null; renderBoard(); return; }
        const info = await api(`/firmware/printers/info?port=${encodeURIComponent(port)}`);
        if (gen !== state.gen) return;
        state.info = info;
        if (info.last_status && !state.status) { state.status = info.last_status; }
        applyControlState(info.control);
        renderStatus();
    }

    async function selectPort(port) {
        state.gen++; clearTimeout(state.timer); state.inFlight = false;
        state.port = port; state.status = null; state.info = null; state.history = []; state.entries = []; state.logNext = 0;
        applyControlState(null);
        if (host === "page") {
            const url = new URL(location.href); if (port) url.searchParams.set("port", port); else url.searchParams.delete("port"); history.replaceState(null, "", url);
        }
        if ($("port").value !== port) $("port").value = port;
        renderStatus(); renderChart(); renderLog();
        loadLevel(); loadPrintRecords();
        if (!port) return;
        $("ident").textContent = "connecting…";
        loadCodes();
        try { await loadInfo(); } catch (e) { logLine("sys", e.message); }
        await pollOnce();
        schedule();
    }

    // --- header controls ------------------------------------------------------------------
    $("port").addEventListener("change", () => selectPort($("port").value));
    $("auto").addEventListener("change", schedule);
    $("interval").addEventListener("change", schedule);
    const onVisibility = () => schedule();
    document.addEventListener("visibilitychange", onVisibility);
    $("poll").onclick = () => pollOnce();
    $("reconnect").onclick = async () => {
        if (!state.port) return;
        try { state.status = await post("/firmware/printers/reconnect", { port: state.port }); pushHistory(state.status); await loadInfo(); renderChart(); }
        catch (e) { logLine("sys", "reconnect failed: " + e.message); }
        await pullLog().catch(() => {});
    };
    $("identify").onclick = async () => {
        if (!state.port) return;
        try { await post("/firmware/devices/identify", { port: state.port }); await loadInfo(); await loadPorts(); }
        catch (e) { logLine("sys", "M115: " + e.message); }
        await pullLog().catch(() => {});
    };
    $("reset").onclick = async () => {
        if (!state.port) return;
        if (!confirm(`Reboot the board on ${state.port} (DTR pulse)?\nA running print would be lost.`)) return;
        try { await post("/firmware/printers/reset", { port: state.port }); state.history = []; renderChart(); await loadInfo(); }
        catch (e) { logLine("sys", "reset failed: " + e.message); }
        await pullLog().catch(() => {});
    };
    $("release").onclick = async () => {
        if (!state.port) return;
        $("auto").checked = false; schedule();
        try { const r = await post("/firmware/printers/release", { port: state.port }); logLine("sys", r.released ? "link released — auto-poll off" : "no link was held"); applyControlState(null); await loadInfo(); }
        catch (e) { logLine("sys", "release failed: " + e.message); }
    };
    $("qform").addEventListener("submit", async (ev) => {
        ev.preventDefault();
        const command = $("q").value.trim(); if (!command || !state.port) return;
        $("q").disabled = true;
        try { await post("/firmware/printers/query", { port: state.port, command }); $("q").value = ""; }
        catch (e) { logLine("sys", "query refused: " + e.message); }
        $("q").disabled = false; $("q").focus();
        await pullLog().catch(() => {});
    });
    $("show-polls").addEventListener("change", renderLog);
    $("clear").onclick = () => { state.entries = []; renderLog(); };
    $("download").onclick = () => {
        const text = state.entries.map((e) => `${e.t} ${e.kind.padEnd(4)} ${e.text}`).join("\n");
        const a = document.createElement("a");
        a.href = URL.createObjectURL(new Blob([text], { type: "text/plain" }));
        a.download = `apothecary-${(state.port || "printer").replace(/[^A-Za-z0-9]+/g, "_")}-${new Date().toISOString().slice(0, 19).replace(/[:T]/g, "-")}.log`;
        a.click(); URL.revokeObjectURL(a.href);
    };

    // --- control latch + pad ---------------------------------------------------------------
    const ctl = { armed: false, until: 0, step: 10, timer: null };
    function renderControl() {
        const left = Math.max(0, Math.round((ctl.until - Date.now()) / 1000));
        if (ctl.armed && left <= 0) { ctl.armed = false; }
        $("ctl").checked = ctl.armed;
        $("ctl-label").classList.toggle("armed", ctl.armed);
        $("control").hidden = !ctl.armed;
        const ttl = ctl.armed ? `${Math.floor(left / 60)}:${String(left % 60).padStart(2, "0")}` : "";
        $("ctl-ttl").textContent = ttl; $("ctl-ttl2").textContent = ttl;
        clearInterval(ctl.timer); ctl.timer = null;
        if (ctl.armed) ctl.timer = setInterval(renderControl, 1000);
    }
    function applyControlState(c) {
        ctl.armed = !!(c && c.armed);
        ctl.until = Date.now() + (c ? c.seconds_left * 1000 : 0);
        renderControl();
    }
    async function arm(on) {
        if (!state.port) { $("ctl").checked = false; return; }
        try { applyControlState(await post("/firmware/printers/control", { port: state.port, armed: on })); }
        catch (e) { logLine("sys", "control: " + e.message); applyControlState(null); }
        await pullLog().catch(() => {});
    }
    function fillTemplate(cmd) {
        return cmd.replace(/\{([a-z-]+)\}/g, (_, id) => $(id).value);
    }
    // Every control send goes through one chain, and the pad is disabled
    // while it runs: two jogs can never interleave their G91/G1/G90 lines,
    // which would turn the second into an absolute move.
    let ctlChain = Promise.resolve();
    function setBusy(on) {
        for (const b of $("control").querySelectorAll("button")) b.disabled = on;
        $("estop").disabled = false;  // never
    }
    async function sendLines(lines) {
        const sent = $("ctl-sent");
        for (const command of lines) {
            sent.textContent = "> " + command; sent.classList.remove("bad");
            try {
                const r = await post("/firmware/printers/command", { port: state.port, command });
                applyControlState(r.control);
            } catch (e) {
                sent.textContent = `${command}: ${e.message}`; sent.classList.add("bad");
                if (/not armed/.test(e.message)) applyControlState(null);
                return false;
            }
        }
        return true;
    }
    function sendControl(command, confirmText) {
        if (!state.port) return Promise.resolve();
        if (confirmText && !confirm(confirmText)) return Promise.resolve();
        return enqueue([command]);
    }
    function enqueue(lines) {
        ctlChain = ctlChain.then(async () => {
            setBusy(true);
            try { await sendLines(lines); await pollOnce(); }  // the effect shows in the cards right away
            finally { setBusy(false); }
            await pullLog();
        }).catch(() => setBusy(false));
        return ctlChain;
    }
    function jog(axis, sign) {
        const d = (sign === "-" ? -ctl.step : ctl.step).toFixed(1).replace(/\.0$/, "");
        const f = Number($("h-feed").value) || 3000;
        // Relative move as three lines, sent back to back, restoring absolute mode afterwards.
        // The nozzle marker moves ahead of the poll that confirms it.
        const p = state.status && state.status.position ? { ...state.status.position } : { x: 0, y: 0, z: 0 };
        p[axis.toLowerCase()] = (p[axis.toLowerCase()] || 0) + Number(d);
        emit("apothecary:position", { position: p, source: "jog", port: state.port });
        return enqueue(["G91", `G1 ${axis}${d} F${f}`, "G90"]);
    }
    $("ctl").addEventListener("change", () => arm($("ctl").checked));
    $("ctl-disarm").onclick = () => arm(false);
    async function estop() {
        if (!state.port || !confirm(`EMERGENCY STOP ${state.port}?\nHeaters and motors off; the board halts until it is reset.`)) return;
        await sendLines(["M112"]);  // straight through, never queued behind a jog
        await pollOnce(); await pullLog();
    }
    $("estop").onclick = estop;
    $("h-fan").addEventListener("input", () => { $("h-fan-v").textContent = $("h-fan").value; });
    $("control").addEventListener("click", (ev) => {
        const btn = ev.target.closest("button"); if (!btn) return;
        if (btn.dataset.step) {
            ctl.step = Number(btn.dataset.step);
            for (const b of $("control").querySelectorAll(".steps button")) b.classList.toggle("on", b === btn);
        } else if (btn.dataset.jog) {
            jog(btn.dataset.jog[0], btn.dataset.jog[1]);
        } else if (btn.dataset.cmd) {
            sendControl(fillTemplate(btn.dataset.cmd), btn.dataset.confirm);
        }
    });
    const onUnload = () => { state.gen++; clearTimeout(state.timer); };
    window.addEventListener("beforeunload", onUnload);
    onWindow.push(["beforeunload", onUnload]);

    // --- bed level: probe or read, show the mesh, keep the records -----------------------
    const level = { records: [], shown: null, timer: null, volume: [220, 220, 250] };
    const onWhere = (ev) => { if (ev.detail && ev.detail.printer && ev.detail.printer.build_volume && (!ev.detail.port || ev.detail.port === state.port)) level.volume = ev.detail.printer.build_volume; };
    window.addEventListener("apothecary:where", onWhere);
    onWindow.push(["apothecary:where", onWhere]);
    function cornerLines(which) {
        // Paper height at the four corners, inset from the edges; lifted first so a
        // nozzle never drags. Absolute moves; the allowlist bounds them.
        const [vx, vy] = level.volume, inset = 30, z = 0.2, f = 3000;
        const x = which[1] === "L" ? inset : Math.round(vx - inset);
        const y = which[0] === "F" ? inset : Math.round(vy - inset);
        return ["G90", `G1 Z5 F${f}`, `G1 X${x} Y${y} F${f}`, `G1 Z${z} F${Math.min(f, 600)}`];
    }
    function heat(v, lo, hi) {
        // Blue below the mean, amber above: the same two hues as the chart, so a
        // low corner reads as "bed" and a high one as "hotend" without a key.
        const t = hi > lo ? (v - lo) / (hi - lo) : 0.5;
        const a = [0x6f, 0xb3, 0xe8], b = [0xe8, 0xb0, 0x4a];
        return `rgb(${a.map((c, i) => Math.round(c + (b[i] - c) * t)).join(",")})`;
    }
    function renderLevel() {
        const rec = level.shown;
        const meshEl = $("mesh"), statsEl = $("level-stats");
        if (!rec || !rec.mesh || !rec.mesh.length) {
            meshEl.innerHTML = ""; meshEl.style.gridTemplateColumns = "";
            statsEl.innerHTML = '<span class="empty">no reading yet — Read mesh, or arm control and Probe bed</span>';
        } else {
            const st = rec.stats || {};
            const rows = rec.mesh, cols = rows[0].length;
            meshEl.style.gridTemplateColumns = `repeat(${cols}, 1fr)`;
            // Drawn as the bed lies: the last row printed is the back of the bed, so it goes on top.
            meshEl.innerHTML = [...rows].reverse().map((row) => row.map((v) => `<div class="cell" style="background:${heat(v, st.min, st.max)}" title="${v.toFixed(3)} mm">${v.toFixed(2)}</div>`).join("")).join("");
            const c = st.corners || {};
            statsEl.innerHTML = `${esc(rec.method)} · ${new Date(rec.at).toLocaleString()} · range <b>${(st.range ?? 0).toFixed(3)}</b> mm · tilt X <b>${(st.tilt_x ?? 0).toFixed(3)}</b> Y <b>${(st.tilt_y ?? 0).toFixed(3)}</b> mm across the bed<br>`
                + `corners vs mean: FL <b>${(c.front_left ?? 0).toFixed(3)}</b> FR <b>${(c.front_right ?? 0).toFixed(3)}</b> BL <b>${(c.back_left ?? 0).toFixed(3)}</b> BR <b>${(c.back_right ?? 0).toFixed(3)}</b> · leveling ${rec.leveling_on == null ? "?" : (rec.leveling_on ? "on" : "off")}`
                + (rec.probe_offset ? ` · probe offset X${rec.probe_offset.x} Y${rec.probe_offset.y} Z${rec.probe_offset.z}` : "")
                + (rec.bed_c != null ? ` · bed ${rec.bed_c.toFixed(1)}°` : "") + (rec.hotend_c != null ? ` hotend ${rec.hotend_c.toFixed(1)}°` : "")
                + (rec.note ? `<br>note: ${esc(rec.note)}` : "");
        }
        emit("apothecary:mesh", rec || null);  // the board view and the world draw it over the bed
        $("level-history").innerHTML = level.records.length
            ? level.records.map((r) => `<div><span class="pick ${level.shown && r.id === level.shown.id ? "on" : ""}" data-id="${esc(r.id)}">${new Date(r.at).toLocaleString()} · ${esc(r.method)} · range ${(r.stats && r.stats.range != null ? r.stats.range : 0).toFixed(3)} mm</span><a href="${BASE}/firmware/printers/leveling/${encodeURIComponent(r.id)}" download="${esc(r.id)}.json" title="The record as JSON, with every line the firmware said">⤓ log</a></div>`).join("")
            : "";
    }
    async function loadLevel() {
        if (!state.port) { level.records = []; level.shown = null; renderLevel(); return; }
        try {
            level.records = await api(`/firmware/printers/leveling?port=${encodeURIComponent(state.port)}`);
            if (!level.shown || !level.records.some((r) => r.id === level.shown.id)) level.shown = level.records[0] || null;
        } catch (e) { level.records = []; }
        renderLevel();
    }
    async function watchLevelJob() {
        clearTimeout(level.timer);
        try {
            const job = await api(`/firmware/printers/level?port=${encodeURIComponent(state.port)}`);
            $("level-job").textContent = job.running ? `${job.stage}…` : (job.error ? `failed: ${job.error}` : "");
            if (job.running) { level.timer = setTimeout(watchLevelJob, 1000); return; }
            if (job.record_id) { await loadLevel(); level.shown = level.records.find((r) => r.id === job.record_id) || level.shown; renderLevel(); }
            await pollOnce();
        } catch (e) { $("level-job").textContent = e.message; }
    }
    async function startLevel(probe) {
        if (!state.port) return;
        if (probe && !ctl.armed) { logLine("sys", "probing moves the machine: arm control first"); return; }
        if (probe && !confirm(`Home and probe the bed on ${state.port}?\nThe nozzle will travel the whole bed.`)) return;
        try {
            const job = await post("/firmware/printers/level", { port: state.port, probe });
            $("level-job").textContent = `${job.stage}…`;
            level.timer = setTimeout(watchLevelJob, 800);
        } catch (e) { logLine("sys", "bed reading: " + e.message); $("level-job").textContent = e.message; }
    }
    $("level-probe").onclick = () => startLevel(true);
    $("level-read").onclick = () => startLevel(false);
    $("level-history").addEventListener("click", (ev) => {
        const pick = ev.target.closest(".pick"); if (!pick) return;
        level.shown = level.records.find((r) => r.id === pick.dataset.id) || level.shown; renderLevel();
    });
    $("level-card").addEventListener("click", (ev) => {
        const b = ev.target.closest("button[data-corner]"); if (!b) return;
        if (!ctl.armed) { logLine("sys", "a corner move needs control armed"); return; }
        enqueue(cornerLines(b.dataset.corner));
    });
    // The state card says when a reading or a print holds the port.
    const onStatus = (ev) => {
        const st = ev.detail; const job = st && st.job;
        if (!st || st.port !== state.port) return;
        if (job && job.kind === "leveling") { $("level-job").textContent = `${job.stage}…`; if (!level.timer) level.timer = setTimeout(watchLevelJob, 1000); }
        if (job && job.kind === "print") { prt.job = job; renderPrint(); if (!prt.timer) prt.timer = setTimeout(watchPrint, 1000); }
    };
    window.addEventListener("apothecary:status", onStatus);
    onWindow.push(["apothecary:status", onStatus]);

    // --- print from here: a kept file streamed over the link -------------------------
    const prt = { files: [], records: [], job: null, timer: null };
    function fmtDurS(s) { s = Math.round(s); return s >= 3600 ? `${Math.floor(s / 3600)}h ${Math.floor((s % 3600) / 60)}m` : `${Math.floor(s / 60)}m ${s % 60}s`; }
    function renderPrint() {
        const job = prt.job, running = !!(job && job.running);
        const paused = running && job.stage === "paused";
        $("print-start").disabled = running || !$("print-pick").value;
        $("print-pause").disabled = !running || paused || job.stage !== "printing";
        $("print-resume").disabled = !paused;
        $("print-cancel").disabled = !running;
        $("print-delete").disabled = !$("print-pick").value || (running && job.file_id === $("print-pick").value);
        if (job && (running || job.stage)) {
            const pct = (job.progress * 100).toFixed(1);
            $("print-progress").className = "";
            $("print-progress").textContent = `${job.name} · ${job.stage} · ${job.sent}/${job.total} lines (${pct}%) · ${fmtDurS(job.elapsed_s)}` + (job.current && running ? ` · ${job.current}` : "") + (job.error ? ` · ${job.error}` : "");
            $("b-print").style.width = pct + "%";
        } else {
            $("print-progress").className = "empty"; $("print-progress").textContent = "nothing printing from here"; $("b-print").style.width = "0";
        }
        $("print-job").textContent = running ? `${job.stage}…` : "";
        $("print-history").innerHTML = prt.records.map((r) => `<div><span class="${esc(r.outcome)}">${new Date(r.at).toLocaleString()} · ${esc(r.name)} · ${esc(r.outcome)} · ${r.sent}/${r.total} lines</span><a href="${BASE}/firmware/printers/print/records/${encodeURIComponent(r.id)}" download="${esc(r.id)}.json" title="The record as JSON, with the tail of what the firmware said">⤓ log</a></div>`).join("");
    }
    async function loadPrintFiles(pick) {
        try { prt.files = await api("/firmware/printers/prints"); } catch (e) { prt.files = []; }
        const sel = $("print-pick"), had = pick || sel.value;
        sel.innerHTML = prt.files.length
            ? prt.files.map((f) => `<option value="${esc(f.id)}" ${f.problems.length ? 'class="bad"' : ""}>${esc(f.name)} · ${f.lines} lines${f.problems.length ? " · refused: " + esc(f.problems[0]) : ""}</option>`).join("")
            : '<option value="">— no files kept —</option>';
        if (had && prt.files.some((f) => f.id === had)) sel.value = had;
        renderPrint();
    }
    async function loadPrintRecords() {
        if (!state.port) { prt.records = []; renderPrint(); return; }
        try { prt.records = await api(`/firmware/printers/print/records?port=${encodeURIComponent(state.port)}`); } catch (e) { prt.records = []; }
        renderPrint();
    }
    async function watchPrint() {
        clearTimeout(prt.timer); prt.timer = null;
        if (!state.port) return;
        try {
            prt.job = await api(`/firmware/printers/print?port=${encodeURIComponent(state.port)}`);
            renderPrint();
            if (prt.job.running) { prt.timer = setTimeout(watchPrint, 1000); return; }
            await loadPrintRecords();
            await pollOnce();
        } catch (e) { $("print-job").textContent = e.message; }
    }
    async function keepPrintFile(file) {
        if (!file) return;
        try {
            const r = await fetch(`${BASE}/firmware/printers/prints?name=${encodeURIComponent(file.name)}`, { method: "POST", body: file, headers: { "Content-Type": "text/plain" } });
            const body = await r.json().catch(() => ({}));
            if (!r.ok) throw new Error(body.detail || r.statusText);
            logLine("sys", `kept ${body.name}: ${body.lines} lines` + (body.problems.length ? ` -- refused: ${body.problems.join("; ")}` : ""));
            await loadPrintFiles(body.id);
        } catch (e) { logLine("sys", "keep file: " + e.message); }
        $("print-file").value = "";
    }
    async function startPrint() {
        const fileId = $("print-pick").value;
        if (!state.port || !fileId) { logLine("sys", "print: pick a port and a file first"); return; }
        if (!ctl.armed) { logLine("sys", "a print heats and moves the machine: arm control first"); return; }
        const f = prt.files.find((x) => x.id === fileId);
        if (!confirm(`Print ${f ? f.name : fileId} on ${state.port}?\n${f ? f.lines + " lines" : ""} will stream from here; the printer will heat and move.`)) return;
        try {
            prt.job = await post("/firmware/printers/print", { port: state.port, file_id: fileId });
            renderPrint();
            prt.timer = setTimeout(watchPrint, 800);
        } catch (e) { logLine("sys", "print: " + e.message); $("print-job").textContent = e.message; }
    }
    async function printVerb(verb) {
        if (!state.port) return;
        if (verb === "cancel" && !confirm("Cancel the print from here? Heaters and fan go off, motors free.")) return;
        try { prt.job = await post(`/firmware/printers/print/${verb}`, { port: state.port }); renderPrint(); if (!prt.timer) prt.timer = setTimeout(watchPrint, 500); }
        catch (e) { logLine("sys", `print ${verb}: ` + e.message); }
    }
    $("print-file").addEventListener("change", (ev) => keepPrintFile(ev.target.files[0]));
    $("print-pick").addEventListener("change", renderPrint);
    $("print-delete").onclick = async () => {
        const id = $("print-pick").value; if (!id) return;
        try { await api(`/firmware/printers/prints/${encodeURIComponent(id)}`, { method: "DELETE" }); await loadPrintFiles(); }
        catch (e) { logLine("sys", "forget file: " + e.message); }
    };
    $("print-start").onclick = startPrint;
    $("print-pause").onclick = () => printVerb("pause");
    $("print-resume").onclick = () => printVerb("resume");
    $("print-cancel").onclick = () => printVerb("cancel");

    // --- the ring's side: what this machine knows, and carrying a chosen verb ------------
    function device() {
        const printer = !!(state.info && state.info.device && state.info.device.device && state.info.device.device.printer);
        return { port: state.port, printer, armed: ctl.armed, bound: true };
    }
    async function carry(intent) {
        const action = intent.action;
        const jogM = /^control:jog:([XYZ])([+-])$/.exec(action);
        if (jogM) { jog(jogM[1], jogM[2]); return true; }
        if (action === "control:estop") { await estop(); return true; }
        if (action === "control:arm") { await arm(true); return true; }
        if (action === "control:disarm") { await arm(false); return true; }
        const corner = /^control:corner:([FB][LR])$/.exec(action);
        if (corner) { if (!ctl.armed) { logLine("sys", "a corner move needs control armed"); return true; } enqueue(cornerLines(corner[1])); return true; }
        if (action === "level:probe") { await startLevel(true); return true; }
        if (action === "level:read") { await startLevel(false); return true; }
        if (action === "print:start") { await startPrint(); return true; }
        if (prt.job && prt.job.running && action in HOST_VERBS) { await printVerb(HOST_VERBS[action]); return true; }
        if (action in LINES) {
            if (!ctl.armed) { logLine("sys", `${intent.label} (⌗${intent.address}): control is not armed`); return true; }
            await sendControl(LINES[action](handle), CONFIRM[action]);
            return true;
        }
        if (action === "device:poll") { await pollOnce(); return true; }
        if (action === "device:query") { await $("identify").onclick(); return true; }
        if (action === "device:rescan") { await loadPorts(); logLine("sys", "ports rescanned"); return true; }
        if (action === "device:watch") { $("auto").checked = true; schedule(); logLine("sys", "auto-poll on"); return true; }
        // The link verbs are the header buttons; their handlers already confirm what needs confirming.
        if (action === "device:reconnect") { $("reconnect").click(); return true; }
        if (action === "device:reset") { $("reset").click(); return true; }
        if (action === "device:release") { $("release").click(); return true; }
        return false;  // not this machine's: the host decides (monitor, pin, unpin)
    }
    // The buttons this machine has, each by the verb it is -- for the ring's addresses.
    function pairs() {
        const out = [];
        for (const b of $("control").querySelectorAll("button[data-cmd]")) out.push([b, BY_CMD[b.dataset.cmd] || null]);
        for (const b of $("control").querySelectorAll("button[data-jog]")) out.push([b, `control:jog:${b.dataset.jog}`]);
        out.push([$("ctl"), ctl.armed ? "control:disarm" : "control:arm"]);
        out.push([$("ctl-label"), ctl.armed ? "control:disarm" : "control:arm"]);
        out.push([$("ctl-disarm"), "control:disarm"]);
        out.push([$("estop"), "control:estop"]);
        out.push([$("poll"), "device:poll"]);
        out.push([$("identify"), "device:query"]);
        out.push([$("reconnect"), "device:reconnect"]);
        out.push([$("reset"), "device:reset"]);
        out.push([$("release"), "device:release"]);
        out.push([$("level-probe"), "level:probe"]);
        out.push([$("level-read"), "level:read"]);
        for (const b of $("level-card").querySelectorAll("button[data-corner]")) out.push([b, `control:corner:${b.dataset.corner}`]);
        out.push([$("print-start"), "print:start"]);
        out.push([$("print-pause"), "control:sd-pause"]);
        out.push([$("print-resume"), "control:sd-resume"]);
        out.push([$("print-cancel"), "control:sd-abort"]);
        return out;
    }

    const handle = {
        root, host, $,
        state, ctl, arm, jog, estop, enqueue, sendControl, fillTemplate, pollOnce, loadPorts, logLine, schedule, selectPort,
        identify: () => $("identify").onclick(),
        device, carry, pairs,
        level: { start: startLevel, corner: (which) => enqueue(cornerLines(which)), lines: cornerLines, records: () => level.records, shown: () => level.shown, load: loadLevel },
        print: { start: startPrint, verb: printVerb, keep: keepPrintFile, job: () => prt.job, files: () => prt.files, records: () => prt.records, load: loadPrintFiles },
        destroy() {
            state.gen++; clearTimeout(state.timer); clearTimeout(level.timer); clearTimeout(prt.timer); clearInterval(ctl.timer);
            document.removeEventListener("visibilitychange", onVisibility);
            for (const [event, fn] of onWindow) window.removeEventListener(event, fn);
            root.innerHTML = ""; root.classList.remove("machine", `host-${host}`);
            if (logRoot) { logRoot.innerHTML = ""; logRoot.classList.remove("machine-log", "right"); }
        },
    };

    loadPrintFiles(); loadPrintRecords(); watchPrint();
    loadPorts().then(() => { if (state.port) selectPort(state.port); });
    return handle;
}
