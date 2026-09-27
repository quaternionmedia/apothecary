# Designing a part from the browser: a spike

*A research spike, not a decision. It maps the loop a person has today for
changing a part from the viewer, what other tools do, and recommends an
order of work. Measured on 2026-09-27 against `review/2026-09-26`.*

## The loop today

A part is changed through its declared `Params` model and nothing else.

1. Select the part; `appendPartPanel` (`templates/fractal_viewer.html.j2`)
   shows the checklist, sliders built from `GET /parts/{name}/params`, a
   stage bar with Apply and Revert, and the SCAD source as read-only text.
2. Each slider event posts the whole staged set to `POST /parts/{name}/validate`
   (a Pydantic check, no render; not debounced) and shows the declared
   envelope from `get_bounds`.
3. Apply posts `POST /parts/{name}/stl/generate?force=true`. The request is
   held open for the whole OpenSCAD run, then every node showing the part
   reloads the one STL on disk.

What that loop cannot do:

- **Edit SCAD.** The source is read-only; includes and the SCAD a Python
  part generates are not shown at all. No save, no history, no variants.
- **Keep more than one variant.** Apply overwrites the part's single STL,
  which every tab shares; two tabs applying at once race. Returning to the
  defaults is a full re-render.
- **Remember what is drawn.** The viewer starts `committed` from the model's
  defaults, not from the params sidecar, so after a reload it can misreport
  a variant on disk as the default. No route exposes the sidecar.
- **Say why a render failed.** The route drops OpenSCAD's stderr and
  `dropped` lines, and the page shows 140 characters of the HTTP error.
- **Offer every parameter.** Sliders only, no typed value, no booleans or
  strings; ranges are synthesised (a quarter to two and a half times the
  default) where the model has none. A part without a `Params` model has no
  controls, though `validate_overrides` accepts its SCAD's top-level
  variables.
- **Notice an edited include.** Freshness tracks the SCAD and the wrapper
  modules, not what the SCAD includes.
- **Reach it from the ring.** `_node_ring` (`apothecary/menu.py`) has no part
  verbs, against the one-screen plan's rule that every action has a cell.

## What renders cost

Wall time per part, process start and STL export included (a scratch
benchmark, not a repository command):

| Part | 2021.01 (installed, CGAL) | snapshot 2026.09.23, `--backend=manifold` |
|---|---|---|
| calibration_cube | 1.25 s | 0.06 s |
| contranot | 2.55 s | 0.08 s |
| datum_core | 4.64 s | 0.22 s |
| ender3 | 2.32 s | 0.08 s |
| gridfinity bins | refused (needs 2021.08.24 or newer) | 0.30 s |

The snapshot with its old CGAL backend is barely faster than 2021.01
(gridfinity takes 30.7 s there); the kernel is the gain. No stable release
carries Manifold: 2021.01 is still the latest, and Manifold became the
snapshots' default in 2025-08. The flag is `--backend=manifold`;
`--enable=manifold` is accepted with a warning and renders with CGAL.

The docs' "thirty seconds of OpenSCAD" (`tests/test_staging.py`,
`walkthrough/02-fitting.md`, `api.py`) matches no measured part.

## What others do

- **OpenSCAD Playground** (OpenSCAD compiled to WebAssembly): a fresh worker
  per run, cancelled by terminating it; a syntax check 300 ms after typing
  stops (`--export-format=param`, which also yields the customizer schema),
  a render at one second with `$preview=true` prepended; errors parsed from
  stderr into editor markers. The wasm is about 3 MB gzipped plus libraries,
  and it links CGAL, so the page ships GPLv3 object code.
- **CadQuery / build123d with OCP CAD Viewer**: a warm local process pushes
  tessellations to the browser over a WebSocket; save to repaint is about a
  tenth of a second. This is apothecary's shape: a local server, a warm
  process, a push.
- **JSCAD** keeps a persistent worker and a parameter form it builds itself;
  **replicad** runs OpenCascade in a worker; **MakerWorld** runs OpenSCAD
  wasm against customizer annotations. **Zoo** is the one tool whose
  dragging rewrites the model's code, and it needs a hosted engine.
- **Customizer annotations** (`x = 34; // [10:100]`, `/* [Tab] */`) and
  `--export-format=param` (snapshots only) give a slider schema straight
  from the SCAD, with no parser of apothecary's own.
- **Editors**: CodeMirror 6 (MIT, roughly 100-200 KB with lint) with a
  small hand-written OpenSCAD mode vendors cleanly. Monaco is about 5 MB and
  its only OpenSCAD grammar is the Playground's, which is GPL.

## Options

| | Per iteration | Cost in the page | Fits stays-local | Effort |
|---|---|---|---|---|
| A. Server CLI, 2021.01 (today) | 0.6-4.6 s; gridfinity refused | none | yes | none |
| B. Server CLI, snapshot with Manifold | 0.05-0.3 s plus transfer | none; OpenSCAD stays a subprocess | yes | low |
| C. OpenSCAD wasm in the page | tenths of a second to seconds, single-threaded | ~3 MB wasm, GPLv3 in the page, a CSP change (`wasm-unsafe-eval`), libraries in a virtual filesystem, a second OpenSCAD to keep in step | yes, once vendored | high |
| D. B for geometry, the browser for editing | a check per pause in typing, a render per second of quiet | CodeMirror 6 and a mode of our own | yes | medium |

## Recommendation: B, then D

**Iteration 1: fast, honest renders (B).**
- Resolve a snapshot through the requirement seam that already exists
  (`openscad_min_version`, `find_openscad`), and pass `--backend=manifold`
  when the chosen OpenSCAD supports it; 2021.01 keeps working, only slower.
- A content-addressed variant cache: key on the SCAD and its includes, the
  overrides, the OpenSCAD version and backend; `render_part` renders to any
  path, and the node-STL cache in `api.py` is the precedent (lock, trim).
  Apply writes a variant and points the part at it; the canonical STL is the
  default variant. Two tabs no longer race.
- The generate route returns stderr parsed to `{line, message}` (both the
  2021.01 and snapshot formats) and the measured bounds from
  `--summary=all`; the page shows them, and the part panel starts from the
  sidecar, not the defaults.
- Superseded renders are cancelled; validate is debounced.
- Correct the "thirty seconds" prose to name the command that measures it.

**Iteration 2: parameters from the SCAD itself.**
- Where `--export-format=param` is available, `/parts/{name}/params` falls
  back to the customizer schema for a part without a `Params` model, so
  every part gets controls; typed number fields beside sliders, checkboxes,
  strings.
- Part verbs join the ring (Apply, Revert, Edit, Variants), per the
  one-screen plan.

**Iteration 3: editing SCAD (D).**
- A vendored CodeMirror 6 with a small OpenSCAD mode in a panel tethered to
  the part; a parameter check 300 ms after typing stops, a render after a
  second of quiet, errors as inline markers.
- A draft is written beside the part (includes still resolve) and rendered
  into the variant cache; Save writes the SCAD, and history is git's: a save
  is a commit the person makes, not one the page makes silently.
- Python-geometry parts (the snowplow) show their generated SCAD read-only;
  their editing surface is their parameters.

**Iteration 4: handles.** A three.js handle bound to one named numeric
parameter (a length, a height), writing to the parameter, never the source;
the mesh scales while dragging and re-renders on release. Rewriting code
from a drag needs to know where each value came from, which is research.

**Not now: wasm in the page (C).** It duplicates the server, puts GPLv3 in
the page, and needs a CSP change the personal-data record's tests hold
against. Revisit only for a static export with no server, and take it to
the licence review first.

## For a person to decide

- Whether apothecary may depend on an OpenSCAD development snapshot for its
  fast path, given no stable release carries Manifold, and how a snapshot is
  pinned (a version floor through `openscad_min_version`, or a tested
  snapshot date).
- Whether a saved SCAD edit from the browser is a commit, a file on disk the
  person commits, or a variant that never touches the part's source.
- Where part editing sits against the pictures-in-the-world plan: the part
  editor is a panel tethered to the part, and a shape found in a picture
  becomes a part the same editor opens.
