# One screen: the world, and what stands in front of it

*Drafted 2026-09-20 on `consolidate/2026-09-19`, after the bench round.
Amended as the phases land; each phase's landing is noted in place.*

## The one-paragraph version

Apothecary has three screens: the fractal viewer (the world), the printer
monitor (one machine, close up) and the firmware page (the toolchain and
the boards on the bench). They are three pages with three toolbars, and
going from one to another is leaving the world. The aim is **one main
screen -- the world -- with everything else in front of it**: things that
belong to a place in the world are drawn *at* that place and follow it as
the camera moves (a printer's temperatures above the printer, its nozzle
where the board says it is, the bed's mesh on the bed, a job's stage beside
the machine), and the windows the other two screens are made of become
panels that open in front of the world -- tethered to the thing they are
about when they are about a thing -- and never replace it. The ring is the
way in to all of it, every option with its keypad cell, and the census is
the meter: today the three screens hold **148 controls of their own, 60 of
them also on a ring** (viewer 54/15, monitor 64/41, firmware 30/4); at the
end there is one page, its count is the sum of what survived, and nothing
was reclassified to make it smaller.

## What there is

| Screen | Route, template | What it holds | Census |
|---|---|---|---|
| The world | `/viewer/sites/{name}`, `templates/fractal_viewer.html.j2` (3 500 lines, `class FractalViewer`) | the three.js scene of a site: navigation by zoom level, selection, drag with a gizmo, wave-loaded real geometry; the toolbar; the Contents tree; the Selected panel (properties, staging, the Device section with pin / query / poll / watch); Jobs; the serial-log overlay; the minimap; the ring | 54 of its own, 15 on the ring |
| The monitor | `/firmware/monitor?port=…`, `templates/monitor.html.j2` (1 000 lines) | one printer: status cards, temperature chart, comms log with a query box, the latched control overlay, the Bed level card, the Print from here card, the board in its printer (`apothecary/static/board_view.js`, a second small three.js scene), the ring | 64 of its own, 41 on the ring |
| The bench | `/firmware`, `templates/firmware.html.j2` (670 lines) | the toolchain (install, cores, libraries), sketches (compile, upload), esptool, tasks and their history, the device cards (probe, identify, poll, live, monitor link, board view) | 30 of its own, 4 on the ring, no ring |

Shared already: `ring.js` (two pages), `board_view.js` (two pages), the
firmware routes, the site-devices view the viewer polls, the nine-cells
standard (`apothecary/menu.py`, `tests/conformance/nine_cells.json`), the
census. Vendored: three.js r160 with `OrbitControls`, `TransformControls`
and `STLLoader` -- no `CSS2DRenderer`, and nothing may be fetched from a
website while a person is using the tool (`static/vendor/three/README.md`),
so the anchor layer below is written here, in forty lines, not imported.

## The shape of the end

```
 ┌──────────────────────────────────────────────────────────────────┐
 │ toolbar: site · zoom out · breadcrumb · ⌗ Ring · ▣ Panels ▸      │
 ├──────────────────────────────────────────────────────────────────┤
 │                                                                  │
 │   THE WORLD (three.js, full bleed, the only scene)              │
 │                                                                  │
 │        ┌ printer_1 · idle · 15°/15° ┐   ← anchored badge:      │
 │        │ ▤ mesh 2.34 mm · leveling  │     follows the node     │
 │        └────────────╥──────────────┘                            │
 │              [printer body, board, nozzle marker, bed relief]    │
 │                                                                  │
 │  ┌ Contents ──────┐        ┌ printer_1 ─────────────────── ✕ ┐ │
 │  │ (docked panel) │        │ tethered popup: cards · chart   │ │
 │  │                │        │ control (latched) · bed · print │ │
 │  └────────────────┘        └──────────────╥──────────────────┘ │
 │                                           ╙─ leader to the node  │
 └──────────────────────────────────────────────────────────────────┘
```

Three kinds of thing in front of the world, and only three:

- **Anchors** -- HTML fixed to a point in the world, re-projected every
  frame: badges (a machine's state and temperatures; a devkit's hello), the
  job callout (`leveling: probing`, `print: 43 %`), the nozzle marker's
  readout. They are read, not operated: a click on a badge selects the
  node or opens its popup; nothing on a badge heats or moves a machine.
- **Popups** -- panels tethered to an anchor: they open at the node, follow
  it, and draw a leader to it. The machine popup (the monitor's cards,
  chart and controls), a devkit's serial popup, a piece's properties.
- **Panels** -- free or docked windows with no place in the world: the
  comms log, the bench (toolchain, sketches, tasks), the Contents tree,
  Jobs. Draggable, collapsible, remembered per browser; a docked rail on
  either side, and nothing docked can push the world off the screen.

What is drawn *in* the world (three.js) rather than in front of it: the
printer's body, the board, the nozzle marker, the bed relief, the build
volume -- what `board_view.js` draws today in its own small scene moves
into the one scene at the printer's node, and the small scene goes.

Rules that hold throughout:

1. **The world is never replaced.** A panel opens in front; a popup opens
   at; a page that today navigates away opens a panel instead. The old
   routes keep answering until the last phase, on the same modules.
2. **Every action has a cell.** A panel's verbs are ring verbs; opening a
   panel is a cell (`Panels ▸` on the canvas ring, `Machine` on a
   printer's node ring); the census's ring-backed share must not fall in
   any phase.
3. **Snappy.** Anchors are projected in the animation frame with no layout
   reads; polls stay asynchronous and coalesced as they are; a panel's
   content mounts lazily; the browser tests keep their timing bounds (a
   badge follows the camera within a frame, a poll lands in the badge
   within the poll interval, a popup opens within 300 ms).
4. **The census counts, the plan does not estimate.** Each phase ends
   with `uv run apothecary census` on the pages that exist, and the test
   that holds the numbers is edited with its docstring saying why.
5. **Human-only contributorship, `Tools:` lines, drafts not records** --
   `governance/qm`'s rules, unchanged.

## Phases

Each phase is shippable on its own: the suite green (unit and e2e with
their bounds), the docs regenerated, the census counted, the changelog
told, one commit or a few. The order is chosen so the visible thing --
the world with things in it -- comes first, and the plumbing that moves
the other two screens follows.

### Phase 0 — The meter, the seams, this plan  *(landed 2026-09-20)*

- The census counts the third screen (`census.FIRMWARE`, 30 / 4); a class
  that only says how a control looks does not name it. The three screens
  have one number: **148 / 60**. `test_the_three_screens_have_one_meter`
  holds it.
- This document; the draft record *One screen* in `governance/qm/adr/`,
  for a human to ratify, saying what stands in front of the world and
  what does not.
- The seams named: `world.js` (the scene, out of the template), `anchors.js`
  (the projection layer), `panels.js` (the window manager), the monitor's
  and the bench's widgets as modules under `apothecary/static/widgets/`.

### Phase 1 — Anchors: the world says what is in it  *(landed 2026-09-20, first slice)*

The viewer gains an anchor layer over its canvas and the first anchored
things. Nothing moves pages yet. Landed: `anchors.js`, the machine badges
(printers and devkits), the marks in the world (`machine_marks.js`, shared
with the monitor's board view), the browser test and the walkthrough page.
Still open in this phase: the devkit's *hello* on its badge (the listen
result is the firmware page's own state until Phase 4 shares it); the
`Machine` cell on a printer's node ring (Device › Monitor, `⌗22`, reaches
the monitor page today; Phase 3 gives it the popup); a jog sent from the
monitor page moving the world's nozzle ahead of the poll when both pages
are open (a cross-page event; Phase 3 makes it one page).

- `apothecary/static/anchors.js`: `mountAnchors(viewer)` keeps a layer of
  HTML elements over the canvas; `anchor(path, el, {offset})` binds one to
  a node's envelope (top centre by default); each frame projects the
  node's world point through the camera and sets a transform; an anchor
  behind the camera or out of frame is hidden; an occluded one is dimmed
  (a ray from the camera, tested against the scene's meshes, once per
  frame per anchor -- at most a dozen anchors, cheap). The viewer's
  `animate()` calls it; nothing reads layout.
- **Machine badges**: every pinned printer wears a badge above it --
  state, hotend/bed, SD or host progress, the job's stage -- fed by the
  polls the viewer already makes (`↻ Devices`, `siteDevices`, the Device
  section's poll). The Contents row's `🖨 210°/60° 43 %` badge stays; this
  is the same text where the printer is. Click: select the node.
- **Devkit badges**: a board pinned to a node wears what it is and the
  sketch last flashed to it; its hello once the bench's listen result is
  shared state (Phase 4).
- **The board in the world**: `board_view.js`'s drawing -- the nozzle
  marker that tweens and moves ahead of a jog, the bed relief, the build
  volume -- becomes a *decoration* the world scene attaches at a printer
  node (`decorations.js`, or a section of `world.js`), driven by the same
  `apothecary:position` / `apothecary:mesh` events. The monitor's small
  scene keeps using `board_view.js` until Phase 3 removes it.
- Census: the badge is a LIST-like surface (it moves attention, WHAT_YOU_SEE);
  classified, not hidden. Ring: `Machine` appears on a printer's node ring
  as a cell that, for now, opens the monitor page; in Phase 3 it opens the
  popup.
- Tests: a badge sits within 4 px of the node's projected top after the
  camera orbits; a poll on the simulator lands in the badge within the
  poll interval; a jog on the monitor page moves the world's nozzle (both
  pages open) within a frame; the walkthrough gains a page.

### Phase 2 — Panels: windows in front of the world  *(landed 2026-09-20)*

Landed: `panels.js` (register, open/close/collapse/float/dock, drag with
clamping, tabs for closed panels, per-browser memory, tethering with a
leader for Phase 3), the side column's five sections as docked panels,
`Panels ▸` on the canvas ring with a cell per panel and the resolver's list
held to the template's marks, the browser test, the walkthrough page. Not
done: the toolbar's `▣ Panels` button (the ring's cell and the tabs are the
ways back in; a button would be one more control of the page's own), and
a left rail in use (the manager has one; nothing docks there yet).

- `apothecary/static/panels.js`: a panel registry and a window manager.
  `register(id, {title, mount(el), unmount, where: "dock-left" | "dock-right"
  | "free" | {tether: path}})`; open, close, collapse, drag (pointer
  events, no library), z-order, remembered per browser (`localStorage`,
  wrapped); a tethered panel takes its position from an anchor and draws
  a leader line (one SVG line in the anchor layer).
- The Contents tree and the Selected panel become docked panels (the
  same markup, mounted by the manager), collapsible to a rail; Jobs
  likewise. The side column's CSS goes.
- `Panels ▸` on the canvas ring lists the registered panels in cells;
  the toolbar's `▣ Panels` button opens the same ring. Every panel action
  is a ring action (`panel:open:<id>`, `panel:close:<id>`), addressed.
- Census: the panel chrome (open, close, collapse, drag handle) is
  classified once, as the ring's chrome is; a panel's content is counted
  as what it was on its page.
- Tests: a panel opens within 300 ms, drags within bounds, survives a
  reload where it was left; nothing docked can shrink the canvas below
  half the window; the ring reaches every panel by address.

### Phase 3 — The machine in front of the world  *(landed 2026-09-20, first slice)*

Landed: `widgets/machine.js` and `machine.css` -- the monitor's whole body
as one module with two hosts (the monitor page as its body; the world in
a tethered popup opened from the badge or Device › Monitor), the comms
log as its own panel on the left rail, the ring's verbs carried to the
open machine, a jog from the popup moving the world's nozzle, the census
following widget imports and the meter counting a widget once. Not done
as planned: the module is one file with sections (status, chart, log,
control, bed, print) rather than six widget files -- the cut that keeps
the two hosts identical; split it when a host wants one part without the
rest. `board_view.js` stays on the monitor page until Phase 5 (the page
is not the world and still needs its own scene). The machine popup is
`Panels › Machine` on the canvas ring; the URL deep link
(`?machine=<port>`) is not done.

The monitor's content becomes modules, mounted by panels; the monitor
page keeps working on the same modules.

- `apothecary/static/widgets/`: `status-cards.js`, `temp-chart.js`,
  `comms-log.js` (with the query box), `control-pad.js` (the latched
  overlay: heaters, fan, home, jog, SD, motors, stop, arm/disarm),
  `bed-level.js`, `print-here.js`. Each `mount(el, {base, port, bus})` and
  `unmount()`; state per port lives in one `machine.js` store the page
  already has in spirit (`window.apothecaryMonitor`), now a module with
  the poll scheduler, the log chain, the latch and the two job watchers.
- The **machine popup**, tethered to the printer's node: cards, chart and
  the control pad behind the latch; bed level and print from here as its
  tabs; the comms log as a dockable panel of its own (it is long). Opened
  by the badge, by the node ring's `Machine` cell, and by the URL
  (`/viewer/sites/garage?machine=/dev/ttyUSB0`).
- `/firmware/monitor` is rebuilt on the same widgets in a plain layout --
  the same tests pass on both hosts -- and `board_view.js` goes, its
  drawing having moved into the world in Phase 1.
- Ring: the device and control rings are what they are today; the
  monitor's `carry()` becomes the machine store's, shared by both hosts.
- Census: the monitor's 64 controls are counted once, wherever they are
  mounted; the ring-backed share stays at or above 41 of 64.
- Tests: the printer suite runs against the world page as well as the
  monitor page (parametrised host); the bench checklist's steps are the
  same on both.

### Phase 4 — The bench in front of the world

- `widgets/toolchain.js` (install, cores, libraries), `sketches.js`
  (pick, compile, upload, esptool), `tasks.js` (the running task, cancel,
  history), `devices.js` (the cards, minus the board view -- the world
  shows the boards). Mounted as the **Bench** panel, docked right, and as
  `/firmware` in a plain layout.
- The device cards' verbs join the ring (a board's node ring gains
  `Probe`, `Identify`, `Live` where they apply), so the third screen's 30
  controls of its own get cells; the census's "no ring yet" goes.
- Tests: the firmware-page suite runs on both hosts.

### Phase 5 — One screen

- `/` and `/viewer/sites/{name}` are the app. `/firmware` and
  `/firmware/monitor` redirect into the world with the right panel open;
  the plain layouts are kept only if a person asks for a kiosk view, else
  deleted with their templates and their tests folded into the world's.
- The census counts one page; `PAGES` is one entry; the number is what
  survived and the docstring says what was retired and why.
- The docs walkthroughs become one (`tests/e2e/test_docs_one_screen.py`),
  the firmware doc's page-by-page sections become panel-by-panel; the
  bench checklist is re-run on the one screen.
- The draft record is proposed for ratification with the numbers filled
  in.

## What is decided here, and what a person decides

Decided by this plan (change it here, not in the code): the three kinds of
thing in front of the world; the world is never replaced; every action has
a cell; the old routes live until Phase 5; the census is the meter.

For a person: whether the plain layouts survive Phase 5 as kiosk views;
whether the Bench belongs in the world at all or stays its own page (the
plan says in the world, docked, since a devkit is a thing at a place too);
the record's ratification.

## Not in this plan

A second site on the screen at once; a browser other than Chromium in the
tests; rad's own record for tethered popups (the nine-cells record covers
rings; a popup is a panel, and a panel's verbs are ring verbs, so nothing
new is asked of rad); a mobile layout.
