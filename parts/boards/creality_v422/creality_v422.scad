// Creality V4.2.2 mainboard, the 32-bit board in an Ender 3's electronics
// box: a 102 x 74 mm PCB (the published footprint) with four TMC2208 stepper
// drivers under heatsinks, the STM32 MCU, the 24 V input and heater screw
// terminals along one edge, the endstop and fan headers along another, the
// SD card slot and the micro-USB jack at the front. The node a printer's
// serial port is pinned to.

include <../board_common.scad>

size = [102, 74];
holes = [[4, 4], [98, 4], [4, 70], [98, 70]];

module creality_v422() {
    pcb(size, holes, hole_d = 3.2, col = "midnightblue");
    for (i = [0 : 3]) heatsink([12 + i * 16, 42]);            // X, Y, Z, E drivers
    chip([10, 10, 1.5], [78, 44], "dimgray");                   // the STM32
    screw_terminal(2, [4, 66]);                                 // 24 V in
    screw_terminal(2, [18, 66]);                                // bed
    screw_terminal(2, [32, 66]);                                // hotend
    for (i = [0 : 3]) jst(4, [12 + i * 16, 30]);               // the steppers
    for (i = [0 : 2]) jst(3, [4, 8 + i * 8], along_y = false);  // endstops
    for (i = [0 : 1]) jst(2, [30 + i * 10, 8]);                // fans
    jst(2, [52, 8]); jst(2, [62, 8]);                          // thermistors
    sd_slot([72, 2]);
    micro_usb([96, 12], along_y = false);
    color("silver") translate([40, 20, pcb_t]) cube([14, 8, 6]);   // the buzzer
}

creality_v422();
