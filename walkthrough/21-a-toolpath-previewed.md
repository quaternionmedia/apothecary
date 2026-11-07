# 21 — A toolpath, previewed

**Hermetic.** Everything here reads text; nothing opens a port or a browser.

A print and a cut are the same thing to look at before it runs: where the tool goes,
in what order, and what each move does. So there is one core, `apothecary/preview`, and
two instantiations of it. [docs/toolpath-preview.md](../docs/toolpath-preview.md) is the
reference; `tests/e2e/test_toolpath_preview.py` runs the page's side on both machines, and
[page 24](24-a-cut-from-the-card.md) pictures it on the router's Cut card.

## One interpreter

`moves.read` turns a G-code file's lines into moves, whichever machine it is for. It
knows absolute and relative moves, inches, words written with no space, a motion word
carried over from the line before, and arcs, written as chords.

    >>> from apothecary.preview.moves import Move, read
    >>> lines = ["G20", "G1X1F10", "Y1", "G21", "G0 Z5"]
    >>> [m.end for m in read(lines) if isinstance(m, Move)]
    [(25.4, 0.0, 0.0), (25.4, 25.4, 0.0), (25.4, 25.4, 5.0)]

It says nothing of what a move means. That is the process's, and it is all that differs.

    >>> from apothecary.preview import ADDITIVE, SUBTRACTIVE, of
    >>> file = ["G0 X10", "G1 Z-1 F300", "G1 X20 F800"]
    >>> a, s = of(file, ADDITIVE), of(file, SUBTRACTIVE)
    >>> a.points == s.points
    True
    >>> [a.kinds[k] for k in a.kind_of]
    ['travel', 'travel', 'travel']
    >>> [s.kinds[k] for k in s.kind_of]
    ['rapid', 'plunge', 'cut']

## A print

A printer's file lays material on some moves and travels on the rest. Its moves group
into layers, by its slicer's marks where it writes them.

    >>> gcode = '''M83
    ... ;LAYER_CHANGE
    ... G1 Z0.2 F600
    ... G1 X105 Y105 F3000
    ... G1 X115 Y105 E0.5
    ... G1 X115 Y115 E0.5
    ... ;LAYER_CHANGE
    ... G1 Z0.4 F600
    ... G1 X115 Y105 E0.5
    ... G1 X5 Y176 F3000
    ... M84 X Y E
    ... '''
    >>> p = of(gcode.splitlines(), ADDITIVE)
    >>> p.word, [(g.label, g.z) for g in p.groups]
    ('layer', [('layer 1', 0.2), ('layer 2', 0.4)])
    >>> p.length_mm["extrude"], p.bounds["extrude"].max
    (30.0, [115.0, 115.0, 0.4])

## A cut

A router's file rapids, plunges and cuts. The toolpath the app writes
(`apothecary.cam`) names each pass on the line before it, so the preview says them in its
words.

    >>> from apothecary.cam import toolpath
    >>> from apothecary.projects.parts.router_coupon import DEFAULT as coupon
    >>> written = toolpath.write(coupon.cuts(), "router_coupon")
    >>> c = of(written.lines, SUBTRACTIVE)
    >>> c.word, c.groups[1].label
    ('pass', 'op 1/4 pass 1/2: pocket 40 x 30 at 30,35 to z -2')
    >>> c.bounds["plunge"].min[2]
    -10.5

The writer counted its moves as it wrote them, and the interpreter reads them back from
the text, neither knowing the other. They agree.

    >>> round(c.length_mm["cut"] + c.length_mm["plunge"], 1) == written.length_mm
    True
    >>> c.length_mm["rapid"] == written.rapid_mm, c.time_s == written.time_s
    (True, True)

A CAM post's file names no operations, and is grouped by the depths it plunges to.

    >>> post = ["G0 X1", "G1 Z-1 F100", "G1 X9 F800", "G0 Z5", "G0 X1", "G1 Z-2", "G1 X9"]
    >>> [g.label for g in of(post, SUBTRACTIVE).groups]
    ['before the first pass', 'depth -1', 'depth -2']

## What a design change does to it

The coupon's holes are smaller than the tool and can only be plunged. Wider than the
tool they are bored in circles, and the preview has the moves to show it.

    >>> from apothecary.projects.parts.router_coupon import Params
    >>> wider = of(toolpath.write(coupon.cuts(Params(hole_diameter=8).model_dump())).lines, SUBTRACTIVE)
    >>> c.moves, wider.moves
    (97, 529)

## In the page

The Print and Cut card has one slider. At the left it is off, and nothing has been asked
of the server. Moved off the left, the chosen file's path is drawn in the world on its
machine: what makes the part in colour, moves through the air dim, through each layer or
pass, all of it at the right. A printer's file stands at its bed. A router's stands at its
work zero, and moves with it, so a zero set in the wrong place shows before the cut does.
