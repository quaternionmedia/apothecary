# Parts that meet

**Hermetic.**

A dust hose with a 40 mm bore, and two ports to put it on: one with a 32 mm bore,
one with a 25 mm bore. `parts/dust/` holds an adapter between them, every end of
it pushing in, and stand-ins for the hose and the ports until the real ones are
measured. Each part says where another meets it, its **interfaces**; two
interfaces say whether and where they **fit**; and parts standing side by side
are placed where their interfaces meet by their **connections**.
[docs/connections.md](../docs/connections.md) is the reference.

## Where another part meets it

The adapter is built in Python from one profile, a stack of round sections with
its hose end on the bed, and its interfaces come from the same numbers as its
solid:

    >>> from apothecary.projects.registry import part_named
    >>> from apothecary.projects.parts.skeleton import ROOT
    >>> adapter = part_named("hose_adapter", ROOT)
    >>> for i in adapter.interfaces():
    ...     print(i.name, i.type, i.source, i.d_base, i.d_tip, i.length, i.normal.z, i.excludes)
    hose spigot drawn 41.0 39.0 40.0 -1.0 []
    fitting_32 spigot drawn 32.6 31.4 25.0 1.0 ['fitting_25']
    fitting_25 spigot drawn 25.6 24.4 20.0 1.0 ['fitting_32']

Each is a spigot: round, tapered, going into something. The hose end points
down, out of the face on the bed; the 32 step and the 25 tip point up, and one
of them is in use at a time. The stand-ins are described parts, each a
`part.json` declaring one socket, and every number in them a guess:

    >>> hose = part_named("dust_hose_40", ROOT).interface("end")
    >>> hose.type, hose.diameter, hose.stretch, hose.source
    ('socket', 40.0, 0.05, 'stub')

## Whether two fit

A spigot goes in tip first, touches the bore where it is as wide as it, and goes
on until it is as wide as the bore opens to or its shoulder reaches the mouth.
The hose opens 5% when pushed, so it takes the whole hose end:

    >>> from apothecary.models.interfaces import fit
    >>> f = fit(adapter.interface("hose"), hose)
    >>> f.verdict, f.seat, f.gap, f.stretch
    ('seats', 40.0, 0.0, 0.025)

A rigid 32.0 bore takes the 32 step halfway, where the step is as wide as the
bore; a 25.0 bore takes the 25 tip the same way:

    >>> port_32 = part_named("dust_port_32", ROOT).interface("port")
    >>> port_25 = part_named("dust_port_25", ROOT).interface("port")
    >>> fit(adapter.interface("fitting_32"), port_32).seat
    12.5
    >>> fit(adapter.interface("fitting_25"), port_25).seat
    10.0

The wrong end for a port says why:

    >>> print(fit(adapter.interface("fitting_32"), port_25).reason)
    its tip is 31.4 across and the bore opens to 25

`apothecary parts fit hose_adapter dust_port_32` tries each of the adapter's
interfaces against the port's, those that seat first:

    >>> from click.testing import CliRunner
    >>> from apothecary.cli.main import cli
    >>> print(CliRunner().invoke(cli, ["parts", "fit", "hose_adapter", "dust_port_32"]).output)
    hose_adapter.fitting_32 ↔ dust_port_32.port: seats
        12.5 in, its shoulder 12.5 from the mouth, 0 wider than the bore there (0.0%)
        it goes 12.5 in and stops: its diameter reaches the bore's 32
    hose_adapter.hose ↔ dust_port_32.port: will not enter
        its tip is 39 across and the bore opens to 32
    hose_adapter.fitting_25 ↔ dust_port_32.port: loose
        it is 25.6 across at its widest and the bore is 32: nothing touches
    <BLANKLINE>

## Placed where they meet

The hose, the adapter and the 32 port stand side by side; none is built from
another. Two connections say how they meet, and `place` stands each where its
interfaces meet: the hose stays where it is, its end up; the adapter stands on
it, pushed all the way in; the port is turned over onto the step.

    >>> from apothecary.projects.assemblies.dust_hose import build
    >>> placed, report = build("32")
    >>> for child in placed.children:
    ...     turn = child.turn.to_list() if child.turn else None
    ...     print(child.name, child.position.to_list(), turn)
    hose [0.0, 0.0, 0.0] None
    adapter [0.0, 0.0, 60.0] None
    port [0.0, 0.0, 155.5] [180.0, 0.0, 0.0]
    >>> for line in report.lines():
    ...     print(line)
    hose.end ↔ adapter.hose: seats, 40 in (it goes 40.0 in and stops: its shoulder reaches the mouth)
    adapter.fitting_32 ↔ port.port: seats, 12.5 in (it goes 12.5 in and stops: its diameter reaches the bore's 32)
    stub numbers: hose.end, port.port

The report ends with the interfaces whose numbers are still a stub's: a fit is as
good as the numbers behind it. Using both of the adapter's fitting ends at once is
refused, since one is in use at a time:

    >>> from apothecary.connections import place
    >>> from apothecary.hierarchy import Assembly, Connection
    >>> both = Assembly(
    ...     name="bench",
    ...     children=[
    ...         Assembly(name="adapter", part_ref="hose_adapter"),
    ...         Assembly(name="big", part_ref="dust_port_32"),
    ...         Assembly(name="small", part_ref="dust_port_25"),
    ...     ],
    ...     connections=[
    ...         Connection(a="adapter.fitting_32", b="big.port"),
    ...         Connection(a="adapter.fitting_25", b="small.port"),
    ...     ],
    ... )
    >>> place(both)[1].problems
    ['adapter.fitting_25 and adapter.fitting_32 exclude each other and are both in use']

## Held to the render

The interfaces are declared numbers; `apothecary parts verify hose_adapter` reads
each round one across the rendered STL, near each end and about its declared axis,
and fails on a diameter 0.05 mm off or a part drawn off its axis. That needs
OpenSCAD, so it is not run on this page; `tests/test_dust_parts.py` runs it with
`--slow`.

| Step | Command |
|---|---|
| A part's interfaces | `apothecary parts interfaces hose_adapter` |
| How two fit | `apothecary parts fit hose_adapter.fitting_32 dust_port_32.port` |
| The plain 40 to 32, no tip | `apothecary parts interfaces hose_adapter -p tip=false` |
| Its interfaces on its render | `apothecary parts verify hose_adapter` |
| What is still a stub | `apothecary problems` |
