# Bed shims

A printer's bed made level on its mounts, so a print does not lean on mesh
compensation to follow a tilted plate. The bed is probed heated, twice. The tilt
of the plane through those readings is taken at each levelling screw, and the
least shims that lift the low corners to the highest are printed and fitted
between each mount and the bed. Then the bed is probed again.
[Walkthrough page 52](../walkthrough/52-shims-that-level-a-bed.md) runs it on a
recorded reading.

printer_1's bed stands on four solid mounts, the springs swapped for them. A
shim stacks on a mount and raises its corner by its thickness. The code is
`apothecary/bed_shims.py`, the command `apothecary bed`, the part
[`bed_shims`](../parts/bed_shims/README.md), and in the page four windows of the
printer's Machine ([below](#in-the-page)).

## On the bench

Heating and probing are a person's acts, done at the printer from its Machine.
`apothecary bed` reads what the bench kept and sends nothing to the printer.

1. **Heat and soak.** Bed on, at the temperature the loaded filament prints at,
   then about ten minutes once it gets there. The plate and the probe both move
   while they warm, and the bed is levelled as it prints. Every reading keeps the
   bed's temperature, and one read at `HEATED_C` or above is heated
   (`apothecary bed runs` says which).
2. **Probe twice.** **▤ Probe bed** on the Bed level card, or Control › Level ›
   Probe (⌗748), then again at once. The two differ only by how well the probe
   repeats, and that difference is the floor a shim must clear.
3. **Compute.** `uv run apothecary bed shims --site garage --printer printer_1`
   takes the newest pair of heated probes and their mean. It says each shim,
   what the plane leaves that shims cannot fix, and the command that slices
   them.
4. **Print** them in a filament that holds its shape at the bed's temperature,
   PETG or ASA. A shim sits directly under the heated plate, and PLA softens
   near the temperatures a bed prints PLA at. The filament is the one loaded
   in the printer's Print window ([the slicer](slicer.md)).
5. **Fit.** Over each corner its label names: loosen the knob, lift the corner
   enough to slide the shim onto the mount, slot first, with its tab out past
   the mount, then tighten the knob again.

Before the first print, the bed screw and a mount's outer diameter are measured and
kept, so the shims fit them ([below](#what-a-shim-fits)).
6. **Heat, soak and probe twice again**, then set the two pairs side by side:
   `uv run apothecary bed compare --site garage --printer printer_1 --before A
   --before B --after C --after D`. `bed shims` with `--fitted LABEL=MM` for
   each shim in place says whether another set would do better. That set is
   one to fit in place of these, not on top of them.

## In the page

Four windows of the Machine's group show it for the printer whose Machine is open,
each beside the world and closed until asked for: ⊞ Windows, or the ring's Panels ›
Machine › Bed (`widgets/bed_shims.js`). Everything in them is the server's answer to
`GET /bed/{site}/{printer}`, the same computation as `apothecary bed`.

| Window | What it shows |
|---|---|
| **Runs** | The readings of the printer's pinned board, newest first: each a small heatmap of its grid, the back row on top as the bed lies, blue low and amber high; its bed temperature, marked *heated* or *cold*; its range and its note. A run chosen is drawn over the bed in the world, on the Bed mesh layer. Above them, **▤ Probe hot** (Panels › Machine › Bed › Probe hot): the bed heated to the temperature typed, the Print window's filament's filled in, held the seconds typed (90 unless typed), then homed and probed twice, a reading each noted *heated … C, soaked … s, 1 of 2* and *2 of 2*, and turned off after, however it ends. It is the Machine's own probe (`POST /firmware/printers/level` with `heat_c`, `soak_s` and `times`), so control must be armed and the Machine's Bed level follows it |
| **Differences** | The newest heated pair's second run less its first, the repeatability floor; the newest pair less the pair before it, what was done between them; and what the plane leaves, the bow, set against the bound for a stored mesh. Each a heatmap of the difference, blue below none and amber above |
| **Fixes** | The bed from above, the probed grid dashed, each screw where the profile puts it with its shim, *none* at the highest and *skipped* where a layer or the floor leaves it out; each corner in words. The shims are drawn at their screws in the world, on the Bed mesh layer, as wide as the mount's ring and stretched as the relief is: drawn again with each reading drawn, so both stand at one stretch, the one the Bed mesh layer's note says. Fixes also stands them on `bed_shims`, the piece on the printer's bed, as soon as it has them: its Parameters show their thicknesses and labels, and the piece drawn is them, not the part's defaults. Under them, what each shim fits: the screw hole and the ring, each marked *default* until it is kept. **⇩ Keep from Parameters** (Panels › Machine › Bed › Keep mount) keeps the hole and the ring Parameters holds for `bed_shims` as the printer's (`PUT /bed/{site}/{printer}/mount`). **⚒ Make these** (Panels › Machine › Bed › Make these) stands the shims on `bed_shims` if they are not standing yet and slices the piece as drawn, at the shims' thicknesses and the mount kept, with the part's brim, for the printer in its Print window, where Print a part goes on. It chooses the Print window's levelling *probe first*: the shims are printed on the bed they are to level, so the mesh is on for their print (docs/slicer.md) |
| **History** | Each reading's range, oldest on the left, heated filled and cold hollow, a read of the stored mesh ringed, with the profile's bound drawn as a line |

The newest pair and the pair before it are told by their order: heated probes taken
two at a time, newest first. A probe taken cold, or heated beside a cold one, is in
no pair. Fixes' shims are those of the newest pair as the bed stands in it, shims
already fitted and all: a set to add, where `bed shims --fitted` says a set to fit in
their place.

The garage holds a `bed_shims` piece on printer_1's bed, where shims are printed, as
the router coupon stands on the router's table. Its Parameters are where the bed screw
(`screw`, M3 or M4, a hole typed over it where it needs another) and the mount's outer
diameter are set before Keep, and the tour's Level a bed chooses it at Measure. Its
thicknesses and labels are the ones Fixes stood on it; a ⚒ Make or a Slice of it makes
those.

The tour's **Level a bed** takes the page through it a stage at a time: Heat, Probe,
Compare, Measure, Shims, Print, Fit and After. Heating, probing, measuring and fitting
are the person's: a stage brings forward the window where each is done or seen, and
does none of them ([the tour](tour.md)). [Walkthrough page 53](../walkthrough/53-a-bed-levelled-in-the-page.md)
walks it on a simulated printer.

## What is computed

| | |
|---|---|
| The readings | Their mean, point by point. When none is named, the newest probe and the probe before it when both are heated. A read of the mesh the board stores (`M420 V`) is never chosen unnamed, since it is not known to be the bed |
| The floor | The most the readings differ at any one point of the grid. A single reading has none, and says so |
| The tilt | The least-squares plane through the mean, placed on the bed as the grid lies (below) |
| At each screw | The plane's height where the nozzle stands over the screw. The screws sit outside the probed grid, so the plane is carried past its points, and the result says how far |
| Each shim | The highest corner, its fitted shim taken out, gets none. Each other gets what lifts it to that height, plus the shim it already has. It is rounded to a 0.1 mm layer over a 0.2 mm first layer, and it is none when that is under one layer or under the floor |
| What is left | The plane's residual, which no shim changes, set against the profile's bound for a stored mesh; and the tilt that rounding and the corners left without a shim leave between corners |

A shim stack only raises a corner, so the rule never lowers one: the highest
stays where it is. The part draws only the shims to print, as many as the
corners that get one.

## What a shim fits

A shim goes round its bed screw and bears on its mount, so its hole and its ring are the
machine's. These two figures are measured at the bench:

| | Kept as | With |
|---|---|---|
| The bed screw | `screw`, M3 or M4, which sets the clearance hole, and `hole_d`, a hole typed over it where the screw needs another | the screw, read off the printer or measured across its thread |
| A mount's outer diameter, where it meets the bed | `outer_d`, the ring at least that across | calipers |

Each is kept per machine, in the state folder's `bed/mounts.json` under the machine's
`site/printer`: machine state, never committed, and the same after a restart.
`apothecary bed mount --site S --printer P --screw M3 --outer 11.8` keeps them, and with
no option says what is kept. Until a figure is kept, the part's default stands: a hole
for an M4 and a 12 mm ring, which are not printer_1's measured screw and mount. `bed
shims`, the slice command it prints and the part's own Parameters each say which figures
are defaults. A figure kept goes into every slice of the shims after it.

## Where the screws are

The printer's profile holds them as `measured.bed_screws` in
`parts/<printer>/slicer.json`. Each screw has its name, the label its shim
carries, and where the nozzle stands over it, in the reading's bed coordinates.
Another printer says its own, three screws or five, and gets as many shims.

printer_1's are where `parts/ender3/ender3.scad` draws the bed's mounts, the
frame model's figure, which its `source` says, and are not measured on the
machine. A screw placed a distance off along X moves its shim by that distance
times the tilt along X, and the same along Y. A measured position goes in the
profile in place of the model's, with where it was measured.

## Where the grid lies

Marlin prints a stored mesh without its positions, but its probe says where each
point lies as it probes it, at `G29 V3`, which is how **Probe bed** probes. A
reading so probed keeps where its first and last points lie (its `area`), and the
plane is fitted there and the Bed mesh layer drawn there. A reading without one (a
read of the stored mesh, or a probe kept before the probe said its points) is placed
by a profile's `measured.mesh_area`, the grid's first and last points with their
source, and otherwise by the estimate the viewer draws the Bed mesh layer by: the
volume less what the probe's offset puts out of reach, Marlin's default inset inside
that (`grid_area_estimate`, `meshBounds` in `static/machine_marks.js`). The result
names which it used. The estimate insets the probe's reach as well as the bed's
edge, where Marlin insets only the edge, so it can stand short of the probed grid.
On printer_1's first heated pair the placements Marlin's rules allow move a shim by
up to 0.2 mm.

## What shims cannot fix

What the plane leaves is the plate's own shape, a bow or a twist. A level
bed's reading spans at least that much. When it is over the profile's
`measured.mesh_range_bound`, the `stored-mesh` start piece stays refused however
well the shims are cut ([the slicer](slicer.md)). The bow is then a mesh's to
follow, `probe-each-print`, or the plate's to replace.

## Commands

| | |
|---|---|
| `apothecary bed runs --site S --printer P` | The readings of the printer's pinned board, newest first: bed temperature, heated or cold, range and note |
| `apothecary bed shims --site S --printer P` | The shims, from the newest heated pair, or from `--reading ID` repeated; `--fitted LABEL=MM` for the shims in place; `--json-out` |
| `apothecary bed mount --site S --printer P` | What the shims fit, kept or the part's defaults; `--screw M3` or `M4`, `--hole MM`, `--outer MM` keep it for the printer |
| `apothecary bed compare --site S --printer P --before ID --after ID` | What each corner needs before and after, the range and the residual of each, and how far the mean moved |
| `apothecary slicer slice bed_shims -p thicknesses=... -p 'labels=...'` | The shims sliced for the printer, as `bed shims` prints it |
