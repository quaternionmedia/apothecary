; Apothecary bench dry run for the router: a 60 mm square traced 10 mm above
; the work zero, the spindle off. This file exists to watch a cut stream from
; the host: the tool moves, the position card follows, Pause holds the
; controller, Cancel holds and resets it. The dwells (seconds, in GRBL's G4)
; give a pause something to interrupt. Zero the tool on the table first (XYZ
; zero here), with nothing in the collet; the table must be clear.
G21 G90        ; millimetres, absolute
G0 Z10         ; well clear of the table
G0 X0 Y0
G1 X60 F800
G4 P0.5
G1 Y60
G4 P0.5
G1 X0
G4 P0.5
G1 Y0
G0 Z10
M30
