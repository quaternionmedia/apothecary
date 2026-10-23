/* Focused systems on the page: one subject each, in windows of its own.
 *
 * The registry is apothecary/systems.py, given to the page as it is rendered; this
 * module is the one place the page turns an entry into windows
 * (docs/plans/focused-systems-2026-10-22.md). For each system it defines the view,
 * and makes each section a window of its own -- `<system>-<section>`, grouped under
 * the system, beside the main window, closed until asked for. The widget that fills
 * a system's windows is mounted the first time any of them is shown, given the main
 * window's slot and an element per section to move that section's content into;
 * a section brought in front asks the widget to draw at its window's size.
 *
 * knownWindows(systems) -> every window a remembered layout may hold: what
 *   panels.js's mountPanels takes as `known`.
 * mountSystems(panels, systems, hooks) -> { [id]: system } for the systems `hooks`
 *   names. A hook is { mount(slot, sections) -> handle, main?: { title, tab, hint },
 *   shown?(handle, { fresh }) }: with `main`, the main window is registered here,
 *   its body the slot; without, the page registers it and mount's slot is null.
 *   A system's widget() mounts it, or answers the handle; showSection(id) opens a
 *   section's window; sections are the elements each section is moved into.
 */

export function knownWindows(systems) {
    return systems.flatMap((s) => [s.main, ...s.sections.map((sec) => sec.window)]);
}

export function mountSystems(panels, systems, hooks = {}) {
    const out = {};
    for (const system of systems) {
        panels.defineView(system.id, { title: system.title, layout: system.view });
        const hook = hooks[system.id];
        if (!hook) continue;
        const slot = hook.main ? document.createElement("div") : null;
        const sections = Object.fromEntries(system.sections.map((sec) => [sec.id, document.createElement("div")]));
        let handle = null;
        const widget = () => {
            if (!handle) {
                handle = hook.mount(slot, sections);
                if (hook.shown) hook.shown(handle, { fresh: true });
            }
            return handle;
        };
        if (hook.main) {
            panels.register(system.main, {
                title: hook.main.title || system.title, tab: hook.main.tab || null, hint: hook.main.hint || null,
                group: system.group, body: slot, open: false,
                onOpen: () => {
                    if (!handle) { widget(); return; }
                    if (hook.shown) hook.shown(handle, { fresh: false });
                },
            });
        }
        for (const sec of system.sections) {
            panels.register(sec.window, {
                title: sec.title, hint: `${system.title}: ${sec.holds}`, group: system.group,
                body: sections[sec.id], home: system.main, open: false,
                onOpen: () => { const h = widget(); if (h && h.redraw) h.redraw(); },
            });
        }
        out[system.id] = {
            id: system.id, title: system.title, sections,
            widget, mounted: () => handle,
            showSection: (id) => panels.open(`${system.id}-${id}`),
        };
    }
    return out;
}
