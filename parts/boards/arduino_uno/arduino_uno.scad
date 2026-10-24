// Arduino Uno R3, from the published board drawing: a 68.58 x 53.34 mm PCB
// (2.7 x 2.1 in) with four mounting holes, the USB-B jack and the barrel jack
// on the left edge, the digital headers along the back edge, the power and
// analog headers along the front, the ATmega328P in its DIP socket, the ICSP
// header at the right edge. Hole positions are the standard ones every Uno
// shield and case is made to.

include <../board_common.scad>

size = [68.58, 53.34];
holes = [[13.97, 2.54], [15.24, 50.8], [66.04, 7.62], [66.04, 35.56]];

module arduino_uno() {
    pcb(size, holes, col = "teal");
    usb_b([-6.5, 31.75]);          // overhangs the left edge by 6.5
    barrel_jack([-2, 3]);
    header(10, [17.53, 50.8 - pitch]);      // D8..D13, GND, AREF, SDA, SCL
    header(8, [43.18, 50.8 - pitch]);       // D0..D7
    header(8, [24.13, 0]);                  // power
    header(6, [47.75, 0]);                  // A0..A5
    chip([35.5, 7.6, 4], [27, 13.5]);       // the ATmega328P, DIP-28, in its socket
    chip([7, 7, 1.5], [48, 44], "dimgray"); // the ATmega16U2 (USB)
    header(3, [61, 22], along_y = true, rows = 2, h = 8);   // ICSP
    button([50, 45.5]);
    crystal([37, 5]);
}

arduino_uno();
