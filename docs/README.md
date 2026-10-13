# Apothecary documentation

`apothecary serve` serves this folder at `/docs` and the walkthrough at
`/walkthrough`; links between pages work because the URL is the path. The
HTTP API is described at `/openapi.json`, the commands by `apothecary --help`.

## The walkthrough

`walkthrough/` is the executable path through this repository, run by
`pytest walkthrough`. Start there, at page 00.

| Page | |
|---|---|
| [00 — Getting started](../walkthrough/00-getting-started.md) | Install, `apothecary check`, `apothecary openscad install`, `apothecary serve --demo`; the four loops and what each needs; the optional installs |
| [01 — The parts registry](../walkthrough/01-a-part.md) | What a part is, and how its envelope is checked |
| [02 — Which numbers are whose](../walkthrough/02-fitting.md) | The seam, and driving it with overrides |
| [03 — Navigating a sub-assembly](../walkthrough/03-an-assembly.md) | datum_core as an addressable tree |
| [04 — Serving it](../walkthrough/04-serving-it.md) | The API and the viewer |
| [05 — Contested numbers](../walkthrough/05-contested-numbers.md) | Numbers the sources disagree about, and turning them in the viewer |
| [06 — Ready to build](../walkthrough/06-ready-to-build.md) | Whether a part can be printed and checked against a real one |
| [07 — Status and progress](../walkthrough/07-status-and-progress.md) | One vocabulary for how the CLI reports state |
| [08 — Problems and solutions](../walkthrough/08-problems-and-solutions.md) | What is unresolved, who can close it, and what exists to close it with |
| [09 — Running the checks before pushing](../walkthrough/09-preflight.md) | `apothecary preflight`: each CI workflow, run here before a push |
| [10 — Being depended on](../walkthrough/10-being-depended-on.md) | What a consumer pinning this repository is entitled to |
| [11 — Photographs into pieces](../walkthrough/11-photographs-into-pieces.md) | A photograph becomes named, placed pieces in the viewer; written by its own run |
| [12 — The bench as it is](../walkthrough/12-the-bench-as-it-is.md) | Geometry from elsewhere, the printer and boards drawn as they are, a camera added above the bench; written by its own run |
| [13 — A picture to a print](../walkthrough/13-a-picture-to-a-print.md) | A camera's picture, its shapes, a piece made and adjusted, sliced for printer_1, and a print job for it there, twice round through the page; written by the browser suite |
| [14 — Designing a part](../walkthrough/14-designing-a-part.md) | A part's size moved, checked, applied and drawn in its tab, OpenSCAD's refusal by line, the saved part again for nothing, round twice and in two tabs; written by the browser suite |
| [15 — Firmware](../walkthrough/15-firmware.md) | A sketch chosen, built, flashed to the ESP32 devkit and heard saying its hello in the board's Machine, the Arduino esp32_blink then the Rust one; written by its own run, in the browser suite |
| [16 — Editing a part's SCAD](../walkthrough/16-editing-a-parts-scad.md) | A part's SCAD edited in Selected's editor, a failing line marked, a change rendered once its check passes and saved as a variant in git, the editor floated and fullscreen, round twice; written by the browser suite |

## Guides

| Page | |
|---|---|
| [The viewer](viewer.md) | The page's own controls: the header and ⚙ View, the world and its faded walls and badges, the ring and its addresses, the rail, the part editor and the SCAD editor, the keys |
| [OpenSCAD](openscad.md) | Installing a snapshot with Manifold on each platform, which OpenSCAD a render uses, what 2021.01 cannot do, how many run at once |
| [Scene JSON format](scene-json.md) | Scenes, primitives, booleans and transforms as JSON |
| [Parts authoring](parts-authoring.md) | How to add a part, override its parameters, and check it |
| [Fitting a part](fitting-a-part.md) | The seam between a consumer and this repository as built: black boxes, a part's parameters and the validator, a gate per pair of descriptions, the pin, and who owns each open problem |
| [Geometry models](models.md) | Vectors, bounds, colors, shapes and units |
| [Geometry made elsewhere](geometry-from-elsewhere.md) | An STL or OBJ as a part (`apothecary parts import`), and a part described by a sidecar |
| [Pictures, cameras and pieces](pictures.md) | Where pictures live, a camera as a part of the site, a picture pinned as a view, its shapes made into pieces, what is taken back and how, the `photo` commands |
| [The census](census.md) | What `apothecary census` counts of the viewer, how each control and listener is classified, ring-backed and taken back, and the ceiling and floor a change to the page keeps |
| [Configuration](configuration.md) | Every `APOTHECARY_*` variable, and the tool variables, each with its default and the page that explains it |
| [Firmware](firmware.md) | Programming boards from sketches kept with their parts, Arduino and Rust for the ESP32, from the Bench or a board's Machine; monitoring a G-code printer from its scene node |
| [The slicer](slicer.md) | OrcaSlicer installed and pinned, the printer's profile kept with its part, a part or a made piece sliced for the pinned printer and kept for the Print card |
| [The bench checklist](bench-checklist.md) | The Ender 3 and an ESP32 for real: pinning, the link, heat, motion, levelling, printing from here, slicing, the emergency stop, and the Rust and Arduino blinks |

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
| [Pictures in the world: what is open](plans/pictures-the-rest-2026-10-13.md) | Gathering out of core as an extra, and the old photo routes closed: the two phases of the pictures plan not built |
| [The shape finder, with a model behind it](plans/photo-finders-local-models-2026-09-21.md) | Optional local models behind the photo finder: the seam, the plugin shape, what reach is lawful, the phases |
| [Iterating on a part, tightened](plans/part-iteration-2026-10-12.md) | The part and SCAD loops reviewed and timed, and this round built: errors as failed renders, real controls, kept work, OpenSCAD's keys, variants drawn where they stand, history, compare, variant management; its next phase written out |
| [Governance, brought up to the corpus](plans/governance-2026-10-13.md) | The audit of apothecary's governance and audit documents against the corpus, and what is decided: the guard's install points, licence exceptions, the serial removed, drafts, the bench checklist |
| [The documentation, swept](plans/timeless-docs-2026-10-12.md) | Every durable text brought under the governance record on durable text: present tense, no internal history, no ornament; the triage by area and the order |

## History

Plans and research that are finished, newest first. Each is a dated record
of what was decided and why; what is still true of it is stated in the
guides above, the governance records, or the code it describes. A plan
whose work is done leaves the table above for this list.

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

- 2026-09-21 — [Local integration run-through](validation/2026-09-21-local-integration.md): a checklist for the review branch, section by section.
- 2026-09-20 — [Ender bench](validation/2026-09-20-ender-bench.md): the printer seam against a real Marlin board, and what the bed measured.

## Generated

`apothecary docs generate` writes these into `docs/generated/`, which is not
committed, from the browser tests marked `docs`, `test_docs_fractal_viewer.py`
and `test_docs_printer_monitor.py`: each `docs.step(...)` in them is an
assertion and a paragraph. Those tests run only under `--generate-docs`,
which the command passes; an ordinary browser run skips them.
`apothecary serve --refresh-docs` does the same in the background. (Walkthrough
pages 11 and 12 come from the two other `test_docs_*.py` files, which are
marked `walkthrough` and write `walkthrough/`, not `docs/generated/`.)

Until they are generated the folder does not exist; once generated, each
page is at its path under `/docs/`:

| Page | Written to |
|---|---|
| Fractal zoom viewer | `docs/generated/fractal-viewer/fractal-viewer.md` |
| Boards and printers: a board's Machine, the Bench | `docs/generated/printer-monitor/printer-monitor.md` |
