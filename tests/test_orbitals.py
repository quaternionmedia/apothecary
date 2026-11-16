"""The orbitals: composition depth, dense shells, radii that keep pieces clear, a point and
an outward turn for each."""

import itertools
import math

import pytest

from apothecary.orbitals import (
    GAP,
    composition_depths,
    dense_shells,
    fibonacci_sphere,
    lay_out,
    outward_turn,
    shell_radii,
    turn_matrix,
    turned,
)


def test_depth_zero_is_built_from_nothing_and_each_level_is_one_more_than_its_deepest():
    depths = composition_depths(
        {"screw": [], "bracket": ["screw"], "arm": ["bracket", "screw"], "rig": ["arm", "screw"]}
    )
    assert depths == {"screw": 0, "bracket": 1, "arm": 2, "rig": 3}


def test_a_child_that_is_not_a_name_given_is_dropped():
    assert composition_depths({"a": ["ghost"], "b": ["a"]}) == {"a": 0, "b": 1}


@pytest.mark.parametrize(
    "children",
    [
        {"a": ["a"]},
        {"a": ["b"], "b": ["a"]},
        {"a": ["b"], "b": ["c"], "c": ["a"], "d": ["a"]},
    ],
)
def test_a_cycle_terminates_and_gives_the_same_depths_every_time(children):
    first = composition_depths(children)
    assert set(first) == set(children)
    assert all(d >= 0 for d in first.values())
    assert composition_depths(dict(reversed(list(children.items())))) == first


def test_shells_are_dense_so_a_depth_nothing_has_leaves_no_empty_shell():
    shells = dense_shells({"a": 0, "b": 3, "c": 3, "d": 7})
    assert shells == {"a": 0, "b": 1, "c": 1, "d": 2}


def test_the_lattice_has_n_points_all_on_the_sphere():
    points = fibonacci_sphere(50, 7.0)
    assert len(points) == 50
    assert all(math.isclose(math.hypot(*p), 7.0) for p in points)
    assert fibonacci_sphere(0, 1.0) == []


def _layout(counts, size=30.0):
    shell_of = {}
    for shell, count in enumerate(counts):
        for i in range(count):
            shell_of[f"s{shell}-{i:03d}"] = shell
    sizes = {name: size + (sum(map(ord, name)) % 7) * 5 for name in shell_of}
    return shell_of, sizes


def test_no_two_pieces_on_a_shell_are_closer_than_their_sizes_allow():
    shell_of, sizes = _layout([40, 25, 9])
    placed = lay_out(shell_of, sizes)
    for a, b in itertools.combinations(placed, 2):
        if placed[a].shell != placed[b].shell:
            continue
        gap = math.dist(placed[a].point, placed[b].point) - sizes[a] - sizes[b]
        assert gap >= GAP - 1e-6, (a, b, gap)


def test_no_piece_overlaps_a_piece_of_any_shell():
    shell_of, sizes = _layout([30, 20, 10, 3])
    placed = lay_out(shell_of, sizes)
    for a, b in itertools.combinations(placed, 2):
        assert math.dist(placed[a].point, placed[b].point) >= sizes[a] + sizes[b] + GAP - 1e-6


def test_radii_strictly_increase_and_each_shell_clears_the_one_inside():
    sizes = [[30.0] * 20, [50.0] * 8, [80.0] * 3, [10.0]]
    radii = shell_radii(sizes)
    assert all(a < b for a, b in zip(radii, radii[1:]))
    for k in range(1, len(radii)):
        assert radii[k] - radii[k - 1] >= max(sizes[k - 1]) + max(sizes[k]) + GAP - 1e-9


def test_a_single_piece_is_off_the_centre_by_its_own_size():
    (radius,) = shell_radii([[40.0]])
    assert radius >= 40.0 + GAP


def test_the_layout_is_deterministic_and_independent_of_the_order_given():
    shell_of, sizes = _layout([12, 6])
    again = lay_out(dict(reversed(list(shell_of.items()))), sizes)
    assert again == lay_out(shell_of, sizes)


def test_adding_a_piece_to_the_outermost_shell_moves_nothing_inside():
    shell_of, sizes = _layout([12, 6, 4])
    before = lay_out(shell_of, sizes)
    more = {**shell_of, "site-new": 2}
    placed = lay_out(more, {**sizes, "site-new": 120.0})
    for name, where in before.items():
        if where.shell < 2:
            assert placed[name] == where


def test_every_shell_is_staggered_from_the_one_inside():
    shell_of = {"a": 0, "b": 1}
    placed = lay_out(shell_of, {"a": 10.0, "b": 10.0})
    direction = lambda p: tuple(c / math.hypot(*p) for c in p)  # noqa: E731
    assert direction(placed["a"].point) != pytest.approx(direction(placed["b"].point))


@pytest.mark.parametrize(
    "point",
    [(1, 0, 0), (0, 1, 0), (0, 0, 1), (0, 0, -1), (3, -4, 5), (-2, -2, -7), (0.1, 0.0, -9)],
)
def test_the_outward_turn_takes_up_along_the_ray(point):
    turn = outward_turn(point)
    up = turned(turn, (0, 0, 1))
    length = math.hypot(*point)
    for got, want in zip(up, (c / length for c in point)):
        assert got == pytest.approx(want, abs=1e-9)


def test_the_origin_turns_nothing_and_a_turn_is_a_rotation():
    assert outward_turn((0, 0, 0)) == (0.0, 0.0, 0.0)
    m = turn_matrix((20, 35, -70))
    for row in m:
        assert math.hypot(*row) == pytest.approx(1.0)
    det = (
        m[0][0] * (m[1][1] * m[2][2] - m[1][2] * m[2][1])
        - m[0][1] * (m[1][0] * m[2][2] - m[1][2] * m[2][0])
        + m[0][2] * (m[1][0] * m[2][1] - m[1][1] * m[2][0])
    )
    assert det == pytest.approx(1.0)


def test_a_turn_about_z_is_openscads():
    # rotate([0, 0, 90]) takes x to y
    assert turned((0, 0, 90), (1, 0, 0)) == pytest.approx((0, 1, 0), abs=1e-12)
    # rotate([90, 0, 0]) takes y to z
    assert turned((90, 0, 0), (0, 1, 0)) == pytest.approx((0, 0, 1), abs=1e-12)
