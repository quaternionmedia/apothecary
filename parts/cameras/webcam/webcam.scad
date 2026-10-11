// A bare webcam: a body and its lens, nothing to stand it on. Drawn looking
// straight down, as a camera added to a site first stands: the middle of the
// lens's front face is the origin, at z = 0, and the body is above it. Its
// long side runs across the picture it takes (+x); the picture's top is +y.
// A camera in a site is this, tilted from straight down about its long side
// and turned about the vertical (apothecary/vision/cameras.py).

body = [90, 30, 30];   // across the picture, up the picture, lens to back
lens_d = 16;           // the lens's diameter
lens_h = 4;            // how far the lens stands out of the body

module webcam() {
    color("dimgray") translate([-body[0] / 2, -body[1] / 2, lens_h]) cube(body);
    color("black") cylinder(d = lens_d, h = lens_h, $fn = 48);
}

webcam();
