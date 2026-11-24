# The cabinet

A part's cabinet holds a **drawer** for each piece made of it, a print or a cut, and
what is said of that piece afterwards, **filed** in its drawer. It is
`apothecary/cabinet.py`; `/cabinet` reads and files; `apothecary cabinet` reads it from
the shell; the page's **Feedback** window is it.

## A drawer

A drawer is opened when a job begins on a kept file whose slice or cut names a part
(a listener on `apothecary.jobs`), and the job's end says how it ended there. A kept
slice or toolpath no job here ran -- printed from a card, cut before -- gets its drawer
when something is first filed of it. Filed by its file, a piece goes into the newest
drawer of that file; the same file printed again is another piece, in a drawer of its
own. A piece made from a picture is no part's, and has none.

## A print that stopped

A print cancelled or failed says where it stopped: the layer its last line sent was
in, of its file's layers, and that layer's height (`cabinet.stopped_at`, counting lines
as a print sends them and layers by OrcaSlicer's `;LAYER_CHANGE`). It is worked out
from the kept file when the job ends, and for a drawer kept before, when it is read
while its job and file are kept. Its end opens the drawer in Part › Feedback, as a
finished print's does, and the drawer says where it stopped. A fault seen on it and
placed nowhere is filed on that layer. **Probe first**, **Brim** and **Raft** (Part ›
View › Feedback › Try again) each slice the piece again for the printer that made it,
in its Print window, with the levelling or the adhesion chosen there
([docs/slicer.md](slicer.md)); ▶ Print stays a person's. A try the part declares
against is greyed, saying so: Brim on a part that declares no brim (`bed_shims`, whose
slots a brim fills). So is a try the piece was made with already, which would slice it
again as it was: Probe first on a piece that probed first (`bed_shims` declares it), Brim
on one with a 5 mm brim, Raft on one on a raft of 3 layers. Site's Jobs opens a job's
Machine and, where the job made a part's piece, its drawer beside it.

A drawer's **made** row (Part › Feedback) says how the piece was made: its values -- a
variant's, those drawn, or the part's own -- and, for a print, how its start levelled
(probe first, the stored mesh, or home only), its skirt, brim and raft, and what
the board said of its levelling as the print began: levelling on or off, the probe's
offset, the mesh's range and where the probe said the grid lies (`job.levelled`). A
start that probes or turns the stored mesh on has the board say them (`M420 S1 V`,
`M851`); the print keeps its answers from before its first layer
(`devices.levelled_by`). The drawer's answer also carries what the part declares of its
print (`declared`, only what it set). The tries, their tips and the made row say a
levelling and an adhesion in the Print window's words, from one module
(`apothecary/static/first_layer.js`): the row's *probe first: G29 once the bed is hot*
is the made row's too.

| Field | What it holds |
|---|---|
| `id` | The moment it was opened, to the millisecond (`apothecary/stamped.py`) |
| `part` | The part's name |
| `made` | `print` or `cut` |
| `file` | The kept file's name and id, and its sha256 as the job recorded it |
| `variant`, `params`, `draft` | The variant drawn, its parameters, the sha256 of the SCAD draft it was rendered from |
| `stl_sha256` | The sha256 of the STL sliced (every slice record carries it) |
| `machine` | The printer or router: its name, site, node, port, and a printer's part |
| `filament`, `process` | The profiles a print used |
| `slice`, `cut` | The slice's record or the cut's, whole: the piece is measured from its drawer after its file is forgotten |
| `job` | The job that made it: its id, how it ended and why, when; a print cancelled or failed, where it stopped (`stopped`); what its start had the board say of its levelling (`levelled`) |
| `filed` | What was said of the piece, in order |

A **filing** is what calipers read (`measured`), what is seen by eye (`look`), or a note.
A printed piece's reading is its printer's next turn of its tuning
([print-tuning.md](print-tuning.md)) and its look the next look; a cut piece's reading is
its router's tool allowance ([cam.md](cam.md)). Each filing names what it made
(`turn-3`, `look-2`, `tool_allowance`) and, when that was undone, says when. The tuning
and the allowance stay their machine's: the drawer is the part's own account of what was
made of it and what was said of each piece.

A **measured** filing also keeps each dimension read, **checked** against its design
(`checked`): its name, the size it was designed at, the mean of what was read, the
deviation, and the tolerance it was checked with and whose that is. A printed piece the
printer's last turn already reads is read again as a check alone: it is filed, makes no
turn, and says which turn reads the piece; Undo turn, then Keep, reads it into a turn.

Kept in the state folder's `cabinet/<part>/`, a JSON file per drawer (`part/cabinet/1`),
written whole under a lock.

## Dimensions

A piece's **dimensions** are what a person reads of it with calipers, each as designed and
with its newest reading in its drawer (`cabinet.dimensions`): a print's are the features
its slice's plan names, each with the line its jaws close on in the part's own frame
(`part`), or, for a part that names none, the box it sliced, x and y across at the base
and its height (`box`); a cut's are the sizes its toolpath names (`none`: no line). A
reading in a filing that was undone is no dimension's newest. A print's answer also says
the box it sliced (`size`), the way up it prints, which the world compares with the part
as it draws it. Part › Feedback's rows and
the marks the world's Measure layer draws on the part
([viewer.md](viewer.md#measure)) both read them, from the one route.

**The tolerance** a reading is checked with, either way:

| Whose | When |
|---|---|
| `part` | its print settings declare one (`PrintSettings.tolerance`); a slice records it as the setting `tolerance`, declared: what the part's design allows, so what a piece of it must hold |
| `printer` | else, the printer's slicer profile holds one under `measured`, `tolerance`, in mm: what that printer holds, as its bench measured it |
| `default` | else `PrintSettings`' own, 0.2 mm, said as a default; a cut piece's is always the default |

printer_1's profile holds none.

## The routes

| Route | |
|---|---|
| `GET /cabinet` | The parts with a drawer; `?job=` the drawer that job's piece is in |
| `GET /cabinet/{part}` | Its drawers, the newest first, each with its `line` and without its record |
| `GET /cabinet/{part}/variants` | Its drawers by the saved variant each piece was made of (`variants`, by name) and those of none (`unsaved`); each piece says `how` |
| `GET /cabinet/{part}/drawers/{id}` | One drawer whole, with its machine's `tuning` (a printer's, for the filament and process the piece used) or `allowance` (a router's), its `dimensions`, and what its part declares of its print (`declared`) |
| `GET /cabinet/{part}/dimensions` | A piece's dimensions and its tolerance: `?drawer=` that drawer's; `?file=` the newest drawer of that kept file, or the file's as designed where none holds it; else the part's newest drawer, else its newest kept file |
| `POST /cabinet/{part}/drawers` | `{file_id}`: the drawer of a kept slice or cut of the part, opened if need be |
| `POST /cabinet/{part}/drawers/{id}/measured` | `{readings}`: a print's features in mm (repeats as a list), a cut's sizes (null where not measured); each checked against its design; `turn` is null for a check alone |
| `POST /cabinet/{part}/drawers/{id}/seen` | `{seen, where, note}`: a print's faults, 0 none to 3 bad |
| `POST /cabinet/{part}/drawers/{id}/note` | `{note}` |
| `POST /cabinet/{part}/drawers/{id}/tune/apply`, `/tune/undo` | Take turn, Undo turn, for the printer that made the piece |

A filing answers with the drawer whole and what it made said (`said`). What cannot be
filed is a 422 saying why, and nothing is kept. The slicer's
`POST /slicer/slices/{id}/measured` and `/seen` and the cam's
`POST /cam/cuts/{id}/measured` file into the piece's drawer too, and say which.

## In the page

**Feedback** is a window of the Part, beside Parameters, Variants, History and
Readiness (`widgets/feedback.js`). It opens:

- from a part's piece's ring, **Part › View › Feedback**, on that part, whose other cells
  are the window's acts -- Measure, Note, Take turn, Undo turn, and Try again's Probe
  first, Brim and Raft;
- on its own when a print or a cut ends, on the drawer of the piece it made;
- from ⊞ Windows › Feedback, on the selected piece's part.

Its **piece** drop-down holds the part's pieces first -- its drawers, the newest first,
then each kept slice or toolpath of it no drawer holds yet, which says it was not
printed or cut from here, for a piece made from it elsewhere -- then every other part's,
a group each; a piece of another part chosen there shows that part's cabinet, which is how a
part standing in no site is reached. Under the piece chosen: **made**, how it was made;
for a print that stopped, **stopped**, where, and the tries
([above](#a-print-that-stopped)); **measured**, a row for each
of a print's dimensions, its designed size, a field, and its newest reading with how far
it is from the design, within its tolerance or outside it (the tolerance and whose it is
said after the rows), or one field of a cut's sizes, with **Keep** (Enter in a row keeps
too); a dimension clicked on the part in the world, with Measure shown, marks its row and
gives it the caret;
**seen**, each fault none to bad, with **Keep look**; **note**, with **Keep note**; Take
turn and Undo turn; the tuning's history; and what the drawer holds, an undone filing
struck through, a measured filing's checks under it. Machine › Print and Cut print and
cut: they measure nothing.

**Variants**, the part's saved variants, lists what was made of each, folded under its
row, and the pieces made of none in their own fold; a piece chosen there opens its
drawer here. A piece is a saved variant's when it was rendered from that variant's text
-- `saved`, as the variant is now, `earlier`, one of its saves before -- or made with the
values the variant's text sets now (`values`): the part's numbers applied, or an overlay's.
An earlier save counts for a piece whose draft is no variant's text now, and each piece
is sorted by itself, whatever else was made.
One made of none is the part's own text (`own`), an edit never saved (`draft`), numbers
never saved (`values`), or of variants now in the trash (`deleted`). A piece is listed
under each variant it is one of: a duplicate's pieces are its original's.

## The command line

```bash
uv run apothecary cabinet                     # the parts with a drawer
uv run apothecary cabinet footpedal           # its drawers, the newest first
uv run apothecary cabinet footpedal DRAWER    # one drawer: what made it, each filing and its checks
```
