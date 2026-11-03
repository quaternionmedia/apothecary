# AnoleX 4060-Evo Ultra 2

An AnoleX 4060-Evo Ultra 2, a desktop CNC router, as a workshop model, built
in OpenSCAD from published dimensions: a moving-gantry machine cutting
400 x 600 x 80 mm, HGH15 linear rails and 1204 ball screws on each axis,
NEMA 23 closed-loop steppers, an 800 W trim router in a 65 mm clamp on the
Z plate, the control box at the back of the base. The axes (`x_axis`,
`y_axis`, `z_axis`) are parameters, so the garage draws its router,
cnc_router, with its tool where the last poll said.

`anolex_4060_evo_ultra_2.scad` says which numbers are the maker's
specifications and which are taken from its listed footprint or chosen to
look right: the maker lists the 4030's footprint and no overall size for the
4060, so the frame is sized to carry the 4060's travel. It contains no one
else's mesh: the model is this repository's own, MIT.

The machine's controller runs Grbl_ESP32 (it reports as GRBL 1.3a) and
speaks GRBL's G-code over USB; the garage pins its port to the controller
inside the control box, `cnc_router.frame_system.controller`.
[docs/cnc.md](../../docs/cnc.md) says what Apothecary does with it.
