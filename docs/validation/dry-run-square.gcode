; Apothecary bench dry run: a 60 mm square traced 10 mm above the bed.
; Nothing heats and nothing extrudes -- this file exists to watch a print
; stream from the host: the head moves, the position card follows, Pause
; stops the feed, Cancel sends the safe-off. The dwells give a pause
; something to interrupt. Home first; the printer must be clear.
G90            ; absolute
G28            ; home all (EZABL probes Z at the centre)
G1 Z10 F600    ; well clear of the bed
G1 X80 Y80 F3000
G4 P500
G1 X140 Y80 F1800
G4 P500
G1 X140 Y140 F1800
G4 P500
G1 X80 Y140 F1800
G4 P500
G1 X80 Y80 F1800
G4 P500
G1 X140 Y140 F1800  ; a diagonal, so the square is not mistaken for a jog
G4 P500
G1 X80 Y140 F1800
G4 P500
G1 X140 Y80 F1800
G4 P500
G1 X110 Y110 F3000  ; centre
G1 Z20 F600
M117 dry run done
M84            ; motors free
