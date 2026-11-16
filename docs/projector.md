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
above the bed, is lit `d · h / (H − h)` further out. The picture is of intent, drawn on
the bed's plane, never a measurement of what stands on it.

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
    "size": [1920, 1080], "bed_offset": -80.0, "at": "2026-11-16T20:10:00+00:00"
  },
  "starting_points": [[20, 20], [200, 20], [200, 200], [20, 200]],
  "mapping": [[0.0, 0.0, 0.0], [0.0, 0.0, 0.0], [0.0, 0.0, 1.0]],
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
  scales it to its canvas. `null` until calibrated.
- `picture` is what changes only when what is made does. `source` is `job` for the file
  streaming on the machine, `plan` for the file its plan names
  ([a machine planned](firmware.md#a-machine-planned-before-its-board-is-connected)), or `null`. `toolpath.segments` are four numbers each, `x0
  y0 x1 y1` in the bed's millimetres, of the moves that make something seen from above:
  the moves through the air (`left_out`) and the moves straight up or down are not
  drawn. `groups` index them, a layer or a pass each. `cuts`, on a router whose plan
  names a part that says how it is cut, is the stock and each operation as an outline,
  placed at the work zero. `said` is what cannot be drawn and why. `key` names the
  picture: another key, and the page asks again.
- `moving` is what a poll moves: the tool where its poll put it in the frame (`null`
  until one has), where the bed stands, `current` -- the group the streaming job is in
  by the lines it has sent -- and the band. The band's `lines` are the poll's words:
  the state, the job's kind, name and stage, its progress and lines sent, and what the
  machine needs (`todo`, an alarm, a refused line, no filament) -- no figure the poll
  does not carry. `said` is what a poll leaves undrawn.

The page strokes the bed's outline dim, the toolpath dim green with the current group
bright, the cuts amber and the tool a red cross, and writes the band along the canvas's
foot, in its own pixels: the band is not registered to the bed. Black is everything
else.

## Calibrating

C on the page, `?calibrate` in its address, or no calibration kept shows four markers,
each standing for one of four points of the bed -- the calibration's, else the volume's
floor set in 20 mm (`starting_points`) -- labelled with its millimetres. Each is
dragged until its cross lights its point on the bed, and dropped; the four are kept with
the canvas's size (`PUT`), and the grid, a line every 10 mm of the bed with every fifth
brighter, is drawn through what was kept, so how true it lies on the bed shows. A
refusal is written in the band. Escape leaves calibrating.

The pixels kept are the canvas's, with its size; drawn on a canvas of another size they
are scaled to it, across and down apart. That holds while the canvas fills the
projector's output both times, so a calibration is marked with the page full screen on
the projector, and kept true only while the projector, its zoom and its keystone stay
as they were.

## Following the machine

The answer is kept current by the surfaces' one stream
(`GET /surfaces/events?names=projector`). A change of this machine's carries its
picture's key and what moves: what moves is taken as it is, and another key has the
answer asked for again. The server says a change when it learns of one -- a poll of the
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
| `PUT /sites/{s}/machines/{path}/projector` | `{bed, pixels, size}` kept as the calibration; answers as GET does; 422 says why a set fixes no mapping, 409 for a bed that carries Y with no poll kept |
| `DELETE /sites/{s}/machines/{path}/projector` | the calibration forgotten |
| `GET /projector/sites/{s}/machines/{path}` | the page |

The calibrations are kept in the state folder's `projectors.json`, one per machine node
of a site, written whole under one lock.

## What a person looks at

A browser draws the page and a projector lights it; neither runs in the suites. With the
projector aimed at the bed: the grid lying square on the bed's own marks from corner to
corner after a calibration; the outline of a print following the Ender's bed as it moves
along Y, a poll behind; the current layer brightening as a print climbs; a router's cuts
lying where its work zero was set; and what a part's height does to the picture at its
top (`tests/e2e/test_projector_page.py` holds what a browser can: the page, a drag kept,
the stream followed, the ring's cell).
