"""The airgap part is its SCAD, and the Python mirror agrees with it.

``parts/airgap/airgap.scad`` computes its rotor, bore, frame, coverage, conductor stations
and conductor paths from its top-level assignments; ``apothecary.projects.parts.airgap``
computes the same in Python for the envelope and the panel. Run with ``-D
echo_surfaces=true``, the SCAD prints what it computed, and these tests hold the two
together across the base forms, features, coverages and windings the part offers.
"""

from __future__ import annotations

import json
import re

import pytest

from apothecary.meshes import bounds, read_mesh
from apothecary.projects.parts import airgap
from apothecary.projects.parts.airgap import DEFAULT, Params
from apothecary.projects.parts.stl_renderer import (
    get_renderer,
    render_part,
    run_openscad,
    scad_definitions,
)
from apothecary.projects.parts.texts import defaults_disagree

# Each case moves a different corner of the part: a base form, a feature, a coverage, a
# frame, a winding. The default is the SCAD as saved.
CASES = {
    "default": {},
    "mobius_lap": dict(
        rotor_base_form="ellipse",
        rotor_base_ratio=0.7,
        rotor_rib_k=5,
        rotor_rib_w=0.2,
        rotor_rib_mode="woven",
        rotor_rib_p=1.5,
        stator_teeth_n=18,
        stator_teeth_l=2,
        stator_cov_segs=3,
        stator_cov_arc=0.8,
        stator_outer_form="hex",
        topology="lap",
        pitch=3,
        pattern="custom",
        layout="A+ A+ C- C- B+ B+ A- A- C+ C+ B- B-",
    ),
    "reuleaux_wave": dict(
        rotor_base_form="constwidth",
        rotor_base_width_k=3,
        rotor_base_width_a=0.12,
        rotor_spiral_b=0,
        rotor_rib_k=0,
        stator_base_form="polygon",
        stator_base_sides=6,
        stator_base_round=0.4,
        stator_rot=15,
        stator_off_x=0.1,
        stator_off_y=-0.05,
        stator_teeth_n=9,
        stator_teeth_shape="sine",
        stator_outer_form="square",
        topology="wave",
    ),
    "superellipse_toroid": dict(
        rotor_base_form="superellipse",
        rotor_base_exp=3,
        rotor_off_x=0.15,
        rotor_rot=30,
        rotor_teeth_n=8,
        rotor_teeth_h=0.05,
        rotor_teeth_shape="tri",
        stator_base_form="ellipse",
        stator_base_ratio=0.85,
        stator_teeth_n=0,
        stator_outer_form="round",
        topology="toroidal",
        slots=12,
    ),
    "custom_stations": dict(
        topology="custom", custom_stations="A: 0:50 90:-50; B: 30:50, 120:-50\nC: 60:25.5 150:-25.5"
    ),
    "sinusoidal": dict(topology="sinusoidal", pole_pairs=2, stator_teeth_n=0),
    "segments_paired": dict(
        stator_cov_segs=4,
        stator_cov_arc=0.6,
        stator_cov_rot=20,
        stator_teeth_n=24,
        stator_teeth_l=1,
        pattern="paired",
        span=0.9,
        skew_deg=15,
    ),
    "saw_sequential": dict(
        rotor_spiral_b=1.2,
        rotor_spiral_k=3,
        rotor_spiral_s=0.5,
        stator_teeth_shape="saw",
        stator_teeth_n=6,
        stator_teeth_h=0.2,
        phases=2,
        pattern="sequential",
    ),
}

ECHO = re.compile(
    r"ECHO: s0 = (?P<s0>[-\d.e+]+), rotor_r = (?P<rotor_r>\[.*?\]), bore_r = (?P<bore_r>\[.*?\]), "
    r"outer_r = (?P<outer_r>\[.*?\]), mask = (?P<mask>\[.*?\]), psi_s = (?P<psi_s>\[.*?\]), "
    r"stations = (?P<stations>\[.*\]), paths = (?P<paths>\[.*\])\s*$",
    re.S,
)


def scad_says(overrides: dict) -> dict:
    """What the SCAD computes for ``overrides``, from its echo export."""
    renderer = get_renderer()
    if not renderer.is_available:
        pytest.skip("OpenSCAD not installed")
    args = ["-o", "-", "--export-format=echo", "-D", "echo_surfaces=true"]
    args += scad_definitions(DEFAULT.scad_overrides(DEFAULT.validate_overrides(overrides)))
    args.append(str(DEFAULT.source_file))
    code, out, err, stopped = run_openscad(renderer.openscad_path, args, DEFAULT.part_dir, 120)
    assert code == 0 and not stopped, err[-2000:]
    assert "WARNING" not in err and "ERROR" not in err, err[-2000:]
    found = ECHO.search(out)
    assert found, out[:500]
    as_list = lambda s: json.loads(s.replace("true", "1").replace("false", "0"))  # noqa: E731
    return {
        "s0": float(found["s0"]),
        **{
            k: as_list(found[k])
            for k in ("rotor_r", "bore_r", "outer_r", "mask", "psi_s", "stations", "paths")
        },
    }


@pytest.mark.parametrize("name", list(CASES))
def test_the_scad_and_the_mirror_compute_the_same_part(name):
    overrides = CASES[name]
    p = Params(**overrides)
    said = scad_says(overrides)
    sf = airgap.build_surfaces(p)
    wd = airgap.build_winding(p, sf)
    paths = airgap.build_paths(p, sf)
    # The echo prints six significant figures: 1e-4 mm on a 40 mm radius.
    for key in ("rotor_r", "bore_r", "outer_r"):
        ours = [v * p.r0 for v in getattr(sf, key)]
        assert len(said[key]) == len(ours) == p.resolution
        assert max(abs(a - b) for a, b in zip(said[key], ours, strict=True)) < 2e-4, key
    assert said["s0"] == pytest.approx(sf.s0 * p.r0, abs=2e-4)
    assert said["mask"] == sf.mask
    theirs = sorted((round(s[0] % 360, 1) % 360, round(s[1], 1), s[2]) for s in said["stations"])
    ours_st = sorted((round(s[0] % 360, 1) % 360, round(s[1], 1), s[2]) for s in wd.stations)
    assert theirs == ours_st
    assert [(q[0], round(q[1], 3), bool(q[2]), len(q[3])) for q in said["paths"]] == [
        (q[0], round(q[1], 3), q[2], len(q[3])) for q in paths
    ]
    for theirs_path, ours_path in zip(said["paths"], paths, strict=True):
        for a, b in zip(theirs_path[3], ours_path[3], strict=True):
            assert max(abs(x - y) for x, y in zip(a, b, strict=True)) < 2e-3


def test_the_models_defaults_are_the_scads_literals():
    assert defaults_disagree(DEFAULT) == []


def test_the_flat_form_folds_into_the_groups_and_back():
    p = Params(rotor_base_form="ellipse", stator_teeth_n=18, topology="lap", r0=40)
    assert p.rotor.rotor_base_form == "ellipse"
    assert p.stator.stator_teeth_n == 18
    assert p.windings.topology == "lap"
    flat = p.flat()
    assert flat["r0"] == 40 and flat["rotor_base_form"] == "ellipse" and flat["pitch"] == 1
    assert Params(**flat) == p
    nested = Params(rotor={"rotor_base_form": "polygon"}, windings={"turns": 12})
    assert nested.rotor.rotor_base_form == "polygon" and nested.windings.turns == 12
    # The part names each group's fields as SCAD assignments of their own.
    emitted = DEFAULT.scad_overrides(DEFAULT.validate_overrides({"rotor": {"rotor_rib_k": 5}}))
    assert emitted["rotor_rib_k"] == 5 and "rotor" not in emitted


def test_a_slot_string_and_typed_stations_read_as_the_scad_reads_them():
    assert airgap.parse_layout("A+ a- C+x2 B×1.5, d") == [
        (0, 1, 1.0),
        (0, -1, 1.0),
        (2, 1, 2.0),
        (1, 1, 1.5),
        (3, 1, 1.0),
    ]
    assert airgap.parse_custom("A: 0:50 90:-50; B: 30:50, 120:-50\nC: -10:25.5") == [
        (0, 0.0, 50.0),
        (0, 90.0, -50.0),
        (1, 30.0, 50.0),
        (1, 120.0, -50.0),
        (2, 350.0, 25.5),
    ]
    assert airgap.parse_layout("1 ? +") == []


def test_a_bare_rotor_or_stator_has_the_envelope_it_draws():
    whole = DEFAULT.get_bounds()
    cores = DEFAULT.get_bounds({"show_windings": False})
    assert cores.max_point.z == pytest.approx(10.0)  # the stack alone
    assert whole.max_point.z > cores.max_point.z  # the end-turns reach past it
    rotor = DEFAULT.get_bounds({"show_stator": False, "show_windings": False})
    assert rotor.max_point.x < cores.max_point.x


def test_an_empty_winding_draws_nothing():
    p = Params(phases=0)
    assert airgap.build_paths(p) == []
    assert (
        airgap.build_winding(
            Params(stator_teeth_n=0), airgap.build_surfaces(Params(stator_teeth_n=0))
        ).stations
        == []
    )


@pytest.mark.slow
@pytest.mark.parametrize(
    "overrides", [{}, {"topology": "lap", "pitch": 3}, {"topology": "wave", "skew_deg": 20}]
)
def test_the_envelope_is_the_rendered_one_to_the_bundles_vertices(overrides, tmp_path):
    """The mirror places the swept bundles' vertices as the SCAD does, so the declared
    envelope is the rendered one to a hundredth of a millimetre, not the library's 0.5."""
    if not get_renderer().is_available:
        pytest.skip("OpenSCAD not installed")
    validated = DEFAULT.scad_overrides(DEFAULT.validate_overrides(overrides))
    result = render_part(DEFAULT, tmp_path / "airgap.stl", params=validated, timeout=240)
    assert result.success, result.stderr
    declared = DEFAULT.get_bounds(overrides)
    lo, hi = bounds(read_mesh(result.stl_path))
    assert list(lo) == pytest.approx(declared.min_point.to_list(), abs=0.05)
    assert list(hi) == pytest.approx(declared.max_point.to_list(), abs=0.05)
