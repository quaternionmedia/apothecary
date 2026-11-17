# Borders and handoffs

Where apothecary ends and another repository begins, how its own package is layered,
and what crosses at each handoff of its loops. `tests/test_boundaries.py` reads the
tables under [The layers](#the-layers), [Where an import reaches up](#where-an-import-reaches-up)
and [Doors](#doors) and checks the package against them, holds
[what a module keeps to itself](#what-a-module-keeps-to-itself), and checks that every
path this page names exists; a change that moves a border changes this page with it.

## The repositories

| Repository | Joined by | Enters through | What crosses | Its contract | Held by |
|---|---|---|---|---|---|
| qm, the governance corpus | the submodule `governance/qm`, on its `project/apothecary` branch, pinned by commit | `AGENTS.md`; the workflows in `.github/workflows/`, which run `governance/qm/project-seed/ci/*.py` | the records this project is governed by, its own records in `governance/qm/adr/`, the checks a pull request passes | `AGENTS.md` | `.github/workflows/submodule-check.yml` (the pin is pushed); each workflow |
| hearth | `qm-hearth`, a git dependency pinned by commit in `pyproject.toml` | `apothecary/family/` alone | `family/1`, hearth's coordinator, `hearth.supervise` | hearth's `family/1`; [The family's hub](family.md) | `tests/test_family_hub.py`, `tests/test_family_members.py` (hearth's vectors replayed); `hearth check` from outside |
| carlos | HTTP on this machine: `APOTHECARY_CARLOS` (`serve --carlos`), or a member in the state folder's `family.json` | `apothecary/wiring/carlos.py` | a site's wiring, held by carlos, as a delivery through the hub | [What goes through it](family.md#what-goes-through-it) | `tests/e2e/test_carlos_bench.py`, with a carlos checkout named by `CARLOS_CHECKOUT` (it skips without one) |
| joe | HTTP on this machine: a member in `family.json` | the hub, `apothecary/family/`; no module names joe | the hub's cues; what it found of a surface, written to `POST /surfaces/contributed` | `family/1`; [Surfaces](surfaces.md#contributed) | `hearth check`; `tests/test_surfaces.py` |
| alfred | HTTP on this machine: a member in `family.json` | `apothecary/routes/surfaces.py`; no module names alfred | the surfaces and their stream, read; what it found of a surface, written to `POST /surfaces/contributed` | [Surfaces](surfaces.md#contributed) | `tests/test_surfaces.py` |
| qmcp | MCP on this machine: `APOTHECARY_QMCP` | `apothecary/finders/qmcp.py` | questions about a picture to an image model | [The models checklist](models-checklist.md) | `tests/test_vision_through_qmcp.py`, against the simulated qmcp; a real one is not reached yet |
| gridfinity-rebuilt-openscad | the submodule `parts/gridfinity/gridfinity-rebuilt-openscad`, pinned by commit | `parts/gridfinity/` | OpenSCAD source the part's SCAD uses | its own SCAD | `.github/workflows/submodule-check.yml` |
| The tools: OpenSCAD, OrcaSlicer, arduino-cli, cargo and espflash, esptool | programs run as subprocesses, in the tools dir or on `PATH` | found by `Tool` in `apothecary/firmware/toolchains.py`; fetched only through `tool_fetch` in `apothecary/stays_local.py` | a SCAD in and an STL out; an STL and profiles in and G-code out; a sketch in and an image on a board | [OpenSCAD](openscad.md), [Slicing](slicer.md), [Firmware](firmware.md) | `tests/test_stays_local.py` (what a fetch reaches); `apothecary check` |
| The page's libraries: three.js, GoldenLayout, CodeMirror | copies vendored in `apothecary/static/vendor/`, each with its README | the page, `templates/fractal_viewer.html.j2` | nothing leaves: served from this origin | each one's README | `tests/test_stays_local.py::test_no_page_loads_from_or_sends_to_another_origin` |

The Rust workspace in `crates/` is two stubs that build; nothing in the package calls
them, and the wheel carries neither. A Rust sketch, `parts/esp32_blink/rust/`, is its
own Cargo project, built by its toolchain module.

### Doors

A package from another repository, or from an install that is optional, is imported by
one module or one folder, so what it brings stops there.

| Package | Enters through | What it is |
|---|---|---|
| `hearth` | `apothecary/family/` | hearth's contract and coordinator |
| `mcp` | `apothecary/finders/qmcp.py` | MCP, for qmcp; imported only to say whether it is installed |
| `StreamDeck` | `apothecary/firmware/deck.py` | python-elgato-streamdeck, the `deck` extra |
| `esptool` | `apothecary/firmware/toolchains.py` | an optional raw flasher, never a declared dependency |
| `serial` | `apothecary/firmware/` | pyserial, the byte transport under the machine seam |

## The layers

A unit is a folder of `apothecary/` or a module at its top. A unit imports from its own
layer and the layers below it, at the top of a module and inside a function alike.

| Layer | Units | What it is |
|---|---|---|
| 0 | `core`, `models`, `version`, `stamped`, `site_names`, `stays_local`, `state_folder`, `picture_root`, `meshes`, `systems`, `journeys`, `census`, `preflight`, `release`, `airgap_metrics`, `preview`, `homography`, `surfaces`, `orbitals` | Foundations: geometry types, names, the network guard, the state folder, the picture root, the window registry, checks over the repository, one plane mapped onto another by four points, the registry of what a page shows and its changes |
| 1 | `primitives`, `booleans`, `objects`, `transforms`, `scene`, `hierarchy`, `jscad`, `templates`, `example`, `lighting`, `console_feedback`, `fittings`, `apothecary` | Geometry: shapes, a scene and its tree, OpenSCAD and JSCAD out; a site's lighting rig; round fittings built with the interfaces they make |
| 2 | `projects`, `universe`, `composition`, `connections`, `kernel_compare`, `datum_core_site`, `theatre_site`, `example_hierarchy`, `openscad_installer` | Parts and the sites built of them: the parts registry, a part's STL and its variants, parts placed where their interfaces meet, OpenSCAD itself |
| 3 | `firmware`, `slicer`, `cam`, `jobs`, `evidence`, `vision`, `vocabulary`, `gathering`, `finders`, `wiring`, `rig`, `family`, `machine_plans`, `projector`, `site_store`, `sites` | Machines and evidence: boards and their sketches, printers and routers, slices, toolpaths and jobs, a projector's calibration to a machine's bed, cameras, pictures and observations, carlos's wiring, the family's hub, the sites kept |
| 4 | `api`, `routes`, `viewer`, `docs_site`, `simulated`, `menu`, `spaces`, `tour` | The server and the page, and what reads across the whole package: the HTTP API, the viewer, the ring's menus, the simulated machines, the problems and solutions indexes, the tour |
| 5 | `cli`, `__main__` | The command line |

`apothecary.firmware` is three things that sit in one layer: the firmware toolchains,
the machine seam (`devices`, the Marlin and GRBL dialects in `gcode` and `grbl`, a port's
task in `tasks`), and the tool finder (`Tool`, `tools_dir`) every installer and the
slicer use. `slicer`, `cam`, `evidence`, `jobs` and `machine_plans` import it for the
machine seam, `openscad_installer` and the slicer's installer for the tool finder.

### Where an import reaches up

| From | To | Where | When | What it takes |
|---|---|---|---|---|
| `family` | `routes` | `apothecary/family/procedures.py` | in a call | `hold_action`, a site's wiring sent to carlos |
| `hierarchy` | `projects` | `apothecary/hierarchy.py` | in a call | the parts registry, for a node's `part_ref`; `ROOT` |
| `primitives` | `projects` | `apothecary/primitives.py` | in a call | `ROOT`, the repository's root |
| `projects` | `cam` | `apothecary/projects/parts/router_coupon.py` | in a call | cam's types, for the coupon's declared cuts |
| `projects` | `cam` | `apothecary/projects/parts/router_emoji.py` | in a call | cam's types, for the 😮's declared cuts |
| `openscad_installer` | `firmware` | `apothecary/openscad_installer.py` | at import | `tools_dir` |

*When* says whether the import runs as the module loads (at import) or only once a
function is called (in a call); the check holds both. No unit of a layer below it
imports `api`.

The sites kept are `apothecary/sites.py`'s: `store` is the one store of them, which
the server, the routes, cam, the family's members and the command line ask for a site
by its name. A name it does not hold is `UnknownSiteError`, and the server answers
that with a 404 in one place, its handler in `apothecary/api.py`.

The picture root is `apothecary/picture_root.py`'s: `picture_root` is the one folder
pictures are read from, and `picture_within_root` a path settled inside it. Each
refusal is an exception of that module's, a `PictureRefused`, and the server gives
each kind its status in one place, `PICTURE_REFUSALS` in `apothecary/api.py`: 500 for
a root that is no folder of pictures, 403 for a path outside it, 400 for one that
cannot be asked about, 404 for one that is no ordinary file. The module is an install
point of the network guard, as `apothecary/state_folder.py` is: whatever resolves the
picture root has the guard on.

### What a module keeps to itself

A name that begins with an underscore is its module's own. No module of the package
imports one from another module of the package, reads one as an attribute of a module
it imported, or imports a module so named; what two modules share has a public name
where it is defined. `tests/test_boundaries.py::test_no_module_takes_an_underscore_name_from_another`
reads every module for it. It follows a module through an import, through a function
of the same module that returns it, and through a name such a call is assigned to. It
does not follow one handed on as an argument or kept in a container, and it says
nothing of an object's own attributes: a class's `_field` read from another module is
not a module's name.

## The handoffs

What crosses between the stages of each loop, where its form is stated, and what holds it.

### A part, printed

| From, to | What crosses | Stated in | Held by |
|---|---|---|---|
| a part, its STL | `build_stl` in `apothecary/projects/parts/stl_renderer.py`: the SCAD's own render beside it, never turned, its parameters in a sidecar beside it; asked for, its rest pose beside that, `<name>.rest.stl` | `apothecary/projects/parts/base.py`, `apothecary/projects/parts/stl_renderer.py` | `tests/test_stl_renderer.py::test_a_part_turned_to_rest_prints_as_its_scad_lays_it` |
| a change, a variant | `apothecary/projects/parts/variants.py`: an STL in the cache under its key, and `measured`, the STL's box | its module docstring | `tests/test_part_variants.py` |
| a variant, git | `apothecary/projects/parts/saved.py`: the SCAD's text as a ref under `refs/apothecary/variants/`, in the repository `APOTHECARY_VARIANTS_REPO` names | its module docstring | `tests/test_saved_variants.py` |
| an STL, a slice | `apothecary/slicer/service.py` copies it into the slice's work folder; `apothecary/slicer/modules/orcaslicer.py` slices it as its SCAD lays it (`--orient 0`), with the printer's profile, `parts/ender3/slicer.json` | [Slicing](slicer.md) | `tests/test_slicer.py` |
| a slice, a job | the G-code kept by `save_print_file` in `apothecary/firmware/devices.py`, the slice's record beside it; a job names it by its file id while it is kept | `apothecary/jobs.py` | `tests/test_jobs.py` |
| a job, the printer | the lines streamed in Marlin's dialect, on the port pinned to the printer's node by its board's identity | [Firmware](firmware.md) | `tests/test_firmware_gcode.py` |

### A part, cut

| From, to | What crosses | Stated in | Held by |
|---|---|---|---|
| a part, its cuts | the part's `cuts(params)`, `Cuts` of `apothecary/cam/models.py`: millimetres, the work zero at the stock's front-left top corner, z up | [CAM](cam.md) | `tests/test_cam.py` |
| a variant, its cuts | `part_cuts` in `apothecary/cam/service.py` reads the variant's `params`: an edit of its SCAD's body is not among them | `part_cuts`'s docstring | |
| cuts, a toolpath | `apothecary/cam/toolpath.py` writes GRBL, its feeds within `apothecary/firmware/grbl.py`'s bounds, kept as a router's file | [The toolpath preview](toolpath-preview.md) | `tests/test_cam.py`, `tests/test_preview.py` |
| a toolpath, the router | a `cut` job, streamed in GRBL's dialect | [CNC](cnc.md) | `tests/test_cam.py`, against the simulated router |

### A sketch, flashed

| From, to | What crosses | Stated in | Held by |
|---|---|---|---|
| a part's folder, a sketch | `firmware.json` beside a `.ino` or a Cargo project, found by `apothecary/firmware/sketches.py` and claimed by a module of `apothecary/firmware/modules/` | [Firmware](firmware.md) | `tests/test_firmware_modules.py` |
| a sketch, a board | the module's commands: arduino-cli's compile and upload for an FQBN, or cargo's offline build and espflash | each module's docstring | `tests/test_firmware_modules.py` |
| a board, its record | a flash record in the state folder's `firmware-state.json`, under the board's stable identity | `apothecary/firmware/devices.py` | `tests/test_firmware_devices.py` |
| a board, the page | the line `apothecary <name>: hello`, at 115200 baud | [Firmware](firmware.md) | `tests/test_firmware_modules.py` |

### A site, drawn

| From, to | What crosses | Stated in | Held by |
|---|---|---|---|
| a site, the API | `apothecary/sites.py` holds the one store, and `apothecary/site_store.py` says what it keeps of each site's tree; `GET /sites/{name}` answers it whole, its tree, structures, SCAD and violations, with no response model, so `/openapi.json` does not describe it | `walkthrough/10-serving-it.md` | `tests/test_site_api.py` |
| an STL, the world | the page's `loadSTLMesh` turns OpenSCAD's z up into three.js's y up and centres the mesh on its node's envelope, or on a variant's `measured` box | [The viewer](viewer.md) | `tests/e2e/test_viewer_regressions.py` |
| a machine, the world | `GET /firmware/printers/where`: its build volume, origin and base, drawn by `apothecary/static/machine_marks.js` | | `tests/e2e/test_printer_ui.py` |
| a machine, a projector | `GET /sites/{s}/machines/{path}/projector`, read through `GET /surfaces/projector`: the calibration's mapping and what is about to be made in the bed's millimetres, drawn by `apothecary/static/projector.js` | [The projector](projector.md) | `tests/test_projector.py`, `tests/test_projector_page.py`, `tests/e2e/test_projector_page.py` |

### What is seen, kept

| From, to | What crosses | Stated in | Held by |
|---|---|---|---|
| a poll, the log | a printer's status, through the status listeners in `apothecary/api.py`, kept by `apothecary/evidence/printers.py` as observations in the state folder | [The Working space](working-space.md) | `tests/test_evidence.py` |
| a picture, a frame | `apothecary/evidence/frames.py` keeps it with the poll it was taken beside, under a budget | [The Working space](working-space.md) | `walkthrough/18-the-working-space.md` |
| the log, the page | `apothecary/evidence/view.py`, at `GET /sites/{site}/evidence` | [The Working space](working-space.md) | `tests/test_evidence.py` |

### Two poses for a part

A part's STL is its SCAD's own render, never turned: the way up it prints, which
the slicer prints as it lies and a download is. A part that stands otherwise in use
declares its rest pose, `rest`, the `-D` definitions that make its SCAD draw it so
([How it rests](parts-authoring.md#how-it-rests)), and a part that says
`display_rotation` is refused when it loads. The page draws a part as it rests,
asking for `?pose=rest`, and a site draws it in that frame, z up, since a node
carries no turn of its own. The bounds a part declares, `measured`, the readiness
check and the slicer stay in the print pose, the SCAD's own frame. The z-up turn
into three.js's frame is written in two places: `sceneAt` in
`apothecary/static/frames.js`, which the page, `apothecary/static/machine_marks.js`,
`apothecary/static/lighting.js` and `apothecary/static/picture_marks.js` import, and
the page's `applyScadAxisTurn`, which turns a mesh's own vertices.
