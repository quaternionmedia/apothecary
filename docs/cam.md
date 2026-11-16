# The toolpath

The router's toolpath is written here, from the cuts a part declares: the
slicer's analogue on the subtractive side. A part cut on the router says,
beside its geometry, the stock it is cut from and the 2.5D operations that make
it; `apothecary/cam` turns them into GRBL's dialect, keeps the file where the
router's Cut card keeps one, records what made it, and measures where the
simulated router's tool went against the design.
[Walkthrough page 20](../walkthrough/20-a-part-through-the-router.md) runs a
part through the whole loop; [docs/cnc.md](cnc.md) is the router itself, and
[docs/plans/subtractive-loop-2026-11-04.md](plans/subtractive-loop-2026-11-04.md)
what is planned around it.

## What a part says

A part's wrapper defines `cuts(params)`, answering `apothecary.cam.models.Cuts`
from its parameters as `Params` reads them:

- **The stock**: a blank of `x` by `y` by `thickness`, its front-left top
  corner the work zero. Every coordinate the toolpath writes counts from that
  corner, X to the right, Y to the back, Z up, so every cut goes to a negative
  Z. That corner is where a person zeroes the router before a cut (the pad's
  Zero, `G10 L20 P1 X0 Y0 Z0`, with the tool touched down there).
- **The tool**: one end mill, its diameter and flutes; the default is a 6 mm
  two-flute.
- **The feeds**: along a cut, straight down, and the spindle's speed, each
  bounded by the router's figures (`grbl.FEED_MAX`, `grbl.SPINDLE_MAX_RPM`),
  so a declaration past them is refused before anything is written.
- **The operations**, in the order they are made: a `Pocket` (a rectangle at
  a corner, a depth), a `Hole` (a centre, a diameter, a depth), an `Outline`
  (a rectangle cut around from outside), a `Disc` (a circle cut around from
  outside: a round part's edge). A depth per pass, a stepover and a safe height
  complete it.
- **Names**, where a person measures it: an operation may carry a `name`, and
  each named one that is cut is a feature of the piece -- inside for a pocket
  or a hole bored, outside for an outline or a disc -- which the toolpath's
  record lists, with its size as designed, as what to measure
  ([below](#measured-by-hand-fed-back)).

The first such part is `parts/router_coupon`: a plate with a pocket and a
column of holes, every size a parameter, standing on the router's table in the
garage where its toolpath cuts it; its pocket, its holes and its plate are
named. `parts/router_emoji` is the piece made for calibrating the router: a 😮,
its face a disc and its eyes and mouth holes bored through it, each a circle
measured across.

## What the toolpath does

`apothecary.cam.toolpath.write` makes one file: a header naming the part,
the tool, the stock and the feeds; `G21 G90 G17 G54`; the tool lifted to the
safe height, the spindle up to speed with a dwell; then each operation in
passes of the depth set, each pass announced on the line before it --
`(op 2/4 pass 1/6: hole 3 mm at 110,36.667 plunged to z -2)` -- so the cut
that streams the file can say which operation it is in; then the spindle off,
the tool up and back over the zero, and `M30`.

- A pocket is cleared in raster lines inset from its walls by the tool's
  radius, then its walls taken in one lap. One narrower than the tool is left
  out, and said.
- A hole wider than the tool is bored in a circle that leaves the hole its
  diameter. One the tool's size, or smaller, is plunged -- and the smaller one
  is said: *bored to the tool*. That is the kind of fact a cut gives back to a
  design, and the change walkthrough 20 makes.
- An outline is cut around from outside, the tool's radius beyond its edge, to
  its depth; one asking for more than the stock's thickness stops a millimetre
  into the spoilboard, and says so. A disc is the same around a circle.
- A circle -- a hole bored, a disc -- is written as chords, 36 of them or as
  many more as keep each within a hundredth of a millimetre of the circle, so
  the piece measures its size across wherever the calipers sit.
- Every offset -- a pocket's inset, a hole's circle, an outline's or a disc's
  distance out -- is the tool's radius as it cuts: its diameter plus the
  router's measured allowance, where one is kept for that tool, which the
  header names on the line after the tool.

Every move is written with its feed, so the controller's bounds and the seam's
(`grbl.check_gcode`, the same check a file a CAM post wrote gets) hold on
every line; the toolpath's bounds, its length along the cuts and its time at
the feeds written are recorded with it. What it leaves out or changes is its
`messages`.

## Kept, recorded, offered

`POST /cam/cut` writes a part's toolpath for a router (`part`, `site` and
`router` as the Cut card names them, or a registry name alone), keeps it as a
cut file -- checked as any streamed file is, listed in the Cut card's files --
and records what made it beside the file (`GET /cam/cuts`, by `file_id`): the
part, the variant drawn when it was one, its parameters, the router, the stock,
the tool, the feeds, each operation with its passes, the lines, the length, the
time, the messages, and the problems the check found.

In the page, a router's Cut card has **Toolpath** where a printer's has Slice,
there once a part is chosen under *makes*: that part gets its toolpath written
for this router, kept and chosen, so ▶ Cut follows; what it holds is said under makes, each
operation with its passes and every message. A part's ring offers Toolpath when
the site has a router, as Slice is offered for a printer; it opens the router's
Machine with the part chosen and writes it there. None of it needs the router's
board: with none connected, the Machine is the router's plan
([docs/firmware.md](firmware.md#a-machine-planned-before-its-board-is-connected)).

## The cut, and as cut

A cut streams the file as a print does (`docs/cnc.md`), and names the operation
it is in: the job's `operation`, shown on the Machine's progress line beside
the percentage. The simulated router keeps every block it ran in work
coordinates, with whether it was a rapid (`SimulatedRouter.trace`);
`apothecary.cam.measure.extent` takes the cutting moves at or below a depth,
widened by the tool's radius, inside a window, and gives their extent -- what a
caliper would find on the piece. The pocket as cut against the pocket as
designed, a hole as bored: that is the measurement the loop closes on.

## Measured by hand, fed back

The piece a router cut is measured by a person with calipers and fed back into
that router's toolpaths (`apothecary/cam/measured.py`), as a printed part is fed
back into its printer's slices ([docs/slicer.md](slicer.md#a-printers-correction-measured)).
The piece made for it is the 😮 of `parts/router_emoji`: its face is an outside
size, its eyes and its mouth inside ones, and a tool that cuts wider than its
diameter -- run out, or bent -- leaves the face small and the holes big by the
same amount.

- **What to measure** is what the toolpath's record names (`features`): for the
  😮, an `eye`, the `mouth` and the `face`, each across, at its size as
  designed. A part that names nothing has nothing to measure.
- **Checked first.** Each size is within 5% of its size as designed, or it is
  not that toolpath's piece -- measured across something else, or cut from
  another file -- and is refused, saying so. Nothing is kept from a refused
  measurement.
- **What is fed back** is the tool's allowance (`tool_allowance`): what every
  offset adds to the tool's diameter. An inside size comes out over by what the
  tool cuts wider than the offsets took, an outside one under by as much. A
  scale the steps per millimetre are off by moves both the same way, in
  proportion to their size, so measured inside and out the two are told apart:
  the tool's share is fed back, taken from the allowance the measured toolpath
  was written with, and the scale's is said and recorded, not applied -- it is
  the controller's `$100` and `$101`, which nothing here changes. Measured on
  one side alone, the error is taken as the tool's. One past half a millimetre
  is refused: that far off is the tool chosen, or the steps per millimetre.
- **The router's own, and its tool's.** It is kept per machine node in the state
  folder (`corrections/<site>/<node>.json`, beside a printer's), with the
  diameter of the tool it was measured with and every measurement that made
  it. Every later toolpath for that router takes it, its record saying the
  allowance, with the origin `measured` and the measurement as its source; one
  with a tool of another diameter takes none, and says so. A toolpath for a
  router standing in no site keeps and takes none.

In the page it is the Cut window's **measured** row, under a chosen toolpath
that names what to measure: the sizes typed in the order its placeholder shows
(`eye × mouth × face mm`, any left out as `-`), then **Keep**, or the router's
control ring's Cut › Measure. The row says what was designed and the allowance
kept; the next Toolpath shows `tool_allowance` with the origin `measured`.
*Cut a part* ends on it, its sixth step.

`POST /cam/cuts/{file_id}/measured` `{"sizes": {name: mm}}` measures the piece a
kept toolpath cut; `GET /cam/corrections?site=&router=` reads what a router
keeps. [Walkthrough page 20](../walkthrough/20-a-part-through-the-router.md#measured-by-hand-fed-back)
cuts the 😮 and feeds it back.

## Previewing it

A kept toolpath is drawn in the world before it is cut: the Cut card's preview slider, on
the core a printer's file is read by too ([docs/toolpath-preview.md](toolpath-preview.md)).
⊞ Windows › Machine, with the router selected or its Machine open, lands on it.

## Not built

- Tabs on an outline, so a cut-out part is held; a climb or conventional
  choice; a second tool; arcs (a circle is written as its segments).
- Three-axis surfacing, or any toolpath from a mesh: a toolpath here comes from
  a part's declared cuts only.
- The real machine: the toolpath has run on the simulated controller alone.
  Section I of [docs/bench-checklist.md](bench-checklist.md) is the bench.
- The scale a measured piece tells: said and recorded, never written to the
  controller's steps per millimetre.
