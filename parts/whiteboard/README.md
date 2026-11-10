# Whiteboard

A whiteboard as a workshop model, built in OpenSCAD: a flat panel in a thin
frame with a tray under its lower edge, hung on a wall. The garage hangs it on
its north wall, the node `whiteboard`, where a person at the bench turns to
draw.

It is what a drawing is made on and what a photograph of one is squared to
(`apothecary photo square`, [docs/pictures.md](../../docs/pictures.md#a-whiteboard-squared)):
`width` and `height` are the writing surface's own, the part of it a photograph
shows inside the frame, so the surface's width is what sizes everything drawn
on it. The frame and the tray stand outside that size.

| Parameter | Is |
|---|---|
| `width` | The writing surface's width, mm |
| `height` | The writing surface's height, mm |
| `frame` | The frame's width round the surface, mm |
| `thickness` | From the wall to the frame's face, mm |
| `tray` | How far the tray stands out from the wall, mm; none at 0 |

Every number here is the model's own: it stands for no maker's product.
