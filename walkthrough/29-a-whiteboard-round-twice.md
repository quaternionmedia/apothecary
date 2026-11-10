# 29 — A whiteboard, round twice

**Hermetic.** Everything here runs in this process, on whiteboards it draws itself in a
scratch folder; nothing opens a port, a browser or the network.

The whiteboard loop from a photograph to pieces and round again, each step the one a
command does: `photo square`, `photo marks`, `photo notes`, `photo build`, and, with the
drawing changed and photographed again, `photo again`. [Page 28](28-a-whiteboard-to-a-model.md)
is what one reading holds; [docs/pictures.md](../docs/pictures.md#a-whiteboards-marks) is
the reference. At every step the tool says what it takes a thing to be, a person's word
wins, and nothing is made or changed that a person did not take.

## The first photograph

A whiteboard on a wall. On it a plate with a ring drawn in it, a dimension line under the
plate with its size written beside it, and a ring alone.

    >>> import tempfile
    >>> from pathlib import Path
    >>> from PIL import Image, ImageDraw, ImageFont
    >>> folder = Path(tempfile.mkdtemp())
    >>> blue, black = (20, 30, 120), (10, 10, 10)
    >>> def photograph(name, plate, ring=True, disc=False):
    ...     image = Image.new("RGB", (1800, 1400), (60, 60, 64))
    ...     pen = ImageDraw.Draw(image)
    ...     pen.rectangle((100, 100, 1700, 1300), fill=(238, 238, 236))
    ...     pen.rectangle(plate, outline=blue, width=9)
    ...     pen.ellipse((420, 420, 500, 500), outline=blue, width=7)
    ...     pen.line((350, 690, 800, 690), fill=black, width=5)
    ...     pen.text((500, 705), "120 mm", fill=black, font=ImageFont.load_default(size=44))
    ...     if ring:
    ...         pen.ellipse((1390, 1050, 1470, 1130), outline=black, width=6)
    ...     if disc:
    ...         pen.ellipse((1000, 350, 1300, 650), outline=blue, width=9)
    ...     image.save(folder / name)
    ...     return folder / name
    >>> first = photograph("monday.png", plate=(350, 350, 800, 620))

## Squared

`photo square` finds the whiteboard's corners and redraws the photograph as the
whiteboard seen square on. This whiteboard is 1600 mm by 1200 mm, and the squared
picture is as wide as it is.

    >>> from apothecary.vision import whiteboard
    >>> used, size = whiteboard.square(first, folder / "monday-squared.png", wide_over_tall=1600 / 1200)
    >>> used.by, size
    ('finder', (1600, 1200))
    >>> drawn_at = [(100 / 1800, 100 / 1400), (1700 / 1800, 100 / 1400), (1700 / 1800, 1300 / 1400), (100 / 1800, 1300 / 1400)]
    >>> all(abs(x - at_x) < 0.006 and abs(y - at_y) < 0.006 for (x, y), (at_x, at_y) in zip(used.corners, drawn_at))
    True
    >>> monday = folder / "monday-squared.png"

## Sorted, and refined

`photo marks` sorts every mark. The ring in the plate is taken for a cut, the line for a
line, the size for writing; the ring alone is unsure.

    >>> from apothecary.vision import marks
    >>> found = marks.marks_in(monday)
    >>> [(mark.id, mark.kind.value) for mark in found]
    [('m1', 'diagram'), ('m2', 'diagram'), ('m3', 'diagram'), ('m4', 'writing'), ('m5', 'unsure')]
    >>> found[1].why, found[1].inside
    ('a closed stroke alone inside a shape is a cut', 'm1')

A person says the ring alone is nothing: a mark left from another day. Their word is
kept beside the picture, as `photo marks --say m5=nothing` keeps it, and every reading
of the picture after takes it.

    >>> from apothecary.vision.cache import picture_hash
    >>> said = marks.Answers(examples=[marks.say(found, "m5", marks.Kind.NOTHING, picture_hash(monday))])
    >>> marks.save(marks.answers_path(monday), said)
    >>> [(m.id, m.kind.value, m.by) for m in marks.marks_in(monday) if m.by != "sorter"]
    [('m5', 'nothing', 'you')]

## Its note, and its size

`photo notes` lists the writing with what it is about. A person types what the note
says; it begins with a size and lies beside a line, so it states the line's length, and
the picture's width follows. The line was drawn 450 mm long on a whiteboard 1600 mm
wide, so the note is wrong about the scale, and it is the person who decides which to
believe: here the whiteboard's own width.

    >>> from apothecary.vision import notes
    >>> said.words.append(notes.say(found, "m4", "120 mm"))
    >>> marks.save(marks.answers_path(monday), said)
    >>> (note,) = notes.notes_of(marks.marks_in(monday), said, tallness=1200 / 1600)
    >>> note.words, note.lies, note.about, note.offer.of
    ('120 mm', 'beside', 'm3', 'm3')
    >>> 410 < note.offer.picture_mm < 440
    True
    >>> print(notes.transcript([note]))
    m4 (beside m3): 120 mm

`photo notes --send` would post that transcript to looksatwords on this machine, and
`--ask --among` a note's region to qmcp; neither is asked here.

## Made

`photo build --finder outline --width-mm 1600` reads the diagram's marks as shapes and
makes them: one plate, with its cut through it.

    >>> from apothecary.vision import ScaleReference, build, get
    >>> before = get("outline").look(monday)
    >>> [(shape.kind.value, len(shape.cuts)) for shape in before.shapes]
    [('rect', 1)]
    >>> built = build(before, scale=ScaleReference(millimetres_across=1600))
    >>> (piece,) = built.site.children
    >>> piece.category, type(piece.base).__name__
    ('plate', 'Difference')
    >>> abs(before.shapes[0].long_side * 1600 - 441) < 8
    True

## Round again

The drawing is changed: the plate drawn wider, a disc added beside it, the stray ring
rubbed out. It is photographed and squared as the first was.

    >>> second = photograph("tuesday.png", plate=(350, 350, 900, 620), ring=False, disc=True)
    >>> _ = whiteboard.square(second, folder / "tuesday-squared.png", wide_over_tall=1600 / 1200)
    >>> after = get("outline").look(folder / "tuesday-squared.png")

`photo again` lists what the later picture proposes of the earlier's shapes, each row
saying by how much.

    >>> from apothecary.vision import again
    >>> rows = again.compare(before, after)
    >>> [(row.number, row.change.value, row.kind) for row in rows]
    [(1, 'resized', 'rect'), (2, 'new', 'disc')]
    >>> rows[0].says
    'its long side is 1.23 times what it was'

Nothing has changed. A row left leaves the earlier picture's shape as it was, and a row
taken takes the later's: here the disc is taken and the wider plate is left.

    >>> again.taken_from(before, after, rows, []).shapes == before.shapes
    True
    >>> kept = again.taken_from(before, after, rows, [2])
    >>> [shape.kind.value for shape in kept.shapes]
    ['rect', 'disc']
    >>> kept.shapes[0].long_side == before.shapes[0].long_side
    True
    >>> len(build(kept, scale=ScaleReference(millimetres_across=1600)).site.children)
    2

## What this page does not show

- **The page.** Each step here is a command or the function under it. In the viewer a
  picture's marks, notes, corners and rows are not yet shown or refined, and the
  whiteboard is not yet a part of the site.
- **A real photograph.** Both whiteboards are drawn to order.
- **A whiteboard seen from one side.** These are square on, with a wall round them;
  `tests/test_whiteboard.py` squares one that leans.
- **Anything sent.** looksatwords and qmcp are not reached; `tests/test_notes.py` stands
  in for both.
- **A fit.** `photo fit` reads the words kept here as examples; `tests/test_marks.py`
  fits a table to some.
