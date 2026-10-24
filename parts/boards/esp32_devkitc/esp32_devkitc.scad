// ESP32-DevKitC V4, from Espressif's published drawing: a 55 x 28 mm PCB, the
// ESP32-WROOM-32 module (18 x 25.5 mm, its antenna at the board's left end),
// two rows of nineteen pins at 0.1 in pitch, the micro-USB jack at the right
// end with the EN and BOOT buttons either side of it, the CP2102 bridge
// behind it. Drawn with its pins pointing down, as it stands on a breadboard
// -- and as the esp32_blink devkit stands on the garage bench.

include <../board_common.scad>

size = [55, 28];

module esp32_devkitc() {
    pcb(size, col = "black");
    // the module, its can and its antenna
    color("silver") translate([6, 5, pcb_t]) cube([19.5, 18, 3.1]);
    color("black") translate([0, 5, pcb_t]) cube([6, 18, 0.8]);
    pins_down(19, [6.35 + pitch / 2 - 1.27, 1.27]);
    pins_down(19, [6.35 + pitch / 2 - 1.27, 28 - 1.27]);
    micro_usb([55 - 5, 28 / 2 - 4]);
    button([46, 2]);
    button([46, 20]);
    chip([5, 5, 1], [40, 11.5]);          // the CP2102
    chip([3, 3, 1], [33, 12], "dimgray"); // the LDO
    chip([1.6, 0.8, 0.6], [30, 24], "red"); // the power LED
}

// standing on its pins, so the lowest point is the bench (z = 0)
translate([0, 0, 11]) esp32_devkitc();
