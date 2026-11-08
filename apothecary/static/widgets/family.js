/* Family: who the family is, and what the hub delivered. The Members and Deliveries
 * windows of the Family system (apothecary/systems.py), read from GET /family/ and GET
 * /family/beside, asked again every LOOK_MS while a window is in front.
 *
 * Members: each member, how it is reached, its state where the hub started it, and its
 * door -- a member hosted here to the window of the node its next step names, one beside
 * the hub to its own page in a new tab, a pull member, read by a page, nowhere. Where a
 * door leads is the Procedure window's to say (its doorOf); with that window not yet
 * open, a name has no door. Deliveries: the hub's audit, newest first, each delivery's
 * step, member, status, milliseconds and the instance that took it.
 *
 * mountFamily({ members, deliveries }, { base, doorOf, open }) fills the two elements.
 */

const LOOK_MS = 2000;

const REACHED = { local: "hosted here", push: "beside the hub", pull: "read by a page" };

export function mountFamily({ members, deliveries }, { base = "", doorOf = () => null, open = null } = {}) {
    members.innerHTML = '<div class="family-ui"><div class="family-members"><span class="empty">asking…</span></div></div>';
    deliveries.innerHTML = '<div class="family-ui"><ol class="family-deliveries"><li class="empty">asking…</li></ol></div>';
    const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
    let family = {}, started = {}, last = [], drawn = "", timer = null;

    async function api(path) {
        const r = await fetch(base + path);
        const body = await r.json().catch(() => ({}));
        if (!r.ok) throw new Error(typeof body.detail === "string" ? body.detail : r.statusText);
        return body;
    }

    function renderMembers() {
        const rows = Object.entries(family).sort(([a], [b]) => a.localeCompare(b));
        members.querySelector(".family-members").innerHTML = rows.map(([who, how]) => {
            const state = started[who]?.state;
            const dot = how.via === "pull" ? "off" : state && state !== "up" ? "warn" : "ok";
            const words = state && state !== "up" ? ` (${state})` : "";
            const reached = state ? `${REACHED[how.via]}, started by the hub: ${state}, restarted ${started[who].restarts} times` : REACHED[how.via] || how.via;
            const door = doorOf(who, how);
            const title = door ? `${reached}; ${door.title}` : reached;
            const inner = `<span class="dot ${dot}"></span>${esc(who)}${esc(words)}`;
            if (!door) return `<span class="family-member" title="${esc(title)}">${inner}</span>`;
            return `<button type="button" class="family-member" data-member="${esc(who)}" title="${esc(title)}">${inner}</button>`;
        }).join("");
    }

    function renderDeliveries() {
        const rows = [...last].reverse();
        deliveries.querySelector(".family-deliveries").innerHTML = rows.length ? rows.map((d) => {
            const answered = d.status === null || d.status === undefined ? (d.done ? "no answer" : "not read yet") : `answered ${d.status}`;
            const ms = d.ms === null || d.ms === undefined ? "" : ` in ${d.ms} ms`;
            const error = d.error ? ` · <span class="bad">${esc(d.error)}</span>` : "";
            const instance = d.instance ? ` · ${esc(d.instance)}` : "";
            const cue = d.cue && typeof d.cue === "object" ? `step ${d.cue.number ?? ""} ${d.cue.name ?? ""}`.trim() : String(d.cue ?? "");
            return `<li class="family-delivery"><span class="cue">${esc(cue)}</span> <span class="who">${esc(d.member)}</span> ${esc(answered)}${esc(ms)}${instance}${error}</li>`;
        }).join("") : '<li class="empty">nothing delivered yet</li>';
    }

    // Drawn again only when what it says changed, so a door pressed is not drawn away.
    async function load() {
        try {
            [{ members: family, last }, started] = await Promise.all([api("/family/"), api("/family/beside")]);
        } catch (err) {
            members.querySelector(".family-members").textContent = `Family: ${err.message}`;
            return;
        }
        const doors = Object.entries(family).map(([who, how]) => doorOf(who, how)?.node || doorOf(who, how)?.url || null);
        const words = JSON.stringify([family, started, last, doors]);
        if (words === drawn) return;
        drawn = words;
        renderMembers();
        renderDeliveries();
    }

    function through(who) {
        const door = doorOf(who, family[who] || {});
        if (!door) return;
        if (door.url) window.open(door.url, "_blank", "noopener");
        else if (open) open(door.node);
    }

    members.addEventListener("click", (event) => {
        const pressed = event.target.closest("button.family-member");
        if (pressed) through(pressed.dataset.member);
    });

    // A window of the system is in front: asked again until none is.
    const inFront = () => members.offsetParent !== null || deliveries.offsetParent !== null;
    timer = setInterval(() => { if (inFront()) load(); }, LOOK_MS);

    return { load, redraw: load, through, close: () => clearInterval(timer) };
}
