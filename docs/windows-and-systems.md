# Windows and focused systems, for an author

What a person sees of the page's windows is [viewer.md](viewer.md#the-windows).
This page is how a window, or a focused system of windows, is added: what to
write, where, and the tests that hold it. The window manager is
`apothecary/static/panels.js`, on GoldenLayout; a focused system is an entry of
`apothecary/systems.py`, which `apothecary/static/systems.js` turns into
windows on the page. Each file's header says the rest.

## A window

The page registers it, in `templates/fractal_viewer.html.j2`:

```js
this.panels.register('gather', {
    title: 'Gather', group: 'Pictures',
    hint: 'Which of the ticked pictures are of one thing, and what the machine would ask a person',
    body: gatherEl, home: 'pictures', open: false,
    onOpen: () => this.pictureList(),
});
```

- `title` is its tab (`tab` a shorter one, the title then its tooltip); `hint`
  the tooltip where it is listed; `group` its heading in ⊞ Windows and a
  stack's +.
- `body` is an element the window adopts, or a function given the slot the
  first time the window is in front of a person.
- `home` is where it opens when it is not in the layout: `"column"`, the one
  column beside the world -- right under the window named by `after`, sharing
  a stack with the others that follow it; a stack of its own while the column
  has fewer than `columnStacks` (four), else a tab beside the window it
  follows, or at the column's foot; `"tabs"`, the stack of the other tabbed
  windows; `"beside"`, next to the world, its room taken from the world's; or
  another window's id, a tab beside that one.
- `open` says whether it opens as it is registered; `loud` that its tab and
  frame say it must be seen (an armed printer's pad). `onOpen` is told when its
  filled body is in front again, `onClose` when it is closed.
- A window a browser may remember is named in `mountPanels`'s `known`; one
  made for the moment, never remembered, in `transient` (both in the page's
  call to `mountPanels`).
- `this.panels.setEmpty(id, empty)` says the window has nothing to show, or
  has again: its stack gives its room away while all of it is empty.

A view -- windows laid out together -- is `defineView(id, { title, layout,
requires, hint })`, its layout written in window ids; a focused system's view
is defined from the registry, so a page defines none by hand.

**Tests.** Where a window opens, what a view lays out, what a browser
remembers, a window's life and the column's limit are
`tests/e2e/test_window_manager.py`'s, on a page of its own with no server: a
new case is a parameter there. A feature's test opens a window through
`tests/e2e/windows.py` and asserts what the feature does, not where the window
stands (`tests/e2e/README.md`).

## A focused system

One subject -- a part, a board, a rotor and stator -- with a main window for
it and its verbs, and sections, each a window of its own, closed until asked
for. It is one entry of `SYSTEMS` in `apothecary/systems.py`:

- `System(id, title, group, main, sections, view, cell, opened_by,
  transient=False)`: `main` is the main window's id; `view` lays the main
  window, every section and the world out, in window ids; `cell` is the view's
  label under Panels › Windows on the ring (`apothecary/menu.py` reads it);
  `opened_by` says how a person opens the subject, said when the view is asked
  for without it; `transient`, that the system's windows live only while its
  subject is open (a board's Machine) and are never remembered.
- `Section(id, title, holds, home=None, verbs=(), kind=None, on_link=False)`:
  its window is `<system>-<section>`; `holds` is said where it is listed;
  `home` as a window's, its main window by default; `verbs` are the ring's
  actions that act on it and open it (an action, or a prefix ending in `:`);
  `kind`, the one kind of subject it is for (a printer, a devkit); `on_link`,
  that a link to the subject opens it.

The page gives the system its widget, as a hook in its call to
`mountSystems(this.panels, SYSTEMS, { ... })`: `{ mount(slot, sections) ->
handle, main?, shown? }`. `mount` moves each section's content into
`sections[id]`, the element its window holds; with `main`, the main window is
registered by `systems.js`, its body `slot`. The handle the page keeps for
the system has:

- `showSection(id)`, to open a section;
- `setEmpty(id, empty)`, for a section with nothing to show;
- `attach({ kind, without })` and `detach()`, for a transient system, as its
  subject opens, turns out to be of a kind, and closes;
- `openLinked()`, where the page follows a link to the subject.

A verb carried from the ring opens the sections it acts on by itself
(`openFor`, after the verb is carried).

**Tests.** `tests/test_systems.py` holds the registry: each window named
once, a cell a ring label, a view's windows the page's, the verbs the ring's.
`tests/e2e/test_focused_systems.py` holds every system and section in the
viewer, parameterized over the registry, from its tables: `OPENING` (how the
subject opens, for each kind), `SHOWS` (what each section's window shows),
`VERB` (a verb that opens one), `LINK` (a link to the subject) and `EMPTY` (how
its sections come to have nothing to show). A system or a section added to
the registry without its lines there fails
`test_every_system_and_section_has_a_line_here`.
