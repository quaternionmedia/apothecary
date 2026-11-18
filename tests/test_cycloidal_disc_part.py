"""The cycloidal disc: its SCAD and its mirror draw the same part, and its lobes run on its pins.

``parts/cycloidal_disc/cycloidal_disc.scad`` draws a stator with a ring of pin holes and a
disc whose flank is the inner parallel of the curve each pin's centre runs on, seen from
the turning disc; ``apothecary.projects.parts.cycloidal_disc`` mirrors its outlines and its
pose. These tests hold the two together through the SCAD's echo and its render, and hold
the motion to what the counts promise, measured from the outlines alone:

- every pin stands ``clearance`` from the flank, within the polygon's sagitta, at every
  turn of the crank, and none stands in the disc: the collision guard;
- the disc turns back ``360 / (pins - 1)`` each turn of the crank, and the pins hold it
  there: turned any other way it meets a pin, and at each crank the turn it can take
  either way before it meets one is centred on the pose's: the ratio guard.
"""

from __future__ import annotations

import json
import math
import re

import pytest

from apothecary.fittings import INTERFACE_TOLERANCE, readings
from apothecary.gap_geometry import ROLLING, STANDING, Pose, circle, sagitta, separation
from apothecary.meshes import bounds, read_mesh
from apothecary.projects.parts import cycloidal_disc as cd
from apothecary.projects.parts.cycloidal_disc import DEFAULT, Params
from apothecary.projects.parts.stl_renderer import (
    get_renderer,
    render_part,
    run_openscad,
    scad_definitions,
)
from apothecary.projects.parts.texts import defaults_disagree

# Few points keep the renders small; the geometry's own tests run at the default.
COARSE = {"profile": 240, "facets": 48}

ECHO = re.compile(
    r"ECHO: profile_outline = (?P<profile>\[.*?\]\]), turn = (?P<turn>[-\d.e+]+), "
    r"disc_at = (?P<disc_at>\[.*?\]), outer_r = (?P<outer_r>[-\d.e+]+)"
)

OTHERS = [
    dict(pins=7, pin_circle=20, pin=4, eccentricity=1.5, bearing=8, outputs=4, output_circle=10),
    # Sharper lobes, drawn with more points to stay within a hundredth of their curve.
    dict(pins=21, pin=6, eccentricity=0.8, clearance=0.0, profile=1440),
]


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
    return {
        "profile": json.loads(found["profile"]),
        "turn": float(found["turn"]),
        "disc_at": json.loads(found["disc_at"]),
        "outer_r": float(found["outer_r"]),
    }


@pytest.mark.parametrize(
    "overrides",
    [COARSE, {**OTHERS[0], "crank": 100, "profile": 168, "facets": 48}],
    ids=["default", "seven_pins"],
)
def test_the_scad_and_the_mirror_draw_the_same_flank(overrides):
    p = Params(**overrides)
    said = scad_says(overrides)
    ours = cd.disc_outline(p)
    # The echo prints six significant figures: 1e-4 mm on a 30 mm radius.
    assert len(said["profile"]) == len(ours)
    assert max(math.dist(a, b) for a, b in zip(said["profile"], ours, strict=True)) < 2e-4
    assert said["turn"] == pytest.approx(cd.turn(p), abs=2e-4)
    assert said["outer_r"] == pytest.approx(p.outer_r)
    assert said["disc_at"] == pytest.approx([cd.print_offset(p), 0, 0])


def test_the_models_defaults_are_the_scads_literals():
    assert defaults_disagree(DEFAULT) == []


def test_the_envelope_and_the_holes_are_the_rendered_ones(tmp_path):
    """The declared envelope is the render's, and each hole a pin, the bearing or an
    insert goes into reads its declared diameter across the rendered pieces."""
    if not get_renderer().is_available:
        pytest.skip("OpenSCAD not installed")
    values = {**COARSE, "outputs": 5, "lobe_insert": 3, "pole_insert": 2}
    validated = DEFAULT.scad_overrides(DEFAULT.validate_overrides(values))
    result = render_part(DEFAULT, tmp_path / "cycloidal_disc.stl", params=validated, timeout=180)
    assert result.success, result.stderr
    triangles = read_mesh(result.stl_path)
    lo, hi = bounds(triangles)
    declared = DEFAULT.get_bounds(values)
    assert list(lo) == pytest.approx(declared.min_point.to_list(), abs=0.05)
    assert list(hi) == pytest.approx(declared.max_point.to_list(), abs=0.05)
    interfaces = DEFAULT.interfaces(values)
    p = Params(**values)
    names = [i.name for i in interfaces]
    assert names[: p.pins] == [f"pin_{k + 1}" for k in range(p.pins)]
    assert {"shaft", "bearing", "output_1", "lobe_1", f"lobe_{p.lobes}", f"pole_{p.pins}"} <= set(names)
    for interface in interfaces:
        for reading in readings(interface, triangles):
            assert reading.measured is not None, reading
            assert abs(reading.measured - reading.declared) <= INTERFACE_TOLERANCE, reading


class TestTheLobesOnThePins:
    p = Params()

    @pytest.mark.parametrize("values", [{}, *OTHERS], ids=["default", "seven_pins", "twenty_one_pins"])
    def test_every_pin_stands_its_clearance_from_the_flank_through_a_turn_of_the_crank(self, values):
        """The collision guard: at every crank no pin stands in the disc, and every pin
        stands the clearance from the flank, to within how far the polygon's edges stand
        from the curve it is drawn from."""
        p = Params(**values)
        tol = cd.profile_sagitta(p) + 1e-6
        assert tol < 0.01
        for crank in cd.cranks(5.0):
            marks = cd.pin_marks(p, crank)
            assert len(marks) == p.pins
            for m in marks:
                assert m.gap == pytest.approx(p.clearance, abs=tol), (crank, m)

    def test_the_polygon_measure_says_the_same_with_the_pins_drawn_as_polygons(self):
        """gap_geometry's own separation of each pin drawn as a 720-gon from the placed
        disc: the same, less than the pin's sagitta wider."""
        p = self.p
        for crank in (0.0, 37.0, 211.0):
            rim = cd.pose(p, crank).place(cd.disc_outline(p))
            least = min(separation(circle(p.pin / 2, 720, c), rim) for c in cd.pin_centres(p))
            assert 0 <= least - cd.least_gap(p, crank) <= sagitta(p.pin / 2, 720) + 1e-9

    def test_the_disc_turns_back_a_pins_pitch_each_turn_of_the_crank(self):
        """The ratio is the counts': pins - 1 turns of the crank turn the disc once."""
        for values in ({}, *OTHERS):
            p = Params(**values)
            assert cd.turn(p, 360.0) == pytest.approx(-360.0 / (p.pins - 1))
            assert cd.pose(p, 360.0 * (p.pins - 1)).turn == pytest.approx(-360.0)

    def test_the_pins_hold_the_disc_where_the_pose_turns_it(self):
        """The ratio guard, from the outlines: at each crank the disc can turn about its
        own centre a little either way before it meets a pin -- its backlash as drawn --
        and the middle of that is the pose's turn. The pins centre it there, not the
        pose. To first order the turn either way is the clearance over the longest
        lever a pin's contact has about the disc's centre; the pins that stop it each
        way differ a little, so the two agree within a few per cent."""
        p = self.p
        for crank in (0.0, 37.0, 90.0, 211.0, 333.0):
            back, on = cd.free_turn(p, crank)
            assert back < 0 < on, crank
            assert (back + on) / 2 == pytest.approx(0.0, abs=2e-3), crank
            at = cd.pose(p, crank)
            lever = 0.0
            for m in cd.pin_marks(p, crank):
                nx, ny = m.to[0] - m.on[0], m.to[1] - m.on[1]
                length = math.hypot(nx, ny)
                lever = max(lever, abs((m.to[0] - at.x) * ny - (m.to[1] - at.y) * nx) / length)
            assert on - back == pytest.approx(2 * math.degrees(p.clearance / lever), rel=0.03), crank

    def test_with_no_clearance_the_pins_hold_it_with_no_play(self):
        """Drawn with no clearance, every pin touches the flank within the polygon's
        sagitta, and turned a twentieth of a degree either way the disc stands in a pin
        deeper than that."""
        p = Params(clearance=0.0)
        tol = cd.profile_sagitta(p) + 1e-6
        for crank in (0.0, 37.0):
            at = cd.pose(p, crank)
            assert abs(cd.least_gap(p, crank)) <= tol
            for delta in (-0.05, 0.05):
                turned = Pose(at.x, at.y, at.turn + delta)
                assert cd.least_gap(p, placed=turned) < -3 * tol, (crank, delta)

    def test_its_pitch_circles_roll_and_one_pins_contact_slides_along_the_flank(self):
        """The disc's pitch circle, E (N - 1), rolls on the ring's, E N: once round the
        ring and N / (N - 1) times round itself each turn of the crank, the same distance
        along each. A fixed pin's contact does not roll: it stands on the pin, sweeping
        back and forth across its face, and goes a lobe round the disc, sliding several
        times as far along the flank as across the pin."""
        p = self.p
        pitch = cd.pitch_travel(p)
        assert pitch.kind == ROLLING
        assert pitch.turns_outer == pytest.approx(1.0, abs=0.005)
        assert pitch.turns_inner == pytest.approx(p.pins / (p.pins - 1), abs=0.005)
        pin = cd.pin_travel(p)
        assert pin.kind == STANDING
        assert pin.travel_inner == pytest.approx(360.0 / (p.pins - 1), abs=0.5)
        assert pin.path_inner > 4 * pin.path_outer > 0

    def test_each_output_pin_stays_in_its_hole_touching_its_wall(self):
        """An output pin turns with the disc about the axis while its hole is carried
        round the eccentric: its centre stands the eccentricity from the hole's, so a
        pin a hole's diameter less twice the eccentricity runs round its wall."""
        p = self.p
        for crank in cd.cranks(15.0):
            disc, out = cd.pose(p, crank), cd.output_pose(p, crank)
            holes = disc.place(cd.output_centres(p))
            pins = out.place(cd.output_centres(p))
            for h, q in zip(holes, pins, strict=True):
                assert math.dist(h, q) == pytest.approx(p.eccentricity, abs=1e-9)
        assert p.output_d / 2 - p.output_pin / 2 == pytest.approx(p.eccentricity)

    def test_the_motion_plays_the_crank_with_the_disc_and_the_output_turning_together(self):
        motion = DEFAULT.motion()
        assert (motion.param, motion.lo, motion.hi, motion.cyclic) == ("crank", 0.0, 360.0, True)
        at = motion.pose(90.0)
        assert at["disc"] == cd.pose(self.p, 90.0)
        assert at["output"] == Pose(0.0, 0.0, cd.turn(self.p, 90.0))
        assert [i.name for i in motion.still.inserts] == ["pin"] * self.p.pins
        (gap,) = motion.gaps
        assert len(gap.measure(90.0)) == self.p.pins


class TestWhatItIs:
    def test_it_lists_what_is_bought_and_each_goes_where_the_part_has_a_hole_for_it(self):
        values = {"outputs": 5, "lobe_insert": 3, "pole_insert": 2}
        listed = {b.name: b for b in DEFAULT.bought(values)}
        assert list(listed) == ["pin", "bearing", "output pin", "lobe insert", "pole insert"]
        p = Params(**values)
        assert listed["pin"].count == p.pins and listed["pin"].diameter == p.pin
        assert listed["lobe insert"].count == p.lobes
        holes = {i.name: i for i in DEFAULT.interfaces(values)}
        for item in listed.values():
            for place in item.goes_in:
                assert item.diameter <= holes[place].diameter, (item.name, place)
                if item.length is not None and holes[place].floor == 0.0:
                    assert item.length <= holes[place].depth
        printed = {b.name for b in DEFAULT.bought({"printed_pins": True})}
        assert "pin" not in printed
        assert not any(i.name.startswith("pin_") for i in DEFAULT.interfaces({"printed_pins": True}))

    @pytest.mark.parametrize(
        "values, says",
        [
            (dict(pin_circle=10), "loops"),
            (dict(pins=7, pin_circle=12, eccentricity=1.6, pin=6, bearing=0, outputs=0, shaft=0), "fold"),
            (dict(pins=31, pin_circle=32, pin=5), "apart"),
            (dict(eccentricity=2.5, pin=4), "into the housing"),
            (dict(output_circle=24), "outside them"),
            (dict(lobe_insert=3), "round the disc's holes"),
            (dict(pole_insert=4), "of a 6 wall"),
        ],
    )
    def test_a_set_that_would_not_run_or_print_is_refused_saying_why(self, values, says):
        with pytest.raises(ValueError, match=says):
            Params(**values)

    def test_it_rests_assembled_and_prints_apart(self):
        assert DEFAULT.rest == {"print": False}
        assert DEFAULT.get_bounds().size.x > 2 * Params().outer_r
