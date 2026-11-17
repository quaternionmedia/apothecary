# The Airgap

The `airgap` part is a rotor/stator pair of any base form; the Airgap panel is
that part as a field, torque and dynamics model, in a window of the viewer's own.
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
OpenSCAD; [walkthrough page 17](../walkthrough/17-a-part-that-computes-itself.md)
walks the mirror and the document in doctests.

## The panel

Panels › Airgap › Airgap on the canvas ring opens it, a tab beside Pictures,
closed until asked for. Shown, the
panel computes from the part's text and draws the section -- the rotor at its
angle, the stator's iron by covered run, the gap field or the gap itself as
colour, each conductor with its phase and its sense. What it computes is in
windows of their own, grouped under Airgap in the header's ⊞ Windows and in
every stack's + ([the windows](viewer.md#the-windows)); one opened while the
panel is open is a tab beside it. Panels › Windows › Airgap view lays them all
out together, the world among them. The Airgap is a focused system, these
windows its entry in `apothecary/systems.py` ([the viewer](viewer.md#the-windows)):

| Window | |
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
| Sweep | The metric the sweep line names mapped over its two ranges, in the Sweep window, opened if it was closed |
| To editor | The panel's values written into the airgap part's text; Part › Edit opened on it first where this site has it |
| From editor | The part's text read again |
| Copy SCAD | The part's text with the panel's values written in, copied |
| Copy metrics | The metrics document copied |
| Reset | The panel back on the part's own text, its rig and sweep as they start |

### The rig

The rig is what the geometry runs under, one JSON document in the Rig window:
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

## What the gap is taken to be

The airgap part and its panel take the machine to be two rigid bodies about
one axis. The rotor turns rigidly about that axis -- an offset rotor is an
eccentric turning with it, a cam -- and the stator stands still. The gap is
read along rays from the axis, the bore's radius less the rotor's, `g(θ, φ)`;
it is the same all along the stack, and the bore is solved so its least over
every rotor angle is the nominal gap. The panel's field counts the gap's
reluctance alone, as though the iron took none, with no fringing; its masses
are of steel's density; and its run moves the rotor's centre and the stator's
modes as small changes added to that same radial gap. Those are the model's
assumptions, and the figures of the metrics document stand on them.

## A gap that is not one number

`apothecary/gap_geometry.py` measures a gap that varies along the machine and
with the pose of what moves, for bodies that are not one rigid pair about one
axis. A body is a polygon in its own frame and a pose places it; both bodies
may move. It reads two gaps: the radial gap along rays from a centre, which is
the airgap's, and the clearance from each point of one boundary to the nearest
of the other, which is what closes at a contact and what a collision is. For
bodies a ray crosses once, the clearance is never more than the radial gap on
the same ray. Of either it gives the least, the mean and where the least is.
Through a sequence of poses it follows the closest approach and says how far
it goes round each body and along each: it *sweeps* when it goes round the
stator and stays at one place on the rotor (a cam, the airgap's offset
rotor), *stands* when the reverse, *rolls* when it goes round both the same
distance, *slips* when the distances differ, and *rocks* when it goes round
neither. Every distance is between polygons, within a circle's sagitta of
the circle. It knows no field, force or material, and its figures are not in
the metrics document, whose figures the panel alone computes.
[Walkthrough page 44](../walkthrough/44-a-gap-that-travels.md) runs it on the
airgap's eccentric rotor and on the two parts below.

## Rotors that do not turn on a shaft

A conventional machine is a rigid rotor, a rigid stator and a uniform gap,
and its motion is one rigid turn. Each family below lets one of those go.

| Family | The motion | The gap | Here |
|---|---|---|---|
| Rolling and eccentric | The rotor's centre goes round and the rotor turns slowly back under it, rolling on the stator: a rolling rotor, a wobble plate, a cycloidal disc on pins | Closes at one point, or a few, that travels with the orbit | `rolling_rotor` |
| Travelling and strain wave | A flexible ring is pushed into a wave that goes round; the ring creeps by its difference in length or teeth from what it rolls in: a strain-wave gear's flexspline, a peristaltic drive | Closes at the wave's crests, several at once, travelling | the panel's run drives a travelling wave across the yoke (its peristaltic preset); no part |
| Compliant and flexure-borne | The rotor turns or oscillates a few degrees on printed leaves instead of a bearing; the rotor and the stator are one piece | Unchanged along the rays; a gap at a flank closes to a stop | `flexure_rotor` |
| Segmented and distributed | Many movers in one stator's field: tiles, a chain, a track; the gap unrolled along a line or wrapped on a cone or a sphere | One gap per mover, each its own function of position | none |
| Soft and bio-shaped | Fins, inchworms, antagonistic pairs: the stator is whatever is anchored at the moment | Between each actuator and its anchor, changing with the gait | none |

### The rolling rotor

[`rolling_rotor`](../parts/rolling_rotor/README.md) is the airgap's pair with
the shaft taken away. A disc of radius `bore - eccentricity` stands in a track
of radius `bore`; at `orbit` its centre stands `eccentricity` off the axis
where it touches the track, and rolling on the track without slip it has
turned back `orbit * eccentricity / (bore - eccentricity)`. Above the track
the pole teeth stand back by `gap`, so the gap to the poles closes to `gap`
where the rotor touches and opens to `gap` plus twice the eccentricity
opposite. Its closest approach goes once round the stator and `bore / (bore -
eccentricity)` times round the rotor each orbit. The stator and the rotor
print side by side; the part rests assembled. The roll without slip is the
pose's assumption, and nothing in the part enforces it: a lobed disc on a
ring of pins would make the ratio a matter of the teeth.

### The flexure rotor

[`flexure_rotor`](../parts/flexure_rotor/README.md) is the airgap's pair with
the bearing printed in: a hub with lobes inside a ring with posts, joined by
leaves, one piece. The hub turns rigidly about the axis by bending the
leaves, so its gap along the rays is the airgap's `g(θ, φ)` over a few
degrees. Each lobe has a post `stop` degrees round from it, and turned that
way the gap between their flanks is `post_r * sin(stop - swing)` until they
touch. Drawn at `swing`, each leaf is the cubic of a beam built in at both
ends, and the strain at its surface is half its thickness times its sharpest
curvature: for a small turn `a`, `leaf * a * (2 L + 3 hub) / L^2`, with `L`
its length. It prints flat in one piece; a pocket in each lobe and each post
takes what is bought.

Neither part declares `kinematics`: that contract moves a machine's pieces
along x, y and z with its tool's mark ([docs/cnc.md](cnc.md)), and a turn
about an axis, or a pose that follows one drive angle, is not in it. Each
part takes its pose as a parameter, `orbit` and `swing`, as the airgap takes
`phi`, and Part › Edit's control for it moves it. The Airgap panel reads the
airgap part alone.

## What is measured, and what is not

The two parts are measured from their own outlines, by the functions their
modules name, and their tests hold each measure to an answer known without
it: a closed form, the SCAD's echo, or a render.

| Measured from geometry | Not measured here |
|---|---|
| The gap at every point of the stator or the posts, at any orbit or swing, its least and where that is | Force, torque, flux, inductance: no field is solved |
| Where the closest approach goes through a cycle, on each body, and whether it rolls or slips | Whether a real track rolls without slipping |
| That nothing touches but what is meant to, through the whole motion, and the swing at which a stop is reached | How hard the stop is met, and what wears |
| A slot's cross-section, the room its coils share | How many turns of which wire fit, and how warm they run |
| A leaf's bending strain at a swing | The leaves' stiffness, the hub's ringing, and whether a leaf survives the strain: the filament's and the print's |
| Each piece's solid volume | Its mass, which is that times the filament's density and the slicer's fill |

A textbook relation can say which way a figure goes and not how far: the pull
across a gap between iron faces rises as the gap closes, for a given current,
and nothing here puts a number on it for these parts.

## At the bench

What the geometry leaves open is settled on the printed parts:

1. **Does the rotor roll?** Drive the rolling rotor's orbit by hand -- a crank
   through a bearing in its centre hole -- for a counted number of orbits,
   and mark how far the rotor turns back. Without slip it turns back the
   eccentricity over its radius of a turn each orbit; the difference is the
   slip, with the rotor free and again with a weight hung from it.
2. **How stiff are the leaves, and how do they ring?** Hang known weights from
   an arm on the flexure rotor's hub and read the swing (or read the arm's
   pull at the stop with a force gauge), then pluck the hub and film it ring
   down. That gives the leaves' turning stiffness, the hub's frequency and
   how fast it dies away for that filament and print; cycling it to the stop
   many times says whether the leaves last.
3. **How does the pull grow as the gap closes?** Set a magnet in a lobe's
   pocket and a steel slug in its post's, and read the force at the lobe
   with a gauge at several swings, each swing's flank gap read from
   `flank_gap`. That gives the curve of pull against gap for those pieces,
   and whether it beats the leaves before the stop.

## What it costs the page

Eleven controls of the viewer's own, seven of them ring-backed, under the
census ([census.md](census.md)); one cell of the canvas ring's Panels, the
eighth and last, so no address before it moved.
