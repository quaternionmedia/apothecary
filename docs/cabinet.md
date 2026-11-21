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
| `job` | The job that made it: its id, how it ended and why, when |
| `filed` | What was said of the piece, in order |

A **filing** is what calipers read (`measured`), what is seen by eye (`look`), or a note.
A printed piece's reading is its printer's next turn of its tuning
([print-tuning.md](print-tuning.md)) and its look the next look; a cut piece's reading is
its router's tool allowance ([cam.md](cam.md)). Each filing names what it made
(`turn-3`, `look-2`, `tool_allowance`) and, when that was undone, says when. The tuning
and the allowance stay their machine's: the drawer is the part's own account of what was
made of it and what was said of each piece.

Kept in the state folder's `cabinet/<part>/`, a JSON file per drawer (`part/cabinet/1`),
written whole under a lock.

## The routes

| Route | |
|---|---|
| `GET /cabinet` | The parts with a drawer; `?job=` the drawer that job's piece is in |
| `GET /cabinet/{part}` | Its drawers, the newest first, each with its `line` and without its record |
| `GET /cabinet/{part}/variants` | Its drawers by the saved variant each piece was made of (`variants`, by name) and those of none (`unsaved`); each piece says `how` |
| `GET /cabinet/{part}/drawers/{id}` | One drawer whole, with its machine's `tuning` (a printer's, for the filament and process the piece used) or `allowance` (a router's) |
| `POST /cabinet/{part}/drawers` | `{file_id}`: the drawer of a kept slice or cut of the part, opened if need be |
| `POST /cabinet/{part}/drawers/{id}/measured` | `{readings}`: a print's features in mm (repeats as a list), a cut's sizes (null where not measured) |
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
  are the window's acts -- Measure, Note, Take turn, Undo turn;
- on its own when a print or a cut ends, on the drawer of the piece it made;
- from ⊞ Windows › Feedback, on the selected piece's part.

Its **piece** drop-down holds the part's pieces first -- its drawers, the newest first,
then each kept slice or toolpath of it no drawer holds yet -- then every other part's, a
group each; a piece of another part chosen there shows that part's cabinet, which is how a
part standing in no site is reached. Under the piece chosen: **measured**, a row for each
feature a print's plan names (or its box), or one field of a cut's sizes, with **Keep**;
**seen**, each fault none to bad, with **Keep look**; **note**, with **Keep note**; Take
turn and Undo turn; the tuning's history; and what the drawer holds, an undone filing
struck through. Machine › Print and Cut print and cut: they measure nothing.

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
uv run apothecary cabinet footpedal DRAWER    # one drawer: what made it, each filing
```
