/* Settings: every shortcut and navigation setting of the page, in one panel, kept
 * per browser (docs/plans/input-2026-10-12.md).
 *
 * The shortcuts: the key that opens the ring on the selection (m), the modifier a
 * right-click is held with to open it at the pointer (Ctrl; a plain right-click is
 * the camera's), and the keys that step a level in and out (Page Down, Page Up).
 * The navigation: automatic zoom -- the wheel, pushed on past the dolly's limit,
 * stepping a level in or out -- on or off, each way on or off, how much scroll past
 * the limit it takes, and where the limit sits: how near a level's pieces the camera
 * may come (a fraction of the level's size) and how far out (a multiple of the
 * distance that frames it).
 *
 * makeSettings() is the store the page reads: values(), set(id, value), reset(id),
 * resetAll(), holder(combo) -- whose a key is -- and onChange(fn), told at once of
 * every change, so nothing waits for a reload. What differs from the defaults is kept
 * under one key of this browser's storage; a browser that keeps nothing (storage
 * refused, a private window) has the defaults, and every setting still works for the
 * page's life.
 *
 * mountSettings(settingsEl, store, { log }) draws the panel into settingsEl: a row per setting,
 * its default shown and a reset beside it, and Reset all. A shortcut's field takes
 * the next key pressed, refusing one another shortcut holds and naming that shortcut;
 * Escape lets go of it.
 */

import { comboOf, MODIFIERS } from "/static/ring.js";

export const SETTINGS_KEY = "apothecary.settings";

// Every setting, in the order the panel shows it: its kind, its default, the words the
// panel says it with, and for a number its reach and step.
export const SETTINGS = [
    { id: "ringKey", kind: "key", group: "Shortcuts", label: "Open the ring", def: "m",
      title: "The key that opens the ring on the selection, at the middle of the screen" },
    { id: "ringModifier", kind: "modifier", group: "Shortcuts", label: "Ring: right-click with", def: "ctrl",
      title: "Held with a right-click, the ring opens at the pointer; a right-click alone is the camera's (on macOS, Ctrl+click is a right-click)" },
    { id: "zoomInKey", kind: "key", group: "Shortcuts", label: "Step in", def: "PageDown",
      title: "Steps into the selected piece, or the one nearest the middle of the view" },
    { id: "zoomOutKey", kind: "key", group: "Shortcuts", label: "Step out", def: "PageUp",
      title: "Steps out to the level above" },
    { id: "autoZoom", kind: "tick", group: "Automatic zoom", label: "Automatic zoom", def: true,
      title: "The wheel, pushed on past the limit of the dolly, steps a level in or out" },
    { id: "autoZoomIn", kind: "tick", group: "Automatic zoom", label: "Stepping in", def: true,
      title: "Scrolling in past the nearest the camera comes steps into a piece" },
    { id: "autoZoomOut", kind: "tick", group: "Automatic zoom", label: "Stepping out", def: true,
      title: "Scrolling out past the farthest the camera goes steps out a level" },
    { id: "wheelResistance", kind: "number", group: "Automatic zoom", label: "Resistance", unit: "of scroll", def: 500, min: 50, max: 5000, step: 50,
      title: "How much scrolling past the limit it takes before a step: a wheel's notch is about 100" },
    { id: "dollyIn", kind: "number", group: "Automatic zoom", label: "Nearest", unit: "× the level's size", def: 0.08, min: 0.01, max: 1, step: 0.01,
      title: "How near the pieces of a level the camera may dolly, as a fraction of the level's size: the limit stepping in starts at" },
    { id: "dollyOut", kind: "number", group: "Automatic zoom", label: "Farthest", unit: "× its framing", def: 8, min: 1.5, max: 50, step: 0.5,
      title: "How far out of a level the camera may dolly, as a multiple of the distance that frames it: the limit stepping out starts at" },
];
const BY_ID = Object.fromEntries(SETTINGS.map((s) => [s.id, s]));

// The modifiers a right-click can be held with, as the panel names them.
export const MODIFIER_LABELS = { ctrl: "Ctrl", alt: "Alt", shift: "Shift", meta: "Meta" };

// The keys the page holds whatever the settings say, and what each does: a shortcut is
// never given one of them, so no key does two things.
const UNDO = Object.fromEntries(["Ctrl", "Meta"].flatMap((m) => [
    [`${m}+z`, "Undo"], [`${m}+Z`, "Redo"], [`${m}+y`, "Redo"], [`${m}+Y`, "Redo"],
]));
export const FIXED = {
    Backspace: "Up one level",
    "?": "Show or hide the hint bar",
    f: "Fit", F: "Fit",
    p: "Take picture", P: "Take picture",
    "~": "Hide or show the rail", "`": "Hide or show the rail",
    Escape: "Close",
    ...UNDO,
    F5: "the SCAD editor's Check", F6: "the SCAD editor's Render",
    "Ctrl+Enter": "the SCAD editor's Render", "Ctrl+s": "the SCAD editor's Save",
};

const KEY_WORDS = {
    PageDown: "Page Down", PageUp: "Page Up", ArrowUp: "↑", ArrowDown: "↓", ArrowLeft: "←", ArrowRight: "→",
    Space: "Space", Escape: "Esc", Delete: "Delete", Insert: "Insert", Home: "Home", End: "End",
};

/* A shortcut as a person reads it: "Page Down", "Ctrl+M". */
export function keyLabel(combo) {
    if (!combo) return "";
    const parts = combo.split("+");
    // "Ctrl++": the key is the plus itself.
    const key = combo.endsWith("++") ? "+" : parts.pop();
    const mods = combo.endsWith("++") ? parts.slice(0, -2) : parts;
    const word = KEY_WORDS[key] ?? (key.length === 1 && mods.length ? key.toUpperCase() : key);
    return [...mods, word].join("+");
}

export function modifierLabel(name) {
    return MODIFIER_LABELS[name] || MODIFIER_LABELS.ctrl;
}

function valid(setting, value) {
    if (setting.kind === "key") return typeof value === "string" && value.length > 0 && value.length <= 40;
    if (setting.kind === "modifier") return typeof value === "string" && value in MODIFIERS;
    if (setting.kind === "tick") return typeof value === "boolean";
    if (setting.kind === "number") return typeof value === "number" && Number.isFinite(value) && value >= setting.min && value <= setting.max;
    return false;
}

export function defaults() {
    return Object.fromEntries(SETTINGS.map((s) => [s.id, s.def]));
}

export function makeSettings({ storageKey = SETTINGS_KEY } = {}) {
    const values = defaults();
    let kept = {};
    try { kept = JSON.parse(localStorage.getItem(storageKey) || "{}") || {}; } catch (e) { kept = {}; }
    if (typeof kept === "object") for (const s of SETTINGS) if (valid(s, kept[s.id])) values[s.id] = kept[s.id];
    // Two shortcuts kept on one key (written by hand): the later goes back to its default.
    const seen = new Set();
    for (const s of SETTINGS.filter((x) => x.kind === "key")) {
        if (seen.has(values[s.id]) || FIXED[values[s.id]]) values[s.id] = s.def;
        seen.add(values[s.id]);
    }
    const listeners = new Set();

    function keep() {
        const out = {};
        for (const s of SETTINGS) if (values[s.id] !== s.def) out[s.id] = values[s.id];
        try {
            if (Object.keys(out).length) localStorage.setItem(storageKey, JSON.stringify(out));
            else localStorage.removeItem(storageKey);
        } catch (e) { /* kept nowhere: the settings hold for this page's life */ }
    }
    function told(id) {
        keep();
        for (const fn of listeners) {
            try { fn({ ...values }, id); } catch (e) { console.error(e); }
        }
    }

    const api = {
        values: () => ({ ...values }),
        get: (id) => values[id],
        /* Whose a key is: the setting's label, or what the page holds it for; null when
         * it is free. `except` is the setting being changed, whose own key is free to it. */
        holder(combo, except = null) {
            if (FIXED[combo]) return FIXED[combo];
            const other = SETTINGS.find((s) => s.kind === "key" && s.id !== except && values[s.id] === combo);
            return other ? other.label : null;
        },
        /* Changed, at once: { ok, said }. A key another shortcut holds is refused, naming it. */
        set(id, value) {
            const s = BY_ID[id];
            if (!s) return { ok: false, said: `No setting ${id}` };
            if (s.kind === "number") {
                const n = typeof value === "number" ? value : Number.parseFloat(value);
                if (!Number.isFinite(n)) return { ok: false, said: `${s.label}: a number, from ${s.min} to ${s.max}` };
                value = Math.min(s.max, Math.max(s.min, n));
            }
            if (!valid(s, value)) return { ok: false, said: `${s.label}: not a value it takes` };
            if (s.kind === "key") {
                const holder = api.holder(value, id);
                if (holder) return { ok: false, said: `${keyLabel(value)} is taken: ${holder}. Press another key` };
            }
            if (values[id] === value) return { ok: true, said: `${s.label}: ${api.describe(id)}` };
            values[id] = value;
            told(id);
            return { ok: true, said: `${s.label}: ${api.describe(id)}` };
        },
        /* Back to its default; a shortcut whose default another holds now is refused,
         * naming the one that holds it. */
        reset(id) {
            const s = BY_ID[id];
            if (!s) return { ok: false, said: `No setting ${id}` };
            const holder = s.kind === "key" ? api.holder(s.def, id) : null;
            if (holder) return { ok: false, said: `${keyLabel(s.def)}, its default, is taken: ${holder}. Change that first, or Reset all` };
            return api.set(id, s.def);
        },
        /* Every setting back to its default at once, whatever holds what. */
        resetAll() {
            Object.assign(values, defaults());
            told(null);
            return { ok: true, said: "Every setting is back to its default" };
        },
        describe(id, value = values[id]) {
            const s = BY_ID[id];
            if (s.kind === "key") return keyLabel(value);
            if (s.kind === "modifier") return modifierLabel(value);
            if (s.kind === "tick") return value ? "on" : "off";
            return String(value);
        },
        onChange(fn) { listeners.add(fn); return () => listeners.delete(fn); },
        SETTINGS,
    };
    return api;
}

// ---------------------------------------------------------------------------
// The panel
// ---------------------------------------------------------------------------

const esc = (v) => String(v ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

const STYLE = `
.settings-ui { gap: 0.5rem; }
.settings-ui .settings-group { display: grid; grid-template-columns: minmax(0, 1fr) auto auto; gap: 0.3rem 0.4rem; align-items: center; }
.settings-ui .settings-group > .k { grid-column: 1 / -1; }
.settings-ui .setting-name { display: flex; flex-direction: column; min-width: 0; }
.settings-ui .setting-name > span:first-child { color: #ccc; }
.settings-ui .setting-default { font-size: 0.68rem; color: #777; }
.settings-ui .setting-key { min-width: 6.5rem; text-align: center; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
.settings-ui .setting-key[aria-pressed="true"] { border-color: #e0b84a; color: #e0b84a; }
.settings-ui .setting-number { width: 4.5rem; }
.settings-ui .setting-choice { font: inherit; font-size: 0.78rem; background: #232823; color: #ddd; border: 1px solid #3a443a; border-radius: 4px; padding: 0.15rem 0.3rem; }
.settings-ui .setting-unit { font-size: 0.68rem; color: #777; white-space: nowrap; }
.settings-ui .setting-control { display: flex; align-items: center; gap: 0.3rem; justify-self: end; }
.settings-ui .setting-reset { padding: 0.1rem 0.35rem; }
.settings-ui .setting-said { min-height: 1em; font-size: 0.72rem; color: #8a9a8a; }
.settings-ui .setting-said.bad { color: #ff8080; }
.settings-ui .setting-row.off > .setting-name > span:first-child { color: #777; }
`;

function ensureStyle() {
    if (document.getElementById("settings-style")) return;
    const style = document.createElement("style");
    style.id = "settings-style";
    style.textContent = STYLE;
    document.head.appendChild(style);
}

function control(store, s, capturing) {
    const value = store.get(s.id);
    if (s.kind === "key") {
        return `<button type="button" class="setting-key" data-setting="${s.id}" aria-pressed="${capturing}" title="Press, then press the key to use (Escape lets go)">${capturing ? "Press a key…" : esc(keyLabel(value))}</button>`;
    }
    if (s.kind === "modifier") {
        const options = Object.keys(MODIFIERS).map((m) => `<option value="${m}"${m === value ? " selected" : ""}>${MODIFIER_LABELS[m]}</option>`).join("");
        return `<select class="setting-choice" data-setting="${s.id}" title="${esc(s.title)}">${options}</select>`;
    }
    if (s.kind === "tick") {
        return `<input type="checkbox" class="setting-tick" data-setting="${s.id}"${value ? " checked" : ""} title="${esc(s.title)}">`;
    }
    return `<input type="number" class="setting-number" data-setting="${s.id}" value="${value}" min="${s.min}" max="${s.max}" step="${s.step}" title="${esc(s.title)}"><span class="setting-unit">${esc(s.unit)}</span>`;
}

export function mountSettings(settingsEl, store, { log = null } = {}) {
    ensureStyle();
    const say = (text, bad = false) => { if (log) log(text, bad ? "bad" : ""); };
    const state = { capturing: null, said: {}, drawing: false };

    function render() {
        // Drawn again whole: the field that had the focus goes with it, which is no
        // letting go of it.
        state.drawing = true;
        try { draw(); } finally { state.drawing = false; }
    }
    function draw() {
        const values = store.values();
        const groups = [...new Set(SETTINGS.map((s) => s.group))];
        settingsEl.innerHTML = `<div class="panel-ui settings-ui">${groups.map((g) => `<div class="settings-group"><div class="k">${esc(g)}</div>${
            SETTINGS.filter((s) => s.group === g).map((s) => {
                const at = values[s.id] === s.def;
                // Stepping in and out mean nothing while automatic zoom is off.
                const off = (s.id === "autoZoomIn" || s.id === "autoZoomOut") && !values.autoZoom;
                const said = state.said[s.id];
                return `<div class="setting-name${off ? " off" : ""}" data-row="${s.id}" title="${esc(s.title)}"><span>${esc(s.label)}</span><span class="setting-default">default: ${esc(store.describe(s.id, s.def))}</span>${
                    said ? `<span class="setting-said${said.bad ? " bad" : ""}">${esc(said.text)}</span>` : ""}</div>`
                    + `<div class="setting-control">${control(store, s, state.capturing === s.id)}</div>`
                    + `<button type="button" class="setting-reset" data-setting="${s.id}" title="Back to its default, ${esc(store.describe(s.id, s.def))}"${at ? " disabled" : ""}>↺</button>`;
            }).join("")
        }</div>`).join("")}<div class="row"><span class="grow"></span><button type="button" class="settings-reset-all" title="Every setting back to its default">Reset all</button></div></div>`;
        if (state.capturing) settingsEl.querySelector(`.setting-key[data-setting="${state.capturing}"]`)?.focus({ preventScroll: true });
    }

    function answered(id, done) {
        state.said = { [id]: { text: done.said, bad: !done.ok } };
        say(done.said, !done.ok);
    }

    // A press: a shortcut's field takes the next key, a reset puts one setting back, and
    // Reset all every one.
    function settingClicked(ev) {
        const b = ev.target.closest("button");
        if (!b || !settingsEl.contains(b)) return;
        const id = b.dataset.setting;
        if (b.classList.contains("setting-key")) {
            state.said = {};
            state.capturing = state.capturing === id ? null : id;
            render();
        } else if (b.classList.contains("setting-reset")) {
            state.capturing = null;
            answered(id, store.reset(id));
            render();
        } else if (b.classList.contains("settings-reset-all")) {
            state.capturing = null;
            const done = store.resetAll();
            state.said = {};
            say(done.said);
            render();
        }
    }

    // A tick-box, the modifier's drop-down or a number, changed.
    function settingChanged(ev) {
        const el = ev.target;
        const id = el.dataset && el.dataset.setting;
        if (!id) return;
        const value = el.type === "checkbox" ? el.checked : el.value;
        answered(id, store.set(id, value));
        render();
    }

    // The next key pressed while a shortcut's field is waiting: kept, or refused for
    // being another's. Nothing else on the page hears it. Escape lets go, and Tab
    // moves on as it does anywhere.
    function keyCaptured(ev) {
        const id = state.capturing;
        if (!id) return;
        if (ev.key === "Tab") {
            // The focus moves on from the field, which shows its key again where it is.
            state.capturing = null;
            const field = ev.target.closest(".setting-key");
            if (field) { field.setAttribute("aria-pressed", "false"); field.textContent = keyLabel(store.get(id)); }
            return;
        }
        ev.preventDefault();
        ev.stopPropagation();
        if (ev.key === "Escape") { state.capturing = null; state.said = {}; render(); return; }
        const combo = comboOf(ev);
        if (!combo) return;  // a modifier on its own: the key is still to come
        const done = store.set(id, combo);
        answered(id, done);
        if (done.ok) state.capturing = null;
        render();
    }

    // The field let go of when the focus leaves it.
    function captureLetGo(ev) {
        if (!state.capturing || state.drawing) return;
        const field = ev.target.closest && ev.target.closest(".setting-key");
        if (!field || field.dataset.setting !== state.capturing) return;
        if (ev.relatedTarget && settingsEl.contains(ev.relatedTarget) && ev.relatedTarget.dataset.setting === state.capturing) return;
        state.capturing = null;
        render();
    }

    settingsEl.addEventListener("click", settingClicked);
    settingsEl.addEventListener("change", settingChanged);
    settingsEl.addEventListener("keydown", keyCaptured);
    settingsEl.addEventListener("focusout", captureLetGo);
    // A setting changed from anywhere else (another reset, Reset all) is shown at once.
    const off = store.onChange(() => { if (!state.capturing) render(); });
    render();
    return {
        render,
        capturing: () => state.capturing,
        destroy() { off(); settingsEl.innerHTML = ""; },
    };
}
