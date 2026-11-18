# The projector

A projector aimed at a machine's bed lights what the machine is about to make, where
it will be made, and what the machine is doing: the light that goes the other way from
a camera's. Its output is a page of its own, for a second display --
`/projector/sites/{site}/machines/{path}` -- black, one canvas and nothing else to
press. Camera › Projector on a machine's ring opens it in a window of its own: on a
printer a board drives, and on a router, planned or driven. A click on the page goes
full screen, which a browser lets a page ask for only on a person's gesture.

## What registers it

Four points of the bed and the four pixels of the output that light them fix one
mapping (`apothecary/homography.py`) from the bed's millimetres to the output's pixels,
and its way back (`apothecary/projector.py`: `bed_to_projector`, `projector_to_bed`).
The bed's millimetres are the machine's working volume as a file counts it -- X and Y
from the volume's low corner, the frame's `volume` standing where its `origin` has it
([A machine's frame](viewer.md#a-machines-frame)) -- on the bed plane, at the frame's
`bed_z`.

The mapping is true on that plane and nowhere else. A point above it -- the top of a
part as it grows, the face of the stock, a clamp, a hand -- is lit where the
projector's ray through it meets the bed plane, displaced away from the point straight
under the lens: a point `h` above the bed, `d` across from the point under a lens `H`
above the bed, is lit `d · h / (H − h)` further out. The picture is of intent, never a
measurement of what stands on it.

### A height: a second plane

With one calibration the picture is drawn on the bed plane, the answer's `plane` says
`bed plane only`, and the band says what stands above the bed is lit displaced. A second
calibration at a known height registers a second plane, and from the two, the plane at
any height between them or a little beyond.

**At the bench.** With the bed calibrated, lay a flat piece of known thickness on it,
covering the four points (or name four others on its top, `bed` in the `PUT` below), and
open the page with `?calibrate&upper=<thickness in mm>`: the four markers start where the
bed plane's were and are dragged, without touching the projector, its zoom or its
keystone, until each cross lights the piece's top over its point. The four are kept with
that height as the calibration's second plane (`PUT .../projector/upper`, below), and the
grid is drawn through the second plane's own mapping. U on the page toggles marking it
(`?upper=` names the thickness; with none named a kept second plane's is used, and with
neither the band says so). Marking the bed plane again forgets the second plane, because
the projector may have moved.

**The relation.** A pinhole projector projects a point `(X, Y, Z, 1)` by a 3 × 4 matrix
`P` with columns `p0 p1 p2 p3`. The plane `Z = z` therefore maps by `[p0 p1 (z·p2 + p3)]`,
a 3 × 3 matrix linear in `z` -- the bed plane `H0 = [p0 p1 p3]`, the second plane at `h`
`Hh = [p0 p1 (h·p2 + p3)]` -- and so the plane at `z` is `(1 − t)·H0 + t·Hh` with
`t = z / h`. Each mapping fixed by four points carries a scale of its own, so `Hh` is first
multiplied by the one number that makes its first two columns, `p0` and `p1`, agree with `H0`'s
as closely as one multiple can (`homography.scaled_like`, least squares); then the blend
(`homography.blend`, `projector.mapping_at`). It is exact for exact points of a pinhole
projector, passes through both marked sets of pixels whatever a hand marked, and past `h` is
the line through the two. `tests/test_projector.py` holds it against a synthetic pinhole
whose pixels are computed from its geometry, apart from the code: exact to a millionth of a
pixel between, at and up to twice `h`, with both planes marked on a bed that carries Y.

**Assumptions, and what is left out.**

- A pinhole: no lens distortion. A real projector's lens bends straight lines, more near
  the edge of its image; the four points of each plane are corrected for none of it, and
  the mapping between them is no better than the pinhole is true.
- Two flat planes: a surface that is not flat is lit displaced as before; what is drawn is a
  plane's worth of the picture, at one height.
- The projector, its zoom and its keystone stood still between the two markings. A projector
  that moved a little is not told apart from a hand's marking error: the only check
  (`AGREE`) is for a gross mismatch -- points marked in another order, or of another plane.
- A thin piece shifts the picture little: the shift of a plane `h` above the bed against the
  bed plane is `d · h / (H − h)` as above, and a piece whose shift is below a hand's marking
  (a pixel or two) fixes no height worth drawing for. A thicker piece does; what a bench
  measures is below.

**Refused**, with the reason in the answer (`PUT .../upper` answers 422; `GET ...?height=`
answers 422; a page's own height falls back to the bed plane and says why):

- a second plane within `MIN_SPAN_MM` (1 mm) of the bed plane -- the two are one plane to a
  hand's marking -- or past `MAX_SPAN_MM` (500 mm), or a height not finite;
- four points or pixels that fix no mapping, or pixels off the output (a second plane's
  pixels are scaled to the bed plane's output from the canvas they were marked on);
- pixels marked exactly where the bed plane's were: a plane above the bed lights the same
  points elsewhere, and nothing of its height is told;
- a second plane that does not agree with the bed plane's by `AGREE` (50 %) of its first two
  columns;
- a height below the bed, any height above it with no second plane, a height past
  `REACH` (2) times the second plane's -- beyond that the line through the two planes is not
  trusted, and an error in marking the second plane is carried `z / h` times over at height
  `z` (between the planes less than once, at `2h` twice) -- and a plane whose picture would
  turn inside out: at that height a point of the bed, or of the volume's floor, reaches the
  projector's lens plane.

**What height the picture is drawn for** (`plane`, and the band says it): the height of what is
drawn, where the plan or the stream says it, and nothing else is guessed:

- a router's **stock's top**: the work zero's height above the bed as its controller reports
  it (`work_origin.z`; the work zero stands at the stock's top, `apothecary/cam/models.py`).
  The cuts, the toolpath and the tool are lit as if on that plane: a cut's own depth below
  the stock's top is not corrected for, so a deep cut is lit as displaced as its depth;
- a printer's **layer** the streaming job is in, at the layer's own Z in the file (the group
  the lines sent put the job in, as `moving.current` has it), not the nozzle's, which a lift
  during a travel moves; the toolpath and the tool are lit for it;
- otherwise, and always while one calibration is kept, the **bed plane**. The bed's outline,
  the grid and a printer's footprint lie on the bed plane and are always drawn through it.

Nothing is guessed for a height the calibration does not fix: a work zero or a layer past the
reach is drawn on the bed plane, and the band says which height was refused, and why.

A set of four is refused, saying why, when it fixes no mapping: three points of either
four on one line (naming them), a pixel off the output, a number that is not finite, or
not four of each.

### A bed that carries Y

The Ender's bed and the AnoleX's table carry Y: the bed moves under a tool that stands
still along it (the frame's `bed_moves_y`). A projector stands still in the room, so a
point of the bed lies at `(x, y + offset)` of the frame, `offset` being how far the bed
stands along Y from where the frame's `origin` has it (`bed_moves_y` less the work's Y
under the tool, as `frames.js`'s `bedOffsetAt` says). The four points are kept with the
offset the bed stood at as they were marked, which is its last poll's; with no poll kept,
a calibration is refused (409).

What rides the bed -- its outline, the toolpath, the cuts -- is drawn where the last
poll says the bed stands, and moves when the next poll says it has moved: every two
seconds while the page follows the machine, so between two polls the picture is behind
the bed by however far it travelled since the first. With no poll kept, nothing on the
bed is drawn, and the band says so. The tool's mark stands still over a bed that carries
Y, at `bed_moves_y`.

### A router's work zero

A router's file counts from its work zero, which its controller reports (`work_origin`,
from its machine position and the way each axis homes). Until a poll has said it, the
toolpath and the cuts are not placed, and the answer says so: no place is guessed.

## What is drawn

The page draws the server's one answer, `GET /sites/{site}/machines/{path}/projector`,
which it reads through the surfaces (`GET /surfaces/projector?site=&path=`,
[Surfaces](surfaces.md)): the page holds no logic of its own of what to draw, only how
to stroke it.

```json
{
  "format": "apothecary.projected/1",
  "site": "garage", "path": "printer_1", "kind": "printer", "port": "/dev/ttyUSB0",
  "made_at": "2026-11-16T20:15:00+00:00",
  "frame": {"volume": [220.0, 220.0, 250.0], "bed_moves_y": 0.0, "...": "api.machine_frame's record"},
  "calibration": {
    "format": "apothecary.projector/1", "site": "garage", "path": "printer_1",
    "bed": [[20, 20], [200, 20], [200, 200], [20, 200]],
    "pixels": [[400, 900], [1500, 880], [1400, 200], [500, 220]],
    "size": [1920, 1080], "bed_offset": -80.0, "at": "2026-11-16T20:10:00+00:00",
    "upper": {
      "bed": [[20, 20], [200, 20], [200, 200], [20, 200]],
      "pixels": [[395, 880], [1505, 862], [1410, 190], [498, 211]],
      "height": 20.0, "bed_offset": -80.0, "at": "2026-11-16T20:12:00+00:00"
    }
  },
  "starting_points": [[20, 20], [200, 20], [200, 200], [20, 200]],
  "mapping": [[0.0, 0.0, 0.0], [0.0, 0.0, 0.0], [0.0, 0.0, 1.0]],
  "upper_mapping": [[0.0, 0.0, 0.0], [0.0, 0.0, 0.0], [0.0, 0.0, 1.0]],
  "plane": {
    "z": 0.4, "for": "layer 1", "wanted": {"z": 0.4, "for": "layer 1"},
    "heights": [0.0, 20.0], "how": "between the two calibrated planes",
    "mapping": [[0.0, 0.0, 0.0], [0.0, 0.0, 0.0], [0.0, 0.0, 1.0]],
    "line": "drawn for layer 1, 0.4 mm above the bed (between the two calibrated planes; planes calibrated at 0 and 20 mm)",
    "said": []
  },
  "size": [1920, 1080],
  "picture": {
    "key": "3f9c0a1b2c3d4e5f",
    "bed": {"outline": [[0, 0], [220, 0], [220, 220], [0, 220]], "carries_y": true},
    "source": "job",
    "file": {"id": "20261116T201000.000-square", "name": "square.gcode"},
    "toolpath": {
      "process": "additive", "word": "layer", "origin": {"x": 0, "y": 0, "z": 0},
      "segments": [10, 10, 60, 10, 60, 10, 60, 40],
      "groups": [{"label": "layer 1", "first": 0, "count": 2}],
      "within_mm": 0.0, "left_out": ["travel"]
    },
    "footprint": {
      "points": [[10, 10], [60, 10], [60, 40], [10, 40], [10, 10]],
      "source": "toolpath", "part": null, "size": null
    },
    "cuts": null,
    "said": [],
    "calibrated_at": "2026-11-16T20:10:00+00:00"
  },
  "moving": {
    "tool": [60.0, 0.0],
    "bed_offset": -40.0,
    "current": 0,
    "status": {
      "state": "printing", "polled_at": "2026-11-16T20:15:00+00:00",
      "job": {"kind": "print", "name": "square.gcode", "stage": "printing", "progress": 0.64, "sent": 7, "total": 11},
      "needs": [],
      "lines": ["printing", "print · square.gcode · printing", "64% · line 7 of 11"]
    },
    "said": []
  }
}
```

- `mapping` takes a point of the frame on the bed plane -- a point of the bed plus
  `(0, moving.bed_offset)` -- to a pixel of an output `size` wide and high; the page
  scales it to its canvas. `null` until calibrated. `upper_mapping` is the same for the
  second plane, from the four points marked on it, `null` with none.
- `plane` is the plane the picture is drawn for ([A height](#a-height-a-second-plane)): `z`
  its height above the bed, `for` what stands there (`the bed plane`, `layer 1`, `the
  stock's top`, `the height asked`), `wanted` the height of what is drawn when it is not the
  bed's (`null` for none), `heights` the calibrated planes' (`[]` until calibrated, `[0]` with
  one, `[0, h]` with two), `how` (`bed plane only`, `measured at the bed plane`, `measured at
  the second plane`, `between the two calibrated planes`, `beyond the second plane:
  extrapolated, weaker`, or `bed plane: the height is refused`), `mapping` the mapping true at
  `z` (the bed plane's when one calibration is kept), `line` the band's sentence naming it, and
  `said` what that leaves out. It moves with a poll (a layer climbs), so a change of the
  stream carries it with `moving`, once the machine is calibrated.
- `picture` is what changes only when what is made does. `source` is `job` for the file
  streaming on the machine, `plan` for the file its plan names
  ([a machine planned](firmware.md#a-machine-planned-before-its-board-is-connected)), or `null`. `toolpath.segments` are four numbers each, `x0
  y0 x1 y1` in the bed's millimetres, of the moves that make something seen from above:
  the moves through the air (`left_out`) and the moves straight up or down are not
  drawn. `groups` index them, a layer or a pass each. `cuts`, on a router whose plan
  names a part that says how it is cut, is the stock and each operation as an outline,
  placed at the work zero. `said` is what cannot be drawn and why. `footprint`, on a
  printer, is where the part stands on the bed, a closed outline: with a file drawn, the
  convex outline of its first layer's lines (`source` `toolpath`, a part's concave edge
  not followed -- the lines themselves are drawn inside it); before one is sliced, the plan's
  part's **planned footprint** (`source` `plan`, `part` its name, `size` its X and Y in mm):
  its declared bounds at its defaults (`BasePart.get_bounds`, the way up it prints), a
  rectangle centred on the bed, where OrcaSlicer's arrange (`--arrange 1`, not turned,
  `--orient 0`) puts one part, and the band says it is planned, not sliced. `null` for a
  router (its `cuts` are its shapes) and for a plan naming no part. The plan's part is
  a piece of the site by path (the part it was made from) or a part by name; a part that
  declares no bounds or does not load is said, and nothing is drawn. The planned rectangle
  is a bounding box at the part's defaults, and its centring is the slicer's as documented,
  not measured here: a variant the slice uses, a rotated or offset arrangement, or a
  part wider than the bed show only when the file exists. `key` names the
  picture: another key, and the page asks again.
- `moving` is what a poll moves: the tool where its poll put it in the frame (`null`
  until one has), where the bed stands, `current` -- the group the streaming job is in
  by the lines it has sent -- and the band. The band's `lines` are the poll's words:
  the state, the job's kind, name and stage, its progress and lines sent, and what the
  machine needs (`todo`, an alarm, a refused line, no filament) -- no figure the poll
  does not carry. `said` is what a poll leaves undrawn.

The page strokes the bed's outline dim, a printer's footprint in a blue of its own (on the
bed plane, where the part stands), the toolpath dim green with the current group
bright, the cuts amber and the tool a red cross, and writes the band along the canvas's
foot, in its own pixels: the band is not registered to the bed. The bed's outline lies
through `mapping`; the toolpath, the cuts and the tool, through `plane.mapping`. The band's
line `plane.line` names the plane the picture is drawn for. Black is everything
else.

## Calibrating

C on the page, `?calibrate` in its address, or no calibration kept shows four markers,
each standing for one of four points of the bed -- the calibration's, else the volume's
floor set in 20 mm (`starting_points`) -- labelled with its millimetres. Each is
dragged until its cross lights its point on the bed, and dropped; the four are kept with
the canvas's size (`PUT`), and the grid, a line every 10 mm of the bed with every fifth
brighter, is drawn through what was kept, so how true it lies on the bed shows. A
refusal is written in the band. Escape leaves calibrating. The second plane is marked the same way, the markers standing
for the same four points on the top of a piece of known thickness
([A height](#a-height-a-second-plane)).

The pixels kept are the canvas's, with its size; drawn on a canvas of another size they
are scaled to it, across and down apart. That holds while the canvas fills the
projector's output both times, so a calibration is marked with the page full screen on
the projector, and kept true only while the projector, its zoom and its keystone stay
as they were.

## Following the machine

The answer is kept current by the surfaces' one stream
(`GET /surfaces/events?names=projector`). A change of this machine's carries its
picture's key and what moves (and, once calibrated, `plane`, which a layer climbing moves):
what moves is taken as it is, and another key has the answer asked for again. The server says a change when it learns of one -- a poll of the
machine's board, whoever made it, a job of it begun or ended, a calibration kept or
forgotten -- and polls nothing for the page.

The page follows the machine as the world follows one it draws: a board pinned under
the machine is watched by `boards.js`, polled every two seconds only while the server
holds its link, never opening a port. Those polls are the ones the stream then relays,
when nothing else polls the machine.

## The routes

| Route | |
|---|---|
| `GET /sites/{s}/machines/{path}/projector` | the answer; 404 for no such node, 400 for one with no working volume |
| `GET /sites/{s}/machines/{path}/projector?height=z` | the answer with `plane` at `z` mm above the bed; 422 for a height the calibration does not fix |
| `PUT /sites/{s}/machines/{path}/projector` | `{bed, pixels, size}` kept as the calibration, the second plane forgotten; answers as GET does; 422 says why a set fixes no mapping, 409 for a bed that carries Y with no poll kept |
| `PUT /sites/{s}/machines/{path}/projector/upper` | `{pixels, size, height, bed?}` kept as the calibration's second plane; 422 says why it fixes none, 409 for no calibration of the bed plane or a bed that carries Y with no poll kept |
| `DELETE /sites/{s}/machines/{path}/projector/upper` | the second plane forgotten, the bed plane's calibration kept |
| `DELETE /sites/{s}/machines/{path}/projector` | the calibration forgotten, its second plane with it |
| `GET /projector/sites/{s}/machines/{path}` | the page |

The calibrations are kept in the state folder's `projectors.json`, one per machine node
of a site, written whole under one lock.

## What a person looks at

A browser draws the page and a projector lights it; neither runs in the suites. With the
projector aimed at the bed: the grid lying square on the bed's own marks from corner to
corner after a calibration; the outline of a print following the Ender's bed as it moves
along Y, a poll behind; the current layer brightening as a print climbs; a router's cuts
lying where its work zero was set; a printer's planned footprint lying where the slice then
puts the part's first layer; and what a part's height does to the picture at its top
(`tests/e2e/test_projector_page.py` holds what a browser can: the page, a drag kept, a second
plane kept and named in the band, the footprint drawn, the stream followed, the ring's cell).

**The height, with a ruler and a block.** Neither a browser nor a suite has met a projector, and
the maths guarantees only what its assumption gives: exact for a pinhole, with no lens distortion,
a flat plane and a projector that stood still between the markings. No accuracy figure for a real
one is stated here. At the bench: calibrate the bed plane and a block's top, say 20 mm thick; set
the block's top at a height between (a second block, or the same one on a spacer) and a ruler's
line on it, ask `?height=` for that plane (`GET ...?height=z`) and see how far the line lies from
where the picture draws it. Do it again at the second plane's own height (the marked points
themselves), beyond it up to twice (where the error of marking the second plane is carried
two times over), and with the block off to one side of the lens and the other, because a lens
that bends the picture shows at the image's edge first. Measure the lens distortion before
trusting the picture past the centre; nothing here corrects it.
