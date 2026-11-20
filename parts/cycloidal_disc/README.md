# cycloidal_disc

A lobed disc that rolls round inside a ring of pins. The disc has one lobe
fewer than there are pins; a crank carries its centre round a circle of
radius `eccentricity`, and the lobes, running on the pins, turn the disc back
one pin's pitch of a lobe each turn of the crank: `pins - 1` turns of the
crank turn it once. It is the [rolling rotor](../rolling_rotor/README.md)
with teeth: the rolling rotor's turn back rests on its track not slipping,
and here the count of lobes and pins sets it, since a disc turned any other
way would stand in a pin.

The disc's flank is constructed rather than quoted. Seen from the disc as it
turns, every pin's centre runs round one closed curve, `(R cos s - E cos N s,
R sin s - E sin N s)` with `R = pin_circle`, `E = eccentricity` and
`N = pins`; the flank is that curve moved in along its normal by the pin's
radius and `clearance`, so each pin stands `clearance` from the flank at every
turn of the crank. A set whose curve loops (`pin_circle` not more than
`eccentricity` times `pins`) or whose flank would fold at a lobe's tip is
refused, saying which.

The stator (a floor with a hole for each pin and a wall round them) and the
disc print side by side, each flat on the bed with nothing overhanging;
`print = false` (hidden) draws them assembled at `crank`, which is how the
part rests in the world.

## Render

```bash
uv run apothecary parts generate-stl cycloidal_disc                       # the two pieces, as they print
uv run apothecary parts generate-stl cycloidal_disc -p pins=15 -p eccentricity=0.8
uv run apothecary parts generate-stl cycloidal_disc -p printed_pins=true  # the pins printed with the floor
```

## Parameters worth tuning first

| | | |
|---|---|---|
| `pins`, `pin_circle`, `pin` | 11, 30, 5 mm | The ring of pins; the disc has `pins - 1` lobes |
| `eccentricity` | 1 mm | How far the crank carries the disc's centre off the axis: the lobes' depth is twice it |
| `clearance` | 0.1 mm | How far the flank stands back from each pin as drawn: what lets the disc turn a little either way at a standing crank |
| `thickness`, `base`, `wall` | 7, 3, 6 mm | The disc, the floor the pins stand in, the wall round them |
| `bearing`, `shaft` | 22, 8 mm | The disc's centre hole for the crank's bearing, the floor's for its shaft |
| `outputs`, `output_pin`, `output_circle` | 6, 4, 18 mm | The holes an output's pins run in, each a pin's diameter plus twice the eccentricity |
| `lobe_insert`, `pole_insert`, `insert_depth` | 0, 0, 4 mm | Pockets from the top of each lobe and of the wall between each two pins, for bought inserts; 0 for none |
| `printed_pins` | false | The pins printed with the floor instead of bought and pressed in |
| `crank` | 0 | Where the crank stands, as drawn assembled |
| `profile`, `facets` | 720, 180 | Points on the disc's flank, sides of a circle |

## What is printed and what is bought

Printed: the stator and the disc. Bought, and not drawn: `pins` dowel pins or
ground rods of `pin` diameter, at least as long as the floor and the disc
(unless `printed_pins`); a ball bearing of `bearing` outside diameter, no
wider than the disc, on an eccentric `eccentricity` off the crank's shaft;
`outputs` pins of `output_pin` diameter on an output disc that turns on the
axis, each running round the wall of its hole once a turn of the crank; an
insert for each pocket asked for. The wrapper lists each with its size and
count (`bought`). Printed plastic carries next to no magnetic flux: what goes
in the pockets, if the disc is to be pulled round rather than cranked, is the
owner's to choose.

## What is measured, and what is not

`apothecary/projects/parts/cycloidal_disc.py` measures the part from its own
outlines with `apothecary/gap_geometry.py`: each pin's gap to the disc at any
crank, its least and where; the turn at which the disc fits between the pins
at a crank, and how far it can turn either way before it meets one, its
backlash as drawn; where the pitch circles' contact goes through a turn of
the crank (they roll) and where one pin's contact goes (it slides along the
flank); and that each output pin stays in its hole. How hard anything
presses, what torque the disc passes, how its flanks wear on fixed pins, and
whether a printed disc runs on its pins or binds are a bench's to say
([docs/airgap.md](../../docs/airgap.md#at-the-bench)).
