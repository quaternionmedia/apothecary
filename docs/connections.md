# Connections

How one part meets another: the **interfaces** a part declares, the **fit** two
interfaces make, and the **connections** that place parts standing side by side
where their interfaces meet. `parts/dust/` is the worked example: one part for a
round end of a dust system, its sizes its presets, and an adapter whose parameters
are its two ends.
[Walkthrough 43](../walkthrough/43-parts-that-meet.md) runs it.

| Word | What it is | Where |
|---|---|---|
| interface | a named place on a part where another part meets it | `apothecary/models/interfaces.py` |
| fit | what the rule for a pair of interface types says of two | `fit(a, b)` there |
| connection | an interface of one child of a node paired with one of another child | `hierarchy.Connection`, `Assembly.connections` |
| profile | a round part as a stack of sections, giving its solid and its interfaces | `apothecary/fittings.py` |

A connection is not composition. `composition.py` says what a part is built from,
which sets its depth and its shell in the universe; a connection says how two
parts that stand side by side meet, and changes neither.

## An interface

An interface is given in the part's own frame, the one its SCAD draws it in (the
pose it prints in), by a `position` on the part and a `normal`: a unit vector
pointing out of the part, toward whatever meets it. Every interface has:

| Field | |
|---|---|
| `name` | one per part |
| `type` | `spigot`, `socket`, `bolt_hole`, `slot` |
| `version` | the interface's own revision |
| `position`, `normal` | where it is and which way it faces; the normal is kept as a unit vector |
| `source` | where its numbers came from: `stub` (guessed), `measured`, `datasheet`, `standard` (then `cite` names it), `drawn` (the part's own drawing, which apothecary makes it to) |
| `excludes` | interfaces of the same part that cannot be in use with this one |
| `notes` | what a reader needs to know of it: what to measure, say |

A standard's numbers are cited, never copied in as though they were the part's
own: `source: standard` without `cite` is refused.

| Type | Its sizes |
|---|---|
| `spigot` | round, goes in: `d_base` across at `position`, `d_tip` at `position + normal * length`; a taper when the tip is narrower. Past its base the part widens, so it goes in no further than `length`. `reach` is how far the part goes on past `position` along the normal; what lies past the tip leads it in, at most `lead_d` across |
| `socket` | round, takes a spigot: a bore of `diameter` at the mouth (`position`) that holds over `depth`; `floor`, the narrowest opening past the depth (none: nothing stops a spigot there); `stretch`, the fraction the bore opens when pushed (0: rigid) |
| `bolt_hole` | `diameter`; declared and placed, no fit rule yet |
| `slot` | `width`, `length`; declared and placed, no fit rule yet |

## A fit

`fit(a, b)` takes the pair in either order and applies the rule for their pair
of types. A spigot and a socket have one; two spigots or two sockets `do not
mate`; any other pair has `no rule` yet.

A spigot goes into a socket tip first. It touches the bore where its diameter at
the mouth reaches the bore, and goes on, opening a compliant socket, until it is
as wide as the bore opens to, its shoulder reaches the mouth, or a floor past the
socket's depth stops its tip or what leads it.

| Verdict | When |
|---|---|
| `seats` | it touches the bore within the socket's depth, and stops |
| `loose` | it is narrower than the bore all along: nothing touches |
| `will not enter` | its tip, or what leads it, is wider than the bore opens to |
| `shallow` | it would touch the bore only past the depth the bore holds over |
| `tip blocked` | a floor stops it before it touches the bore |

A fit that seats says `seat`, how far the tip goes past the mouth; `gap`, how far
the spigot's shoulder then stands from the mouth; `interference`, how much wider
than the bore the spigot is at the mouth, in mm across; and `stretch`, that as a
fraction of the bore. Each verdict carries its `reason` in words.

A seated spigot points into its socket with its tip `seat` past the mouth: its
position is the socket's plus the socket's normal times its length less the
seat, and its normal is the socket's reversed (`seated_frame`). A round
interface has no clocking: turning it about its normal changes nothing.

## A round part, built with its interfaces

`fittings.Profile` holds a round part as a stack of `Section`s along +Z, section
0 on the bed, each a frustum with its outer diameter and its bore at its bottom
and its top (no bore: solid). From the one stack:

| | |
|---|---|
| `solid()` | each section's outside a cylinder, the bore cut out of the whole, cleared past each open end; cylinders under a difference, which OpenSCAD, JSCAD and the viewer draw with nothing new |
| `spigot(name, first, last, up=)` | the spigot a run of sections makes, pointing up or down, led by what lies past its tip |
| `socket(name, top=)` | the socket the bore makes at a mouth: its diameter there, how far it holds at it, and the narrowest past that |
| `problems(wall, overhang)` | what would not print as it stands: a wall under `WALL` (2.0, five lines of a 0.4 nozzle); an outside leaning out, or a bore closing in, past `OVERHANG` (45 degrees from vertical); a ledge facing down; a flat ceiling over a bore; a facet count that leaves a flat more than `SAGITTA` (0.01 mm) inside the widest circle |

The geometry and the interfaces come from the same numbers, so they cannot
disagree. `hose_adapter`'s `Params` refuses a set whose profile would not print,
with what would not.

## Declaring them

A wrapper overrides `BasePart.interfaces(params)` (default: none); a part built
from a profile returns the profile's. A described part lists them in its
`part.json`, at its defaults:

```json
"interfaces": [
  {"name": "port", "type": "socket", "source": "stub",
   "position": {"x": 0, "y": 0, "z": 30}, "normal": {"x": 0, "y": 0, "z": 1},
   "diameter": 32.0, "depth": 30.0,
   "notes": "Guessed: measure the bore at the mouth and 20 mm in."}
]
```

`part.interface(name)` finds one, and names the part's own when it is not there.
Names are one per part and `excludes` names only the part's own: a sidecar that
breaks either is no part description.

## Held to the render

`apothecary parts verify` reads each round interface across the part's render,
`READ_IN` (0.5 mm) in from each end, square to its normal and about the line
through its position: a spigot's outside at its base and its tip, a socket's bore
at its mouth and its depth (`fittings.readings`, over `meshes.section_radii`). A
diameter more than `--interface-tolerance` (`INTERFACE_TOLERANCE`, 0.05 mm) from
the one declared fails, and so does a part drawn off the axis it declares. It is
the gate for the pair interface ↔ rendered geometry, beside bounds ↔ rendered
geometry. A reading takes the widest and the nearest the cut comes to the axis,
so it is a round part's: anything else the plane cuts at that height reads as
part of the interface.

## Connections in an assembly

A node's `connections` each pair `child.interface` with `child.interface`, two of
its children, each a registered part:

```python
Assembly(
    name="dust_hose_32",
    children=[
        Assembly(name="hose", part_ref="dust_port", params={"diameter": 40.0, "stretch": 5.0, ...}),
        Assembly(name="adapter", part_ref="hose_adapter"),
        Assembly(name="port", part_ref="dust_port", params={"diameter": 32.0, ...}),
    ],
    connections=[
        Connection(a="hose.end", b="adapter.a"),
        Connection(a="adapter.step", b="port.end"),
    ],
)
```

A child's `params` are the parameters its part stands at where they are not its
defaults: the hose's end and the port above are two nodes of one part at two of
its presets. A connection reads each child's interfaces, and `place` its bounds,
at them.

`connections.check(node)` answers each connection's fit, names each interface
whose numbers are a stub's, and names what is wrong: a child or an interface that
is not there, a pair that does not seat, two children standing apart from where
their connection puts them (more than `PLACED_WITHIN`, 0.01 mm, or not facing),
an interface in two connections, and two interfaces of one part that exclude each
other in use together.

`connections.place(node)` returns the node with its connected children placed,
and `check`'s report on it. The first child of each connected group, in the
node's order, stays where it stands, turned as it is. Each child joined to a
placed one by a connection that seats is turned so its interface faces the
other's, by the smallest turn that does (`turn_toward`, as OpenSCAD's `rotate`),
and moved so its interface stands where the fit puts it; its `footprint` is its
part's bounds, where it had none. A connection between two children already
placed closes a loop, and is checked, not solved again. One that does not seat
places nothing.

Two children a connection joins are not checked for overlap with each other in
`Assembly.validate()`: a spigot is in its socket by design.

`apothecary/projects/assemblies/dust_hose.py` builds the example: the hose stays
where it is, its end up; the adapter stands on it, pushed all the way in; the
port is turned over and stands on the adapter's step as far as it goes.

## The adapter between two ends

Two round ends that do not meet are joined by an adapter generated between them
(`apothecary/adapters.py`). An **end** is a round interface of a part at its
parameters: `dust_port@hose_40.end` is the part, the preset its parameters start
from, and the interface, which may be left out where the part has one round
interface. What a person measured goes over the preset: a caliper's reading of
the real end, and `measured` ticked.

`between(x, y)` reads each end's interface and derives the parameters of the one
adapter part, `hose_adapter`, whose parameters are its two ends:

| An end that is | is met by |
|---|---|
| a socket that opens when pushed: a hose | a spigot end of a hose's taper and length (`HOSE`, 2.0 across over 40), with the collar a hose stops against where it is end `a` |
| a rigid socket: a port | a spigot end of a fitting's (`FITTING`, 1.2 across over 25), never longer than twice the depth the bore holds over, so it touches the bore within it |
| a spigot: a tool's outlet stub | a socket end whose bore is that spigot's diameter at its middle, as deep as the spigot is long, a lip of the wall under it to stop it |

The end whose outside is the wider stands on the bed as end `a`, so every
outside narrows going up, and the transition between the ends is as long as its
bore needs to close in at `OVERHANG` (45 degrees), and no shorter than the
adapter's own 8. Nothing is stepped: a step is a hand-made adapter's, for one
that goes into either of two fittings.

**The nominal rule** (`hose_adapter.NOMINAL`): a spigot end straddles the bore it
meets by half its taper either side, so it touches a rigid bore halfway in; a
socket end's bore is the outside it takes, at that spigot's middle. **No
clearance is added.** Nothing here knows how true a printer draws a bore and an
outside, or how a fit feels: those are the first print's to say.

It is refused, with the reason, when:

| Refused | Because |
|---|---|
| an end is a bolt hole or a slot | an adapter is generated between round ends |
| a part with several round interfaces is named alone | which one is meant is a person's to say: `hose_adapter.b` |
| the two ends meet already | `fit` says the one seats in the other: no adapter is needed |
| an end would leave no bore | a spigot into a bore under twice the wall and its taper has no inside |
| it would not print without support | `Profile.problems`: a wall under 2.0, a bore closing in or an outside leaning out past 45 degrees, a ledge facing down |
| the adapter derived does not seat on both ends | the round trip: an adapter is never answered that does not fit the ends it was made from |

Given the adapter's own parameters instead, nothing is derived: those are
checked against the two ends, so an adapter adjusted -- a longer end, a bore
opened by what the first print showed -- is checked again, and says which end no
longer seats.

`Adapter.placed()` stands the two ends and the adapter where their interfaces
meet (`connections.place`), each node at its part's parameters: the end `a` meets
stays where it is, the adapter is pushed on, and the other end is turned over onto
it.

### What is checked, and what only a print shows

| Checked here | Only the real things show |
|---|---|
| each end seats by the rule for a spigot and a socket | how tight it feels, and whether a 1.2 taper holds without a clamp |
| the profile prints without support at a 2.0 wall | whether the printer draws a bore and an outside to size: that is the printer's, measured and fed back to its slices ([slicer.md](slicer.md#a-printers-correction-measured)) |
| the render is the interfaces declared, to 0.05 (`apothecary parts verify`) | a hose's real bore and give, and a port's real bore: measured with calipers, at the mouth and 20 mm in |

So a person measures each end before generating, ticks `measured`, prints the
adapter, and pushes it in. Too tight or too loose, they open or close that end's
`a_d` or `b_d` by what they felt and check it again: with a 1.2 taper over 25,
each 0.1 of diameter moves the seat about 2 mm.

## Asking

| | Command line | HTTP |
|---|---|---|
| a part's interfaces | `apothecary parts interfaces NAME[@PRESET]` (`--json-out`, `-p`) | `GET /parts/{name}/interfaces?preset=` |
| how two fit | `apothecary parts fit PART[@PRESET][.INTERFACE] PART[@PRESET][.INTERFACE]` | `GET /parts/{name}/interfaces/{interface}/fit?to=part[@preset].interface&preset=` |
| on the render | `apothecary parts verify NAME` | |
| the adapter between two ends | `apothecary parts adapter END END` (`-a`, `-b` a number over an end's preset; `-p` the adapter's own; `--json-out`) | `POST /parts/hose_adapter/between` with `{a, b, params?}`, each end `{part, preset?, interface?, params?}` |

`apothecary parts adapter` ends with the `-p` pairs that slice what it derived:
`apothecary slicer slice hose_adapter -p ...` slices that variant for a printer
([slicer.md](slicer.md#slicing)).

In the page, a port's presets are a drop-down in its Parameters, and ⇄ Adapter in
its Selected keeps one end and then makes the adapter between it and the other,
which is drawn and framed in the universe with each end's fit listed and asked
again after each Apply ([viewer.md](viewer.md#presets-and-the-adapter-between-two-ends));
*Join a hose* is that journey in the tour.

`parts fit` with a part named alone tries each of its interfaces against each of
the other's, those that seat first, and exits 1 when nothing seats. `PART@PRESET`
stands a part at one of its presets
([parts-authoring.md](parts-authoring.md#presets)).

## In the problems index

`apothecary problems` lists an interface whose numbers are a stub's as
`unmeasured`, a measurement's to close, and a site's connection that does not
fit or does not stand where it meets as `misfit`, apothecary's to close
(`apothecary/spaces.py`).

## Not yet

The viewer draws no interface and makes no connection: the adapter it makes is
drawn alone, not between its two ends, though `Adapter.placed()` says where each
stands; a site's connections are not placed when it loads; a node's `params` are read by connections and by
nothing that draws, so a viewer draws its part at the part's defaults; and the
types with a rule are the spigot and the socket. A thread, a DIN rail, a VESA pattern or a bolt pattern is
a type with a rule of its own, each citing its standard.
