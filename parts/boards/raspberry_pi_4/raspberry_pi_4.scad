// Raspberry Pi 4 Model B, from the published mechanical drawing: an 85 x 56 mm
// PCB with four M2.5 holes 3.5 mm in from the edges, the 40-pin GPIO header
// along the back edge, USB-C power, two micro-HDMI and the audio jack along
// the front edge, the two USB stacks and the Ethernet jack on the right edge,
// the SoC in the middle.

include <../board_common.scad>

size = [85, 56];
holes = [[3.5, 3.5], [61.5, 3.5], [3.5, 52.5], [61.5, 52.5]];

module raspberry_pi_4() {
    pcb(size, holes, hole_d = 2.7);
    header(20, [7.1, 56 - 2 * pitch - 1.6], rows = 2);   // GPIO, 2 x 20
    usb_c([7.7, -1.3]);
    micro_usb([22, -1.3], along_y = true);
    micro_usb([35.5, -1.3], along_y = true);
    color("black") translate([50, -2, pcb_t]) cube([6, 12, 6]);        // the audio jack
    usb_a_stack([85 - 17.5 + 2, 1.5]);                                   // USB 2.0, overhanging 2
    usb_a_stack([85 - 17.5 + 2, 18.5]);                                  // USB 3.0
    rj45([85 - 21.5 + 2, 36]);
    chip([15, 15, 1.5], [25, 24], "silver");                             // the BCM2711
    chip([12, 12, 1], [42, 25]);                                         // the RAM
    chip([10, 10, 1], [8, 30], "silver");                                // the wireless module
    header(2, [55, 45], rows = 2, h = 6);                                // PoE
    color("silver") translate([1, 22, -1.5]) cube([12, 12, 1.5]);        // the SD slot, underneath
}

raspberry_pi_4();
