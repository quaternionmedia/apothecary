# Apothecary documentation

`apothecary serve` serves this folder at `/docs` and the walkthrough at
`/walkthrough`; links between pages work because the URL is the path. The
root [README](../README.md), with the map of what the browser suite walks, is served
at `/README.md`, and every page's bar links it. The HTTP API is described at `/openapi.json`, the commands by `apothecary --help`.

## The walkthrough

`walkthrough/` is the path through this repository. Pages 01 to 06 and 18 are
written by the browser tests that walk them; page 00, pages 07 to 17 and page
19 are doctests, run by `pytest walkthrough`. Start there, at page 00.

| Page | |
|---|---|
| [00 — Getting started](../walkthrough/00-getting-started.md) | Install, `apothecary check`, `apothecary openscad install`, `apothecary serve --demo`; the four loops and what each needs; the optional installs |
| [01 — Photographs into pieces](../walkthrough/01-photographs-into-pieces.md) | A photograph becomes named, placed pieces in the viewer; written by its own run |
| [02 — The bench as it is](../walkthrough/02-the-bench-as-it-is.md) | Geometry from elsewhere, the printer and boards drawn as they are, a camera added above the bench; written by its own run |
| [03 — A picture to a print](../walkthrough/03-a-picture-to-a-print.md) | A camera's picture, its shapes, a piece made and adjusted, sliced for printer_1, and a print job for it there, twice round through the page; written by the browser suite |
| [04 — Designing a part](../walkthrough/04-designing-a-part.md) | A part's size moved, checked, applied and drawn in its tab, OpenSCAD's refusal by line, the saved part again for nothing, round twice and in two tabs; written by the browser suite |
| [05 — Firmware](../walkthrough/05-firmware.md) | A sketch chosen, built, flashed to the ESP32 devkit and heard saying its hello in the board's Machine, the Arduino esp32_blink then the Rust one; written by its own run, in the browser suite |
| [06 — Editing a part's SCAD](../walkthrough/06-editing-a-parts-scad.md) | A part's SCAD edited in its SCAD window, a failing line marked, a change rendered once its check passes and saved as a variant in git, the editor fullscreen, round twice; written by the browser suite |
| [07 — The parts registry](../walkthrough/07-a-part.md) | What a part is, and how its envelope is checked |
| [08 — Which numbers are whose](../walkthrough/08-fitting.md) | The seam, and driving it with overrides |
| [09 — Navigating a sub-assembly](../walkthrough/09-an-assembly.md) | datum_core as an addressable tree |
| [10 — Serving it](../walkthrough/10-serving-it.md) | The API and the viewer |
| [11 — Contested numbers](../walkthrough/11-contested-numbers.md) | Numbers the sources disagree about, and turning them in the viewer |
| [12 — Ready to build](../walkthrough/12-ready-to-build.md) | Whether a part can be printed and checked against a real one |
| [13 — Status and progress](../walkthrough/13-status-and-progress.md) | One vocabulary for how the CLI reports state |
| [14 — Problems and solutions](../walkthrough/14-problems-and-solutions.md) | What is unresolved, who can close it, and what exists to close it with |
| [15 — Running the checks before pushing](../walkthrough/15-preflight.md) | `apothecary preflight`: each CI workflow, run here before a push |
| [16 — Being depended on](../walkthrough/16-being-depended-on.md) | What a consumer pinning this repository is entitled to |
| [17 — A part that computes itself](../walkthrough/17-a-part-that-computes-itself.md) | The airgap: a part whose SCAD computes its surfaces from its assignments, the Python mirror that declares its envelope, and the metrics document its panel says |
| [18 — The working space](../walkthrough/18-the-working-space.md) | A site as its evidence has it and a printer's hour in it, from each of its doors: three cameras added above printer_1, each told its device in its row, a frame set kept with a poll and opened beside it, the budget set; written by the browser suite |
| [19 — The router](../walkthrough/19-the-router.md) | The garage's CNC router, an AnoleX 4060-Evo Ultra 2: its working area on its table, GRBL's dialect read and bounded, the simulated controller identified, polled, driven and stopped |
| [20 — A part through the router](../walkthrough/20-a-part-through-the-router.md) | The subtractive loop on one part: the coupon's declared cuts, its toolpath written and checked, kept and cut from here with the work zeroed, the job naming its operation, the cut measured against the design, and the design changed and cut again |
| [21 — A toolpath, previewed](../walkthrough/21-a-toolpath-previewed.md) | One interpreter and two processes: a print's layers and a cut's passes read through one core, held to the toolpath's own writer, and a design change seen in the moves |
| [22 — The irl family's hub](../walkthrough/22-the-irl-hub.md) | apothecary as the family's hub on hearth's contract: what it says it is, its table, a fire and what is kept |

## Guides

| Page | |
|---|---|
| [The dev loop](dev-loop.md) | Change, see, test, commit, integrate: a command for each step, two servers at once on two ports, what others pushed brought into a checkout, and a change brought into main |
| [The viewer](viewer.md) | The page's own controls: the header and ⚙ View, the world and its faded walls and badges, the ring and its addresses, the windows, the part editor and the SCAD editor, the keys |
| [Windows and focused systems](windows-and-systems.md) | For an author: a window of the page -- where it opens, what a browser remembers, an empty one -- and a focused system's registry entry, its widget's hook, and the tests that hold each |
| [The family's hub](family.md) | apothecary as the `irl` family's hub on hearth's contract: its routes, its table, what goes through it and how `hearth check` judges it |
| [Lighting](lighting.md) | A site's lighting rig -- fixture types, a patch, live levels -- the theatre site that uses it, another console's exports in its place, and a console's levels by sACN or OSC |
| [OpenSCAD](openscad.md) | Installing a snapshot with Manifold on each platform, which OpenSCAD a render uses, what 2021.01 cannot do, how many run at once |
| [Scene JSON format](scene-json.md) | Scenes, primitives, booleans and transforms as JSON |
| [Parts authoring](parts-authoring.md) | How to add a part, override its parameters, and check it |
| [Fitting a part](fitting-a-part.md) | The seam between a consumer and this repository as built: black boxes, a part's parameters and the validator, a gate per pair of descriptions, the pin, and who owns each open problem |
| [Geometry models](models.md) | Vectors, bounds, colors, shapes and units |
| [Geometry made elsewhere](geometry-from-elsewhere.md) | An STL or OBJ as a part (`apothecary parts import`), and a part described by a sidecar |
| [The Working space](working-space.md) | A site as its evidence has it: a printer's polls kept as observations, the frames its cameras keep with them under a budget, the window that shows both, and the doors that read them |
| [Pictures, cameras and pieces](pictures.md) | Where pictures live, a camera as a part of the site, a picture pinned as a view, its shapes made into pieces, what is taken back and how, the `photo` commands |
| [The census](census.md) | What `apothecary census` counts of the viewer, how each control and listener is classified, ring-backed and taken back, and the ceiling and floor a change to the page keeps |
| [Configuration](configuration.md) | Every `APOTHECARY_*` variable, and the tool variables, each with its default and the page that explains it |
| [Firmware](firmware.md) | Programming boards from sketches kept with their parts, Arduino and Rust for the ESP32, from the Bench or a board's Machine; monitoring a G-code printer from its scene node |
| [The router](cnc.md) | The garage's CNC router beside the Ender: the AnoleX 4060-Evo Ultra 2 as a part on its stand, its Grbl_ESP32 controller as the node a port is pinned to, GRBL's dialect of the machine seam -- identified, polled, driven within bounds, stopped, a cut streamed -- the simulated controller, and what is not built |
| [The toolpath preview](toolpath-preview.md) | Where a file's tool goes, drawn in the world before anything is sent: one core for a print and a cut, its two instantiations, what else reads through it, the route and the card's slider |
| [The toolpath](cam.md) | The router's toolpath, written from the cuts a part declares: what a part says, what the toolpath does, how it is kept, recorded and offered, and the cut measured as cut |
| [The slicer](slicer.md) | OrcaSlicer installed and pinned, the printer's profile kept with its part, a part or a made piece sliced for the pinned printer and kept for the Print card |
| [The Airgap](airgap.md) | The `airgap` part -- a rotor/stator pair computed in its SCAD -- and the Airgap panel: the part as a field, torque and dynamics model that follows its text in the editor, its verbs on the ring, its rig and sweep as documents, and the metrics document Python reads back |
| [The bench checklist](bench-checklist.md) | The Ender 3, an ESP32 and the router for real: pinning, the link, heat, motion, levelling, printing from here, slicing, the emergency stop, the Rust and Arduino blinks, and the router's homing, jogs, spindle, zero, probe and a cut |
| [The models checklist](models-checklist.md) | Image models through qmcp by hand, against the simulated qmcp: the Models window, asking about a shape, a person's word, switching an origin off, and each way qmcp can be missing |

## The Rust workspace

`crates/` is a Cargo workspace of two stubs, which neither the suites nor CI
build (CONTRIBUTING.md says how to check them). Each README says what the
crate is for:

| Crate | |
|---|---|
| `crates/apothecary-core/README.md` | A Rust core inside Python, by PyO3 and maturin, for the hot paths a profile names |
| `crates/apothecary-service/README.md` | A Rust service beside `apothecary serve`: the serial and printer daemon, or a renderer without OpenSCAD |

`apothecary kernel-reference` renders the kernel corpus with OpenSCAD's
Manifold and prints what it measures, case by case: the reference a Rust
geometry kernel is compared with (`tests/test_kernel_comparison.py`; the
2026-10-09 [survey](plans/rust-geometry-kernels-2026-10-09.md) says which
kernel to try first).

## Plans

Open plans: each says what is decided and what is not built.

| Page | |
|---|---|
| [A part through the subtractive loop](plans/subtractive-loop-2026-11-04.md) | The loop the app is built around from here, on the router beside the Ender: a part's declared cuts, the app's own toolpath, Cut from here, the cut's operation named, the simulated router's footprint measured and one iteration executed (built); then the bench, then the cut watched |
| [Pictures in the world: what is open](plans/pictures-the-rest-2026-10-13.md) | Gathering out of core as an extra, and the old photo routes closed: the two phases of the pictures plan not built |
| [The shape finder, with a model behind it](plans/photo-finders-local-models-2026-09-21.md) | Optional local models behind the photo finder: the seam, the plugin shape, what reach is lawful, the phases |
| [Image models through qmcp](plans/image-models-through-qmcp-2026-10-30.md) | Image models as an always-optional source of measurements, served by qmcp on this machine: the vision tools' contract, observations beside the plain readers' and never over a person's word, how each degrades, which come first and how each is measured, qmcp's own slice, the records and the owner's questions |
| [Iterating on a part, tightened](plans/part-iteration-2026-10-12.md) | The part and SCAD loops reviewed and timed, and this round built: errors as failed renders, real controls, kept work, OpenSCAD's keys, variants drawn where they stand, history, compare, variant management; its next phase written out |
| [Governance, brought up to the corpus](plans/governance-2026-10-13.md) | The audit of apothecary's governance and audit documents against the corpus, and what is decided: the guard's install points, licence conflict rows, the serial removed, drafts, the bench checklist |
| [Reviewed: the systems, the tests and the docs](plans/review-2026-10-24.md) | The whole read once for gaps at the top of the stack: safety, the code's shape, what the tests run and where, their duplication and time, the docs against the page, and what stands on origin; each gap with its evidence and a next step |
| [A review cycle at ten times the requests](plans/review-cycle-2026-10-24.md) | How requests are reviewed and landed, measured, and a proposed cycle that holds at ten times as many: machines gate a request and its author merges it, a merge queue tests batches once, releases are reviewed by area at a tag, stacks stay shallow, shared files are split |
| [Focused systems](plans/focused-systems-2026-10-22.md) | The Airgap as the standard for a focused layout, the Part and the Machine on it, one registry every system is configured through, and Board, Lighting, Fit and build and Bench after them |
| [The documentation, swept](plans/timeless-docs-2026-10-12.md) | Every durable text brought under the governance record on durable text: present tense, no internal history, no ornament; the triage by area and the order; its notes on each area in [its folder](plans/timeless-docs-2026-10-12/) |
| [The bench as a rig carlos can draw](plans/qm-family-carlos-2026-10-29.md) | Carlos, in the instruments family, holding and drawing the bench as apothecary sees it: the bench written as a `carlos.patch` with each board's and lead's state and sent whenever it changes (built, with a demo), a picture naming a device, IO configuration, and carlos's one action |
| [A synth rig photographed through a concert, held in carlos](plans/carlos-concert-rig-2026-10-29.md) | Carlos's rigs, bolstered from apothecary: each knob, fader, switch and socket read off a camera's picture against carlos's own panels and held in carlos frame by frame through a concert, turned in place, with a test of both apps end to end (built, on drawn pictures); the first real photographs, power and USB into an Uno; then the airgap's test rig and a server room |
| [A working space, seen from every kind of evidence at once](plans/working-space-view-2026-10-30.md) | One view of a place (what is here, what state it is in, how it is known, what changed) from its cameras (one thing from several angles among them), ports and polls, sensors, a person's goals, directives and actions, and optional image models, every line opening its evidence and every disagreement kept; first the Ender's three cameras (on the bed for its timelapse, on the head, across the room) tied to its polls; not built |
| [One page for two machines](plans/ui-refresh-2026-11-04.md) | A round of unification and polish from a walk of the demo with the router beside the printer: the kinds' words in one module, one badge grammar, a section's title by kind, the card in the loop's order, Selected's shape, the Working space on any machine, the palette in one sheet (built); what it left, and why |
| [One page for every effort](plans/ui-coordination-2026-10-31.md) | The viewer's windows, doors and words across the efforts in flight (the Working space, the image models, the rig's faces, the bench in carlos, lighting, pictures): where they collide, one observation module, and the order the collisions are settled in. |
| [An irl hub of ShowRunner's class](plans/irl-hub-2026-11-02.md) | Apothecary as hearth's second exemplar: a procedure of steps on a blueprint in place of a cue list on a script, each step's family block delivered over `family/1` to the printer, the boards and the cameras hosted in the hub and to carlos, joe with vox, alfred with otto, datum, ira and ShowRunner beside it, every outcome kept in the evidence log; each member's verbs, what it has and what it needs, the order of the work and the owner's questions; not built |

## History

Plans and research that are finished, newest first. Each is a dated record
of what was decided and why; what is still true of it is stated in the
guides above, the governance records, or the code it describes. A plan
whose work is done leaves the table above for this list.

- 2026-10-20 — [Landing the stack on main](plans/landing-the-stack-2026-10-20.md): every open pull request and the governance records it pins, reviewed once as a whole and merged into `main` bottom first, the order checked by merging each branch in turn; what is still open of its *After* is in [todo.md](../todo.md).
- 2026-10-12 — [The pointer, the keys and the ring](plans/input-2026-10-12.md): right-click the camera's and Ctrl+right-click the ring's, Page Down and Page Up stepping levels, automatic zoom's settings, one Settings panel, and every input of the page mapped and made to agree.
- 2026-10-11 — [Onboarding at the top of the stack](plans/onboarding-2026-10-11.md): a newcomer's path, the docs, the suites and the pictures reviewed; `serve --demo`, a Getting started page, one ordinary test command, pictures held to their captions.
- 2026-10-10 — [A managed slicer](plans/slicer-2026-10-10.md): OrcaSlicer behind a slicer interface, installed like OpenSCAD, the printer's profile kept with its part, print settings from what each part declares.
- 2026-10-09 — [A Rust geometry kernel](plans/rust-geometry-kernels-2026-10-09.md): a survey of which Rust kernel could render scenes to STL without OpenSCAD -- Manifold bindings, csgrs, boolmesh, truck, Fornjot, OCCT -- by licence, build, coverage and maturity; Manifold's bindings first.
- 2026-10-08 — [The loops through the page](plans/ui-flows-2026-10-08.md): designing a part, editing its SCAD, firmware, and a picture to a print, each built out and held end to end by a browser test.
- 2026-10-08 — [Rust](plans/rust-2026-10-08.md): firmware in Rust for the ESP32 behind modular toolchains, a Rust geometry kernel researched and compared by numbers, a Rust service and core stubbed.
- 2026-10-08 — [Cleanup, triaged](plans/cleanup-triage-2026-10-08.md): the open cleanup items sorted by kind and given an order, while the review branch was split into a stack.
- 2026-10-04 — [Cameras and clutter](plans/cameras-and-clutter-2026-10-04.md): a camera as a part of the site, pictures sized and taken from it, and less on the screen (icon badges, the Machine in the rail, one header row, faded walls).
- 2026-10-03 — [Consolidation](plans/consolidation-2026-10-03.md): one page and one place per thing; Site and Selected over a strip of tabs, one Machine per board, the Bench, one Pictures panel, jobs over machine kinds.
- 2026-09-27 — [Designing a part from the browser](plans/part-editing-in-the-browser-2026-09-27.md): a spike measuring the part loop, OpenSCAD 2021.01 against a Manifold snapshot, and what other tools do; fast renders, parameters from the SCAD, then an editor in the page.
- 2026-09-26 — [Pictures in the world](plans/pictures-in-the-world-2026-09-26.md): a picture pinned at a place as a view, its shapes made into pieces standing there, every surface of the camera panel given a home in the world (Phases 0 and 2 to 4; Phases 1 and 7 continue in [what is open](plans/pictures-the-rest-2026-10-13.md)).
- 2026-09-20 — [One screen](plans/one-screen-2026-09-20.md): the world as the one page, with anchors and panels in front of it, and the census as the meter.

### Records from the bench

- 2026-11-03 — [The router walked in the demo](validation/2026-11-03-router-walk.md): the AnoleX 4060-Evo Ultra 2's Machine, pad, cut and stop against the simulated controller, step by step with the owner, and what the walk changed.
- 2026-11-05 — [Family integrations](validation/2026-11-05-family-integrations.md): how each family member's seam with apothecary stands, each checked against the member itself.
- 2026-10-12 — [OpenSCAD runs at once](validation/2026-10-12-openscad-runs-at-once.md): the timing behind the queue's default of two.
- 2026-10-11 — [Walkthrough picture drift](validation/2026-10-11-walkthrough-picture-drift.md): how far two runs' pictures differ, behind CI's tolerance.
- 2026-10-10 — [What the installs reach](validation/2026-10-10-what-the-installs-reach.md): the hosts the Rust and slicer installs reached under strace, and that a build and a slice reach none.
- 2026-09-21 — [Local integration run-through](validation/2026-09-21-local-integration.md): a checklist for the review branch, section by section.
- 2026-09-20 — [Ender bench](validation/2026-09-20-ender-bench.md): the printer seam against a real Marlin board, and what the bed measured.
- 2026-08-28 — [Gathering thresholds](validation/2026-08-28-gathering-thresholds.md): what the gathering's and the finder's thresholds were measured at.

## Generated

`apothecary docs generate` writes these into `docs/generated/`, which is not
committed, from the browser tests marked `docs`, `test_docs_fractal_viewer.py`
and `test_docs_printer_monitor.py`: each `docs.step(...)` in them is an
assertion and a paragraph. Those tests run only under `--generate-docs`,
which the command passes; an ordinary browser run skips them.
`apothecary serve --refresh-docs` does the same in the background, and `apothecary docs clean` removes the folder. (Walkthrough
pages 01 and 02 come from the two other `test_docs_*.py` files, which are
marked `walkthrough` and write `walkthrough/`, not `docs/generated/`.)

Until they are generated the folder does not exist; once generated, each
page is at its path under `/docs/`, and says under its title the day it was made and the commit it was made from:

| Page | Written to |
|---|---|
| Fractal zoom viewer | `docs/generated/fractal-viewer/fractal-viewer.md` |
| Boards and printers: a board's Machine, the Bench | `docs/generated/printer-monitor/printer-monitor.md` |
| Which pictures went together: the gathering map, light and dark | `docs/generated/gathering/which-pictures-went-together.png` and `-dark.png`, written by every browser run of `tests/e2e/test_gathering_map_in_a_browser.py`, not by `docs generate` |
