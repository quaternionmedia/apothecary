# Shims that level a bed

**Hermetic.** Nothing is heated, probed, printed or sent here. `apothecary.bed_shims`
computes from readings this page writes into a state folder of its own.

A bed that is not level is followed by a mesh, or levelled where it stands. printer_1's
bed stands on four solid mounts, one at each levelling screw, and a shim stacked on a
mount raises that corner. This page takes printer_1's recorded probe and a heated pair
made up from it. It turns them into the least shims that level the bed, says what the
shims cannot fix, and hands the shims to the slicer. Then it sets readings after them
beside readings before. [docs/bed-shims.md](../docs/bed-shims.md) is the reference.

## A recorded probe

printer_1's probe of 2026-09-26, as the bench kept it: a grid of five by five, rows from
the front, each left to right, in mm. Positive is a bed standing higher.

    >>> from datetime import datetime, timezone
    >>> recorded = [
    ...     [-0.065, -0.055, 0.017, 0.148, 0.740],
    ...     [0.151, 0.178, 0.241, 0.381, 0.638],
    ...     [0.166, 0.200, 0.286, 0.416, 0.698],
    ...     [0.006, 0.033, 0.128, 0.260, 0.495],
    ...     [-0.090, -0.082, -0.000, 0.117, 0.343],
    ... ]
    >>> taken = datetime(2026, 9, 26, 21, 8, 23, tzinfo=timezone.utc)

The printer's profile says where its screws are, and the grid is placed where the
viewer's Bed mesh layer places it: Marlin says no positions.

    >>> from apothecary import bed_shims as bs
    >>> from apothecary.slicer.profiles import load_profile
    >>> profile = load_profile("ender3")
    >>> bed = bs.bed_screws(profile)
    >>> [(s.label, s.x, s.y) for s in bed.screws]
    [('FL', 7.5, 7.5), ('FR', 212.5, 7.5), ('BR', 212.5, 212.5), ('BL', 7.5, 212.5)]
    >>> area = bs.grid_area_estimate(profile.measured["build_volume"].value, {"x": -44.0, "y": -10.0})
    >>> area.x0, area.y0, area.x1, area.y1
    (10.0, 10.0, 166.0, 200.0)

The plane through it, taken at each screw. The front right stands highest and gets no
shim. Each other corner needs what lifts it to the front right, and gets that rounded
to a layer unless it is under one. The bed was cold, which the result says:

    >>> once = bs.compute([recorded], bed, area, runs=[bs.Run("20260926T210823.479-dev_ttyUSB1", taken, "probe", 15.04)], bound=bs.range_bound(profile))
    >>> print("\n".join(once.said()))
    reading 20260926T210823.479-dev_ttyUSB1 (probe, 2026-09-26 21:08 UTC, bed 15.04 °C, cold)
    a cold reading: the bed is levelled at the temperature it prints at, so heat it, let it soak, and probe it there
    grid placed by an estimate: the 220 x 220 volume less the probe's offset (X-44 Y-10), 10 mm inside it: x 10..166, y 10..200 mm
    screws from parts/ender3/slicer.json (measured.bed_screws)
    tilt: +0.335 mm per 100 mm along X, -0.070 along Y
    repeatability floor: not known from one reading; probe twice, one after the other
       FL front_left   at (7.5, 7.5): plane +0.012 mm, needs 0.688 -> shim 0.7 mm
       FR front_right  at (212.5, 7.5): plane +0.700 mm, needs 0.000 -> none (the highest)
       BR back_right   at (212.5, 212.5): plane +0.556 mm, needs 0.143 -> none (under one layer)
       BL back_left    at (7.5, 212.5): plane -0.131 mm, needs 0.831 -> shim 0.8 mm
    left by the plane, which shims cannot fix: -0.263..+0.222 mm (a range of 0.486), rms 0.137
    left by rounding to 0.1 mm layers and the corners that get none: up to 0.156 mm between corners
    the furthest screw stands 48.2 mm outside the probed grid, where the plane is carried beyond its points
    the profile's bound for a stored mesh is 0.3 mm (measured.mesh_range_bound): the plane alone leaves 0.486, over it, so no shim brings a reading under it

The last line is the one to read before printing anything. What the plane leaves is the
plate's own bow, and it is wider than the profile's bound for a stored mesh. Shims
take out the tilt, and a mesh still has the bow to follow.

## A heated pair

The bench levels the bed at the temperature it prints at, probed twice one after the
other. No heated probe is kept yet, so this pair is made up: the recorded grid, each
point moved by a probe's noise of about a hundredth. It shows the arithmetic. A heated
bed's own shape is the bench's to find.

    >>> import random
    >>> rng = random.Random(52)
    >>> def probe(grid):
    ...     return [[round(v + rng.gauss(0, 0.01), 3) for v in row] for row in grid]
    >>> one, two = probe(recorded), probe(recorded)

Their mean is levelled, and the most they differ at any point is the floor a shim must
clear:

    >>> pair = bs.compute([one, two], bed, area, bound=bs.range_bound(profile))
    >>> round(pair.floor, 3)
    0.026
    >>> [(s.screw.label, s.printed, s.none) for s in pair.shims]
    [('FL', 0.7, None), ('FR', None, 'the highest'), ('BR', None, 'under one layer'), ('BL', 0.8, None)]

## The part

`parts/bed_shims` draws the shims to print and nothing for a corner that gets none.
Each is a slotted ring that slides onto its mount around the screw. A tab trails
behind it, thicker than the shim and clear of the mount, carrying its label. The
slicer takes them as the part's parameters:

    >>> pair.params()
    {'thicknesses': [0.7, 0.8], 'labels': 'FL BL'}
    >>> from apothecary.projects.parts.bed_shims import DEFAULT as part
    >>> box = part.get_bounds(pair.params())
    >>> round(box.max_point.x, 2), box.max_point.y, box.max_point.z
    (25.54, 34.0, 1.2)
    >>> pair.slice_command()
    "apothecary slicer slice bed_shims -p thicknesses=0.7,0.8 -p 'labels=FL BL'"
    >>> part.print_settings.layer_height
    0.1

## Fitted, and probed again

Once the shims are fitted, the bed is heated, soaked and probed twice again. Here the
plate is taken as rigid, so each shim's lift reaches the grid as the plane through the
lifts at the screws. That makes this after pair up too: the bench's after-probe is
the measurement.

    >>> lift = bs.fit_plane([(s.screw.x, s.screw.y, s.printed or 0.0) for s in pair.shims])
    >>> def lifted(grid):
    ...     return [[v + lift.at(area.x0 + i * 39.0, area.y0 + j * 47.5) for i, v in enumerate(row)] for j, row in enumerate(grid)]
    >>> after = bs.compute([lifted(probe(recorded)), lifted(probe(recorded))], bed, area, fitted={"FL": 0.7, "BL": 0.8})

Most of the tilt is gone, and the range has come down to about the bow, which is the
least a level bed spans. What tilt is left is BR's, which got no shim, and the rounding.
With the shims in place said, the next set takes a layer off FL's rather than lift
the two right corners by less than a layer each:

    >>> f"{pair.plane.a * 100:+.3f} -> {after.plane.a * 100:+.3f} mm per 100 mm along X"
    '+0.336 -> -0.029 mm per 100 mm along X'
    >>> def span(grid):
    ...     flat = [v for row in grid for v in row]
    ...     return round(max(flat) - min(flat), 3)
    >>> span(pair.mesh), span(after.mesh), round(after.bow, 3)
    (0.829, 0.462, 0.48)
    >>> [(s.screw.label, s.printed) for s in after.shims]
    [('FL', 0.6), ('FR', None), ('BR', None), ('BL', 0.8)]

## From the shell

`apothecary bed` does the same from the readings the bench keeps, those of the board
pinned at the printer's node, wherever it is plugged in. A state folder of this page's
own, with printer_1's board pinned, the made-up pair kept as heated probes, and the
after pair:

    >>> import json, os, tempfile
    >>> from pathlib import Path
    >>> before_dir = os.environ.get("APOTHECARY_STATE_DIR")
    >>> state = Path(tempfile.mkdtemp(prefix="walkthrough-52-"))
    >>> os.environ["APOTHECARY_STATE_DIR"] = str(state)
    >>> _ = (state / "firmware-state.json").write_text(json.dumps({"bindings": [{"site": "garage", "path": "printer_1.frame_system.mainboard", "identity": "BOARD52", "bound_at": "2026-11-22T12:00:00Z", "kind": "printer"}]}))
    >>> (state / "leveling").mkdir()
    >>> def keep(rid, minute, grid, note):
    ...     record = {"id": rid, "port": "/dev/ttyUSB1", "board": "BOARD52", "machine": "printer", "method": "probe",
    ...               "at": f"2026-11-22T12:{minute:02d}:00Z", "mesh": grid, "stats": {"range": span(grid)},
    ...               "bed_c": 60.1, "note": note,
    ...               "probe_offset": {"x": -44.0, "y": -10.0, "z": -3.15}}
    ...     _ = (state / "leveling" / f"{rid}.json").write_text(json.dumps(record))
    >>> keep("before-1", 0, one, "heated 60 C, soaked 10 min, 1 of 2")
    >>> keep("before-2", 4, two, "heated 60 C, soaked 10 min, 2 of 2")

    >>> from click.testing import CliRunner
    >>> from apothecary.cli import cli
    >>> def bed(*args):
    ...     print(CliRunner().invoke(cli, ["bed", *args, "--site", "garage", "--printer", "printer_1"]).output.rstrip())
    >>> bed("runs")
    before-2 (probe, 2026-11-22 12:04 UTC, bed 60.1 °C, heated, 'heated 60 C, soaked 10 min, 2 of 2'): 5 x 5, range 0.820 mm
    before-1 (probe, 2026-11-22 12:00 UTC, bed 60.1 °C, heated, 'heated 60 C, soaked 10 min, 1 of 2'): 5 x 5, range 0.842 mm

The newest heated pair is what `bed shims` levels, with no reading named:

    >>> bed("shims")
    reading before-2 (probe, 2026-11-22 12:04 UTC, bed 60.1 °C, heated, 'heated 60 C, soaked 10 min, 2 of 2')
    reading before-1 (probe, 2026-11-22 12:00 UTC, bed 60.1 °C, heated, 'heated 60 C, soaked 10 min, 1 of 2')
    grid placed by an estimate: the 220 x 220 volume less the probe's offset (X-44 Y-10), 10 mm inside it: x 10..166, y 10..200 mm
    screws from parts/ender3/slicer.json (measured.bed_screws)
    tilt: +0.336 mm per 100 mm along X, -0.067 along Y
    repeatability floor: 0.026 mm, the most the readings differ at one point
       FL front_left   at (7.5, 7.5): plane +0.009 mm, needs 0.689 -> shim 0.7 mm
       FR front_right  at (212.5, 7.5): plane +0.698 mm, needs 0.000 -> none (the highest)
       BR back_right   at (212.5, 212.5): plane +0.560 mm, needs 0.138 -> none (under one layer)
       BL back_left    at (7.5, 212.5): plane -0.129 mm, needs 0.827 -> shim 0.8 mm
    left by the plane, which shims cannot fix: -0.266..+0.218 mm (a range of 0.484), rms 0.138
    left by rounding to 0.1 mm layers and the corners that get none: up to 0.150 mm between corners
    the furthest screw stands 48.2 mm outside the probed grid, where the plane is carried beyond its points
    each shim fits a screw hole 4.6 mm (a default), ring 12 mm across (a default): a default stands until the bed screw and the mount's outer diameter, read with calipers, are kept (`apothecary bed mount`)
    the profile's bound for a stored mesh is 0.3 mm (measured.mesh_range_bound): the plane alone leaves 0.484, over it, so no shim brings a reading under it
    <BLANKLINE>
    slice them: uv run apothecary slicer slice bed_shims -p thicknesses=0.7,0.8 -p 'labels=FL BL'
    then: print them, fit each on the mount its label names, heat the bed and let it soak, probe it twice, and compare (apothecary bed compare)

A shim goes round its bed screw and bears on the mount, so its hole and its ring are the
machine's: the screw and the mount's outer diameter, measured at the bench. Until they are
kept, the part's defaults stand, and every answer says they are defaults. `bed mount`
keeps them for the printer, in the state folder, and the slice takes them:

    >>> bed("mount", "--screw", "M3", "--outer", "11.8")  # doctest: +ELLIPSIS
    printer_1's shims fit a screw hole 3.4 mm (M3), ring 11.8 mm across: kept ...
    >>> said = CliRunner().invoke(cli, ["bed", "shims", "--site", "garage", "--printer", "printer_1", "--json-out"]).output
    >>> json.loads(said)["slice"]
    "apothecary slicer slice bed_shims -p thicknesses=0.7,0.8 -p 'labels=FL BL' -p hole_d=3.4 -p outer_d=11.8"

Once the shims are fitted and the bed is probed twice again, `bed compare` sets the two
pairs side by side:

    >>> keep("after-1", 40, after.mesh, "heated 60 C, soaked 10 min, shims FL 0.7 BL 0.8, 1 of 2")
    >>> bed("compare", "--before", "before-1", "--before", "before-2", "--after", "after-1")
    before: before-1; before-2
      range 0.829 mm, the plane leaving 0.484; tilt +0.336 / -0.067 mm per 100 mm along X / Y
    after: after-1
      range 0.462 mm, the plane leaving 0.480; tilt -0.029 / -0.042 mm per 100 mm along X / Y
       FL needed 0.689 mm before, 0.000 after
       FR needed 0.000 mm before, 0.059 after
       BR needed 0.138 mm before, 0.146 after
       BL needed 0.827 mm before, 0.087 after
    after less before: +0.144..+0.777 mm at any point

What the after pair still needs at each corner is under a layer, BR's being about the
shim it never got.

    >>> _ = os.environ.pop("APOTHECARY_STATE_DIR") if before_dir is None else os.environ.update(APOTHECARY_STATE_DIR=before_dir)

Heating the bed, probing it, printing the shims, fitting them and probing again are
the bench's, from the printer's Machine. Nothing on this page did any of them.
