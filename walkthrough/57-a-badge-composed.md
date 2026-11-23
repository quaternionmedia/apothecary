# 57 — A badge composed

**Hermetic.** Nothing here runs OpenSCAD or opens a port. This page is run by
`uv run pytest` (the quick loop) and by `apothecary test run`, as a doctest:
every value shown is the value the run computed, and a run that computes
another fails here.

A badge is a face or a word engraved in a plate (`parts/badge`): a face drawn
after its emoji from circles and strokes, which a printer prints and the router
cuts, or a word in a font, which a printer prints. In the page it is composed in
the Badge window and handed to a machine by ⚒ Print or ⚒ Cut, the tour's
*Compose a badge*; this page is the same part at the command line.
[parts/badge/README.md](../parts/badge/README.md) is the part's reference, and
[docs/cam.md](../docs/cam.md) the router's.

## A face or the word: its presets

What the Badge window's buttons choose: six faces and the word. They are the part's
presets too, each its numbers over the part's defaults, which `apothecary parts info
badge` lists.

    >>> from apothecary.projects.parts.badge import DEFAULT, FONTS, PRESETS
    >>> for name, preset in PRESETS.items():
    ...     print(name, "|", preset.label, "|", preset.params)
    open | 😮 Open | {'kind': 'face', 'face': 'open'}
    smile | 🙂 Smile | {'kind': 'face', 'face': 'smile'}
    neutral | 😐 Neutral | {'kind': 'face', 'face': 'neutral'}
    wink | 😉 Wink | {'kind': 'face', 'face': 'wink'}
    frown | 🙁 Frown | {'kind': 'face', 'face': 'frown'}
    grin | 😀 Grin | {'kind': 'face', 'face': 'grin'}
    word | ✎ Word | {'kind': 'word'}

## A face, cut on the router

A face says how it is cut. The 😉: its open eye bored, its smile and its closed
eye each a groove the tool's width, its centre along the stroke, then the face cut
around from outside, through the stock. The stock is the face's square and its
margin, the work zero at its front-left top corner.

    >>> from apothecary.cam import toolpath
    >>> cuts = DEFAULT.cuts(DEFAULT.preset("wink"))
    >>> (cuts.stock.x, cuts.stock.y, cuts.stock.thickness, cuts.tool.diameter)
    (100.0, 100.0, 6.0, 6.0)
    >>> written = toolpath.write(cuts, "badge")
    >>> for op in written.operations:
    ...     print(op.index, "|", op.words, "|", op.passes, "pass" if op.passes == 1 else "passes")
    1 | hole 12 mm at 36,62, 2 deep | 1 pass
    2 | groove of 12 strokes from 31.979,37.381, 2 deep | 1 pass
    3 | groove of 1 stroke from 58,62, 2 deep | 1 pass
    4 | disc 80 mm at 50,50, 6.5 deep | 4 passes
    >>> (written.messages, written.features)
    ([], [])

Nothing is named to measure: a badge is no calibration piece, and a groove is the
tool's width whatever the router's allowance ([page 56](56-a-router-calibrated-by-a-face.md)
is the one that is). A stroke on the router is its tool's width, so a face
composed with thinner strokes, for a printer, is refused there:

    >>> DEFAULT.cuts({"face": "smile", "stroke": 3})
    Traceback (most recent call last):
    apothecary.projects.parts.badge.Refused: a face's strokes are 3 mm wide and the router cuts them its 6 mm tool's width: stroke 6 to cut it

## A word, printed

A word is drawn in one of OpenSCAD's own fonts, which its manual says it
includes, so it draws the same wherever the part renders:

    >>> FONTS
    ('Liberation Sans:style=Bold', 'Liberation Sans', 'Liberation Serif:style=Bold', 'Liberation Serif:style=Italic', 'Liberation Mono:style=Bold')
    >>> word = DEFAULT.validate_overrides({**DEFAULT.preset("word"), "text": "HI MOM"})
    >>> word
    {'kind': 'word', 'text': 'HI MOM'}
    >>> DEFAULT.get_bounds(word).max_point
    Vector3D(x=120.0, y=40.0, z=6.0)

Its letters are a font's outlines, which the router's one end mill cannot follow,
so the router refuses it, and ⚒ Cut in the Badge window is greyed with the same
words:

    >>> DEFAULT.cuts(word)
    Traceback (most recent call last):
    apothecary.projects.parts.badge.Refused: a word is printed, not cut: its letters are a font's outlines, which the router's one end mill cannot follow -- choose a face to cut, or make the word on a printer

## Who makes it

A printer makes either; a router a face. ⚒ Print and ⚒ Cut take it to the first
machine of each kind that makes it, in whichever site it stands, as ⚒ Make does,
where *Print a part* and *Cut a part* go on:

    >>> from apothecary.machine_plans import kinds_that_make
    >>> kinds_that_make("badge")
    ('printer', 'router')

What this page does not show is the badge drawn: OpenSCAD draws it, and the Badge
window's browser test (`tests/e2e/test_badge.py`) watches the page draw it.
