# The viewer

`apothecary serve` serves one page, the viewer: a three.js world that zooms
through a site's tree at any depth, with one rail of panels beside it and a
ring that holds every verb by address. This page describes the page's own
controls as they are. The loops through them are walkthrough pages
[03](../walkthrough/03-a-picture-to-a-print.md) to
[06](../walkthrough/06-editing-a-parts-scad.md); boards and printers are in
[firmware.md](firmware.md), the slicer in [slicer.md](slicer.md).

| Address | Opens |
|---|---|
| `/viewer` (or `/`) | the garage |
| `/viewer/sites/<name>` | a site: `garage`, `parts_library` (the catalog), `datum_core` |
| `?focus=<path>` | stepped into that piece |
| `?panel=bench` | with the Bench in front (`/firmware` redirects here) |
| `?machine=<port>` | with the Machine of the board on that port open (`/firmware/monitor?port=` leads here) |
| `?variant=<part>:<key>` | with that applied variant of a part drawn, as Apply left it |

## The header

Left to right, one row:

- **The site drop-down** loads another site and puts it in the address,
  `/viewer/sites/<name>`, so a reload or a link lands on it and Back returns
  to the one before; the old site's focus, Machine and variants stay with it.
  The drop-down, Site in the canvas ring, a link and Back are the only ways
  the site on screen changes: no other verb switches it as a side effect. A
  picture's view or a take-back in another site names that site and leaves the
  screen where it is.
- **The breadcrumb**: the site, then each piece you have stepped into. A crumb
  steps out to its level; Page Up or Backspace steps out one.
- **⚙ View**: how the world is drawn ([below](#how-the-world-is-drawn)), and
  Settings ([below](#settings)).
- **Docs** opens the documentation in a new tab, the world left where it
  was: the guides, and from its bar the walkthrough's index (`/walkthrough`),
  its pages in order. The ring's Panels › Docs opens the same.
- **⌗ Ring** opens the ring for the chosen piece, as `m` does; its tooltip names
  the key and the modifier Settings gives the ring.
- **The validity count**, "Layout valid" or the number of violations: a click
  unfolds the site's problems in Site.

Under `apothecary serve --demo`, one quiet line above the header says it is
the demo -- a simulated printer and ESP32, scripted firmware tools, its own
state folder -- and how to leave it: `apothecary serve` without `--demo`.

The status line is the bar along the bottom: every verb says there what it
did and what comes next, with the address of the ring cell that does it,
`(⌗98)`. It is announced to a screen reader as it changes. Over the world, the
depth ladder has a tick per level, and the hint bar names the essentials -- a
click, stepping in and out, panning, the ring -- in one line, and fades once
they have been used (`?` shows it again); it names the keys and the modifier
Settings has. [Settings](#settings) is the reference for every binding.

## The world

A still click -- pressed and let go without the pointer travelling more than a
few pixels -- selects the piece it lands on; on empty space it lets the
selection go. A drag of any button selects nothing: it is the view's. A
double-click, Page Down, or scrolling in past the edge of what is framed steps
into a piece; Page Up, Backspace, or scrolling out past the edge steps out. A
selected piece wears move arrows: dragging one moves it, snapped to a 50 mm
grid while Snap to grid is on. A picture dropped on a structure, or pasted, is
pinned there; on empty canvas, at the floor.

**The right button is the camera's.** A right-drag pans. A still right-click
re-centres the view on the surface under the pointer: the point the view turns
about moves there, gliding, and the camera keeps its distance and its angle, so
the next turn turns about what was clicked. On a badge it re-centres on what
the badge stands for; on empty space it does nothing. Neither selects anything
or opens the ring. Ctrl+right-click opens the ring ([below](#the-ring)), heard
before the view so it never turns it.

| Pointer | Does |
|---|---|
| Click | Selects the piece under it; on empty space, lets the selection go |
| Double-click | Steps into the piece under it, as deep as it is drawn |
| Drag | Turns the view about the point it looks at |
| Right-drag, or Shift and drag | Pans |
| Middle-drag | Dollies |
| Right-click | Re-centres the view on the surface under the pointer, or on a badge's piece; on empty space, nothing |
| Ctrl+right-click | Opens the ring at the pointer (the modifier is Settings') |
| Wheel | Dollies in and out; pushed on past the limit, steps a level in or out (automatic zoom) |
| A finger: drag, two fingers, tap, a still long press | Turns; dollies and pans; selects; opens the ring |

**Stepping in** goes into the piece named -- the one double-clicked, or the
ring's -- else the selection, else what the middle of the view shows, walls
passed through as a click passes them; as deep as it is drawn. The status line
says which, and why. Stepping out lands on the piece left, selected. Inside a
piece the world draws what it holds, not the piece: stepped into a printer, its
board and its posts are drawn, and its body is the picture at the level above.
A piece that holds nothing is drawn itself.

**Automatic zoom** is the wheel's step: once the camera is as near the level's
pieces as it may come, or as far out, more scrolling the same way adds up, and
past the resistance the view steps in or out. A trackpad's momentum is not a
push: what scrolled past the limit is forgotten after a quarter of a second
without a turn of the wheel, and nothing steps for a moment after a step.
Whether it steps, each way, how much scrolling it takes and where the limits
sit are [Settings](#settings).

**The world takes the keyboard's focus** -- a press in it, or Tab to it, a ring
round it for the keyboard's hand. While it has it, the arrows pan the view and
Shift+arrows turn it, and Page Up and Page Down step out and in; with nothing
focused after a press in the world they step too. Anywhere else Page Up and
Page Down scroll, as the browser does.

**Escape** does one thing a press, the first that applies: folds ⚙ View; puts a
drag of the move arrows, or of a camera's turn ring or tilt arc, back where it
began, nothing saved; then lets go of the selection. The ring, the SCAD editor's
fullscreen and the picture chosen in Pictures take their Escape first, and a
box being typed in keeps its own.

**Walls are drawn faded**, whatever is in front of them: anything whose
category is `wall` is see-through, and a click passes through it to what is
behind or inside. A wall is solid while it is selected. To pick one, tick
⚙ View › Select walls (the ring's View › Select walls), or click its row
in Site's tree, which works either way.

**Badges** stand over things in the world, their words shown on hover or
while their thing is selected; three or more that overlap fold into one,
"×N", whose card lists them.

| Badge | Over | A click |
|---|---|---|
| ▣ | a picture lying where it was pinned: its host or the floor, the file, its shapes | selects the host, or the floor |
| 📷 | a camera: its device, its lens, where its next picture lands | selects the camera |
| ⚡ or 🖨 | a pinned board: a devkit's state, or a printer's state and readings | selects the machine and opens its Machine |

A badge passes the right button to what it stands for: a still right-click on
it re-centres the view there, and Ctrl+right-click opens that piece's ring (the
floor's, and a ×N's, the canvas ring).

A part applied as a variant ([below](#the-part-editor)) is drawn with amber
edges and an amber dot: an applied variant, not saved.

## How the world is drawn

⚙ View folds out the controls below, each named as its cell of the canvas
ring's View is, which adds **Fit**: frame the pieces at this level (Shift+F;
`f` with nothing selected).

| ⚙ View, and the ring's View | Does |
|---|---|
| Snap to grid | Snaps a dragged piece to a 50 mm grid (on at first) |
| Detail: Full, Black box, Dot | How much of each compound piece to draw: its real geometry, its bounding box, or a marker. Leaves are always drawn in full; Selected's Detail overrides it for one piece |
| Outlines | Outlines each compound piece's whole extent, so a subassembly reads as one thing (on at first) |
| Select walls | A click in the world picks a wall again, until the page is left (off at first) |
| Settings | Opens the Settings panel in the rail ([below](#settings)) |

None of the first four is remembered: a reload starts from the defaults.
Settings are kept by this browser.

The world is the site's own frame, z up, turned onto the screen and never
mirrored: a part reads as OpenSCAD draws it, its engraved text the right way
round, and a picture lies on what it was taken of as it was taken. The axes are
the site's -- red x, green y, blue z -- at its origin while the origin is on the
floor grid, else at the grid's middle; the grid lies on the floor under the
level in view, its lines on whole cells, where snapping puts things. A level is
framed from its front right, above, from as near as 30 mm for a small part, and
View › Fit frames it so again; `f` frames a piece from the side the view is on.

The world is drawn only when something in it changes -- the view turned or
easing to a stop, a piece or its colour, the handles, the window's size, a live
camera's video, a texture arriving, a printer's nozzle moving -- so a machine
drawing in software, without a GPU, idles between them and answers typing at
once.

## The ring

`m` opens the ring at the middle of the screen, Shift+M the canvas ring
whatever is selected, Ctrl+right-click at the pointer, a still long press by
touch at the finger, and ⌗ Ring from the header; [Settings](#settings) gives
the ring other keys, or Alt, Shift or Meta for Ctrl. It opens on what it is
for: the selected piece's ring, or with nothing selected (or the floor) the
canvas ring. Ctrl+right-click is one rule everywhere: on a piece, a badge or a
tree row it selects that piece and opens its ring, on empty canvas the canvas
ring, and inside a Machine that board's device ring. Without the modifier a
right-click is the camera's in the world and the browser's anywhere else, so a
Machine's log can be copied. The press is heard before the view's controls, so
Ctrl+right-click never turns the view. On macOS, Ctrl+click is a right-click,
so Ctrl+click opens the ring there.

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

**Addresses hold still.** The cells a ring always has come first and keep one
address wherever it is opened; the cells that come and go with where it is
opened are seated after them.

**The canvas ring** lists Pieces 8 (each piece at this level; at a site's top
the pieces made from pictures are one more cell, Made; at a leaf, the leaf
itself), Site 6 (every site), View 2, Panels 4, Pictures 9 and Rebuild 3 (the
site built again from its factory, as it was first built: chosen twice); then
Step out 1 (when stepped in) and Group (each category of the site's pieces:
expand it, as its chip in Site does; 7 when stepped in, 1 at the top).

- **Panels** › Site, Selected, Pictures, Machine (the selected board's), Rail
  (as `~`), Bench › Bench (show it), Install (a cell per toolchain
  module, then the slicer), Compile, Upload, Raw flash, Cancel, Cores,
  Libraries; and Docs (the documentation in a new tab, as the header's Docs).
- **Pictures** › Add (a picture pinned at the floor), Floor (the floor's
  Fit, Camera and Picture), Purge and Gather.

**A piece's ring** lists Step in 8, Move 6 and Why this 2, then Inside (the
pieces it holds: a digit selects one), then what the piece is:

- a structure that stands on its own footprint, a host: **Camera** › Add here,
  and **Picture** › Add, Folder, Views, Make, Size, Unpin, Forget, Find shapes
  ([pictures.md](pictures.md) says what each does); Add here selects the camera
  it added, and Make the piece it made;
- a camera: **Device**, Live or Still and **Take picture** (once its device is
  this browser's camera), and Remove (chosen twice);
- a piece made from a picture: **Picture** › Word, Drop (chosen twice);

then **Part** (a part, a camera or a made piece; [below](#the-part-editor): Edit,
Defaults, Apply, Revert, Save, View › Float, Fullscreen, Ghost and Fit,
History › Undo and Redo, and Variants › each saved variant › Draw, Rename,
Duplicate, History, Compare and Delete, and Variants › Deleted), and, when a printer is pinned in the site, **Print** (a made piece) and
**Slice** (a made piece, or a part not inside a printer and not a board: a
devkit is flashed, never printed). Print and Slice say whether the printer
has no board pinned or one pinned and not connected. Last come the cells that
depend on where the piece is: **Device** (when a board is pinned to it) and
**Parent** (the piece it is inside, selected).

A printer's Pin, in its Device section, pins the board inside it -- printer_1's
mainboard, where its Device, its Machine and Slice look -- and asks the board
once what it is (M115), so its Machine opens as a printer's; it asks only when
nothing is known to be printing on that port (a print from here, a running job,
a poll that said so), and the status line says whether it asked, and if not,
why. The printer's Device section then shows its board's pin, with Unpin beside
it. A piece made from a picture holds no board and has no Device section. A
board's **Device** holds Open (its Machine), Poll, Flash, Query, Unpin,
Rescan, Link (Reconnect, Reboot, Release) and, on a printer, Control;
[firmware.md](firmware.md#in-the-viewer-one-machine-per-board) says what each
does.

**Asking first goes by consequence.** What the page can undo asks nothing. What
it cannot -- Rebuild, Drop, a camera's Remove, a picture's Forget, Purge, a
variant's Forget and Empty, a board's Reboot, a print's Cancel and Abort -- is
chosen twice: chosen once, its wedge (or its button) says "again to …", and
choosing it again does it. What heats, moves or flashes a machine -- Probe the
bed, Print, Compile and upload, Raw flash -- asks in a dialog; the control
overlay's own buttons stand behind its armed latch. The emergency stop never
asks.

## The rail

One rail beside the world, on the right until ⇄ (or dragging its ⋮⋮ grip
across the page) moves it; its edge sets its width, up to half the page. ✕,
`~` or the ring's Panels › Rail hides it, and `~` brings it back.

- **Site**: the site's problems in one fold (each row selects its piece, at
  its level), its category chips, the **Contents** tree (a click selects a
  row, a double-click steps in, ⚠ marks a piece in a problem), then folds for
  what is **Pinned** in every site (each with its Remove or Unpin), the
  site's **Jobs** (a row opens its machine) and its **SCAD**, generated from
  the tree.
- **Selected**: the selected piece -- its name, place and footprint, a
  compound piece's Detail, "⤵ Step into" for one with children -- then its
  part editor, its Device line where a board belongs -- on a board, a printer,
  a piece that names a sketch, or anything a board is pinned to already (a
  pinned board's port and state, with Open and Unpin; for one with none, the
  detected ports to pin) -- and what a camera or a picture's piece knows. A
  plain printed part, a bin, a piece made from a picture has no Device line.
- **The strip of tabs** below them, one shown at a time: **Pictures**, the
  **Bench**, **Settings**, and a **Machine** for each board opened. A tab
  pressed again folds away.

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

**The parameters and the SCAD are one draft.** A part's values are the
top-level assignments in its SCAD, read as
[parts-authoring.md](parts-authoring.md#in-the-page-the-text-is-the-truth)
says: moving a control rewrites its value in its line, at once, keeping the
line's comment and range, and a value typed in the text moves its control. A
name the text does not assign yet gets its line appended. The controls are
the part's model's fields, where it has a model, then every other parameter
its text assigns, each described by its line's comment and the caption above
it. **A computed one** (`wall = size * 0.1;`) shows the value the newest
check gave it, under its expression; until a check has given one it says
"computed when checked". Moving it asks first: **Replace** puts the plain value
in place of the expression, as one edit Undo takes back; **Keep it computed**
leaves it. **A part in a submodule** (gridfinity) is edited as its overlay: the
editor holds the include of the upstream file and the values set after it;
the upstream's parameters the overlay does not set are listed with
upstream's value, and moving one sets it in the overlay. The upstream file is
one step away, **Upstream SCAD, read only**, beside Download SCAD. A part whose
SCAD its Python generates (the snowplow) and a made piece stay one way: their
controls drive the model, and the SCAD follows, read only.

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

Where this OpenSCAD cannot build the part at all (gridfinity on
[2021.01](openscad.md#what-openscad-202101-cannot-do)), the
editor says so as it opens and **Apply is off** from the start, saying why.

The bar of what is staged -- Apply, Revert, Defaults, Undo, Redo, Ghost --
stands under the Parameters heading, and Selected shows the piece's name,
place and facts first. While the piece is being edited -- Part › Edit asked
for its editor, or something is staged -- the bar stands pinned at the top of
Selected, above its body, in its own space: in view however far the parameters
are scrolled, and over none of them. Where Selected is squeezed short (a tab's
panel open under it), the bar scrolls in itself rather than spill over what is
below. Whatever control had the focus in Selected has it again when the panel
is drawn anew.

Moving a control **stages** a value: its line is rewritten and nothing is
drawn. Once the controls rest the text is checked, its values against the
part's own model, and the bar above them says what is staged -- what the text
says otherwise than the text drawn -- whether it is valid and the envelope it
would make. What is typed in the SCAD is drawn once it reads
([below](#the-scad-editor)).
**Apply** renders the text, its values in it, nothing passed on the side:
when the result is not the saved part, it is
drawn in this tab only as an applied variant -- amber, not saved -- and the
address carries `?variant=`, so a reload or the link draws it again. The
focus stays where it was: in the box or the slider last moved, or in the SCAD
editor. **Revert** puts the text drawn back; **Defaults** puts the part's
own text back -- its defaults are its SCAD as saved -- and Apply, saying
"Apply: the saved part", then draws the saved part. Each of these is an edit
of the text, which Undo takes back, and each is also a cell of Part on the
ring.

**A failed render** -- any error OpenSCAD says, though it finished -- is drawn
greyed where the part stands, as far as OpenSCAD built it, a red flag over it
naming the failing line; what was drawn waits hidden under it until what is
staged is put back or an Apply succeeds. It is never a variant, and Save
refuses it. A render or a check waiting its turn among OpenSCAD's runs (a
few go at once) is said to be **queued**, and how far back, until it runs.

**Undo** and **Redo** under them, Ctrl+Z and Ctrl+Shift+Z (or Ctrl+Y) outside
a box being typed in, and Part › History › Undo and Redo step the draft back
and forward: the SCAD editor's own history, so the text and the controls go
back together, whichever moved them. A slider dragged is one step, a control's
moves are never one step with typing beside them, and Revert, Defaults and a
variant chosen are a step each. **Recent applies**, a fold under the
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

**Work is kept, per tab.** A part's SCAD as edited -- its values with it -- and
a made piece's or a camera's numbers staged and not applied are kept in the
tab's own storage as they change; after a reload
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

Below the parameters is the part's SCAD, in an editor: the same draft as the
controls above it, its values theirs. Typing in it is
checked 300 ms after typing stops, the values in it: a line OpenSCAD
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

OpenSCAD's keys work inside the editor, and Ctrl+S anywhere on the page while
a part's editor is open:

| Key | Does |
|---|---|
| F5 | Checks the SCAD now, and draws it as soon as it reads (in the editor) |
| F6, or Ctrl+Enter | Renders and draws: Apply (in the editor) |
| Ctrl+S | Saves a variant: Save (anywhere, while the editor is open) |

Outside the editor F5, F6 and Ctrl+Enter are the browser's.

- **Part › Save** keeps the text as a variant in git, its values in it,
  under the name in the editor's *as* box -- empty, the next free name greyed
  in it: a commit on
  `refs/apothecary/variants/<part>/<name>`, written without touching the
  checkout, HEAD or the working tree. The status line says what making it the
  part's source takes, as the server words it: where the ref lives (a fetch
  first, when `APOTHECARY_VARIANTS_REPO` names another repository to keep them
  in), and that a merge brings its values with it -- or, for a variant whose
  values are in a `.variant.json` beside its SCAD and not in its text, that a
  merge does not apply them until it is saved again.
  What would be a failed render is not saved. A part in a submodule
  (gridfinity) is saved as its **overlay**: the include of the upstream file
  and the values set after it, the submodule never touched; an edit of the
  upstream file itself is refused, saying so.
- The *as* box names the variant the text came from while the text is that
  variant's, and is cleared once the text moves on from it, so Save keeps the
  edit under a name of its own. A name already saved is asked about first:
  Save again replaces it.
- **Part › Variants** › a saved variant's name opens a ring of what can be done
  to it, each a button of its row in the editor's list too (its **⋯** unfolds
  them): **Draw** loads it -- its SCAD into the editor, its values in it and
  the controls on them, checked and drawn; a part in a submodule's variant is
  its overlay, the upstream file never put in the editor as the part's; a
  variant whose values are in a `.variant.json` and not its text has them
  written in when it is read -- **Rename** and
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

## Settings

**Settings**, a tab of the rail's strip, holds every shortcut and navigation
setting of the page, and is the reference for every binding. ⚙ View ›
Settings and the canvas ring's View › Settings open it. Each row says its default under its name, and its ↺ puts it back;
**Reset all**, at the foot, puts every one back. A change applies at once,
with no reload.

| Setting | Default | What it is |
|---|---|---|
| Open the ring | `m` | The key that opens the ring on the selection |
| Open the canvas ring | Shift+M | The key that opens the canvas ring, whatever is selected |
| Ring: right-click with | Ctrl | The modifier held with a right-click to open the ring at the pointer: Ctrl, Alt, Shift or Meta |
| Step in | Page Down | The key that steps into the selected piece, or what the middle of the view shows |
| Step out | Page Up | The key that steps out to the level above |
| Automatic zoom | on | Whether the wheel pushed on past the limit steps at all |
| Stepping in | on | Whether it steps in |
| Stepping out | on | Whether it steps out |
| Resistance | 500 | How much scrolling past the limit it takes before a step; a wheel's notch is about 100 |
| Nearest | 0.08 | How near the pieces of a level the camera may come, as a fraction of the level's size: where stepping in starts |
| Farthest | 8 | How far out of a level it may go, as a multiple of the distance that frames the level: where stepping out starts |

**A shortcut's field** takes the next key pressed: press the field, then the
key, with Ctrl, Alt, Shift or Meta if they are to be held. A key another
shortcut holds -- one of these, or one of the page's own [keys](#keys) -- is
refused, and the field says whose it is and waits for another; Escape lets go
of it. A shortcut is matched by the key it prints and by where the key sits on
a US keyboard, so a layout that prints something else there still reaches it;
a letter is matched with Shift said or not, so Caps Lock changes nothing.

The settings are kept in this browser's storage, under one key
(`apothecary.settings`), and only those that differ from their defaults. A
browser that keeps nothing (storage refused, a private window) starts from the
defaults, and a change holds until the page is left.

## Keys

| Key | Does |
|---|---|
| `m` | Opens the ring on the selection (Settings' Open the ring) |
| Shift+M | Opens the canvas ring, whatever is selected (Settings' Open the canvas ring) |
| Page Down | Steps in: the selection, else what the middle of the view shows (Settings' Step in), while the world has the keys |
| Page Up, or Backspace | Steps out a level (Settings' Step out), Page Up while the world has the keys |
| Arrows, Shift+arrows | Pan, and turn, the view, while the world has the keyboard's focus |
| `~` (or the key left of 1) | Hides or shows the rail |
| `P` | Takes a picture, with a camera selected |
| `?` | Shows or hides the hint bar |
| Escape | One thing a press: folds ⚙ View; puts a drag back where it began, nothing saved; lets go of the selection. In the ring it closes the ring, in the SCAD editor's fullscreen it leaves it, in Pictures it lets go of the picture chosen, in a Settings field it lets go of the field |
| `f` | Frames the selected piece, as drawn, Selected and its editor kept open (Part › View › Fit); with nothing selected, the level |
| Shift+F | Frames the level, whatever is selected (View › Fit) |
| Ctrl+Z, Ctrl+Shift+Z or Ctrl+Y | Undoes and redoes the part editor's staged numbers (Part › History) |
| Ctrl+S | Saves the variant, anywhere, while a part's editor is open (Part › Save) |
| In the ring: 1-9, arrows, Enter, Space, Backspace | As [above](#the-ring) |
| In the SCAD editor: F5, F6, Ctrl+Enter | As [above](#the-scad-editor) |

One check decides for every key: none acts while you are typing in a box, a
drop-down or the SCAD editor, nor on a key the focus takes itself (a slider
keeps the arrows, Page Up and Page Down; a button, Enter and Space); Ctrl,
Alt, Shift or Meta held rules Backspace out. Ctrl+Z in a box, or in the SCAD
editor, is that box's own undo.
