"""The router's toolpath, written here from the cuts a part declares.

A part cut on the router says, beside its geometry, the stock it is cut from and
the 2.5D operations that make it: a pocket, a hole, its outline
(``apothecary.cam.models``). This package turns them into GRBL's dialect with one
tool, a depth per pass and the maker's feeds as bounds (``toolpath``), keeps the
file where the router's Cut card keeps one and records what made it (``service``),
and measures where the simulated router's tool went against the design
(``measure``). It is the slicer's analogue on the subtractive side
(``docs/cam.md``); a file a CAM post wrote is still taken as it is.
"""
