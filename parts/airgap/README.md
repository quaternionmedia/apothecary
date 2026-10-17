# airgap

A rotor/stator pair of any base form, with the conductors that wind it. The
rotor and the stator each start from a base curve -- a circle, an ellipse, a
superellipse, a rounded polygon or a constant-width support curve -- scaled in
its own frame by a nautilus step, a Möbius ribbon's reach and fractal gearing,
then rotated and offset from the machine axis and re-sampled as a polar profile
about that axis. The bore is scaled so the closest approach over every rotor
angle is the nominal air gap. The stator can be cut into covered segments
behind a concentric, round, square or hexagonal frame. Windings reduce to
conductor stations -- tooth coils, lap coils, wave windings, toroidal belts, a
sinusoidal sheet or stations typed by hand -- and are swept as bundles.

Every surface is computed in the SCAD from the assignments at its top, so the
part is edited as text: Part › Edit in the page, or the file itself. Change a
base form, a feature ratio, a coverage or a slot string and the part follows;
a saved variant carries its values ([walkthrough page 06](../../walkthrough/06-editing-a-parts-scad.md)).
The Airgap panel of the viewer explores the same geometry as a field, torque
and dynamics model and writes a chosen arrangement into this editor
([docs/airgap.md](../../docs/airgap.md)).

## Render

```bash
uv run apothecary parts generate-stl airgap                                  # the pair, as the viewer draws it
uv run apothecary parts generate-stl airgap -p rotor_base_form=ellipse        # with a value moved
uv run apothecary parts generate-stl airgap -p topology=lap -p pitch=3        # another winding
openscad -o airgap.stl -D show_windings=false parts/airgap/airgap.scad       # the cores alone, fast
```

Each bundle is swept as one polyhedron. On OpenSCAD 2021.01, which unions
every bundle through the teeth with CGAL, `time openscad -o airgap.stl
parts/airgap/airgap.scad` says a few seconds for the tooth coils and about half
a minute for a lap winding; an OpenSCAD with Manifold (`apothecary openscad
install`) is the fast path the walkthrough installs before the first serve.
Evaluating the file -- what the editor's check does -- is a fraction of a
second on either. `sweep_hulls = true` (hidden) sweeps hulls of spheres
instead: slower, and indifferent to a path that crosses itself.

## Parameters worth tuning first

| | | |
|---|---|---|
| `r0`, `stack`, `gap` | 30, 20, 1.5 mm | The rotor's base radius, the stack length and the air gap everything else is scaled to |
| `rotor_base_form`, `stator_base_form` | circle | The base curves; `*_base_ratio`, `*_base_exp`, `*_base_sides`, `*_base_round`, `*_base_width_*` shape each |
| `rotor_spiral_b`, `rotor_spiral_k` | 0.35, 2 | The nautilus: growth per turn and steps per revolution (0 growth is none) |
| `rotor_rib_k`, `rotor_rib_w` | 3, 0.12 | The Möbius ribbon's lobes and reach |
| `stator_teeth_n`, `stator_teeth_l` | 12, 3 | Teeth, and fractal levels of smaller teeth under each |
| `stator_cov_segs`, `stator_cov_arc` | 1, 1 | Segments, and the fraction of the ring they cover |
| `stator_outer_form`, `stator_yoke` | concentric, 6 mm | The frame behind the yoke and its thickness |
| `rotor_off_x`, `stator_off_y`, … | 0 | Offsets from the axis, in r0: an offset rotor is eccentric, an offset stator a displaced bore |
| `topology`, `pattern`, `layout` | tooth, diametral, "" | The winding, which phase each slot gets, and a slot string (`A+ A+ C- C- …`) when the pattern is custom |
| `turns`, `span`, `pitch`, `wire_d` | 50, 0.6, 1, 1.2 mm | Turns per coil, a tooth coil's span in slot pitches, a lap coil's pitch in slots, the bundle diameter |
| `custom_stations` | "" | Stations typed by hand when the topology is custom: `A: 0:50 90:-50; B: 30:50` (degrees:turns) |

`resolution` is the number of polar samples about the axis (360); the surfaces
are sampled in their own frames at `own_samples` (2880, hidden) before being
re-sampled. `-D echo_surfaces=true` prints the sampled surfaces, the stations
and the conductor paths; `tests/test_airgap_part.py` compares them with the
Python mirror in `apothecary/projects/parts/airgap.py`, which is what the
envelope and the panel's figures are computed from.
