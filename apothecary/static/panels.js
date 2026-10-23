/* Panels: the page's windows, laid out by GoldenLayout.
 *
 * The world and every window the page registers are components of one GoldenLayout
 * (vendor/golden-layout): each its own window, in a stack of tabs, a person drags
 * anywhere, splits beside another, maximises or closes. There is no other system of
 * panels. The module names no window of the page's: the page gives it the windows a
 * remembered layout may hold (`known`), those made for the moment and never
 * remembered (`transient`), and its own layout (`defaultRoot`); each has a default.
 *
 * Where a window opens when it is not in the layout is its `home`: "column", the one
 * column beside the world, right under the window it follows (`after`), where the
 * windows following that one share a stack -- a stack of its own while the column has
 * fewer than `columnStacks`, else a tab beside the window it follows; "tabs", the
 * stack where the other tabbed windows are; "beside", a stack of its own next to the
 * world, its room taken from the world's; or another window's id, a tab beside it,
 * else beside a window open with the same home. A `loud` window's tab and frame say
 * so. The world's stack maximised is the world alone (the tilde); again, everything
 * back.
 *
 * A window the page says has nothing to show (setEmpty) gives its room away: in front
 * of one that has something, it gives that one the front; a stack of nothing but
 * empty windows, in a column, is minimised to its tabs, and has its height back when
 * one of them has something to show, is opened, or has its tab pressed. What is
 * remembered is the height it had.
 *
 * A view is a named arrangement of windows, written in their ids (resolveView), and
 * may name the window it cannot be laid out without (`requires`). Every stack but the
 * world's wears a + listing every window by its group; fillMenu draws the same, under
 * the views, into a menu of the page's.
 *
 * What a person did to the layout is remembered per browser, without the windows
 * made for the moment, and a remembered layout the page cannot read is ignored.
 *
 * Each window's element is a `section.panel[data-panel=<id>]`: a pinned bar
 * (pinnedSlot) above a body that scrolls. The element outlives its component:
 * closed and opened again, the same element, with what it holds, is shown.
 */

import { GoldenLayout, LayoutConfig } from "golden-layout";
import { mayAct } from "./keys.js";

const TILDE_KEYS = new Set(["`", "~"]);
const WORLD = "world";
const HOMES = new Set(["column", "tabs", "beside"]);
// A window opened beside the world takes this share of the world's row (per cent).
const BESIDE = 28;
// How low a stack goes, its tabs and a sliver: the height a minimised one is given.
const LOWEST = 40;

const LAYOUT_SETTINGS = {
    settings: { showPopoutIcon: false, constrainDragToContainer: true, reorderEnabled: true },
    // A stack's own ✕ is hidden by the page's CSS, not turned off here: turned off, no
    // window alone in its stack could be closed by its tab's ✕ either.
    header: { popout: false, maximise: "Maximise", minimise: "Restore", close: "Close", tabDropdown: "More tabs" },
    // The least a window is dragged down to: its tab and a sliver of it, never nothing.
    dimensions: { borderWidth: 6, headerHeight: 26, defaultMinItemWidth: "160px", defaultMinItemHeight: `${LOWEST}px` },
};
// The page's own layout when it gives none: the world alone in a row, where every
// window opens at its home.
const WORLD_ONLY = {
    type: "row",
    content: [{ type: "stack", header: { show: false }, content: [{ type: "component", componentType: WORLD, id: WORLD, title: "World", isClosable: false }] }],
};
// Every component type a layout names.
function typesIn(item, out = new Set()) {
    if (!item) return out;
    if (item.type === "component") out.add(item.componentType);
    for (const c of item.content || []) typesIn(c, out);
    return out;
}

// A resolved layout with the transient components and anything this page does not
// register taken out, and the stacks and rows they leave empty; null when no world
// is left in it (nothing to lay the rest around). A stack keeps the window it had in
// front, wherever that window now stands in it.
function kept(config, known, transient) {
    let world = false;
    const walk = (item) => {
        if (item.type === "component") {
            if (item.componentType === WORLD) world = true;
            return known.has(item.componentType) && !transient.has(item.componentType) ? item : null;
        }
        const content = (item.content || []).map(walk).filter(Boolean);
        if (!content.length) return null;
        const out = { ...item, content };
        // The world's window has no tab, whatever a layout says.
        if (item.type === "stack" && content.some((c) => c.componentType === WORLD)) out.header = { ...(item.header || {}), show: false };
        if (item.type === "stack" && typeof item.activeItemIndex === "number") {
            const front = (item.content || [])[item.activeItemIndex];
            const at = front ? content.indexOf(front) : -1;
            out.activeItemIndex = at >= 0 ? at : 0;
        }
        return out;
    };
    const root = config && config.root ? walk(config.root) : null;
    return root && world ? { ...config, root } : null;
}

export function mountPanels({ host, world, storageKey = "apothecary.layout", known = [], transient = [], defaultRoot = WORLD_ONLY, columnStacks = 4 } = {}) {
    const records = new Map();  // id -> the panel: its element, its body, its callbacks
    // The windows made for the moment, never remembered, so a reload does not bring
    // back an empty one.
    const TRANSIENT = new Set(transient);
    const DEFAULT_LAYOUT = { ...LAYOUT_SETTINGS, root: defaultRoot };
    const knownTypes = new Set([WORLD, ...typesIn(defaultRoot), ...TRANSIENT, ...known]);
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
        r = { id, title: id, tab: null, hint: null, flag: null, home: null, after: null, group: null, loud: false, empty: false, el, slot, mount: null, filled: true, open: false,
              registered: false, container: null, onClose: null, onOpen: null, releasing: false };
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
        // A tab says whose it is, and double-clicked maximises its stack (again, restores).
        const markTab = (tab) => {
            if (!tab || !tab.element) return;
            tab.element.dataset.panel = id;
            tab.element.classList.toggle("loud", r.loud);
            tab.element.classList.toggle("empty", r.empty);
            if (r.flag) tab.element.classList.add(r.flag);
            tab.element.title = r.hint || r.title;
            if (!tab.element.dataset.maximises) {
                tab.element.dataset.maximises = "dblclick";
                tab.element.addEventListener("dblclick", () => tab.contentItem?.parentItem?.toggleMaximise());
                tab.element.addEventListener("click", () => { const stack = tab.contentItem?.parentItem; gaveFront.delete(stack); if (minimised.has(stack)) unminimise(stack); });
            }
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
    const start = (remembered && kept(remembered, knownTypes, TRANSIENT)) || null;
    // Laid out from what this browser remembered: a panel it left out was closed, and
    // stays closed when the page registers it, until it is opened -- unless the page
    // had no such panel when the layout was remembered (`panels`), which opens at home.
    let fromMemory = !!start;
    const rememberedPanels = new Set((start && Array.isArray(start.panels)) ? start.panels : []);
    try {
        layout.loadLayout(start ? LayoutConfig.fromResolved(start) : DEFAULT_LAYOUT);
    } catch (e) {
        console.warn("The remembered layout could not be read; the page's own is laid out instead.", e);
        layout.loadLayout(DEFAULT_LAYOUT);
        fromMemory = false;
    }

    // Remembered a moment after a change, so a drag is saved once; and at once when
    // the page goes, so a window closed just before a reload stays closed.
    let saving = null;
    function save() {
        saving = null;
        try {
            const resolved = layout.saveLayout();
            const out = kept(JSON.parse(JSON.stringify(resolved)), knownTypes, TRANSIENT);
            if (out) {
                unminimisedIn(out.root);
                out.panels = [...records.values()].filter((r) => r.registered && !TRANSIENT.has(r.id)).map((r) => r.id);
                localStorage.setItem(storageKey, JSON.stringify(out));
            }
        } catch (e) { /* private window, blocked storage: the layout still works */ }
    }
    function remember() {
        if (!saving) saving = setTimeout(save, 200);
    }
    const flush = () => { if (saving) { clearTimeout(saving); save(); } };
    layout.on("stateChanged", remember);
    window.addEventListener("pagehide", flush);

    const item = (id) => layout.findFirstComponentItemById(id);
    const worldStack = () => item(WORLD)?.parentItem || null;
    // A window dropped on the world's left, right, top or bottom is a stack of its own
    // made with the world's stack's header -- hidden -- and would have no tab to drag,
    // close or find it by. While a drop is made on it, the world's stack hands new
    // stacks the layout's own header; at any other time (saving the layout) its own.
    function tabsForDrops() {
        const ws = worldStack();
        if (!ws || ws.apothecaryDrops) return;
        ws.apothecaryDrops = true;
        const drop = ws.onDrop;
        ws.onDrop = function (contentItem, area) {
            const own = this.createHeaderConfig;
            this.createHeaderConfig = () => undefined;
            try { return drop.call(this, contentItem, area); } finally { this.createHeaderConfig = own; }
        };
    }
    tabsForDrops();
    layout.on("stateChanged", tabsForDrops);
    const isWorldAlone = () => !!worldStack()?.isMaximised;

    // Where a panel opens when it is not in the layout: its home. Added to a stack of
    // tabs, it is in front only when `front` (opened by a person), so a panel the page
    // registers does not take the place of the one a person was reading.
    function addAt(r, front = true) {
        const config = { type: "component", componentType: r.id, id: r.id, title: r.tab || r.title };
        const tabbed = [...records.values()].filter((o) => o.id !== r.id && o.registered && o.home === "tabs" && item(o.id));
        // A window whose home is another one goes beside it, else beside a window open
        // with the same home (an Airgap section beside another, the Airgap closed).
        const kin = (o) => o.id !== r.id && o.home === r.home && item(o.id);
        const beside = !HOMES.has(r.home) && r.home !== r.id
            ? item(r.home) || item([...records.values()].find(kin)?.id) : null;
        if ((r.home === "tabs" && tabbed.length) || beside) {
            const stack = (beside || item(tabbed[0].id)).parentItem;
            const before = stack.getActiveComponentItem();
            // Beside its home panel, else after the stack's last tab.
            stack.addItem(config, beside ? stack.contentItems.indexOf(beside) + 1 : undefined);
            if (!front && before) stack.setActiveComponentItem(before, false);
            return;
        }
        // A component's stack is its parentItem; a stack's row or column, its parent.
        rowForTheWorld();
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
        // A stack of its own in the column beside the world, right under the window it
        // follows (a system's section under its main window) or at the column's foot;
        // else beside the world. A window that follows another, where one following the
        // same window is open there already, is a tab of that one's stack: a system's
        // sections opened in the column share one stack under it.
        const sibling = r.after && r.home === "column"
            ? [...records.values()].find((o) => o.id !== r.id && o.after === r.after && o.home === "column" && item(o.id)) : null;
        if (sibling) {
            const stack = item(sibling.id).parentItem;
            const before = stack.getActiveComponentItem();
            stack.addItem(config);
            if (!front && before) stack.setActiveComponentItem(before, false);
            return;
        }
        const near = r.after ? item(r.after)?.parentItem : null;
        const column = (near?.parent?.type === "column" ? near.parent : null)
            || [...records.values()].map((o) => item(o.id)).filter(Boolean)
                .map((ci) => ci.parentItem?.parent).find((p) => p && p.type === "column");
        if (column && column.contentItems.length >= columnStacks) {
            // The column full: a tab beside the window it follows, else at its foot.
            const stack = near && near.parent === column ? near : column.contentItems[column.contentItems.length - 1];
            if (stack.isStack) {
                const before = stack.getActiveComponentItem();
                stack.addItem(config);
                if (!front && before) stack.setActiveComponentItem(before, false);
                return;
            }
        }
        if (column) {
            const at = near && near.parent === column ? column.contentItems.indexOf(near) + 1 : undefined;
            column.addItem({ type: "stack", content: [config] }, at);
            return;
        }
        besideWorld.addItem({ type: "stack", content: [config] }, besideWorld.contentItems.indexOf(ws) + 1);
    }

    // With every window but the world closed, GoldenLayout lays the world's stack on the
    // layout's root, where nothing can stand beside it. Before a window opens there, the
    // layout is laid out again with the world in a row, every window kept, as reset()
    // lays the page's own out.
    function rowForTheWorld() {
        const ws = worldStack();
        if (!ws || ws.parent?.isRow || ws.parent?.isColumn) return;
        const config = LayoutConfig.fromResolved(layout.saveLayout());
        config.root = { type: "row", content: [config.root] };
        for (const r of records.values()) r.releasing = true;
        layout.loadLayout(config);
        for (const r of records.values()) r.releasing = false;
        tabsForDrops();
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

    // ---- a window with nothing to show ------------------------------------------------
    // A stack of nothing but empty windows, in a column with others to take its room, is
    // as low as a stack goes, its sliver hidden; `minimised` keeps the height it had.
    const minimised = new Map();  // stack -> its size before
    // The window that gave the front away for being empty: in front again once the
    // whole stack is empty, or once it has something to show, until a tab is pressed.
    const gaveFront = new Map();  // stack -> component item
    const isEmpty = (ci) => !!records.get(ci.id)?.empty;
    function setLow(stack, low) {
        const items = stack.element.querySelector(":scope > .lm_items");
        if (items) items.style.visibility = low ? "hidden" : "";
        stack.element.classList.toggle("minimised", low);
    }
    // Sizes the column's stacks so `stack` has `size`, the others keeping their shares.
    function resize(stack, size) {
        const column = stack.parent;
        const others = column.contentItems.filter((c) => c !== stack);
        const sum = others.reduce((a, c) => a + c.size, 0);
        if (!sum) return;
        const room = stack.size - size;
        for (const c of others) c.size += room * (c.size / sum);
        stack.size = size;
        column.updateSize(false);
    }
    function minimise(stack) {
        const column = stack.parent;
        if (minimised.has(stack) || !column?.isColumn || column.contentItems.length < 2) return;
        const height = column.element.getBoundingClientRect().height - LAYOUT_SETTINGS.dimensions.borderWidth * (column.contentItems.length - 1);
        if (height <= 0) return;
        const low = (100 * LOWEST) / height;
        if (stack.size <= low) return;
        minimised.set(stack, stack.size);
        resize(stack, low);
        setLow(stack, true);
    }
    function unminimise(stack) {
        if (!minimised.has(stack)) return;
        const was = minimised.get(stack);
        minimised.delete(stack);
        setLow(stack, false);
        if (stack.parent?.isColumn) resize(stack, was);
    }
    // A stack minimised when every window in it is empty, its height back otherwise.
    function fitEmpty(stack) {
        if (!stack?.isStack || stack === worldStack()) return;
        if (stack.contentItems.length && stack.contentItems.every(isEmpty)) {
            const was = gaveFront.get(stack);
            if (was && stack.contentItems.includes(was)) stack.setActiveComponentItem(was, false);
            minimise(stack);
        } else unminimise(stack);
    }
    function fitEveryEmpty() {
        for (const stack of [...minimised.keys()]) if (!stack.parent) minimised.delete(stack);
        const stacks = new Set([...records.values()].filter((r) => r.empty).map((r) => item(r.id)?.parentItem).filter(Boolean));
        for (const stack of stacks) fitEmpty(stack);
    }
    // What a browser remembers is each minimised stack at the height it had.
    function unminimisedIn(root) {
        const was = new Map();
        for (const [stack, size] of minimised) if (stack.parent && stack.contentItems[0]) was.set(stack.contentItems[0].id, size);
        if (!was.size) return;
        const walk = (node) => {
            const kids = node.content || [];
            const hits = kids.filter((k) => k.type === "stack" && was.has(k.content?.[0]?.componentType));
            if (hits.length) {
                const total = kids.reduce((a, k) => a + (k.size || 0), 0);
                const now = hits.reduce((a, k) => a + k.size, 0);
                const then = hits.reduce((a, k) => a + was.get(k.content[0].componentType), 0);
                const scale = total - now > 0 ? (total - then) / (total - now) : 1;
                for (const k of kids) k.size = hits.includes(k) ? was.get(k.content[0].componentType) : k.size * scale;
            }
            kids.forEach(walk);
        };
        walk(root);
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

    // ---- views ----------------------------------------------------------------
    // A view is written in window ids: "site" is a window (a stack of its own where it
    // stands in a row or a column); { stack: [...ids], size, active } a stack of tabs,
    // `active` the one in front; { row: [...] } and { column: [...] } split, each child
    // with an optional `size` (per cent of its row or column). "world", or
    // { world: true, size }, is the world's window, tabless. A window the page has not
    // registered is left out, and a stack, row or column left empty goes with it.
    const views = new Map([["default", { title: "Default", spec: null }]]);
    const worldItem = () => ({ type: "component", componentType: WORLD, id: WORLD, title: "World", isClosable: false });
    function resolveView(spec, parent = "row") {
        const sized = (out, size) => { if (size) out[parent === "column" ? "height" : "width"] = size; return out; };
        if (typeof spec === "string") {
            if (spec === WORLD) return { type: "stack", header: { show: false }, content: [worldItem()] };
            const r = records.get(spec);
            if (!r || !r.registered) return null;
            return { type: "stack", content: [{ type: "component", componentType: spec, id: spec, title: r.tab || r.title }] };
        }
        if (spec.world) return sized({ type: "stack", header: { show: false }, content: [worldItem()] }, spec.size);
        if (spec.stack) {
            const ids = spec.stack.filter((id) => records.get(id)?.registered);
            if (!ids.length) return null;
            const content = ids.map((id) => ({ type: "component", componentType: id, id, title: records.get(id).tab || records.get(id).title }));
            const out = { type: "stack", content };
            if (spec.active && ids.includes(spec.active)) out.activeItemIndex = ids.indexOf(spec.active);
            return sized(out, spec.size);
        }
        const type = spec.row ? "row" : "column";
        const content = (spec.row || spec.column).map((child) => resolveView(child, type)).filter(Boolean);
        if (!content.length) return null;
        return sized({ type, content }, spec.size);
    }

    // ---- spawning a window ----------------------------------------------------
    // Every stack but the world's wears a + among its buttons: pressed, a list of the
    // windows, by group; a closed one chosen opens as a tab of that stack, an open one
    // comes in front where it is.
    // The list listens to itself alone: Escape, or the focus leaving it (a press
    // anywhere else), closes it.
    let spawnOpen = null;
    function closeSpawn() {
        if (!spawnOpen) return;
        const list = spawnOpen;
        spawnOpen = null;
        list.remove();
    }
    // Up and down move along a list's buttons, Home and End to its ends.
    function stepFocus(list, ev) {
        const keys = { ArrowDown: 1, ArrowUp: -1, Home: -Infinity, End: Infinity };
        if (!list || !(ev.key in keys)) return;
        const buttons = [...list.querySelectorAll("button")];
        if (!buttons.length) return;
        ev.preventDefault();
        const at = buttons.indexOf(document.activeElement);
        const step = keys[ev.key];
        const to = Number.isFinite(step) ? (at + step + buttons.length) % buttons.length : (step < 0 ? 0 : buttons.length - 1);
        buttons[to].focus();
    }
    function windowsByGroup() {
        const groups = new Map();
        for (const r of records.values()) {
            if (!r.registered) continue;
            const g = r.group || "Panels";
            if (!groups.has(g)) groups.set(g, []);
            groups.get(g).push(r);
        }
        return groups;
    }
    function windowButton(r, into) {
        const b = document.createElement("button");
        b.type = "button";
        b.className = "window-item";
        b.dataset.window = r.id;
        const open = !!item(r.id);
        b.classList.toggle("open", open);
        b.textContent = (open ? "● " : "○ ") + (r.tab || r.title);
        b.title = `${r.hint || r.title} · ${open ? "open: brought in front" : into ? "opens here" : "opens at its place"}`;
        return b;
    }
    function spawnInto(stack, button) {
        closeSpawn();
        const list = document.createElement("div");
        list.className = "spawn-list";
        list.setAttribute("role", "menu");
        list.tabIndex = -1;  // a press inside it keeps the focus in it, a browser's buttons focusable or not
        for (const [group, rs] of windowsByGroup()) {
            const head = document.createElement("div");
            head.className = "spawn-group";
            head.textContent = group;
            list.append(head);
            for (const r of rs) {
                const b = windowButton(r, true);
                b.addEventListener("click", () => {
                    closeSpawn();
                    if (!item(r.id) && stack.element.isConnected) {
                        stack.addItem({ type: "component", componentType: r.id, id: r.id, title: r.tab || r.title });
                    }
                    api.open(r.id);
                });
                list.append(b);
            }
        }
        // It floats over the layout, wherever the page's styles say it looks.
        Object.assign(list.style, { position: "fixed", zIndex: "1000" });
        document.body.append(list);
        const at = button.getBoundingClientRect();
        // Below the +, or as low as the page lets it stand.
        list.style.top = `${Math.round(Math.max(8, Math.min(at.bottom + 4, innerHeight - list.offsetHeight - 8)))}px`;
        list.style.left = `${Math.round(Math.max(8, Math.min(at.right - list.offsetWidth, innerWidth - list.offsetWidth - 8)))}px`;
        spawnOpen = list;
        list.addEventListener("keydown", (ev) => {
            if (ev.key === "Escape") { ev.preventDefault(); ev.stopPropagation(); closeSpawn(); button.focus(); return; }
            stepFocus(list, ev);
        });
        // The + itself toggles the list, on its click.
        list.addEventListener("focusout", (ev) => {
            if (!list.contains(ev.relatedTarget) && ev.relatedTarget !== button && spawnOpen === list) closeSpawn();
        });
        list.querySelector("button")?.focus();
    }
    function stacksOf(itemNode, out = []) {
        if (!itemNode) return out;
        if (itemNode.isStack) out.push(itemNode);
        for (const c of itemNode.contentItems || []) stacksOf(c, out);
        return out;
    }
    function spawnButtons() {
        const ws = worldStack();
        for (const stack of stacksOf(layout.rootItem)) {
            if (stack === ws) continue;
            const controls = stack.element.querySelector(":scope > .lm_header .lm_controls");
            if (!controls || controls.querySelector(".lm_spawn")) continue;
            const b = document.createElement("button");
            b.type = "button";
            b.className = "lm_spawn";
            b.textContent = "+";
            b.title = "Open a window here: every window, by its group";
            b.setAttribute("aria-label", "Open a window here");
            b.addEventListener("pointerdown", (ev) => ev.stopPropagation());
            b.addEventListener("click", (ev) => { ev.stopPropagation(); if (spawnOpen) closeSpawn(); else spawnInto(stack, b); });
            controls.prepend(b);
        }
    }
    spawnButtons();
    layout.on("stateChanged", spawnButtons);

    function fillMenu(into, done) {
        into.replaceChildren();
        const viewsHead = document.createElement("div");
        viewsHead.className = "spawn-group";
        viewsHead.textContent = "Views";
        into.append(viewsHead);
        for (const [id, v] of views) {
            const b = document.createElement("button");
            b.type = "button";
            b.className = "window-item view-item";
            b.dataset.view = id;
            b.textContent = v.title;
            const missing = api.viewMissing(id);
            b.disabled = !!missing;
            b.title = missing ? `${v.title} lays out ${missing.title}'s windows: open ${missing.title} first${missing.hint ? ` (${missing.hint})` : ""}` : `The windows laid out as ${v.title}`;
            b.addEventListener("click", () => { api.applyView(id); if (done) done(); });
            into.append(b);
        }
        for (const [group, rs] of windowsByGroup()) {
            const head = document.createElement("div");
            head.className = "spawn-group";
            head.textContent = group;
            into.append(head);
            for (const r of rs) {
                const b = windowButton(r, false);
                b.addEventListener("click", () => { api.open(r.id); if (done) done(); });
                into.append(b);
            }
        }
    }

    const api = {
        layout,
        /* Register a panel. `body` is an element the panel adopts or a function given
         * the slot to fill the first time the panel is in front of a person. `title`
         * is its tab, `hint` its tab's tooltip (else the title); `home` where it opens
         * ("column", "tabs", "beside", or another panel's id: a tab beside it), and
         * `after` the window it opens right under, in the column; `open`
         * whether it opens now when the layout does not hold it; `loud` a panel whose
         * tab and frame say it must be seen. `onClose` is called when it is closed;
         * `onOpen` when its filled body is in front of a person again. */
        register(id, { title, tab = null, hint = null, body, home = "tabs", after = null, group = null, open = true, loud = false, onClose = null, onOpen = null } = {}) {
            if (!knownTypes.has(id)) { knownTypes.add(id); layout.registerComponentFactoryFunction(id, factory); }
            const r = record(id);
            r.title = title || id; r.tab = tab; r.hint = hint; r.loud = !!loud; r.group = group; r.after = after;
            r.home = HOMES.has(home) || (typeof home === "string" && home && home !== id) ? home : "tabs";
            r.onClose = onClose; r.onOpen = onOpen; r.registered = true;
            if (typeof body === "function") { r.mount = body; r.filled = false; } else if (body) {
                r.slot.appendChild(body);
                // Already in front of a person: told now, as a tab pressed would tell it.
                if (r.onOpen && r.container?.visible) queueMicrotask(() => { if (r.container?.visible && r.onOpen) r.onOpen(); });
            }
            const ci = item(id);
            if (ci) {
                ci.setTitle(r.tab || r.title);
                r.container?.tab && (r.container.tab.element.title = r.hint || r.title);
                r.container?.element.classList.toggle("loud", r.loud);
                if (r.container?.visible && r.mount) { const mount = r.mount; r.mount = null; mount(r.slot); r.filled = true; }
            } else if (open && (!fromMemory || TRANSIENT.has(id) || !rememberedPanels.has(id))) {
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
        /* Open a panel: shown where it is, else opened at its home, its tab in front,
         * its body filled before this returns, so a verb sent to it next finds it. */
        open(id) {
            const r = records.get(id);
            if (!r || !r.registered) return false;
            if (!item(id)) addAt(r);
            const shown = show(id);
            const stack = item(id)?.parentItem;
            if (minimised.has(stack)) unminimise(stack);
            if (shown && r.mount && r.container?.visible) { const mount = r.mount; r.mount = null; mount(r.slot); r.filled = true; }
            return shown;
        },
        close(id) {
            const ci = item(id);
            if (!ci) return false;
            ci.remove();
            return true;
        },
        /* The window has nothing to show (`empty`), or has again: see the header. */
        setEmpty(id, empty = true) {
            const r = records.get(id);
            if (!r || r.empty === !!empty) return false;
            r.empty = !!empty;
            r.container?.tab?.element.classList.toggle("empty", r.empty);
            const ci = item(id);
            if (!ci) return true;
            const stack = ci.parentItem;
            if (r.empty && stack.getActiveComponentItem() === ci) {
                const full = stack.contentItems.find((c) => !isEmpty(c));
                if (full) {
                    if (!gaveFront.has(stack)) gaveFront.set(stack, ci);
                    stack.setActiveComponentItem(full, false);
                }
            }
            if (!r.empty && gaveFront.get(stack) === ci) {
                gaveFront.delete(stack);
                stack.setActiveComponentItem(ci, false);
            }
            fitEmpty(stack);
            return true;
        },
        /* A panel's tab says something new -- a count -- and wears `flag` as a class
         * while it is given (Problems' count, red). */
        retitle(id, title, { flag = null } = {}) {
            const r = records.get(id);
            if (!r) return false;
            r.title = title;
            const element = r.container?.tab?.element;
            if (element && r.flag) element.classList.remove(r.flag);
            r.flag = flag;
            const ci = item(id);
            if (ci) ci.setTitle(r.tab || title);
            if (element) { if (flag) element.classList.add(flag); element.title = r.hint || title; }
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
                id, title: r ? r.title : "World", home: r ? r.home : "world", group: r ? r.group : null, loud: !!(r && r.loud),
                // A window a remembered layout names is known before it is registered.
                registered: r ? r.registered : true,
                empty: !!(r && r.empty), minimised: !!(ci && minimised.has(ci.parentItem)),
                open: !!ci, shown: this.isShown(id), where: ci ? "layout" : "closed",
                stack: stack ? stack.contentItems.map((c) => c.id) : [],
            };
        },
        list() { return [WORLD, ...records.keys()].map((id) => this.state(id)); },
        /* The page's own layout again, whatever a person made of it. */
        reset() { return this.applyView("default"); },
        /* A view: a named arrangement of windows, the page's own ("default") or one a
         * page defines -- `layout` in rows, columns and stacks of window ids (see
         * resolveView), the window it cannot be laid out without (`requires`) and how a
         * person opens that window (`hint`), said where the view is refused. A window a
         * view leaves out is closed; one made for the moment that was open stays open,
         * at its home. */
        defineView(id, { title, layout: spec, requires = null, hint = null }) { views.set(id, { title: title || id, spec, requires, hint }); },
        views() { return [...views].map(([id, v]) => ({ id, title: v.title, requires: v.requires })); },
        /* The window a view needs and the page has not got now ({ id, title, hint }), else null. */
        viewMissing(id) {
            const view = views.get(id);
            if (!view || !view.requires || records.get(view.requires)?.registered) return null;
            return { id: view.requires, title: view.title, hint: view.hint };
        },
        applyView(id) {
            const view = views.get(id);
            if (!view || this.viewMissing(id)) return false;
            const root = view.spec ? resolveView(view.spec) : null;
            if (view.spec && !root) return false;
            fromMemory = false;
            const wereOpen = new Set([...records.values()].filter((r) => TRANSIENT.has(r.id) && item(r.id)).map((r) => r.id));
            for (const r of records.values()) r.releasing = true;
            layout.loadLayout(root ? { ...DEFAULT_LAYOUT, root } : DEFAULT_LAYOUT);
            tabsForDrops();
            for (const r of records.values()) {
                r.releasing = false;
                if (wereOpen.has(r.id) && r.registered && !item(r.id)) addAt(r, false);
            }
            for (const r of records.values()) if (r.container?.visible && r.onOpen && r.filled) r.onOpen();
            minimised.clear();
            gaveFront.clear();
            fitEveryEmpty();
            remember();
            return true;
        },
        /* The header's Windows menu, drawn into `into` each time it opens: the views,
         * then every window by its group, each opened (or brought in front) by a press. */
        fillMenu(into, { done = null } = {}) { fillMenu(into, done); },
        /* Up, down, Home and End along a list's buttons: the Windows menu's keys. */
        stepFocus,
        destroy() {
            closeSpawn();
            window.removeEventListener("keydown", onKey);
            window.removeEventListener("pagehide", flush);
            for (const r of records.values()) r.releasing = true;
            layout.destroy();
        },
    };
    return api;
}
