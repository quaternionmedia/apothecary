"""One plane onto another by four points (apothecary/homography.py): each point lands on
its partner, the mapping goes back, two compose, and four points with three on a line
are refused, saying which three."""

from __future__ import annotations

import pytest

from apothecary import homography as h
from apothecary.rig import panels
from apothecary.vision import projection

SQUARE = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]
LEANING = [(120.0, 80.0), (1700.0, 140.0), (1620.0, 1000.0), (180.0, 940.0)]


def test_each_of_four_points_lands_on_its_partner_and_comes_back():
    onto = h.homography(SQUARE, LEANING)
    for (x, y), (u, v) in zip(SQUARE, LEANING, strict=True):
        assert h.apply(onto, x, y) == pytest.approx((u, v))
    back = h.invert(onto)
    for u, v in LEANING:
        assert h.apply(back, *h.apply(onto, *h.apply(back, u, v))) == pytest.approx(
            h.apply(back, u, v)
        )
    assert h.apply(back, *h.apply(onto, 0.3, 0.8)) == pytest.approx((0.3, 0.8))


def test_two_mappings_compose_inner_first():
    onto = h.homography(SQUARE, LEANING)
    double = ((2.0, 0.0, 0.0), (0.0, 2.0, 0.0), (0.0, 0.0, 1.0))
    both = h.compose(onto, double)
    assert h.apply(both, 0.25, 0.5) == pytest.approx(h.apply(onto, 0.5, 1.0))


@pytest.mark.parametrize(
    "points, three",
    [
        ([(0, 0), (1, 1), (2, 2), (0, 5)], "points 1, 2 and 3"),
        ([(0, 0), (5, 1), (1, 0), (3, 0)], "points 1, 3 and 4"),
        ([(0, 0), (0, 0), (4, 0), (0, 4)], "points 1, 2 and 3"),
    ],
)
def test_three_points_on_a_line_are_refused_saying_which(points, three):
    assert h.on_one_line(points) is not None
    with pytest.raises(h.Degenerate, match=f"{three} of the four onto lie on one line"):
        h.homography(SQUARE, points)
    with pytest.raises(h.Degenerate, match=f"{three} of the four from lie on one line"):
        h.homography(points, SQUARE)


def test_a_mapping_that_flattens_the_plane_has_no_way_back():
    with pytest.raises(h.Degenerate, match="no way back"):
        h.invert(((1.0, 2.0, 0.0), (2.0, 4.0, 0.0), (0.0, 0.0, 1.0)))


def test_the_rig_and_the_pictures_take_the_one_mapping():
    """A face onto a picture, and the types a picture's mapping is written in, are
    the shared module's: one mapping, not a copy beside each reader."""
    assert panels.face_onto(LEANING) == h.homography(projection.CORNERS, LEANING)
    assert (panels.apply, panels.invert, panels.compose) == (h.apply, h.invert, h.compose)
    assert projection.Matrix is h.Matrix
