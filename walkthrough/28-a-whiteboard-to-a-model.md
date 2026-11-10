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
its two ticks, and some writing.

    >>> import tempfile
    >>> from pathlib import Path
    >>> from PIL import Image, ImageDraw
    >>> photograph = Path(tempfile.mkdtemp()) / "whiteboard.png"
    >>> image = Image.new("L", (1600, 1200), 60)
    >>> pen = ImageDraw.Draw(image)
    >>> pen.rectangle((80, 80, 1520, 1120), fill=238, outline=150, width=14)
    >>> pen.rectangle((250, 250, 700, 520), outline=30, width=9)
    >>> pen.ellipse((400, 340, 470, 410), outline=30, width=7)
    >>> pen.ellipse((900, 250, 1200, 550), outline=30, width=9)
    >>> pen.polygon(((350, 950), (650, 950), (500, 700)), outline=30, width=9)
    >>> pen.line((250, 590, 700, 590), fill=30, width=5)
    >>> for x in (250, 700):
    ...     pen.line((x, 575, x, 605), fill=30, width=5)
    >>> for letter in range(6):
    ...     pen.line((400 + letter * 30, 615, 412 + letter * 30, 655), fill=30, width=5)
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

## Read as a drawing

The outline finder takes the whiteboard as the ground, whatever runs round it, and
reads each closed stroke lying on it as the shape of what it encloses. The plate, the
disc and the wedge are found, largest first; the wall, the frame, the dimension line and
the writing are not shapes. The stroke inside the plate is not a piece of its own.

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
- **A cut.** The stroke inside the plate is left out, not cut through it.
- **A whiteboard seen from one side.** The picture is read as it lies, and its width is
  the picture's, not the whiteboard's.
- **The page.** Find shapes on a host's ring offers `outline` beside `plain` for a
  picture that holds a drawing (`tests/test_outline_finder.py`); no browser test walks
  a drawing through it.
- **Round again.** A second photograph of a changed drawing makes its pieces anew.
