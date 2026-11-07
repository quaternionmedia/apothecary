// The controller board in an AnoleX 4060-Evo Ultra 2's control box: an ESP32
// running Grbl_ESP32 (it reports as Grbl 1.3a) behind a CH340 USB bridge,
// which is what the bench saw of it. The maker publishes no drawing of the
// board, so the rest is assumed, and README.md beside this file says which:
// a 100 x 80 mm PCB with four mounting holes, the ESP32-WROOM-32 module with
// its antenna at the left edge, the USB-B jack at the back edge with the CH340
// beside it, the 24 V input and the spindle's screw terminals along the same
// edge, three driver headers along the front (X, Y, Z: the closed-loop NEMA 23
// steppers have drivers of their own, so the board sends step and direction),
// the limit switch and probe headers beside them, the SD slot (ESP3D's) at the
// right edge, the spindle relay and a reset button. The node a router's serial
// port is pinned to.

include <../board_common.scad>

size = [100, 80];   // assumed: a board of this kind, standing in a 200 x 100 mm control box
holes = [[4, 4], [96, 4], [4, 76], [96, 76]];

module anolex_grbl_esp32() {
    pcb(size, holes, hole_d = 3.2, col = "darkgreen");
    // the ESP32-WROOM-32 module, its can and its antenna, at the left edge
    color("black") translate([0, 31, pcb_t]) cube([6, 18, 0.8]);
    color("silver") translate([6, 31, pcb_t]) cube([19.5, 18, 3.1]);
    // the USB-B jack at the back edge, its face to the rear as the box's socket is
    color("silver") translate([40, 64, pcb_t]) cube([12, 16, 11]);
    chip([5, 5, 1], [30, 66]);                                  // the CH340
    screw_terminal(2, [58, 72]);                                // 24 V in
    screw_terminal(2, [72, 72]);                                // the spindle
    chip([15, 10, 10.5], [60, 44], "midnightblue");             // the spindle relay
    for (i = [0 : 2]) jst(4, [8 + i * 14, 8]);                  // X, Y, Z: step and direction to the drivers
    for (i = [0 : 2]) jst(3, [52 + i * 12, 8]);                 // the limit switches
    jst(2, [88, 8]);                                            // the probe
    sd_slot([74, 36]);
    button([88, 24]);                                           // reset
    chip([3, 3, 1], [40, 40], "dimgray");                       // the LDO
    chip([1.6, 0.8, 0.6], [28, 56], "red");                     // the power LED
}

anolex_grbl_esp32();
