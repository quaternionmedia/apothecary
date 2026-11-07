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
  (a rectangle cut around from outside). A depth per pass, a stepover and a
  safe height complete it.

The first such part is `parts/router_coupon`: a plate with a pocket and a
column of holes, every size a parameter, standing on the router's table in the
garage where its toolpath cuts it.

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
  into the spoilboard, and says so.

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

In the page, a router's Cut card has **Toolpath** where a printer's has Slice:
what is chosen under *makes* gets its toolpath written for this router, kept
and chosen, so ▶ Cut follows; what it holds is said under makes, each
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
