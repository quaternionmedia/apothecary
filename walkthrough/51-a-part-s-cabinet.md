# A part's cabinet

**Hermetic.** Nothing is printed, sliced or sent here; `apothecary.cabinet` keeps what
was made of a part and what is said of each piece, and `apothecary.slicer.tuning` keeps
what the printer learns from it.

A print is a piece of a part. What it measures, what it shows and what a person says of
it belong to that piece, and so to the part, whichever printer made it and with whatever
filament. The cabinet keeps a drawer for each piece, and files there what is said of it.
In the page it is the Part's Feedback window. [docs/cabinet.md](../docs/cabinet.md) is
the reference.

## A print opens a drawer

A cube sliced for printer_1, as its slice recorded it:

    >>> import os, tempfile
    >>> from datetime import datetime, timezone
    >>> from apothecary import cabinet, jobs
    >>> from apothecary.slicer import tuning
    >>> from apothecary.slicer.models import Made, Setting, SlicedFor, SliceRecord
    >>> before = os.environ.get("APOTHECARY_STATE_DIR")
    >>> os.environ["APOTHECARY_STATE_DIR"] = tempfile.mkdtemp(prefix="walkthrough-51-")
    >>> used = {"filament profile": "Creality Generic PLA", "process profile": "0.20mm Standard @Creality Ender3",
    ...         "retraction_length": "4", "filament_retraction_length": "nil", "nozzle_temperature": "220",
    ...         "nozzle_temperature_range_low": "190", "nozzle_temperature_range_high": "230", "travel_speed": "150"}
    >>> cube = SliceRecord(file_id="c1", name="calibration_cube.gcode", at=datetime(2026, 11, 20, 9, 0, tzinfo=timezone.utc),
    ...     slicer="orcaslicer", made=Made(kind="part", name="calibration_cube", params={"size": 10}),
    ...     printer=SlicedFor(part="ender3", name="printer_1", site="garage", path="printer_1"),
    ...     settings=[Setting(name=k, value=v, origin="printer", source="this page") for k, v in used.items()],
    ...     size=[10.0, 10.0, 10.0], stl_sha256="5" * 64)

Its print begins. The job that runs it opens the piece's drawer, keeping the slice's
record whole, and its end says how it ended:

    >>> def printed(at, outcome="running"):
    ...     started = datetime(2026, 11, 20, at, 0, tzinfo=timezone.utc)
    ...     return jobs.Job(id=jobs.new_id(started, "/dev/ttyUSB0"), kind="print",
    ...         machine=jobs.JobMachine(kind="printer", port="/dev/ttyUSB0"), site="garage",
    ...         input=jobs.JobInput(name=cube.name, file_id=cube.file_id), started_at=started, outcome=outcome)
    >>> drawer = cabinet.for_slice(cube, printed(10))
    >>> drawer.id, drawer.said()
    ('20261120T100000.000', 'print on printer_1 (Creality Generic PLA): running')
    >>> cabinet.job_told(printed(10, "done"))
    >>> cabinet.get("calibration_cube", drawer.id).said()
    'print on printer_1 (Creality Generic PLA): done'

The drawer names what was made and on what, the part's parameters and the hash of the
STL sliced among them, so the piece is known whatever happens to the file it came from:

    >>> drawer.params, drawer.stl_sha256[:8], drawer.machine.path, drawer.process
    ({'size': 10}, '55555555', 'printer_1', '0.20mm Standard @Creality Ender3')

## What is said of the piece is filed in its drawer

It strings between its letters. The look is the printer's next look of its tuning, and
it is filed in the piece's drawer, naming it:

    >>> drawer, doc, look = cabinet.looked(drawer, {"stringing": 2}, {"stringing": "between the X and Y"})
    >>> [(f.id, f.kind, f.made) for f in drawer.filed]
    [('filed-1', 'look', 'look-1')]
    >>> print(drawer.filed[0].said)
    calibration_cube looked at: stringing clear (between the X and Y); proposed: filament_retraction_length 4 mm -> 4.5 mm

A note changes no machine's settings; it is kept with the piece all the same:

    >>> drawer = cabinet.noted(drawer, "the top face is a little rough")
    >>> [(f.id, f.kind, f.said) for f in drawer.filed][-1]
    ('filed-2', 'note', 'the top face is a little rough')

## The same file printed again is another piece

    >>> again = cabinet.for_slice(cube, printed(11))
    >>> [d.id for d in cabinet.drawers("calibration_cube")]
    ['20261120T110000.000', '20261120T100000.000']

## An undone look says so where it was filed

The printer's look undone, the filing that made it says when; it stays in the drawer:

    >>> doc, gone = tuning.undo("garage", "printer_1", doc.applies_to)
    >>> cabinet.undone("calibration_cube", "garage", "printer_1", doc.applies_to, gone.id)
    >>> filed = cabinet.get("calibration_cube", drawer.id).filed
    >>> [(f.id, f.undone is not None) for f in filed]
    [('filed-1', True), ('filed-2', False)]
    >>> cabinet.get("calibration_cube", drawer.id).said()
    'print on printer_1 (Creality Generic PLA): done; 1 filed'

## At the command line

    >>> from click.testing import CliRunner
    >>> from apothecary.cli import cli
    >>> print(CliRunner().invoke(cli, ["cabinet"]).output, end="")
    calibration_cube: 2 drawers
    >>> print(CliRunner().invoke(cli, ["cabinet", "calibration_cube"]).output, end="")
    20261120T110000.000  print on printer_1 (Creality Generic PLA): running
    20261120T100000.000  print on printer_1 (Creality Generic PLA): done; 1 filed

    >>> _ = os.environ.pop("APOTHECARY_STATE_DIR") if before is None else os.environ.update(APOTHECARY_STATE_DIR=before)
