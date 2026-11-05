# Router coupon

A plate with a rectangular pocket and a column of holes: the first part cut on
the garage's router, and the part walkthrough 20 takes through the subtractive
loop, design to monitoring. Every size is a parameter, so a coupon is as big as
the stock to hand.

`router_coupon.scad` draws the plate the cuts leave. The wrapper,
`apothecary/projects/parts/router_coupon.py`, says the cuts that make it from
its stock: the pocket cleared first, the holes bored through, the outline cut
around last; the stock is the plate plus `stock_margin` on every side, and the
work zero is the stock's front-left top corner. The router's toolpath is written
from that ([docs/cam.md](../../docs/cam.md)).

The holes are 3 mm by default, smaller than the 6 mm end mill the toolpath
uses: the toolpath says so and bores them to the tool. That is the fact a cut
gives back to the design, and the change the walkthrough makes.
