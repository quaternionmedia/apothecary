/* Panels: the page's windows, laid out by GoldenLayout.
 *
 * The world and every panel the page registers -- Site, Selected, Pictures, the
 * Bench, Settings, a board's Machine, an armed printer's control pad, the SCAD
 * editor popped out of Selected -- are components of one GoldenLayout
 * (vendor/golden-layout): each its own window, in a stack of tabs, a person
 * drags anywhere, splits beside another, maximises or closes. There is no other
 * system of panels.
 *
 * Where a panel opens when it is not in the layout is its `home`: "column", a
 * stack of its own in the column beside the world (Site, Selected); "tabs", the
 * stack where the other tabbed panels are (Pictures, the Bench, Settings, a
 * Machine); "beside", a stack of its own next to the world (the control pad, the
 * SCAD editor out of Selected). A `loud` panel's tab and frame say so (the armed
 * control pad). The world's stack maximised is the world alone (the tilde, and
 * the ring's Panels › World); again, everything back.
 *
 * What a person did to the layout is remembered per browser; the components a
 * page makes for the moment (a Machine, the control pad, the editor out of
 * Selected) are left out of what is remembered, and a remembered layout this
 * page cannot read is ignored.
 *
 * Each panel's element is a `section.panel[data-panel=<id>]`: a pinned bar
 * (pinnedSlot) above a body that scrolls. The element outlives its component:
 * closed and opened again, the same element, with what it holds, is shown.
 */

import { GoldenLayout, LayoutConfig } from "golden-layout";
import { mayAct } from "./keys.js";

const TILDE_KEYS = new Set(["`", "~"]);
const WORLD = "world";
// Made for the moment: never remembered, so a reload does not bring back an empty one.
const TRANSIENT = new Set(["machine", "control", "scad-editor"]);
const HOMES = new Set(["column", "tabs", "beside"]);
// A window opened beside the world takes this share of the world's row (per cent).
const BESIDE = 28;

const DEFAULT_LAYOUT = {
    settings: { showPopoutIcon: false, constrainDragToContainer: true, reorderEnabled: true },
    header: { popout: false, maximise: "Maximise", minimise: "Restore", close: "Close", tabDropdown: "More tabs" },
    dimensions: { borderWidth: 6, headerHeight: 26, minItemWidth: 160, minItemHeight: 80 },
    root: {
        type: "row",
        content: [
            {
                type: "stack", width: 70, header: { show: false },
                content: [{ type: "component", componentType: WORLD, id: WORLD, title: "World", isClosable: false }],
            },
            {
                type: "column", width: 30,
                content: [
                    { type: "stack", height: 42, content: [{ type: "component", componentType: "site", id: "site", title: "Site" }] },
                    { type: "stack", height: 34, content: [{ type: "component", componentType: "selected", id: "selected", title: "Selected" }] },
                    {
                        type: "stack", height: 24,
                        content: [
                            { type: "component", componentType: "pictures", id: "pictures", title: "Pictures" },
                            { type: "component", componentType: "bench", id: "bench", title: "Bench" },
                            { type: "component", componentType: "settings", id: "settings", title: "Settings" },
                        ],
                    },
                ],
            },
        ],
    },
};

// A resolved layout with the transient components and anything this page does not
// register taken out, and the stacks and rows they leave empty; null when no world
// is left in it (nothing to lay the rest around).
function kept(config, known) {
    let world = false;
    const walk = (item) => {
        if (item.type === "component") {
            if (item.componentType === WORLD) world = true;
            return known.has(item.componentType) && !TRANSIENT.has(item.componentType) ? item : null;
        }
        const content = (item.content || []).map(walk).filter(Boolean);
        if (!content.length) return null;
        const out = { ...item, content };
        if (item.type === "stack" && typeof item.activeItemIndex === "number") {
            out.activeItemIndex = Math.min(item.activeItemIndex, content.length - 1);
        }
        return out;
    };
    const root = config && config.root ? walk(config.root) : null;
    return root && world ? { ...config, root } : null;
}

export function mountPanels({ host, world, storageKey = "apothecary.layout", known = [] } = {}) {
    const records = new Map();  // id -> the panel: its element, its body, its callbacks
    const knownTypes = new Set([WORLD, "site", "selected", "pictures", "bench", "settings", ...TRANSIENT, ...known]);
    const layout = new GoldenLayout(host);
    // The host is the page's main row, not the body: its size follows the window, the
    // demo's banner and the status line, and the layout follows it.
    layout.resizeWithContainerAutomatically = true;

    function record(id) {
        let r = records.get(id);
        if (r) return r;
        const el = document.createElement("section");
        el.className = "panel";
        el.dataset.panel = id;
        const pinned = document.createElement("div");
        pinned.className = "panel-pinned";
        const slot = document.createElement("div");
        slot.className = "panel-body-slot";
        el.append(pinned, slot);
        r = { id, title: id, tab: null, home: null, loud: false, el, slot, mount: null, filled: true, open: false,
              registered: false, container: null, onClose: null, onOpen: null, onDock: null, releasing: false };
        records.set(id, r);
        return r;
    }

    // The world's component holds the world itself; every other one its panel's element.
    function factory(container, state) {
        const id = container.componentType;
        if (id === WORLD) {
            container.element.classList.add("world-window");
            container.element.appendChild(world);
            return;
        }
        const r = record(id);
        r.container = container;
        r.open = true;
        container.element.classList.add("panel-window");
        container.element.appendChild(r.el);
        const markTab = (tab) => {
            if (!tab || !tab.element) return;
            tab.element.dataset.panel = id;
            tab.element.classList.toggle("loud", r.loud);
            tab.element.title = r.title;
        };
        markTab(container.tab);
        container.on("tab", markTab);
        container.element.classList.toggle("loud", r.loud);
        const shown = () => {
            if (r.mount && r.registered) { const mount = r.mount; r.mount = null; mount(r.slot); r.filled = true; return; }
            if (r.filled && r.onOpen) r.onOpen();
        };
        container.on("shown", shown);
        if (container.visible) Promise.resolve().then(() => { if (r.container === container && container.visible && r.mount) shown(); });
        container.on("beforeComponentRelease", () => {
            if (r.container !== container) return;
            giveBackRoom(container.parent);
            r.container = null;
            r.open = false;
            r.el.remove();
            if (!r.releasing && r.onClose) r.onClose();
        });
    }
    for (const id of knownTypes) layout.registerComponentFactoryFunction(id, factory);

    let remembered = null;
    try { remembered = JSON.parse(localStorage.getItem(storageKey) || "null"); } catch (e) { remembered = null; }
    const start = (remembered && kept(remembered, knownTypes)) || null;
    try {
        layout.loadLayout(start ? LayoutConfig.fromResolved(start) : DEFAULT_LAYOUT);
    } catch (e) {
        console.warn("The remembered layout could not be read; the page's own is laid out instead.", e);
        layout.loadLayout(DEFAULT_LAYOUT);
    }

    let saving = null;
    function remember() {
        if (saving) return;
        saving = setTimeout(() => {
            saving = null;
            try {
                const resolved = layout.saveLayout();
                const out = kept(JSON.parse(JSON.stringify(resolved)), knownTypes);
                if (out) localStorage.setItem(storageKey, JSON.stringify(out));
            } catch (e) { /* private window, blocked storage: the layout still works */ }
        }, 200);
    }
    layout.on("stateChanged", remember);

    const item = (id) => layout.findFirstComponentItemById(id);
    const worldStack = () => item(WORLD)?.parentItem || null;
    const isWorldAlone = () => !!worldStack()?.isMaximised;

    // Where a panel opens when it is not in the layout: its home. Added to a stack of
    // tabs, it is in front only when `front` (opened by a person), so a panel the page
    // registers does not take the place of the one a person was reading.
    function addAt(r, front = true) {
        const config = { type: "component", componentType: r.id, id: r.id, title: r.tab || r.title };
        const tabbed = [...records.values()].filter((o) => o.id !== r.id && o.registered && o.home === "tabs" && item(o.id));
        if (r.home === "tabs" && tabbed.length) {
            const stack = item(tabbed[0].id).parentItem;
            const before = stack.getActiveComponentItem();
            stack.addItem(config);
            if (!front && before) stack.setActiveComponentItem(before, false);
            return;
        }
        // A component's stack is its parentItem; a stack's row or column, its parent.
        const ws = worldStack();
        const besideWorld = ws && ws.parent;
        if (r.home === "beside" && besideWorld) {
            // Its room is taken from the world's: the windows on the world's other side
            // keep theirs.
            const sizes = new Map(besideWorld.contentItems.map((c) => [c, c.size]));
            const at = besideWorld.contentItems.indexOf(ws) + 1;
            besideWorld.addItem({ type: "stack", content: [config] }, at);
            const added = besideWorld.contentItems[at];
            const room = Math.min(BESIDE, sizes.get(ws) / 2);
            for (const [c, size] of sizes) c.size = c === ws ? size - room : size;
            added.size = room;
            besideWorld.updateSize(false);
            return;
        }
        // A stack of its own in the column beside the world, else beside the world.
        const column = [...records.values()].map((o) => item(o.id)).filter(Boolean)
            .map((ci) => ci.parentItem?.parent).find((p) => p && p.type === "column");
        if (column) { column.addItem({ type: "stack", content: [config] }); return; }
        if (besideWorld) besideWorld.addItem({ type: "stack", content: [config] }, besideWorld.contentItems.indexOf(ws) + 1);
        else layout.addItem(config);
    }

    // A window beside the world closed, its stack with it: its room goes back to the
    // world, and the windows on the world's other side keep theirs -- so a window
    // opened beside the world and closed again leaves the layout as it found it.
    // GoldenLayout takes the stack away after this, in the same task.
    function giveBackRoom(ci) {
        const stack = ci?.parentItem, ws = worldStack(), row = ws?.parent;
        if (!stack || !row || stack === ws || stack.parent !== row || stack.contentItems.length !== 1) return;
        const sizes = new Map(row.contentItems.filter((c) => c !== stack).map((c) => [c, c.size]));
        sizes.set(ws, sizes.get(ws) + stack.size);
        queueMicrotask(() => {
            if (row.contentItems.includes(stack) || !row.contentItems.includes(ws)) return;
            for (const [c, size] of sizes) if (row.contentItems.includes(c)) c.size = size;
            row.updateSize(false);
        });
    }

    function show(id) {
        const ci = item(id);
        if (!ci) return false;
        if (isWorldAlone() && id !== WORLD) worldStack().toggleMaximise();
        ci.parentItem.setActiveComponentItem(ci, false);
        return true;
    }

    // The tilde: the world alone, or everything back -- unless a person is typing.
    // Matched by the key's place as well (Backquote, left of 1), so a layout where that
    // key prints something else, or is a dead key, still reaches it.
    const onKey = (ev) => {
        if (!(TILDE_KEYS.has(ev.key) || ev.code === "Backquote") || ev.ctrlKey || ev.metaKey || ev.altKey) return;
        if (!mayAct(ev)) return;
        ev.preventDefault();
        api.worldAlone(!isWorldAlone());
    };
    window.addEventListener("keydown", onKey);

    const api = {
        layout,
        /* Register a panel. `body` is an element the panel adopts or a function given
         * the slot to fill the first time the panel is in front of a person. `title`
         * is its tab; `home` where it opens ("column", "tabs", "beside"); `open`
         * whether it opens now when the layout does not hold it; `loud` a panel whose
         * tab and frame say it must be seen. `onClose` is called when it is closed;
         * `onOpen` when its filled body is in front of a person again; `onDock`, for a
         * panel that is a part of another one popped out of it (the SCAD editor),
         * is what docking it does. */
        register(id, { title, tab = null, body, home = "tabs", open = true, loud = false, onClose = null, onOpen = null, onDock = null } = {}) {
            if (!knownTypes.has(id)) { knownTypes.add(id); layout.registerComponentFactoryFunction(id, factory); }
            const r = record(id);
            r.title = title || id; r.tab = tab; r.home = HOMES.has(home) ? home : "tabs"; r.loud = !!loud;
            r.onClose = onClose; r.onOpen = onOpen; r.onDock = onDock; r.registered = true;
            if (typeof body === "function") { r.mount = body; r.filled = false; } else if (body) { r.slot.appendChild(body); }
            const ci = item(id);
            if (ci) {
                ci.setTitle(r.tab || r.title);
                r.container?.tab && (r.container.tab.element.title = r.title);
                r.container?.element.classList.toggle("loud", r.loud);
                if (r.container?.visible && r.mount) { const mount = r.mount; r.mount = null; mount(r.slot); r.filled = true; }
            } else if (open) {
                addAt(r, false);
            }
            return r.el;
        },
        /* Take a panel away for good; its onClose is called when it was open. Called
         * from its own onClose (its ✕), GoldenLayout is already taking it away. */
        unregister(id) {
            const r = records.get(id);
            if (!r) return;
            const ci = r.container ? item(id) : null;
            r.releasing = true;
            ci?.remove();
            r.el.remove();
            records.delete(id);
            if (ci && r.onClose) r.onClose();
        },
        /* Open a panel: shown where it is, else opened at its home, its tab in front. */
        open(id) {
            const r = records.get(id);
            if (!r || !r.registered) return false;
            if (!item(id)) addAt(r);
            return show(id);
        },
        close(id) {
            const ci = item(id);
            if (!ci) return false;
            ci.remove();
            return true;
        },
        /* The panel's frame pulses, for a loud one that has just opened. */
        alert(id) {
            const el = records.get(id)?.container?.element;
            if (!el) return false;
            el.classList.remove("alert");
            void el.offsetWidth;  // the animation starts again
            el.classList.add("alert");
            return true;
        },
        /* Open and in front, closed; else opened. */
        toggle(id) { return this.isShown(id) ? this.close(id) : this.open(id); },
        /* A popped-out part going back where it came from (onDock), or the panel opened. */
        dock(id) { const r = records.get(id); if (r && r.onDock) { r.onDock(); return true; } return this.open(id); },
        /* The world alone (its stack maximised), or everything back. */
        worldAlone(on = true) {
            const ws = worldStack();
            if (!ws) return false;
            if (!!on !== isWorldAlone()) ws.toggleMaximise();
            return isWorldAlone();
        },
        isWorldAlone,
        isOpen(id) { return !!item(id); },
        /* In the layout, its tab in front, and not behind the world alone. */
        isShown(id) {
            const ci = item(id);
            if (!ci) return false;
            if (isWorldAlone() && id !== WORLD) return false;
            return ci.parentItem.getActiveComponentItem() === ci;
        },
        /* The panel's pinned slot: above its body, out of its scrolling. */
        pinnedSlot(id) { const r = records.get(id); return r ? r.el.querySelector(":scope > .panel-pinned") : null; },
        state(id) {
            const r = records.get(id);
            if (!r && id !== WORLD) return null;
            const ci = item(id);
            const stack = ci?.parentItem;
            return {
                id, title: r ? r.title : "World", home: r ? r.home : "world", loud: !!(r && r.loud),
                open: !!ci, shown: this.isShown(id), where: ci ? "layout" : "closed",
                stack: stack ? stack.contentItems.map((c) => c.id) : [],
            };
        },
        list() { return [WORLD, ...records.keys()].map((id) => this.state(id)); },
        /* The page's own layout again, whatever a person made of it. */
        reset() {
            for (const r of records.values()) r.releasing = true;
            layout.loadLayout(DEFAULT_LAYOUT);
            for (const r of records.values()) {
                r.releasing = false;
                if (TRANSIENT.has(r.id) && r.registered) addAt(r, false);
            }
            remember();
            return true;
        },
        destroy() {
            window.removeEventListener("keydown", onKey);
            for (const r of records.values()) r.releasing = true;
            layout.destroy();
        },
    };
    return api;
}
