# The toolpath preview

Where a file's tool goes, in what order, and what each move does, drawn in the world on
its machine before anything is sent: one core for a print and for a cut.
[Walkthrough page 21](../walkthrough/21-a-toolpath-previewed.md) runs it;
[docs/cam.md](cam.md) is what writes a router's file, and [docs/slicer.md](slicer.md) a
printer's.

## The core and its two instantiations

`apothecary/preview` is three modules, and only the last knows a machine exists.

| Module | What it does |
|---|---|
| `moves.py` | The modal interpreter: where the tool is, through absolute and relative moves (`G90`, `G91`), absolute and relative extrusion (`M82`, `M83`), `G92`, inches (`G20`), a motion word carried over, words with no space (`G1X10`) and arcs (`G2`, `G3`, as chords). |
| `core.py` | A file as one shape: every piece of travel in order, its kind, the groups a person scrubs through, and what the moves add up to by kind. The same for every machine. |
| `process.py` | What a move means. A `Process` is a machine's kinds of move, how they group, what a pause's words mean and how fast a rapid goes. |

The instantiations:

| | `ADDITIVE`, on a printer | `SUBTRACTIVE`, on a router |
|---|---|---|
| A move is | `extrude` if it pushes filament, else `travel` | `rapid` (`G0`), `plunge` (a feed straight down), else `cut` |
| Moves group into | layers, by the slicer's marks (`;LAYER_CHANGE`, `;LAYER:n`), else each higher Z that lays material | passes, by the toolpath's own names (`(op i/n pass p/m: ...)`), else each new depth a CAM post's file plunges to |
| A pause's `P` is | milliseconds | seconds |
| A rapid goes at | the file's feed | the machine's rapid |

A new way of making something is one more `Process`, registered by the kind of machine
that works that way (`BY_MACHINE`, which `tests/test_preview.py` holds to
`apothecary/jobs.py`'s kinds). Nothing else changes.

What the file cannot place is not drawn: homing (`G28`, `$H`), a probe (`G38.x`) and a move
in machine coordinates (`G53`) end where the file does not say.

## Who else reads through it

The core is what already said what a file does:

- The slicer's bounds (`slicer.service.gcode_bounds`, on a slice's record) are the core's
  reach of a printer's extruding moves.
- A job names its operation by the same comment grammar, and counts lines the same way:
  `moves.split_comments` is held to `gcode.strip_gcode` on every line of both kinds of file.
- The toolpath's writer counts its lengths and time as it writes; the interpreter reads
  them back from the text and must agree (`tests/test_preview.py`).

## A long file

The page is given `core.MAX_SEGMENTS` segments at most. A longer file has its consecutive
short moves of one kind in one group drawn as one, to within a distance that doubles until
it fits; the preview says the distance. What it adds up to is read before that, so its
lengths, bounds and time are always the file's own.

## The route

`GET /firmware/printers/prints/{file_id}/preview?machine=printer|router` answers a kept
file's preview as that kind of machine would run it: `points` (six per segment),
`kind_of`, `groups`, `bounds`, `length_mm`, `time_s`, `lines`. A kept file does not change,
so the last few are kept. 404 for no such file, 422 for a machine with no process.

## In the page

The Print and Cut card has one slider, `preview`, and the ring's Control › Print or Cut ›
Preview turns it on and off. At the left it is off, and nothing has been asked of the
server. Moved off the left, the chosen file's path is drawn in the world on its machine:
what makes the part in colour, moves through the air dim, through each layer or pass, all
of it at the right. It follows the file chosen, and goes when the Machine closes.

A printer's file is in the bed's coordinates, so it stands at the bed. A router's counts
from its work zero, so it stands where the controller's last poll says that is
(`machine_marks.fileOrigin`), and moves when the zero does: a zero set in the wrong place
shows before the cut does. In `apothecary serve --demo` the router's work zero is seeded at
the coupon's stock, so the coupon's toolpath is drawn on the coupon.

⊞ Windows › Machine, and the ring's Panels › Windows › Machine view, land on it. The
selected machine's Machine is opened when none is, its windows are laid out, the file its
card has chosen is drawn, all of it, and the world is framed on the path; a slider a person
left part way stays there. With no file of that machine's kept, the status line says how
one comes to be: Slice or Toolpath of a part chosen under makes, or Choose File.

The files kept are every machine's. A card chooses the newest that was not made for the
other kind of machine -- a router's toolpath is not a printer's to print -- and the Machine
view draws the other kind's only where a person turned its preview on.

## Not built

- Following a running job along the path: a job's lines sent map to a segment (`Group.sent`
  says where each group starts), and the card does not use it yet.
- A check that the path fits the machine's travel, which waits on the bench: `todo.md`.
- Tool width: a cut is drawn as the tool's centre, a line, not the material it takes.
