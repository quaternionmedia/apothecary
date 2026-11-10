# A whiteboard to a model, and round again: a plan

*A plan, dated. Built: slice 1, the `outline` finder
([pictures.md](../pictures.md#finders),
[walkthrough 28](../../walkthrough/28-a-whiteboard-to-a-model.md)). Each slice
is one branch of a short stack, built in the order listed once the owner says
yes to it.*

## What this plans

A person thinks on a whiteboard: a bracket, a plate with two holes, where three
things stand on the bench. This plan makes the whiteboard a way into
apothecary. The drawing is photographed, the photograph becomes pieces with
names and sizes, the pieces are looked at in the world and adjusted, and the
whiteboard is corrected and photographed again. Each time round, the model
follows the drawing, and a person's word holds where they gave one.

It plans two things:

- **the path**: the steps a person takes from a marker to a model, each a step
  of the page or one command, shown by a walkthrough page a test writes;
- **the featureset**: what the tool gains so each step works on a drawing, in
  slices.

The loop beside the ones built:

| Station | A picture to a print, as built | A whiteboard to a model, this plan |
|---|---|---|
| The subject | a thing lying on the bench, under a camera | a drawing in marker on a whiteboard |
| The picture | a camera of the site takes it, or a file is pinned | a phone's photograph dropped on the page, or a camera aimed at the whiteboard |
| Squared and sized | a camera's picture lands through a pinhole; a file is flat, a width across | the whiteboard's own edge squares it, and its width, said once, sizes every drawing on it |
| Found | filled shapes, light from dark | strokes: a closed stroke is a shape, a stroke inside it a cut |
| Made | a shape stands up as a piece | the same, with its cuts |
| Adjusted | Part › Edit, a person's numbers over the guess | the same |
| Round again | a second picture, a second piece | a second photograph of the same whiteboard, and the pieces already made follow it |
| Kept | sliced and printed | sliced and printed as built; saved as a part once *A made piece saved as a variant* is built |

## Words

*Whiteboard* is always written out. *Board* is a circuit board here (the
devkit, a printer's mainboard) and *sketch* is firmware, so the drawing is a
*drawing*, its marks are *strokes*, and the finder that reads them is `outline`.

## What exists

- The finder seam: a protocol, a registry, two finders (`stated`, `plain`), a
  bench of pictures whose answers are known (`apothecary/vision/finder.py`,
  `apothecary photo check`).
- The plain finder: light split from dark, touching pixels gathered, a blob's
  family guessed from how much of its tightest box it fills
  (`apothecary/vision/plain.py`).
- Words: `disc`, `plate`, `post`, `slot`, `wedge` (`apothecary photo words`).
- A picture pinned at a place as a view, sized by a width a person types or by
  the camera that took it, its shapes made into pieces, a piece adjusted,
  sliced and printed ([pictures.md](../pictures.md),
  [walkthrough 03](../../walkthrough/03-a-picture-to-a-print.md)).
- A view's mapping is a homography (`apothecary/vision/projection.py`), so a
  picture taken at an angle has a place to carry its squaring.
- Several photographs sorted into which are of the same thing, by matching
  shapes under one step and zoom (`apothecary/gathering/`,
  [walkthrough 01](../../walkthrough/01-photographs-into-pieces.md)).
- A made piece's record keeps the shape and extent it was made from, which
  Make all reads to skip a shape already made (`apothecary/vision/views.py`).
- A picture's ways in: dropped or pasted on the page, added from disk, put in
  the picture folder, taken by a camera of the site.

## What a drawing reads as to the plain finder

Three pictures drawn to order, each a rectangle, a circle and a triangle on a
light ground, read by `apothecary photo find --finder plain`:

| The picture | What `photo find` says |
|---|---|
| The three filled in | `rect`, `disc`, `tri`, read as plate, disc and wedge, each sure past 0.6 |
| The three as marker outlines, the whiteboard filling the picture | three `poly`, each read as plate at 0.30: the stroke is the blob, and a ring fills little of its box |
| The same outlines, the whiteboard framed by a darker wall, a small circle drawn inside the rectangle and a dimension line under it | the outlines' insides as plate, disc and wedge; the whiteboard itself as one more shape, a disc across nearly the whole picture; the small circle as a plate of its own, not a cut; the dimension line not at all |

The third reads the drawing's insides only because the wall is dark: the
picture's edge decides which side is ground, and the whiteboard becomes the
thing found. Not measured here: a real photograph. Glare, a shadow across the
whiteboard, a marker running dry, an eraser's smear and the tray under it are
all absent from a drawn picture, and slice 1's bench is where each is drawn and
counted.

## The path

What a person does, in the page's own words where they exist:

1. **Draw** on a whiteboard, in any dark marker. A closed stroke is a thing; a
   closed stroke inside it is a hole through it.
2. **Photograph** it, the whole whiteboard in the frame, edge to edge.
3. **Bring it in**: drop the photograph on the place the thing belongs (the
   bench, the floor), or pin it from Pictures. With a camera of the site aimed
   at the whiteboard, Take picture.
4. **Size it**: the place's ring, Picture › Size, and the whiteboard's width.
   Said once for a whiteboard, it sizes each later photograph of it.
5. **Find shapes**: Picture › Find shapes outlines each closed stroke where the
   picture lies, squared to the whiteboard's edge.
6. **Make**: Picture › Make, or Make all. Each stands as a piece, its cuts
   through it, named for its word.
7. **Adjust**: Part › Edit. A thickness, which no drawing shows, and any side a
   person knows better than the marker did.
8. **Round again**: change the drawing, photograph it, drop it on the same
   place. The page lists what moved, grew, appeared and was rubbed out, piece
   by piece, and changes nothing until each is taken.
9. **Keep it**: Slice and Print as built.

From the command line the same path is `apothecary photo build --finder
outline --width-mm`, and `photo view` for the result.

## The featureset

Each slice is one branch, stacked on the one before it, gated by
`apothecary test run`, with `apothecary test all` once on the top. The path's
walkthrough page starts in slice 1 and gains a step with each slice after it.

### 1. A drawing's strokes read as shapes

A third finder, `outline`, registered beside `plain` and `stated`:

- the ground is the whiteboard, found as the light region the strokes lie in,
  whatever runs round the picture's edge; the whiteboard is never a shape;
- light is split from dark near each pixel, not once for the whole picture, so
  a shadow or a glare across the whiteboard moves no stroke to the wrong side;
- a closed stroke is the shape of what it encloses, named by the rule the plain
  finder names a filled shape by, and no surer than the plain finder is;
- a mark filled in is the shape it covers;
- a stroke that neither closes nor fills a shape, a dimension line, an arrow or
  writing, is not reported, and neither is a stroke inside a shape, which
  slice 2 reads;
- a gap in a stroke a few pixels of the working picture wide is closed, and a
  wider one leaves the stroke open;
- Pillow alone, with the network off, as every finder is.

`apothecary photo check` draws whiteboards whose answers are known: in
outline, turned, faint, a gap in a stroke, a shadow's gradient, a glare, a
smear, notes beside the shapes, a wall, a frame and a tray. The page's Find
shapes offers `outline` beside `plain` for a picture that holds a drawing, a
closed stroke at least, and stays one press for any other. Held by
`tests/test_outline_finder.py`, whose floors are the bench's; the hermetic half
of the path's page is
[walkthrough 28](../../walkthrough/28-a-whiteboard-to-a-model.md).

Not in it: a shadow with a hard edge, which, where it is dark enough to read
as a stroke, loses a shape it crosses; a shape filled in faintly, which it
misses; and a real photograph.

### 2. A stroke inside a stroke is a cut

A closed stroke wholly inside another is a cut through the outer one, not a
piece of its own: `FoundShape` says which shape holds it, a made piece is its
word less its cuts, and Part › Edit lists each cut's place and size beside the
piece's own. A cut inside a cut is reported and not made. Held by the made
part's tests (`tests/test_made_part.py`) and the vocabulary's.

### 3. The whiteboard squared, and its width said once

- The whiteboard's four corners are found from its ground's outline; a person
  drags any the finder got wrong, on the picture where it lies.
- The corners give the view its mapping, so a photograph taken from one side
  lays its shapes square.
- Picture › Size on a squared picture is the whiteboard's width, not the
  photograph's. It is kept with the place's views as a camera's lens is kept
  with the camera: the next photograph of that whiteboard, told as the same
  one by its corners' proportions, is sized as it lands, and a person's later
  word replaces it.

Held by `tests/test_views_api.py` and a browser test of the corners.

### 4. Round again

A photograph pinned where an earlier one of the same whiteboard lies is read
against the pieces made from the earlier one, shapes matched as the gathering
matches two photographs of one thing:

- a shape that matches a piece and has not changed proposes nothing;
- one that moved or changed size proposes the change to its piece;
- one that matches nothing proposes a new piece;
- a piece whose shape is gone proposes its Drop.

Each proposal is a row a person takes or leaves, and nothing changes until
one is taken, as *Photo gathering proposes and waits* ([todo.md](../../todo.md),
*Next round*) decides for the gathering. A side a person stated in Part › Edit is not proposed over: the row
says the drawing and the person disagree, and by how much. Held by a browser
test that goes round twice.

### 5. The path, promoted

- **Its page**: a runtime-bound page beside
  [walkthrough 28](../../walkthrough/28-a-whiteboard-to-a-model.md), the next
  number free when it lands, written by the browser test that walks the path
  twice round; a row of the README's map, held by `tests/test_readme_map.py`.
- **In the demo**: `apothecary serve --demo`'s picture folder holds a drawn
  whiteboard, so the path is a drop and three cells away for a newcomer, and
  page 00's table of loops names it.
- **In the page**: no sentence is added. A photograph the `outline` finder
  reads better than `plain` does has Find shapes offer it first; the status
  line names the next step, as every step of walkthrough 03 does.

## Pages with pictures

| Slice | Page | Written by |
|---|---|---|
| 1 | 28, *A whiteboard to a model*, hermetic: a drawn whiteboard read, named, placed and sized | its own doctests |
| 2 | 28 gains a piece with a cut | the same |
| 3 to 5 | a runtime-bound page beside it: the photograph dropped, squared, sized, found, made, adjusted, and round again | a browser test, its pictures recorded and never compared |

## Questions the owner decides

Asked one at a time:

1. the plan's shape: these five slices, in this order;
2. whether a marker's colour means anything (red for a cut, green for a note
   that is never made), or nesting alone says a cut, as slice 2 has it;
3. whether a whiteboard is a part of the site, standing at a wall with its
   width in its parameters and a camera aimed at it, or only a picture's
   ground, as slice 3 has it;
4. whether the path is a fifth loop of page 00, or a way into the third;
5. whether a real photograph of a real whiteboard is kept in `examples/` for
   the bench, and whose.

## What it leaves

- **A size written on the whiteboard.** No plain reader reads handwriting. A
  written size beside a side is a label an image model reads, on a person's
  ask, as an observation that never stands over a person's word:
  [image-models-through-qmcp-2026-10-30.md](image-models-through-qmcp-2026-10-30.md).
  Until then a side is sized in Selected's width box.
- **The model kept as a part.** A made piece has no Save; *A made piece saved
  as a variant* ([todo.md](../../todo.md), *Next round*) is the path's last
  step once it is built, and waits on the record it names.
- **A drawing to a cut.** A piece made from a drawing declares no cuts for the
  router ([cam.md](../cam.md)); a flat piece with holes is the router's
  natural work, and a plan of its own.
- **A phone that sends its photograph.** A photograph arrives by a drop, a
  paste or the picture folder. Nothing listens for a phone, and what may is the
  draft record *Personal data stays on the device*'s to say.
- **Curves and freehand.** A closed stroke is named as one of the words. A
  freehand outline kept as its own polygon needs `FoundShape.points` to have a
  consumer, which the finders plan also waits on
  ([photo-finders-local-models-2026-09-21.md](photo-finders-local-models-2026-09-21.md)).
- **Height.** A drawing is flat. A thickness is a person's, in Part › Edit.
