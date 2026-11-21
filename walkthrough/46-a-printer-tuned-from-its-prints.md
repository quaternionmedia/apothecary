# A printer tuned from its prints

**Hermetic.** Nothing is printed, sliced or sent here; `apothecary.print_tuning`
computes and `apothecary.slicer.tuning` keeps what it computed.

A printer's parts come out a little off what was drawn: outer walls standing out,
holes closing in, the first layer spread wider than the walls above it, every size
a share too large. Each is a slicer setting's to take back out. This page prints
nothing: it reads a made-up printer's coupon with made-up calipers, solves the
readings into the printer's errors, takes half of each back out, and reads the next
coupon to see the errors shrink. The printer is the error model itself, its numbers
no machine's. [docs/print-tuning.md](../docs/print-tuning.md) is the reference.

## A piece made to be measured

`parts/print_coupon` is a plate with two blocks on it, a pocket in each, a window
through the plate and a fin, and its wrapper names every size a caliper reads of
it, in the order to read them:

    >>> from apothecary import print_tuning as pt
    >>> from apothecary.projects.parts.print_coupon import DEFAULT as coupon
    >>> plan = coupon.measures()
    >>> [f.name for f in plan.features][:6], len(plan.features)
    (['plate_x', 'plate_y', 'a_x', 'a_y', 'b_x', 'b_y'], 16)

Outside sizes and holes of several nominals along each axis, read at the base and
above it, and three tops: enough that every term of the model is told from every
other, which the design matrix says before anything is printed:

    >>> all(plan.check().values()), sorted(plan.check())
    (True, ['contour', 'first', 'foot', 'hole', 'scale_x', 'scale_y', 'scale_z'])

A cube cannot do that. Its X is a scale and its walls and its first layer all at
once, and its height a scale and the first layer's thickness; the solver names the
terms it cannot tell apart instead of choosing a split:

    >>> cube = [pt.Feature("x", "outside", "x", 10, "base"), pt.Feature("z", "height", "z", 10)]
    >>> found = pt.solve([pt.Reading(cube[0], (10.12,)), pt.Reading(cube[1], (9.98,))])
    >>> print(found.said[0])
    these readings cannot tell scale_z and first apart: scale_z +0.10%, first -0.01 mm together move none of them

## The first turn

A made-up printer: everything 0.3 % large in X and Y, outer walls 0.08 mm out on
each side, holes 0.1 mm in, the first layer 0.12 mm wider than the walls above it
and 0.06 mm thinner than sliced.

    >>> import random
    >>> printer = {"scale_x": 0.003, "scale_y": 0.003, "scale_z": 0.0, "contour": 0.08,
    ...            "hole": 0.1, "foot": 0.12, "first": -0.06}

Each feature read three times with calipers that show hundredths and a hand that
wanders by about one:

    >>> rng = random.Random(46)
    >>> def piece(terms):
    ...     reads = []
    ...     for f in plan.features:
    ...         if f.kind == "wall":
    ...             continue
    ...         true = f.nominal + pt.predicted(f.feature(), terms)
    ...         reads.append(pt.Reading(f.feature(), tuple(round(true + rng.gauss(0, 0.01), 2) for _ in range(3))))
    ...     return reads
    >>> first = pt.solve(piece(printer))
    >>> for name in ("scale_x", "contour", "hole", "foot", "first", "scale_z"):
    ...     t = first.terms[name]
    ...     print(name, round(t.value, 4), "±", round(t.error, 4), "resolved" if t.resolved else "within what the readings resolve")
    scale_x 0.003 ± 0.0002 resolved
    contour 0.0795 ± 0.0032 resolved
    hole 0.1002 ± 0.002 resolved
    foot 0.1199 ± 0.0025 resolved
    first -0.0543 ± 0.0053 resolved
    scale_z -0.001 ± 0.0006 within what the readings resolve

Seven terms from fifteen readings, eight to spare, and the residuals about what
the readings' spread says they should be. The readings came from the model they
were solved by: this shows the arithmetic, not a printer.

    >>> first.rank, first.dof, round(first.chi2, 1)
    (7, 8, 0.6)

## A step, and the next turn

Each term moves one setting by a named relation. The walls are drawn in by what
they stand out, the holes opened by what closes them; a turn takes half of each,
never more than a tenth of a millimetre, and nothing for a term the readings do
not resolve:

    >>> walls = pt.step(first.terms["contour"], pt.RELATIONS["take_out"], 0.0, pt.Limits(-0.5, 0.5, 0.1))
    >>> holes = pt.step(first.terms["hole"], pt.RELATIONS["put_back"], 0.0, pt.Limits(-0.5, 0.5, 0.1))
    >>> foot = pt.step(first.terms["foot"], pt.RELATIONS["put_back"], 0.0, pt.Limits(0.0, 0.5, 0.1))
    >>> round(walls.new, 3), round(holes.new, 3), round(foot.new, 3), walls.why
    (-0.04, 0.05, 0.06, '0.5 of the whole change')
    >>> pt.step(first.terms["scale_z"], pt.RELATIONS["percent"], 100.0, pt.Limits(95, 105, 1)).new is None
    True

The next coupon, printed with those settings, by a printer whose settings move
its errors as the relations say:

    >>> moved = dict(printer, contour=0.08 + walls.new, hole=0.1 - holes.new, foot=0.12 - foot.new)
    >>> second = pt.solve(piece(moved))
    >>> [round(second.terms[n].value, 3) for n in ("contour", "hole", "foot")]
    [0.041, 0.049, 0.06]
    >>> trend = pt.trend("contour", [
    ...     pt.Point("turn-1", first.terms["contour"].value, first.terms["contour"].error, True, walls.expected),
    ...     pt.Point("turn-2", second.terms["contour"].value, second.terms["contour"].error, False)])
    >>> trend.state, trend.said
    ('shrinking', '+0.07949 at turn-1, +0.04104 at turn-2')

Had it turned past none, the next step would take a quarter; had it not moved at
all, the loop would stop and say the setting does not govern that error.

## Kept as a document

On a printer the turns are kept in one document per printer and material,
`print/tuning/1`: each turn's slice, readings, terms, proposals and the changes
applied, every figure saying what it rests on. A slice's record, as OrcaSlicer's
would say it, here made by hand:

    >>> import os, tempfile
    >>> from datetime import datetime, timezone
    >>> from apothecary.slicer import tuning
    >>> from apothecary.slicer.models import Made, Setting, SlicedFor, SliceRecord
    >>> before = os.environ.get("APOTHECARY_STATE_DIR")
    >>> os.environ["APOTHECARY_STATE_DIR"] = tempfile.mkdtemp(prefix="walkthrough-46-")
    >>> used = {"filament profile": "Creality Generic PLA", "process profile": "0.20mm Standard @Creality Ender3",
    ...         "xy_contour_compensation": "0", "xy_hole_compensation": "0", "elefant_foot_compensation": "0",
    ...         "filament_shrink": "100%", "filament_shrinkage_compensation_z": "100%", "z_offset": "0",
    ...         "layer_height": "0.2", "initial_layer_print_height": "0.2"}
    >>> record = SliceRecord(file_id="f1", name="print_coupon.gcode", at=datetime.now(timezone.utc),
    ...     slicer="orcaslicer", made=Made(kind="part", name="print_coupon"),
    ...     printer=SlicedFor(part="ender3", name="printer_1", site="garage", path="printer_1"),
    ...     settings=[Setting(name=k, value=v, origin="printer", source="this page") for k, v in used.items()],
    ...     size=[54.0, 36.0, 12.0], plan=plan)
    >>> doc, turn = tuning.add_turn(record, {r.feature.name: r.values for r in piece(printer)})
    >>> print(tuning.said(turn))
    print_coupon read at 15 features: scale_x +0.254% ± 0.023%, scale_y +0.259% ± 0.027%, scale_z +0.026% ± 0.052%, contour +0.086 mm ± 0.0029, hole +0.099 mm ± 0.002, foot +0.123 mm ± 0.0023, first -0.061 mm ± 0.0036; proposed: xy_contour_compensation +0.000 mm -> -0.043 mm; xy_hole_compensation +0.000 mm -> +0.049 mm; elefant_foot_compensation +0.000 mm -> +0.062 mm; filament_shrink 100% -> 100.128%

A third coupon of the same printer, so other readings: X's scale is read 0.254 % where
0.3 % was planted, two of its standard errors off, as one turn in twenty is. X and Y
agree, so the XY shrinkage takes half of their mean. The first layer's thickness is
said and not applied: printer_1's profile holds
`z_offset` at 0, and a measured first-layer offset is a start piece not yet built.

    >>> turn.proposal("z_offset").why.startswith("said, not applied")
    True
    >>> doc, changes = tuning.apply("garage", "printer_1", doc.applies_to)
    >>> sorted(doc.settings)
    ['elefant_foot_compensation', 'filament_shrink', 'xy_contour_compensation', 'xy_hole_compensation']
    >>> doc.settings["xy_contour_compensation"].source
    'turn-1'

Every later slice for printer_1 with that filament and process takes those four,
each with the turn it came from; `apothecary tuning` does all of this from the
shell, and the **measured** row of the part's Feedback window from the page, where each
turn is filed in the drawer of the piece it read (`apothecary cabinet`).

    >>> _ = os.environ.pop("APOTHECARY_STATE_DIR") if before is None else os.environ.update(APOTHECARY_STATE_DIR=before)
