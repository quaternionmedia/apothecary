# datum_core

The tray of an enclosure for a 40 × 40 mm control-surface board: a printable
tray with four standoffs, an edge-connector cutout, and an antenna relief that
thins the wall opposite the connector without opening it. Its cover is a part
of its own, [`datum_cap`](../datum_cap/datum_cap.scad): four contact openings
and an indicator light pipe over a lip that drops into this tray.

It renders from its own defaults and knows nothing about any particular PCB.
Every dimension is a parameter.

## Render

```bash
uv run apothecary parts generate-stl datum_core                   # the tray, as the viewer draws it
uv run apothecary parts generate-stl datum_core -p headroom=10    # with a parameter moved
uv run apothecary parts generate-stl datum_cap                    # its cover
```

The SCAD draws the tray and nothing else; `openscad -o datum_core.stl
parts/datum_core/datum_core.scad` renders the same. The tray and its lid as one
addressable tree are the `datum_core` site (`/viewer/sites/datum_core`, and
[walkthrough page 03](../../walkthrough/03-an-assembly.md)).

## Parameters worth tuning first

| | | |
|---|---|---|
| `board_x`, `board_y` | 40 | Board footprint. Everything else follows from it |
| `board_clearance` | 0.4 | Board edge to cavity wall |
| `standoff_h` | 4.0 | Floor to board underside — clears through-hole legs and solder |
| `headroom` | 8.0 | Board top to the cover's underside — clears the tallest component |
| `mount_inset` | 3.5 | Mounting hole centres, inset from the board edge |
| `connector_w`, `connector_h` | 9.4 × 3.6 | Edge connector opening, plus `connector_margin` each side |
| `antenna_band`, `antenna_wall` | 8.0, 0.8 | How tall the thinned band of the antenna wall is, and how thin |
| `walls` | 3 | Side wall thickness. House constant, print-validated |
| `tolerence` | 0.4 | Total fit clearance. House constant; the tray draws nothing from it, and `datum_cap`'s lip takes half of it each side |

The contact grid (`contact_pitch_x`, `contact_pitch_y`) and the indicator
(`indicator_x`, `indicator_y`) are the cover's parameters, in `datum_cap`.

## Fit is unverified

These numbers are assumptions, not measurements. No schematic exists for the
board this is sized around, so the footprint, the connector position and the
mounting pattern are placeholders chosen to render coherently and to be easy
to move; so are the cover's contact grid and indicator.

What has to be checked against a real board before this is printed in anger:

- board footprint and corner radius
- mounting hole pattern — this assumes four, symmetric, inset equally
- connector height above the board surface, which sets the cutout centre
- where the radio module's antenna is, which sets the relief
- tallest component, which sets `headroom`

## Bounds

`apothecary parts info datum_core` reports the envelope the tray declares at
its defaults, and `apothecary parts verify datum_core` renders it and checks
that envelope against the real one.
