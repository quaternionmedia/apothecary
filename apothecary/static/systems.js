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
 * transientWindows(systems) -> the windows of the systems that live only while their
 *   subject is open (a board's Machine): never remembered, mountPanels' `transient`.
 * openFor(panels, systems, action) opens each section the ring's verb `action` acts
 *   on (its entry's `verbs`); a section whose window is not there now is passed by.
 * mountSystems(panels, systems, hooks) -> { [id]: system } for the systems `hooks`
 *   names. A hook is { mount(slot, sections) -> handle, main?: { title, tab, hint },
 *   shown?(handle, { fresh }) }: with `main`, the main window is registered here,
 *   its body the slot; without, the page registers it and mount's slot is null.
 *   A system's widget() mounts it, or answers the handle; showSection(id) opens a
 *   section's window; sections are the elements each section is moved into. A
 *   system that lives while its subject is open registers its sections' windows on
 *   attach() and takes them away on detach(), its subject opened and closed. A
 *   section for one kind of subject (`kind`) is there only for that kind:
 *   attach({ kind, without }) registers the sections for `kind` but those named in
 *   `without`, and takes away any other, as the subject turns out to be of a kind.
 */

export function knownWindows(systems) {
    return systems.flatMap((s) => [s.main, ...s.sections.map((sec) => sec.window)]);
}

export function openFor(panels, systems, action) {
    for (const system of systems) {
        for (const sec of system.sections) {
            const acts = sec.verbs.some((verb) => (verb.endsWith(":") ? action.startsWith(verb) : action === verb));
            if (acts) panels.open(sec.window);
        }
    }
}

export function transientWindows(systems) {
    return systems.filter((s) => s.transient).flatMap((s) => [s.main, ...s.sections.map((sec) => sec.window)]);
}

export function mountSystems(panels, systems, hooks = {}) {
    const out = {};
    for (const system of systems) {
        panels.defineView(system.id, { title: system.title, layout: system.view, requires: system.main, hint: system.opened_by });
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
        const attach = ({ kind = null, without = [] } = {}) => {
            for (const sec of system.sections) {
                if ((sec.kind && sec.kind !== kind) || without.includes(sec.id)) { panels.unregister(sec.window); continue; }
                if (panels.state(sec.window)?.registered) continue;  // there already, where a person left it
                panels.register(sec.window, {
                    title: sec.title, hint: `${system.title}: ${sec.holds}`, group: system.group,
                    body: sections[sec.id], home: sec.home || system.main, after: system.main, open: false,
                    onOpen: () => { const h = widget(); if (h && h.redraw) h.redraw(); },
                });
            }
        };
        const detach = () => { for (const sec of system.sections) panels.unregister(sec.window); };
        if (!system.transient) attach();
        out[system.id] = {
            id: system.id, title: system.title, sections,
            widget, mounted: () => handle,
            showSection: (id) => panels.open(system.sections.find((sec) => sec.id === id).window),
            attach, detach,
        };
    }
    return out;
}
