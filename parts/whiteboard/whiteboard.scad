// A whiteboard, as a workshop model: a flat panel in a thin frame with a tray
// under its lower edge, hung on a wall. What a person draws on, and what the
// outline finder reads a photograph of (docs/pictures.md).
//
// The origin is the lower-left corner as a person facing it sees it, at the
// front of its tray; X runs along the wall, Y runs back to the wall it hangs
// on, Z runs up. Its back, the face it hangs by, is at its greatest Y: it hangs
// on a wall whose inner face looks toward -Y, and its writing surface looks the
// same way, toward a person in the room.
//
// The size is the panel's own writing surface, the part a photograph is
// squared to; the frame and the tray stand outside it.

// Customizer parameters
width = 1200;    // [300:50:3000] The writing surface's width (mm): what sizes a photograph squared to it
height = 900;    // [200:50:1500] The writing surface's height (mm)
frame = 15;      // [5:1:40] The frame's width round the surface (mm)
thickness = 20;  // [8:1:40] From the wall to the frame's face (mm)
tray = 60;       // [0:5:120] How far the tray stands out from the wall (mm); 0 draws none

/* [Hidden] */
eps = 0.5;   // how far a part sinks into what it stands on, so the union is one closed mesh

depth = max(thickness, tray);   // from the front of the tray to the wall

// the frame against the wall, with the surface set a little back in its front
color("#b8bcc2") difference() {
    translate([0, depth - thickness, 0]) cube([width + 2 * frame, thickness, height + 2 * frame]);
    translate([frame, depth - thickness - eps, frame]) cube([width, 4 + eps, height]);
}
// the writing surface
color("#f2f2ee") translate([frame, depth - thickness + 2 + eps, frame]) cube([width, 2, height]);
// the tray under the lower edge, the width of the surface, out into the room
if (tray > 0)
    color("#b8bcc2") translate([frame, depth - tray, 0]) cube([width, tray, frame * 0.6]);
