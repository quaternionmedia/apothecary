"""A control loop's maths (``apothecary.control_loops``), each against an answer known
without it.

Plants against their step formulas; the PID's two forms against each other and the
running controller against its z-domain response; margins against loops whose margins
have closed forms; identification against data drawn from a known plant, with noise and
one sample a second, recovered within a tolerance stated here; the relay's describing
function against the exact limit cycle of a FOPDT, which says how far the relation is
off; and the rules against their formulas and, where a rule was designed for a
robustness, that robustness. Data drawn from the same model the code fits shows the code
works, not that a machine is that model.
"""

from __future__ import annotations

import cmath
import math
import random

import pytest

from apothecary.control_loops import (
    FOPDT,
    LEFT_OUT,
    PID,
    RULES,
    SOPDT,
    Loop,
    PIDRunner,
    PlantRunner,
    Standard,
    Ultimate,
    areas,
    bode,
    closed_loop,
    design,
    filter_of,
    fit_fopdt,
    fopdt_relay_exact,
    frequency_response,
    hold,
    loop_margins,
    margins,
    oscillation,
    relay_point,
    relay_run,
    resample,
    series_to_standard,
    smoothing,
    step_measures,
    two_point,
    ultimate_of,
)

HEATER = FOPDT(2.0, 60.0, 8.0)  # a made-up heater: no machine's numbers


def _wrap(deg: float) -> float:
    return (deg + 180) % 360 - 180


# ---- plants -------------------------------------------------------------------------------


class TestPlants:
    def test_a_fopdt_answers_its_closed_forms(self):
        p = HEATER
        assert p.step(8.0) == 0 and p.step(8.0 + 60.0) == pytest.approx(2 * (1 - math.exp(-1)))
        g = p.response(1 / 60)
        assert abs(g) == pytest.approx(2 / math.sqrt(2))
        assert math.degrees(p.phase(1 / 60)) == pytest.approx(-45 - math.degrees(8 / 60))
        assert _wrap(math.degrees(cmath.phase(g))) == pytest.approx(
            _wrap(math.degrees(p.phase(1 / 60)))
        )

    @pytest.mark.parametrize(
        "plant, h",
        [(HEATER, 0.5), (SOPDT(1.5, 40.0, 10.0, 5.0), 0.25), (SOPDT(1.5, 20.0, 20.0, 5.0), 0.25)],
        ids=["fopdt", "sopdt", "sopdt-equal-lags"],
    )
    def test_the_runner_is_the_exact_step_when_the_dead_time_is_whole_steps(self, plant, h):
        runner = PlantRunner(plant, h)
        worst = max(abs(runner.step(1.0) - plant.step((i + 1) * h)) for i in range(800))
        assert worst < 1e-12

    def test_a_dead_time_between_steps_is_rounded_and_said(self):
        runner = PlantRunner(FOPDT(1, 10, 1.26), 0.5)
        assert runner.steps == 3 and runner.dead_time_used == 1.5

    def test_a_runner_started_settled_stays_put(self):
        runner = PlantRunner(SOPDT(2, 30, 5, 3), 0.1, start=40.0)
        assert all(runner.step(40.0) == pytest.approx(80.0) for _ in range(100))

    def test_a_plant_needs_a_lag_and_no_negative_dead_time(self):
        with pytest.raises(ValueError):
            FOPDT(1, 0)
        with pytest.raises(ValueError):
            SOPDT(1, 1, 1, -1)


# ---- the PID ------------------------------------------------------------------------------


class TestThePID:
    def test_the_parallel_and_ideal_forms_convert_exactly_both_ways(self):
        pid = PID(kp=21.5, ki=1.25, kd=92.0, dt=0.164)
        std = pid.standard()
        assert (std.kc, std.ti, std.td) == (21.5, 21.5 / 1.25, 92.0 / 21.5)
        back = std.parallel(dt=0.164)
        assert (back.kp, back.ki, back.kd) == pytest.approx((21.5, 1.25, 92.0), rel=1e-15)
        p_only = Standard(3.0).parallel(1.0)
        assert p_only.ki == 0 and p_only.standard().ti == math.inf

    def test_a_series_pid_is_the_ideal_one_it_equals(self):
        std = series_to_standard(1.0, 4.0, 1.0)
        assert (std.kc, std.ti, std.td) == pytest.approx((1.25, 5.0, 0.8))
        # The two are one controller: their responses agree at any frequency.
        for w in (0.01, 0.3, 2.0):
            s = 1j * w
            series = 1.0 * (1 + 1 / (4.0 * s)) * (1 + 1.0 * s)
            assert std.parallel(1.0).response(w) == pytest.approx(series)

    def test_the_filter_and_its_smoothing_are_one_another(self):
        assert smoothing(filter_of(0.95, 0.164), 0.164) == pytest.approx(0.95)
        assert filter_of(0.95, 0.1) == pytest.approx(1.9)
        with pytest.raises(ValueError):
            filter_of(1.0, 0.1)

    def test_the_runner_is_its_z_domain_response(self):
        """A unit step of the error, the derivative on the error: ``u_k = kp + ki dt (k + 1)
        + kd (1 - a) a^k / dt``, which is ``C(z)`` applied to a step."""
        pid = PID(kp=2.0, ki=0.5, kd=3.0, dt=0.2, filter=0.6, derivative="error")
        a = smoothing(0.6, 0.2)
        runner = PIDRunner(pid, low=-1e9, high=1e9)
        runner.update(0.0, 0.0)  # at rest, no error
        for k in range(30):
            u = runner.update(1.0, 0.0)
            assert u == pytest.approx(2.0 + 0.5 * 0.2 * (k + 1) + 3.0 * (1 - a) * a**k / 0.2)

    def test_the_sampled_response_tends_to_the_continuous_one(self):
        pid = PID(kp=2.0, ki=0.5, kd=3.0, dt=1e-4, filter=0.6)
        for w in (0.05, 0.5, 2.0):
            assert pid.response(w, sampled=True) == pytest.approx(pid.response(w), rel=1e-3)

    def test_a_clamped_output_winds_up_no_integral(self):
        runner = PIDRunner(PID(kp=1.0, ki=1.0, dt=1.0), low=0.0, high=10.0)
        for _ in range(50):
            assert runner.update(100.0, 0.0) == 10.0
        assert runner.integral == 0.0
        # Once the error turns, the output leaves the clamp at once.
        assert runner.update(0.0, 5.0) == 0.0


# ---- margins ------------------------------------------------------------------------------


class TestMargins:
    """``L = K e^(-theta s) / s``: crossover K, phase margin 90 - K theta (rad), phase
    crossover pi/(2 theta), gain margin pi/(2 K theta). ``L = k / (s (s + 1))``: the closed
    loop is second order with ``zeta = 1/(2 sqrt(k))``, so ``Mt = 1/(2 zeta sqrt(1 -
    zeta^2))``; no phase crossover."""

    K, TH = 0.5, 1.0

    def _integrator(self, w):
        return self.K * cmath.exp(-1j * self.TH * w) / (1j * w)

    @pytest.mark.parametrize("analytic", [True, False], ids=["analytic-phase", "unwrapped"])
    def test_an_integrator_with_a_delay(self, analytic):
        phase = (lambda w: -math.pi / 2 - self.TH * w) if analytic else None
        m = margins(self._integrator, phase, 1e-3, 1e2)
        assert m.gain_crossover == pytest.approx(self.K)
        assert m.phase_margin == pytest.approx(90 - math.degrees(self.K * self.TH))
        assert m.phase_crossover == pytest.approx(math.pi / (2 * self.TH))
        assert m.gain_margin == pytest.approx(math.pi / (2 * self.K * self.TH))
        assert m.gain_margin_db == pytest.approx(20 * math.log10(math.pi))

    def test_a_second_order_loop(self):
        k = 4.0
        m = margins(lambda w: k / ((1j * w) * (1j * w + 1)), None, 1e-3, 1e3)
        zeta = 1 / (2 * math.sqrt(k))
        assert m.mt == pytest.approx(1 / (2 * zeta * math.sqrt(1 - zeta**2)), rel=1e-6)
        wc = math.sqrt((-1 + math.sqrt(1 + 4 * k * k)) / 2)
        assert m.phase_margin == pytest.approx(90 - math.degrees(math.atan(wc)))
        assert m.gain_margin is None and m.phase_crossover is None

    def test_the_sensitivity_peak_is_the_densest_grid_s(self):
        m = margins(self._integrator, None, 1e-3, 1e2)
        dense = max(
            abs(1 / (1 + self._integrator(1e-3 * 1e5 ** (i / 200000)))) for i in range(200001)
        )
        assert m.ms == pytest.approx(dense, rel=1e-6)

    def test_simc_with_its_default_closed_loop_time_is_its_published_loop(self):
        """With ``tau_c = theta`` and ``tau <= 8 theta`` SIMC's PI cancels the lag and the
        loop is ``e^(-theta s) / (2 theta s)``: gain margin pi, phase margin 61.4 degrees,
        the figures Skogestad (2003) gives for it."""
        plant = FOPDT(2.0, 30.0, 8.0)
        d = design("simc", plant=plant, kind="pi", dt=0.01)
        m = loop_margins(Loop(plant, d.pid, sampled=False))
        assert m.gain_margin == pytest.approx(math.pi, rel=1e-6)
        assert m.phase_margin == pytest.approx(90 - math.degrees(0.5), rel=1e-6)

    def test_a_sampled_loop_loses_phase_to_its_hold(self):
        plant = HEATER
        pid = design("simc", plant=plant, kind="pi", dt=0.5).pid
        cont = loop_margins(Loop(plant, pid, sampled=False))
        held = loop_margins(Loop(plant, pid, sampled=True))
        assert held.phase_margin < cont.phase_margin
        # About half a sample's delay at the crossover, plus the integral's rectangles.
        lost = cont.phase_margin - held.phase_margin
        assert lost == pytest.approx(math.degrees(cont.gain_crossover * 0.5 / 2), rel=0.5)
        assert hold(0.0, 1.0) == 1 and abs(hold(math.pi, 1.0)) == pytest.approx(2 / math.pi)

    def test_bode_curves_cover_the_span(self):
        curves = bode(Loop(HEATER, PID(kp=1.0, ki=0.02, dt=1.0)), n=50)
        assert set(curves) == {
            "w",
            "plant_mag",
            "plant_phase",
            "loop_mag",
            "loop_phase",
            "s_mag",
            "t_mag",
        }
        assert all(len(v) == 50 for v in curves.values())
        assert curves["w"][-1] < math.pi  # half the sampling rate, at one sample a second


# ---- identification -----------------------------------------------------------------------


def _step_data(seed: int, sigma: float = 0.2, dt: float = 1.0):
    """The heater stepped by 20 at t = 10 from 25, read every ``dt`` with Gaussian noise."""
    rng = random.Random(seed)
    t = [i * dt for i in range(int(600 / dt) + 1)]
    return t, [25 + HEATER.step(s - 10, 20) + rng.gauss(0, sigma) for s in t]


class TestIdentification:
    def test_both_step_methods_are_exact_on_a_fopdt(self):
        t = [i * 0.05 for i in range(24001)]
        y = [HEATER.step(s) for s in t]
        for method in (two_point, areas):
            p = method(t, y, 1.0).plant
            assert (p.gain, p.time_constant, p.dead_time) == pytest.approx(
                (2.0, 60.0, 8.0), rel=2e-3
            )

    @pytest.mark.parametrize(
        "method, tau_tol, theta_tol",
        [(two_point, 0.05, 1.5), (areas, 0.02, 0.6)],
        ids=["two-point", "areas"],
    )
    def test_one_sample_a_second_with_noise_is_recovered_within_a_stated_tolerance(
        self, method, tau_tol, theta_tol
    ):
        """Twenty seeds, a standard deviation of 0.2 on a change of 40: the gain within
        1 %, the time constant and the dead time within what the method's parameters say.
        The area method averages the noise; the two points read it."""
        for seed in range(20):
            t, y = _step_data(seed)
            p = method(t, y, 20.0, step_time=10.0).plant
            assert p.gain == pytest.approx(2.0, rel=0.01)
            assert p.time_constant == pytest.approx(60.0, rel=tau_tol)
            assert p.dead_time == pytest.approx(8.0, abs=theta_tol)

    def test_a_fit_is_exact_on_noise_free_closed_loop_data(self):
        pid = PID(kp=1.875, ki=0.03125, dt=1.0)
        for plant in (HEATER, FOPDT(2.0, 60.0, 7.3)):
            trace = closed_loop(
                plant, pid, lambda s: 200.0 if s < 50 else 205.0, 600, ambient=25.0, substeps=100
            )
            found = fit_fopdt(trace.u, trace.y, 1.0)
            p = found.plant
            assert (p.gain, p.time_constant, p.dead_time) == pytest.approx(
                (plant.gain, plant.time_constant, plant.dead_time), rel=1e-6
            )
            assert found.initial == pytest.approx(25.0)

    def test_a_fit_to_a_noisy_closed_loop_read_once_a_second(self):
        """The PID runs ten times a second and the record is one snapshot of its output a
        second, with noise of 0.05 on the reading: ten seeds within 10 % in the gain and the
        time constant and a second in the dead time. With noise of 0.2 the snapshot's own
        noise carries the gain a quarter off; that is the fit's weakest part."""
        pid = design("simc", plant=HEATER, kind="pi", dt=0.1).pid
        for seed in range(10):
            trace = closed_loop(
                HEATER,
                pid,
                lambda s: 200.0 if s < 60 else 205.0,
                900,
                ambient=25.0,
                sample=1.0,
                noise=0.05,
                seed=seed,
            )
            p = fit_fopdt(trace.u, trace.y, 1.0).plant
            assert p.gain == pytest.approx(2.0, rel=0.1)
            assert p.time_constant == pytest.approx(60.0, rel=0.1)
            assert p.dead_time == pytest.approx(8.0, abs=1.0)

    def test_a_fit_refuses_an_input_that_never_moves(self):
        with pytest.raises(ValueError, match="does not move"):
            fit_fopdt([1.0] * 20, [float(i) for i in range(20)], 1.0)


class TestTheRelay:
    @pytest.mark.parametrize("theta", [2.0, 8.0, 20.0])
    def test_a_simulated_relay_holds_the_exact_limit_cycle(self, theta):
        plant = FOPDT(2.0, 60.0, theta)
        a, period = fopdt_relay_exact(plant, 50.0)
        trace = relay_run(plant, setpoint=0.0, bias=0.0, amplitude=50.0, duration=1500, h=0.01)
        found = oscillation(trace.t, trace.y, 0.0)
        assert found.amplitude == pytest.approx(a, abs=0.02)
        assert found.period == pytest.approx(period, abs=0.05)

    @pytest.mark.parametrize("theta", [2.0, 8.0, 20.0])
    def test_the_describing_function_reads_the_ultimate_gain_low_for_a_fopdt(self, theta):
        """The relation keeps the first harmonic alone. On a FOPDT the true oscillation
        (``fopdt_relay_exact``) puts it 15 to 20 % under the true ultimate gain and within
        2.5 % of the ultimate period, for dead times of a thirtieth to a third of the lag."""
        plant = FOPDT(2.0, 60.0, theta)
        a, period = fopdt_relay_exact(plant, 50.0)
        found = relay_point(50.0, a, period)
        true = ultimate_of(plant)
        assert -0.20 < found.ultimate_gain / true.gain - 1 < -0.15
        assert found.ultimate_period == pytest.approx(true.period, rel=0.025)

    def test_the_ultimate_point_is_where_the_phase_is_a_half_turn(self):
        u = ultimate_of(HEATER)
        w = 2 * math.pi / u.period
        assert HEATER.phase(w) == pytest.approx(-math.pi)
        assert u.gain * abs(HEATER.response(w)) == pytest.approx(1.0)
        with pytest.raises(ValueError, match="never reaches"):
            ultimate_of(FOPDT(1.0, 10.0))

    def test_a_relay_read_once_a_second_with_noise_and_hysteresis(self):
        """Decided once a second on a reading with noise of 0.2, with a hysteresis of 1: the
        point the oscillation sits on is ``-180 + asin(eps/a)`` degrees of the plant, and the
        plant's own phase and magnitude at the frequency found are within 12 degrees and
        25 % of what the relation says -- the first harmonic, a second's late switching
        and the noise between them."""
        trace = relay_run(
            HEATER,
            setpoint=0.0,
            bias=0.0,
            amplitude=50.0,
            duration=1800,
            hysteresis=1.0,
            h=0.05,
            decide_every=1.0,
            noise=0.2,
            seed=7,
        )
        found = oscillation(trace.t, trace.y, 0.0, last=5)
        point = relay_point(50.0, found.amplitude, found.period, hysteresis=1.0)
        assert point.ultimate_gain is None  # with hysteresis it is not the ultimate point
        assert math.degrees(HEATER.phase(point.frequency)) == pytest.approx(point.phase_deg, abs=12)
        assert abs(HEATER.response(point.frequency)) == pytest.approx(point.magnitude, rel=0.25)

    def test_a_relay_point_refuses_what_has_no_point(self):
        with pytest.raises(ValueError):
            relay_point(10.0, 1.0, 30.0, hysteresis=1.0)
        with pytest.raises(ValueError):
            relay_point(0.0, 1.0, 30.0)


class TestFrequencyResponse:
    """A closed loop driven by a square wave of the setpoint, 200 +/- 2 with a period of
    120 s, read once a second: the plant at the odd harmonics, against its own response.
    The setpoint changes half a second after a reading. The controller's output jumps
    with it, and a jump read on a reading's instant is read as half a sample early: the
    plant's phase would come out half a sample late (6 degrees at the fifth harmonic)."""

    P = 120.0

    def _trace(self, noise: float, periods: int = 7):
        pid = design("simc", plant=HEATER, kind="pi", dt=0.1).pid
        square = lambda s: 200.0 + (2.0 if ((s - 0.5) % self.P) < self.P / 2 else -2.0)  # noqa: E731
        return closed_loop(
            HEATER, pid, square, self.P * periods, ambient=25.0, sample=1.0, noise=noise, seed=3
        )

    def test_noise_free_the_low_harmonics_are_the_plant(self):
        """Within 1 % and 1 degree up to the fifth harmonic. Higher, the input's edges
        alias at one sample a second and the estimate drifts (10 % low by the 21st), which
        the coherence, being 1, does not show: the reference page says so."""
        tr = self._trace(0.0)
        for q in frequency_response(tr.u, tr.y, 1.0, self.P, (1, 3, 5), reference=tr.r, skip=120):
            g = HEATER.response(q.frequency)
            assert q.magnitude == pytest.approx(abs(g), rel=0.01)
            assert _wrap(q.phase_deg - math.degrees(cmath.phase(g))) == pytest.approx(0, abs=1)
            assert q.trust == "good" and q.segments == 6

    def test_with_noise_good_points_hold_and_poor_ones_are_said(self):
        tr = self._trace(0.1)
        points = frequency_response(
            tr.u, tr.y, 1.0, self.P, (1, 3, 5, 7, 9, 11, 21), reference=tr.r, skip=120
        )
        trusted = [q for q in points if q.trust == "good"]
        assert [round(q.frequency * self.P / (2 * math.pi)) for q in trusted] == [1, 3, 5]
        for q in trusted:
            g = HEATER.response(q.frequency)
            assert q.magnitude == pytest.approx(abs(g), rel=0.03)
            assert _wrap(q.phase_deg - math.degrees(cmath.phase(g))) == pytest.approx(0, abs=3)
        assert points[-1].trust == "poor" and points[-1].coherence < 0.6

    def test_one_period_says_nothing_of_its_coherence_and_nyquist_is_the_edge(self):
        tr = self._trace(0.1, periods=2)
        points = frequency_response(
            tr.u, tr.y, 1.0, self.P, (1, 3, 60, 61), reference=tr.r, skip=120
        )
        assert [q.trust for q in points] == ["unknown", "unknown"]  # 60 and 61: at or past Nyquist
        with pytest.raises(ValueError, match="whole number of samples"):
            frequency_response(tr.u, tr.y, 1.0, 120.5)

    def test_polls_at_uneven_times_are_read_onto_an_even_grid(self):
        t, v = resample([0.0, 0.9, 2.1, 3.0], [0.0, 0.9, 2.1, 3.0], 1.0)
        assert t == [0.0, 1.0, 2.0, 3.0] and v == pytest.approx([0.0, 1.0, 2.0, 3.0])


# ---- rules --------------------------------------------------------------------------------


class TestRules:
    def test_every_rule_names_its_source_and_what_it_assumes(self):
        for rule in RULES.values():
            assert rule.source and rule.assumes and rule.relation and rule.kinds
        assert set(LEFT_OUT).isdisjoint(RULES)

    def test_the_ultimate_rules_are_their_constants(self):
        u = Ultimate(10.0, 40.0)
        zn = design("zn_ultimate", ultimate=u, dt=1.0).standard
        assert (zn.kc, zn.ti, zn.td) == pytest.approx((6.0, 20.0, 5.0))
        pi = design("zn_ultimate", ultimate=u, kind="pi", dt=1.0).standard
        assert (pi.kc, pi.ti) == pytest.approx((4.5, 40 / 1.2))
        tl = design("tyreus_luyben", ultimate=u, dt=1.0).standard
        assert (tl.kc, tl.ti, tl.td) == pytest.approx((10 / 2.2, 88.0, 40 / 6.3))

    def test_ziegler_nichols_in_the_parallel_form_is_kp_two_kp_over_tu_and_kp_tu_over_8(self):
        """``Ki = 2 Kp / Tu`` and ``Kd = Kp Tu / 8``: the parallel form of 0.6 Ku, Tu/2, Tu/8."""
        u = Ultimate(10.0, 40.0)
        pid = design("zn_ultimate", ultimate=u, dt=1.0).pid
        assert (pid.ki, pid.kd) == pytest.approx((2 * pid.kp / 40.0, pid.kp * 40.0 / 8))

    def test_the_plant_rules_are_their_formulas(self):
        p = FOPDT(2.0, 60.0, 8.0)
        r = 8.0 / 60.0
        a = 2.0 * 8.0 / 60.0
        zr = design("zn_reaction", plant=p, dt=1.0).standard
        assert (zr.kc, zr.ti, zr.td) == pytest.approx((1.2 / a, 16.0, 4.0))
        cc = design("cohen_coon", plant=p, dt=1.0).standard
        assert (cc.kc, cc.ti, cc.td) == pytest.approx(
            ((60 / 16) * (4 / 3 + r / 4), 8 * (32 + 6 * r) / (13 + 8 * r), 32 / (11 + 2 * r))
        )
        simc = design("simc", plant=p, kind="pi", dt=1.0, closed_loop_time=4.0).standard
        assert (simc.kc, simc.ti) == pytest.approx((60 / (2 * 12), 48.0))

    def test_simc_pid_on_a_sopdt_is_its_series_form_made_ideal(self):
        p = SOPDT(2.0, 60.0, 10.0, 8.0)
        std = design("simc", plant=p, dt=1.0).standard
        series = series_to_standard(60 / (2 * 16), min(60.0, 64.0), 10.0)
        assert (std.kc, std.ti, std.td) == pytest.approx((series.kc, series.ti, series.td))

    def test_imc_pid_is_the_imc_controller_with_the_dead_time_pade_approximated(self):
        """``C = q / (1 - G q)`` with ``G`` the plant, its dead time by first-order Pade, and
        ``q = (tau s + 1)(1 + theta s/2) / (K (lambda s + 1))``: the PID the rule gives is that
        controller, at any frequency."""
        p, lam = FOPDT(2.0, 60.0, 8.0), 5.0
        pid = design("imc", plant=p, dt=1.0, closed_loop_time=lam).pid
        for w in (0.003, 0.05, 0.4):
            s = 1j * w
            pade = (1 - 8.0 * s / 2) / (1 + 8.0 * s / 2)
            g = 2.0 * pade / (60.0 * s + 1)
            q = (60.0 * s + 1) * (1 + 8.0 * s / 2) / (2.0 * (lam * s + 1))
            assert pid.response(w) == pytest.approx(q / (1 - g * q), rel=1e-12)

    @pytest.mark.parametrize("ratio", [0.05, 0.1, 0.3, 1.0, 3.0])
    def test_amigo_pid_holds_the_sensitivity_it_was_chosen_for(self, ratio):
        """AMIGO was chosen for a maximum sensitivity of about 1.4; across dead times of a
        twentieth to three times the lag its PID gives 1.4 within 0.02 here, which is the
        constants' corroboration, not their source."""
        p = FOPDT(1.0, 1.0, ratio)
        d = design("amigo", plant=p, dt=1e-3)
        m = loop_margins(Loop(p, d.pid, sampled=False))
        assert m.ms == pytest.approx(1.4, abs=0.02)
        pi = design("amigo", plant=p, kind="pi", dt=1e-3)
        assert 1.2 < loop_margins(Loop(p, pi.pid, sampled=False)).ms < 1.46

    def test_a_rule_is_asked_for_what_it_takes(self):
        with pytest.raises(ValueError, match="no rule"):
            design("guess", plant=HEATER)
        with pytest.raises(ValueError, match="takes a plant"):
            design("cohen_coon", ultimate=Ultimate(1, 1))
        with pytest.raises(ValueError, match="gives pi, pid, not p"):
            design("cohen_coon", plant=HEATER, kind="p")
        with pytest.raises(ValueError, match="for a SOPDT"):
            design("simc", plant=HEATER, kind="pid")
        # An ultimate rule given only a plant finds the plant's ultimate point.
        assert design("zn_ultimate", plant=HEATER, dt=1.0).standard.kc == pytest.approx(
            0.6 * ultimate_of(HEATER).gain
        )


# ---- a recorded step ----------------------------------------------------------------------


class TestStepMeasures:
    def test_a_first_order_step(self):
        """``1 - e^(-t/tau)``: rise ``tau ln 9``, settling into 2 % ``tau ln 50``, no
        overshoot, and an IAE of ``tau`` against a setpoint of 1."""
        tau, dt = 10.0, 0.001
        t = [i * dt for i in range(200001)]
        y = [1 - math.exp(-s / tau) for s in t]
        m = step_measures(t, y, setpoint=[1.0] * len(t), tail=0.01)
        assert m.rise_time == pytest.approx(tau * math.log(9), abs=2 * dt)
        assert m.settling_time == pytest.approx(tau * math.log(50), abs=2 * dt)
        assert m.overshoot == 0 and m.peak_time is None
        assert m.iae == pytest.approx(tau, rel=1e-4) and m.steady_error == pytest.approx(
            0, abs=1e-6
        )

    def test_a_second_order_step_overshoots_by_its_damping(self):
        zeta, wn, dt = 0.3, 0.5, 0.01
        wd = wn * math.sqrt(1 - zeta**2)
        t = [i * dt for i in range(20001)]
        y = [
            1
            - math.exp(-zeta * wn * s)
            * (math.cos(wd * s) + zeta / math.sqrt(1 - zeta**2) * math.sin(wd * s))
            for s in t
        ]
        m = step_measures(t, y, tail=0.05)
        assert m.overshoot == pytest.approx(
            math.exp(-math.pi * zeta / math.sqrt(1 - zeta**2)), abs=1e-4
        )
        assert m.peak_time == pytest.approx(math.pi / wd, abs=dt)

    def test_a_proportional_loop_leaves_its_steady_error(self):
        """P alone round a plant of gain 2 with kp 4: the error settles at ``1/(1 + 8)`` of
        the step."""
        trace = closed_loop(
            FOPDT(2.0, 5.0),
            PID(kp=4.0, dt=0.01),
            lambda s: 0.0 if s < 1 else 9.0,
            60,
            low=-1e6,
            high=1e6,
            settled=False,
        )
        m = step_measures(trace.t, trace.y, step_time=1.0, setpoint=trace.r)
        assert m.steady_error == pytest.approx(1.0, rel=1e-3)
