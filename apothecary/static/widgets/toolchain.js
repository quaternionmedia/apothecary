/* The toolchain: arduino-cli and esptool as they are installed, the suggested
 * cores, and libraries -- the Bench's first section.
 *
 * arduino-cli is downloaded from Arduino's releases (SHA-256 verified) into the
 * tools dir by POST /firmware/install; a core is POST /firmware/cores/install
 * (its board-manager index added first); libraries are POST
 * /firmware/libraries/install. Each is a task, followed in the Bench's task log
 * (`tasks`, widgets/tasks.js).
 *
 * mountToolchain(root, { base, tasks, say, onStatus }) renders into `root` and
 * returns { load(), status(), install(), core(id), libraries(), destroy() }.
 * load() asks GET /firmware/status again and hands it to `onStatus` as well.
 */

import { esc } from "/static/board_text.js";

const MARKUP = `
<div class="bench-toolchain">
    <div class="k">Toolchain</div>
    <div class="tc-status kv"><span class="empty">loading…</span></div>
    <div class="row">
        <button type="button" class="install-btn" title="Download arduino-cli from Arduino's GitHub releases (SHA-256 verified) into the tools dir; installed, it says so and keeps it unless forced">Install arduino-cli</button>
        <label title="Download it again even when one is installed"><input type="checkbox" class="install-force"> force</label>
    </div>
    <div class="k">Cores</div>
    <ul class="tc-cores"><li class="empty">–</li></ul>
    <div class="note">One-click installs add the vendor's board-manager index first.</div>
    <div class="k">Libraries</div>
    <div class="row">
        <input class="lib-input grow" placeholder="e.g. FastLED, Control Surface@2.1.2" spellcheck="false" aria-label="Libraries to install">
        <button type="button" class="lib-btn" title="Install the libraries named in the box, comma-separated">Install</button>
    </div>
</div>`;

export function mountToolchain(root, { base = "", tasks = null, say = null, onStatus = null } = {}) {
    root.innerHTML = MARKUP;
    const $ = (sel) => root.querySelector(sel);
    let status = null, alive = true;

    async function api(path, opts = {}) {
        const r = await fetch(base + path, { headers: { "Content-Type": "application/json" }, ...opts });
        const body = await r.json().catch(() => ({}));
        if (!r.ok) throw new Error(typeof body.detail === "string" ? body.detail : (body.detail ? JSON.stringify(body.detail) : r.statusText));
        return body;
    }
    const post = (path, data) => api(path, { method: "POST", body: JSON.stringify(data ?? {}) });

    function render() {
        const s = status;
        if (!s) return;
        // Every value from the server is escaped here; only the markup built around it is markup.
        const rows = [
            ["tools dir", esc(s.tools_dir)],
            ["arduino-cli", s.arduino_cli_ok ? `<b class="ok">✓ ${esc(s.arduino_cli_version)}</b> ${esc(s.arduino_cli_path)}` : '<b class="bad">✗ not installed</b>'],
            ["config", esc(s.config_file || "–")],
            ["esptool", s.esptool_ok ? `<b class="ok">✓ ${esc(s.esptool_version)}</b> ${esc(s.esptool_path)}` : '<span class="warn">• not found (optional)</span>'],
        ];
        $(".tc-status").innerHTML = rows.map(([k, v]) => `<div><span class="meta">${k}:</span> ${v}</div>`).join("")
            + (s.problems || []).map((p) => `<div class="warn">! ${esc(p)}</div>`).join("");
        $(".install-btn").textContent = s.arduino_cli_ok ? "Update arduino-cli" : "Install arduino-cli";
        const installed = new Map((s.cores || []).map((c) => [c.id, c]));
        const suggested = s.suggested_cores || [];
        const items = suggested.map(({ id, label }) => {
            const c = installed.get(id);
            return `<li data-id="${esc(id)}"><span>${esc(label)}</span> <span class="meta">${esc(id)}</span><span class="grow"></span>`
                + (c && c.installed ? `<span class="ok meta">✓ ${esc(c.installed)}</span>` : `<button type="button" class="core-install" data-id="${esc(id)}">Install</button>`) + "</li>";
        });
        for (const c of installed.values()) {
            if (!suggested.some((x) => x.id === c.id) && c.installed) items.push(`<li><span>${esc(c.name || c.id)}</span> <span class="meta">${esc(c.id)}</span><span class="grow"></span><span class="ok meta">✓ ${esc(c.installed)}</span></li>`);
        }
        $(".tc-cores").innerHTML = items.join("") || '<li class="empty">–</li>';
        enable();
    }
    // What can be pressed: nothing while a task runs; cores and libraries only
    // with arduino-cli installed.
    function enable() {
        const busy = !!(tasks && tasks.running()) || !!(status && status.active_task && status.active_task.status === "running");
        const ok = !!(status && status.arduino_cli_ok);
        $(".install-btn").disabled = busy;
        $(".lib-btn").disabled = busy || !ok;
        for (const b of root.querySelectorAll(".core-install")) b.disabled = busy || !ok;
    }

    async function load() {
        try { status = await api("/firmware/status"); }
        catch (e) { $(".tc-status").innerHTML = `<span class="bad">${esc(e.message)}</span>`; return null; }
        if (!alive) return status;
        render();
        if (onStatus) onStatus(status);
        return status;
    }

    function run(fn) {
        if (!tasks) return null;
        const ending = tasks.start(fn);
        enable();
        return ending;
    }
    const install = () => run(() => post("/firmware/install", { force: $(".install-force").checked }));
    const core = (id) => run(() => post("/firmware/cores/install", { id }));
    // The names typed in the box, comma-separated; none typed, the box is where the cursor goes.
    function libraries() {
        const names = $(".lib-input").value.split(",").map((s) => s.trim()).filter(Boolean);
        if (!names.length) {
            $(".lib-input").focus();
            if (say) say("Libraries: type a library's name in the Bench's box first", "error");
            return null;
        }
        return run(() => post("/firmware/libraries/install", { names }));
    }

    $(".install-btn").onclick = () => install();
    $(".lib-btn").onclick = () => libraries();
    const coresEl = $(".tc-cores");
    coresEl.addEventListener("click", (ev) => {
        const btn = ev.target.closest(".core-install");
        if (btn) core(btn.dataset.id);
    });
    const libEl = $(".lib-input");
    libEl.addEventListener("keydown", (ev) => { if (ev.key === "Enter") libraries(); });

    return {
        load, install, core, libraries, enable,
        status: () => status,
        destroy() { alive = false; root.innerHTML = ""; },
    };
}
