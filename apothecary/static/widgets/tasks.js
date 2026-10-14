/* Tasks: the running toolchain task, its output, Cancel, and the recent ones.
 *
 * Every firmware route that runs an engine -- an install, a core, a library, a
 * compile, an upload, a raw flash -- answers at once with a task, and its output
 * is asked for again until it ends (GET /firmware/tasks/{id}?since=N). This is
 * the one view of that, mounted by the Bench (with the recent tasks under it) and
 * by a board's Machine (its Flashing card's task alone).
 *
 * mountTasks(root, { base, history, say, onStart, onEnd }) renders into `root` and returns
 * { start(fn, tasks), show(task), attach(id), list(), current(), cancel(), destroy() }.
 * start(fn) calls fn() -- a request that answers with a task -- and follows the
 * task it answers with; the promise it returns settles with the task as it ended
 * (or null when it could not start, said through `say`). `onStart(task)` is
 * told of a task started here, `onEnd(task)` of every task that ends while it
 * is followed here. A task of another runner -- the slicer's, whose tasks are
 * GET /slicer/tasks/{id} -- is followed, and cancelled, at the route `tasks`
 * names when it is started; the recent tasks are the firmware's.
 */

import { esc } from "/static/board_text.js";

const POLL_MS = 500;

const MARKUP = `
<div class="bench-task">
    <div class="row"><span class="k">Task</span><span class="grow"></span>
        <button type="button" class="cancel-btn" hidden title="Stop the running task (its process is terminated)">Cancel</button></div>
    <div class="task-title empty">No task running.</div>
    <pre class="task-log"></pre>
</div>`;

const HISTORY = `
<div class="bench-history">
    <div class="k">Recent tasks</div>
    <ul class="task-history"><li class="empty">–</li></ul>
</div>`;

const mark = (status) => (status === "succeeded" ? ["ok", "✓"] : status === "running" ? ["warn", "…"] : ["bad", "✗"]);

export function mountTasks(root, { base = "", history = true, say = null, onStart = null, onEnd = null } = {}) {
    root.innerHTML = MARKUP + (history ? HISTORY : "");
    const $ = (sel) => root.querySelector(sel);
    const state = { task: null, next: 0, timer: null, waiters: [], alive: true, route: "/firmware/tasks" };

    async function api(path, opts = {}) {
        const r = await fetch(base + path, { headers: { "Content-Type": "application/json" }, ...opts });
        const body = await r.json().catch(() => ({}));
        if (!r.ok) throw new Error(typeof body.detail === "string" ? body.detail : (body.detail ? JSON.stringify(body.detail) : r.statusText));
        return body;
    }

    function append(lines) {
        const log = $(".task-log");
        const atBottom = log.scrollHeight - log.scrollTop - log.clientHeight < 40;
        for (const line of lines) {
            const span = document.createElement("span");
            span.textContent = line + "\n";
            if (/^\$ /.test(line)) span.className = "cmd";
            else if (/error|ERROR|exit [1-9]|failed/i.test(line)) span.className = "err";
            log.appendChild(span);
        }
        if (atBottom) log.scrollTop = log.scrollHeight;
    }

    // A task drawn: fresh, its log starts over; else what it said since is added.
    function show(task, fresh = false) {
        if (!state.alive) return;
        if (fresh || !state.task || state.task.id !== task.id) { $(".task-log").textContent = ""; state.next = 0; }
        state.task = task;
        const [cls] = mark(task.status);
        $(".task-title").className = "task-title";
        $(".task-title").innerHTML = `<span class="${cls}">${esc(task.status)}</span> — ${esc(task.title)}`;
        $(".cancel-btn").hidden = task.status !== "running";
        append(task.lines || []);
        state.next = task.next;
        clearTimeout(state.timer); state.timer = null;
        if (task.status === "running") state.timer = setTimeout(poll, POLL_MS);
        else ended(task);
    }
    function ended(task) {
        const waiters = state.waiters.filter((w) => w.id === task.id);
        state.waiters = state.waiters.filter((w) => w.id !== task.id);
        for (const w of waiters) w.done(task);
        if (history) list();
        if (onEnd) onEnd(task);
    }
    async function poll() {
        if (!state.task || !state.alive) return;
        try { show(await api(`${state.route}/${state.task.id}?since=${state.next}`)); }
        catch (e) { append([`poll error: ${e.message}`]); state.timer = setTimeout(poll, POLL_MS * 4); }
    }

    // fn() starts a task; it is followed here until it ends.
    async function start(fn, tasks = "/firmware/tasks") {
        let task;
        try { task = await fn(); }
        catch (e) { if (say) say(e.message, "error"); return null; }
        state.route = tasks;
        const ending = new Promise((done) => state.waiters.push({ id: task.id, done }));
        show(task, true);
        if (history) list();
        if (onStart) onStart(task);
        return ending;
    }
    // A task started elsewhere (another tab, another mount): followed here too.
    async function attach(id) {
        if (state.task && state.task.id === id && state.task.status === "running") return;
        state.route = "/firmware/tasks";
        try { show(await api(`/firmware/tasks/${encodeURIComponent(id)}`), true); } catch (e) { /* gone */ }
    }

    async function list() {
        if (!history) return [];
        let tasks = [];
        try { tasks = await api("/firmware/tasks"); } catch (e) { tasks = []; }
        if (!state.alive) return tasks;
        $(".task-history").innerHTML = tasks.length
            ? tasks.map((t) => {
                const [cls, sign] = mark(t.status);
                return `<li data-id="${esc(t.id)}" title="Show this task's output"><span class="${cls}">${sign}</span> <span>${esc(t.title)}</span><span class="grow"></span><span class="meta">${esc(new Date(t.started).toLocaleTimeString())}</span></li>`;
            }).join("")
            : '<li class="empty">–</li>';
        return tasks;
    }

    async function cancel() {
        if (!state.task || state.task.status !== "running") { if (say) say("no task is running", "error"); return false; }
        try { show(await api(`${state.route}/${state.task.id}/cancel`, { method: "POST" })); return true; }
        catch (e) { if (say) say(`cancel: ${e.message}`, "error"); return false; }
    }

    $(".cancel-btn").onclick = () => cancel();
    if (history) {
        const historyEl = $(".task-history");
        historyEl.addEventListener("click", (ev) => {
            const li = ev.target.closest("li[data-id]");
            if (li) attach(li.dataset.id);
        });
    }

    return {
        start, show, attach, list, cancel,
        current: () => state.task,
        running: () => !!(state.task && state.task.status === "running"),
        destroy() { state.alive = false; clearTimeout(state.timer); root.innerHTML = ""; },
    };
}
