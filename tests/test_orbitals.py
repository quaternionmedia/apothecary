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
    lattice_neighbours,
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
    assert all(a < b for a, b in zip(radii, radii[1:], strict=False))
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


def _angle(a, b) -> float:
    """The angle between two points' directions from the centre, in radians."""
    dot = sum(x * y for x, y in zip(a, b, strict=True)) / (math.hypot(*a) * math.hypot(*b))
    return math.acos(max(-1.0, min(1.0, dot)))


def _mixed(count=36, kinds=("bolt", "board", "bracket")):
    """One shell whose categories alternate by name, so laying them by name scatters
    each over the whole sphere."""
    names = [f"p{i:03d}" for i in range(count)]
    category_of = {name: kinds[i % len(kinds)] for i, name in enumerate(names)}
    return {name: 0 for name in names}, category_of, {name: 20.0 for name in names}


def _together(placed, category_of, kind) -> float:
    """How far apart a category's pieces are, against how far they are from the rest
    of the shell: the mean angle within over the mean angle across."""
    own = [n for n in placed if category_of[n] == kind]
    rest = [n for n in placed if category_of[n] != kind]
    within = [_angle(placed[a].point, placed[b].point) for a, b in itertools.combinations(own, 2)]
    across = [_angle(placed[a].point, placed[b].point) for a in own for b in rest]
    return (sum(within) / len(within)) / (sum(across) / len(across))


def _nearest(placed, near=6) -> dict:
    """Each name's ``near`` nearest on its shell: six, the neighbours a point of the
    lattice has about it."""
    names = list(placed)
    return {
        n: sorted(
            (m for m in names if m != n), key=lambda m: _angle(placed[n].point, placed[m].point)
        )[:near]
        for n in names
    }


def _pieces_of(placed, category_of, kind, near=6, nearest=None) -> int:
    """How many pieces a category's points make on its shell, each point joined to
    those of its category among its ``near`` nearest points of the shell (``nearest``,
    where they are already found)."""
    nearest = nearest or _nearest(placed, near)
    seen, count = set(), 0
    for start in (n for n in placed if category_of[n] == kind):
        if start in seen:
            continue
        count += 1
        stack = [start]
        seen.add(start)
        while stack:
            for m in nearest[stack.pop()]:
                if category_of[m] == kind and m not in seen:
                    seen.add(m)
                    stack.append(m)
    return count


@pytest.mark.parametrize(
    "count, kinds",
    [(36, ("bolt", "board", "bracket")), (40, ("a", "b", "c", "d")), (30, tuple("abcdef"))],
)
def test_the_pieces_of_a_category_sit_together_on_their_shell(count, kinds):
    """Each category is one piece of its shell, and its pieces nearer one another than
    the rest of the shell."""
    shell_of, category_of, sizes = _mixed(count, kinds)
    placed = lay_out(shell_of, sizes, category_of=category_of)
    for kind in kinds:
        assert _pieces_of(placed, category_of, kind) == 1, kind
        assert _together(placed, category_of, kind) < 0.75, kind


def test_a_category_given_no_cluster_is_scattered_which_the_rule_above_would_catch():
    """The measure is no measure if laying by name passes it too."""
    shell_of, category_of, sizes = _mixed()
    placed = lay_out(shell_of, sizes)
    assert all(_pieces_of(placed, category_of, kind) > 1 for kind in set(category_of.values()))
    assert max(_together(placed, category_of, kind) for kind in set(category_of.values())) > 0.9


def test_the_lattice_is_one_piece_on_its_graph_of_neighbours():
    """Each point joined to those of its six nearest that have it among theirs: the
    joins go both ways, and every lattice is one piece on them."""
    for n in [*range(1, 65), 100, 150]:
        joined = lattice_neighbours(fibonacci_sphere(n, 1.0))
        assert all(i in joined[j] for i in range(n) for j in joined[i]), n
        seen, stack = {0}, [0]
        while stack:
            for j in joined[stack.pop()]:
                if j not in seen:
                    seen.add(j)
                    stack.append(j)
        assert len(seen) == n, n


def test_a_region_cuts_off_no_free_points_it_has_no_room_to_take():
    """On a path 0-1-2-3-4 with a branch 2-5-6, three points grown from 2, where it
    branches, would leave 0-1 and 5-6 apart: refused, where grown regardless they are
    apart. Five from 2 take what 2 cuts off with it, and leave the rest one piece."""
    from apothecary.orbitals import _grow, _pieces

    joined = [[1], [0, 2], [1, 3, 5], [2, 4], [3], [2, 6], [5]]
    free = set(range(7))

    def rank(i):
        return (i,)

    assert _grow(2, 3, free, joined, rank, keep_free_whole=True) is None
    regardless = _grow(2, 3, free, joined, rank, keep_free_whole=False)
    assert len(_pieces(free - set(regardless), joined)) == 2
    region = _grow(2, 5, free, joined, rank, keep_free_whole=True)
    assert _pieces(free - set(region), joined) == [{0, 1}]
    assert _grow(4, 2, free, joined, rank, keep_free_whole=True) == [4, 3]


def _every_category_one_piece(shell_of, sizes, category_of, parent_of):
    placed = lay_out(shell_of, sizes, category_of=category_of, parent_of=parent_of)
    split = []
    for shell in set(shell_of.values()):
        on = {name: placed[name] for name in placed if shell_of[name] == shell}
        of = {name: category_of.get(name) for name in on}
        nearest = _nearest(on)
        split += [
            (shell, kind)
            for kind in sorted(set(of.values()), key=str)
            if _pieces_of(on, of, kind, nearest=nearest) != 1
        ]
    return split


# A shell inside a shell of seven: a category of six, two of whose members are built
# into pieces outside in different directions, and three single pieces built into
# others; then a category of four, one of three, five of two and eight of one that
# nothing pulls -- the shape of the universe's innermost shell where a category of
# two was laid on either side of the six.
PULLED_TWO_WAYS = {
    "a": 6,
    "b": 4,
    "c": 3,
    **dict.fromkeys("defgh", 2),
    **dict.fromkeys("pqrstuvw", 1),
}


def test_a_category_pulled_two_ways_leaves_every_other_one_piece():
    inner = {f"{kind}{i}": kind for kind, n in PULLED_TWO_WAYS.items() for i in range(n)}
    outer = {f"out{i}": "xxxyyzz"[i] for i in range(7)}
    shell_of = {**dict.fromkeys(inner, 0), **dict.fromkeys(outer, 1)}
    sizes = dict.fromkeys(shell_of, 20.0)
    split = {}
    for one, other in itertools.permutations(range(7), 2):
        for singles in ((s, (s + 2) % 7, (s + 4) % 7) for s in range(7)):
            parent_of = {
                "a0": f"out{one}",
                "a1": f"out{other}",
                **{f"{kind}0": f"out{at}" for kind, at in zip("pqr", singles, strict=True)},
            }
            found = _every_category_one_piece(shell_of, sizes, {**inner, **outer}, parent_of)
            if found:
                split[(one, other, singles)] = found
    assert split == {}


def _random_shells(rng):
    """A shell of 4 to 64 pieces in categories of random sizes, under a shell of 1 to 12
    whose pieces some of them are built into."""
    inner, left, kind = {}, rng.randint(4, 64), 0
    while left:
        size = min(left, max(1, int(rng.expovariate(1 / rng.choice([1.5, 3, 6, 10])))))
        named = f"k{kind:02d}" if kind or rng.random() < 0.8 else None
        for _ in range(size):
            inner[f"in{len(inner):03d}"] = named
        left, kind = left - size, kind + 1
    outer = {f"out{i:02d}": f"o{rng.randint(0, 2)}" for i in range(rng.randint(1, 12))}
    share = rng.choice([0.05, 0.15, 0.3])
    parent_of = {name: rng.choice(sorted(outer)) for name in inner if rng.random() < share}
    shell_of = {**dict.fromkeys(inner, 0), **dict.fromkeys(outer, 1)}
    return shell_of, dict.fromkeys(shell_of, 20.0), {**inner, **outer}, parent_of


def test_every_category_is_one_piece_of_its_shell_whatever_pulls_it():
    """Shells of random sizes, categories and pulls, the same each run: no category is
    in two pieces of its shell."""
    import random

    split = {}
    for seed in range(120):
        found = _every_category_one_piece(*_random_shells(random.Random(seed)))
        if found:
            split[seed] = found
    assert split == {}


def _two_shells(inner=20, outer=8):
    shell_of = {
        **{f"in{i:02d}": 0 for i in range(inner)},
        **{f"out{i:02d}": 1 for i in range(outer)},
    }
    return shell_of, {name: 15.0 for name in shell_of}


def test_a_piece_stands_as_nearly_under_the_piece_it_is_built_into_as_its_shell_allows():
    shell_of, sizes = _two_shells()
    placed = lay_out(shell_of, sizes, parent_of={"in07": "out05"})
    above = placed["out05"].point
    nearest = min(_angle(p, above) for p in fibonacci_sphere(20, 1.0, 0.0))
    assert _angle(placed["in07"].point, above) == pytest.approx(nearest, abs=1e-12)
    # Not by chance: laid by name, it stands elsewhere.
    alone = lay_out(shell_of, sizes)
    assert _angle(alone["in07"].point, alone["out05"].point) > nearest + 0.1


def test_a_piece_on_its_own_shell_or_inside_is_no_piece_to_stand_under():
    shell_of, sizes = _two_shells()
    placed = lay_out(shell_of, sizes)
    assert lay_out(shell_of, sizes, parent_of={"in07": "in03", "out01": "in02"}) == placed


def test_a_cluster_gathers_under_the_pieces_its_members_are_built_into():
    """Three categories inside, one of them built into two neighbours outside: that
    one's middle is under them, nearer than either other category's, where laid with
    no pull it is the farthest of the three."""
    names = [f"in{i:02d}" for i in range(18)]
    category_of = {name: ("board", "bolt", "cable")[i % 3] for i, name in enumerate(names)}
    shell_of = {**{name: 0 for name in names}, **{f"out{i}": 1 for i in range(6)}}
    sizes = {name: 15.0 for name in shell_of}

    def near(parent_of):
        placed = lay_out(shell_of, sizes, category_of=category_of, parent_of=parent_of)
        under = [sum(placed[f"out{i}"].point[k] for i in (3, 4)) for k in range(3)]

        def middle(kind):
            return [
                sum(placed[n].point[k] for n in names if category_of[n] == kind) for k in range(3)
            ]

        return {kind: _angle(middle(kind), under) for kind in ("board", "bolt", "cable")}

    pulled = near({"in00": "out3", "in03": "out4"})
    assert pulled["board"] < min(pulled["bolt"], pulled["cable"]), pulled
    unpulled = near({})
    assert unpulled["board"] > max(unpulled["bolt"], unpulled["cable"]), unpulled


def test_a_piece_added_outside_that_nothing_is_built_into_moves_nothing_inside():
    shell_of, category_of, sizes = _mixed(24)
    shell_of = {**shell_of, "out0": 1, "out1": 1}
    category_of = {**category_of, "out0": "rig", "out1": "rig"}
    sizes = {**sizes, "out0": 40.0, "out1": 40.0}
    parent_of = {"p004": "out1"}
    before = lay_out(shell_of, sizes, category_of=category_of, parent_of=parent_of)
    placed = lay_out(
        {**shell_of, "site-new": 2},
        {**sizes, "site-new": 120.0},
        category_of=category_of,
        parent_of=parent_of,
    )
    for name, where in before.items():
        assert placed[name] == where, name


def test_the_seats_are_the_same_whatever_order_the_names_come_in():
    shell_of, category_of, sizes = _mixed(18)
    shell_of = {**shell_of, "out0": 1}
    parent_of = {"p005": "out0", "p011": "out0"}
    first = lay_out(shell_of, sizes | {"out0": 30.0}, category_of=category_of, parent_of=parent_of)
    again = lay_out(
        dict(reversed(list(shell_of.items()))),
        sizes | {"out0": 30.0},
        category_of=dict(reversed(list(category_of.items()))),
        parent_of=parent_of,
    )
    assert again == first


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
    for got, want in zip(up, (c / length for c in point), strict=True):
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
