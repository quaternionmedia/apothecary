# Router emoji

The router's calibration piece, a 😮: a round face with two eyes and an open
mouth, every one of them a circle, so calipers read each across. The face is cut
around from outside, an outside size; the eyes and the mouth are bored inside it,
inside sizes. A tool that cuts wider than its diameter leaves the face small and
the holes big by the same amount; a router whose steps per millimetre are off
leaves them all off in proportion to their size. Measured inside and out, the
two are told apart.

`router_emoji.scad` draws the face the cuts leave. The wrapper,
`apothecary/projects/parts/router_emoji.py`, says the cuts that make it from its
stock -- the eyes and the mouth bored through, then the face cut around -- each
named, so its toolpath's record says what to measure: the `face`, an `eye`, the
`mouth`. The stock is the face's square plus `stock_margin` on every side, and
the work zero is the stock's front-left top corner. The eyes are wider than the
6 mm end mill, so they are bored and measure the tool.

Choose it under *makes* in the router's Cut window, **Toolpath**, and cut it.
At the cut's end its drawer opens in the part's Feedback window (Part ›
Feedback): measure it, type what it measures under *measured*, and **Keep**.
The router keeps the tool allowance it makes, and its next toolpaths take it
([docs/cam.md](../../docs/cam.md#measured-by-hand-fed-back)). The tour's
*Calibrate a router* goes round it a stage at a time.
