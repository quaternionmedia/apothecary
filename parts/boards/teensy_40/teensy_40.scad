// Teensy 4.0, from the published card: a 35.56 x 17.78 mm PCB (1.4 x 0.7 in),
// fourteen pins down each long edge at 0.1 in pitch, the micro-USB jack on
// the left short edge, the i.MX RT1062 in the middle, the program button at
// the right. Drawn with its pins pointing down, as it stands on a breadboard.

include <../board_common.scad>

size = [35.56, 17.78];

module teensy_40() {
    pcb(size, col = "darkgreen");
    pins_down(14, [pitch / 2, 1.27]);
    pins_down(14, [pitch / 2, 17.78 - 1.27]);
    micro_usb([-1.5, 17.78 / 2 - 4]);
    chip([10, 10, 1.2], [12, 3.9]);
    button([27, 6]);
    chip([2, 1.2, 0.6], [22, 1.8], "orange");   // the LED
}

// standing on its pins, so the lowest point is the bench (z = 0)
translate([0, 0, 11]) teensy_40();
