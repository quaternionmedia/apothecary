"""The rolling rotor: its SCAD and its mirror draw the same part, and its gap travels.

``parts/rolling_rotor/rolling_rotor.scad`` draws a stator with a track and pole teeth and a
rotor that rolls in the track; ``apothecary.projects.parts.rolling_rotor`` mirrors its
outlines and pose. These tests hold the two together through the SCAD's echo and its
render, and hold the gap to what the geometry promises: least at the tip nearest where the
rotor touches the track, gap plus twice the eccentricity opposite, once round the stator
and bore / rotor radius times round the rotor per orbit, and nothing but the track ever
touching the rotor.
"""

from __future__ import annotations

import json
import math
import re

import pytest

from apothecary.fittings import INTERFACE_TOLERANCE, readings
from apothecary.gap_geometry import ROLLING, contained, sagitta
from apothecary.meshes import bounds, read_mesh
from apothecary.projects.parts import rolling_rotor as rr
from apothecary.projects.parts.rolling_rotor import DEFAULT, Params
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
    r"ECHO: bore_outline = (?P<bore_outline>\[.*?\]\]), turn = (?P<turn>[-\d.e+]+), "
    r"rotor_at = (?P<rotor_at>\[.*?\]), outer_r = (?P<outer_r>[-\d.e+]+)"
)


def scad_says(overrides: dict, rest: bool = False) -> dict:
    renderer = get_renderer()
    if not renderer.is_available:
        pytest.skip("OpenSCAD not installed")
    args = ["-o", "-", "--export-format=echo", "-D", "echo_shapes=true"]
    args += scad_definitions(DEFAULT.scad_overrides(DEFAULT.validate_overrides(overrides)))
    if rest:
        args += scad_definitions(DEFAULT.rest)
    args.append(str(DEFAULT.source_file))
    code, out, err, stopped = run_openscad(renderer.openscad_path, args, DEFAULT.part_dir, 60)
    assert code == 0 and not stopped, err[-2000:]
    assert "WARNING" not in err and "ERROR" not in err, err[-2000:]
    found = ECHO.search(out)
    assert found, out[:500]
    return {
        "bore_outline": json.loads(found["bore_outline"]),
        "turn": float(found["turn"]),
        "rotor_at": json.loads(found["rotor_at"]),
        "outer_r": float(found["outer_r"]),
    }


@pytest.mark.parametrize(
    "overrides",
    [COARSE, dict(poles=5, pole_width=11, gap=0, eccentricity=2.5, orbit=100, facets=60)],
    ids=["default", "five_poles"],
)
def test_the_scad_and_the_mirror_draw_the_same_outlines(overrides):
    p = Params(**overrides)
    said = scad_says(overrides)
    ours = rr.bore_outline(p)
    # The echo prints six significant figures: 1e-4 mm on a 40 mm radius.
    assert len(said["bore_outline"]) == len(ours)
    assert max(math.dist(a, b) for a, b in zip(said["bore_outline"], ours, strict=True)) < 2e-4
    assert said["turn"] == pytest.approx(rr.turn(p), abs=2e-4)
    assert said["outer_r"] == pytest.approx(p.outer_r)
    assert said["rotor_at"] == pytest.approx([rr.print_offset(p), 0, 0])


@pytest.mark.parametrize("orbit", [0.0, 70.0, 250.0])
def test_assembled_the_scad_stands_the_rotor_where_the_motions_table_does(orbit):
    """The SCAD's own pose, as it rests, is the row the motion's table has at that orbit:
    the table the viewer plays and the drawing a render makes agree."""
    from apothecary.motion import table

    values = {**COARSE, "orbit": orbit}
    said = scad_says(values, rest=True)
    p = Params(**COARSE)
    made = table(DEFAULT.motion(p.model_dump()), p.model_dump())
    (rotor,) = made["pieces"]
    i = made["samples"].index(orbit)
    x, y, turned = rotor["poses"][i]
    assert said["rotor_at"] == pytest.approx([x, y, p.base], abs=2e-4)
    assert said["turn"] == pytest.approx(turned, abs=2e-4)


def test_the_models_defaults_are_the_scads_literals():
    assert defaults_disagree(DEFAULT) == []


def test_the_envelope_and_the_holes_are_the_rendered_ones(tmp_path):
    """The declared envelope is the render's, and each hole an output's pin or a
    bearing goes into reads its declared diameter across the rendered rotor."""
    if not get_renderer().is_available:
        pytest.skip("OpenSCAD not installed")
    validated = DEFAULT.scad_overrides(DEFAULT.validate_overrides(COARSE))
    result = render_part(DEFAULT, tmp_path / "rolling_rotor.stl", params=validated, timeout=120)
    assert result.success, result.stderr
    triangles = read_mesh(result.stl_path)
    lo, hi = bounds(triangles)
    declared = DEFAULT.get_bounds(COARSE)
    assert list(lo) == pytest.approx(declared.min_point.to_list(), abs=0.05)
    assert list(hi) == pytest.approx(declared.max_point.to_list(), abs=0.05)
    interfaces = DEFAULT.interfaces(COARSE)
    assert [i.name for i in interfaces] == [
        "centre",
        "output_1",
        "output_2",
        "output_3",
        "output_4",
    ]
    for interface in interfaces:
        for reading in readings(interface, triangles):
            assert reading.measured is not None, reading
            assert abs(reading.measured - reading.declared) <= INTERFACE_TOLERANCE, reading


class TestTheGap:
    p = Params()

    def test_it_is_least_at_the_tip_where_the_rotor_touches_and_widest_opposite(self):
        """With the rotor touching the track under a tooth, the gap there is `gap`, and at
        the tooth opposite it is `gap` plus twice the eccentricity; the tips' polygon
        stands within its sagitta inside their circle."""
        p = self.p
        g = rr.pole_gap(p, 0.0)
        tol = sagitta(p.tip_r, p.facets) + 1e-9
        assert g.where == pytest.approx(0.0)
        assert g.minimum == pytest.approx(p.gap, abs=tol)
        opposite = g.gaps[min(range(len(g.angles)), key=lambda i: abs(g.angles[i] - 180.0))]
        assert opposite == pytest.approx(p.gap + 2 * p.eccentricity, abs=tol)

    def test_over_a_slot_the_closest_tips_are_the_teeth_either_side(self):
        """With the rotor touching the track at a slot's middle, the poles come closest at
        the corners of the two teeth beside it, a closed form away."""
        p = self.p
        pitch = 360 / p.poles
        corner = pitch / 2 - math.degrees(math.asin(p.pole_width / 2 / p.tip_r))
        want = (
            math.sqrt(
                p.tip_r**2
                + p.eccentricity**2
                - 2 * p.tip_r * p.eccentricity * math.cos(math.radians(corner))
            )
            - p.rotor_r
        )
        g = rr.pole_gap(p, pitch / 2)
        assert g.minimum == pytest.approx(want, abs=sagitta(p.rotor_r, p.facets) + 1e-9)
        assert g.minimum > p.gap
        assert min(abs(g.where - (pitch / 2 + s * corner)) for s in (-1, 1)) < 360 / p.facets
        # The tips either side come as near as each other: two places, one on the tip of
        # each tooth beside the slot.
        half_tip = pitch / 2 - corner
        first, second = g.minima(0.01)
        assert -half_tip <= first <= half_tip + 1e-6
        assert pitch - half_tip - 1e-6 <= second <= pitch + half_tip

    def test_its_least_goes_once_round_the_stator_and_bore_over_r_round_the_rotor(self):
        p = self.p
        poles = rr.pole_travel(p)
        assert poles.turns_outer == pytest.approx(1.0, abs=0.005)
        assert poles.turns_inner == pytest.approx(p.bore / p.rotor_r, abs=0.005)
        assert min(poles.gaps) >= p.gap - sagitta(p.tip_r, p.facets) - 1e-9

    def test_the_rotor_rolls_on_the_track_and_turns_back_by_e_over_r_an_orbit(self):
        p = self.p
        assert rr.turn(p, 360.0) == pytest.approx(-360 * p.eccentricity / p.rotor_r)
        track = rr.track_travel(p)
        assert track.kind == ROLLING
        assert track.turns_outer == pytest.approx(1.0, abs=0.005)
        assert track.turns_inner == pytest.approx(p.bore / p.rotor_r, abs=0.005)
        assert track.path_outer == pytest.approx(2 * math.pi * p.bore, rel=0.005)
        assert max(track.gaps) <= sagitta(p.bore, p.facets)

    def test_nothing_but_the_track_touches_the_rotor_through_an_orbit(self):
        p = self.p
        rotor, poles, track = rr.rotor_outline(p), rr.bore_outline(p), rr.track_outline(p)
        for orbit in rr.orbits(15.0):
            placed = rr.pose(p, orbit).place(rotor)
            assert contained(placed, track), orbit
            assert contained(placed, poles), orbit


class TestWhatItIs:
    def test_a_slot_is_the_annulus_less_a_parallel_tooth(self):
        """Between the circles of the tips and the slots' bottoms, a slot is the annulus's
        share less one tooth of width w: the integral of the chord between the circles."""
        p = Params(facets=360)
        a = p.pole_width / 2

        def half_strip(radius: float) -> float:
            return a * math.sqrt(radius**2 - a**2) + radius**2 * math.asin(a / radius)

        want = math.pi * (p.yoke_r**2 - p.tip_r**2) / p.poles - (
            half_strip(p.yoke_r) - half_strip(p.tip_r)
        )
        assert rr.slot_area(p) == pytest.approx(want, rel=1e-3)

    def test_each_piece_has_a_volume_and_the_holes_are_taken_out_of_the_rotor(self):
        solid = rr.volumes(Params(hole=0, outputs=0))
        holed = rr.volumes(Params())
        assert solid["stator"] == pytest.approx(holed["stator"])
        assert holed["rotor"] < solid["rotor"]
        p = Params()
        assert solid["rotor"] == pytest.approx(math.pi * p.rotor_r**2 * p.stack, rel=1e-3)

    @pytest.mark.parametrize(
        "values, says",
        [
            (dict(poles=24, pole_width=10), "meet at their tips"),
            (dict(output_circle=26), "outside them"),
            (dict(hole=30), "round the centre hole"),
            (dict(outputs=12, output_pin=5), "between them"),
        ],
    )
    def test_a_set_that_would_not_print_is_refused_saying_why(self, values, says):
        with pytest.raises(ValueError, match=says):
            Params(**values)

    def test_it_rests_assembled_and_prints_apart(self):
        assert DEFAULT.rest == {"print": False}
        assert DEFAULT.get_bounds().size.x > 2 * Params().outer_r


INSERTS = {**COARSE, "pole_insert": 3.5, "rim_insert": 4}


class TestTheInserts:
    """Pockets for what is bought: drawn by the SCAD, listed by the wrapper, never in the
    STL. Printed plastic carries next to no flux; what goes in them is the owner's."""

    def test_the_pockets_are_where_the_interfaces_say(self, tmp_path):
        if not get_renderer().is_available:
            pytest.skip("OpenSCAD not installed")
        validated = DEFAULT.scad_overrides(DEFAULT.validate_overrides(INSERTS))
        result = render_part(DEFAULT, tmp_path / "pockets.stl", params=validated, timeout=120)
        assert result.success, result.stderr
        triangles = read_mesh(result.stl_path)
        pockets = [i for i in DEFAULT.interfaces(INSERTS) if i.name.startswith(("pole_", "rim_"))]
        assert len(pockets) == Params().poles + Params().rim_inserts
        for interface in pockets:
            for reading in readings(interface, triangles):
                assert reading.measured is not None, reading
                assert abs(reading.measured - reading.declared) <= INTERFACE_TOLERANCE, reading

    def test_each_bought_insert_is_listed_with_its_size_and_count_and_fits_its_pocket(self):
        listed = {b.name: b for b in DEFAULT.bought(INSERTS)}
        assert list(listed) == ["output pin", "bearing", "pole insert", "rim insert"]
        p = Params(**INSERTS)
        assert listed["pole insert"].count == p.poles and listed["rim insert"].count == p.rim_inserts
        holes = {i.name: i for i in DEFAULT.interfaces(INSERTS)}
        for item in listed.values():
            assert item.material is None
            for place in item.goes_in:
                assert item.diameter <= holes[place].diameter, (item.name, place)
                if item.length is not None:
                    assert item.length <= holes[place].depth
        assert [b.name for b in DEFAULT.bought()] == ["output pin", "bearing"]

    def test_the_pockets_are_taken_out_of_the_volumes(self):
        p = Params(**INSERTS)
        plain, pocketed = rr.volumes(Params(facets=48)), rr.volumes(p)
        hole = rr.area(rr.hole_outline(p, p.pole_insert))
        assert plain["stator"] - pocketed["stator"] == pytest.approx(p.poles * hole * p.insert_depth)

    @pytest.mark.parametrize(
        "values, says",
        [
            (dict(pole_insert=5), "tooth round it"),
            (dict(rim_insert=4, rim_inserts=36), "between them"),
            (dict(rim_insert=12), "round the output holes"),
        ],
    )
    def test_a_pocket_with_no_room_is_refused_saying_why(self, values, says):
        with pytest.raises(ValueError, match=says):
            Params(**values)
