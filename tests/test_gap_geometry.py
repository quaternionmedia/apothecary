"""The gap between two bodies when it is not one number (``apothecary.gap_geometry``).

Each case has an answer known without this module: two concentric circles have one gap
all round; an eccentric circle's gap is a closed form along a ray and another to the
nearest point; a circle rolling inside another without slip moves its contact once
round the bore and R/r times round itself, the same distance along each; a cam sweeps
the bore and stands still on itself. Polygons stand in for the circles, so each answer
is held to within the polygon's sagitta, which is computed, not guessed.
"""

from __future__ import annotations

import math

import pytest

from apothecary.gap_geometry import (
    KINDS,
    ROCKING,
    ROLLING,
    SLIPPING,
    STANDING,
    STILL,
    SWEEPING,
    UNIFORM,
    Pose,
    approach,
    area,
    circle,
    clearance,
    clearance_in,
    contained,
    crosses,
    follow,
    inside,
    overlaps,
    radial_gap,
    sagitta,
    separation,
    wrap,
)

R, r = 30.0, 27.0


def _mean_root(k: float, terms: int = 40) -> float:
    """The mean over a turn of sqrt(1 - k^2 sin^2 phi): (2/pi) E(k), by its series."""
    total, c = 1.0, 1.0
    for n in range(1, terms):
        c *= (2 * n - 1) / (2 * n)
        total -= c * c * k ** (2 * n) / (2 * n - 1)
    return total


def _orbit(e: float, turn_per_degree: float, step: int = 5):
    """Poses of a body whose centre goes once round the axis at radius ``e``, turning
    ``turn_per_degree`` of its own for each degree of the orbit; the end included."""
    return [
        Pose(e * math.cos(math.radians(a)), e * math.sin(math.radians(a)), a * turn_per_degree)
        for a in range(0, 361, step)
    ]


class TestTheShapes:
    def test_a_pose_places_a_point_and_local_takes_it_back(self):
        pose = Pose(3.0, -2.0, 37.0)
        point = (1.25, 4.5)
        placed = pose.place([point])[0]
        assert pose.local(placed) == pytest.approx(point, abs=1e-12)
        assert Pose(0, 0, 90).place([(1.0, 0.0)])[0] == pytest.approx((0.0, 1.0), abs=1e-12)

    def test_a_polygon_circles_area_is_its_n_triangles(self):
        n = 90
        assert area(circle(r, n)) == pytest.approx(n / 2 * r * r * math.sin(2 * math.pi / n))
        assert sagitta(r, n) == pytest.approx(r * (1 - math.cos(math.pi / n)))

    def test_wrap_takes_an_angle_into_a_half_turn_either_way(self):
        assert wrap(190) == -170 and wrap(-190) == 170 and wrap(180) == 180 and wrap(720) == 0

    def test_two_bars_crossing_overlap_with_no_corner_inside_the_other(self):
        across = [(-5.0, -1.0), (5.0, -1.0), (5.0, 1.0), (-5.0, 1.0)]
        upright = [(-1.0, -5.0), (1.0, -5.0), (1.0, 5.0), (-1.0, 5.0)]
        assert not any(inside(p, upright) for p in across)
        assert not any(inside(p, across) for p in upright)
        assert crosses(across, upright) and overlaps(across, upright)
        assert separation(across, upright) < 0

    def test_two_squares_apart_are_their_gap_apart(self):
        a = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]
        b = [(x + 3.5, y + 0.5) for x, y in a]
        assert not overlaps(a, b)
        assert separation(a, b) == pytest.approx(2.5)

    def test_a_body_in_a_cavity_clears_its_walls_and_one_through_them_does_not(self):
        bore = circle(R, 120)
        assert contained(circle(r, 120), bore)
        assert clearance_in(circle(r, 120), bore) == pytest.approx(
            (R - r) * math.cos(math.pi / 120)
        )
        poking = Pose(R - r + 0.5, 0.0).place(circle(r, 120))
        assert not contained(poking, bore) and clearance_in(poking, bore) < 0


class TestOneGapAllRound:
    def test_two_concentric_circles_have_one_gap_and_no_closest_place(self):
        n = 360
        bore, rotor = circle(R, n), circle(r, n)
        # Corner to corner the polygons stand R - r apart: along each ray, and from each
        # corner of the bore to the rotor's corner facing it. From a corner of the rotor
        # the bore's two edges either side are nearer, by the factor cos(pi/n).
        radial = radial_gap(bore, rotor, n)
        assert radial.minimum == pytest.approx(R - r) and radial.is_uniform(1e-9)
        near = clearance(bore, rotor)
        assert near.is_uniform(1e-9) and near.minimum == pytest.approx(R - r)
        tol = (R - r) * (1 - math.cos(math.pi / n)) + 1e-12
        assert approach(bore, rotor, Pose(0, 0, 17.0), tol=tol) is None
        assert approach(bore, rotor, Pose(0, 0, 17.0), tol=tol / 2) is not None
        spun = follow(bore, rotor, [Pose(0, 0, a) for a in range(0, 361, 30)], tol=tol)
        assert spun.kind == UNIFORM and all(g is None for g in spun.gaps)


def test_a_ray_along_an_edge_meets_the_boundary_where_that_edge_begins():
    """A post's flank runs along a ray from the axis; that ray meets the free space's
    boundary at the post's tip, where the flank begins, and nowhere nearer. The post
    stands from 208 to 238 degrees, its tip on a circle of 14, in a ring of 34: arcs
    sampled as a part's SCAD samples them, so the flank's two ends are on the ray only
    to within rounding."""

    def arc(radius, a0, a1, facets=180):
        n = max(1, math.ceil(abs(a1 - a0) * facets / 360))
        return [
            (
                radius * math.cos(math.radians(a0 + (a1 - a0) * i / n)),
                radius * math.sin(math.radians(a0 + (a1 - a0) * i / n)),
            )
            for i in range(n + 1)
        ]

    cavity = arc(14.0, 208, 238) + arc(34.0, 238, 208 + 360)
    g = radial_gap(cavity, circle(10.0, 360), 360)
    assert g.gaps[238] == pytest.approx(4.0) and g.gaps[208] == pytest.approx(4.0)
    assert 4.0 - sagitta(14.0, 180) - 1e-9 <= g.minimum <= 4.0
    assert g.maximum == pytest.approx(24.0)


class TestAnEccentricCircle:
    """A rotor of radius r whose centre stands e from the axis, at angle alpha."""

    n = 720
    e = 1.2
    alpha = 40.0

    def rotor(self):
        a = math.radians(self.alpha)
        return Pose(self.e * math.cos(a), self.e * math.sin(a)).place(circle(r, self.n))

    def test_its_radial_gap_is_the_closed_form_along_every_ray(self):
        """g(theta) = R - e cos(phi) - sqrt(r^2 - e^2 sin^2 phi), phi = theta - alpha. The
        rays fall on the bore's corners, which are on the circle; the rotor's polygon
        stands within its sagitta inside its circle, read along a ray that meets it at
        most asin(e / r) off square."""
        g = radial_gap(circle(R, self.n), self.rotor(), 360)
        tol = sagitta(r, self.n) / math.sqrt(1 - (self.e / r) ** 2) + 1e-9
        for theta, got in zip(g.angles, g.gaps, strict=True):
            phi = math.radians(theta - self.alpha)
            want = R - self.e * math.cos(phi) - math.sqrt(r * r - (self.e * math.sin(phi)) ** 2)
            assert -1e-9 <= got - want <= tol
        assert g.where == pytest.approx(self.alpha)
        assert g.minimum == pytest.approx(R - r - self.e, abs=tol)
        assert g.maximum == pytest.approx(R - r + self.e, abs=tol)
        assert g.minima(1e-6) == [pytest.approx(self.alpha)]

    def test_its_mean_radial_gap_is_r_times_an_elliptic_integral_short_of_the_bore(self):
        g = radial_gap(circle(R, self.n), self.rotor(), 360)
        want = R - r * _mean_root(self.e / r)
        assert g.mean == pytest.approx(want, abs=sagitta(r, self.n))

    def test_its_clearance_is_the_distance_to_the_circle_and_never_more_than_the_ray(self):
        """From a point of the bore at theta, the nearest point of the rotor is
        sqrt(R^2 + e^2 - 2 R e cos(phi)) - r away; along the ray it is farther, except
        where the ray runs through the rotor's centre."""
        bore = circle(R, self.n)
        near = clearance(bore, self.rotor())
        radial = radial_gap(bore, self.rotor(), self.n)
        tol = sagitta(r, self.n) + 1e-9
        for theta, got, along in zip(near.angles, near.gaps, radial.gaps, strict=True):
            phi = math.radians(theta - self.alpha)
            want = math.sqrt(R * R + self.e**2 - 2 * R * self.e * math.cos(phi)) - r
            assert -1e-9 <= got - want <= tol
            assert got <= along + 1e-9
        # A quarter turn from the closest approach the two differ by a closed form.
        k = round((self.alpha + 90) / 360 * self.n)
        assert radial.gaps[k] - near.gaps[k] == pytest.approx(
            (R - math.sqrt(r * r - self.e**2)) - (math.sqrt(R * R + self.e**2) - r), abs=tol
        )


class TestWhereTheClosestApproachTravels:
    n = 720
    e = R - r

    def bore(self):
        # Drawn round its circle, as a hole is, so the rolling rotor inside it never
        # pokes through an edge.
        return circle(R / math.cos(math.pi / self.n), self.n)

    def test_a_rotor_rolling_inside_the_bore_rolls_once_round_it_and_r_over_r_round_itself(
        self,
    ):
        """A circle of radius r rolling without slip inside one of radius R = r + e turns
        -e/r of a turn for each orbit of its centre; its contact goes once round the
        bore and R/r times round the rotor, 2 pi R along each."""
        rolled = follow(self.bore(), circle(r, self.n), _orbit(self.e, -self.e / r))
        assert rolled.kind == ROLLING
        assert rolled.turns_outer == pytest.approx(1.0, abs=0.005)
        assert rolled.turns_inner == pytest.approx(R / r, abs=0.005)
        assert rolled.path_outer == pytest.approx(2 * math.pi * R, rel=0.005)
        assert rolled.path_inner == pytest.approx(2 * math.pi * R, rel=0.005)
        assert max(rolled.gaps) <= sagitta(R, self.n) * 2  # touching all the way round

    def test_an_orbit_that_does_not_turn_slips_by_the_difference_of_the_circumferences(self):
        orbited = follow(self.bore(), circle(r, self.n), _orbit(self.e, 0.0))
        assert orbited.kind == SLIPPING
        assert orbited.turns_outer == pytest.approx(1.0, abs=0.005)
        assert orbited.turns_inner == pytest.approx(1.0, abs=0.005)
        assert orbited.slip == pytest.approx(2 * math.pi * self.e, rel=0.02)

    def test_a_cam_sweeps_the_bore_and_stands_still_on_itself(self):
        """An eccentric turning rigidly about the axis: the airgap part's offset rotor."""
        n = 240
        cam = follow(circle(R, n), circle(r - 1, n), _orbit(self.e, 1.0, step=10))
        assert cam.kind == SWEEPING
        assert cam.turns_outer == pytest.approx(1.0) and cam.turns_inner == pytest.approx(0.0)

    def test_a_rotor_turning_on_its_own_offset_centre_stands_on_the_bore(self):
        n = 240
        spun = follow(
            circle(R, n),
            circle(r - 1, n),
            [Pose(self.e, 0.0, a) for a in range(0, 361, 10)],
        )
        assert spun.kind == STANDING
        assert spun.turns_outer == pytest.approx(0.0, abs=0.01)
        assert spun.turns_inner == pytest.approx(-1.0, abs=0.01)

    def test_an_eccentric_swung_back_and_forth_rocks(self):
        n = 240
        swing = [a for a in range(-10, 11, 2)] + [a for a in range(8, -11, -2)]
        rocked = follow(
            circle(R, n),
            circle(r - 1, n),
            [
                Pose(self.e * math.cos(math.radians(a)), self.e * math.sin(math.radians(a)), a)
                for a in swing
            ],
        )
        assert rocked.kind == ROCKING
        assert rocked.path_outer > 0 and abs(rocked.travel_outer) < 1.0

    def test_a_stator_carried_round_with_its_rotor_keeps_the_approach_still(self):
        """When what stands still moves too -- the whole machine turned -- only the poses
        between the two count."""
        n = 240
        turns = range(0, 361, 30)
        off = 0.37  # off the polygons' corners, so no two pairs of points tie for closest
        both = follow(
            circle(R, n),
            circle(r - 1, n),
            [
                Pose(
                    self.e * math.cos(math.radians(a + off)),
                    self.e * math.sin(math.radians(a + off)),
                    a,
                )
                for a in turns
            ],
            outer_poses=[Pose(0.0, 0.0, a) for a in turns],
        )
        assert both.kind == STILL and both.path_outer == pytest.approx(0.0, abs=1e-9)

    def test_an_ellipse_in_a_round_bore_comes_closest_at_both_ends(self):
        n = 360
        ellipse = [
            (28.0 * math.cos(math.radians(360 * k / n)), 22.0 * math.sin(math.radians(360 * k / n)))
            for k in range(n)
        ]
        near = clearance(circle(R, n), ellipse)
        assert near.minima(1e-6) == [pytest.approx(0.0), pytest.approx(180.0)]


def test_every_kind_says_what_it_means():
    assert set(KINDS) == {UNIFORM, STILL, ROCKING, SWEEPING, STANDING, ROLLING, SLIPPING}
    assert all(KINDS[k] for k in KINDS)
