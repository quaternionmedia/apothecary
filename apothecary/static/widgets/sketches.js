/* Sketches: one sketch built for one board and, asked, uploaded to a port -- and
 * raw images written to an Espressif chip with esptool.
 *
 * A sketch is parts/<name>/<name>.ino; a firmware.json beside it names the
 * board it is built for by default (its FQBN), the libraries it needs and a
 * note. mountBuild() is the form that picks one, names the board, and compiles
 * it (POST /firmware/sketches/{name}/compile) or compiles and uploads it to a
 * port, after asking (.../upload): the Bench's, with a drop-down of the
 * detected ports, and a board's Machine's Flashing card, for its own port. Each
 * is a task, followed in a task log (`tasks`, widgets/tasks.js). mountRawFlash()
 * is the Bench's esptool section: images, one "offset path" per line, written
 * to the chip on the Bench's port (POST /firmware/esptool/flash), after asking.
 *
 * mountBuild(root, { base, tasks, say, port, suggest, onEnd, onPort }) returns
 * { load(status), compile(), upload(), choose(name), chosen(), fqbn(), port(),
 * enable(), destroy() }. `port` fixes the port (a Machine's); left out, the form
 * offers the detected ones. `suggest()` names the sketch to start from (what the
 * board should run); `onEnd(task, what)` is told how a compile or an upload
 * ended, `what` being { kind, sketch, fqbn, port }; `onPort(port)` of a port
 * chosen from the drop-down.
 */

import { esc } from "/static/board_text.js";

const FQBN = /^[\w.\-]+:[\w.\-]+:[\w.\-]+(:[\w=,.\-]+)?$/;
let mounted = 0;  // a datalist needs an id, one per form on the page

async function call(base, path, opts = {}) {
    const r = await fetch(base + path, { headers: { "Content-Type": "application/json" }, ...opts });
    const body = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(typeof body.detail === "string" ? body.detail : (body.detail ? JSON.stringify(body.detail) : r.statusText));
    return body;
}

export function mountBuild(root, { base = "", tasks = null, say = null, port = null, suggest = null, onEnd = null, onPort = null } = {}) {
    const listId = `fqbn-list-${++mounted}`;
    root.innerHTML = `
<div class="bench-build">
    <div class="row"><span class="meta">sketch</span>
        <select class="sketch-select grow" aria-label="Sketch" title="A sketch under parts/: parts/&lt;name&gt;/&lt;name&gt;.ino"><option value="">— no sketches under parts/ —</option></select></div>
    <div class="sk-note note" hidden></div>
    <div class="row"><span class="meta">board</span>
        <input class="fqbn-input grow" list="${listId}" placeholder="arduino:avr:uno" spellcheck="false" aria-label="Board (FQBN)" title="The board to build for (its FQBN); the sketch's firmware.json names one"></div>
    <datalist id="${listId}"></datalist>
    <div class="row sk-port-row"><span class="meta">port</span>
        <select class="port-select grow" aria-label="Port" title="The port to upload to"><option value="">(none detected)</option></select></div>
    <div class="row">
        <button type="button" class="compile-btn" title="Build the sketch for the board; nothing is sent to a board">Compile</button>
        <button type="button" class="upload-btn" title="Build it, then write it to the board on the port (asks first)">Compile &amp; upload</button>
    </div>
</div>`;
    const $ = (sel) => root.querySelector(sel);
    const api = (path, opts) => call(base, path, opts);
    const post = (path, data) => api(path, { method: "POST", body: JSON.stringify(data ?? {}) });
    let sketches = [], status = null, alive = true;
    if (port) $(".sk-port-row").hidden = true;

    function choose(name) {
        const s = sketches.find((x) => x.name === name);
        if (!s) return false;
        $(".sketch-select").value = name;
        if (s.fqbn) $(".fqbn-input").value = s.fqbn;
        const bits = [];
        if (s.libraries && s.libraries.length) bits.push("libraries: " + s.libraries.join(", "));
        if (s.note) bits.push(s.note);
        $(".sk-note").hidden = !bits.length;
        $(".sk-note").textContent = bits.join(" — ");
        enable();
        return true;
    }
    const chosen = () => $(".sketch-select").value || null;
    const fqbn = () => $(".fqbn-input").value.trim();
    const portOf = () => port || $(".port-select").value || null;

    function enable() {
        const ok = !!(status && status.arduino_cli_ok);
        const busy = !!(tasks && tasks.running()) || !!(status && status.active_task && status.active_task.status === "running");
        const ready = ok && !!chosen() && FQBN.test(fqbn());
        $(".compile-btn").disabled = !ready || busy;
        $(".upload-btn").disabled = !ready || !portOf() || busy;
    }

    async function load(given = null) {
        const [s, list, all, found] = await Promise.all([
            given ? Promise.resolve(given) : api("/firmware/status").catch(() => null),
            api("/firmware/sketches").catch(() => []),
            api("/firmware/boards/all").catch(() => []),
            port ? Promise.resolve(null) : api("/firmware/devices").catch(() => ({ devices: [] })),
        ]);
        if (!alive) return;
        status = s; sketches = list;
        const had = chosen();
        $(".sketch-select").innerHTML = sketches.length
            ? sketches.map((x) => `<option value="${esc(x.name)}">${esc(x.name)}${x.fqbn ? " · " + esc(x.fqbn) : " · no default board"}</option>`).join("")
            : '<option value="">— no sketches under parts/ —</option>';
        root.querySelector(`#${CSS.escape(listId)}`).innerHTML = all.map((b) => `<option value="${esc(b.fqbn)}">${esc(b.name)}</option>`).join("");
        if (found) {
            const sel = $(".port-select"), was = sel.value;
            const devices = (found.devices || []).map((v) => v.device);
            sel.innerHTML = devices.length
                ? devices.map((d) => `<option value="${esc(d.port)}">${esc(d.port)} — ${esc(d.printer ? (d.printer.firmware_name || "printer") : (d.board_name || d.chip || "unknown"))}</option>`).join("")
                : '<option value="">(none detected)</option>';
            if (devices.some((d) => d.port === was)) sel.value = was;
        }
        const want = (had && sketches.some((x) => x.name === had) && had) || (suggest && suggest()) || (sketches[0] && sketches[0].name);
        if (!want || !choose(want)) enable();
    }

    async function run(kind, request) {
        if (!tasks) return null;
        const what = { kind, sketch: chosen(), fqbn: fqbn(), port: portOf() };
        const ending = tasks.start(request);
        enable();
        const task = await ending;
        enable();
        if (task && onEnd) onEnd(task, what);
        return task;
    }
    function compile() {
        if (!chosen() || !FQBN.test(fqbn())) { if (say) say("Compile: choose a sketch and a board (FQBN) first", "error"); return null; }
        return run("compile", () => post(`/firmware/sketches/${encodeURIComponent(chosen())}/compile`, { fqbn: fqbn() }));
    }
    function upload() {
        const to = portOf();
        if (!chosen() || !FQBN.test(fqbn()) || !to) { if (say) say("Upload: choose a sketch, a board (FQBN) and a port first", "error"); return null; }
        if (!confirm(`Compile and upload "${chosen()}" to ${to}?`)) return null;
        return run("upload", () => post(`/firmware/sketches/${encodeURIComponent(chosen())}/upload`, { fqbn: fqbn(), port: to }));
    }

    $(".compile-btn").onclick = () => compile();
    $(".upload-btn").onclick = () => upload();
    const sketchEl = $(".sketch-select");
    sketchEl.addEventListener("change", () => choose(sketchEl.value));
    const fqbnEl = $(".fqbn-input");
    fqbnEl.addEventListener("input", enable);
    const portEl = $(".port-select");
    portEl.addEventListener("change", () => { enable(); if (onPort) onPort(portOf()); });

    return {
        load, compile, upload, choose, chosen, fqbn, enable,
        port: portOf,
        setStatus(s) { status = s; enable(); },
        destroy() { alive = false; root.innerHTML = ""; },
    };
}

// esptool's raw flash: the images, one "offset path" per line, written to the
// chip on `port()` -- the Bench's port drop-down.
export function mountRawFlash(root, { base = "", tasks = null, say = null, port = () => null } = {}) {
    root.innerHTML = `
<div class="bench-raw">
    <div class="row">
        <span class="meta">chip</span><input class="esp-chip" value="auto" spellcheck="false" aria-label="Chip" title="esptool's chip name, or auto">
        <span class="meta">baud</span><input class="esp-baud" type="number" value="460800" aria-label="Baud" title="The flashing baud rate">
    </div>
    <textarea class="esp-images" rows="2" spellcheck="false" aria-label="Images" placeholder="0x10000 build/firmware/app.bin" title="One image per line: its flash offset, then its path relative to the repository"></textarea>
    <div class="row">
        <label title="Erase the whole flash before writing"><input type="checkbox" class="esp-erase"> erase flash first</label>
        <span class="grow"></span>
        <button type="button" class="esp-flash-btn" title="Write the images to the chip on the Bench's port (asks first)">Flash</button>
    </div>
    <div class="esp-note note"></div>
</div>`;
    const $ = (sel) => root.querySelector(sel);
    let status = null;

    function images() {
        return $(".esp-images").value.split("\n").map((line) => line.trim()).filter(Boolean).map((line) => {
            const [offset, ...rest] = line.split(/\s+/);
            return { offset, path: rest.join(" ") };
        });
    }
    function enable() {
        const busy = !!(tasks && tasks.running()) || !!(status && status.active_task && status.active_task.status === "running");
        $(".esp-flash-btn").disabled = !(status && status.esptool_ok) || !port() || busy;
        $(".esp-note").textContent = status && !status.esptool_ok ? "esptool not found: pip install esptool, or install the esp32 core (it bundles one)." : "";
    }
    async function flash() {
        const to = port(), list = images();
        if (!to) { if (say) say("Raw flash: choose a port on the Bench first", "error"); return null; }
        if (!list.length || list.some((i) => !i.path)) { if (say) say("Raw flash: one image per line, its offset and its path", "error"); return null; }
        const erase = $(".esp-erase").checked;
        if (!confirm(`Flash ${list.length} image(s) to ${to}${erase ? " after erasing" : ""}?`)) return null;
        if (!tasks) return null;
        const ending = tasks.start(() => call(base, "/firmware/esptool/flash", {
            method: "POST",
            body: JSON.stringify({ port: to, chip: $(".esp-chip").value.trim() || "auto", baud: Number($(".esp-baud").value) || 460800, erase, images: list }),
        }));
        enable();
        const task = await ending;
        enable();
        return task;
    }
    $(".esp-flash-btn").onclick = () => flash();
    return { flash, images, enable, setStatus(s) { status = s; enable(); }, destroy() { root.innerHTML = ""; } };
}
