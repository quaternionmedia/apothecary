# Apothecary documentation

`apothecary serve` serves this folder at `/docs` and the walkthrough at
`/walkthrough`; links between pages work because the URL is the path. The
root [README](../README.md), with the map of what the browser suite walks, is served
at `/README.md`, and every page's bar links it. The HTTP API is described at `/openapi.json`, the commands by `apothecary --help`.

## The walkthrough

`walkthrough/` is the path through this repository. Each page's opening says what runs
it: a page *Written by* a browser test is that test's output, and a **Hermetic** page is
doctests, run by `pytest walkthrough`. The table links every page in the folder, which
`tests/test_docs_site.py` holds it to; served, `/walkthrough` lists them in order. Start
at page 00.

| Page | |
|---|---|
| [00 — Getting started](../walkthrough/00-getting-started.md) | Install, `apothecary check`, `apothecary openscad install`, `apothecary serve --simulated`; the five loops and what each needs; the optional installs |
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
| [19 — The router](../walkthrough/19-the-router.md) | The garage's CNC router, an AnoleX 4060-Evo Ultra 2: its working area on its table, GRBL's dialect read and bounded, the simulated controller identified, polled, driven and stopped, its table mapped by its probe |
| [20 — A part through the router](../walkthrough/20-a-part-through-the-router.md) | The subtractive loop on one part: the coupon's declared cuts, its toolpath written and checked, kept and cut from here with the work zeroed, the job naming its operation, the cut measured against the design, and the design changed and cut again |
| [21 — A toolpath, previewed](../walkthrough/21-a-toolpath-previewed.md) | One interpreter and two processes: a print's layers and a cut's passes read through one core, held to the toolpath's own writer, and a design change seen in the moves |
| [22 — The irl family's hub](../walkthrough/22-the-irl-hub.md) | apothecary as the family's hub on hearth's contract: what it says it is, its table, a fire and what is kept |
| [23 — A procedure](../walkthrough/23-a-procedure.md) | What the family fires: the steps that bring a site's blueprint into working order, each waiting for GO and the evidence it names, a person's own, a member's refusal, a page's read and a member that is not there, and what the log keeps |
| [24 — A cut from the card](../walkthrough/24-a-cut-from-the-card.md) | The router's Cut card as a person goes round it: the coupon chosen under makes, its toolpath written and drawn on the table, kept as the router's plan, control armed and the work zeroed, the cut streamed, held, resumed and cancelled; written by the browser suite |
| [25 — A procedure through the window](../walkthrough/25-a-procedure-through-the-window.md) | A site's procedure through the Procedure window on the simulated bench: GO on a step, a step's node as a door to the window its work is in, a machine's step refused in the member's words, the latch armed through that door and the step fired again, and the Family view's Members and Deliveries; written by the browser suite |
| [26 — The Stream Deck +](../walkthrough/26-the-stream-deck.md) | An Elgato Stream Deck + at the garage's bench: its piece opens the Deck window, a program draws its eight keys and strip, and a simulated deck is pressed, turned and tapped, each event listed and kept; written by the browser suite |
| [27 — The deck jogging the machines](../walkthrough/27-the-deck-jogging-the-machines.md) | The Stream Deck +'s knobs jog the router through the control latch: its layout drawn, a turn disarmed moving nothing, an armed jog read back on the X key, the step key, the stop key stopping a spinning spindle, two long presses of the router's key arming it, DISARM letting go of every machine, and UNLOCK after a stop mid-move; written by the browser suite |
| [28 — A whiteboard to a model](../walkthrough/28-a-whiteboard-to-a-model.md) | A drawing in marker read by the `outline` finder: the whiteboard as the ground, each closed stroke the shape of what it encloses, named, placed and sized, with what the `plain` finder makes of the same picture |
| [29 — A whiteboard, round twice](../walkthrough/29-a-whiteboard-round-twice.md) | The whiteboard loop by its commands: a photograph squared to its whiteboard, its marks sorted and a person's word kept, its note typed and its size offered, a plate made with its cut, then the drawing changed and photographed again, what changed proposed and one row taken |
| [30 — A whiteboard, round twice through the page](../walkthrough/30-a-whiteboard-round-twice-through-the-page.md) | A photograph pinned at the garage's whiteboard from its ring, squared and laid in front, its shapes found, its writing typed in Marks and its shapes made; a second photograph of the changed drawing, the whiteboard's history, a change taken, Earlier on the ring back to the first, and that moment placed on the bench; written by the browser suite |
| [31 — What the router needs](../walkthrough/31-what-the-router-needs.md) | What stops a person at the router, in its Machine: a controller in alarm saying what clears it, a jog that did not go kept in Needs you, each axis's home beside its button, Unlock, a home not proved refused, an axis jogged the way it homes, and the router armed on its badge and its row; written by the browser suite |
| [32 — A quiet board, and a router's pins](../walkthrough/32-a-quiet-board-and-a-router-s-pins.md) | Two values as the Working space's table reads them: a printer not heard for ten minutes, last heard and its state last known at its board's last answer, and a router's pins read as their items, then none; written by the browser suite |
| [33 — Windows kept over a reload](../walkthrough/33-windows-kept-over-a-reload.md) | Models, Marks, the Working space and the Deck opened from ⊞ Windows, and the page reloaded: each open again in the stack it was in, the world as wide; written by the browser suite |
| [34 — The tour](../walkthrough/34-the-tour.md) | The page's journeys a stage at a time, in a box over the page: a journey chosen and the page taken to its stage, ✓ Works and ✗ Off kept, See reached from nothing, a stage that says what it needs, a view laid out beneath the box, the ring's cells, a reload, and every word given back; written by the browser suite |
| [35 — The Models window](../walkthrough/35-the-models-window.md) | Image models through the simulated qmcp: no guess trusted, a shape chosen on the bench's mat, Ask with each guess not checked, a person's word over the model's, the model switched off and still off after a reload; written by the browser suite |
| [36 — The Models window, narrow and wide](../walkthrough/36-the-models-window-narrow-and-wide.md) | The Models table reading down beside the world on a narrow page, and a table on a wide one; written by the browser suite |
| [37 — Marks worn in the world](../walkthrough/37-marks-worn-in-the-world.md) | A whiteboard's marks sorted in the Marks window and worn over its picture in the world, a person's word read back by its shapes, and a note's ✎ opening its box and offering the size it states; written by the browser suite |
| [38 — A whiteboard's corners](../walkthrough/38-a-whiteboard-s-corners.md) | A photograph from one side with the whiteboard's corners found on it, a corner nudged with the arrow keys and the whiteboard squared again; written by the browser suite |
| [39 — The chain, a stage at a time](../walkthrough/39-the-chain-a-stage-at-a-time.md) | Every journey in the chain's order, the page taken to each stage by the tour, on simulated machines as a person starts them: a part designed, made, cut, its board, a deck's knobs, the site brought up and watched, a drawing read into shapes; what the page did to stand on each, and nothing armed, started or made; written by the browser suite |
| [40 — Layers and depth](../walkthrough/40-layers-and-depth.md) | The universe's sphere turned until a piece of an outer shell stands in front of one of an inner shell, a click selecting the outer one, then the outer shell made not selectable in the Layers window beside the world and the same click selecting the piece behind; written by the browser suite |
| [41 — The deck while a print streams](../walkthrough/41-the-deck-while-a-print-streams.md) | The Stream Deck +'s touch strip while a print streams on the simulated printer: Progress brought forward once, a swipe along the Deck window's strip back to the knobs, which say the print holds the port, on to Status, and a cancelled print kept on Progress until a touch; written by the browser suite |
| [42 — Measuring in the world](../walkthrough/42-measuring-in-the-world.md) | Measure ticked in the Layers window: the calibration cube reading its size along its own axes, each number saying where it comes from, then two of its corners clicked for the distance between them and dx, dy and dz; written by the browser suite |
| [43 — Parts that meet](../walkthrough/43-parts-that-meet.md) | A dust hose adapter's interfaces, how each fits the hose and two ports, the three placed where they meet by their connections, both fitting ends in use refused, and what is still a stub |

## The checklists

What is ticked by a person before a stack is pulled and before a tag is cut. The
suites hold everything else.

| Checklist | |
|---|---|
| [The integration checklist](integration-checklist.md) | A stack, before it is pulled: the tree that will land, the suite once on its head, the pictures judged, the docs read together, preflight, the rows only a person sees, the pull requests and the landing |
| [The bench checklist](bench-checklist.md) | The Ender 3, an ESP32 and the router for real: pinning, the link, heat, motion, levelling, printing from here, slicing, the emergency stop, the Rust and Arduino blinks, and the router's homing, jogs, spindle, zero, probe and a cut |
| [The models checklist](models-checklist.md) | Image models through qmcp by hand, against the simulated qmcp: the Models window, asking about a shape, a person's word, switching an origin off, and each way qmcp can be missing |

## Guides

| Page | |
|---|---|
| [The dev loop](dev-loop.md) | Change, see, test, commit, integrate: a command for each step, two servers at once on two ports, what others pushed brought into a checkout, and a change brought into main |
| [The viewer](viewer.md) | The page's own controls: the header and ⚙ View, the world and its faded walls and badges, the ring and its addresses, the windows, the part editor and the SCAD editor, the keys |
| [The Stream Deck +](stream-deck.md) | An Elgato Stream Deck + found on USB, its keys and strip drawn and its keys, knobs and touches heard, through a module beside the toolchains: setting it up, what is found, drawn and heard, its routes and the simulated deck |
| [Windows and focused systems](windows-and-systems.md) | For an author: a window of the page -- where it opens, what a browser remembers, an empty one -- and a focused system's registry entry, its widget's hook, and the tests that hold each |
| [The family's hub](family.md) | apothecary as the `irl` family's hub on hearth's contract: its routes, its table, what goes through it and how `hearth check` judges it |
| [Lighting](lighting.md) | A site's lighting rig -- fixture types, a patch, live levels -- the theatre site that uses it, another console's exports in its place, and a console's levels by sACN or OSC |
| [OpenSCAD](openscad.md) | Installing a snapshot with Manifold on each platform, which OpenSCAD a render uses, what 2021.01 cannot do, how many run at once |
| [Scene JSON format](scene-json.md) | Scenes, primitives, booleans and transforms as JSON |
| [Parts authoring](parts-authoring.md) | How to add a part, override its parameters, and check it |
| [Fitting a part](fitting-a-part.md) | The seam between a consumer and this repository as built: black boxes, a part's parameters and the validator, a gate per pair of descriptions, the pin, and who owns each open problem |
| [Connections](connections.md) | How one part meets another: the interfaces a part declares, the fit two make, a round part built with its interfaces, the render held to them, and parts placed side by side where their interfaces meet |
| [Borders and handoffs](boundaries.md) | Where apothecary ends and another repository begins, the package's layers and the imports that reach up one, and what crosses at each handoff of the loops, held by a test |
| [Geometry models](models.md) | Vectors, bounds, colors, shapes and units |
| [Geometry made elsewhere](geometry-from-elsewhere.md) | An STL or OBJ as a part (`apothecary parts import`), and a part described by a sidecar |
| [The tour](tour.md) | The page's journeys a stage at a time, in a box over the page: the page taken to a stage for a person to explore, what a stage needs said where it is not there, and one word kept on each stage |
| [The Working space](working-space.md) | A site as its evidence has it: a printer's polls kept as observations, the frames its cameras keep with them under a budget, the window that shows both, and the doors that read them |
| [Pictures, cameras and pieces](pictures.md) | Where pictures live, a camera as a part of the site, a picture pinned as a view, its shapes made into pieces, what is taken back and how, the `photo` commands |
| [The census](census.md) | What `apothecary census` counts of the viewer, how each control and listener is classified, ring-backed and taken back, and the ceiling and floor a change to the page keeps |
| [Configuration](configuration.md) | Every `APOTHECARY_*` variable, and the tool variables, each with its default and the page that explains it |
| [Firmware](firmware.md) | Programming boards from sketches kept with their parts, Arduino and Rust for the ESP32, from the Bench or a board's Machine; monitoring a G-code printer from its scene node |
| [The router](cnc.md) | The garage's CNC router beside the Ender: the AnoleX 4060-Evo Ultra 2 as a part on its stand, its Grbl_ESP32 controller as the node a port is pinned to, GRBL's dialect of the machine seam -- identified, polled, driven within bounds, stopped, a cut streamed -- the simulated controller, and what is not built |
| [The projector](projector.md) | A projector aimed at a machine's bed: its page for a second display, its calibration of four points of the bed plane, what it draws there -- the file about to be made, the tool, the band of the machine's state -- what registers it and what does not, a bed that carries Y, and the routes |
| [Surfaces](surfaces.md) | What the server keeps of each thing a page shows, declared by its owner in its frame: one read, one stream of the changes the server already learns of, with no poller, what the family's members write of what they found, and what the page could move onto the stream |
| [The toolpath preview](toolpath-preview.md) | Where a file's tool goes, drawn in the world before anything is sent: one core for a print and a cut, its two instantiations, what else reads through it, the route and the card's slider |
| [The toolpath](cam.md) | The router's toolpath, written from the cuts a part declares: what a part says, what the toolpath does, how it is kept, recorded and offered, and the cut measured as cut |
| [The slicer](slicer.md) | OrcaSlicer installed and pinned, the printer's profile kept with its part, a part or a made piece sliced for the pinned printer and kept for the Print card |
| [The Airgap](airgap.md) | The `airgap` part -- a rotor/stator pair computed in its SCAD -- and the Airgap panel: the part as a field, torque and dynamics model that follows its text in the editor, its verbs on the ring, its rig and sweep as documents, and the metrics document Python reads back |

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
| [A whiteboard to a model, and round again](plans/whiteboard-loop-2026-11-09.md) | A drawing in marker as a way in, the fifth loop and a heads-up layer towards designing for making: writing and diagrams sorted apart, a person's word kept at every step, the whiteboard a part of the site, a photograph squared and laid in front of it, cuts, notes with a way out to qmcp and looksatwords, round again, and the whiteboard's history scrubbed and placed elsewhere; every slice built ([walkthrough 30](../walkthrough/30-a-whiteboard-round-twice-through-the-page.md)), what it leaves named |
| [Integrating the local stacks](plans/integration-2026-11-07.md) | Every local stack cut from `main` at 1e12ec58 -- testing, the fixes, standardize, homing, family, streamdeck -- finished, merged in landing order into one tree, tested once as a whole by the integration checklist, its owed fixes taken home, and landed, its push priced before it is made: the phases, the conflicts found and each one's resolution, and what only the bench shows |
| [One way of doing each thing](plans/standardization-2026-11-07.md) | What the package does two ways and the one standard each folds into: a dialect's rules in its own module, one module for the state folder, one finder for every bought engine, a board by its part, a kind of machine from its dialect; in slices, three of them removals, each approved before it was built; what is left, named with its reason |
| [Journeys: window sets and a rail of steps](plans/journeys-2026-11-11.md) | A path through the page held as one: the windows it passes through laid out together as a view, and a numbered rail of its steps in the header, the step a person is on filled and Next naming the one after, taken from codecartographer's step rail and alfred's stage rail; *Print a part on a machine* first, Choose, Shape, Slice, See, Print; in slices |
| [The family's journeys through the viewer](plans/family-journeys-2026-11-07.md) | The page shaped round the paths through the family's work: the sentences telling a person what to do gone, a control surfacing when what it needs holds, a procedure's step and a member each a door to the window its work is in, and the family one focused system with a view of its own; in four slices, each a branch |
| [The Stream Deck + at the bench](plans/stream-deck-2026-11-07.md) | An Elgato Stream Deck + three ways: a part on the garage's workbench from the maker's figures, a device programmed from here (its keys and strip drawn, its presses, turns and touches heard, through a module beside Arduino's and Rust's and a simulated deck the demo shows), and a controller whose knobs jog the chosen machine's axes through the control latch, the dialect's bounds and its own stop; in slices, with the questions it decided |
| [Each machine keeps its own](plans/machine-identity-2026-11-07.md) | One answer to which board is on a port and what kind of machine it is; every record and cache keyed by it, a port that changes hands forgetting its board, one kind's work refused on another at the server, and the stop always sent; in slices: the stop, the port's forgetting, readings by board, pins by board, files by kind and machines planned before their board built; the page's marks by board not |
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
| [One page for every effort](plans/ui-coordination-2026-10-31.md) | The viewer's windows, doors and words across the efforts in flight (the Working space, the image models, the rig's faces, the bench in carlos, lighting, pictures): where they collide, one observation module, and the order the collisions are settled in. |
| [An irl hub of ShowRunner's class](plans/irl-hub-2026-11-02.md) | Apothecary as hearth's second exemplar: a procedure of steps on a blueprint in place of a cue list on a script, each step's family block delivered over `family/1` to the printer, the boards and the cameras hosted in the hub and to carlos, joe with vox, alfred with otto, datum, ira and ShowRunner beside it, every outcome kept in the evidence log; each member's verbs, what it has and what it needs, the order of the work and the owner's questions; the hub, its machine and board members and the procedure are built ([the family's hub](family.md)), the rest is not |

## History

Plans and research that are finished, newest first. Each is a dated record
of what was decided and why; what is still true of it is stated in the
guides above, the governance records, or the code it describes. A plan
whose work is done leaves the table above for this list.

- 2026-11-04 — [One page for two machines](plans/ui-refresh-2026-11-04.md): the kinds' words in one module, one badge grammar, a section's title by kind, the card in the loop's order, the Working space on any machine, the palette in one sheet; what it left is in [todo.md](../todo.md).
- 2026-10-20 — [Landing the stack on main](plans/landing-the-stack-2026-10-20.md): every open pull request and the governance records it pins, reviewed once as a whole and merged into `main` bottom first, the order checked by merging each branch in turn; what is still open of its *After* is in [todo.md](../todo.md).
- 2026-10-10 — [A managed slicer](plans/slicer-2026-10-10.md): OrcaSlicer behind a slicer interface, installed like OpenSCAD, the printer's profile kept with its part, print settings from what each part declares.
- 2026-10-09 — [A Rust geometry kernel](plans/rust-geometry-kernels-2026-10-09.md): a survey of which Rust kernel could render scenes to STL without OpenSCAD -- Manifold bindings, csgrs, boolmesh, truck, Fornjot, OCCT -- by licence, build, coverage and maturity; Manifold's bindings first.
- 2026-10-08 — [The loops through the page](plans/ui-flows-2026-10-08.md): designing a part, editing its SCAD, firmware, and a picture to a print, each built out and held end to end by a browser test.
- 2026-10-08 — [Rust](plans/rust-2026-10-08.md): firmware in Rust for the ESP32 behind modular toolchains, a Rust geometry kernel researched and compared by numbers, a Rust service and core stubbed.
- 2026-10-04 — [Cameras and clutter](plans/cameras-and-clutter-2026-10-04.md): a camera as a part of the site, pictures sized and taken from it, and less on the screen (icon badges, the Machine in the rail, one header row, faded walls).
- 2026-10-03 — [Consolidation](plans/consolidation-2026-10-03.md): one page and one place per thing; Site and Selected over a strip of tabs, one Machine per board, the Bench, one Pictures panel, jobs over machine kinds.
- 2026-09-27 — [Designing a part from the browser](plans/part-editing-in-the-browser-2026-09-27.md): a spike measuring the part loop, OpenSCAD 2021.01 against a Manifold snapshot, and what other tools do; fast renders, parameters from the SCAD, then an editor in the page.
- 2026-09-26 — [Pictures in the world](plans/pictures-in-the-world-2026-09-26.md): a picture pinned at a place as a view, its shapes made into pieces standing there, every surface of the camera panel given a home in the world (Phases 0 and 2 to 4; Phases 1 and 7 continue in [what is open](plans/pictures-the-rest-2026-10-13.md)).
- 2026-09-20 — [One screen](plans/one-screen-2026-09-20.md): the world as the one page, with anchors and panels in front of it, and the census as the meter.

### Records from the bench

- 2026-11-07 — [The garage's two machines, read from what is recorded](validation/2026-11-07-machine-setup.md): where the relief the viewer lays over the router comes from, the Ender's stored mesh against its probes, the router's settings never read and what each decides, and the boxes the bench needs.
- 2026-11-05 — [The family started through the hub](validation/2026-11-05-family-started.md): one procedure with a step for every member, carlos and joe real and started by the hub, what each did and what running it found.
- 2026-11-05 — [Family integrations](validation/2026-11-05-family-integrations.md): how each family member's seam with apothecary stands, each checked against the member itself.
- 2026-11-03 — [The router walked in the demo](validation/2026-11-03-router-walk.md): the AnoleX 4060-Evo Ultra 2's Machine, pad, cut and stop against the simulated controller, step by step, each step approved from its picture and the live page, and what the walk changed.
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
