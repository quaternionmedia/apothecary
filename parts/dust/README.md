# Dust

Dust collection: one part for a round end of a dust system -- a hose's end, a
tool's port, a collector's inlet -- and the adapter between two ends. Each part
declares its interfaces, the places another part meets it, and `apothecary parts
fit` says how two meet; `apothecary parts adapter` generates the adapter between
two ends (docs/connections.md).

| Part | What it is | Interfaces |
|---|---|---|
| `dust_port` | A round end, its parameters which end it is; its sizes are its presets | `end` (a socket, or a spigot) |
| `hose_adapter` | The adapter between two ends, its parameters its two ends; at its defaults a 40 mm hose onto a 32 mm or a 25 mm port | `a`, `step`, `b` |

## The port

`dust_port` (`apothecary/projects/parts/dust_port.py`) is drawn as a stand-in:
a tube standing on the bed, its end at the top. Its parameters are what a
person finds with calipers and a hand:

| Parameter | What it is |
|---|---|
| `socket` | it takes a spigot in (a hose's bore, a port's); off, it is a spigot that goes into one (a tool's outlet stub) |
| `diameter` | what calipers read at the end: a socket's bore at its mouth, a spigot's outside at its tip |
| `length` | how deep a socket's bore holds at that diameter, or how long a spigot is |
| `stretch` | how far a socket's bore opens when pushed, in %: a hose's give, 0 for anything rigid |
| `taper` | how much wider a spigot is at its base than at its tip |
| `wall` | the stand-in's wall |
| `measured` | the numbers were measured on the real end; off, guessed, and its interface says `stub` |

Its presets are the sizes met here, every number in them a guess until the
real thing is measured:

| Preset | What it stands for |
|---|---|
| `hose_40` | a smooth 40 mm bore hose, rubber or PVC: 100 mm of it, opening 5% when pushed |
| `port_32` | a rigid port with a 32 mm bore (the part's defaults) |
| `port_25` | a rigid port with a 25 mm bore |
| `outlet_35` | a tool's outlet stub, 35 mm across, that a hose's cuff goes over |

`dust_port@port_32` names one at the command line; a measured end is a preset
with the caliper's numbers over it: `dust_port@port_32 -p diameter=31.6 -p
measured=true`.

## The adapter

`hose_adapter` (`apothecary/projects/parts/hose_adapter.py`) is built in Python
from one profile, so its solid and its interfaces come from the same numbers.
End `a` stands on the bed and points down; end `b` points up. Each is a spigot
into what it meets or a socket that takes it, sized by what it meets (`a_d`,
`b_d`). A spigot end straddles its bore, `taper` (`a_taper` for end `a`) wider
at its base than at its tip, its own bore leaving a `wall` of 2.0 at the tip:
five lines of a 0.4 nozzle. A socket end's bore is the outside it takes, a lip
of the wall under it. A spigot end `a` has a collar past its base that a hose
stops against. An optional `step` stands between the transition and a spigot
end `b`, so one adapter goes into either of two fittings, one at a time.

At its defaults, the preset `stepped_40_32_25`, it prints as it is drawn and
needs no support:

| Section | Outside, bottom to top | Length | Bore |
|---|---|---|---|
| `a`: the hose is pushed on and clamped over it | 39.0 to 41.0 | 40 | 35.0 |
| `flare`: under the collar, at 45 degrees | 41.0 to 46.0 | 2.5 | 35.0 |
| `collar`: the hose's end stops against it | 46.0 | 2.5 | 35.0 |
| `transition` | 46.0 to 32.6 | 8 | 35.0 to 27.4 |
| `step` | 32.6 to 31.4 | 25 | 27.4 |
| `shoulder`, as short as the bore may close in | 31.4 to 25.6 | 3.5 | 27.4 to 20.4 |
| `b` | 25.6 to 24.4 | 20 | 20.4 |

At these numbers a 32.0 bore takes the step 12.5 of its 25, a 25.0 bore takes
end `b` 10 of its 20, and a 40 hose that opens 5% takes the whole of end `a`,
opened 2.5% at the collar. The preset `plain_40_32` is the same without the
step: the stepped one sawn at the shoulder.

The step's end `b` costs a 32 port airflow: in a 32 port the air still goes
through `b`'s 20.4 bore. A diameter the real fittings do not have moves the seat
a long way: a taper of 1.2 over 25 moves it about 2 mm for each 0.1 of bore, so
measure the fittings before printing for them.

## An adapter between two ends

`apothecary parts adapter dust_port@hose_40 dust_port@port_32` derives the
adapter's parameters from the two ends' interfaces by the nominal rule: a spigot
end straddles the bore it meets by half its taper, a socket end's bore is the
outside it takes, and no clearance is added. It says how each end fits, which
numbers are still a guess, and the `-p` pairs that render it. A measured end goes
over its preset: `-b diameter=31.6 -b measured=true`. The first print settles
the fit; docs/connections.md says what is checked and what only a print shows.
