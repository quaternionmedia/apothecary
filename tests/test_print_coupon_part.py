"""The printer's coupon (parts/print_coupon): its plan names each feature where its SCAD
draws it, and the plan's readings separate the terms it claims to.

One render, read along every feature's line: what a caliper closing there would meet."""

from __future__ import annotations

import pytest

from apothecary.meshes import bounds, crossings, read_mesh
from apothecary.models.measures import MEASURE_TOLERANCE, MeasurePlan, box_plan
from apothecary.projects.parts.print_coupon import DEFAULT, PLAN_SEPARATES, Params, plan
from apothecary.projects.parts.stl_renderer import get_renderer, render_part
from apothecary.projects.parts.texts import defaults_disagree


def _cube(size: float):
    """A cube of ``size`` from the origin as twelve triangles."""
    s = size
    corners = [(x, y, z) for x in (0, s) for y in (0, s) for z in (0, s)]
    faces = [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)]
    out = []
    for a, b, c, d in faces:
        out += [(corners[a], corners[b], corners[c]), (corners[a], corners[c], corners[d])]
    return out


def test_a_line_along_an_axis_meets_a_cube_at_its_two_faces():
    cube = _cube(10.0)
    assert crossings(cube, (0.0, 3.0, 4.0), 0) == [0.0, 10.0]
    assert crossings(cube, (3.0, 0.0, 4.0), 1) == [0.0, 10.0]
    # Down a diagonal of the top, through an edge two triangles share: once each face.
    assert crossings(cube, (5.0, 5.0, 0.0), 2) == [0.0, 10.0]
    assert crossings(cube, (12.0, 3.0, 0.0), 2) == []


def test_the_models_defaults_are_the_scads_literals():
    assert defaults_disagree(DEFAULT) == []


def _claims_hold(features) -> bool:
    found = MeasurePlan(features=list(features)).check()
    return all(found.get(name, False) for name in PLAN_SEPARATES)


def test_its_plan_separates_every_term_it_claims_and_breaking_it_shows():
    p = plan(Params())
    assert p.separates == list(PLAN_SEPARATES)
    assert p.check() == {name: True for name in PLAN_SEPARATES}
    assert [f.name for f in p.features][:2] == ["plate_x", "plate_y"]
    assert {f.nominal for f in p.features if f.kind == "outside" and f.axis == "x"} == {54, 20, 12}
    assert _claims_hold(p.features)
    # The holes left out: nothing says how far a hole's faces stand in.
    assert not _claims_hold(f for f in p.features if f.kind != "inside")
    # Every reading at the base left out: the first layer's spread is not told from the faces.
    above = MeasurePlan(features=[f for f in p.features if f.level != "base"])
    assert above.check().get("foot", False) is False
    # One top alone: a scale in Z and the first layer's height read the same.
    one_top = MeasurePlan(features=[f for f in p.features if f.name not in ("b_z", "a_z")])
    found = one_top.check()
    assert found["first"] is False and found["scale_z"] is False
    # The plan has readings to spare: any one feature left out, it still separates all.
    for left_out in p.features:
        assert _claims_hold(f for f in p.features if f is not left_out), left_out.name
    # The plate's two sizes and both pockets left out, the only outside size at the
    # base and the only inside sizes above are gone: the first layer's spread is
    # told from neither offset.
    gone = {"plate_x", "plate_y", "a_pocket_x", "a_pocket_y", "b_pocket_x", "b_pocket_y"}
    assert not _claims_hold(f for f in p.features if f.name not in gone)


def test_a_box_separates_nothing():
    found = box_plan((10.0, 10.0, 10.0)).check()
    assert found and not any(found.values())


@pytest.mark.parametrize(
    "values, says",
    [
        ({"b_size": 20, "b_pocket": 12}, "of two sizes"),
        ({"a_pocket": 18}, "under 2 mm of wall"),
        ({"plate_x": 45}, "along X"),
        ({"plate_y": 30}, "along Y"),
    ],
)
def test_a_coupon_that_could_not_separate_or_would_not_fit_is_refused(values, says):
    with pytest.raises(ValueError, match=says):
        Params(**values)


def test_the_render_has_every_feature_where_the_plan_draws_it(tmp_path):
    if not get_renderer().is_available:
        pytest.skip("OpenSCAD not installed")
    result = render_part(DEFAULT, tmp_path / "print_coupon.stl", params={}, timeout=180)
    assert result.success, result.stderr
    triangles = read_mesh(result.stl_path)
    lo, hi = bounds(triangles)
    declared = DEFAULT.get_bounds()
    assert list(lo) == pytest.approx(declared.min_point.to_list(), abs=1e-3)
    assert list(hi) == pytest.approx(declared.max_point.to_list(), abs=1e-3)
    drawn = DEFAULT.measures()
    for feature in drawn.features:
        found = feature.read_on(triangles)
        assert found is not None, feature.name
        assert found == pytest.approx(feature.faces, abs=MEASURE_TOLERANCE), feature.name
    # A plan drawn for another window and fin than the render's: those two are found off.
    other = plan(Params(window=9, fin_t=0.6))
    off = {
        f.name
        for f in other.features
        if f.read_on(triangles) != pytest.approx(f.faces, abs=MEASURE_TOLERANCE)
    }
    assert off == {"window_x", "window_y", "fin"}
