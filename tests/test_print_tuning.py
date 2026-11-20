"""What a printed piece's measurements say about the printer (apothecary/print_tuning.py),
each held to a case whose answer is known in closed form.

Where readings are made from the model and solved by it, the test holds the arithmetic:
the terms found again are the terms planted, which says nothing of a printer."""

from __future__ import annotations

import math

import pytest

from apothecary import print_tuning as pt

F = pt.Feature


def _reading(feature, *values, **kw):
    return pt.Reading(feature, tuple(values), **kw)


def _made(features, terms, **kw):
    """Readings that are each feature's nominal plus what ``terms`` give: the model's own."""
    return [_reading(f, f.nominal + pt.predicted(f, terms), **kw) for f in features]


# ---- the linear algebra -------------------------------------------------------------------


def test_jacobi_finds_the_eigenvalues_and_vectors_of_a_known_matrix():
    values, vectors = pt.symmetric_eigen([[2.0, 1.0], [1.0, 2.0]])
    assert sorted(round(v, 12) for v in values) == [1.0, 3.0]
    m = [[4.0, 1.0, 2.0], [1.0, 3.0, 0.5], [2.0, 0.5, 5.0]]
    values, v = pt.symmetric_eigen(m)
    for k, lam in enumerate(values):
        col = [v[i][k] for i in range(3)]
        product = [sum(m[i][j] * col[j] for j in range(3)) for i in range(3)]
        assert all(abs(product[i] - lam * col[i]) < 1e-10 for i in range(3))
    # The trace and the determinant are the sum and the product of the eigenvalues.
    assert math.isclose(sum(values), 12.0)
    det = 4 * (15 - 0.25) - 1 * (5 - 1) + 2 * (0.5 - 6)
    assert math.isclose(values[0] * values[1] * values[2], det)


# ---- the error model ------------------------------------------------------------------------


def test_each_kind_of_feature_is_moved_by_its_own_terms():
    assert pt.row(F("a", "outside", "x", 20, "base")) == {"scale_x": 20, "contour": 2, "foot": 2}
    assert pt.row(F("a", "outside", "y", 20)) == {"scale_y": 20, "contour": 2}
    assert pt.row(F("h", "inside", "x", 8, "base")) == {"scale_x": 8, "hole": -2, "foot": -2}
    assert pt.row(F("h", "inside", "y", 8)) == {"scale_y": 8, "hole": -2}
    assert pt.row(F("t", "height", "z", 12)) == {"scale_z": 12, "first": 1}
    assert pt.row(F("w", "wall", "x", 0.45)) == {}
    with pytest.raises(ValueError, match="a height is along Z"):
        F("t", "height", "x", 12)
    with pytest.raises(ValueError, match="a nominal size"):
        F("a", "outside", "x", 0)


def test_two_outside_sizes_along_x_tell_the_scale_from_the_faces():
    """e1 = N1 s + 2c and e2 = N2 s + 2c: s = (e1 - e2) / (N1 - N2), c = (e1 - N1 s) / 2,
    with errors from the readings' own: sigma sqrt(2) / |N1 - N2| and sigma sqrt(N1^2 +
    N2^2) / (2 |N1 - N2|), with no residual to check them."""
    a, b = F("a", "outside", "x", 20), F("b", "outside", "x", 12)
    e1, e2 = 0.16, 0.1
    found = pt.solve([_reading(a, 20 + e1), _reading(b, 12 + e2)])
    s, c = (e1 - e2) / 8, (e1 - 20 * (e1 - e2) / 8) / 2
    assert math.isclose(found.terms["scale_x"].value, s, abs_tol=1e-12)
    assert math.isclose(found.terms["contour"].value, c, abs_tol=1e-12)
    sigma = 0.01 / math.sqrt(12)
    assert math.isclose(found.terms["scale_x"].error, sigma * math.sqrt(2) / 8)
    assert math.isclose(found.terms["contour"].error, sigma * math.sqrt(20**2 + 12**2) / 16)
    assert found.dof == 0 and found.chi2 is None
    assert any("no residual checks the model" in s for s in found.said)


def test_one_cube_cannot_tell_a_scale_from_an_offset_and_says_so():
    """A cube's X, Y and Z: each a sum of terms no other reading separates."""
    cube = [
        _reading(F("x", "outside", "x", 10, "base"), 10.12),
        _reading(F("y", "outside", "y", 10, "base"), 10.08),
        _reading(F("z", "height", "z", 10), 9.98),
    ]
    found = pt.solve(cube)
    assert not any(t.determined for t in found.terms.values())
    assert found.terms["contour"].value is None
    assert set(found.terms["contour"].with_) == {"scale_x", "scale_y", "foot"}
    words = " ".join(found.said)
    assert "cannot tell scale_x, scale_y, contour and foot apart" in words
    # One height: a scale of 0.1 % and a first layer 0.01 mm thinner read the same.
    assert "cannot tell scale_z and first apart: scale_z +0.10%, first -0.01 mm" in words


def test_the_earlier_rule_is_the_cube_with_scale_and_foot_assumed_none():
    """xy_contour_compensation's earlier rule took a cube's X and Y errors as the walls'
    alone: with the scales and the foot assumed nothing, the walls are half the mean."""
    found = pt.solve(
        [
            _reading(F("x", "outside", "x", 10, "base"), 10.12),
            _reading(F("y", "outside", "y", 10, "base"), 10.08),
        ],
        {"scale_x": 0.0, "scale_y": 0.0, "foot": 0.0},
    )
    assert math.isclose(found.terms["contour"].value, 0.05)
    assert found.terms["scale_x"].assumed and found.terms["scale_x"].value == 0.0
    # The two disagree by 0.04 mm, far past a 0.01 mm caliper's step: the residuals,
    # not the resolution, give the walls' error.
    assert found.chi2 > 1 and math.isclose(found.terms["contour"].error, 0.01)


def test_an_outside_and_an_inside_size_err_opposite_ways_for_the_faces_alike_for_a_scale():
    out_, in_ = F("o", "outside", "x", 10), F("i", "inside", "x", 10)
    faces = {"contour": 0.05, "hole": 0.05}
    assert pt.predicted(out_, faces) == 0.1 and pt.predicted(in_, faces) == -0.1
    scale = {"scale_x": 0.01}
    assert pt.predicted(out_, scale) == pt.predicted(in_, scale) == 0.1
    # One of each, of one size: three terms, two readings; not separable.
    found = pt.solve([_reading(out_, 10.1), _reading(in_, 9.9)])
    assert not found.terms["scale_x"].determined


def test_a_planted_error_is_found_again_from_the_models_own_readings():
    """The coupon's plan with every term planted: each found to rounding, with readings
    to spare and a fit that leaves nothing. The readings came from the model: this holds
    the arithmetic, not a printer."""
    plan = [
        F("plate_x", "outside", "x", 50, "base"),
        F("plate_y", "outside", "y", 36, "base"),
        F("a_x", "outside", "x", 20),
        F("a_y", "outside", "y", 20),
        F("b_x", "outside", "x", 12),
        F("b_y", "outside", "y", 12),
        F("a_pocket_x", "inside", "x", 12),
        F("a_pocket_y", "inside", "y", 12),
        F("b_pocket_x", "inside", "x", 6),
        F("b_pocket_y", "inside", "y", 6),
        F("window_x", "inside", "x", 8, "base"),
        F("window_y", "inside", "y", 8, "base"),
        F("plate_z", "height", "z", 2),
        F("b_z", "height", "z", 8),
        F("a_z", "height", "z", 12),
    ]
    planted = {
        "scale_x": 0.004,
        "scale_y": -0.003,
        "scale_z": 0.002,
        "contour": 0.06,
        "hole": 0.08,
        "foot": 0.1,
        "first": -0.05,
    }
    found = pt.solve(_made(plan, planted))
    assert found.rank == 7 and found.dof == 8
    for name, value in planted.items():
        assert math.isclose(found.terms[name].value, value, abs_tol=1e-9), name
        assert found.terms[name].resolved
    assert found.chi2 < 1e-12
    assert pt.separable(plan) == {name: True for name in planted}
    # Without the holes, nothing says how far a hole's faces stand in: red.
    assert not pt.separable(f for f in plan if f.kind != "inside").get("hole", False)
    # Without the heights' second top, a scale and a first layer read the same.
    no_second = [f for f in plan if f.name not in ("b_z", "a_z")]
    assert pt.separable(no_second)["first"] is False


# ---- measurement quality ----------------------------------------------------------------------


def test_a_readings_uncertainty_is_its_resolution_its_spread_and_its_layer():
    one = _reading(F("a", "outside", "x", 20), 20.1)
    assert math.isclose(one.uncertainty, 0.01 / math.sqrt(12))
    assert one.understated
    three = _reading(F("a", "outside", "x", 20), 20.08, 20.1, 20.12)
    assert math.isclose(three.spread, 0.02)
    assert math.isclose(three.uncertainty, math.sqrt(0.01**2 / 12 + 0.02**2 / 3))
    assert not three.understated
    stated = _reading(F("a", "outside", "x", 20), 20.1, 20.1, repeatability=0.03)
    assert math.isclose(stated.uncertainty, math.sqrt(0.01**2 / 12 + 0.03**2 / 2))
    assert pt.layer_quantum(2.0, 0.2, 0.2) == 0.0
    assert pt.layer_quantum(12.0, 0.2, 0.2) == 0.0
    assert math.isclose(pt.layer_quantum(2.1, 0.2, 0.2), 0.2 / math.sqrt(12))
    assert math.isclose(pt.layer_quantum(2.0, 0.3, 0.2), 0.2 / math.sqrt(12))


def test_a_term_smaller_than_its_readings_resolve_gets_no_step():
    a, b = F("a", "outside", "x", 20), F("b", "outside", "x", 12)
    noisy = pt.solve(
        [_reading(a, 20.01, 20.05, 19.99), _reading(b, 12.0, 12.04, 11.98)],
    )
    contour = noisy.terms["contour"]
    assert contour.determined and not contour.resolved
    said = pt.step(contour, pt.RELATIONS["take_out"], 0.0, pt.Limits(-0.5, 0.5, 0.1))
    assert said.new is None and "smaller than the readings resolve" in said.why


# ---- a step -----------------------------------------------------------------------------------


def _solved(name, value, error=0.001):
    return pt.Solved(name, value, error, True, resolved=abs(value) > pt.RESOLVE * error)


def test_each_relation_takes_out_what_it_says_and_a_turn_takes_half():
    limits = pt.Limits(-0.5, 0.5, 0.2)
    # Faces standing out by 0.06: the walls drawn 0.06 further in, half of it a turn.
    s = pt.step(_solved("contour", 0.06), pt.RELATIONS["take_out"], -0.02, limits)
    assert math.isclose(s.whole, -0.08) and math.isclose(s.new, -0.05)
    assert math.isclose(s.expected, 0.03)
    # A hole closed by 0.08 a side: the hole drawn 0.08 wider, half of it a turn.
    s = pt.step(_solved("hole", 0.08), pt.RELATIONS["put_back"], 0.0, limits)
    assert math.isclose(s.whole, 0.08) and math.isclose(s.new, 0.04)
    assert math.isclose(s.expected, 0.04)
    # 94 mm for 100 at 100 %: 94 % leaves none (the slicer's own example).
    shrink = pt.Limits(95, 105, 10)
    s = pt.step(_solved("scale_x", -0.06), pt.RELATIONS["percent"], 100.0, shrink, damping=1.0)
    assert math.isclose(s.whole, 94.0)
    assert s.new == 95  # held at its limit
    assert math.isclose(s.expected, 0.94 * 100 / 95 - 1)
    s = pt.step(_solved("scale_x", 0.004), pt.RELATIONS["percent"], 100.0, shrink)
    assert math.isclose(s.new, 100.2) and math.isclose(s.expected, 1.004 / 1.002 - 1)


def test_a_step_is_never_more_than_one_turns_most_nor_past_a_limit():
    s = pt.step(_solved("foot", 0.4), pt.RELATIONS["put_back"], 0.1, pt.Limits(0, 0.5, 0.1))
    assert math.isclose(s.new, 0.2) and "most one turn" in s.why
    s = pt.step(_solved("foot", 0.4), pt.RELATIONS["put_back"], 0.45, pt.Limits(0, 0.5, 0.1))
    assert s.new == 0.5 and "limit" in s.why
    s = pt.step(_solved("foot", 0.4), pt.RELATIONS["put_back"], 0.5, pt.Limits(0, 0.5, 0.1))
    assert s.new is None and "it is there" in s.why
    s = pt.step(
        pt.Solved("contour", None, None, False, with_=("scale_x",)),
        pt.RELATIONS["take_out"],
        0.0,
        pt.Limits(-0.5, 0.5, 0.1),
    )
    assert s.new is None and "not determined: scale_x read the same" in s.why


# ---- convergence ------------------------------------------------------------------------------


def _points(*values, error=0.005, expected=None):
    return [
        pt.Point(f"turn-{i + 1}", v, error, stepped=True, expected=(expected or {}).get(i))
        for i, v in enumerate(values)
    ]


def test_the_turns_say_whether_a_term_shrinks_oscillates_stalls_or_grows():
    t = pt.trend("contour", _points(0.08, 0.04, expected={0: 0.04}))
    assert (t.state, t.stop) == ("shrinking", False)
    t = pt.trend("contour", _points(0.08, -0.05, expected={0: 0.04}))
    assert (t.state, t.damping, t.stop) == ("oscillating", 0.25, False)
    t = pt.trend("contour", _points(0.08, 0.079, expected={0: 0.04}))
    assert (t.state, t.stop) == ("not responding", True)
    assert "does not govern this error" in t.said
    t = pt.trend("contour", _points(0.08, 0.12, expected={0: 0.04}))
    assert (t.state, t.stop) == ("growing", True)
    t = pt.trend("contour", _points(0.08, 0.004, expected={0: 0.04}))
    assert t.state == "within resolution"
    t = pt.trend("contour", _points(0.08))
    assert t.state == "one turn"
    t = pt.trend("contour", [pt.Point("turn-1", 0.08, 0.005, stepped=False), *_points(0.07)[0:]])
    assert t.state == "not stepped"


def test_a_planted_turn_converges_as_damped_steps_take_it_out():
    """A printer whose faces stand out by 0.08 mm, its walls moved by half the error each
    turn: the error halves each turn, and the loop says it shrinks, then that it is within
    what the readings resolve. The printer here is the model: this holds the loop's
    arithmetic, not a printer's response."""
    a, b = F("a", "outside", "x", 20), F("b", "outside", "x", 12)
    true_faces, setting, points = 0.08, 0.0, []
    for k in range(8):
        error = true_faces + setting  # the setting moves the faces as it says
        found = pt.solve(_made([a, b], {"contour": error, "scale_x": 0.0}, repeatability=0.002))
        contour = found.terms["contour"]
        trend = pt.trend(
            "contour", points + [pt.Point(f"turn-{k + 1}", contour.value, contour.error, False)]
        )
        if trend.state == "within resolution":
            break
        s = pt.step(contour, pt.RELATIONS["take_out"], setting, pt.Limits(-0.5, 0.5, 0.1))
        points.append(pt.Point(f"turn-{k + 1}", contour.value, contour.error, True, s.expected))
        setting = s.new
    assert trend.state == "within resolution"
    assert [round(p.value, 4) for p in points[:3]] == [0.08, 0.04, 0.02]
