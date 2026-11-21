"""The flexure rotor: its SCAD and its mirror draw the same piece, and its hub swings
until a lobe meets its post.

``parts/flexure_rotor/flexure_rotor.scad`` draws a hub with lobes, a ring with posts and
the leaves that join them, in one piece; ``apothecary.projects.parts.flexure_rotor``
mirrors its outlines. These tests hold the two together through the SCAD's echo and its
render, and hold the motion to what the geometry promises: the gap between a lobe's flank
and its post's is ``post_r * sin(stop - swing)`` and closes at ``stop``; nothing else meets
anything on the way, either way; a leaf's bending strain is the small-turn closed form of
a beam built in at both ends.
"""

from __future__ import annotations

import json
import math
import re

import pytest

from apothecary.fittings import INTERFACE_TOLERANCE, readings
from apothecary.gap_geometry import ROCKING
from apothecary.meshes import bounds, read_mesh
from apothecary.projects.parts import flexure_rotor as fr
from apothecary.projects.parts.flexure_rotor import DEFAULT, Params
from apothecary.projects.parts.stl_renderer import (
    get_renderer,
    render_part,
    run_openscad,
    scad_definitions,
)
from apothecary.projects.parts.texts import defaults_disagree

# Few facets keep the renders small; the geometry's own tests run at the default.
COARSE = {"facets": 48}

ECHO = re.compile(
    r"ECHO: hub_outline = (?P<hub>\[\[.*?\]\]), cavity_outline = (?P<cavity>\[\[.*?\]\]), "
    r"leaves = (?P<leaves>\[\[\[.*?\]\]\])"
)


def scad_says(overrides: dict) -> dict:
    renderer = get_renderer()
    if not renderer.is_available:
        pytest.skip("OpenSCAD not installed")
    args = ["-o", "-", "--export-format=echo", "-D", "echo_shapes=true"]
    args += scad_definitions(DEFAULT.scad_overrides(DEFAULT.validate_overrides(overrides)))
    args.append(str(DEFAULT.source_file))
    code, out, err, stopped = run_openscad(renderer.openscad_path, args, DEFAULT.part_dir, 60)
    assert code == 0 and not stopped, err[-2000:]
    assert "WARNING" not in err and "ERROR" not in err, err[-2000:]
    found = ECHO.search(out)
    assert found, out[:500]
    return {k: json.loads(found[k]) for k in ("hub", "cavity", "leaves")}


def _apart(said, ours) -> float:
    assert len(said) == len(ours)
    return max(math.dist(a, b) for a, b in zip(said, ours, strict=True))


@pytest.mark.parametrize(
    "overrides",
    [
        COARSE,
        dict(lobes=3, lobe_arc=30, post_arc=20, stop=10, leaves=1, swing=-7.5, pocket=0, facets=60),
    ],
    ids=["default", "three_lobes_swung"],
)
def test_the_scad_and_the_mirror_draw_the_same_outlines(overrides):
    p = Params(**overrides)
    said = scad_says(overrides)
    # The echo prints six significant figures: 1e-4 mm on a 40 mm radius.
    assert _apart(said["hub"], fr.hub_outline(p)) < 2e-4
    assert _apart(said["cavity"], fr.cavity_outline(p)) < 2e-4
    ours = [fr.leaf_outline(p, a, ext=p.leaf) for a in fr.leaf_angles(p)]
    assert len(said["leaves"]) == len(ours) == p.lobes * p.leaves
    for theirs, mine in zip(said["leaves"], ours, strict=True):
        assert _apart(theirs, mine) < 2e-4


@pytest.mark.parametrize("swing", [-6.0, 4.5])
def test_swung_the_scad_draws_the_hub_where_the_motions_table_turns_it(swing):
    """The SCAD's hub drawn at a swing is the hub's own outline, at swing 0, placed by
    the motion's table's row at that swing; and its leaves are the table's."""
    from apothecary.gap_geometry import Pose as Placed
    from apothecary.motion import table

    values = {**COARSE, "swing": swing}
    said = scad_says(values)
    p = Params(**COARSE)
    made = table(DEFAULT.motion(p.model_dump()), p.model_dump())
    i = made["samples"].index(swing)
    (hub,) = made["pieces"]
    placed = Placed(*hub["poses"][i]).place(fr.hub_outline(p, 0.0))
    assert max(math.dist(a, b) for a, b in zip(said["hub"], placed, strict=True)) < 2e-4
    (leaves,) = made["bent"]
    # The SCAD carries each leaf on into the hub and the ring; the table draws its free span.
    for drawn, own in zip(said["leaves"], leaves["outlines"][i], strict=True):
        inner = drawn[1 : 1 + len(own) // 2] + drawn[len(own) // 2 + 3 : len(own) + 3]
        assert max(math.dist(a, b) for a, b in zip(inner, own, strict=True)) < 2e-4


def test_the_models_defaults_are_the_scads_literals():
    assert defaults_disagree(DEFAULT) == []


def test_the_envelope_and_the_pockets_are_the_rendered_ones(tmp_path):
    if not get_renderer().is_available:
        pytest.skip("OpenSCAD not installed")
    validated = DEFAULT.scad_overrides(DEFAULT.validate_overrides(COARSE))
    result = render_part(DEFAULT, tmp_path / "flexure_rotor.stl", params=validated, timeout=120)
    assert result.success, result.stderr
    triangles = read_mesh(result.stl_path)
    lo, hi = bounds(triangles)
    declared = DEFAULT.get_bounds(COARSE)
    assert list(lo) == pytest.approx(declared.min_point.to_list(), abs=0.05)
    assert list(hi) == pytest.approx(declared.max_point.to_list(), abs=0.05)
    interfaces = DEFAULT.interfaces(COARSE)
    assert [i.name for i in interfaces] == ["lobe_1", "lobe_2", "post_1", "post_2"]
    for interface in interfaces:
        for reading in readings(interface, triangles):
            assert reading.measured is not None, reading
            assert abs(reading.measured - reading.declared) <= INTERFACE_TOLERANCE, reading


class TestTheSwing:
    p = Params()

    def test_the_flank_gap_is_the_closed_form_and_closes_at_the_stop(self):
        """From the post's corner square to the lobe's flank: post_r * sin(stop - swing),
        while post_r * cos(stop - swing) stands beyond the hub's rim. The flanks are
        straight and the corner a point of the outline, so the polygons give it exactly."""
        p = self.p
        for swing in (-20.0, -12.5, -5.0, 0.0, 3.0, 6.0, 7.5):
            assert p.post_r * math.cos(math.radians(p.stop - swing)) > p.hub
            assert fr.flank_gap(p, swing) == pytest.approx(
                fr.flank_gap_closed_form(p, swing), abs=1e-9
            )
        assert fr.flank_gap(p, p.stop) == pytest.approx(0.0, abs=1e-9)
        assert fr.flank_gap(p, p.stop + 1) < 0
        assert fr.stop_reached(p) == pytest.approx(p.stop, abs=1e-5)

    @pytest.mark.parametrize("swing", [-20.0, -10.0, 0.0, 4.0, 7.5])
    def test_nothing_else_meets_anything_on_the_way(self, swing):
        """Up to the stop one way and the model's limit the other, the hub clears the ring
        and its posts, and each leaf, bent, clears every lobe and every post."""
        assert all(v > 0 for v in fr.clearances(self.p, swing).values())

    def test_at_the_stop_the_hub_meets_the_ring_where_a_lobe_meets_its_post(self):
        near = fr.clearances(self.p, self.p.stop)
        assert near["hub_to_ring"] == pytest.approx(0.0, abs=1e-9)

    def test_its_closest_approach_rocks_on_the_lobes_flank_and_stands_at_the_posts_corner(self):
        swung = fr.hub_travel(self.p, 6.0)
        assert swung.kind == ROCKING
        assert swung.path_outer == pytest.approx(0.0, abs=1e-9)
        assert swung.path_inner > 0 and swung.travel_inner == pytest.approx(0.0, abs=1e-9)
        assert min(swung.gaps) == pytest.approx(fr.flank_gap_closed_form(self.p, 6.0), abs=1e-9)


class TestTheLeaves:
    p = Params()

    def test_a_leaf_bends_sharpest_at_its_root_as_a_beam_built_in_at_both_ends(self):
        """A cubic with its root turned by a and carried a * hub across, the ring's end
        still: curvature 2 a (2 L + 3 hub) / L^2 at the root, so a surface strain of
        leaf * a * (2 L + 3 hub) / L^2 for a small turn."""
        p = self.p
        assert fr.leaf_strain(p, 0.0) == pytest.approx(0.0, abs=1e-12)
        for swing in (0.25, 1.0, -1.0):
            assert fr.leaf_strain(p, swing) == pytest.approx(
                fr.leaf_strain_small(p, swing), rel=1e-3
            )
        assert fr.leaf_strain(p, 2.0) == pytest.approx(2 * fr.leaf_strain(p, 1.0), rel=1e-3)

    def test_a_longer_leaf_bends_less_for_the_same_turn(self):
        short, long = Params(), Params(ring=44, lobe_r=22)
        assert fr.leaf_strain(long, 5.0) < fr.leaf_strain(short, 5.0)


class TestWhatItIs:
    def test_a_disc_for_each_pocket_is_listed_bought_and_fits_it(self):
        (discs,) = DEFAULT.bought()
        p = Params()
        assert (discs.name, discs.count, discs.diameter, discs.length) == ("pocket insert", 2 * p.lobes, 6.0, 3.0)
        holes = {i.name: i for i in DEFAULT.interfaces()}
        assert sorted(discs.goes_in) == sorted(holes)
        assert all(discs.diameter < holes[n].diameter and discs.length <= holes[n].depth for n in discs.goes_in)
        assert DEFAULT.bought({"pocket": 0}) == []

    def test_it_is_one_piece_with_its_pockets_taken_out(self):
        whole = fr.volume(Params(pocket=0))
        pocketed = fr.volume(Params())
        p = Params()
        taken = 2 * p.lobes * math.pi * (p.pocket / 2) ** 2 * p.pocket_depth
        assert whole - pocketed == pytest.approx(taken, rel=1e-3)
        assert 0 < pocketed < math.pi * (p.ring + p.wall) ** 2 * p.height

    def test_the_hubs_radial_gap_never_reads_below_the_posts_tips(self):
        """Along every ray the hub with its lobes stands inside the ring with its posts, by
        at least the post's tip over the hub's rim or the flank's gap."""
        p = Params()
        g = fr.hub_gap(p)
        assert g.minimum > 0
        assert g.minimum >= min(p.post_r - p.hub, p.ring - p.lobe_r) - 0.01

    @pytest.mark.parametrize(
        "values, says",
        [
            (dict(post_r=24), "nothing stops the hub"),
            (dict(swing=8), "past the stop"),
            (dict(lobes=4), "no room on the hub"),
            (dict(pocket=9), "of each lobe round it"),
            (dict(post_r=10.2), "from the hub"),
        ],
    )
    def test_a_set_that_would_not_print_or_move_is_refused_saying_why(self, values, says):
        with pytest.raises(ValueError, match=says):
            Params(**values)
