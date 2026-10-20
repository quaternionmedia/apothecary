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

The Pictures tab of the rail lists every picture under the root, the folder's
and the kept ones, newest first. A row chosen there is what the ring's
Picture › Folder pins.

## Cameras

A camera is a root structure of a site, `camera_1`, `camera_2` and so on,
drawn as the library's webcam (`parts/cameras/webcam`) standing where it is put
(`apothecary/vision/cameras.py`).

- **Camera › Add here**, on a host's ring, stands one above the host, looking
  straight down, and selects it. A camera can also be dropped from the library.
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

Pinning finds nothing: Find shapes is a step of its own. A view a camera took
keeps where the camera stood and how it was aimed at that moment, so moving
the camera after does not move it, and its picture lands through a pinhole. A
view no camera took is flat on its place, a width across. An unsized view has
no mapping, and nothing is made from it. A picture dropped on a structure, or
pasted, is pinned there; on empty canvas, at the floor.

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
restart; whether they may be kept in the state folder waits on what the draft
record *Personal data stays on the device* counts as this machine. Nothing
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
