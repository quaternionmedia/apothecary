# rolling_rotor

A rotor that rolls round inside its stator instead of turning on a shaft. The
rotor is a disc a little smaller than the track it stands in: pulled to one
side it touches the track there, and pulled round, the place it touches goes
round the track and the rotor rolls. Rolling without slip, each orbit of its
centre turns it back by `eccentricity / (bore - eccentricity)` of a turn, so
the slow turn is the output and the orbit is the input. Above the track the
stator's pole teeth stand back by `gap`: the gap between the poles and the
rotor closes to `gap` where the rotor touches the track and opens to `gap`
plus twice the eccentricity opposite, and the place where it is least goes
round with the orbit. It is the [airgap](../airgap/README.md)'s rotor and
stator with the shaft taken away: the airgap's offset rotor turns rigidly
about the axis, a cam, while this one's centre goes round and it turns back
on itself under it.

The stator and the rotor print side by side, each flat on the bed with
nothing overhanging; `print = false` (hidden) draws them assembled at
`orbit`, which is how the part rests in the world.

## Render

```bash
uv run apothecary parts generate-stl rolling_rotor                       # the two pieces, as they print
uv run apothecary parts generate-stl rolling_rotor -p eccentricity=2      # a faster creep, a wider swing of the gap
openscad -o assembled.stl -D print=false -D orbit=60 parts/rolling_rotor/rolling_rotor.scad
```

## Parameters worth tuning first

| | | |
|---|---|---|
| `bore`, `eccentricity` | 30, 1 mm | The track's radius and how far the rotor's centre stands off the axis; the rotor's radius is their difference, and each orbit turns it back by their ratio |
| `gap` | 0.5 mm | How far the pole tips stand back from the track: the least gap between the poles and the rotor |
| `poles`, `pole_width`, `pole_depth`, `yoke` | 8, 8, 10, 5 mm | The teeth a coil is wound on, and the ring behind them |
| `stack`, `base`, `track_height` | 12, 2, 2 mm | The rotor's height, the floor it stands on, and the track's height above the floor |
| `hole`, `outputs`, `output_pin`, `output_circle` | 10, 4, 4, 16 mm | The rotor's centre hole, and the holes an output disc's pins run in |
| `orbit` | 0 | Where the rotor's centre stands, as drawn assembled |
| `facets` | 180 | Sides of a circle; a multiple of 12 |

A set of values whose teeth meet at their tips, or whose holes leave less
than two millimetres of wall, is refused, saying which.

## What is printed and what is bought

Printed: the stator (floor, track, teeth and yoke in one piece) and the
rotor. Bought, and not drawn: `outputs` pins of `output_pin` diameter on an
output disc that turns on the axis, each running round the wall of its hole
in the rotor (the holes are a pin's diameter plus twice the eccentricity); a
ball bearing of `hole` outside diameter on an eccentric crank, where a crank
drives the orbit instead of the poles; magnet wire for a coil on each tooth,
in the room `slot_area` measures. Printed plastic carries next to no magnetic
flux, so for the poles to pull the rotor round, the teeth and the rotor's rim
need soft iron in them, which the part does not draw or choose.

## What is measured, and what is not

`apothecary/projects/parts/rolling_rotor.py` measures the part from its own
outlines with `apothecary/gap_geometry.py`: the gap from every point of the
poles to the rotor at any orbit, its least and where that is, where the
closest approach goes through an orbit on the stator and on the rotor, that
the rotor never touches anything but the track, a slot's cross-section, and
each piece's volume. The roll's ratio is the pose's assumption, not a
measurement: whether the rotor rolls without slipping, how hard the poles
pull it, and what torque the slow turn gives are a bench's to say
([docs/airgap.md](../../docs/airgap.md#at-the-bench)).
