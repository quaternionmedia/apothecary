# The Airgap

The `airgap` part is a rotor/stator pair of any base form; the Airgap panel is
that part as a field, torque and dynamics model, in a tab of the viewer's rail.
The two meet in the part's text: the panel reads the part's top-level
assignments -- the SCAD editor's text while the part is being edited, its own
file otherwise -- and computes from them, and what the panel chooses is
written back into that text, where the editor's check and render see it. The
geometry has one source, and it is the SCAD ([parts-authoring.md](parts-authoring.md),
*the text is the truth*).

## The part

[parts/airgap/airgap.scad](../parts/airgap/airgap.scad) computes every surface
from the assignments at its top, grouped the customizer's way: `[Scale]`,
`[Rotor]`, `[Stator]`, `[Windings]`. Each side starts from a base curve
(circle, ellipse, superellipse, rounded polygon, constant-width support curve),
is scaled in its own frame by a nautilus step, a Möbius ribbon's reach and
fractal teeth, then rotated and offset from the machine axis and re-sampled as
a polar profile about it; the bore is scaled so the closest approach over every
rotor angle is the nominal gap. The stator can be cut into covered segments
behind a concentric, round, square or hexagonal frame. Windings reduce to
conductor stations -- tooth coils, lap coils, wave windings, toroidal belts, a
sinusoidal sheet or stations typed by hand -- and each bundle is swept as one
polyhedron.

Part › Edit on it edits it as any part: a control writes its line, a line
typed moves its control, a saved variant carries the arrangement
([walkthrough page 06](../walkthrough/06-editing-a-parts-scad.md)). The Python
mirror, `apothecary/projects/parts/airgap.py`, computes the same pipeline for
the envelope and for the checks; `tests/test_airgap_part.py` runs the SCAD with
`-D echo_surfaces=true` and holds radii, coverage, stations and conductor paths
to it, and with `--slow` the declared envelope to the rendered one. The part's
README lists the parameters worth tuning first and what a render costs on each
OpenSCAD.

## The panel

Panels › Airgap on the canvas ring, or the Airgap tab of the rail. Shown, the
panel computes from the part's text and draws the section -- the rotor at its
angle, the stator's iron by covered run, the gap field or the gap itself as
colour, each conductor with its phase and its sense -- and, in folds below it:

| Fold | |
|---|---|
| Metrics | One document, `airgap/metrics/1`: geometry, windings, the static field and torque, the run |
| Winding functions and gap field | Each phase's N(θ), and the signed gap flux density at the rotor angle |
| Gap map g(θ, φ) | The gap over stator angle and rotor angle; rotor features sweep as diagonals, stator features stand as verticals |
| Phase inductance and commutation | Each phase's L against rotor angle, and the currents the rig's excitation applies |
| Co-energy and torque | W′ and T against rotor angle |
| Harmonic overlap | The orders both surfaces carry, and the dominant ripple order |
| Run-up, Rotor orbit, Vibration spectrum | The run: speed and torque against time, the rotor centre's path with the clearance and touchdown rings, the stator's modes, and their spectrum |
| Rig | The settings the geometry runs under, as one JSON document |
| Sweep | A metric mapped over two of the SCAD's names |

The panel computes in the browser, in the same degrees and with the same
nudges as the SCAD: surfaces, winding functions, the permeance tables, co-energy
and torque by finite difference, the generalized magnetic forces and
stiffnesses per degree of freedom, and a run of the rotor's spin, whirl and
axial motion with the stator's modes under the rig (RK4). Nothing is fetched
from outside the page.

### Following the text

While the airgap part is in the editor, the panel follows every edit of its
text, within the frame, and says *following the editor*. A preset chosen in
the panel is written into the text -- the editor checks and renders it as any
edit -- and the rig the preset names is set. A sweep cell clicked writes its
two values the same way. With no editor on the part the panel holds values of
its own (*the panel's own values*) until To editor writes them.

### The verbs

Panels › Airgap holds the panel and seven verbs; each is also the panel's
button of the same name, which wears the cell's address.

| Cell | |
|---|---|
| Airgap | The panel shown or hidden |
| Play | The rotor spun, or the run played, and paused; what Play moves is the rig's `playback` |
| Sweep | The metric the sweep line names mapped over its two ranges |
| To editor | The panel's values written into the airgap part's text; Part › Edit opened on it first where this site has it |
| From editor | The part's text read again |
| Copy SCAD | The part's text with the panel's values written in, copied |
| Copy metrics | The metrics document copied |
| Reset | The panel back on the part's own text, its rig and sweep as they start |

### The rig

The rig is what the geometry runs under, one JSON document in the Rig fold:
the excitation (`excite` auto · sin · dc · uniform, `current` in A, `advance`
in electrical degrees) and the drive, load, bearing, axial, carrier, yoke and
playback settings. A value outside its range is clamped and said; an unknown
name is refused. A preset sets the rig with its geometry. The settings and
their ranges are `DYN_SPECS` in `apothecary/static/widgets/airgap.js`.

### The sweep

One line: `stator_teeth_n 3..24 × rotor_rib_k 0..12 → mean_torque`. Two of the
SCAD's names with their ranges, and the metric: `mean_torque`, `ripple`,
`peak_b`, `mean_coenergy` or `dominant_order`. Run maps it; a cell clicked
takes its two values.

## The metrics document

The panel says its figures as one document, `airgap/metrics/1`, with at most
one each of the groups `geometry`, `windings`, `field` and `dynamics`, in that
order of meaning; a metric is `{key, label, value, unit, note}`, its value a
finite number, a string, a boolean or `null` for *unavailable*. The panel is
the only thing that computes a figure; Python validates and renders:

- `GET /airgap/metrics/schema`: the JSON Schema, the published contract.
- `POST /airgap/metrics/validate`: a document read back normalized, or as
  Markdown with `?format=md`; 422 names what is wrong with one.
- `apothecary airgap metrics validate <file> [--format summary|json|md]` and
  `apothecary airgap metrics schema`: the same from the shell.

The Markdown view rounds for display and never recomputes; `tests/test_airgap_metrics.py`
holds the contract and that promise.

## What it costs the page

Eleven controls of the viewer's own, seven of them ring-backed, under the
census ([census.md](census.md)); one cell of the canvas ring's Panels, the
eighth and last, so no address before it moved.
