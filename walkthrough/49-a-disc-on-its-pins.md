# A disc on its pins

**Hermetic.** Nothing here runs OpenSCAD; the part's mirror,
`apothecary.gap_geometry` and `apothecary.motion` compute.

The rolling rotor of [page 44](44-a-gap-that-travels.md) turns back by
`eccentricity / rotor radius` of a turn each orbit, but only while its track
does not slip, which nothing in that part enforces. `cycloidal_disc` gives the
disc lobes and the stator pins: one lobe fewer than pins, so each turn of the
crank turns the disc back one pin's pitch, and a disc turned any other way
would stand in a pin. [docs/airgap.md](../docs/airgap.md#the-cycloidal-disc)
is the reference.

## The flank, and why every pin touches it

    >>> from apothecary.projects.parts import cycloidal_disc as cd
    >>> p = cd.Params()
    >>> p.pins, p.lobes, p.pin_circle, p.eccentricity, p.pin, p.clearance
    (11, 10, 30.0, 1.0, 5.0, 0.1)

At a crank of 90 degrees the disc's centre stands the eccentricity up the y
axis and the disc has turned back 90 / 10 degrees:

    >>> at = cd.pose(p, 90)
    >>> round(at.x, 6), round(at.y, 6), round(at.turn, 6)
    (0.0, 1.0, -9.0)

Seen from the disc, every pin's centre runs on one curve,
`(R cos s - E cos N s, R sin s - E sin N s)`. The first pin, at `(30, 0)`, is
on it at `s = 90 / 10` degrees:

    >>> pin = cd.pin_centres(p)[0]
    >>> [round(v, 9) for v in at.local(pin)] == [round(v, 9) for v in cd.pin_path(p, 9)]
    True

The flank is that curve moved in along its normal by the pin's radius and the
clearance, so each pin stands the clearance from it. Measured from the
outlines at every 10 degrees of crank, all eleven pins, it is 0.1 within how
far the drawn polygon stands from its curve:

    >>> gaps = [m.gap for a in cd.cranks(10) for m in cd.pin_marks(p, a)]
    >>> len(gaps), round(min(gaps), 4), round(max(gaps), 4), round(cd.profile_sagitta(p), 4)
    (407, 0.0986, 0.1011, 0.0014)

## The ratio is the teeth's

Ten turns of the crank turn the disc once, the other way:

    >>> cd.turn(p, 360), cd.turn(p, 3600)
    (-36.0, -360.0)

The pins hold it there. At a crank of 37 degrees the disc can turn a little
over half a degree either way about its own centre before it meets a pin --
its backlash as drawn, from the clearance -- and the middle of that is the
pose's turn:

    >>> back, on = cd.free_turn(p, 37)
    >>> round(back, 2), round(on, 2), round((back + on) / 2, 3)
    (-0.57, 0.58, 0.001)

Turned back a pin's pitch of eleven at a whole turn of the crank, as a roll
over eleven would, it stands nearly half a millimetre into a pin; turned back
one of ten, it stands its clearance off:

    >>> from apothecary.gap_geometry import Pose
    >>> round(cd.least_gap(p, placed=Pose(p.eccentricity, 0, -360 / p.pins)), 3)
    -0.453
    >>> round(cd.least_gap(p, placed=Pose(p.eccentricity, 0, -360 / p.lobes)), 3)
    0.099

## Where the contact goes

The pitch circles, `E N` about the axis and `E (N - 1)` about the disc's centre,
roll on each other. A fixed pin's contact with the flank does not: it stays on
the pin, sweeping back and forth across its face, and goes a lobe round the
disc each turn of the crank, nearly five times as far along the flank as
across the pin -- it slides:

    >>> cd.pitch_travel(p).kind
    'rolling'
    >>> one = cd.pin_travel(p)
    >>> one.kind, round(one.travel_inner, 1), round(one.path_outer, 1), round(one.path_inner, 1)
    ('standing', 36.0, 3.8, 17.9)

What that sliding costs, how the flanks wear on fixed pins, and whether a
printed disc runs or binds, are a bench's.

## The motion the viewer plays

The part declares its motion: the crank, the stator still, the disc and the
output's pins moving. The server samples the part's own pose function into
the table the viewer plays, each pin's gap measured at each sample:

    >>> from apothecary.motion import table
    >>> made = table(cd.DEFAULT.motion(p.model_dump()), p.model_dump())
    >>> made["format"], made["param"], made["range"], len(made["samples"])
    ('motion/1', 'crank', [0.0, 360.0], 181)
    >>> [(x["piece"], x["drawn"], x["per_cycle"]) for x in made["pieces"]]
    [('disc', True, -36.0), ('output', False, -36.0)]
    >>> [(g["name"], len(g["marks"][0])) for g in made["gaps"]]
    [('pins', 11)]
    >>> made["interpolation"]["error_mm"] < 0.001
    True

The output's pins are bought, not printed: the piece is not drawn, it only
carries them. So are the dowels and the crank's bearing:

    >>> [(b.name, b.count, b.diameter) for b in cd.DEFAULT.bought()]
    [('pin', 11, 5.0), ('bearing', 1, 22.0), ('output pin', 6, 4.0)]

## Recipes

| | |
|---|---|
| Render the two pieces | `apothecary parts generate-stl cycloidal_disc` |
| Print the pins with the floor | `apothecary parts generate-stl cycloidal_disc -p printed_pins=true` |
| Its motion, as the viewer gets it | `GET /parts/cycloidal_disc/motion` |
| Play it | `/viewer/parts/cycloidal_disc`, the part's ring, Part › View › Motion › Play |
