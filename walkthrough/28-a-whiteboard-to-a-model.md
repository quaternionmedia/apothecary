# 28 — A whiteboard to a model

**Hermetic.** Everything here runs in this process, on a whiteboard it draws itself in a
scratch folder; nothing opens a port, a browser or the network.

A drawing in marker on a whiteboard becomes pieces with names and sizes. The `outline`
finder reads what each closed stroke encloses, where the `plain` finder gathers dark
pixels into blobs ([docs/pictures.md](../docs/pictures.md#finders)). The pieces it makes
are the ones [page 01](01-photographs-into-pieces.md) makes from a photograph, and in the
page they are made, adjusted, sliced and printed as [page 03](03-a-picture-to-a-print.md)
does. [The plan](../docs/plans/whiteboard-loop-2026-11-09.md) says which steps of the path
are not built.

## The drawing

A whiteboard on a darker wall, a frame round it. On it, in marker: a plate with a hole
drawn in it, a disc and a wedge, each in outline; under the plate a dimension line with
its two ticks and its size written under it, a remark, and a small ring alone.

    >>> import tempfile
    >>> from pathlib import Path
    >>> from PIL import Image, ImageDraw, ImageFont
    >>> photograph = Path(tempfile.mkdtemp()) / "whiteboard.png"
    >>> image = Image.new("RGB", (1600, 1200), (60, 60, 64))
    >>> pen = ImageDraw.Draw(image)
    >>> blue, red, black = (20, 30, 120), (160, 20, 20), (10, 10, 10)
    >>> pen.rectangle((80, 80, 1520, 1120), fill=(238, 238, 236), outline=(150, 150, 150), width=14)
    >>> pen.rectangle((250, 250, 700, 520), outline=blue, width=9)
    >>> pen.ellipse((400, 340, 470, 410), outline=blue, width=7)
    >>> pen.ellipse((900, 250, 1200, 550), outline=blue, width=9)
    >>> pen.polygon(((350, 950), (650, 950), (500, 700)), outline=red, width=9)
    >>> pen.line((250, 590, 700, 590), fill=black, width=5)
    >>> for x in (250, 700):
    ...     pen.line((x, 575, x, 605), fill=black, width=5)
    >>> pen.text((400, 612), "120 mm", fill=black, font=ImageFont.load_default(size=44))
    >>> pen.text((800, 800), "check the fit before cutting", fill=black, font=ImageFont.load_default(size=40))
    >>> pen.ellipse((1290, 950, 1370, 1030), outline=black, width=6)
    >>> image.save(photograph)

## Read as blobs

The plain finder splits the picture's light from its dark and takes whichever does not
run round the edge as the shapes. Here that is the whiteboard itself, the largest thing
it reports, most of the picture across.

    >>> from apothecary.vision import get
    >>> blobs = get("plain").look(photograph)
    >>> whole = blobs.shapes[0]
    >>> whole.max_point.x - whole.min_point.x > 0.85
    True

## Sorted first

Before anything is read as a shape, every mark on the whiteboard is sorted: a diagram's,
writing, or unsure. A mark is the strokes that belong together: a closed stroke, a line,
or small strokes in a row, which is how writing lies. Each says why, and how sure it is.

    >>> from apothecary.vision import marks
    >>> found = marks.marks_in(photograph)
    >>> for mark in found:
    ...     print(mark.id, mark.kind.value, "--", mark.why)
    m1 diagram -- a closed stroke this size is a shape
    m2 diagram -- a closed stroke this size is a shape
    m3 diagram -- a closed stroke alone inside a shape is a cut
    m4 diagram -- a long straight stroke is a line
    m5 writing -- small strokes in a row are writing
    m6 diagram -- a closed stroke this size is a shape
    m7 writing -- small strokes in a row are writing
    m8 unsure -- a small closed stroke alone: a letter, or a hole

*Unsure* is an answer. The ring alone is a small closed stroke: a letter, or a shape
too small to tell. The ring drawn inside the plate is taken for a cut through it. A
mark inside a closed stroke says which, and each mark's colour is read and kept,
deciding nothing.

    >>> found[2].inside, found[7].inside
    ('m1', None)
    >>> found[5].colour, found[0].colour == found[1].colour
    ('red', True)

## A person's word

A person says what a mark is, and their word wins and says who decided. It is kept as
an example: where the mark is, its features, what the sorter said and what the person
said. Examples are what the sorter's thresholds are fitted to (`apothecary photo fit`).

    >>> example = marks.say(found, "m8", marks.Kind.DIAGRAM, picture="this whiteboard")
    >>> example.guess.value, example.word.value, example.by
    ('unsure', 'diagram', 'you')
    >>> said = marks.apply(found, marks.Answers(examples=[example]))
    >>> said[7].kind.value, said[7].why, said[7].guess.value
    ('diagram', 'you said so', 'unsure')

From the command line `apothecary photo marks PICTURE --say m8=diagram` keeps the word
in a file beside the picture, and a reading of the picture takes the words that lie
beside it.

## Read as a drawing

The outline finder takes the whiteboard as the ground, whatever runs round it, and
reads each closed stroke of a diagram's mark as the shape of what it encloses. The
plate, the disc and the wedge are found, largest first; the wall, the frame, the
dimension line, the writing and the ring nobody has spoken for are not shapes. The
ring inside the plate is not a shape of its own: it is the plate's cut.

    >>> drawing = get("outline").look(photograph)
    >>> [shape.kind.value for shape in drawing.shapes]
    ['rect', 'disc', 'tri']
    >>> {shape.origin for shape in drawing.shapes}
    {'outline'}

It is no surer of a shape than the plain finder is of a filled one: how much of its box
a shape fills is a guess at its family, never a certainty.

    >>> all(0.45 <= shape.confidence <= 0.8 for shape in drawing.shapes)
    True

A shape is as wide as the middle of its stroke. The plate was drawn 441 pixels across
between the middles of its sides, of a picture 1600 wide:

    >>> plate = drawing.shapes[0]
    >>> round(plate.long_side * 1600 / 441, 2)
    1.0

## Named, placed and sized

Each shape is matched to a word, and the words are placed as pieces. Nothing is a
measurement until somebody says how wide the picture is; this one is said to be 1600 mm
across, so a pixel of it is a millimetre.

    >>> from apothecary.vision import ScaleReference, build
    >>> unsized = build(drawing)
    >>> unsized.album.sized
    False
    >>> built = build(drawing, scale=ScaleReference(millimetres_across=1600))
    >>> built.album.sized
    True
    >>> for name, piece in built.album.provenance.items():
    ...     print(name, "--", piece.summary().split(";")[0])
    plate_1 -- plate — any other rectangle reads as a flat slab
    disc_2 -- disc — any other circle reads as a flat round piece
    wedge_3 -- wedge — a triangle reads as a tapering block
    >>> {piece.finder for piece in built.album.provenance.values()}
    {'outline'}

The plate is made with its cut through it, where the ring was drawn from the plate's
middle, and about as wide as the middle of the ring's stroke, 63 pixels: a working
picture's pixel is three of this one's.

    >>> (cut,) = drawing.shapes[0].cuts
    >>> cut.kind.value, abs(cut.long_side * 1600 - 63) < 6
    ('disc', True)
    >>> plate_piece = built.site.children[0]
    >>> type(plate_piece.base).__name__, "1 cut(s) through it" in plate_piece.comment
    ('Difference', True)
    >>> [bool(shape.cuts) for shape in drawing.shapes]
    [True, False, False]

A drawing is flat, so a piece's thickness is a guess until a person gives one.

    >>> all(piece.thickness_guessed for piece in built.album.provenance.values())
    True

## From the command line

`apothecary photo find` and `photo build` take the finder by name, and `photo finders`
lists it.

    >>> from click.testing import CliRunner
    >>> from apothecary.cli.main import cli
    >>> listed = CliRunner().invoke(cli, ["photo", "finders"])
    >>> listed.exit_code, listed.output.split()
    (0, ['outline', 'plain', 'stated'])
    >>> found = CliRunner().invoke(cli, ["photo", "find", str(photograph), "--finder", "outline"])
    >>> found.exit_code
    0
    >>> print(found.output.splitlines()[0])
    whiteboard: 3 shape(s), found by outline

`apothecary photo check --finder outline` measures it on drawn whiteboards whose
answers are known: in outline, turned, faint, with a gap in a stroke, under a shadow, a
glare and a smear, with notes beside the shapes, and framed by a wall.

## What this page does not show

- **A real photograph.** The whiteboard here is drawn to order, which is how the answers
  are known.
- **A cut inside a cut.** What is drawn inside a cut is not read.
- **The writing read.** A line of writing is sorted as writing, and what it says is
  not read.
- **A whiteboard seen from one side.** This one is drawn square on.
  `apothecary photo square` finds a leaning whiteboard's corners and redraws the
  photograph square, as wide as the whiteboard (`tests/test_whiteboard.py`).
- **The page.** Find shapes on a host's ring offers `outline` beside `plain` for a
  picture that holds a drawing (`tests/test_outline_finder.py`); no browser test walks
  a drawing through it.
- **Round again.** A second photograph of a changed drawing makes its pieces anew.
