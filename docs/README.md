# Apothecary documentation

`apothecary serve` serves this folder at `/docs` and the walkthrough at
`/walkthrough`; links between pages work because the URL is the path. The
HTTP API is described at `/openapi.json`, the commands by `apothecary --help`.

## The walkthrough

`walkthrough/` is the executable path through this repository, run by
`pytest walkthrough`. Start there.

| Page | |
|---|---|
| [01 — The parts registry](../walkthrough/01-a-part.md) | What a part is, and how its envelope is checked |
| [02 — Which numbers are whose](../walkthrough/02-fitting.md) | The seam, and driving it with overrides |
| [03 — Navigating a sub-assembly](../walkthrough/03-an-assembly.md) | datum_core as an addressable tree |
| [04 — Serving it](../walkthrough/04-serving-it.md) | The API and the viewer |
| [05 — Contested numbers](../walkthrough/05-contested-numbers.md) | Numbers the sources disagree about, and the dashboard for turning them |
| [06 — Ready to build](../walkthrough/06-ready-to-build.md) | Whether a part can be printed and checked against a real one |
| [07 — Status and progress](../walkthrough/07-status-and-progress.md) | One vocabulary for how the CLI reports state |
| [08 — Problems and solutions](../walkthrough/08-problems-and-solutions.md) | What is unresolved, who can close it, and what exists to close it with |
| [09 — Running the checks before pushing](../walkthrough/09-preflight.md) | `apothecary preflight`: each CI workflow, run here before a push |
| [10 — Being depended on](../walkthrough/10-being-depended-on.md) | What a consumer pinning this repository is entitled to |
| [11 — Photographs into pieces](../walkthrough/11-photographs-into-pieces.md) | A photograph becomes named, placed pieces in the viewer; written by its own run |
| [12 — The bench as it is](../walkthrough/12-the-bench-as-it-is.md) | Geometry from elsewhere, the printer and boards drawn as they are, a camera added above the bench; written by its own run |
| [13 — A picture to a print](../walkthrough/13-a-picture-to-a-print.md) | A camera's picture, its shapes, a piece made and adjusted, and a print job for it on printer_1, twice round through the page; written by its own run |

## Guides

| Page | |
|---|---|
| [Scene JSON format](scene-json.md) | Scenes, primitives, booleans and transforms as JSON |
| [Parts authoring](parts-authoring.md) | How to add a part, override its parameters, and check it |
| [Fitting a part](fitting-a-part.md) | Which numbers belong to a consumer and which to this repository, and who owns each open problem |
| [Geometry models](models.md) | Vectors, bounds, colors, shapes and units |
| [Geometry made elsewhere](geometry-from-elsewhere.md) | An STL or OBJ as a part (`apothecary parts import`), and a part described by a sidecar |
| [Firmware](firmware.md) | Programming boards from sketches kept with their parts, from the Bench or a board's Machine; monitoring a G-code printer from its scene node |

## Plans and records

| Page | |
|---|---|
| [One screen](plans/one-screen-2026-09-20.md) | The world as the one screen: anchors, popups and panels in front of it, and the census as the meter; done |
| [Consolidation](plans/consolidation-2026-10-03.md) | One page and one place per thing: Site and Selected over a strip of tabs, one Machine per board, the Bench, one Pictures panel, jobs over machine kinds; done |
| [Cameras and clutter](plans/cameras-and-clutter-2026-10-04.md) | Cameras as parts, easier pictures, and less on the screen: badges as icons, the Machine in the rail, one header row, faded walls; in four phases |
| [Cleanup, triaged](plans/cleanup-triage-2026-10-08.md) | Every open cleanup item sorted by kind and given an order: in flight, delivery, dead code, parts, tests, structure, the owner's |
| [Rust](plans/rust-2026-10-08.md) | Firmware in Rust for the ESP32 behind modular toolchains; a Rust geometry kernel researched and compared by numbers; a Rust service and core stubbed |
| [The loops through the page](plans/ui-flows-2026-10-08.md) | Designing a part, editing its SCAD, firmware, and a picture to a print: each built out and held end to end by a browser test |
| [A managed slicer](plans/slicer-2026-10-10.md) | OrcaSlicer behind a switchable slicer interface, installed like OpenSCAD; the printer's profile kept with its part, print settings from what each part declares |
| [Pictures in the world](plans/pictures-in-the-world-2026-09-26.md) | A picture pinned at a place as a view, its shapes made into pieces there; what is built, and what is open |
| [Designing a part from the browser](plans/part-editing-in-the-browser-2026-09-27.md) | A spike: the loop for changing a part from the viewer today, what other tools do, and a recommended order |
| [The shape finder, with a model behind it](plans/photo-finders-local-models-2026-09-21.md) | Optional local models behind the photo finder: the seam, the plugin shape, what reach is lawful, the phases |
| [Ender bench, 2026-09-20](validation/2026-09-20-ender-bench.md) | The printer seam against a real Marlin board, and the checklist for the rest |
| [Local integration run-through, 2026-09-21](validation/2026-09-21-local-integration.md) | A checklist to walk at the bench, section by section |

## Generated

`apothecary docs generate` writes these into `docs/generated/`, which is not
committed, from the browser tests marked `docs`: each `docs.step(...)` in
`tests/e2e/test_docs_*.py` is an assertion and a paragraph. Those tests run
only under `--generate-docs`, which the command passes; an ordinary browser
run skips them. `apothecary serve --refresh-docs` does the same in the
background.

| Page | |
|---|---|
| Fractal zoom viewer | [`generated/fractal-viewer/fractal-viewer.md`](generated/fractal-viewer/fractal-viewer.md) |
| Boards and printers: a board's Machine, the Bench | [`generated/printer-monitor/printer-monitor.md`](generated/printer-monitor/printer-monitor.md) |
