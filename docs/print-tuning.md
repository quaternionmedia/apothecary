# Print tuning

A printer's parts come out a little off what was drawn, and some of that is a slicer
setting's to take back out. Print tuning is a loop a person goes round: print a piece
made to be measured, read it with calipers, and apothecary says what the readings
imply for which setting and how sure that is; Take turn takes the change into the
printer's next slices, and the next piece confirms it or does not. Every turn is kept.
Three modules hold it:

| Module | |
|---|---|
| `apothecary/print_tuning.py` | The maths, standard library only: the error model, the least squares and what it cannot separate, a reading's uncertainty, the step, the trend over turns |
| `apothecary/slicer/tuning.py` | `print/tuning/1`, a printer's turns for one filament and process: the settings each term moves, the document and its validator, where it is kept, and what the next slice takes |
| `parts/print_coupon` | The piece made to be measured, its measurement plan in its wrapper |
| `apothecary/print_faults.py` | What a piece shows that calipers do not: the faults a person sees, the settings that govern each, and the one change a look makes |
| `apothecary/slicer/filaments.py` | The filament loaded on a printer, chosen among the slicer's profiles that fit it: what its next slices, and so its tuning, are for |

[Walkthrough page 46](../walkthrough/46-a-printer-tuned-from-its-prints.md) tunes a
made-up printer from its coupon, in doctests; [page 50](../walkthrough/50-a-printer-tuned-from-what-it-shows.md)
from what its pieces show.

## The error model

A feature is one size a caliper reads: across two outer faces (`outside`), across a
hole or a slot (`inside`), a top's height over the bed face (`height`), or a single
wall's thickness (`wall`). Along X or Y a feature is read **at the base**, where the
jaws take in the first layer -- the widest of an outer face, the narrowest of a hole
-- or **above** it, on faces that begin above the first layers. Its error, the mean of
its readings less its nominal, is taken to be a sum of terms:

| Term | Unit | What it is | An outside size `N` | An inside size `N` | A height `H` |
|---|---|---|---|---|---|
| `scale_x`, `scale_y` | share | every size along that axis is off by this share | `+N` | `+N` | |
| `scale_z` | share | every height is off by this share | | | `+H` |
| `contour` | mm | how far each outer face stands out of where it was drawn | `+2` | | |
| `hole` | mm | how far each face of a hole stands into it | | `-2` | |
| `foot` | mm | how far the first layer spreads past the faces above it, each side | `+2` at the base | `-2` at the base | |
| `first` | mm | how much higher every top stands for a first layer printed thicker than sliced | | | `+1` |

An outside and an inside size err in opposite directions for a face's offset and in
the same direction for a scale, and two sizes of one kind tell a scale from an offset
by their difference. The model is linear and its terms independent: what a scale does
to an offset, a product of two small errors, is left out.

**Solving.** Weighted least squares over the terms the readings touch, each reading
weighted by its uncertainty, each column scaled to unit length, by the
eigen-decomposition of the normal matrix (Jacobi's rotations). A direction the
readings cannot see -- an eigenvalue under `1e-9` of the largest -- is a combination of
terms they read the same; the terms in it are **not determined**, are given no value,
and the answer says which they are and, where it is one direction, how they trade
("scale_z +0.10%, first -0.01 mm together move none of them"). A cube's three sizes
determine nothing: its X is a scale, its walls and its first layer all at once. A term
outside every such direction is determined, whatever else is not.

A person may **assume** a term -- hold it at a value they state -- and the rest are
solved round it; the turn records what was assumed, and a solved term's basis says so.
The earlier walls-only correction is the cube with `scale_x`, `scale_y` and `foot`
assumed none: its walls are half the mean of X's and Y's errors.

A `wall` reading is not in the model; see [the flow](#the-flow).

## Measurement quality

A caliper reads to its **resolution** `q`, a step of its display: a reading is
anywhere in a step, a standard uncertainty of `q / sqrt(12)`, and readings of a part
that stays the same round the same way, so repeats do not shrink it. A person's
**repeatability** -- stated, or the spread of repeated readings, whichever is larger
-- does shrink with repeats: `s / sqrt(n)`. A height whose top falls between two of the
slice's layers carries a layer's quantization too, `h / sqrt(12)`. They add in
quadrature. A single reading with no repeatability stated carries the resolution's
alone, which understates it, and the turn says so.

Each determined term's **standard error** is the larger of what the readings'
uncertainties give and what the residuals give: where there are more readings than
terms, the residuals' mean square over their uncertainties (`chi2`) scales the error
when it is over 1. With no reading to spare there is no residual to check the model
against, and that is said. A `chi2` over 4 with two or more to spare is said too,
with the reading furthest off: a feature misread, or an error the model leaves out.

A term within **two standard errors** of zero is within what the readings resolve, and
no change is proposed for it.

A reading further from its nominal than 5 % or 1 mm, whichever is more, is refused: it
is not of this piece's feature, or was read across something else.

## The settings, and where they were read

Which OrcaSlicer settings exist, what they are called and which way they move was
read from the release apothecary pins, 2.4.2, as installed by `apothecary slicer
install`: the keys and the values its bundled profiles write
(`resources/profiles/**/*.json`), and the words its own option list gives each (the
strings of the program itself, `orca-slicer`), not recalled. printer_1's profiles are
Creality's Ender-3 0.4 nozzle machine, its 0.20 mm Standard process and Creality
Generic PLA.

| Term | Setting | Profile | Unit | OrcaSlicer's words | printer_1's chain sets | Relation | Limits | Applied |
|---|---|---|---|---|---|---|---|---|
| `contour` | `xy_contour_compensation` | process | mm | "Contours of objects will expand or contract in the XY plane by the configured value. Positive values make contours bigger" | `0` | take out: `used - term` | -0.5 to 0.5 | yes |
| `hole` | `xy_hole_compensation` | process | mm | "Holes in objects will expand or contract ... Positive values make holes bigger" | `0` | put back: `used + term` | -0.5 to 0.5 | yes |
| `foot` | `elefant_foot_compensation` | process | mm | "Shrinks the first layer on build plate to compensate for elephant foot effect." | `0.1` | put back: `used + term` | 0 to 0.5 | yes |
| `scale_x`, `scale_y` | `filament_shrink` | filament | % | "Enter the shrinkage percentage that the filament will get after cooling (94% if you measure 94mm instead of 100mm). The part will be scaled in XY to compensate." | nothing (OrcaSlicer's own) | percent: `used x (1 + term)` | 95 to 105 | yes, where X and Y agree |
| `scale_z` | `filament_shrinkage_compensation_z` | filament | % | the same, "scaled in Z" | nothing (OrcaSlicer's own) | percent: `used x (1 + term)` | 95 to 105 | yes, where it moves a top half a layer |
| `first` | `z_offset` | machine | mm | "This value will be added (or subtracted) from all the Z coordinates in the output G-code." | `0`, held by printer_1's profile | take out: `used - term` | | **no**: said |

- **The units** are what the bundled profiles write, read across all of them: the two
  compensations and the foot as plain millimetres (`xy_contour_compensation` from
  -0.05 to 0.02, `xy_hole_compensation` from 0 to 0.25, `elefant_foot_compensation`
  from 0 to 1), the two shrinkages as percentages in the filament's lists (`["100%"]`,
  `["99.5%"]`; a few write the number alone), from 98.994 % to 100 % in XY and 99 % to
  100 % in Z. The relation for a percentage is the tooltip's own example: a part 94 mm
  for 100 at 100 % wants 94 %.
- **Taken, not established.** That a compensation moves each edge by its value -- a
  polygon offset, so a size across moves by twice it -- is taken, as the earlier
  correction took it; the tooltips say "by the configured value" and no more. That
  the foot's value is per side is taken alike. That OrcaSlicer fills 100 % where a
  profile leaves a shrinkage out is not taken: a slice records what its G-code's own
  configuration block says it used, and a turn steps from that. Each is a line for
  the bench: a step of known size, and the next turn's term moved by it, or by half or
  twice it, says which.
- **The XY shrinkage is one value.** `scale_x` and `scale_y` are solved apart; where
  they differ by more than they resolve, their difference is an axis's steps per
  millimetre (`M92`), which nothing here changes, and no shrinkage is proposed. Where
  they agree, their weighted mean moves it.
- **A Z scale under a layer** moves no top: a proposed change that moves the tallest
  top under half a layer is not proposed, since the slice would put every top where it
  was.
- **The first layer is said, not applied.** printer_1's profile holds `z_offset` at 0
  because the board applies the probe's offset when `G28` homes Z, and a measured
  first-layer offset is the start piece `first-layer-offset`, a stub
  ([the slicer](slicer.md#what-a-slice-is-composed-from)). `initial_layer_print_height`
  is not the first layer's term: it sets how thick the first layer is sliced, and every
  top above stands on it as sliced; a turn records it, because a height's quantization
  depends on it.
- **The limits are apothecary's**, carried from the earlier decisions until the owner
  sets them: an offset within the 0.5 mm the earlier correction refused past, a
  shrinkage within the 5 % a reading is refused past, the foot never negative (no
  bundled profile sets it below 0, so none grows the first layer). A turn moves a
  setting a fifth of its reach at most: 0.1 mm, or 1 %.

### The flow

A single wall's thickness says how wide the line was that printed it, and so how much
plastic went into it -- but only through the slicer's model of a line's section and
the width it chose for that wall. printer_1's process detects thin walls
(`detect_thin_wall` 1), so how a fin narrower than two lines is printed -- as one line,
and of what width -- is the slicer's choice, which is not established here, and a slice
does not record the width it chose. So the coupon's fin is
read, its error kept and said, and it moves nothing: no flow ratio is proposed. What
would establish it: the fin's printed width read from the kept G-code's own width
comments, and the flow model read from OrcaSlicer's source at the pinned release.

## The step, and when the loop says stop

A turn proposes, for each setting whose term it determines and resolves, half of the
change that would leave none of the term (**damping** 0.5), never more than the
setting's most a turn, never past its limits, and nothing for a setting the slice did
not say it used. Nothing is applied until **Take turn**, which takes the last turn's
proposals into the printer's next slices; **Undo turn** drops the last turn and what it
applied.

Over the turns kept, each setting's term against the turn before, when a change for
it was applied between:

| The term | The loop |
|---|---|
| within two standard errors of none | done: nothing to take out |
| smaller, the same sign | shrinking: the next step as this one |
| turned past none, still resolved | oscillating: the next step takes half the share (down to an eighth) |
| moved less than the readings resolve, though the step meant more | not responding: **stop**, the setting does not govern this error |
| larger, the same sign, past what the readings resolve | growing: **stop**, the relation does not hold for this printer |

A stop proposes nothing for that setting at that turn, and says why; a person decides
what comes next, an undone turn or another piece.

## The document

`print/tuning/1`, one per printer and material: the printer (its site, node and
part), what it applies to (the slicer, the filament profile and the process profile:
a correction learnt with one material or process is not another's), every turn, and
the settings the next slices take. A turn holds the slice it measured (its file, its
part, its parameters, and each tuned setting and layer height as the slice recorded
it), the instrument, every reading with its nominal and its uncertainty, what was
assumed, the terms with their errors and whether each was determined, the solve's
design matrix, rank and residuals, each wall's error, the change proposed for each
setting and why, and the change applied. Every figure says what it rests on:

| Basis | Means | Its source |
|---|---|---|
| `measured` | a reading, a wall, or a value the slice recorded | its turn |
| `solved` | a term from its turn's readings | its turn, which must have a reading the term moves |
| `assumed` | a term held at a value a person stated | its turn |
| `computed` | a proposal, a change applied, a setting held | its turn; a held setting, the turn whose change set it last |

The validator refuses a figure resting on a turn the document lacks, a term solved
from no reading that moves it, a change its turn did not propose, and a held setting
that is not the last change applied. `GET /slicer/tuning/schema` and `apothecary
tuning schema` publish the schema; `POST /slicer/tuning/validate` and `apothecary
tuning validate` read a document back.

It is kept in the state folder where the printer's correction was kept,
`corrections/<site>/<printer>/<filament>--<process>.json`, written whole under a
lock. A correction kept in the older shape, `corrections/<site>/<printer>.json`, is
read once, at the first slice or turn for that printer, into its document for the
printer's one filament and process --
each measurement a turn whose readings are its X, Y and Z, the scales and the foot
assumed none as its rule took them, its change the one it applied -- and the older
file is removed; nothing reads that shape again. A router's correction, beside it,
keeps its own shape ([cam](cam.md#measured-by-hand-fed-back)).

## The piece made to be measured

`parts/print_coupon` ([its README](../parts/print_coupon/README.md)): a 54 × 36 × 2 mm
plate, block A (20 square, its top at 12) and block B (12, its top at 8) standing on
it, a square pocket in each (12 and 6), a square window through the plate (8), and a
0.45 mm fin; labelled A, B, W, F and X in the plate's top. Its wrapper declares the
measurement plan (`measures`): sixteen features in the order to read them, each with
its jaws and the line they close along, its nominal the distance between the faces it
meets, so a plan cannot say one size and draw another -- `apothecary parts verify
print_coupon` finds each on the render. The plan's design matrix determines every
term, any one feature left out; a part that names no plan is read by its box, which
determines nothing.

## Through the slicer and the page

The next slice for a printer whose document holds settings for the filament and
process its profile names takes them, each as a value whose origin is `measured` and
whose source names the turn (`tuning.applied`, which `service.slice_into` calls
before the slicer's values are resolved, where the earlier correction was held). Every
slice records the plan of what it sliced and each tuned setting it used -- from its
profiles, or, where they leave one out, from the configuration block its G-code
carries -- so the turn after it knows what it measured.

| Route | |
|---|---|
| `POST /slicer/slices/{file_id}/measured` | `{readings, resolution, repeatability, assume}`: the piece that slice made, read, kept as the next turn; nothing applied |
| `GET /slicer/tuning?site=&printer=` | The printer's documents, each with its settings' trends |
| `POST /slicer/tuning/apply`, `/undo` | `{site, printer, filament, process}`: Apply, Undo turn |
| `GET /slicer/tuning/schema`, `POST /slicer/tuning/validate` | The schema; a document read back |

In the page it is the part's Feedback window ([cabinet.md](cabinet.md)), opened by a
piece's ring, Part › View › Feedback, and by a print's end on the piece it made. Under the
piece chosen there, **measured** has a row for each feature its slice's plan names (or its
box), each a field for what it reads, repeats a space apart; **Keep** files the reading in
the piece's drawer, keeps the turn and says what it implies; **Take turn** and **Undo turn**
(Part › View › Feedback › Take turn and Undo turn on the ring) act for the printer that made
the piece and the filament and process it used, greyed with the reason the tuning
document gives; and the turns and each setting's trend are listed beneath. *Print a
part*'s last step, Measure, stands there on the footpedal's cabinet, says that a box's
sizes separate nothing and that the coupon is the piece made to be measured, and gives
this page's walkthrough to try. The Print window measures nothing.

## The filament loaded

A printer whose profile names the filament piece `choose` (printer_1's, the owner's
decision of 2026-11-19) slices with the filament loaded on it: chosen in the Print
window's **filament** row, or `POST /slicer/filaments/loaded` `{site, printer,
filament, note}`, among OrcaSlicer's filament profiles of the printer's vendor that
can be chosen and whose `compatible_printers` names its machine (or names none), read
from the installed release (`GET /slicer/filaments?site=&printer=`). The note is a
person's words for the spool. It is kept in the state folder's
`filaments/<site>/<printer>.json` with every filament loaded before it; until one is
loaded the profile's own is taken. A slice's `filament` setting says which, and from
where. Each filament has its own document, so loading another filament takes that
filament's corrections and looks, and loading the first one back takes its own again.

## What a piece shows: looks

A **look** is a piece read by eye: each fault a person sees on it, none (0), slight
(1, seen up close), clear (2, at arm's length) or bad (3, the piece is not usable),
and where it shows. The faults, each with what it looks like and its **levers** --
the OrcaSlicer settings that govern it, in the order they are tried, each with the
step that takes the fault out and its limits -- are `print_faults.FAULTS`
(`GET /slicer/faults`):

| Fault | Levers, in order | When none governs it |
|---|---|---|
| Stringing | `filament_retraction_length` +0.5 mm (the machine's `retraction_length` where the filament says nil); `nozzle_temperature` -5 °C; `travel_speed` +20 mm/s | dry the spool |
| First layer does not hold | `cool_plate_temp_initial_layer` +5 °C; `nozzle_temperature_initial_layer` +5 °C | the Z offset on the printer's screen, a clean bed |
| Corners lift | `cool_plate_temp` +5 °C; `brim_width` +3 mm; `close_fan_the_first_x_layers` +1 | a draught, a cold room |
| Too little plastic | `filament_flow_ratio` +0.02; `nozzle_temperature` +5 °C; `filament_max_volumetric_speed` -2 mm³/s | a clog, the extruder, the e-steps |
| Too much plastic | `filament_flow_ratio` -0.02; `nozzle_temperature` -5 °C | the e-steps, the filament's diameter |
| Overhangs sag | `nozzle_temperature` -5 °C; `slow_down_layer_time` +2 s | the fan and its duct, supports |
| Layers split | `nozzle_temperature` +5 °C; `fan_max_speed` -10 % | a draught, wet filament |
| Ripples beside corners | `outer_wall_speed` -10 mm/s | a loose belt or wheel |
| A layer shifted | `travel_speed` -30 mm/s | a belt, a pulley, a collision: not a slicer's |

The bed's keys are the cool plate's: the Ender 3's profiles name no bed type, and
OrcaSlicer's own is the cool plate (`curr_bed_type = Cool Plate` in the G-code's
configuration). A temperature stays inside the filament's own printable range
(`nozzle_temperature_range_low` .. `_high`) where the slice recorded it.

A look proposes **one** setting's change, for the worst fault it saw (ties in the
table's order), so the next look can say what that change did
(`print_faults.next_step`):

- a fault never stepped: its first lever that can move, one step;
- a fault stepped, read on a piece sliced with that step: less than when it was
  stepped, the same lever again; the same or worse, the lever put back where it was
  and the next one stepped in the same look -- a value already printed with adds no
  second unknown -- and a lever put back is not tried again for that fault;
- a piece sliced before the last look's change was taken: no change at all;
- every lever put back or at its limit: nothing, and what to look at instead is said.

Looks are kept in the same `print/tuning/1` document as the caliper turns, under
`looks`, each with the slice it read and the values that slice used, what was seen
(basis `seen`), the steps proposed and the changes applied; **Take turn** and **Undo
turn** take the newest turn or look. The settings held are each the last change any
turn or look applied, in the order they were kept. A look is read with any piece: a
cube read with calipers proposes nothing, but what it shows does.

| Route | |
|---|---|
| `POST /slicer/slices/{file_id}/seen` | `{seen, where, note}`: the piece that slice made, looked at, kept as the next look; nothing applied |
| `GET /slicer/faults` | The faults, their levers, the severities |
| `GET /slicer/filaments`, `POST /slicer/filaments/loaded` | The filament loaded and the choices; another loaded |

In the page, the Feedback window's **seen** row, under **measured**, has a choice of
none to bad for each fault and **Keep look**, which files the look in the piece's drawer;
Part › View › Feedback › Measure on the ring files the look too, when a fault is chosen
and nothing is read. The history beneath lists turns and looks in the order they were
kept, and each fault seen over the looks. The Print window's **filament** row loads the
filament chosen; a note of the spool is the route's alone.

## The command line

```bash
uv run apothecary tuning plan print_coupon                 # what to read, and what it separates
uv run apothecary tuning turn FILE_ID --read a_x=20.08,20.1 --read a_pocket_x=11.86 --explain
uv run apothecary tuning turn FILE_ID --csv readings.csv   # columns feature, value: a row per reading
uv run apothecary tuning show --site garage --printer printer_1 --explain
uv run apothecary tuning apply --site garage --printer printer_1
uv run apothecary tuning history --site garage --printer printer_1
uv run apothecary tuning undo --site garage --printer printer_1
```

`--assume TERM=VALUE` holds a term; `--resolution` and `--repeatability` state the
instrument. Nothing here opens a port or slices: a turn names a slice already kept.

## What calipers cannot tell

| Read here | Not here |
|---|---|
| A scale per axis, the outer faces' and the holes' offsets, the first layer's spread and its height, each from sizes and tops | Flow, from a wall's thickness: see [the flow](#the-flow) |
| Whether a setting's change took the error out, over turns | Temperature, retraction, cooling, flow: judged by eye, as a look ([above](#what-a-piece-shows-looks)); pressure advance, by nothing here |
| An axis's steps per millimetre, as X and Y disagreeing | Which of steps per millimetre and the material's shrinkage a common scale is |
| | A round hole's polygon facets, a seam's bump, a corner's bulge: the coupon is square to keep them out of its readings |

## At the bench

What only a bench can say, in order:

1. **The first coupon, unchanged.** Slice `print_coupon` for printer_1 with nothing
   applied, print it, read every feature twice or more, and keep the turn. Its terms
   and their errors are the first figures of this printer and filament; if `chi2` is
   over a few, read again before anything is applied.
2. **One step.** Apply, slice the coupon again, print it, read it, keep the turn. Each
   applied term should have moved by about the step: by half or twice it says the
   compensations are not per side, or the foot not per side, and the relation is
   corrected before another step.
3. **The second step, or stop.** A third coupon: shrinking terms go on; a term that
   did not respond says its setting does not govern it on this printer, and is left.

The owner decides which material is tuned first, the limits of each setting, whether a
correction learnt with one material applies to another, and whether the router's tool
allowance joins this document.
