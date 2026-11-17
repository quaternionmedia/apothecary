# Dust

Dust collection: an adapter that joins a hose to the ports it serves, and
stand-ins for the hose and the ports until the real ones are measured. Each
part declares its interfaces, the places another part meets it, and
`apothecary parts fit` says how two meet (docs/connections.md).

| Part | What it is | Interfaces |
|---|---|---|
| `hose_adapter` | A stepped adapter, every end pushing in: a 40 mm hose onto a 32 mm or a 25 mm fitting | `hose`, `fitting_32`, `fitting_25` (spigots) |
| `dust_hose_40` | A stand-in for a smooth 40 mm bore hose, rubber or PVC | `end` (a socket that opens when pushed) |
| `dust_port_32` | A stand-in for a rigid port with a 32 mm bore | `port` (a socket) |
| `dust_port_25` | A stand-in for a rigid port with a 25 mm bore | `port` (a socket) |

The stand-ins are tagged `stub`, and so is each of their interfaces: every
number in them is a guess. `stub_tube.scad` is what they are drawn as; it is a
library, not a part.

## The adapter

Built in Python (`apothecary/projects/parts/hose_adapter.py`) from one profile,
so its solid and its interfaces come from the same numbers. It prints as it is
drawn, hose end on the bed, and needs no support.

| Section | Outside, bottom to top | Length | Bore |
|---|---|---|---|
| `hose`: the hose is pushed on and clamped over it | 39.0 to 41.0 | 40 | 35.0 |
| `flare`: under the collar, at 45 degrees | 41.0 to 46.0 | 2.5 | 35.0 |
| `collar`: the hose's end stops against it | 46.0 | 2.5 | 35.0 |
| `transition` | 46.0 to 32.6 | 8 | 35.0 to 27.4 |
| `step_32` | 32.6 to 31.4 | 25 | 27.4 |
| `shoulder`, as short as the bore may close in | 31.4 to 25.6 | 3.5 | 27.4 to 20.4 |
| `tip_25` | 25.6 to 24.4 | 20 | 20.4 |

Each spigot is its nominal bore, `taper` wider at its base than at its tip
(`hose_taper` for the hose end), and its bore leaves a `wall` of 2.0 at the tip:
five lines of a 0.4 nozzle. At these numbers a 32.0 bore takes the 32 step 12.5
of its 25, a 25.0 bore takes the tip 10 of its 20, and a 40 hose that opens 5%
takes the whole hose end, opened 2.5% at the collar.

The 25 tip costs a 32 fitting airflow: in a 32 port, the air still goes through
the tip's 20.4 bore. `-p tip=false` draws the plain 40 to 32, and a saw at the
shoulder makes one of a printed adapter. A diameter the real fittings do not
have moves the seat a long way: a taper of 1.2 over 25 moves it about 2 mm for
each 0.1 of bore, so measure the fittings before printing for them, and set
`fitting_d` and `tip_d` to what was measured.
