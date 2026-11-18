# Parts that meet

**Hermetic.**

A dust hose with a 40 mm bore, and two ports to put it on: one with a 32 mm bore,
one with a 25 mm bore. `parts/dust/` holds one part for a round end of a dust
system, whose parameters say which end it is, and an adapter whose parameters are
its two ends. Each part says where another meets it, its **interfaces**; two
interfaces say whether and where they **fit**; and parts standing side by side
are placed where their interfaces meet by their **connections**.
[docs/connections.md](../docs/connections.md) is the reference.

## One part for every end

A hose's end and a port are one part, `dust_port`, at two sets of its parameters.
The sizes met here are its presets, every number in them a guess:

    >>> from apothecary.projects.registry import part_named
    >>> from apothecary.projects.parts.skeleton import ROOT
    >>> port = part_named("dust_port", ROOT)
    >>> for name, preset in port.presets.items():
    ...     print(name, "--", preset.description)
    hose_40 -- a smooth 40 mm bore dust hose, rubber or PVC: 100 mm of it, opening 5% when pushed
    port_32 -- a rigid port with a 32 mm bore, a tool's or a collector's
    port_25 -- a rigid port with a 25 mm bore
    outlet_35 -- a tool's outlet stub, 35 mm across, that a hose's cuff goes over

Its one interface, `end`, is what its parameters say: at `hose_40` a socket that
opens 5% when pushed, its numbers a stub's until `measured` is ticked:

    >>> hose = port.interface("end", port.preset("hose_40"))
    >>> hose.type, hose.diameter, hose.stretch, hose.source
    ('socket', 40.0, 0.05, 'stub')

A port measured with calipers is the preset with the reading over it:

    >>> measured = port.interface("end", {**port.preset("port_32"), "diameter": 31.6, "measured": True})
    >>> measured.diameter, measured.source
    (31.6, 'measured')

## Where another part meets the adapter

The adapter is built in Python from one profile, a stack of round sections with
its end `a` on the bed, and its interfaces come from the same numbers as its
solid. At its defaults it is the stepped adapter: a 40 hose onto a 32 or a 25
port:

    >>> adapter = part_named("hose_adapter", ROOT)
    >>> for i in adapter.interfaces():
    ...     print(i.name, i.type, i.source, i.d_base, i.d_tip, i.length, i.normal.z, i.excludes)
    a spigot drawn 41.0 39.0 40.0 -1.0 []
    step spigot drawn 32.6 31.4 25.0 1.0 ['b']
    b spigot drawn 25.6 24.4 20.0 1.0 ['step']

Each is a spigot: round, tapered, going into something. End `a` points down, out
of the face on the bed; the step and end `b` point up, and one of them is in use
at a time.

## Whether two fit

A spigot goes in tip first, touches the bore where it is as wide as it, and goes
on until it is as wide as the bore opens to or its shoulder reaches the mouth.
The hose opens 5% when pushed, so it takes the whole of end `a`:

    >>> from apothecary.models.interfaces import fit
    >>> f = fit(adapter.interface("a"), hose)
    >>> f.verdict, f.seat, f.gap, f.stretch
    ('seats', 40.0, 0.0, 0.025)

A rigid 32.0 bore takes the step halfway, where the step is as wide as the bore;
a 25.0 bore takes end `b` the same way:

    >>> port_32 = port.interface("end", port.preset("port_32"))
    >>> port_25 = port.interface("end", port.preset("port_25"))
    >>> fit(adapter.interface("step"), port_32).seat
    12.5
    >>> fit(adapter.interface("b"), port_25).seat
    10.0

The wrong end for a port says why:

    >>> print(fit(adapter.interface("step"), port_25).reason)
    its tip is 31.4 across and the bore opens to 25

`apothecary parts fit hose_adapter dust_port@port_32` tries each of the adapter's
interfaces against the port's at that preset, those that seat first:

    >>> from click.testing import CliRunner
    >>> from apothecary.cli.main import cli
    >>> print(CliRunner().invoke(cli, ["parts", "fit", "hose_adapter", "dust_port@port_32"]).output)
    hose_adapter.step ↔ dust_port@port_32.end: seats
        12.5 in, its shoulder 12.5 from the mouth, 0 wider than the bore there (0.0%)
        it goes 12.5 in and stops: its diameter reaches the bore's 32
    hose_adapter.a ↔ dust_port@port_32.end: will not enter
        its tip is 39 across and the bore opens to 32
    hose_adapter.b ↔ dust_port@port_32.end: loose
        it is 25.6 across at its widest and the bore is 32: nothing touches
    <BLANKLINE>

## Placed where they meet

The hose, the adapter and the 32 port stand side by side; none is built from
another. The hose and the port are two nodes of the one port part, each at its
preset's parameters. Two connections say how they meet, and `place` stands each
where its interfaces meet: the hose stays where it is, its end up; the adapter
stands on it, pushed all the way in; the port is turned over onto the step.

    >>> from apothecary.projects.assemblies.dust_hose import build
    >>> placed, report = build("32")
    >>> for child in placed.children:
    ...     turn = child.turn.to_list() if child.turn else None
    ...     print(child.name, child.part_ref, child.position.to_list(), turn)
    hose dust_port [0.0, 0.0, 0.0] None
    adapter hose_adapter [0.0, 0.0, 60.0] None
    port dust_port [0.0, 0.0, 155.5] [180.0, 0.0, 0.0]
    >>> for line in report.lines():
    ...     print(line)
    hose.end ↔ adapter.a: seats, 40 in (it goes 40.0 in and stops: its shoulder reaches the mouth)
    adapter.step ↔ port.end: seats, 12.5 in (it goes 12.5 in and stops: its diameter reaches the bore's 32)
    stub numbers: hose.end, port.end

The report ends with the interfaces whose numbers are still a stub's: a fit is as
good as the numbers behind it. Using the step and end `b` at once is refused,
since one is in use at a time:

    >>> from apothecary.connections import place
    >>> from apothecary.hierarchy import Assembly, Connection
    >>> both = Assembly(
    ...     name="bench",
    ...     children=[
    ...         Assembly(name="adapter", part_ref="hose_adapter"),
    ...         Assembly(name="big", part_ref="dust_port", params=port.preset("port_32")),
    ...         Assembly(name="small", part_ref="dust_port", params=port.preset("port_25")),
    ...     ],
    ...     connections=[
    ...         Connection(a="adapter.step", b="big.end"),
    ...         Connection(a="adapter.b", b="small.end"),
    ...     ],
    ... )
    >>> place(both)[1].problems
    ['adapter.b and adapter.step exclude each other and are both in use']

## Held to the render

The interfaces are declared numbers; `apothecary parts verify hose_adapter` reads
each round one across the rendered STL, near each end and about its declared axis,
and fails on a diameter 0.05 mm off or a part drawn off its axis. That needs
OpenSCAD, so it is not run on this page; `tests/test_dust_parts.py` runs it with
`--slow`, the port at each of its presets.

| Step | Command |
|---|---|
| A part's interfaces | `apothecary parts interfaces hose_adapter` |
| A port at a preset | `apothecary parts interfaces dust_port@hose_40` |
| How two fit | `apothecary parts fit hose_adapter.step dust_port@port_32.end` |
| The plain 40 to 32, no step | `apothecary parts interfaces hose_adapter -p step=false -p b_d=32` |
| Its interfaces on its render | `apothecary parts verify hose_adapter` |
| What is still a stub | `apothecary problems` |
