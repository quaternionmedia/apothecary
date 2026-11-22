/* Panels: the page's windows, laid out by GoldenLayout.
 *
 * The world and every window the page registers are components of one GoldenLayout
 * (vendor/golden-layout): each its own window, in a stack of tabs, a person drags
 * anywhere, splits beside another, maximises or closes. There is no other system of
 * panels. The module names no window of the page's: the page gives it the windows a
 * remembered layout may hold (`known`), those made for the moment and never
 * remembered (`transient`), and its own layout (`defaultRoot`); each has a default.
 * A window registered that is in neither list is lost from a remembered layout, so
 * registering one says so on the console.
 *
 * Where a window opens when it is not in the layout is its `home`: "column", the one
 * column beside the world, right under the window it follows (`after`), where the
 * windows following that one share a stack -- a stack of its own while the column has
 * fewer than `columnStacks`, else a tab beside the window it follows, unless that one
 * has a least height (below), which a tab in front of it would hide; "tabs", the
 * stack where the other tabbed windows are; "beside", next to the world (below); or
 * another window's id, a tab beside it, else beside a window open with the same home.
 * The page may open a window somewhere else than its home for once (open's `at`). A
 * `loud` window's tab and frame say so, and it must be seen: wherever it is placed --
 * opened, registered, or kept open as a view is laid out -- it is the front tab of its
 * stack. The world's stack maximised is the world alone (the tilde); again, everything
 * back.
 *
 * Beside the world there is one stack of windows: a window whose home is "beside" is a
 * tab of the stack in the world's row that holds one already. With none there, it is a
 * stack of its own next to the world, its room taken from the world's: BESIDE per cent
 * of the row at most, and never so much that the world is narrower than WORLD_LEAST
 * pixels. Where the world cannot spare BESIDE_LEAST pixels, it is a tab of the stack
 * next to the world instead -- the tallest, where a column stands there, that holds no
 * window with a least height.
 *
 * A window may have a least height (`least`, pixels, its stack's tabs included): where
 * it stands in a column, its stack is given that much as the window opens or a view is
 * laid out, from the stacks beside it, while they keep the height of their tabs.
 *
 * A window the page says has nothing to show (setEmpty) gives its room away: in front
 * of one that has something, it gives that one the front; a stack of nothing but
 * empty windows, in a column, is minimised to its tabs, and has its height back when
 * one of them has something to show, is opened, or has its tab pressed. What is
 * remembered is the height it had.
 *
 * A view is a named arrangement of windows, written in their ids (resolveView), and
 * may name the window it cannot be laid out without (`requires`). Every stack but the
 * world's wears a + listing every window by its group; fillMenu draws the same into
 * a menu of the page's, and fillViews the views into another.
 *
 * What a person did to the layout is remembered per browser, without the windows
 * made for the moment, and a remembered layout the page cannot read is ignored.
 *
 * Each window's element is a `section.panel[data-panel=<id>]`: a pinned bar
 * (pinnedSlot) above a body that scrolls. The element outlives its component:
 * closed and opened again, the same element, with what it holds, is shown.
 *
 * See-through (seeThrough), the world is laid under the whole layout rather than in
 * its own window alone, and every other window lets it show through: the host wears
 * `see-through` and `--window-opacity`, how opaque the page's styles draw a window
 * then. The world's element is told where its window stands in it (`--frame-left`,
 * `-top`, `-right`, `-bottom`) and so is the page (onFrame), which frames its view
 * on that window, so what the world's window shows is what it showed -- or on the
 * whole layout while another window is maximised over it. Off, the
 * world is as big as its window again. ⊞ Windows wears the switch and the opacity
 * when the page gives fillMenu its own (`seeThrough`).
 */

import { GoldenLayout, LayoutConfig } from "golden-layout";
import { setReason } from "./can.js";
import { mayAct, takes } from "./keys.js";

const TILDE_KEYS = new Set(["`", "~"]);
const WORLD = "world";
const HOMES = new Set(["column", "tabs", "beside"]);
// A window opened beside the world takes this share of the world's row (per cent) at
// most, and half the world's at most.
const BESIDE = 28;
// The least a window opened beside the world leaves the world (pixels): enough to see a
// machine and select a piece in it.
const WORLD_LEAST = 400;
// The least room a stack beside the world is opened with (pixels); with less to spare,
// the window is a tab next to the world.
const BESIDE_LEAST = 280;
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
    // simulated machines' banner and the status line, and the layout follows it.
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
        r = { id, title: id, tab: null, hint: null, flag: null, home: null, after: null, group: null, loud: false, empty: false, least: 0, el, slot, mount: null, filled: true, open: false,
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
            watchWorld(container.element);
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
            wearGroup(tab.element, r.group);
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
        wearGroup(container.element, r.group);
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

    // ---- see-through windows ----------------------------------------------------
    // Declared before the layout is first laid out, which makes the world's window.
    let through = null;      // { opacity } while see-through, else null
    let worldWindow = null;  // the world's window's element, where it stands now
    let framed = "null";     // the frame last told, so each is told once
    let laidUnder = false;   // the world's element wears the styles below
    const framers = [];
    const FRAME_SIDES = ["left", "top", "right", "bottom"];
    const watcher = window.ResizeObserver ? new ResizeObserver(() => frameWorld()) : null;
    watcher?.observe(host);
    function watchWorld(el) {
        if (worldWindow && worldWindow !== el) watcher?.unobserve(worldWindow);
        worldWindow = el;
        watcher?.observe(el);
        frameWorld();
    }
    // Where the world's window stands in the layout (`x`, `y`: the world's element is laid
    // that far up and left of it) and the frame the view is drawn in, in pixels of the
    // world's element laid under the layout: the world's window -- or, while another
    // window is maximised over it, which GoldenLayout lays out of sight, the whole layout.
    // Null while not see-through, or while the world's window has no size.
    function frameOf() {
        if (!through || !worldWindow?.isConnected) return null;
        const whole = host.getBoundingClientRect(), own = worldWindow.getBoundingClientRect();
        if (!(own.width > 0 && own.height > 0 && whole.width > 0 && whole.height > 0)) return null;
        const x = own.left - whole.left, y = own.top - whole.top;
        const covered = !!host.querySelector(".lm_maximised") && !isWorldAlone();
        const frame = covered ? { x: 0, y: 0, width: whole.width, height: whole.height } : { x, y, width: own.width, height: own.height };
        return { x, y, frame, fullWidth: whole.width, fullHeight: whole.height };
    }
    // The world laid under the whole layout, or back in its window; the page told the
    // frame of its view whenever that changed.
    function frameWorld() {
        const f = frameOf();
        if (f) {
            Object.assign(world.style, {
                position: "absolute", left: `${-f.x}px`, top: `${-f.y}px`, right: "auto", bottom: "auto",
                width: `${f.fullWidth}px`, height: `${f.fullHeight}px`,
            });
            const { frame } = f;
            const inset = { left: frame.x, top: frame.y, right: f.fullWidth - frame.x - frame.width, bottom: f.fullHeight - frame.y - frame.height };
            for (const side of FRAME_SIDES) world.style.setProperty(`--frame-${side}`, `${inset[side]}px`);
            laidUnder = true;
        } else if (laidUnder) {
            for (const k of ["position", "left", "top", "right", "bottom", "width", "height"]) world.style[k] = "";
            for (const side of FRAME_SIDES) world.style.removeProperty(`--frame-${side}`);
            laidUnder = false;
        }
        const told = f ? { ...f.frame } : null;
        const key = JSON.stringify(told);
        if (key === framed) return;
        framed = key;
        for (const fn of framers) fn(told);
    }
    function seeThrough(on, opacity) {
        const level = Math.min(1, Math.max(0.05, Number(opacity) || (through ? through.opacity : 1)));
        through = on ? { opacity: level } : null;
        host.classList.toggle("see-through", !!through);
        if (through) host.style.setProperty("--window-opacity", String(level));
        else host.style.removeProperty("--window-opacity");
        frameWorld();
    }

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
    // The layout as it stands, as it is remembered: null when none can be.
    function remembering() {
        const out = kept(JSON.parse(JSON.stringify(layout.saveLayout())), knownTypes, TRANSIENT);
        if (!out) return null;
        unminimisedIn(out.root);
        out.panels = [...records.values()].filter((r) => r.registered && !TRANSIENT.has(r.id)).map((r) => r.id);
        return JSON.stringify(out);
    }
    function save() {
        saving = null;
        try {
            const out = remembering();
            if (out) localStorage.setItem(storageKey, out);
        } catch (e) { /* private window, blocked storage: the layout still works */ }
    }
    function remember() {
        if (!saving) saving = setTimeout(save, 200);
    }
    const flush = () => { if (saving) { clearTimeout(saving); save(); } };
    layout.on("stateChanged", remember);
    // A window moved past the world's, which moves it and leaves its size, is seen here.
    layout.on("stateChanged", frameWorld);
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

    // A window added to a stack of tabs (at `index`, else after its last), in front only
    // when `front`.
    function addTab(stack, config, front, index = undefined) {
        const before = stack.getActiveComponentItem();
        stack.addItem(config, index);
        if (!front && before) stack.setActiveComponentItem(before, false);
    }
    // The stack of windows beside the world: one in the world's row holding a window
    // whose home is "beside" (not `except`), the nearest the world where there are two.
    function besideStack(except) {
        const ws = worldStack(), row = ws?.parent;
        if (!row?.isRow) return null;
        const at = row.contentItems.indexOf(ws);
        const beside = (c) => c !== ws && c.isStack && c.contentItems.some((ci) => ci.id !== except && records.get(ci.id)?.home === "beside");
        const far = (c) => Math.abs(row.contentItems.indexOf(c) - at);
        return row.contentItems.filter(beside).sort((a, b) => far(a) - far(b))[0] || null;
    }
    // A stack holding a window that must stay in view: one with a least height.
    const holdsLeast = (s) => s.contentItems.some((ci) => records.get(ci.id)?.least > 0);
    // The stack next to the world, on its right (else its left): itself, or the tallest
    // stack of the column standing there, the first of two as tall -- never one holding
    // a window that must stay in view (a least height), while there is another.
    function nextToTheWorld() {
        const ws = worldStack(), row = ws?.parent;
        if (!row?.isRow) return null;
        const at = row.contentItems.indexOf(ws);
        const next = row.contentItems[at + 1] || row.contentItems[at - 1];
        if (!next) return null;
        if (next.isStack) return next;
        const height = (s) => s.element.getBoundingClientRect().height;
        const stacks = stacksOf(next);
        const free = stacks.filter((s) => !holdsLeast(s));
        return (free.length ? free : stacks).reduce((best, s) => (!best || height(s) > height(best) ? s : best), null);
    }

    // Where a panel opens when it is not in the layout: its home, or `home` given for
    // this once. Added to a stack of tabs, it is in front only when `front` (opened by a
    // person), so a panel the page registers does not take the place of the one a
    // person was reading -- a loud one always, as it must be seen. Then every window
    // keeps its least height.
    function addAt(r, front = true, home = r.home) {
        placeAt(r, front || r.loud, home);
        keepLeast();
    }
    function placeAt(r, front, home) {
        const config = { type: "component", componentType: r.id, id: r.id, title: r.tab || r.title };
        const tabbed = [...records.values()].filter((o) => o.id !== r.id && o.registered && o.home === "tabs" && item(o.id));
        // A window whose home is another one goes beside it, else beside a window open
        // with the same home (an Airgap section beside another, the Airgap closed).
        const kin = (o) => o.id !== r.id && o.home === home && item(o.id);
        const beside = !HOMES.has(home) && home !== r.id
            ? item(home) || item([...records.values()].find(kin)?.id) : null;
        if ((home === "tabs" && tabbed.length) || beside) {
            const stack = (beside || item(tabbed[0].id)).parentItem;
            // Beside its home panel, else after the stack's last tab.
            addTab(stack, config, front, beside ? stack.contentItems.indexOf(beside) + 1 : undefined);
            return;
        }
        // A component's stack is its parentItem; a stack's row or column, its parent.
        rowForTheWorld();
        const ws = worldStack();
        const besideWorld = ws && ws.parent;
        if (home === "beside" && besideWorld) {
            // The one stack beside the world, where there is one: a tab of it.
            const shared = besideStack(r.id);
            if (shared) { addTab(shared, config, front); return; }
            // Else a stack of its own, its room taken from the world's, the windows on
            // the world's other side keeping theirs -- unless the world cannot spare it.
            const sizes = new Map(besideWorld.contentItems.map((c) => [c, c.size]));
            let room = Math.min(BESIDE, sizes.get(ws) / 2);
            const worldPx = ws.element.getBoundingClientRect().width;
            if (worldPx > 0) {
                const perCent = worldPx / sizes.get(ws);  // pixels per per cent of the row
                const spare = Math.min(room, (worldPx - WORLD_LEAST) / perCent);
                if (spare * perCent >= BESIDE_LEAST) room = spare;
                else {
                    const next = nextToTheWorld();
                    if (next) { addTab(next, config, front); return; }
                    // Nothing else stands in the row: a stack of its own all the same.
                }
            }
            const at = besideWorld.contentItems.indexOf(ws) + 1;
            besideWorld.addItem({ type: "stack", content: [config] }, at);
            const added = besideWorld.contentItems[at];
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
        const sibling = r.after && home === "column"
            ? [...records.values()].find((o) => o.id !== r.id && o.after === r.after && o.home === "column" && item(o.id)) : null;
        if (sibling) {
            addTab(item(sibling.id).parentItem, config, front);
            return;
        }
        const near = r.after ? item(r.after)?.parentItem : null;
        const column = (near?.parent?.type === "column" ? near.parent : null)
            || [...records.values()].map((o) => item(o.id)).filter(Boolean)
                .map((ci) => ci.parentItem?.parent).find((p) => p && p.type === "column");
        if (column && column.contentItems.length >= columnStacks) {
            // The column full: a tab beside the window it follows, else at its foot --
            // never over a window that must stay in view (a least height): a stack of its
            // own under that one all the same.
            const stack = near && near.parent === column ? near : column.contentItems[column.contentItems.length - 1];
            if (stack.isStack && !holdsLeast(stack)) {
                addTab(stack, config, front);
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
    // A window with a least height (`least`) whose stack stands lower in a column: given
    // it from the stacks beside it in their shares -- none minimised, each keeping its
    // tabs' height.
    function keepLeast() {
        for (const r of records.values()) {
            if (!r.least || !r.registered) continue;
            const stack = item(r.id)?.parentItem, column = stack?.parent;
            if (!column?.isColumn || minimised.has(stack)) continue;
            const has = stack.element.getBoundingClientRect().height;
            if (!has || has >= r.least - 1) continue;
            const height = column.element.getBoundingClientRect().height - LAYOUT_SETTINGS.dimensions.borderWidth * (column.contentItems.length - 1);
            const others = column.contentItems.filter((c) => c !== stack && !minimised.has(c));
            const sum = others.reduce((a, c) => a + c.size, 0);
            if (height <= 0 || !sum) continue;
            const want = Math.min((100 * r.least) / height, stack.size + sum - (100 * LOWEST * others.length) / height);
            if (want <= stack.size) continue;
            for (const c of others) c.size -= (want - stack.size) * (c.size / sum);
            stack.size = want;
            column.updateSize(false);
        }
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
    // Up and down move along a list's buttons, Home and End to its ends -- unless what
    // has the focus takes the key itself (a slider, its arrows).
    function stepFocus(list, ev) {
        const keys = { ArrowDown: 1, ArrowUp: -1, Home: -Infinity, End: Infinity };
        if (!list || !(ev.key in keys) || takes(ev.target, ev.key)) return;
        const buttons = [...list.querySelectorAll("button:not(:disabled)")];
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
    // Whose a thing is: its group's colour is tokens.css's, read from data-group.
    function wearGroup(el, group) {
        if (group) el.dataset.group = group; else delete el.dataset.group;
    }
    function windowButton(r, into) {
        const b = document.createElement("button");
        b.type = "button";
        b.className = "window-item";
        b.dataset.window = r.id;
        wearGroup(b, r.group);
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
            wearGroup(head, group);
            list.append(head);
            for (const r of rs) {
                const b = windowButton(r, true);
                b.addEventListener("click", () => {
                    closeSpawn();
                    if (!item(r.id) && stack.element.isConnected) {
                        stack.addItem({ type: "component", componentType: r.id, id: r.id, title: r.tab || r.title });
                    }
                    api.open(r.id);
                    chosen(r.id);
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

    // A window a person chooses -- its tab pressed, or its entry in ⊞ Windows or a
    // stack's + -- told to whoever asked (onChoose), after it is in front. A window the
    // page brings forward itself is not chosen, and a tab's ✕ chooses nothing.
    const choosers = [];
    function chosen(id) { for (const fn of choosers) fn(id); }
    host.addEventListener("pointerdown", (ev) => {
        const tab = ev.target.closest(".lm_tab");
        if (!tab || ev.target.closest(".lm_close_tab")) return;
        for (const stack of stacksOf(layout.rootItem)) {
            const found = (stack.header?.tabs || []).find((t) => t.element === tab);
            if (found && found.componentItem) { const id = found.componentItem.id; setTimeout(() => chosen(id), 0); return; }
        }
    });

    // ⊞ Windows' first row, given the page's own see-through (`look`): its switch, and
    // how opaque a window is then, a slider that turns it on as it moves. The page keeps
    // both and calls seeThrough; the row says what it was told.
    function seeThroughRow(look) {
        const row = document.createElement("div");
        row.className = "see-through-row";
        const b = document.createElement("button");
        b.type = "button";
        b.className = "window-item see-through-item";
        const range = document.createElement("input");
        range.type = "range";
        range.className = "see-through-level";
        Object.assign(range, { min: String(look.min ?? 10), max: String(look.max ?? 90), step: String(look.step ?? 5) });
        range.setAttribute("aria-label", "How opaque a window is, see-through");
        const said = document.createElement("span");
        said.className = "see-through-said";
        let on = !!look.on, level = Math.round(Number(look.opacity) * 100);
        const paint = () => {
            b.textContent = `${on ? "◉" : "○"} See-through`;
            b.setAttribute("aria-pressed", String(on));
            b.title = on ? `See-through: the world shows through every window, each ${level}% opaque. Pressed, the windows are solid again${look.key ? ` (${look.key})` : ""}`
                : `Solid windows. Pressed, the world is drawn under every window and shows through it, each ${level}% opaque${look.key ? ` (${look.key})` : ""}`;
            range.value = String(level);
            range.title = `How opaque a window is, see-through: ${level}%. Moved, see-through is on`;
            said.textContent = `${level}%`;
        };
        b.addEventListener("click", () => { on = !on; look.set({ on }); paint(); });
        range.addEventListener("input", () => { on = true; level = Number(range.value); look.set({ on, opacity: level / 100 }); paint(); });
        paint();
        row.append(b, range, said);
        return row;
    }

    // The views, each an entry that lays its windows out: drawn into a menu of the
    // page's (its ⚙ View), under their heading.
    function fillViews(into, done, own) {
        into.replaceChildren();
        const viewsHead = document.createElement("div");
        viewsHead.className = "spawn-group";
        viewsHead.textContent = "Views";
        into.append(viewsHead);
        for (const [id, v] of views) {
            if (v.listed === false) continue;  // a journey's, laid out by the Tour box going to it
            const b = document.createElement("button");
            b.type = "button";
            b.className = "window-item view-item";
            b.dataset.view = id;
            b.textContent = v.title;
            const missing = api.viewMissing(id);
            const offer = own ? own.offer(id) : { refused: missing ? `${v.title} lays out ${missing.title}'s windows: open ${missing.title} first${missing.hint ? ` (${missing.hint})` : ""}` : null };
            // Greyed where it cannot be laid out now, as every control the page greys is
            // (can.js): "Disabled: <why>. <what it does>". The page's own press says why
            // as well, so its entry is pressed all the same, disabled to assistive
            // technology alone (aria-disabled); without one it is disabled.
            setReason(b, offer.refused || null, offer.title || `The windows laid out as ${v.title}`);
            if (own) b.disabled = false;
            b.addEventListener("click", () => { if (own) own.press(id); else api.applyView(id); if (done) done(); });
            into.append(b);
        }
    }

    function fillMenu(into, done, look) {
        into.replaceChildren();
        if (look) into.append(seeThroughRow(look));
        for (const [group, rs] of windowsByGroup()) {
            const head = document.createElement("div");
            head.className = "spawn-group";
            head.textContent = group;
            wearGroup(head, group);
            into.append(head);
            for (const r of rs) {
                const b = windowButton(r, false);
                b.addEventListener("click", () => { api.open(r.id); chosen(r.id); if (done) done(); });
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
         * tab and frame say it must be seen; `least` the least height of its stack, in
         * pixels, where it stands in a column (see the header). `onClose` is called when
         * it is closed; `onOpen` when its filled body is in front of a person again. */
        register(id, { title, tab = null, hint = null, body, home = "tabs", after = null, group = null, open = true, loud = false, least = 0, onClose = null, onOpen = null } = {}) {
            if (!knownTypes.has(id)) {
                // Not given in `known` or `transient`: the remembered layout was laid
                // out without it, so a reload has closed it, its room kept from the world.
                console.warn(`The window ${id} is not one the page gave panels.js as known or transient: a reload closes it.`);
                knownTypes.add(id); layout.registerComponentFactoryFunction(id, factory);
            }
            const r = record(id);
            r.title = title || id; r.tab = tab; r.hint = hint; r.loud = !!loud; r.group = group; r.after = after; r.least = Math.max(0, Number(least) || 0);
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
                if (r.container?.tab) wearGroup(r.container.tab.element, r.group);
                if (r.container) wearGroup(r.container.element, r.group);
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
        /* Open a panel: shown where it is, else opened at its home -- or at `at`, a home
         * given for this once (a window the page opens of its own accord, in the column
         * rather than beside the world) -- its tab in front, its body filled before this
         * returns, so a verb sent to it next finds it. */
        open(id, { at = null } = {}) {
            const r = records.get(id);
            if (!r || !r.registered) return false;
            if (!item(id)) addAt(r, true, at && at !== id ? at : r.home);
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
        /* Whether the browser holds the layout as it stands: false while a change is
         * waiting to be written, and while one has been made that the layout has not
         * yet said it made. True where nothing can be remembered. */
        remembered() {
            try {
                const out = remembering();
                return !saving && (!out || localStorage.getItem(storageKey) === out);
            } catch (e) { return true; }
        },
        /* A view: a named arrangement of windows, the page's own ("default") or one a
         * page defines -- `layout` in rows, columns and stacks of window ids (see
         * resolveView), the window it cannot be laid out without (`requires`) and how a
         * person opens that window (`hint`), said where the view is refused. A window a
         * view leaves out is closed; one made for the moment that was open stays open,
         * at its home. */
        defineView(id, { title, layout: spec, requires = null, hint = null, listed = true }) { views.set(id, { title: title || id, spec, requires, hint, listed }); },
        views() { return [...views].map(([id, v]) => ({ id, title: v.title, requires: v.requires, listed: v.listed })); },
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
            keepLeast();
            remember();
            return true;
        },
        /* The header's Windows menu, drawn into `into` each time it opens: every window
         * by its group, each opened (or brought in front) by a press. `done()` is called
         * after a press. `seeThrough`, the page's: { on, opacity
         * (a fraction), min, max, step (per cent), key (its shortcut, as said),
         * set({ on, opacity }) }, a row above them: its switch, and a slider of how
         * opaque a window is. */
        fillMenu(into, { done = null, seeThrough: look = null } = {}) { fillMenu(into, done, look); },
        /* The views, drawn into `into` each time the menu that holds them opens: a
         * heading, then an entry a view (`.view-item[data-view]`), its windows laid out
         * by a press. `done()` is called after a press. `views` is the page's own way
         * with a view, where it has one: { offer(id) -> { refused, title }, press(id) }
         * -- why the view cannot be laid out now (else null) and what its entry says,
         * and the press itself, which may open the window the view needs and says what
         * came of it. Without it a view is laid out by applyView, and one whose window
         * the page has not got is disabled. */
        fillViews(into, { done = null, views: own = null } = {}) { fillViews(into, done, own); },
        /* See-through windows (see the header): on, every window but the world's drawn
         * `opacity` opaque (a fraction) over the world laid under the whole layout; off,
         * solid, the world in its own window. */
        seeThrough(on = true, { opacity = null } = {}) { seeThrough(!!on, opacity); return !!through; },
        isSeeThrough() { return !!through; },
        /* `fn(frame)` is told where the world's window stands in the world's element --
         * { x, y, width, height }, pixels -- each time that changes while see-through,
         * and null when it is not; at once, with where it stands now. */
        onFrame(fn) { framers.push(fn); fn(JSON.parse(framed)); },
        /* `fn(id)` is told of each window a person chooses: its tab, ⊞ Windows, a +. */
        onChoose(fn) { choosers.push(fn); },
        /* Up, down, Home and End along a list's buttons: a menu's keys. */
        stepFocus,
        destroy() {
            closeSpawn();
            seeThrough(false);
            watcher?.disconnect();
            window.removeEventListener("keydown", onKey);
            window.removeEventListener("pagehide", flush);
            for (const r of records.values()) r.releasing = true;
            layout.destroy();
        },
    };
    return api;
}
