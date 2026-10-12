# The viewer

`apothecary serve` serves one page, the viewer: a three.js world that zooms
through a site's tree at any depth, with one rail of panels beside it and a
ring that holds every verb by address. This page describes the page's own
controls as they are. The loops through them are walkthrough pages
[13](../walkthrough/13-a-picture-to-a-print.md) to
[16](../walkthrough/16-editing-a-parts-scad.md); boards and printers are in
[firmware.md](firmware.md), the slicer in [slicer.md](slicer.md).

| Address | Opens |
|---|---|
| `/viewer` (or `/`) | the garage |
| `/viewer/sites/<name>` | a site: `garage`, `parts_library` (the catalog), `datum_core` |
| `?focus=<path>` | zoomed into that piece |
| `?panel=bench` | with the Bench in front (`/firmware` redirects here) |
| `?machine=<port>` | with the Machine of the board on that port open (`/firmware/monitor?port=` leads here) |
| `?variant=<part>:<key>` | with that applied variant of a part drawn, as Apply left it |

## The header

Left to right, one row:

- **The site drop-down** loads another site and puts it in the address,
  `/viewer/sites/<name>`, so a reload or a link lands on it and Back returns
  to the one before; the old site's focus, Machine and variants stay with it.
- **The breadcrumb**: the site, then each piece you have gone into. A crumb
  goes up to its level; Backspace goes up one.
- **⚙ View**: how the world is drawn ([below](#how-the-world-is-drawn)).
- **Docs** opens the documentation in a new tab, the world left where it
  was: the guides, and from its bar the walkthrough's index (`/walkthrough`),
  its pages in order. The ring's Panels › Docs opens the same.
- **⌗ Ring** opens the ring for the chosen piece, as `m` does.
- **The validity count**, "Layout valid" or the number of violations: a click
  unfolds the site's problems in Site.

Under `apothecary serve --demo`, one quiet line above the header says it is
the demo -- a simulated printer and ESP32, scripted firmware tools, its own
state folder -- and how to leave it: `apothecary serve` without `--demo`.

The status line is the bar along the bottom: every verb says there what it
did and what comes next, with the address of the ring cell that does it,
`(⌗98)`. Over the world, the depth ladder has a tick per level, and the hint
bar says the mouse's verbs and fades once they have been used (`?` shows it
again).

## The world

A click selects a piece; a double-click, or scrolling in past the edge of
what is framed, goes into it; scrolling out past the edge comes back up. A
selected piece wears move arrows: dragging one moves it, snapped to a 50 mm
grid while Snap to grid is on. Shift and drag pans. A picture dropped on a
structure, or pasted, is pinned there; on empty canvas, at the floor.

**Walls are drawn faded**, whatever is in front of them: anything whose
category is `wall` is see-through, and a click passes through it to what is
behind or inside. A wall is solid while it is selected. To pick one, tick
⚙ View › Walls selectable (the ring's View › Select walls), or click its row
in Site's tree, which works either way.

**Badges** stand over things in the world, their words shown on hover or
while their thing is selected; three or more that overlap fold into one,
"×N", whose card lists them.

| Badge | Over | A click |
|---|---|---|
| ▣ | a picture lying where it was pinned: its host or the floor, the file, its shapes | selects the host, or the floor |
| 📷 | a camera: its device, its lens, where its next picture lands | selects the camera |
| ⚡ or 🖨 | a pinned board: a devkit's state, or a printer's state and readings | selects the machine and opens its Machine |

A part applied as a variant ([below](#the-part-editor)) is drawn with amber
edges and an amber dot: an applied variant, not saved.

## How the world is drawn

⚙ View folds out the controls below. Each is also a cell of the canvas
ring's View, which adds **Fit**: frame the pieces at this level.

| ⚙ View | The ring's View | Does |
|---|---|---|
| Snap to grid | Snap to grid | Snaps a dragged piece to a 50 mm grid (on at first) |
| Detail: Full, Black box, Dot | Detail › | How much of each compound piece to draw: its real geometry, its bounding box, or a marker. Leaves are always drawn in full; Selected's Detail overrides it for one piece |
| Assembly outlines | Outlines | Outlines each compound piece's whole extent, so a subassembly reads as one thing (on at first) |
| Walls selectable | Select walls | A click in the world picks a wall again, until the page is left (off at first) |

None of them is remembered: a reload starts from the defaults.

The world is drawn only when something in it changes -- the view turned or
easing to a stop, a piece or its colour, the handles, the window's size, a live
camera's video, a texture arriving, a printer's nozzle moving -- so a machine
drawing in software, without a GPU, idles between them and answers typing at
once.

## The ring

`m` opens the ring at the middle of the screen, a right-click at the pointer,
and ⌗ Ring from the header. It opens on what it is for: the selected piece's
ring, or with nothing selected (or the floor) the canvas ring; a right-click
on a piece or a tree row selects it and opens its ring, on empty canvas the
canvas ring, and inside a Machine that board's device ring.

Its cells are a numeric keypad, `7 8 9 / 4 5 6 / 1 2 3`. A ring holds up to
eight options, seated in the order it lists them: 8, 6, 2 and 4 first, then
9, 3, 1 and 7. **5** is the hub: it backs out one ring, and closes the first.
A label ending `›` opens a ring of its own. The digits pressed through nested
rings are the option's **address**, shown under the hub as you go and after
every verb in the status line: `(⌗98)` is 9, then 8. The page writes the same
address into the tooltip of each of its own buttons that a cell also does
(`· ⌗NN`), so a button teaches its digits.

While it is open the ring takes every key: a digit chooses, the arrows move
the highlight to the nearest cell that way, two arrows at right angles
pressed together jump to the corner between them, Enter or Space chooses the
highlighted cell, Backspace backs out, Escape closes. A click on a cell
chooses it, on the hub backs out, and far outside the ring closes it.

**The canvas ring** lists Pieces (each piece at this level; at a site's top
the pieces made from pictures are one more cell, Made), Up (when zoomed in),
Site (every site), Group (each category of the site's pieces: expand it, as
its chip in Site does), View, Panels, Pictures and Reset (the site rebuilt
from its factory, as it was first built).

- **Panels** › Site, Selected, Pictures, Machine (the selected board's), Rail
  (as `~`), Bench › Bench (show it), Install (a cell per toolchain
  module, then the slicer), Compile, Upload, Raw flash, Cancel, Cores,
  Libraries; and Docs (the documentation in a new tab, as the header's Docs).
- **Pictures** › Add (a picture pinned at the floor), Floor (the floor's
  Fit, Camera and Picture), Purge and Gather.

**A piece's ring** lists Zoom in, Move, Device (when a board is pinned to
it), Why this, Into (its children), Up (when nested), then what the piece is:

- a structure that stands on its own footprint, a host: **Camera** › Add here,
  and **Picture** › Add, Folder, Views, Make, Size, Unpin, Forget, Find shapes;
  Add here selects the camera it added, and Make the piece it made;
- a camera: **Device**, Live or Still and **Take picture** (once its device is
  this browser's camera), and Remove;
- a piece made from a picture: **Picture** › Word, Drop;

then **Part** (a part, a camera or a made piece; [below](#the-part-editor): Edit,
Defaults, Apply, Revert, Save, View › Float, Fullscreen, Ghost and Fit,
History › Undo and Redo, and Variants › each saved variant › Draw, Rename,
Duplicate, History, Compare and Delete, and Variants › Deleted), and, when a printer is pinned in the site, **Print** (a made piece) and
**Slice** (a made piece, or a part not inside a printer and not a board: a
devkit is flashed, never printed). Print and Slice say whether the printer
has no board pinned or one pinned and not connected.

A printer's Pin, in its Device section, pins the board inside it -- printer_1's
mainboard, where its Device, its Machine and Slice look -- and asks the board
once what it is (M115), so its Machine opens as a printer's; it asks only when
nothing is known to be printing on that port (a print from here, a running job,
a poll that said so), and the status line says whether it asked, and if not,
why. The printer's Device section then shows its board's pin, with Unpin beside
it. A piece made from a picture holds no board and has no Device section. A
board's **Device** holds Open (its Machine), Poll, Flash, Query, Unpin,
Rescan, Link and, on a printer, Control; [firmware.md](firmware.md#in-the-viewer-one-machine-per-board)
says what each does.

## The rail

One rail beside the world, on the right until ⇄ (or dragging its ⋮⋮ grip
across the page) moves it; its edge sets its width, up to half the page. ✕,
`~` or the ring's Panels › Rail hides it, and `~` brings it back.

- **Site**: the site's problems in one fold (each row selects its piece, at
  its level), its category chips, the **Contents** tree (a click selects a
  row, a double-click goes in, ⚠ marks a piece in a problem), then folds for
  what is **Pinned** in every site (each with its Remove or Unpin), the
  site's **Jobs** (a row opens its machine) and its **SCAD**, generated from
  the tree.
- **Selected**: the selected piece -- its name, place and footprint, a
  compound piece's Detail, "⤵ Zoom into" for one with children -- then its
  part editor, its Device line where a board belongs -- on a board, a printer,
  a piece that names a sketch, or anything a board is pinned to already (a
  pinned board's port and state, with Open and Unpin; for one with none, the
  detected ports to pin) -- and what a camera or a picture's piece knows. A
  plain printed part, a bin, a piece made from a picture has no Device line.
- **The strip of tabs** below them, one shown at a time: **Pictures**, the
  **Bench**, and a **Machine** for each board opened. A tab pressed again
  folds away.

Each panel's title bar collapses it (▾), floats it over the world (⧉; ⇥
docks it again) or closes it (✕); a closed panel keeps a tab at the world's
corner, and the ring's Panels opens it too. A floating panel is dragged by
its title and sized from its corner. The rail's side, width and shown tab,
and each panel's place and state, are remembered by this browser.

## The part editor

**Part › Edit** on a piece's ring opens its editor in Selected: the part's
readiness to build, its **Parameters**, its saved variants and its SCAD. Each
parameter is a control starting from what is drawn, its description as its
caption; a contested one comes first, with its candidates as buttons.

- **A number** is a slider and a box beside it, kept in step: the slider for
  the reach, the box for the exact value, which takes any number typed. Each
  steps on round numbers: the step the field states (a SCAD customizer's
  `[1:0.5:20]`), one for a field that says it is an integer, else a power of
  ten that crosses the range in a hundred to a thousand steps.
- **A choice** is a drop-down; **a yes or no** a tick-box; **words** a box.
- **A vector** is a box for each of its numbers, each captioned (x, y, z).
- **A nested model** is a group of its own fields, under its name.
- A field that declares a **unit** shows it beside its number; one that
  declares none shows nothing.

Where this OpenSCAD cannot build the part at all (gridfinity on 2021.01), the
editor says so as it opens and **Apply is off** from the start, saying why.

The bar of what is staged -- Apply, Revert, Defaults, Undo, Redo, Ghost --
stands pinned at the top of Selected, above its body, in its own space: in view
however far the parameters are scrolled, and over none of them. Where Selected
is squeezed short (a tab's panel open under it), the bar scrolls in itself
rather than spill over what is below.

Moving a control **stages** a value and nothing more. Once the controls rest
the staged set is checked against the part's own model, and the bar above
them says what is staged, whether it is valid and the envelope it would
make. **Apply** renders it: when the result is not the saved part, it is
drawn in this tab only as an applied variant -- amber, not saved -- and the
address carries `?variant=`, so a reload or the link draws it again. The
focus stays where it was: in the box or the slider last moved, or in the SCAD
editor. **Revert** puts what is staged back to what is drawn; **Defaults**
stages the part's own numbers, and Apply then draws the saved part -- after a
SCAD edit too, when the numbers drawn are the part's own already: Apply,
saying "Apply: the saved part", puts the part's own SCAD back in the editor.
Each of these is also a cell of Part on the ring.

**A failed render** -- any error OpenSCAD says, though it finished -- is drawn
greyed where the part stands, as far as OpenSCAD built it, a red flag over it
naming the failing line; what was drawn waits hidden under it until what is
staged is put back or an Apply succeeds. It is never a variant, and Save
refuses it. A render or a check waiting its turn among OpenSCAD's runs (a
few go at once) is said to be **queued**, and how far back, until it runs.

**Undo** and **Redo** under them, Ctrl+Z and Ctrl+Shift+Z (or Ctrl+Y) outside
a box being typed in, and Part › History › Undo and Redo step the staged
numbers back and forward: a slider dragged is one step, and Revert, Defaults
and a variant chosen are a step each. **Recent applies**, a fold under the
parameters, lists this tab's applies of the part, newest first, a reload of
the tab included; one clicked is drawn again from the cache of variants, its
numbers and its SCAD with it.

**A variant is drawn where it stands**: placed by the bounds its render
measured, at its piece, so a part grown is drawn where it grew, standing on
what it stood on. Beside the envelope the part declares is what its drawn STL
measures; when the two differ the line turns amber and says by how much, and a
part reaching below the floor says how far. Selected's Footprint is what the
variant drawn measures, the declared one beside it. The readiness checklist is
of what is drawn -- the variant, its fit judged by what it measured -- against
the build volume of the printer pinned in the site, and **Slice** slices the
variant drawn, its record naming it.

**Ghost**, the tick-box beside Undo and Part › View › Ghost, shows what was
drawn before the newest Apply -- the saved part, or the variant before -- faint
behind what is drawn now, its edges seen through it, and the editor says how
much the size changed. **Part › View › Fit**, and `f`, frames the selected
piece as drawn, from where the view looks, and leaves Selected and its editor
open.

**Work is kept, per tab.** A part's numbers staged and not applied, and its
SCAD edited, are kept in the tab's own storage as they change; after a reload
the status line says which parts have work kept, and each one's editor offers
it back: **Restore** puts it back, **Discard** lets it go. A browser that keeps
nothing for the page offers nothing. Leaving the page with numbers staged and
not applied, or SCAD edited and not rendered or not saved, asks first. Each
part keeps its editor -- the SCAD's text, its undo and where it was scrolled --
while another part is selected.

A piece made from a picture and a camera have the same editor, for their own
numbers: Edit, Apply, Revert, Undo and Redo, and Fit. A made piece's Apply
draws the piece again and nothing else.

## The SCAD editor

Below the parameters is the part's SCAD, in an editor. Typing in it is
checked 300 ms after typing stops, with the numbers staged: a line OpenSCAD
refuses is marked where it is, with its message, and nothing is rendered until
it reads. About 300 ms after a check that passes, the edit is rendered as Apply
renders, from the edited SCAD written beside the part, and drawn as an applied
variant; a newer edit cancels a render waiting, and a render that lands for
older text than the editor holds says so and is not taken for the newer (each
render carries the editor's version, and its answer hands it back). An edit
that compiles as one already rendered, a comment's, is drawn at once. The
part's own file is not touched. **Download SCAD** gives the SCAD as the editor
has it, named as the part's own; with no edit, the draft the variant drawn was
rendered from.

OpenSCAD's keys work inside the editor, and only there:

| Key | Does |
|---|---|
| F5 | Checks the SCAD now, and draws it as soon as it reads |
| F6, or Ctrl+Enter | Renders and draws: Apply |
| Ctrl+S | Saves a variant: Save |

Outside the editor the browser's keys are the browser's.

- **Part › Save** keeps the edit and the staged numbers as a variant in git,
  under the name in the editor's *as* box -- empty, the next free name greyed
  in it: a commit on
  `refs/apothecary/variants/<part>/<name>`, written without touching the
  checkout, HEAD or the working tree. The status line says what making it the
  part's source takes, as the server words it: where the ref lives (a fetch
  first, when `APOTHECARY_VARIANTS_REPO` names another repository to keep them
  in), and that a merge does not apply its numbers. What would be a failed
  render is not saved. A part in a submodule (gridfinity) is saved as an
  **overlay**: a small SCAD that includes the upstream file and sets the values,
  the submodule never touched; an edit of the upstream file itself is refused,
  saying so.
- The *as* box names the variant the text came from while the text is that
  variant's, and is cleared once the text moves on from it, so Save keeps the
  edit under a name of its own. A name already saved is asked about first:
  Save again replaces it.
- **Part › Variants** › a saved variant's name opens a ring of what can be done
  to it, each a button of its row in the editor's list too (its **⋯** unfolds
  them): **Draw** loads it -- its SCAD into the editor, its numbers staged,
  checked and drawn; an overlay is drawn as the upstream SCAD with its values,
  its own text never put in the editor as the part's -- **Rename** and
  **Duplicate**, under the name typed in its row's box (the cell puts the
  cursor there; Enter does it), **History** (each save, newest first, an
  earlier one restored by its **Restore** as a new save, the history keeping
  what came between), **Compare** and **Delete**. The editor's list says of
  each what it changes, and whether it is in HEAD.
- Delete moves a variant to the trash (`refs/apothecary/trash/`): **Part ›
  Variants › Deleted**, and the Deleted fold under the editor's list, hold
  it -- each deleted variant's **Restore** brings it back, its **Forget**
  deletes it for good, and **Empty** deletes them all; Forget and Empty only
  when chosen again to confirm.
- **Compare** draws the variant beside another -- what is drawn, the part's
  own, or another saved one, chosen in the comparison -- where the part stands,
  overlaid (blue and orange, seen through) or side by side, framed, with each
  one's measured size, every number that differs and what the SCAD changes.
  Close draws the part as it was.
- **Part › View › Float** floats the editor over the world (its Dock puts it
  back); **Part › View › Fullscreen** gives it the page (Escape gives it back).

A part built by Python geometry shows the SCAD its geometry generates, read
only, and has no Save; a made piece shows its few lines, read only; a camera
has none. The routes are `/parts/{name}/draft/check`, `/draft/render` and
`/saved`, in `/openapi.json`.

## Keys

| Key | Does |
|---|---|
| `m` | Opens the ring |
| `~` (or `` ` ``) | Hides or shows the rail |
| `P` | Takes a picture, with a camera selected |
| `?` | Shows or hides the hint bar |
| Backspace | Goes up one level |
| Escape | Closes the ring; lets go of the picture chosen in Pictures; leaves the SCAD editor's fullscreen |
| `f` | Frames the selected piece, as drawn, Selected and its editor kept open (Part › View › Fit) |
| Ctrl+Z, Ctrl+Shift+Z or Ctrl+Y | Undoes and redoes the part editor's staged numbers (Part › History) |
| In the ring: 1-9, arrows, Enter, Space, Backspace | As [above](#the-ring) |
| In the SCAD editor: F5, F6, Ctrl+Enter, Ctrl+S | As [above](#the-scad-editor) |

None of them acts while you are typing in a box; Ctrl+Z in a box, or in the
SCAD editor, is that box's own undo.
