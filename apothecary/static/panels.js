/* Panels: windows in front of the world.
 *
 * A panel is a titled box the world's page registers once -- the Contents
 * tree, the Selected piece, Jobs -- and a person opens, closes, collapses,
 * drags free or docks back. Docked panels stack in a rail on the right or
 * the left; a rail can never be wider than a third of the page, so the
 * world is never pushed off the screen. A free panel is dragged by its
 * title bar and clamped to the page. A tethered panel follows an anchor
 * (anchors.js) and draws a leader to it; its position is set every frame
 * by update(). What a person did to the panels is remembered per browser.
 *
 * The chrome is the module's: every listener it installs is on the
 * elements it makes, except the pointer moves that finish a drag, which
 * go on the window while a drag is in progress and come off after. The
 * census's test on this module holds it to that.
 */

const RAIL_MAX_FRACTION = 1 / 3;

export function mountPanels({ container, overlay, storageKey = "apothecary.panels" } = {}) {
    overlay = overlay || container;  // where free and tethered panels float: over the world
    const panels = new Map();
    const rails = {};
    for (const side of ["left", "right"]) {
        const rail = document.createElement("div");
        rail.className = `panel-rail panel-rail-${side}`;
        rail.dataset.side = side;
        rails[side] = rail;
    }
    const free = document.createElement("div");
    free.className = "panel-free-layer";
    const leaders = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    leaders.setAttribute("class", "panel-leaders");
    free.appendChild(leaders);
    const tabs = document.createElement("div");
    tabs.className = "panel-tabs";
    container.prepend(rails.left);
    container.appendChild(rails.right);
    overlay.appendChild(free);
    overlay.appendChild(tabs);

    let remembered = {};
    try { remembered = JSON.parse(localStorage.getItem(storageKey) || "{}") || {}; } catch (e) { remembered = {}; }
    function remember() {
        const out = {};
        for (const [id, p] of panels) out[id] = { open: p.open, collapsed: p.collapsed, where: p.where, x: p.x, y: p.y };
        try { localStorage.setItem(storageKey, JSON.stringify(out)); } catch (e) { /* private window, blocked storage: the panels still work */ }
    }

    function esc(v) { return String(v ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c])); }

    function place(p) {
        // Where the panel's element lives: a rail, the free layer, or nowhere while closed.
        if (!p.open) { p.el.remove(); renderTabs(); return; }
        if (typeof p.where === "object" && p.where && p.where.tether) { free.appendChild(p.el); p.el.classList.add("tethered"); }
        else if (p.where === "free") { free.appendChild(p.el); p.el.classList.remove("tethered"); p.el.style.left = `${p.x}px`; p.el.style.top = `${p.y}px`; }
        else { rails[p.where === "left" ? "left" : "right"].appendChild(p.el); p.el.classList.remove("tethered"); p.el.style.left = ""; p.el.style.top = ""; }
        p.el.classList.toggle("free", p.where === "free" || (typeof p.where === "object"));
        p.el.querySelector(".panel-title").title = p.tether ? "Drag to let go of the machine and float freely" : (p.where === "free" ? "Drag to move" : "");
        p.el.classList.toggle("collapsed", p.collapsed);
        p.el.querySelector(".panel-collapse").textContent = p.collapsed ? "▸" : "▾";
        p.el.querySelector(".panel-float").textContent = p.where === "free" ? "⇥" : "⧉";
        p.el.querySelector(".panel-float").title = p.where === "free" ? "Dock this panel" : "Float this panel";
        renderTabs();
    }

    function renderTabs() {
        // Closed panels keep a tab, so nothing a person closed is lost.
        const closed = [...panels.values()].filter((p) => !p.open);
        tabs.innerHTML = closed.map((p) => `<button type="button" class="panel-tab" data-panel="${esc(p.id)}" title="Open ${esc(p.title)}">${esc(p.title)}</button>`).join("");
        tabs.hidden = closed.length === 0;
    }
    tabs.addEventListener("click", (ev) => {
        const b = ev.target.closest(".panel-tab");
        if (b) api.open(b.dataset.panel);
    });

    function clampFree(p) {
        const w = overlay.clientWidth, h = overlay.clientHeight;
        const pw = p.el.offsetWidth || 320, ph = p.el.offsetHeight || 40;
        p.x = Math.max(0, Math.min(w - Math.min(pw, w), p.x));
        p.y = Math.max(0, Math.min(h - Math.min(ph, 40), p.y));
    }

    function startDrag(p, ev) {
        if (p.tether) {
            // Dragging a tethered panel lets go of the tether: it becomes a free panel where it was.
            p.tether = null; p.where = "free";
            if (p.leader) { p.leader.remove(); p.leader = null; }
            place(p);
        }
        if (p.where !== "free") return;
        ev.preventDefault();
        const startX = ev.clientX, startY = ev.clientY, fromX = p.x, fromY = p.y;
        const move = (e) => { p.x = fromX + (e.clientX - startX); p.y = fromY + (e.clientY - startY); clampFree(p); p.el.style.left = `${p.x}px`; p.el.style.top = `${p.y}px`; };
        const up = () => { window.removeEventListener("pointermove", move); window.removeEventListener("pointerup", up); remember(); };
        window.addEventListener("pointermove", move);
        window.addEventListener("pointerup", up);
    }

    function build(p) {
        const el = document.createElement("section");
        el.className = "panel";
        el.dataset.panel = p.id;
        el.innerHTML = `<div class="panel-title"><button type="button" class="panel-collapse" title="Collapse or expand">▾</button><span class="panel-name">${esc(p.title)}</span><span class="panel-spacer"></span><button type="button" class="panel-float" title="Float this panel">⧉</button><button type="button" class="panel-close" title="Close (reopen from its tab, or the ring's Panels)">✕</button></div>`;
        const body = document.createElement("div");
        body.className = "panel-body-slot";
        el.appendChild(body);
        el.querySelector(".panel-collapse").addEventListener("click", () => api.collapse(p.id, !p.collapsed));
        el.querySelector(".panel-close").addEventListener("click", () => api.close(p.id));
        el.querySelector(".panel-float").addEventListener("click", () => (p.where === "free" ? api.dock(p.id, p.home) : api.float(p.id)));
        el.querySelector(".panel-title").addEventListener("pointerdown", (ev) => { if (!ev.target.closest("button")) startDrag(p, ev); });
        p.el = el;
        p.slot = body;
    }

    function leaderFor(p) {
        if (!p.leader) {
            p.leader = document.createElementNS("http://www.w3.org/2000/svg", "line");
            p.leader.setAttribute("class", "panel-leader");
            leaders.appendChild(p.leader);
        }
        return p.leader;
    }

    const api = {
        rails, free, tabs,
        /* Register a panel. `body` is an element the panel adopts (moved into
         * it) or a function given the slot to fill. `where` is "right",
         * "left" or "free"; `open` and `collapsed` are the defaults a browser
         * that has not seen the panel starts from. */
        register(id, { title, body, where = "right", open = true, collapsed = false, x = 40, y = 40 } = {}) {
            if (panels.has(id)) this.unregister(id);
            const p = { id, title: title || id, where, home: where === "free" ? "right" : where, open, collapsed, x, y, el: null, slot: null, leader: null, tether: null };
            const had = remembered[id];
            if (had) {
                if (typeof had.open === "boolean") p.open = had.open;
                if (typeof had.collapsed === "boolean") p.collapsed = had.collapsed;
                if (had.where === "left" || had.where === "right" || had.where === "free") p.where = had.where;
                if (typeof had.x === "number") p.x = had.x;
                if (typeof had.y === "number") p.y = had.y;
            }
            build(p);
            if (typeof body === "function") body(p.slot);
            else if (body) p.slot.appendChild(body);
            panels.set(id, p);
            place(p);
            return p.el;
        },
        unregister(id) {
            const p = panels.get(id);
            if (!p) return;
            p.el.remove();
            if (p.leader) p.leader.remove();
            panels.delete(id);
            renderTabs();
        },
        open(id) { const p = panels.get(id); if (!p) return false; p.open = true; place(p); remember(); return true; },
        close(id) { const p = panels.get(id); if (!p) return false; p.open = false; place(p); remember(); return true; },
        toggle(id) { const p = panels.get(id); if (!p) return false; return p.open ? this.close(id) : this.open(id); },
        collapse(id, collapsed = true) { const p = panels.get(id); if (!p) return false; p.collapsed = collapsed; place(p); remember(); return true; },
        float(id) {
            const p = panels.get(id);
            if (!p) return false;
            const rect = p.el.getBoundingClientRect(), base = overlay.getBoundingClientRect();
            p.where = "free"; p.open = true;
            p.x = Math.max(0, rect.left - base.left - 24); p.y = Math.max(0, rect.top - base.top + 8);
            place(p); clampFree(p); p.el.style.left = `${p.x}px`; p.el.style.top = `${p.y}px`; remember();
            return true;
        },
        dock(id, side) {
            const p = panels.get(id);
            if (!p) return false;
            p.where = side === "left" ? "left" : "right"; p.home = p.where; p.open = true;
            if (p.leader) { p.leader.remove(); p.leader = null; }
            p.tether = null;
            place(p); remember();
            return true;
        },
        /* Tie a panel to an anchor: update() places it beside the anchor's
         * point every frame and draws a leader. */
        tether(id, anchorKey) {
            const p = panels.get(id);
            if (!p) return false;
            p.tether = anchorKey; p.where = { tether: anchorKey }; p.open = true;
            place(p);
            return true;
        },
        /* Called each frame with a function answering an anchor's canvas position. */
        update(anchorAt) {
            for (const p of panels.values()) {
                if (!p.open || !p.tether) continue;
                const at = anchorAt(p.tether);
                const line = leaderFor(p);
                if (!at) { p.el.hidden = true; line.setAttribute("visibility", "hidden"); continue; }
                p.el.hidden = false;
                const w = overlay.clientWidth, h = overlay.clientHeight;
                const pw = p.el.offsetWidth || 320, ph = p.el.offsetHeight || 200;
                // Beside the anchor: to its right when there is room, else to its left; when
                // neither fits, on the far side of the page from it, so as little of what it
                // stands over is covered as can be. Below its point.
                const fitsRight = at.x + 24 + pw <= w, fitsLeft = at.x - 24 - pw >= 0;
                const x = fitsRight ? at.x + 24 : (fitsLeft ? at.x - 24 - pw : (at.x > w / 2 ? 0 : Math.max(0, w - pw)));
                const y = Math.max(0, Math.min(h - ph, at.y - 40));
                p.x = x; p.y = y;
                p.el.style.left = `${x}px`; p.el.style.top = `${y}px`;
                line.setAttribute("visibility", "visible");
                line.setAttribute("x1", at.x); line.setAttribute("y1", at.y);
                line.setAttribute("x2", x + (x > at.x ? 0 : pw)); line.setAttribute("y2", y + 14);
            }
        },
        isOpen(id) { const p = panels.get(id); return !!(p && p.open); },
        state(id) { const p = panels.get(id); return p ? { id, title: p.title, open: p.open, collapsed: p.collapsed, where: p.where, x: p.x, y: p.y } : null; },
        list() { return [...panels.keys()].map((id) => this.state(id)); },
        element(id) { const p = panels.get(id); return p ? p.el : null; },
        railWidthLimit() { return Math.floor(container.clientWidth * RAIL_MAX_FRACTION); },
        destroy() {
            for (const id of [...panels.keys()]) this.unregister(id);
            rails.left.remove(); rails.right.remove(); free.remove(); tabs.remove();
        },
    };
    return api;
}
