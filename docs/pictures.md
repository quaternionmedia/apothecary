# Pictures, cameras and pieces

A picture becomes named, placed pieces you can build: it is pinned at a place
in a site as a **view**, a finder finds the flat shapes in it, and a shape is
made into a **piece** standing where it was seen. A **camera** is a part of the
site that takes the picture. [Walkthrough 03](../walkthrough/03-a-picture-to-a-print.md)
goes round the loop from a camera's picture to a print, and
[walkthrough 01](../walkthrough/01-photographs-into-pieces.md) takes photographs
into pieces; the ring's cells named here are [the viewer's](viewer.md#the-ring).

## Where pictures live

Pictures are read from one folder, the picture root: `APOTHECARY_PICTURE_ROOT`,
or else the folder `apothecary serve` was started in. It is never the whole
machine, a home folder or anything above one, or the state folder: a server
started anywhere else refuses to read pictures, saying why. Nothing outside it
is listed or read by the server.

The browser fills two folders under it: a camera's frames are kept in
`captures/`, and the pictures a person adds from the browser in `uploads/`.
Each is checked to be a picture by its first bytes, not its name. Those are the
*kept* pictures: a page may forget them. The folder's own pictures are never
deleted from a page.

The Pictures tab, below Site and Selected, lists every picture under the root, the folder's
and the kept ones, newest first. A row chosen there is what the ring's
Picture › Folder pins.

## Cameras

A camera is a root structure of a site, `camera_1`, `camera_2` and so on,
drawn as the library's webcam (`parts/cameras/webcam`) standing where it is put
(`apothecary/vision/cameras.py`).

- **Camera › Add here**, on a host's ring, stands one above the host, looking
  straight down, and selects it; added where one already stands, it stands a
  step beside it, clear of it, the next few filling the place's top in rows; with
  no room left over it, it stands outside, and the line says it is not one of the
  place's cameras. A camera can also be dropped from the library.
- **Device** on the camera's ring chooses which of this browser's cameras it
  is; **Allow** asks the browser once. One device is one camera: choosing it
  for one takes it off any other. A device is one browser's, as a board is one
  machine's.
- **Its lens** starts at a typical webcam's field of view. The first width a
  person types for one of its pictures teaches it the real one, and its other
  pictures no person sized follow.
- **Its aim**: the turn ring and the tilt arc in the world, or Part › Edit for
  its numbers. Reset stands an added camera back where it was added; only
  Remove (chosen twice) takes it away.
- **Live** shows its video in the world, and **Still** stops it; its pyramid
  is drawn while it is selected or live.

A camera's record -- its pose, its lens, its device by the id and label the
browser gave it -- is kept in the state folder, the person's alone. Nothing
about the device goes into the site.

## Views

**Take picture** -- on the camera's ring, in Selected, or `P` with a camera
selected -- keeps a frame and pins it as a view where the camera looks: the
first upward-facing surface its centre ray meets, a host's top or the floor. A
picture of a wall or the sky lands nowhere: it is kept, and nothing is made
from it.

A view is a picture lying on a *place*: a host -- a root structure with a
footprint that is neither a made piece nor a camera -- or the site's floor
(the canvas ring's Pictures › Floor). A view is data attached to the place,
not a node of the tree, so SCAD, STL, validation and jobs never see it.

On a host's ring, **Picture** holds:

| Cell | Does |
|---|---|
| Add | Pins a picture from disk |
| Folder | Pins one already under the picture root: the newest, each a cell, and the one chosen in Pictures |
| Views | Each view at this place, drawn |
| Find shapes | Runs a finder on the view drawn; the other finders are offered where one can read the picture |
| Make | Stands a shape up as a piece; Make all makes every shape found that is not made yet |
| Size | Puts the cursor in Selected's width box: how wide the picture is, or one shape's side |
| Unpin | Takes the view off its place; the picture stays |
| Forget | Forgets a kept picture (chosen twice) |

Pinning finds nothing: Find shapes is a step of its own, and its finder is one of
[the finders](#finders). A view a camera took
keeps where the camera stood and how it was aimed at that moment, so moving
the camera after does not move it, and its picture lands through a pinhole. A
view no camera took is flat on its place, a width across. Pinned at a
structure, it is laid where the widest picture of its shape fits clear of what
rests on the structure's top -- on the garage's bench, between printer_1 and the
boards -- and stays there; made pieces and cameras are not counted, so a second
picture of a place lies where the first did. An unsized view has no mapping,
and nothing is made from it; it is drawn as wide as fits there. A picture
dropped on a structure, or pasted, is pinned there; on empty canvas, at the
floor.

A picture is drawn seen through at half, and hatched: an overlay on what it was
taken of, not a part. Once it has a width, a shape whose footprint lies over
something resting on the structure is flagged: its area filled in warning red,
and the place's badge, Find shapes and Size name what it lies over. Make still
makes it, and the layout check then names the piece.

## Finders

A finder reads a picture and reports flat shapes, each with its family, where it is
as fractions of the picture, how sure the finder is and which finder it was. Find
shapes is one press where one finder can read the picture, and a cell for each
where several can: `stated` where a description lies beside it, `outline` where it
holds a drawing, a closed stroke at least; `apothecary photo find --finder` takes one by name.

| Finder | Reads | For |
|---|---|---|
| `plain` | Light split from dark once for the picture, touching dark pixels gathered into blobs, a blob's family from how much of its tightest box it fills | A thing lying on a plain surface, or a shape filled in |
| `outline` | Strokes darker than the whiteboard near them; each closed stroke lying on the whiteboard is the shape of what it encloses, as wide as the stroke's middle | A drawing in marker on a whiteboard ([walkthrough 28](../walkthrough/28-a-whiteboard-to-a-model.md)) |
| `stated` | A description a person wrote beside the picture, `name.shapes.json` | A picture whose shapes somebody knows |

To `outline` the whiteboard is the ground, whatever runs round the picture's edge,
and never a shape. A shadow or a glare across it moves no stroke, and a smear is not
one. It reads the shapes of [a diagram's marks](#a-whiteboards-marks) alone: a
stroke left open, a dimension line, an arrow and writing are not shapes; a mark
filled in is the shape it covers; a stroke inside a shape is left out. A gap
in a stroke a few pixels of the working picture wide is closed, a wider one leaves
the stroke open. `apothecary photo check --finder` measures a finder on drawn
pictures whose answers are known, filled in and in outline.

## A whiteboard's marks

Before a whiteboard's strokes are read as shapes they are gathered into marks and
sorted (`apothecary/vision/marks.py`). A mark is the strokes that belong together:
a closed stroke, a line, or small strokes in a row, which is how writing lies.

| Kind | Is | Becomes |
|---|---|---|
| `diagram` | A closed stroke the size of a shape, a mark filled in, a long straight line | A shape, where it closes or is filled |
| `writing` | Small strokes in a row, or one stroke of letters run together | Nothing yet; it is never a shape |
| `unsure` | What the sorter cannot place: a small closed stroke alone, a large open one | Nothing, until a person says |
| `nothing` | A person's word alone: a smear, a magnet, a reflection | Nothing |

Each mark says why it is what it is, how sure the sorter is, the mark it lies
inside where it lies inside a closed stroke, and its colour, which is read and
kept and decides nothing. *Unsure* is an answer.

`apothecary photo marks PICTURE` lists them. `--say m3=writing` is a person's word
on one: it wins, says who decided, and is kept as an example -- where the mark is,
its features, what the sorter said, what the person said -- in the file `--answers`
names, or beside the picture as `NAME.marks.json`. A reading of a picture takes the
words that lie beside it, so the finder's shapes follow them.

`apothecary photo fit FILE...` reads examples and fits the sorter's thresholds to
them, moving as few as it can. It prints the table, or writes it where `--out`
names, and refuses a fit that sorts the drawn whiteboards worse than the table in
use. The sorter reads the table `APOTHECARY_MARKS_TABLE` names, so a fit is used
only where a person points to it, and the same picture gives the same answer.
`apothecary photo check --finder outline` scores the sorting on drawn whiteboards
with writing beside their shapes.

## Pieces

A shape made into a piece is a root structure of the same site, standing where
the shape was seen, checked for overlap in every site. What is known about a
piece -- its picture, host, camera, the shape and its extent as made, its word
and why -- is kept outside the site, so it finds its outline after its view is
gone; a shape already made is told by that recorded extent, which Make all
skips.

A piece's ring has **Picture › Word** (what it is made as, from the
vocabulary) and **Drop** (chosen twice); **Part › Edit** adjusts its numbers;
and, with a printer pinned in the site, **Slice** and **Print**
([the slicer](slicer.md)). Its SCAD is read only, and it has no Save. Re-sizing
a view rebuilds every piece made from it whose sides no person stated.

## Taking things back

- **Unpin** never deletes a picture.
- **Forget** on a kept picture unpins its views, every site's, and leaves the
  pieces made from it marked forgotten, each still holding its outline.
- **Purge** (the canvas ring's Pictures › Purge) forgets every kept picture,
  never the folder's own.
- **Rebuild** builds the site again from its factory, and its made pieces go.

Views and made pieces are kept in the server's memory and are gone after a
restart; whether they may be kept in the state folder waits on the draft
record *Personal data stays on the device*, which counts the one machine as
the device, being ratified. Nothing
picture-shaped is stored in the browser, its HTTP cache included.

## From the command line

`apothecary photo` takes a picture's path:

| Command | |
|---|---|
| `photo find` | The flat shapes a finder sees in a picture |
| `photo build` | A picture turned into an arrangement of named pieces |
| `photo words` | The named pieces a found shape can turn into |
| `photo finders` | The shape finders available |
| `photo check` | How well a finder does, on pictures whose answers are known |
| `photo view` | A picture's pieces, in a viewer of its own |
| `photo gather`, `photo gather-check` | Several pictures taken in at once and sorted, and how well the sorting does |

`apothecary photo --help`, and `--help` on each, says the rest.
What the gathering's and the finder's thresholds were measured at is in
[validation/2026-08-28-gathering-thresholds.md](validation/2026-08-28-gathering-thresholds.md).
