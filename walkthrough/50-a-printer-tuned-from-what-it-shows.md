# A printer tuned from what its prints show

**Hermetic.** Nothing is printed, sliced or sent here; `apothecary.print_faults`
decides and `apothecary.slicer.tuning` keeps what it decided.

Calipers say how big a piece came out; they do not say it strung, that its corners
lifted or its layers split. Those a person sees. This page reads made-up pieces by
eye, keeps each look in the printer's tuning, and follows the one setting each look
changes. [docs/print-tuning.md](../docs/print-tuning.md) is the reference.

## The faults, and their levers

Each fault says what it looks like and the settings that govern it, in the order
they are tried, each with the step that takes the fault out:

    >>> from apothecary import print_faults as pf
    >>> [f.id for f in pf.FAULTS]
    ['stringing', 'first_layer', 'warping', 'under_extrusion', 'over_extrusion', 'overhangs', 'weak_layers', 'ringing', 'layer_shift']
    >>> [(lv.key, lv.step, lv.unit) for lv in pf.fault("stringing").levers]
    [('filament_retraction_length', 0.5, 'mm'), ('nozzle_temperature', -5.0, '°C'), ('travel_speed', 20.0, 'mm/s')]
    >>> pf.fault("layer_shift").otherwise.endswith("a slicer cannot take a shift out")
    True

## A first look

A cube printed with Creality Generic PLA, as its slice recorded it:

    >>> import os, tempfile
    >>> from datetime import datetime, timezone
    >>> from apothecary.slicer import tuning
    >>> from apothecary.slicer.models import Made, Setting, SlicedFor, SliceRecord
    >>> before = os.environ.get("APOTHECARY_STATE_DIR")
    >>> os.environ["APOTHECARY_STATE_DIR"] = tempfile.mkdtemp(prefix="walkthrough-50-")
    >>> used = {"filament profile": "Creality Generic PLA", "process profile": "0.20mm Standard @Creality Ender3",
    ...         "retraction_length": "4", "filament_retraction_length": "nil", "nozzle_temperature": "220",
    ...         "nozzle_temperature_range_low": "190", "nozzle_temperature_range_high": "230", "travel_speed": "150"}
    >>> def sliced(file_id, **over):
    ...     values = {**used, **over}
    ...     return SliceRecord(file_id=file_id, name="calibration_cube.gcode", at=datetime.now(timezone.utc),
    ...         slicer="orcaslicer", made=Made(kind="part", name="calibration_cube"),
    ...         printer=SlicedFor(part="ender3", name="printer_1", site="garage", path="printer_1"),
    ...         settings=[Setting(name=k, value=v, origin="printer", source="this page") for k, v in values.items()],
    ...         size=[10.0, 10.0, 10.0])

It strings between its letters, clearly; nothing else:

    >>> doc, look = tuning.add_look(sliced("c1"), {"stringing": 2, "warping": 0}, {"stringing": "between the X and Y"})
    >>> print(tuning.said_look(look))
    calibration_cube looked at: stringing clear (between the X and Y); proposed: filament_retraction_length 4 mm -> 4.5 mm

The filament's retraction says nil, so the machine's 4 mm stands; the look draws
back half a millimetre more. Apply takes it into the printer's next slices:

    >>> doc, changes = tuning.apply("garage", "printer_1", doc.applies_to)
    >>> [(c.setting, c.before, c.after) for c in changes]
    [('filament_retraction_length', 4.0, 4.5)]

## A piece sliced before the change says nothing of it

The same G-code printed again is not a piece of the change:

    >>> doc, look = tuning.add_look(sliced("c1-again"), {"stringing": 2})
    >>> look.proposed, look.said
    ([], ['this piece was sliced with filament_retraction_length 4 mm, not 4.5 mm as look-1 set it: print one sliced since, to see what that change did'])
    >>> doc, _ = tuning.undo("garage", "printer_1", doc.applies_to)

## The next piece

Sliced since, it strings no less: the retraction does not govern it on this printer.
It is put back, and the next lever stepped in the same look -- going back to a value
already printed with adds no second unknown:

    >>> doc, look = tuning.add_look(sliced("c2", filament_retraction_length="4.5"), {"stringing": 2})
    >>> for step in look.proposed:
    ...     print(step.setting, step.used, "->", step.new, *(["(put back)"] if step.back else []))
    filament_retraction_length 4.5 -> 4.0 (put back)
    nozzle_temperature 220.0 -> 215.0

Applied, and the third piece strings only slightly: the temperature governs it, and
the same lever goes on:

    >>> doc, _ = tuning.apply("garage", "printer_1", doc.applies_to)
    >>> doc, look = tuning.add_look(sliced("c3", filament_retraction_length="4", nozzle_temperature="215"), {"stringing": 1})
    >>> print(tuning.said_look(look))
    calibration_cube looked at: stringing slight; proposed: nozzle_temperature 215 °C -> 210 °C; stringing: clear -> slight after nozzle_temperature 220 °C -> 215 °C: it governs it
    >>> tuning.fault_trends(doc)["stringing"]
    'clear at look-1 (then filament_retraction_length 4.5); clear at look-2 (then filament_retraction_length 4, nozzle_temperature 215); slight at look-3'

A temperature never leaves the filament's own range: at 190 °C, the bottom of PLA's,
the next look steps the travel instead. Every look sits in the same document as the
caliper turns, `print/tuning/1`, one per printer, filament and process; loading
another filament (the Print window's filament row, `POST /slicer/filaments/loaded`)
starts that filament's own.

    >>> _ = os.environ.pop("APOTHECARY_STATE_DIR") if before is None else os.environ.update(APOTHECARY_STATE_DIR=before)
