# flexure_rotor

A rotor carried on leaves printed with its stator, in one piece. A hub with
lobes stands inside a ring with posts, joined to it by thin leaves: the hub
turns by bending them, a few degrees either way, with no bearing and nothing
to assemble. Each lobe has a post beside it, `stop` degrees round: turning
the hub that way closes the gap between the lobe's flank and the post's,
`post_r * sin(stop - swing)`, until they touch and stop it. The leaves are the
spring that brings it back. It is the [airgap](../airgap/README.md)'s rotor
and stator with the bearing printed in: the same pair, the same rigid turn
about the axis, over a few degrees instead of whole turns, and the rotor and
the stator are one compliant piece.

Drawn at `swing`, the hub is turned and each leaf bent as a beam built in at
both ends is for a small turn: a cubic from the hub's rim to the ring,
leaving each square to it. It prints flat, as drawn at `swing = 0`, with
nothing overhanging; at the default 0.8 mm a leaf is two lines of a 0.4 mm
nozzle, so check that the slice keeps both.

## Render

```bash
uv run apothecary parts generate-stl flexure_rotor                    # the piece, as it prints
uv run apothecary parts generate-stl flexure_rotor -p swing=6          # turned 6 degrees, the leaves bent
uv run apothecary parts generate-stl flexure_rotor -p lobes=3 -p post_arc=20 -p leaves=1
```

## Parameters worth tuning first

| | | |
|---|---|---|
| `hub`, `lobes`, `lobe_r`, `lobe_arc` | 10 mm, 2, 22 mm, 40 | The hub the leaves start from, and the lobes it carries |
| `ring`, `wall`, `post_r`, `post_arc` | 34, 5, 14 mm, 30 | The ring the leaves end at, and the posts reaching in from it past the lobes' tips |
| `stop` | 8 | How far the hub turns before each lobe's flank meets its post's |
| `leaves`, `leaf` | 2, 0.8 mm | Leaves in the room after each post, and their thickness; their length is `ring - hub` |
| `height` | 8 mm | The whole piece's height |
| `pocket`, `pocket_depth` | 6.2, 3 mm | A pocket from the top in each lobe and each post, 0 for none |
| `swing` | 0 | The hub's turn as drawn; a swing at or past `stop` is refused |
| `facets` | 180 | Sides of a circle; a multiple of 12 |

A set whose posts would pass over the lobes (so nothing stops the hub),
whose pieces stand less than half a millimetre apart, which leaves no room
for its leaves, or whose pockets leave less than two millimetres of wall, is
refused, saying which.

## What is printed and what is bought

Printed: the one piece. Bought, and not drawn: what goes in the pockets, a
6 mm by 3 mm disc magnet or a steel slug of that size at the defaults, one in
each lobe and each post; and whatever drives the hub -- a coil set against a
post, a magnet brought near a lobe, a finger. Which way a magnet faces, and
what pulls what, is the bench's first question.

## What is measured, and what is not

`apothecary/projects/parts/flexure_rotor.py` measures the piece from its own
outlines with `apothecary/gap_geometry.py`: the gap between each lobe and its
post at any swing, held to `post_r * sin(stop - swing)`; the clearance of the
hub from the ring and of each leaf from the lobes and posts; the swing at
which a lobe first touches its post, found from the outlines; the strain at a
leaf's surface bent to a swing, `leaf / 2` times its sharpest curvature, which
for a small turn `a` is `leaf * a * (2 L + 3 hub) / L^2` with `L = ring - hub`;
and the volume. That strain is a beam's bending with its sections staying
plane, its stretch along its length left out. How stiff the leaves are, how
fast the hub rings when struck, how far it swings for a given pull, and
whether a leaf survives its strain belong to the filament and the print, and
are a bench's to say ([docs/airgap.md](../../docs/airgap.md#at-the-bench)).
