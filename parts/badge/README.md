# Badge

A face or a word engraved in a plate, composed in the page's Badge window. A
face is drawn after its emoji -- 😮 open, 🙂 smile, 😐 neutral, 😉 wink, 🙁
frown, 😀 grin -- from circles and strokes: its eyes and an open mouth round
holes, a smile, a frown, a line or a winking eye a stroke as wide as `stroke`.
A word is drawn in a font's outlines, `text` in `font`, one of OpenSCAD's own
Liberation family, on a rounded plate `width` by `height`. Either is engraved
`depth` into a plate `thickness` thick.

In the page the Badge window composes it: a face picked, or the word typed
and its font chosen, and ⚒ Print or ⚒ Cut; on the badge's ring, Part › View ›
Badge. The faces and the word are also the part's presets, each its numbers
over the part's defaults, which `apothecary parts info badge` lists.

A face is printed, or cut on the router. The wrapper,
`apothecary/projects/parts/badge.py`, places every eye, mouth and stroke as
`badge.scad` does, as shares of the face's radius, and says the cuts that
make it from its stock: the eyes and an open mouth bored to the depth, each
stroke a groove its centre runs along, then the face cut around, through. A
stroke on the router is its 6 mm tool's width, so a `stroke` of any other
width is refused there. The stock is the face's square plus `stock_margin`
on every side, its front-left top corner the work zero.

A word is printed alone: its letters are a font's outlines, which the
router's one end mill cannot follow, and its toolpath is refused, saying so.

[Walkthrough page 57](../../walkthrough/57-a-badge-composed.md) composes one at
the command line; the tour's *Compose a badge* in the page.
