/* Panels: windows in front of the world.
 *
 * A panel is a titled box the world's page registers once -- Site, Selected,
 * Pictures, Jobs, a machine and its log -- and a person opens, closes,
 * collapses, drags free or docks back. Docked panels live in one rail, on the
 * right of the world unless a person moved it; the other side stays world. In
 * the rail, the panels registered to stack (Site and Selected) are stacked at
 * its top, each collapsible, and below them one tab strip holds every other
 * docked panel, one shown at a time: a tab pressed shows its panel, pressed
 * again folds it away. The rail has a width a person drags (never more than
 * half the page, so the world keeps the other half), it hides and shows on
 * the tilde key, and it moves -- press its swap button, or drag its grip
 * across the page -- to the other side. A docked panel's body has a height a
 * person drags; a free panel is dragged by its title bar, clamped to the page,
 * and resized from its corner. A tethered panel follows an anchor (anchors.js)
 * and draws a leader to it; its position is set every frame by update(), and
 * docked it joins the tab strip. What a person did to the panels and the rail
 * is remembered per browser; a remembered panel the page no longer registers
 * is ignored, and forgotten the next time anything is remembered, and a layout
 * remembered from before the one rail (a left and a right rail) is ignored
 * whole.
 *
 * The chrome is the module's: every listener it installs is on the elements
 * it makes, except the pointer moves that finish a drag, which go on the
 * window while a drag is in progress and come off after, and the tilde key,
 * which is on the window so it works wherever the pointer is.
 */

const RAIL_MAX_FRACTION = 1 / 2;
const RAIL_MIN_PX = 220;
const PANEL_MIN_PX = 60;
const TILDE_KEYS = new Set(["`", "~"]);
const SIDES = new Set(["left", "right"]);
const STRIP_ORDER = 1000; // the tab strip, and the shown tab under it, below every stacked panel

export function mountPanels({ container, overlay, storageKey = "apothecary.panels" } = {}) {
    overlay = overlay || container;  // where free and tethered panels float: over the world
    const panels = new Map();
    // The one rail: which side it is on, the width a person dragged it to, whether
    // it is hidden, and which tab of its strip is shown (null: none).
    const rail = { side: "right", width: null, hidden: false, tab: null };
    const railEl = document.createElement("div");
    railEl.className = "panel-rail";
    // Its own head: a grip to drag it across, a swap and a hide.
    railEl.innerHTML = `<div class="panel-rail-head"><span class="panel-rail-grip" title="Drag across the page to move the rail to the other side">⋮⋮</span><span class="panel-rail-name">Panels</span><span class="panel-spacer"></span><button type="button" class="panel-rail-swap" title="Move the rail to the other side">⇄</button><button type="button" class="panel-rail-hide" title="Hide the rail (tilde shows it again)">✕</button></div><div class="panel-rail-body"><div class="panel-tabstrip" role="tablist"></div><div class="panel-tabbody"></div></div><div class="panel-rail-resizer" title="Drag to resize"></div>`;
    railEl.querySelector(".panel-rail-swap").addEventListener("click", () => api.moveRail(rail.side === "left" ? "right" : "left"));
    railEl.querySelector(".panel-rail-hide").addEventListener("click", () => api.hideRail(true));
    railEl.querySelector(".panel-rail-grip").addEventListener("pointerdown", (ev) => startRailDrag(ev));
    railEl.querySelector(".panel-rail-resizer").addEventListener("pointerdown", (ev) => startRailResize(ev));
    const railBody = railEl.querySelector(".panel-rail-body");
    const strip = railEl.querySelector(".panel-tabstrip");
    const tabBody = railEl.querySelector(".panel-tabbody");
    strip.style.order = String(STRIP_ORDER);
    tabBody.style.order = String(STRIP_ORDER + 1);
    const free = document.createElement("div");
    free.className = "panel-free-layer";
    const leaders = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    leaders.setAttribute("class", "panel-leaders");
    free.appendChild(leaders);
    const tabs = document.createElement("div");
    tabs.className = "panel-tabs";
    overlay.appendChild(free);
    overlay.appendChild(tabs);

    let remembered = {};
    try { remembered = JSON.parse(localStorage.getItem(storageKey) || "{}") || {}; } catch (e) { remembered = {}; }
    // A layout from before the one rail names a left and a right rail and panels
    // docked to either: none of it says where anything goes now, so all of it is
    // ignored, and the panels start as they would in a browser that saw none.
    if (typeof remembered !== "object" || !remembered._rail || typeof remembered._rail !== "object") remembered = {};
    if (remembered._rail) {
        const had = remembered._rail;
        if (SIDES.has(had.side)) rail.side = had.side;
        if (typeof had.width === "number" && had.width > 0) rail.width = had.width;
        if (typeof had.hidden === "boolean") rail.hidden = had.hidden;
        if (typeof had.tab === "string") rail.tab = had.tab;
    }
    function remember() {
        const out = { _rail: { ...rail } };
        for (const [id, p] of panels) out[id] = { open: p.open, collapsed: p.collapsed, where: p.where === "free" ? "free" : "rail", x: p.x, y: p.y, height: p.height };
        try { localStorage.setItem(storageKey, JSON.stringify(out)); } catch (e) { /* private window, blocked storage: the panels still work */ }
    }

    const docked = (p) => p.where === "rail";
    const tethered = (p) => typeof p.where === "object" && p.where !== null;
    const inStrip = (p) => p.open && p.offered && docked(p) && p.zone === "tabs";
    // Whether a panel's body is in front of a person, the rail's hiding aside.
    function visible(p) {
        if (!p.open || !p.offered) return false;
        if (docked(p) && p.zone === "tabs") return rail.tab === p.id;
        return true;
    }

    function railMax() { return Math.floor(container.clientWidth * RAIL_MAX_FRACTION); }
    function layoutRail() {
        const any = [...panels.values()].some((p) => p.open && p.offered && docked(p));
        railEl.hidden = rail.hidden || !any;
        railEl.dataset.side = rail.side;
        railEl.classList.toggle("panel-rail-right", rail.side === "right");
        railEl.classList.toggle("panel-rail-left", rail.side === "left");
        // On the left it comes before the world; on the right, after it.
        if (rail.side === "left" && container.firstElementChild !== railEl) container.prepend(railEl);
        if (rail.side === "right" && container.lastElementChild !== railEl) container.appendChild(railEl);
        railEl.style.width = rail.width ? `${Math.max(RAIL_MIN_PX, Math.min(railMax(), rail.width))}px` : "";
    }
    function startRailResize(ev) {
        ev.preventDefault();
        const startX = ev.clientX, from = railEl.offsetWidth;
        const move = (e) => {
            const delta = rail.side === "right" ? startX - e.clientX : e.clientX - startX;
            rail.width = Math.max(RAIL_MIN_PX, Math.min(railMax(), from + delta));
            layoutRail();
        };
        const up = () => { window.removeEventListener("pointermove", move); window.removeEventListener("pointerup", up); remember(); };
        window.addEventListener("pointermove", move);
        window.addEventListener("pointerup", up);
    }
    function startRailDrag(ev) {
        // The rail follows the pointer across the page: past the middle it is on the other side.
        ev.preventDefault();
        const move = (e) => {
            const rect = container.getBoundingClientRect();
            const wanted = e.clientX < rect.left + rect.width / 2 ? "left" : "right";
            if (wanted !== rail.side) api.moveRail(wanted);
        };
        const up = () => { window.removeEventListener("pointermove", move); window.removeEventListener("pointerup", up); remember(); };
        window.addEventListener("pointermove", move);
        window.addEventListener("pointerup", up);
    }
    // The tilde: the rail hides and shows, as a console does -- unless a person is typing.
    const onKey = (ev) => {
        if (!TILDE_KEYS.has(ev.key) || ev.ctrlKey || ev.metaKey || ev.altKey) return;
        const t = ev.target;
        if (t && (t.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName))) return;
        ev.preventDefault();
        api.hideRail(!rail.hidden);
    };
    window.addEventListener("keydown", onKey);

    function esc(v) { return String(v ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c])); }

    // In the order the page registered them, whatever order they were docked in.
    function insertInOrder(parent, p) {
        const after = [...parent.children].find((el) => el.classList.contains("panel") && Number(el.dataset.order) > p.order);
        if (p.el.parentElement === parent && p.el.nextElementSibling === (after || null)) return;
        parent.insertBefore(p.el, after || null);
    }

    function place(p) {
        // Where the panel's element lives: the rail's stack, the rail's tab body,
        // the free layer, or nowhere while closed.
        if (!p.open) { p.el.remove(); relayout(); return; }
        if (tethered(p)) { free.appendChild(p.el); p.el.classList.add("tethered"); }
        else if (p.where === "free") { free.appendChild(p.el); p.el.classList.remove("tethered"); p.el.style.left = `${p.x}px`; p.el.style.top = `${p.y}px`; }
        else { insertInOrder(p.zone === "stack" ? railBody : tabBody, p); p.el.classList.remove("tethered"); p.el.style.left = ""; p.el.style.top = ""; }
        // Filled the first time its body is in front of a person.
        if (p.mount && visible(p)) { const mount = p.mount; p.mount = null; mount(p.slot); }
        p.slot.style.height = docked(p) && p.height ? `${p.height}px` : "";
        p.el.classList.toggle("sized", docked(p) && !!p.height);  // a height a person dragged it to
        p.el.querySelector(".panel-resizer").hidden = !docked(p);
        p.el.classList.toggle("free", !docked(p));
        p.el.querySelector(".panel-title").title = p.tether ? "Drag to let go of the machine and float freely" : (p.where === "free" ? "Drag to move" : "");
        p.el.classList.toggle("collapsed", p.collapsed && !(docked(p) && p.zone === "tabs"));
        p.el.querySelector(".panel-collapse").textContent = p.collapsed ? "▸" : "▾";
        p.el.querySelector(".panel-float").textContent = docked(p) ? "⧉" : "⇥";
        p.el.querySelector(".panel-float").title = docked(p) ? "Float this panel" : "Dock this panel in the rail";
        relayout();
    }
    // What follows from where every panel is: which shows, the tab strip, the
    // closed panels' tabs, the rail.
    function relayout() {
        for (const p of panels.values()) {
            if (!p.open) continue;
            // A tethered panel's showing is update()'s, by whether its anchor is in view.
            if (!tethered(p)) p.el.hidden = !visible(p);
        }
        renderStrip();
        renderTabs();
        layoutRail();
    }

    function renderStrip() {
        const here = [...panels.values()].filter(inStrip).sort((a, b) => a.order - b.order);
        strip.innerHTML = here.map((p) => {
            const on = rail.tab === p.id;
            return `<div class="rail-tab${on ? " active" : ""}" data-panel="${esc(p.id)}" role="presentation">`
                + `<button type="button" class="rail-tab-name" role="tab" aria-selected="${on}" title="${on ? `Fold ${esc(p.title)} away` : `Show ${esc(p.title)}`}">${esc(p.title)}</button>`
                + `<button type="button" class="rail-tab-float" title="Float this panel"${on ? "" : " hidden"}>⧉</button>`
                + `<button type="button" class="rail-tab-close" title="Close (reopen from its tab, or the ring's Panels)"${on ? "" : " hidden"}>✕</button></div>`;
        }).join("");
        strip.hidden = here.length === 0;
        tabBody.hidden = !here.some((p) => p.id === rail.tab);
    }
    strip.addEventListener("click", (ev) => {
        const tab = ev.target.closest(".rail-tab");
        if (!tab) return;
        const id = tab.dataset.panel;
        if (ev.target.closest(".rail-tab-close")) api.close(id);
        else if (ev.target.closest(".rail-tab-float")) api.float(id);
        else api.collapse(id, rail.tab === id);
    });

    function renderTabs() {
        // Closed panels keep a tab, so nothing a person closed is lost; a hidden
        // rail with panels in it keeps one too, since the tilde is not a thing to see.
        const closed = [...panels.values()].filter((p) => !p.open && p.offered);
        const railTab = rail.hidden && [...panels.values()].some((p) => p.open && p.offered && docked(p));
        tabs.innerHTML = (railTab ? `<button type="button" class="panel-tab panel-tab-rail" title="Show the rail (tilde does too)">⋮ Panels ~</button>` : "")
            + closed.map((p) => `<button type="button" class="panel-tab" data-panel="${esc(p.id)}" title="Open ${esc(p.title)}">${esc(p.title)}</button>`).join("");
        tabs.hidden = closed.length === 0 && !railTab;
    }
    tabs.addEventListener("click", (ev) => {
        const b = ev.target.closest(".panel-tab");
        if (!b) return;
        if (b.classList.contains("panel-tab-rail")) api.hideRail(false); else api.open(b.dataset.panel);
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
        el.dataset.order = String(p.order);
        el.style.order = String(p.order);
        el.innerHTML = `<div class="panel-title"><button type="button" class="panel-collapse" title="Collapse or expand">▾</button><span class="panel-name">${esc(p.title)}</span><span class="panel-spacer"></span><button type="button" class="panel-float" title="Float this panel">⧉</button><button type="button" class="panel-close" title="Close (reopen from its tab, or the ring's Panels)">✕</button></div>`;
        const body = document.createElement("div");
        body.className = "panel-body-slot";
        el.appendChild(body);
        // A docked panel's body has a height a person drags from its bottom edge.
        const resizer = document.createElement("div");
        resizer.className = "panel-resizer";
        resizer.title = "Drag to resize";
        resizer.addEventListener("pointerdown", (ev) => startPanelResize(p, ev));
        el.appendChild(resizer);
        el.querySelector(".panel-collapse").addEventListener("click", () => api.collapse(p.id, !p.collapsed));
        el.querySelector(".panel-close").addEventListener("click", () => api.close(p.id));
        el.querySelector(".panel-float").addEventListener("click", () => (docked(p) ? api.float(p.id) : api.dock(p.id)));
        el.querySelector(".panel-title").addEventListener("pointerdown", (ev) => { if (!ev.target.closest("button")) startDrag(p, ev); });
        p.el = el;
        p.slot = body;
    }

    function startPanelResize(p, ev) {
        ev.preventDefault();
        const startY = ev.clientY, from = p.slot.offsetHeight;
        const move = (e) => { p.height = Math.max(PANEL_MIN_PX, from + (e.clientY - startY)); p.slot.style.height = `${p.height}px`; p.el.classList.add("sized"); };
        const up = () => { window.removeEventListener("pointermove", move); window.removeEventListener("pointerup", up); remember(); };
        window.addEventListener("pointermove", move);
        window.addEventListener("pointerup", up);
    }

    function leaderFor(p) {
        if (!p.leader) {
            p.leader = document.createElementNS("http://www.w3.org/2000/svg", "line");
            p.leader.setAttribute("class", "panel-leader");
            leaders.appendChild(p.leader);
        }
        return p.leader;
    }

    // A change to a panel, and what follows from it: placed again and remembered,
    // and a panel whose filled body comes back in front of a person told so
    // (onOpen) -- the first time it shows, filling it is the panel's to do.
    function change(p, fn) {
        const was = visible(p), filled = !p.mount;
        fn();
        place(p);
        remember();
        if (!was && visible(p) && filled && p.onOpen) p.onOpen();
    }
    // A tab shown: the one shown before it folds away, and the rail shows.
    function showTab(p) {
        const before = rail.tab && rail.tab !== p.id ? panels.get(rail.tab) : null;
        rail.tab = p.id;
        if (before) place(before);
    }

    let order = 0;
    const api = {
        rail: railEl, free, tabs,
        /* Register a panel. `body` is an element the panel adopts (moved into
         * it) or a function given the slot to fill the first time the panel
         * shows. `zone` is "stack" (Site, Selected: stacked at the rail's top)
         * or "tabs" (a tab of the strip below them); `where` is "rail" or
         * "free"; `open` and `collapsed` are the defaults a browser that has not
         * seen the panel starts from. `onClose` is called when an open panel is
         * closed or unregistered; `onOpen` when a panel whose body is already
         * filled comes back in front of a person -- opened again, or its tab
         * shown again. */
        register(id, { title, body, zone = "tabs", where = "rail", open = true, collapsed = false, x = 40, y = 40, onClose = null, onOpen = null } = {}) {
            if (panels.has(id)) this.unregister(id);
            const p = { id, title: title || id, zone: zone === "stack" ? "stack" : "tabs", where: where === "free" ? "free" : "rail", order: order++, offered: true, open, collapsed, x, y, height: null, el: null, slot: null, leader: null, tether: null, mount: null, onClose, onOpen };
            const had = remembered[id];
            if (had && typeof had === "object") {
                if (typeof had.open === "boolean") p.open = had.open;
                if (typeof had.collapsed === "boolean") p.collapsed = had.collapsed;
                if (had.where === "rail" || had.where === "free") p.where = had.where;
                if (typeof had.x === "number") p.x = had.x;
                if (typeof had.y === "number") p.y = had.y;
                if (typeof had.height === "number") p.height = had.height;
            }
            build(p);
            if (typeof body === "function") p.mount = body;
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
            relayout();
            if (p.open && p.onClose) p.onClose();
        },
        /* Open a panel: in the rail it shows (its tab shown, the rail shown). */
        open(id) {
            const p = panels.get(id);
            if (!p) return false;
            change(p, () => {
                p.open = true;
                if (docked(p)) { rail.hidden = false; if (p.zone === "tabs") showTab(p); }
            });
            return true;
        },
        close(id) {
            const p = panels.get(id);
            if (!p) return false;
            const was = p.open;
            p.open = false;
            if (rail.tab === id) rail.tab = null;
            place(p); remember();
            if (was && p.onClose) p.onClose();
            return true;
        },
        /* Open and showing, closed; else opened. */
        toggle(id) { const p = panels.get(id); if (!p) return false; return p.open && visible(p) ? this.close(id) : this.open(id); },
        /* Folded away or shown again: a stacked or free panel's body, or a
         * docked tab (folded, no tab is shown). */
        collapse(id, collapsed = true) {
            const p = panels.get(id);
            if (!p) return false;
            change(p, () => {
                if (docked(p) && p.zone === "tabs") {
                    if (collapsed) { if (rail.tab === id) rail.tab = null; } else { p.open = true; showTab(p); }
                } else p.collapsed = collapsed;
            });
            return true;
        },
        float(id) {
            const p = panels.get(id);
            if (!p) return false;
            const rect = p.el.getBoundingClientRect(), base = overlay.getBoundingClientRect();
            change(p, () => {
                p.where = "free"; p.open = true;
                if (rail.tab === id) rail.tab = null;
                if (p.leader) { p.leader.remove(); p.leader = null; }
                p.tether = null;
                p.x = Math.max(0, rect.left - base.left - 24); p.y = Math.max(0, rect.top - base.top + 8);
            });
            clampFree(p); p.el.style.left = `${p.x}px`; p.el.style.top = `${p.y}px`; remember();
            return true;
        },
        /* Docked in the rail: Site and Selected in its stack, any other panel a
         * tab of its strip, shown. A tethered panel lets go of its anchor. */
        dock(id) {
            const p = panels.get(id);
            if (!p) return false;
            change(p, () => {
                p.where = "rail"; p.open = true; rail.hidden = false;
                if (p.leader) { p.leader.remove(); p.leader = null; }
                p.tether = null;
                if (p.zone === "tabs") showTab(p);
            });
            return true;
        },
        /* Tie a panel to an anchor: update() places it beside the anchor's
         * point every frame and draws a leader. */
        tether(id, anchorKey) {
            const p = panels.get(id);
            if (!p) return false;
            change(p, () => {
                if (rail.tab === id) rail.tab = null;
                p.tether = anchorKey; p.where = { tether: anchorKey }; p.open = true;
            });
            return true;
        },
        /* Whether the page offers a panel now (Jobs, on a site with build
         * volumes): one it does not has no tab and no body, and keeps what a
         * person did to it for when it is offered again. */
        offer(id, offered = true) {
            const p = panels.get(id);
            if (!p) return false;
            change(p, () => { p.offered = !!offered; });
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
        /* The rail: hidden or shown (the tilde does it too), moved to a side, its width. */
        hideRail(hidden = true) { rail.hidden = !!hidden; relayout(); remember(); return rail.hidden; },
        railHidden() { return rail.hidden; },
        moveRail(side) {
            if (!SIDES.has(side) || side === rail.side) return false;
            rail.side = side; rail.hidden = false;
            relayout(); remember();
            return true;
        },
        railSide() { return rail.side; },
        railWidth() { return railEl.hidden ? 0 : railEl.offsetWidth; },
        shownTab() { return rail.tab; },
        isOpen(id) { const p = panels.get(id); return !!(p && p.open); },
        isShown(id) { const p = panels.get(id); return !!(p && visible(p) && !(docked(p) && rail.hidden)); },
        state(id) { const p = panels.get(id); return p ? { id, title: p.title, zone: p.zone, open: p.open, shown: this.isShown(id), collapsed: p.collapsed, where: p.where, x: p.x, y: p.y, height: p.height } : null; },
        list() { return [...panels.keys()].map((id) => this.state(id)); },
        destroy() {
            for (const id of [...panels.keys()]) this.unregister(id);
            window.removeEventListener("keydown", onKey);
            railEl.remove(); free.remove(); tabs.remove();
        },
    };
    layoutRail();
    return api;
}
