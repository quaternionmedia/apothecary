# Boards

Development boards and controllers, each drawn in OpenSCAD from its maker's
published drawing -- the PCB outline, the mounting holes, the headers and
jacks where a case or a shield expects them -- so a site can show the board
that is on the bench, and a bench can be laid out around it.

| Part | What it is | Size (PCB) |
|---|---|---|
| `arduino_uno` | Arduino Uno R3 | 68.58 x 53.34 mm |
| `raspberry_pi_4` | Raspberry Pi 4 Model B | 85 x 56 mm |
| `teensy_40` | Teensy 4.0, standing on its pins | 35.56 x 17.78 mm |
| `esp32_devkitc` | ESP32-DevKitC V4, standing on its pins | 55 x 28 mm |
| `creality_v422` | Creality V4.2.2 printer mainboard | 102 x 74 mm |

Every board's origin is its PCB's front-left bottom corner, lying flat on
z = 0 (a board standing on its pins is lifted so the pin tips are at z = 0),
X to the right, Y back, Z up. `board_common.scad` holds what they are made
of (a PCB with holes, headers, chips, jacks); it is a library, not a part.

Each board is described by a `part.json` beside its SCAD rather than a
Python wrapper -- see `docs/geometry-from-elsewhere.md`. No mesh of anyone
else's went into them; the dimensions are the specifications the makers
publish so that things can be made to fit.
