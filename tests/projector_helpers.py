"""What the projector's tests share: an output, four lit pixels, and a pinhole projector
whose pixels are worked out from ray geometry apart from the code under test."""

import math

from apothecary import projector

VOLUME = [220.0, 220.0, 250.0]
OUTPUT = (1920, 1080)
LIT = [(400.0, 900.0), (1500.0, 880.0), (1400.0, 200.0), (500.0, 220.0)]


class Pinhole:
    """A projector's lens at ``eye`` in the room, aimed at ``target``: a point (x, y, z) of
    the room lands at the pixel its ray through the lens meets the output, worked out from
    the geometry, never from a mapping the code under test returns."""

    def __init__(self, eye=(150.0, -420.0, 1800.0), target=(110.0, 110.0, 0.0), focal=2600.0):
        def sub(a, b):
            return [p - q for p, q in zip(a, b, strict=True)]

        def unit(a):
            n = math.sqrt(sum(v * v for v in a))
            return [v / n for v in a]

        def cross(a, b):
            return [
                a[1] * b[2] - a[2] * b[1],
                a[2] * b[0] - a[0] * b[2],
                a[0] * b[1] - a[1] * b[0],
            ]

        self.eye, self.focal = eye, focal
        self.forward = unit(sub(target, eye))
        self.right = unit(cross(self.forward, [0.0, 1.0, 0.0]))
        self.down = cross(self.forward, self.right)

    def pixel(self, x, y, z=0.0):
        d = [x - self.eye[0], y - self.eye[1], z - self.eye[2]]
        along = sum(a * b for a, b in zip(d, self.forward, strict=True))
        across = sum(a * b for a, b in zip(d, self.right, strict=True))
        down = sum(a * b for a, b in zip(d, self.down, strict=True))
        return (960 + self.focal * across / along, 540 + self.focal * down / along)

    def calibration(self, height=None, offset=0.0, bed=None, **noise):
        marked = projector.starting_points(VOLUME) if bed is None else bed
        lit = [self.pixel(x, y + offset) for x, y in marked]
        first = projector.checked("garage", "printer_1", marked, lit, OUTPUT, bed_offset=offset)
        if height is None:
            return first
        up = [self.pixel(x, y + offset, height) for x, y in marked]
        return projector.checked_upper(first, up, OUTPUT, height, bed_offset=offset)


PROBES = [(0.0, 0.0), (110.0, 110.0), (220.0, 40.0), (35.0, 200.0), (210.0, 210.0)]
