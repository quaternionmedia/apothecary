# Changelog

All notable changes to Apothecary will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **The ring addresses nine cells, and the census knows what it backs** – the ring menu (`⌗ Ring`, `m`, or right-click a piece; on the monitor page, the port) adopts rad's *the menu addresses nine cells* record: options are seated on a numeric keypad, cardinals first (`8 6 2 4 9 3 1 7`), cell 5 always backs out, a digit chooses its cell, an arrow moves to the nearest occupied cell in that direction, and the digits pressed to reach an option are its address (`⌗2728` is Device › Control › Jog › Y+ from a printer's node). `POST /menu/resolve` returns every option with its cell; intents carry their address; the Device and Control rings expose every device verb the viewer's Device section and the monitor's control overlay have, and each of those buttons shows its ⌗ address. `apothecary census` now reads `templates/monitor.html.j2` too (`census.MONITOR`), names a control by the G-code line it carries when it has no name, and reports *N controls of its own, M of them also on the ring* (`RING_BACKED`, `Found.ring_action`): the viewer stands at 54 and 15, the monitor at 64 and 41. The ring navigates too: the canvas ring's **Pieces** lists the current level in groups of a keypad's worth and a digit selects a piece; **Up** steps out; the node ring's **Into** and **Up** walk the tree; the Contents rows and the zoom buttons wear their addresses. Governance: the draft *rad host integration for apothecary*, pending rad's own record.
- **Firmware toolchain seam** – `apothecary firmware` installs a checksum-verified `arduino-cli` into `~/.apothecary/tools`, validates it, installs cores (ESP32/ESP8266/RP2040 board-manager URLs added automatically) and libraries, discovers sketches under `parts/<name>/<name>.ino` (optional `firmware.json` sidecar for default FQBN/libraries), compiles and uploads, and esptool-flashes raw Espressif binaries. The `/firmware` page does the same from the GUI with polled task output; `/firmware/*` API routes return task ids. Both engines are invoked over a subprocess seam, never linked — see the *Firmware toolchain seam* decision record.
- **Device identity and expected-vs-observed firmware** – `apothecary firmware devices|probe|listen` and the `/firmware` Devices panel: esptool probe (chip, revision, MAC, flash size), a persisted record of what apothecary last flashed to that MAC (with "source edited since" / "newer build never uploaded" drift flags), and the sketch observed announcing itself over serial (`apothecary <name>: hello`, printed at boot and periodically). Records live in `~/.apothecary/firmware-state.json`.
- **Live serial log** – `GET /firmware/devices/stream` (SSE over `arduino-cli monitor`), shown inline on the firmware page and as a toggleable terminal overlay in the fractal viewer ("⌨ Serial log"). Monitors are stopped automatically before any upload needs the port. A baud-rate token bucket drops bytes a USB-UART bridge replays (seen on a CP2102) and reopens a wedged port.
- **G-code printer seam** – a 3D-printer mainboard running Marlin (or RepRapFirmware, Klipper, Prusa) is monitored, not programmed: `apothecary firmware printer PORT` identifies it (`M115`), polls temperatures/position/endstops/SD progress, and runs report-only queries (`--query M503`; an allowlist refuses anything else). The port is held open and reset only on request (`--reset`), because DTR-on-open resets Creality boards and would kill a print. Transport is a swappable engine: pyserial (new dependency), stdlib `termios`, or an in-process **simulated printer** for demos and browser tests. See the *G-code printer seam* decision record.
- **A printer drives its scene node** – each garage printer now carries a `mainboard` node inside its base enclosure (`printer_1.frame_system.mainboard`); pin a printer's port there (`PUT /sites/{name}/nodes/{path}/device`, or the viewer's Device panel) and every poll writes `idle`/`printing`/`offline` into the status of the nearest status-bearing ancestor — the printer Structure; a hand-set `maintenance` is never overridden. The printer's Contents row and Device section show the board's state "via" the board. `GET /sites/{name}/devices` carries the last poll per binding.
- **Device panel and repolling in the viewer** – the Selected panel's Device section: pin from detected ports or by typed identity (`/dev/ender`, a MAC), Query (M115 without pinning), Poll now, Watch (opens the serial overlay, which polls a printer every 2 s instead of streaming it), Unpin, Rescan; live badges on Contents rows; **↻ Devices** auto-refresh on a schedule. Polls update the panel in place so an edit in progress is never lost; the `arduino-cli` port scan is cached for 2 s.
- **Focused printer monitor** – `/firmware/monitor?port=…`: status cards, a temperature history chart, and the port's server-side **comms log** (every command/reply/boot line/link event, tagged by origin, surviving reconnects and reloads) with a query box; Poll, Reconnect, M115, Reset (confirmed), Release. Linked from the viewer, the overlay and the firmware page.
- **Latched printer control** – the monitor's ⚙ Control toggle arms a per-port latch (five minutes of activity, server-side, dropped with the link) and opens an overlay: heater targets, fan, home, jog pad, motors off, SD start/pause/abort, mesh on/off. Commands come from a bounded allowlist (`gcode.CONTROL_CODES`; temperature and travel caps) and are refused with `409` unless armed; `M112` E-STOP always goes. The simulated printer honours the controls so the effect shows in the next poll.
- **Printing without an SD card** – the monitor's Print from here card keeps a sliced G-code file on the host (`~/.apothecary/prints/`), checks it before anything is sent (`gcode.check_gcode`: no `M500`/`M502`/`M997`/`M999`/`M112`/`M0`/`M1`, no temperature over the seam's caps) and streams it to the printer one line per `ok` as a job (`devices.PrintJob`; latch required, confirmed once). Polls keep coming between lines (`GcodeLink.command(wait=…)`, `LinkBusy`), heaters and fan stay in reach, motion and the SD card are the job's, and release/reconnect/reset/upload on that port answer `409` until it ends. Pause stops the feed, Resume needs the latch, Cancel and any failed line send the safe-off (`M104 S0`, `M140 S0`, `M107`, `M84`); E-STOP ends it with nothing more sent. The stream stays out of the comms log (start, every 500 lines, objections and the end are logged); every print is a record with its outcome (`GET /firmware/printers/print/records`). Routes: `GET/POST/DELETE /firmware/printers/prints`, `POST/GET /firmware/printers/print`, `POST /firmware/printers/print/{pause,resume,cancel}`. On the ring the Control ring's SD cell is now **Print** and carries Resume/Pause/Abort to whichever print is running, with **Send file** (`⌗794`) starting the chosen one; the simulated printer honours `M109`/`M190`, `G92` and dwells on `G4`.
- **The rail resizes, hides on tilde, and moves** – the panel rail has a head of its own: drag its inner edge to set its width (220 px to half the page), press `` ` `` / `~` to hide and show it (never while typing; a tab stands in for a hidden rail), drag its grip across the page or press ⇄ to move every panel in it to the other side; a docked panel's body has a height you drag, a free panel resizes from its corner. The canvas ring's Panels cell gains **Rail**. Remembered per browser; browser test with bounds.
- **The machine in front of the world (one screen, phase 3)** – the monitor's whole body becomes a module, `apothecary/static/widgets/machine.js` (`mountMachine(root, {base, port, host, logRoot})`), with its stylesheet `widgets/machine.css`: the monitor page mounts it as its body, and the world mounts it in a panel tethered to the printer when its badge is clicked or the node ring's Device › Monitor is chosen -- the same ids, chain, latch and confirms on both hosts, the comms log as a panel of its own on the left rail, a jog from the popup moving the world's nozzle ahead of the poll, the ring's control verbs carried to whichever machine is open, and a drag letting go of the tether. The census counts a widget module as part of every page that mounts it (each entry says its source) and the three-screen meter counts it once: still 148 / 60. The simulated printer's SD print now goes round instead of ending, so a long browser session still finds it printing. Browser test with bounds; the walkthrough gains a page.
- **Panels in front of the world (one screen, phase 2)** – the viewer's side column becomes a rail of panels (`apothecary/static/panels.js`): Contents, Selected, Jobs, Layout Validation and Generated OpenSCAD each close to a tab, collapse, float free and drag by their title bar (clamped to the page), dock back, and are remembered per browser; a rail can never take more than a third of the page. The canvas ring gains **Panels** with a cell per panel (`panel:toggle:<id>`, `⌗98` is Contents at the root); the resolver's list and the template's `data-panel` marks are held to each other by a test. A tethered panel (following an anchor, with a leader line) is in the manager for the machine popup to use next. Browser test with bounds; the walkthrough gains a page.
- **The docs are served with the viewer, and refreshed on start** – `/docs` renders `docs/` and `/walkthrough` renders `walkthrough/` (a small Markdown renderer written in `apothecary/docs_site.py`, no dependency; screenshots, GIFs, recordings and G-code files served as they are; relative links work because the URL is the path). `apothecary serve` and `apothecary dev` run `apothecary docs generate` in the background as they start, so the generated walkthroughs are current after a restart; the bar on every docs page says whether that run is going or how it ended (`docs/generated/.refresh.json`, `refresh.log`); `--no-refresh-docs` skips it. The API's Swagger page moves to `/api/docs`.
- **The world wears its machines (one screen, phase 1)** – the fractal viewer gains an anchor layer (`apothecary/static/anchors.js`: HTML fixed to a point in the scene, re-projected every frame with no layout reads, hidden out of frame, dimmed when occluded) and the first anchored things: a **badge above every pinned, connected board** -- a printer's state, hotend and bed, progress and job stage; a devkit's identity and last-flashed sketch -- fed by the same rows the Contents badges read, following the machine as the camera moves, a click selecting it; and a printer's **marks in the world** -- the nozzle marker tweening to each poll, the bed plane, the newest bed reading as a relief -- at the printer's node, from `apothecary/static/machine_marks.js`, which the monitor's board view now draws with too. Browser test with bounds (to the pixel after a pan, within the poll interval); the walkthrough gains a page.
- **The census counts the third screen, and the one-screen plan begins** – `apothecary census --page templates/firmware.html.j2` counts the firmware page (30 controls of its own, 4 on the ring, no ring yet; a class that only says how a control looks, `small`, `primary`, does not name one), so the three screens have one meter: 148 controls of their own, 60 on a ring. `docs/plans/one-screen-2026-09-20.md` plans the world as the one screen with anchors, tethered popups and panels in front of it, in six phases; the draft record *One screen* is on the governance branch.
- **The bed reading drawn in the world** – the board view on the monitor page and on the firmware page's device cards lays the shown reading over the bed as a relief: a surface through the probed points, its lowest point on the bed, stretched ×10–×50 (said in the note) so a few millimetres of tilt are visible, in the heatmap's two hues, with corner posts down to the bed; placed on the probeable area the probe offset leaves (Marlin's default inset), since Marlin prints the grid without positions. `mountBoardView(...).setMesh(record)` / `.mesh()`; the monitor dispatches `apothecary:mesh` whenever the shown reading changes. `GET /firmware/printers/where` now answers on a fresh server before any page has loaded the site.
- **Bed leveling, read and recorded** – the monitor's Bed level card: **Read mesh** saves the board's stored mesh (`M420 V`), probe offset (`M851`) and temperatures as a *bed reading* without moving; **Probe bed** homes and probes (`G28`, `G29`; latch required, confirmed once) as a job that holds the port for the minutes it takes (polls report the stage without queueing, queries and controls answer `409`, E-STOP still goes). Readings are drawn as a heatmap with range, tilt and each corner against the mean, kept under `~/.apothecary/leveling/` with every line the firmware said, and listed per port newest first (`POST/GET /firmware/printers/level`, `GET /firmware/printers/leveling[/{id}]`). Four corner buttons move the nozzle to paper height at each corner for a tramming check. On the ring, Control › Level is seated so the keypad is the bed (`⌗741` front left, `⌗748` Probe); `G29` and `G30 X Y` join the control allowlist. `gcode.parse_meshes` reads Marlin's grid, its subdivided grid and `M503`'s `G29 W` points; the simulated printer answers all four codes with a tilted, bowed bed.
- **The board drawn in its printer** – the monitor page and the firmware page's device cards draw a pinned board where it sits (`apothecary/static/board_view.js`, from the same STL routes the viewer uses): the printer translucent, the board solid, the build volume on the printer's base, and a nozzle marker that tweens to each polled position and moves ahead of every jog. `GET /firmware/printers/where` answers the site, node, positions and volume a view needs.
- **Printer walkthrough docs** – `apothecary docs generate` now runs its server against scripted ports and the simulated printer (`--real-devices` to opt out), so `docs/generated/printer-monitor/` is identical on every machine; Playwright tests with timing bounds (`tests/e2e/test_printer_ui.py`) hold the UI to its cadence.
- **`parts/esp32_blink`** – smoke-test sketch for classic ESP32 devkits (verified on ESP32-D0WD-V3): blinks GPIO 2 and self-announces over serial.
- **Git submodules command** – `apothecary submodules` to init/update external dependencies
- **Gridfinity integration** – Parametric storage bin wrapper for gridfinity-rebuilt-openscad
- **OpenSCAD Nightly detection** – Auto-detect development builds for parts requiring newer syntax
- **Part STL customization** – Parts can define custom STL output paths and OpenSCAD requirements
- **Fractal `Assembly` model** (prototype, unratified) – Site/Structure/Substructure/Feature collapsed into one generic recursive class (`apothecary/hierarchy.py`); depth is unbounded rather than four fixed levels
- **Revision/diff building blocks** (prototype) – `apothecary/revisions.py`: `Revision`, `RevisionGraph` (branching history), `diff_assemblies` (path-addressed structural diff) — first slice toward planning/comparing design iterations, no compositing/merge yet
- **Fractal zoom viewer** (prototype, unratified) – `/viewer/sites/{name}` navigates any registered site's Assembly tree at any depth with standardized controls (click to select, double-click or scroll-past-resistance to zoom in, one zoom-out control) and an abstract depth-ladder minimap
- **Parts library as a fractal tree** – the registered `parts/` library is migrated in as leaf `Assembly` nodes (`apothecary/example_parts_library.py`, new `part_ref` field), reachable by zooming into the `parts_library` site instead of a separate parts browser
- **Real geometry in the fractal viewer** – placeholder boxes upgrade in the background to real geometry: a leaf's own Cube/Cylinder/Sphere renders as an exact Three.js primitive (`_primitive_descriptor` in `api.py`), and a `part_ref` leaf loads its real OpenSCAD-rendered STL, generating it on demand if missing.
- **Garage scene expanded** – a building shell (four walls, a door opening, a window opening), abstract utility fixture stubs (lighting/HVAC/electrical/fluids, each a housing plus one "output" Feature), a storage shelving stub, and a floor-standing CNC router stub (subtractive manufacturing, deliberately not wired into the job queue) — all simple stubs left for further development, not modeled in functional detail. The garage floor plan is 6000mm × 6000mm (doubled from the original 3000mm × 2300mm) so the equipment reads as furnishing a real garage, not shrink-wrapping one.
- **Real geometry for composite nodes** – `GET /sites/{name}/nodes/{path}/stl` renders any addressable Assembly node's own subtree through the same OpenSCAD CLI pipeline `/parts/{name}/stl` already uses, cached by content hash; the fractal viewer's wave-loading seam now upgrades composite nodes (walls, whole Structures), not just leaves, to real geometry. A container with no footprint of its own (e.g. the garage building shell) falls back to the envelope of its descendants' bounds for camera framing and placeholder placement.
- **Subsystem category coloring** – `Assembly.category` (inherited from the nearest tagged ancestor, resolved server-side in `_assembly_tree`) tags each top-level garage Structure as wall/furniture/mechanical/fluid/electrical; the viewer colors every node by its resolved category instead of a single hardcoded workbench-brown special case.
- **Snap-to-grid** – dragging a node snaps to a 50mm grid by default (three.js `TransformControls.setTranslationSnap`), toggleable from the toolbar.
- **Hierarchy tree selector** – the Contents panel is a full expandable/collapsible tree of every descendant beneath the current focus (not just direct children), each row showing whether it's currently rendered in the 3D view; per-subsystem category chips expand just one subsystem's subtree at a time, replacing the single all-or-nothing "show all levels" toggle.
- **Doc-generation videos** – `apothecary docs generate` now extracts each doc-workflow test's actual Playwright screen recording (previously discarded) into `docs/generated/<workflow>/<workflow>.webm` and embeds it in the workflow's Markdown alongside the existing step-screenshot GIF.
- **Elephant walk** – `apothecary parts elephant-walk` generates a preview file with all parts arranged in a line, using bounding boxes to prevent overlap
- **Dev command** – `apothecary dev` for quick development workflow (generate STLs + start server)
- **STL rendering** – OpenSCAD CLI integration for SCAD→STL conversion
- **STL API endpoints** – `GET /parts/{name}/stl`, `POST /parts/{name}/stl/generate`
- **OpenSCAD status endpoint** – `GET /openscad/status` to check availability
- **PartFiles data model** – Links SCAD/JSCAD/STL files with status tracking
- **`apothecary test all`** – Combined test runner with aggregate summary
- Three.js-based 3D viewer with real STL geometry loading
- Viewer download/open dropdowns for SCAD and JSCAD files
- Loading overlay with blur effect during STL generation
- `QUICKSTART.md` for rapid onboarding
- `CONTRIBUTING.md` with development guidelines
- Documentation index at `docs/README.md`
- Comprehensive E2E tests using Playwright

### Changed
- **`/sites/{name}` payload** – gains an additive recursive `tree` key (the whole Assembly tree, including additions/subtractions) alongside the existing flattened `structures` list
- **Calibration cube** – Default size reduced to 10mm, labels as relief (not extruded), axes preview-only
- **Parts reorganized** – Each part now has its own folder (`parts/<name>/<name>.scad`)
- **Viewer renders actual STL** – No more placeholder geometry; auto-generates if missing
- **Root redirects to viewer** – `/` now redirects to `/viewer` with elephant_walk as default
- Refactored viewer into Jinja2 template + dedicated module
- Registry scanner updated for new folder structure
- Reduced `api.py` from 827 to ~450 lines

### Removed
- **Standalone parts browser and Site/Structure hierarchy viewer** – `templates/viewer.html.j2` and `templates/site_viewer.html.j2`, along with `/viewer/random` and `/viewer/parts/{name}`, absorbed into the fractal zoom viewer (`/viewer` now redirects to it)
- `render_context.py` (orphaned, unused)
- `openscad_framework.py` (deprecated compatibility shim)
- `star_cookeicutter.py` (legacy misspelling)
- Legacy JSCAD viewer endpoints (`/viewer/ui/*`, `/css/*`)
- `_require_viewer_root()` helper (no longer needed)
- `E2E_SETUP.md` (consolidated into CONTRIBUTING.md)

### Fixed
- **The pyserial engine dropped DTR on close, so the next open rebooted the board** – seen on the bench with the Ender's FTDI: the kernel's `HUPCL` default hangs up on close, and only the termios engine cleared it. Both engines now clear it on open (`gcode.keep_dtr_on_close`); server → CLI → server reopen the port with no boot banner. The first open after a plug-in still resets the board (the bridge comes up with DTR dropped), and the docs say so.
- **A pin by port broke when the kernel renumbered the port** – the printer came back as `/dev/ttyUSB0` after a night as `/dev/ttyUSB1`. A pin of a detected port is now kept as the board's own identity (MAC, else the USB bridge's serial number), and every place a pin is matched to a port (`bindings.same_device`: the bindings view, the board view's `where`, the status sync) accepts the serial number, a MAC, the port, or a path that resolves to the same device (`/dev/serial/by-id/…`, a udev name). A serial number is a valid typed identity in the Device section.
- **The board view drew the printer's shape a bench-width away** – a node's STL arrives in its parent's frame (a printer on the bench at x 100–400), and the view placed it untranslated; the board was offset twice. Each body is now centred and placed at its envelope, as the fractal viewer does, and the browser test checks the printer encloses its board and its build volume.
- **Fractal viewer: world position was only ever one level deep** – `Assembly.world_bounds()`/`api.py`'s tree serialization only offset a node by its own `position`, not its accumulated ancestor chain, so anything nested more than one level below a site's direct children rendered as if its parent were sitting at the origin. Fixed by threading cumulative world position through `_assembly_tree`'s recursion — the root cause of camera framing looking "too zoomed in and not centered" once you zoomed past the first level.
- **Fractal viewer: camera framing and grid size** – framing now considers all three axes (not just the horizontal footprint) and targets the true 3D center instead of an arbitrary height guess; the grid/axes helpers resize to match whatever's actually in view instead of a fixed 2000mm grid, often far too small a few levels deep
- **Fractal viewer: real geometry rendered rotated 90 degrees** – a loaded STL's raw vertex data is in apothecary's own (x, y, z) z-up frame; every other object in the scene is positioned via the (x, z, y) y-up axis swap `boxFromBounds` documents, but the loaded mesh's own geometry never had that swap applied, so its "up" landed on three.js's depth axis instead of its up axis. Fixed by applying the same swap to the loaded geometry (plus a matching triangle-winding reversal, since the swap is a reflection, not a rotation, and would otherwise shade every face inside-out).
- **Fractal viewer: moving any item corrupted every real-geometry mesh on screen** – `rebuildSingleMesh` unconditionally re-scaled a node's mesh by its real-world millimeter size after every position edit, which was harmless for a still-placeholder box (a unit box stretched via `mesh.scale`) but ballooned an already-upgraded real-geometry mesh (already actual-size, scale left at 1) into a screen-filling artifact — for *every* currently-rendered node, not just the one being moved, since this ran once per node on every layout submit. Fixed by tagging placeholder meshes explicitly so only they get re-scaled.
- Viewer loads without console errors
- Parts dropdown properly populates on page load
- `.gitignore` no longer lists tracked `parts/` folder

## [0.1.0] - 2026-01-02

### Added
- Initial release
- Core primitives: `Cube`, `Sphere`, `Cylinder`
- Boolean operations: `Union`, `Difference`, `Intersection`
- Transform operations: `Translate`, `Rotate`, `Scale`
- `Scene` model with `render()` and `render_jscad()` methods
- FastAPI server with REST API
- CLI with commands: `render`, `templategenerate`, `parts`, `serve`, `inventory`
- Parts registry with wrapper system
- Jinja2 template support
- Example parts: parametric star, V-slot, dryer knob, solder fan mount

---

## Release Notes Format

### Added
New features and capabilities.

### Changed
Changes in existing functionality.

### Deprecated
Features that will be removed in upcoming releases.

### Removed
Features removed in this release.

### Fixed
Bug fixes.

### Security
Security-related changes.
