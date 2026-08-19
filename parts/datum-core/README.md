# datum-core

A two-piece enclosure for a 40 × 40 mm control-surface board: a printable tray
with four standoffs and an edge-connector cutout, and a printable lid with four
contact openings and an indicator light pipe.

It renders from its own defaults and knows nothing about any particular PCB.
Every dimension is a parameter.

## Render

```bash
openscad -o datum-core.stl parts/datum-core/datum-core.scad                 # tray
openscad -o lid.stl -D 'show="lid"' parts/datum-core/datum-core.scad        # lid
openscad -o both.stl -D 'show="exploded"' parts/datum-core/datum-core.scad  # assembly
```

`show="exploded"` is the one to look at while tuning fit. It is a preview, not
a printable object.

## Parameters worth tuning first

| | | |
|---|---|---|
| `board_x`, `board_y` | 40 | Board footprint. Everything else follows from it |
| `board_clearance` | 0.4 | Board edge to cavity wall |
| `standoff_h` | 4.0 | Floor to board underside — clears through-hole legs and solder |
| `headroom` | 8.0 | Board top to lid underside — clears the tallest component |
| `mount_inset` | 3.5 | Mounting hole centres, inset from the board edge |
| `connector_w`, `connector_h` | 9.4 × 3.6 | Edge connector opening, plus `connector_margin` each side |
| `contact_pitch_x/y` | 18 | Contact opening spacing, a 2 × 2 grid |
| `indicator_x`, `indicator_y` | 0, 14 | Light pipe position, relative to the board centre |
| `lip_clearance` | 0.25 | Lid lip to cavity wall. Print-process dependent |

## Fit is unverified

These numbers are assumptions, not measurements. No schematic exists for the
board this is sized around, so the footprint, the connector position, the
indicator position and the contact grid are all placeholders chosen to render
coherently and to be easy to move.

What has to be checked against a real board before this is printed in anger:

- board footprint and corner radius
- mounting hole pattern — this assumes four, symmetric, inset equally
- connector height above the board surface, which sets the cutout centre
- indicator position, and whether a light pipe or an open hole is wanted
- tallest component, which sets `headroom`

## Bounds

`apothecary parts info datum-core` reports the envelope. At the defaults the
tray is 45.6 × 45.6 × 15.6 mm.
