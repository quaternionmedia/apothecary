# Apothecary

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Apothecary builds 3D-printable things from Python and keeps the parts it has built.

- **Scenes to OpenSCAD.** Pydantic models (`Cube`, `Union`, `Translate`, ...) render to
  OpenSCAD or JSCAD, from Python or from a scene JSON file
  ([docs/scene-json.md](docs/scene-json.md)).
- **A parts library.** Each part is a folder under `parts/`: its SCAD, the parameters and
  bounds it declares, and the STL the `openscad` CLI builds from it.
- **A viewer.** A local FastAPI server and one page: a three.js world that zooms through
  sites, assemblies and parts at any depth, its panels as windows beside it, and a ring that
  reaches every verb by address. A part's parameters and its SCAD are edited there, applied
  as a variant drawn in its own tab, and saved as a variant kept in git
  ([docs/viewer.md](docs/viewer.md)).
- **Boards, printers and a router.** Sketches kept with their parts, Arduino and Rust, are compiled and
  uploaded to Arduinos and ESP32s, from the command line or the viewer; a Marlin printer is
  monitored, and drives its node in the viewer ([docs/firmware.md](docs/firmware.md)). A part
  or a made piece is sliced for the pinned printer with OrcaSlicer, and a print is a job,
  kept with the part it makes ([docs/slicer.md](docs/slicer.md)).
- **Photographs into pieces.** A picture becomes named, placed pieces you can build.
- **It stays on this machine.** The server answers this machine only, and the process
  connects nowhere else but to fetch its tools: OpenSCAD, the slicer, the firmware
  toolchain, and the crates a Rust sketch builds from (`apothecary/stays_local.py`).

## Start here

Python 3.11 or newer and [uv](https://docs.astral.sh/uv/), then

```bash
git clone --recurse-submodules https://github.com/quaternionmedia/apothecary.git
cd apothecary
uv sync
uv run apothecary check              # what is installed here, and what is missing
uv run apothecary openscad install   # an OpenSCAD with Manifold, before the first serve
uv run apothecary serve --simulated  # the viewer, with a simulated printer and board
```

[Walkthrough page 00, *Getting started*](walkthrough/00-getting-started.md) says each step
-- a clone made without its submodules, the OpenSCAD renders use, what `serve` prints --
then the five loops -- designing a part, editing its SCAD, a picture to a print, firmware,
a whiteboard to a model -- with what each needs, and the installs only some of them want:
the slicer, each firmware toolchain and the browser the tests drive.
`uv run apothecary --help` gives the same three steps after its commands.

## What it does, and how to see it

Each row is one thing the code does, where to see it on the running server (the page at
`http://127.0.0.1:6283/viewer`, unless the row gives a command; `uv run apothecary serve
--simulated` stands simulated machines where none is plugged in), the tests that hold it
(paths under `tests/`), and the walkthrough page its run writes or its doctests check. A
review walks these rows on the running server, on the whole codebase at once:
`uv run apothecary test all` runs every test named here, and
`tests/test_readme_map.py` fails when a row names a test or a page that is not there, when a
browser test is in no row, or when a page a run writes is in no row that names the run.

| What it does | See it | Held by | Page |
|---|---|---|---|
| A part designed in the page: a size moved, checked, applied and drawn as a variant | `/viewer/sites/apothecary`, a part's ring, Part › Edit; move a size, Apply | `e2e/test_part_loop.py`, `e2e/test_part_iteration.py`, `e2e/test_part_iteration_answers.py`, `e2e/test_text_tied.py`, `e2e/test_assignments_in_the_page.py`, `e2e/test_nothing_covers_a_control.py`, `test_part_variants.py` | [04](walkthrough/04-designing-a-part.md) |
| A part's SCAD edited in the page, checked as typing stops, saved as a variant in git | Part › Edit, then Part › View › SCAD editor (or Panels › Windows › Part view); type in it; Part › Save | `e2e/test_scad_loop.py`, `test_saved_variants.py` | [06](walkthrough/06-editing-a-parts-scad.md) |
| A picture to a print: a camera's picture, a piece made from it, sliced for printer_1 and printed | In the garage, the bench's ring: Camera › Add here (or Picture › Add, `examples/pictures/shapes.png`); Picture › Find shapes, Picture › Make; the piece's Slice, then its print | `e2e/test_picture_to_print.py`, `e2e/test_steps_a_picture_to_a_print.py`, `e2e/test_the_loop.py`, `e2e/test_edit_a_made_piece.py`, `e2e/test_picture_in_the_world.py`, `e2e/test_pictures_panel.py`, `test_slicer.py`, `test_made_part.py` | [03](walkthrough/03-a-picture-to-a-print.md) |
| A part that computes itself: the airgap's rotor, stator and windings from its SCAD's assignments, analysed as a field, torque and dynamics model | `/viewer/parts/airgap`, the part's ring, Part › Edit; Panels › Airgap › Airgap beside it, following the text; Panels › Windows › Airgap view, each of its sections a window | `e2e/test_airgap.py`, `test_airgap_part.py`, `test_airgap_metrics.py` | [17](walkthrough/17-a-part-that-computes-itself.md) |
| Firmware: a sketch built, flashed and heard saying hello, in Arduino and in Rust | The Bench, a tab beside Pictures: `esp32_blink`, built and flashed to the devkit; its hello in the devkit's Machine | `e2e/test_the_firmware_loop.py`, `e2e/test_steps_firmware.py`, `e2e/test_bench.py`, `test_firmware_seam.py` | [05](walkthrough/05-firmware.md) |
| One made thing round the four loops: the footpedal's sizes and its SCAD, a print of it, then its own sketch flashed to its board and heard, each loop's end naming the next on it | In the garage, the footpedal's ring: Part › Edit, Part › Save, Slice; then select it, and its Device section's Flash its sketch opens the Bench on it; Upload, then its ring's Device › Query | `e2e/test_the_made_thing.py` | [00](walkthrough/00-getting-started.md) |
| A photograph made into named pieces, opened as an arrangement | `uv run apothecary photo view examples/pictures/shapes.png --width-mm 300 --port 8001` | `e2e/test_docs_photo_walkthrough.py`, `e2e/test_gathering_map_in_a_browser.py`, `test_gathering.py`, `test_photo_shapes.py` | [01](walkthrough/01-photographs-into-pieces.md) |
| A drawing in marker on a whiteboard read as the shapes its strokes enclose: the whiteboard the ground, a dimension line and writing left out, each shape named, placed and sized | `uv run apothecary photo find PICTURE --finder outline`, or Picture › Find shapes › outline on a pinned picture ([docs/pictures.md](docs/pictures.md#finders)) | `test_outline_finder.py`, `test_again.py`, `test_marks.py`, `test_notes.py`, `test_whiteboard.py` | [28](walkthrough/28-a-whiteboard-to-a-model.md), [29](walkthrough/29-a-whiteboard-round-twice.md) |
| A whiteboard's marks in the page: the Marks window lists a pinned picture's marks and notes, a person's word on a mark is read back by the picture's shapes, and a note is typed | ⊞ Windows › Marks, with a drawing pinned and Find shapes › outline run on it ([docs/pictures.md](docs/pictures.md#the-marks-window)) | `test_marks_api.py`, `test_whiteboard_views.py`, `test_whiteboard_history.py`, `e2e/test_marks_window.py`, `e2e/test_whiteboard_round_twice.py` | [30](walkthrough/30-a-whiteboard-round-twice-through-the-page.md), [37](walkthrough/37-marks-worn-in-the-world.md), [38](walkthrough/38-a-whiteboard-s-corners.md) |
| The bench drawn as it is: Ender 3s, the boards, a camera placed above a piece | The garage's bench; double-click printer_1 for its mainboard; a camera added above the bench | `e2e/test_docs_bench_walkthrough.py`, `e2e/test_camera.py`, `e2e/test_first_camera.py`, `test_geometry_from_elsewhere.py` | [02](walkthrough/02-the-bench-as-it-is.md) |
| One Machine per board: a printer watched, controlled and printed to; a devkit listened to | printer_1's ring, Device › Open: its Machine beside Pictures, then Control and its pad's window; the devkit's Machine, Listen | `e2e/test_one_machine.py`, `e2e/test_machine_stops.py`, `e2e/test_steps_one_machine.py`, `e2e/test_printer_ui.py`, `e2e/test_less_on_screen.py`, `e2e/test_docs_printer_monitor.py`, `test_firmware_gcode.py`, `test_jobs.py` | |
| A button the server would refuse is greyed, with the server's reason in its tip: a jog while a print holds the port, a Home not proved, a file for the other kind of machine, a flash to a machine's controller; the stops are never greyed | A Machine during a print, hover a greyed button ([docs/firmware.md](docs/firmware.md)) | `e2e/test_buttons_say_why.py`, `test_can_now.py`, `test_can_js.py` | |
| A projector aimed at a machine's bed: a black page of its own that draws what is about to be made and the machine's state in the bed's millimetres, through four points marked on the bed | A machine's ring, Camera › Projector; C to mark the four points ([docs/projector.md](docs/projector.md)) | `e2e/test_projector_page.py`, `test_projector.py`, `test_homography.py`, `test_surfaces.py` | |
| The router beside the Ender: cnc_router's controller pinned to the simulated GRBL router, its Machine's state, positions, spindle and pins, its pad's home, jog, spindle, zero and probe, a cut from here, the soft reset, its table mapped by its probe and laid over the table, and what it needs of a person: Needs you, each axis's home proved first, armed on its badge | On simulated machines, cnc_router's 🪚 badge: its Machine, ⚙ Control and its pad, its Table map ([docs/cnc.md](docs/cnc.md)) | `e2e/test_router_ui.py`, `e2e/test_router_table_map.py`, `e2e/test_router_needs.py`, `test_firmware_grbl.py`, `test_firmware_table_map.py`, `test_menu.py` | [19](walkthrough/19-the-router.md), [31](walkthrough/31-what-the-router-needs.md) |
| A part through the router: the coupon on its table says how it is cut, Toolpath writes the cut in GRBL's dialect and says what it bored to the tool, the work zeroed, the cut names its operation as it streams, the simulated router's trace is measured against the design, and the design is changed and cut again | On simulated machines, the coupon's ring › Toolpath, or Toolpath in cnc_router's Machine ([docs/cam.md](docs/cam.md)) | `test_cam.py`, `e2e/test_router_ui.py` | [20](walkthrough/20-a-part-through-the-router.md), [24](walkthrough/24-a-cut-from-the-card.md) |
| The router calibrated by its 😮: the face, an eye and the mouth named in its toolpath as what to measure, cut, measured with calipers in its cabinet, and the tool's allowance they give kept for the router and taken by its next toolpaths | On simulated machines, the tour's Calibrate a router; or router_emoji under makes in cnc_router's Cut window, Toolpath, ▶ Cut, then measured in Part › Feedback ([docs/cam.md](docs/cam.md#measured-by-hand-fed-back)) | `test_cam_measured.py`, `e2e/test_router_ui.py` | [56](walkthrough/56-a-router-calibrated-by-a-face.md) |
| A badge composed: a face drawn after its emoji from circles and strokes, or a word in one of OpenSCAD's fonts, engraved in a plate; a face's toolpath its eyes bored and its strokes grooves, a word printed and refused by the router in its words | `uv run apothecary parts info badge`; a face's toolpath, `badge` under makes in cnc_router's Cut window ([parts/badge/README.md](parts/badge/README.md)); in the page, the tour's Compose a badge, or the badge in the universe and ⊞ Windows › Badge | `test_badge.py`, `test_cam.py`, `e2e/test_badge.py` | [57](walkthrough/57-a-badge-composed.md) |
| The Stream Deck + at the bench: found on USB, its eight keys and strip drawn from here, its keys, knobs and touches heard, in the Deck window; a simulated deck is pressed from it | On simulated machines, the `stream_deck` piece's Open Deck, or ⊞ Windows › Deck ([docs/stream-deck.md](docs/stream-deck.md)) | `test_firmware_deck.py`, `test_stream_deck_part.py`, `e2e/test_deck.py` | [26](walkthrough/26-the-stream-deck.md) |
| The Stream Deck +'s knobs jogging the router and the printer through the control latch, the dialect's bounds and the machine's own stop: the layout drawn on the deck, a turn disarmed moving nothing, an armed jog, the step key, the stop key, two long presses arming a machine, DISARM, UNLOCK after an alarm | On simulated machines, the Deck window's knobs after arming control in a machine's Machine or by two long presses of its key ([docs/stream-deck.md](docs/stream-deck.md#the-controller)) | `test_firmware_deck_control.py`, `e2e/test_deck_jog.py` | [27](walkthrough/27-the-deck-jogging-the-machines.md) |
| The Stream Deck +'s strip while a print streams: the knobs' screen, Progress and Status, a swipe along the strip walking them, a print bringing Progress forward once | On simulated machines, the Deck window during a print; drag along its strip ([docs/stream-deck.md](docs/stream-deck.md)) | `e2e/test_deck_screens.py`, `test_deck_screens.py`, `test_firmware_deck_control.py` | [41](walkthrough/41-the-deck-while-a-print-streams.md) |
| A toolpath previewed: a kept file's path drawn in the world on its machine, a printer's layers or a router's passes scrubbed through on one slider, from one core, a router's standing at its work zero | The Print or Cut card's preview slider, or Device › Control › Print or Cut › Preview ([docs/toolpath-preview.md](docs/toolpath-preview.md)) | `test_preview.py`, `e2e/test_toolpath_preview.py` | [21](walkthrough/21-a-toolpath-previewed.md) |
| A machine planned before its board is connected: its Machine opens as its plan, the part it makes, its slice or toolpath written and drawn over it, kept and chosen whenever its Machine opens | A machine with no board: its badge, its ring, or ⚙ View › Machine view ([docs/firmware.md](docs/firmware.md#a-machine-planned-before-its-board-is-connected)) | `test_machine_plans.py`, `e2e/test_machine_plans.py` | |
| A machine whose pinned board is not connected says why, read with no port opened: on USB, given a serial port, open to this user, found by the scan, the first that fails said as what to try, where it was last found and every serial port plugged in now; its own Machine opens once it comes up | A machine with its board pinned and not plugged in: its Machine's *Its board, not found* card; `GET /sites/{name}/machines/{path}/missing` ([docs/firmware.md](docs/firmware.md#its-board-pinned-and-not-connected)) | `test_missing.py`, `e2e/test_missing_board.py` | |
| A machine renamed, its path with it: every record kept under the old path moved to the new one, kept across a rebuild, and followed by the tour, the deck and the simulated printer | Selected's **Name** on a machine, or Panels › Machine › Rename; `PUT /sites/{name}/machines/{path}/name` ([docs/firmware.md](docs/firmware.md#a-machine-renamed)) | `test_renames.py`, `e2e/test_rename_a_machine.py` | |
| A part made on a machine from wherever a person is looking at it: a printer's or a router's Machine opens with its Print or Cut window, whose makes lists every part of the apothecary, and ⚒ Make in the header makes the part selected or stepped into on the first machine that makes it, in any site | ⚒ Make in the header, or a machine's badge; `GET /sites/{name}/makers` ([docs/viewer.md](docs/viewer.md#the-header)) | `test_machine_plans.py`, `test_job_api.py`, `e2e/test_make.py` | |
| The ring: every verb of what it opens on, at an address; the pointer and the keys | `m` or Ctrl + right-click on a piece; a digit reaches a cell; Settings | `e2e/test_ring.py`, `e2e/test_the_pointer_and_the_keys.py`, `test_menu.py` | |
| The world: site, assembly and part at any depth, drawn as OpenSCAD draws them on a floor grid under the level, the panels as windows of one layout, any window opened from a stack's + or the header's ⊞ Windows, views that lay windows out together, the site's problems and pins, and the windows a person opened open again after a reload where they were | Double-click a piece to step in, Page Up to step out; drag a window's tab or a splitter; a stack's +; ⚙ View › Part view, Machine view or Airgap view, then reload; the Site panel | `e2e/test_viewer.py`, `e2e/test_viewer_regressions.py`, `e2e/test_world_resize.py`, `e2e/test_render_on_demand.py`, `e2e/test_the_page_keeps_up.py`, `e2e/test_site_panel.py`, `e2e/test_windows_over_a_reload.py`, `e2e/test_docs_fractal_viewer.py`, `e2e/test_window_manager.py`, `e2e/test_journeys.py`, `e2e/test_focused_systems.py`, `test_systems.py` | [33](walkthrough/33-windows-kept-over-a-reload.md) |
| The tour: the page's journeys chosen and stepped a stage at a time, in a box over the page and nowhere else, the page taken to each stage in the chain's order, a window chosen moving the box to its stage, the address keeping the stage and opening the box on it, the box closed leaving the journey, and a person's word on each stage kept and given back | Tour in the header, or the ring's Panels › Windows › Tour; a journey chosen; ‹ and ›; ✓ Works or ✗ Off on each stage; its ✕; `GET /tour/feedback` ([docs/tour.md](docs/tour.md)) | `e2e/test_tour.py`, `e2e/test_tour_from_anywhere.py`, `e2e/test_the_chain.py`, `e2e/test_journeys.py`, `test_tour.py` | [34](walkthrough/34-the-tour.md), [39](walkthrough/39-the-chain-a-stage-at-a-time.md) |
| Apothecary, the universe: every registered part a leaf on the shell of a sphere its composition depth gives it, standing outward, and every other site one piece, drawn in miniature, on the outermost shell; a step into a site's piece opens the site, and a step out of a site's own level comes back | `/viewer/sites/apothecary`; double-click a site's piece, then Page Up ([docs/viewer.md](docs/viewer.md#the-world)) | `e2e/test_the_universe.py`, `e2e/test_orbitals_in_the_world.py`, `test_universe.py`, `test_orbitals.py`, `test_orbits_drawn.py`, `test_composition.py`, `test_site_names.py` | [10](walkthrough/10-serving-it.md) |
| How deep a click reaches and which layers are shown and selectable: the shells of the universe, the categories, the alignment grid and the machines' buttons, so a click passes an outer shell to the piece behind; each layer in one colour, in the world, in its ring and in the window, and a drawn ring that opens its layer's ring | ⊞ Windows › Layers, the ring's View › Layers and View › Depth, or a shell's ring or a cluster's outline clicked in the universe ([docs/viewer.md](docs/viewer.md#layers)) | `e2e/test_layers.py`, `e2e/test_orbitals_in_the_world.py`, `test_pick_scope.py`, `test_layer_colours.py`, `test_layers_world.py` | [40](walkthrough/40-layers-and-depth.md) |
| A dimension read in the world: the selection's size along its own axes with where each number comes from, the distance between two points clicked, the gap between two pieces, and the shape under a click from the mesh drawn -- a hole's or a boss's diameter beside the one the part declares, a wall's thickness, an edge, the angle of two faces, or why it cannot tell | Layers, Measure shown; a click on a piece, then another ([docs/viewer.md](docs/viewer.md#measure)) | `e2e/test_measure.py`, `test_measure.py`, `test_measure_world.py`, `test_measure_features.py` | [42](walkthrough/42-measuring-in-the-world.md) |
| The view banner: the header's one trail of where you are, the universe first, then the site (its own level, and under ▾ the other sites), then each piece stepped into | The header: `🧪 Apothecary › garage ▾ › cnc_router`; the first crumb, the site's crumb and its ▾ ([docs/viewer.md](docs/viewer.md#the-header)) | `e2e/test_view_banner.py`, `test_viewer_assets.py` | |
| Simulated machines, and the paths a newcomer takes | The banner over simulated machines; the bare `/viewer` address; the header's Docs | `e2e/test_simulated_machines.py`, `e2e/test_onboarding.py`, `e2e/test_paths_people_take.py`, `test_simulated.py` | [00](walkthrough/00-getting-started.md) |
| The HTTP API, and the docs it serves | `/openapi.json`, `/docs`, `/walkthrough` | `test_api.py`, `test_docs_site.py` | [10](walkthrough/10-serving-it.md) |
| Scenes to OpenSCAD, and the parts library | `uv run apothecary render --scene-file examples/scenes/cube.json -o scene.scad`; `uv run apothecary parts list` | `test_models.py`, `test_scene_render.py`, `test_registry.py` | [00](walkthrough/00-getting-started.md), [07](walkthrough/07-a-part.md), [09](walkthrough/09-an-assembly.md) |
| Parts that meet: a part's interfaces, whether two fit and how far one goes into the other, held to the render, parts placed where their interfaces meet, and the adapter generated between two ends | `uv run apothecary parts interfaces hose_adapter`; `uv run apothecary parts fit hose_adapter dust_port@port_32`; `uv run apothecary parts adapter dust_port@hose_40 dust_port@port_32` | `test_interfaces.py`, `test_fittings.py`, `test_part_interfaces.py`, `test_dust_parts.py`, `test_connections.py`, `test_parts_fit.py`, `test_adapters.py` | [43](walkthrough/43-parts-that-meet.md) |
| Two ends joined in the page: a part's presets in Parameters, ⇄ Adapter keeping one end and making the adapter between it and another, its fits said and checked again after each Apply | `/viewer/sites/apothecary`, `dust_port`'s ring, Part › Edit; a preset, ⇄ Adapter, another, ⇄ Adapter | `e2e/test_join_two_ends.py`, `test_ends_js.py` | [43](walkthrough/43-parts-that-meet.md) |
| A bed levelled on its solid mounts: the newest heated pair of probes made into the least shims that lift the low corners to the highest, the bow no shim fixes said against the bound for a stored mesh, the shims sliced as a part and probed again after | `uv run apothecary bed shims --site garage --printer printer_1`; `bed runs`, `bed mount`, `bed compare`; the tour's Level a bed, and Panels › Machine › Bed ([docs/bed-shims.md](docs/bed-shims.md)) | `test_bed_shims.py`, `e2e/test_level_a_bed.py` | [52](walkthrough/52-shims-that-level-a-bed.md), [53](walkthrough/53-a-bed-levelled-in-the-page.md) |
| A printer's first layer set to the height it holds at: a one-layer square, printed as a shim's first layer is, read for lines round and apart or thin and scraped, and the offset kept for the printer, which every slice made for it after takes as its `z_offset` | `first_layer_square` under makes, the Print window's **first layer** row (Print › Next slice › First layer); `POST /slicer/first-layer/offset` ([docs/slicer.md](docs/slicer.md#a-printers-first-layer-offset)) | `test_first_layer_offset.py`, `test_first_layer_js.py` | |
| A printer tuned from what its prints measure: a coupon made to be measured, its readings solved into the printer's errors with what they cannot separate said, half of each taken out of OrcaSlicer's own settings, the next coupon confirming it or not, every turn kept in one document | `uv run apothecary tuning plan print_coupon`; a coupon sliced, printed and read, then `uv run apothecary tuning turn FILE_ID --csv readings.csv --explain` and `tuning apply`; the Feedback window's **measured** row ([docs/print-tuning.md](docs/print-tuning.md)) | `test_print_tuning.py`, `test_slicer_tuning.py`, `test_tuning_cli.py`, `test_tuning_js.py`, `test_print_coupon_part.py`, `e2e/test_make.py` | [46](walkthrough/46-a-printer-tuned-from-its-prints.md) |
| A printer tuned from what its prints show, with the filament loaded on it: the filament chosen among OrcaSlicer's profiles that fit the printer, each fault a person sees on a piece (stringing, corners lifting, layers splitting, ...) kept as a look in the same per-filament document, which moves one setting at a time and puts back one that did not govern the fault | the Print window's **filament** row and the Feedback window's **seen** row; `GET /slicer/filaments`, `POST /slicer/slices/FILE_ID/seen`, `GET /slicer/faults` ([docs/print-tuning.md](docs/print-tuning.md)) | `test_print_faults.py`, `test_filaments_and_looks.py`, `test_tuning_js.py`, `e2e/test_make.py` | [50](walkthrough/50-a-printer-tuned-from-what-it-shows.md) |
| A part's cabinet: a drawer for each piece made of it, opened as its print or cut begins and told how it ended -- a print that stopped told on which layer, and tried again with probe first, a brim or a raft -- and what is read, seen or noted of the piece filed there, each filing naming the turn, look or allowance it made | a part's piece's ring, Part › View › Feedback, or a print's end; `uv run apothecary cabinet`; `/cabinet` ([docs/cabinet.md](docs/cabinet.md)) | `test_cabinet.py`, `e2e/test_make.py`, `e2e/test_router_ui.py`, `e2e/test_simulated_machines.py`, `e2e/test_a_print_that_stopped.py` | [51](walkthrough/51-a-part-s-cabinet.md), [54](walkthrough/54-a-print-that-stopped.md) |
| A printed piece checked against its design: a part's piece's dimensions marked on the part with Measure shown, a dimension's label clicked into Part › Feedback, what calipers read kept and checked against the design with the tolerance and whose it is, there and on the dimension in the world | Layers, Measure shown, a part's piece selected, a dimension's label clicked; `GET /cabinet/{part}/dimensions` ([docs/cabinet.md](docs/cabinet.md#dimensions)) | `test_cabinet.py`, `test_measure_world.py`, `e2e/test_a_piece_against_its_design.py` | [55](walkthrough/55-a-printed-piece-checked-against-its-design.md) |
| A gap that is not one number: measured along a ray and to the nearest point at any pose, and where its least travels; a rotor that rolls inside its stator, a rotor on leaves printed with its stator and a disc on a ring of pins, each measured from its own outlines, and each played in the viewer through its motion, its pieces drawn once and moved | `/viewer/parts/rolling_rotor`, `/viewer/parts/flexure_rotor` and `/viewer/parts/cycloidal_disc`, the part's ring, Part › View › Motion › Play; `uv run apothecary parts verify cycloidal_disc` | `e2e/test_part_motion.py`, `test_gap_geometry.py`, `test_rolling_rotor_part.py`, `test_flexure_rotor_part.py`, `test_cycloidal_disc_part.py`, `test_motion.py`, `test_part_motion_js.py`, `test_bought.py` | [44](walkthrough/44-a-gap-that-travels.md), [49](walkthrough/49-a-disc-on-its-pins.md) |
| A heater's loop: its plant identified from a step, a relay or a perturbation, a controller designed by a named rule, the loop's margins, and experiments run on a printer behind the latch, each ending with the heater off | `uv run apothecary loop design --gain 2 --time-constant 60 --dead-time 8`; `uv run apothecary loop simulate step --ceiling 200 --max-duration 1200 --base 180 --step 5 --settle 600 --after 400` ([docs/control-loops.md](docs/control-loops.md)) | `test_control_loops.py`, `test_loop_document.py`, `test_loop_tuning.py`, `test_loop_cli.py` | [45](walkthrough/45-a-heater-s-loop.md) |
| A heater's loop in the page: the board's gains beside the design, an experiment typed, started and followed from the stream, its plots and figures as the server says them, and the designed gains set and read back | A printer's Machine, then ⊞ Windows › Loops or the ring's Panels › Machine › Loops ([docs/control-loops.md](docs/control-loops.md#the-loops-window)) | `e2e/test_loops_window.py`, `test_loop_plots.py`, `test_loop_tuning.py`, `test_census.py` | [48](walkthrough/48-a-heater-s-loop-in-the-page.md) |
| Whose numbers are whose, which disagree, what is ready to build, and what is open | `uv run apothecary problems` | `test_parameter_coverage.py`, `test_contested_values.py`, `test_readiness.py` | [08](walkthrough/08-fitting.md), [11](walkthrough/11-contested-numbers.md), [12](walkthrough/12-ready-to-build.md), [13](walkthrough/13-status-and-progress.md), [14](walkthrough/14-problems-and-solutions.md) |
| A theatre's shell sized by sliders, its lighting rig drawn in it, its fixtures lit by a console's levels, received and never answered | `/viewer/sites/theatre`; the shell's ring, Part › Edit, its sliders; then `uv run apothecary lighting simulate` ([docs/lighting.md](docs/lighting.md)) | `e2e/test_lighting_overlay.py`, `test_theatre_site.py`, `test_lighting.py`, `test_lighting_routes.py`, `test_console_feedback.py` | |
| A rig of synths photographed: each knob, fader, switch and socket read off a picture against carlos's own panels, and held in carlos frame by frame through a concert, turned in place, a plug moved between songs followed | carlos running on this machine, as [the plan](docs/plans/carlos-concert-rig-2026-10-29.md#the-demo) starts it; `uv run apothecary rig simulate --carlos URL --out .cache/concert`, then `uv run apothecary rig follow .cache/concert --carlos URL --pace 1` | `e2e/test_carlos_concert.py`, `test_rig.py`, `test_wiring.py` | |
| A workspace seen from its evidence: a printer's polls kept with a frame from each camera that looks at it, each value saying how it is known | ⊞ Windows › Workspace, then printer_1's hour; its first line names each step after -- Add a camera above printer_1, each camera's device in its row, Keep a set now. Or printer_1's ring, Camera › Workspace ([docs/working-space.md](docs/working-space.md)) | `e2e/test_working_space.py`, `test_evidence.py`, `test_firmware_gcode.py`, `test_camera_parts.py` | [18](walkthrough/18-the-working-space.md), [32](walkthrough/32-a-quiet-board-and-a-router-s-pins.md) |
| The irl family's hub, on hearth's contract: its own members hosted, a procedure's steps fired on GO, and what each member answered (Panels › Windows › Family view: the Procedure, Members and Deliveries) | `/family/`, `uv run hearth check --hub http://127.0.0.1:6283` | `test_family_hub.py`, `test_family_members.py`, `test_family_procedures.py`, `test_family_beside.py`, `e2e/test_procedure_window.py`, `e2e/test_procedure_doors.py` | [22](walkthrough/22-the-irl-hub.md), [23](walkthrough/23-a-procedure.md), [25](walkthrough/25-a-procedure-through-the-window.md) |
| Image models asked about a shape through qmcp, only when a person asks: each guess beside the colour read off its pixels, none trusted since checking a model is not built, a person's word over every guess, a model switched off, the table reading down in a narrow window | `uv run apothecary serve --simulated`; a shape chosen on a picture's mat, then ⊞ Windows › Models, Ask; `uv run apothecary vision status` ([docs/models-checklist.md](docs/models-checklist.md)) | `e2e/test_models_window.py`, `test_vision_through_qmcp.py` | [35](walkthrough/35-the-models-window.md), [36](walkthrough/36-the-models-window-narrow-and-wide.md) |
| The bench as carlos draws it: each board's and lead's state sent from the garage as it changes, a printer's polls among them, held and drawn by carlos without a reload | carlos running on this machine, then `uv run apothecary serve --simulated --carlos URL`; flash a board from the Machine ([the bench plan](docs/plans/qm-family-carlos-2026-10-29.md#the-demo)) | `e2e/test_carlos_bench.py`, `test_wiring.py` | |
| It stays on this machine: the server answers this machine only, and the process connects nowhere else | `curl -H 'Host: evil.example' http://127.0.0.1:6283/sites/garage/attached` answers 403; without the header, the garage's cameras and views | `test_stays_local.py` | [02](walkthrough/02-the-bench-as-it-is.md) |
| The checks before a push, and what a project pinning this one may rely on | `uv run --group preflight apothecary preflight` | `test_cli_testing.py`, `test_e2e_shards.py`, `test_browser_suite_is_not_gated.py` | [15](walkthrough/15-preflight.md), [16](walkthrough/16-being-depended-on.md) |

## First commands

None of these needs the server. `serve` keeps its terminal until Ctrl+C, so beside it they
run in another one.

```bash
uv run apothecary render --scene-file examples/scenes/cube.json -o scene.scad   # a scene to OpenSCAD
uv run apothecary parts list                        # the registered parts
uv run apothecary parts generate-stl datum_core     # one part's STL (needs openscad)
uv run apothecary problems                          # what is open here, and who can close it
uv run apothecary photo view examples/pictures/shapes.png --width-mm 300 --port 8001   # a picture's pieces, in a viewer of its own
```

In the viewer, a camera is a part of the site: Camera › Add here stands one above a
structure, Take picture (`P`) pins its frame where it looks, Picture › Find shapes finds the
shapes in it, and Picture › Make stands one up as a piece to slice and print
([docs/pictures.md](docs/pictures.md); [walkthrough 03](walkthrough/03-a-picture-to-a-print.md)
goes round twice).

From Python, a scene is a few Pydantic models and its `render()` OpenSCAD's text:
[page 00's *A scene from Python*](walkthrough/00-getting-started.md#a-scene-from-python)
runs one and shows what it writes.

STLs are build products and are not committed. `apothecary serve` builds the missing ones
in the background when OpenSCAD is present (`APOTHECARY_SKIP_STL_GENERATION=1` skips that);
`apothecary parts generate-stl --all` builds them all.

## Where next

- [walkthrough/](walkthrough/00-getting-started.md): the executable path through the
  repository, run by `uv run pytest walkthrough`. Start at page 00.
- [docs/README.md](docs/README.md): the guides, plans and records.
- [examples/README.md](examples/README.md): small things to run, by kind -- scenes, scripts,
  pictures -- and *LLM's own*, the lane for language-model agents' contributions.
- `uv run apothecary --help`, and `--help` on every command: the command reference.
- `/openapi.json` on a running server: the HTTP API. `/docs` serves `docs/` and
  `/walkthrough` serves `walkthrough/`, rendered.
- [docs/dev-loop.md](docs/dev-loop.md): the dev loop -- change, see, test, commit, integrate.
- [docs/integration-checklist.md](docs/integration-checklist.md): a stack, box by box,
  before it is pulled; [docs/bench-checklist.md](docs/bench-checklist.md): the real
  machines, before a tag.
- [CONTRIBUTING.md](CONTRIBUTING.md): the test loop -- `uv run apothecary test run` is the
  ordinary test command -- what CI gates, and how commits are written.
  [CHANGELOG.md](CHANGELOG.md): what changed.

## Troubleshooting

- `apothecary: command not found`: prefix `uv run`, or activate `.venv`
  (`source .venv/bin/activate`; on Windows `.venv\Scripts\activate`).
- An import error after a pull: `uv sync`.
- An empty viewer or a part that will not render: `uv run apothecary check` says what is
  missing.
- A part drawn as a placeholder box: it has no STL yet. `serve` builds the missing ones as it
  starts; an OpenSCAD too old for the part (`check` names it) never will, and
  `apothecary openscad install` puts in one that can.

## License

MIT; see [LICENSE](LICENSE). Each file's licence is recorded for
[REUSE](https://reuse.software/) (`REUSE.toml`, `LICENSES/`).
