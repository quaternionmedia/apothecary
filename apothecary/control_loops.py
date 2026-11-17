"""A control loop: a plant, a PID, and how the loop they make responds.

A heater is a plant: power in, temperature out. This module describes such a plant
by a transfer function, a PID by the gains a firmware takes, and the loop the two
make by its frequency response and its response to a step. It identifies a plant
from what a machine reports, designs a PID by a named rule, and measures a loop. It
knows no port, no machine and no units beyond the ones it is handed; the standard
library alone.

**Plants.** ``FOPDT`` is first order plus dead time, ``K e^(-theta s) / (tau s + 1)``;
``SOPDT`` is second order plus dead time, two lags in series. Each gives its response
at any frequency (``response``, its unwrapped ``phase``) and its step response by the
exact formula (``step``). ``PlantRunner`` steps one through time with its input held
over each step, by the exact discretization of its lags: with a dead time that is a
whole number of steps it agrees with ``step`` to rounding; otherwise the dead time is
rounded to a whole step, which it says (``dead_time_used``).

**A PID** is ``PID``: the parallel form a firmware's ``M301``/``M304`` takes, ``u = kp
e + ki * integral(e) + kd * de/dt``, with ``ki`` per second and ``kd`` in seconds, a
sample time ``dt`` and a first-order filter on the derivative of time constant
``filter``. ``Standard`` is the ideal form, ``kc (e + integral(e)/ti + td de/dt)``, and
the two convert exactly both ways. ``PIDRunner`` runs one a sample at a time as a
firmware does: the derivative on the measurement through its filter, the integral
held while the output is clamped and the error would push it further.

**Identification.** From a step: Smith's two points (28.3 % and 63.2 % of the change)
and the area method (``two_point``, ``areas``). From a relay experiment: the point of
the plant the oscillation sits on, by the describing function of a relay
(``relay_point``); without hysteresis that is the ultimate gain and period. From
sampled input and output: a first-order-plus-dead-time fit (``fit_fopdt``) and the
frequency response at the frequencies an experiment excited, each with its coherence
and how far it stands above the noise (``frequency_response``).

**Rules** (``RULES``) are named relations from a plant or an ultimate point to a PID,
each with its source and what it assumes; ``LEFT_OUT`` names the ones not here and why.

**Measures.** ``margins`` gives the crossovers, the gain and phase margins and the
peaks of the sensitivity and the complementary sensitivity of a loop's open-loop
response; ``step_measures`` gives rise time, overshoot, settling time, steady error
and the integrated absolute error of a recorded step.

Units are the caller's: seconds and radians per second here, the plant's gain in the
output's unit per the input's. Nothing here says what a real machine is: a model that
fits data drawn from the same model shows the code, not the machine.
"""

from __future__ import annotations

import bisect
import cmath
import math
import random
from collections import deque
from dataclasses import dataclass, field, replace
from typing import Callable, Dict, List, Optional, Sequence, Tuple, Union

INF = float("inf")

# ---- plants -------------------------------------------------------------------------------


@dataclass(frozen=True)
class FOPDT:
    """First order plus dead time: ``gain * exp(-dead_time * s) / (time_constant * s + 1)``."""

    gain: float
    time_constant: float
    dead_time: float = 0.0

    model = "fopdt"

    def __post_init__(self):
        if not self.time_constant > 0:
            raise ValueError("a time constant is more than zero")
        if self.dead_time < 0:
            raise ValueError("a dead time is not negative")

    @property
    def lags(self) -> Tuple[float, ...]:
        return (self.time_constant,)

    def response(self, w: float) -> complex:
        return self.gain * cmath.exp(-1j * self.dead_time * w) / (1 + 1j * self.time_constant * w)

    def phase(self, w: float) -> float:
        """The phase at ``w``, unwrapped, in radians: the dead time's and the lag's."""
        sign = 0.0 if self.gain >= 0 else -math.pi
        return sign - self.dead_time * w - math.atan(self.time_constant * w)

    def step(self, t: float, amplitude: float = 1.0) -> float:
        """The output at ``t`` after a step of ``amplitude`` at 0, from rest: exact."""
        s = t - self.dead_time
        if s <= 0:
            return 0.0
        return self.gain * amplitude * (1 - math.exp(-s / self.time_constant))


@dataclass(frozen=True)
class SOPDT:
    """Second order plus dead time: two lags in series,
    ``gain * exp(-dead_time * s) / ((time_constant * s + 1) (second_time_constant * s + 1))``."""

    gain: float
    time_constant: float
    second_time_constant: float
    dead_time: float = 0.0

    model = "sopdt"

    def __post_init__(self):
        if not (self.time_constant > 0 and self.second_time_constant > 0):
            raise ValueError("time constants are more than zero")
        if self.dead_time < 0:
            raise ValueError("a dead time is not negative")

    @property
    def lags(self) -> Tuple[float, ...]:
        return (self.time_constant, self.second_time_constant)

    def response(self, w: float) -> complex:
        lag = (1 + 1j * self.time_constant * w) * (1 + 1j * self.second_time_constant * w)
        return self.gain * cmath.exp(-1j * self.dead_time * w) / lag

    def phase(self, w: float) -> float:
        sign = 0.0 if self.gain >= 0 else -math.pi
        return (
            sign
            - self.dead_time * w
            - math.atan(self.time_constant * w)
            - math.atan(self.second_time_constant * w)
        )

    def step(self, t: float, amplitude: float = 1.0) -> float:
        s = t - self.dead_time
        if s <= 0:
            return 0.0
        t1, t2 = self.time_constant, self.second_time_constant
        if math.isclose(t1, t2, rel_tol=1e-12):
            shape = 1 - (1 + s / t1) * math.exp(-s / t1)
        else:
            shape = 1 - (t1 * math.exp(-s / t1) - t2 * math.exp(-s / t2)) / (t1 - t2)
        return self.gain * amplitude * shape


Plant = Union[FOPDT, SOPDT]


class PlantRunner:
    """A plant stepped through time by ``h`` seconds at a call, its input held over each
    step: the exact discretization of its lags, the dead time a queue of whole steps.
    Output is the deviation from rest; ``start`` begins it settled at that input."""

    def __init__(self, plant: Plant, h: float, start: float = 0.0):
        if not h > 0:
            raise ValueError("a step is more than zero")
        self.plant, self.h = plant, h
        self.steps = int(round(plant.dead_time / h))
        self.dead_time_used = self.steps * h
        self._queue: deque = deque([start] * self.steps)
        lags = plant.lags
        self._a1 = math.exp(-h / lags[0])
        self._second = len(lags) > 1
        k = plant.gain
        self.x1 = k * start
        self.x2 = k * start
        if self._second:
            t1, t2 = lags
            self._a2 = math.exp(-h / t2)
            if math.isclose(t1, t2, rel_tol=1e-12):
                self._c = (h / t1) * self._a1
            else:
                self._c = t1 * (self._a1 - self._a2) / (t1 - t2)

    @property
    def output(self) -> float:
        return self.x2 if self._second else self.x1

    def step(self, u: float) -> float:
        """Hold ``u`` for one step; the output at its end."""
        if self.steps:
            self._queue.append(u)
            u = self._queue.popleft()
        ku = self.plant.gain * u
        x1 = self.x1
        self.x1 = self._a1 * x1 + (1 - self._a1) * ku
        if self._second:
            self.x2 = self._a2 * self.x2 + (1 - self._a2) * ku + (x1 - ku) * self._c
        return self.output


# ---- the PID ------------------------------------------------------------------------------


@dataclass(frozen=True)
class Standard:
    """The ideal (standard, non-interacting) form: ``kc (e + integral(e)/ti + td de/dt)``.
    ``ti`` is infinite for no integral action."""

    kc: float
    ti: float = INF
    td: float = 0.0

    def parallel(self, dt: float, filter: float = 0.0) -> "PID":
        """The same controller in the parallel form: exact."""
        ki = 0.0 if math.isinf(self.ti) else self.kc / self.ti
        return PID(kp=self.kc, ki=ki, kd=self.kc * self.td, dt=dt, filter=filter)


def series_to_standard(kc: float, ti: float, td: float) -> Standard:
    """A series (interacting) PID, ``kc (1 + 1/(ti s)) (1 + td s)``, in the ideal form:
    ``kc (1 + td/ti)``, ``ti + td``, ``ti td / (ti + td)``. Exact."""
    if math.isinf(ti):
        return Standard(kc=kc, ti=INF, td=td)
    return Standard(kc=kc * (1 + td / ti), ti=ti + td, td=ti * td / (ti + td))


@dataclass(frozen=True)
class PID:
    """The parallel form, as a firmware's ``M301``/``M304`` takes it.

    ``kp`` in the output's unit per the error's, ``ki`` the same per second, ``kd`` the
    same times seconds; ``dt`` the sample time in seconds; ``filter`` the derivative
    filter's time constant in seconds (0: none). ``derivative="measurement"`` says the
    derivative acts on the measurement, not the error, as a firmware's does, so a step
    of the setpoint kicks nothing; the feedback loop is the same either way."""

    kp: float
    ki: float = 0.0
    kd: float = 0.0
    dt: float = 0.1
    filter: float = 0.0
    derivative: str = "measurement"

    def standard(self) -> Standard:
        """The same controller in the ideal form: exact. ValueError for no proportional
        gain, which the ideal form cannot say."""
        if self.kp == 0:
            raise ValueError("the ideal form needs a proportional gain")
        ti = INF if self.ki == 0 else self.kp / self.ki
        return Standard(kc=self.kp, ti=ti, td=self.kd / self.kp)

    def response(self, w: float, sampled: bool = False) -> complex:
        """The controller's response at ``w``, continuous or as the sampled controller
        ``PIDRunner`` is (its integral by rectangles, its filter by backward Euler)."""
        if not sampled:
            if w == 0:
                return complex(INF, 0) if self.ki else complex(self.kp, 0)
            s = 1j * w
            return self.kp + self.ki / s + self.kd * s / (self.filter * s + 1)
        zi = cmath.exp(-1j * w * self.dt)  # z^-1
        a = smoothing(self.filter, self.dt)
        integral = self.ki * self.dt / (1 - zi) if self.ki else 0
        deriv = self.kd * (1 - a) * (1 - zi) / (self.dt * (1 - a * zi))
        return self.kp + integral + deriv


def smoothing(filter: float, dt: float) -> float:
    """The per-sample smoothing ``a`` of a derivative filtered as ``d = a d + (1 - a) x``
    that is the backward-Euler image of a first-order filter of time constant ``filter``:
    ``filter / (filter + dt)``."""
    return filter / (filter + dt) if filter > 0 else 0.0


def filter_of(smoothing: float, dt: float) -> float:
    """The filter time constant a per-sample smoothing ``a`` stands for: ``a dt / (1 - a)``."""
    if not 0 <= smoothing < 1:
        raise ValueError("a smoothing is at least 0 and less than 1")
    return smoothing * dt / (1 - smoothing)


class PIDRunner:
    """The parallel PID run a sample at a time, its output clamped to ``[low, high]``.

    Each ``update`` reads the setpoint and the measurement and returns the output to
    hold until the next. The derivative acts on the measurement through the filter; the
    integral is a rectangle sum that does not grow while the output is clamped and the
    error would push it further (conditional integration)."""

    def __init__(self, pid: PID, low: float = 0.0, high: float = 255.0, integral: float = 0.0):
        self.pid, self.low, self.high = pid, low, high
        self.integral = integral
        self.derivative = 0.0
        self._last: Optional[float] = None
        self._last_error: Optional[float] = None

    def update(self, setpoint: float, measured: float) -> float:
        p = self.pid
        e = setpoint - measured
        a = smoothing(p.filter, p.dt)
        if p.derivative == "measurement":
            last = measured if self._last is None else self._last
            raw = -p.kd * (measured - last) / p.dt
        else:
            last = e if self._last_error is None else self._last_error
            raw = p.kd * (e - last) / p.dt
        self._last, self._last_error = measured, e
        self.derivative = a * self.derivative + (1 - a) * raw
        trial = self.integral + p.ki * e * p.dt
        u = p.kp * e + trial + self.derivative
        if (u > self.high and e > 0) or (u < self.low and e < 0):
            u = p.kp * e + self.integral + self.derivative
        else:
            self.integral = trial
        return min(self.high, max(self.low, u))


# ---- simulated experiments ----------------------------------------------------------------


@dataclass
class Trace:
    """A record of an experiment: at each time, the setpoint, the input and the output."""

    t: List[float] = field(default_factory=list)
    r: List[float] = field(default_factory=list)
    u: List[float] = field(default_factory=list)
    y: List[float] = field(default_factory=list)

    def add(self, t: float, r: float, u: float, y: float) -> None:
        self.t.append(t)
        self.r.append(r)
        self.u.append(u)
        self.y.append(y)


def _noise(sigma: float, seed: int) -> Callable[[], float]:
    rng = random.Random(seed)
    return (lambda: rng.gauss(0.0, sigma)) if sigma > 0 else (lambda: 0.0)


def closed_loop(
    plant: Plant,
    pid: PID,
    setpoint: Callable[[float], float],
    duration: float,
    *,
    ambient: float = 0.0,
    low: float = 0.0,
    high: float = 255.0,
    substeps: int = 10,
    sample: Optional[float] = None,
    noise: float = 0.0,
    seed: int = 0,
    settled: bool = True,
) -> Trace:
    """The loop of ``pid`` round ``plant`` run for ``duration`` seconds: the PID every
    ``pid.dt``, the plant in ``substeps`` exact steps between. The output is ``ambient``
    plus the plant's; the PID reads it with Gaussian ``noise`` of that deviation.
    ``settled`` begins at rest at the first setpoint (the integral holding the input that
    keeps it there); else from ambient with the integral empty. Recorded every
    ``sample`` seconds (default every ``pid.dt``): the setpoint, the input as it is held
    then, and the output as measured, noise and all."""
    h = pid.dt / substeps
    r0 = setpoint(0.0)
    u0 = (r0 - ambient) / plant.gain if settled else 0.0
    u0 = min(high, max(low, u0))
    runner = PlantRunner(plant, h, start=u0)
    ctrl = PIDRunner(pid, low, high, integral=u0 if settled else 0.0)
    noisy = _noise(noise, seed)
    every = sample or pid.dt
    trace = Trace()
    t = 0.0
    u = u0
    next_sample = 0.0
    steps = int(round(duration / h))
    measured = ambient + runner.output + noisy()
    for i in range(steps + 1):
        t = i * h
        if i % substeps == 0:
            measured = ambient + runner.output + noisy()
            u = ctrl.update(setpoint(t), measured)
        if t >= next_sample - 1e-9:
            trace.add(t, setpoint(t), u, measured)
            next_sample += every
        if i < steps:
            runner.step(u)
    return trace


def relay_run(
    plant: Plant,
    *,
    setpoint: float,
    bias: float,
    amplitude: float,
    duration: float,
    hysteresis: float = 0.0,
    ambient: float = 0.0,
    h: float = 0.01,
    decide_every: Optional[float] = None,
    sample: Optional[float] = None,
    noise: float = 0.0,
    seed: int = 0,
) -> Trace:
    """A relay experiment: the input ``bias + amplitude`` while the output is below
    ``setpoint - hysteresis``, ``bias - amplitude`` above ``setpoint + hysteresis``, and as
    it was between. The plant starts at rest at ``bias``. The relay decides every
    ``decide_every`` seconds (default every step ``h``) on the output as measured, with
    ``noise``; recorded every ``sample`` seconds (default every decision)."""
    runner = PlantRunner(plant, h, start=bias)
    noisy = _noise(noise, seed)
    every_decide = max(1, int(round((decide_every or h) / h)))
    every_sample = max(1, int(round((sample or decide_every or h) / h)))
    trace = Trace()
    u = bias + amplitude
    steps = int(round(duration / h))
    for i in range(steps + 1):
        if i % every_decide == 0:
            measured = ambient + runner.output + noisy()
            if measured < setpoint - hysteresis:
                u = bias + amplitude
            elif measured > setpoint + hysteresis:
                u = bias - amplitude
        if i % every_sample == 0:
            trace.add(i * h, setpoint, u, ambient + runner.output + noisy())
        if i < steps:
            runner.step(u)
    return trace


def fopdt_relay_exact(plant: FOPDT, amplitude: float) -> Tuple[float, float]:
    """The limit cycle an ideal relay of ``amplitude`` (no hysteresis) holds a FOPDT
    plant in, exactly: its amplitude ``K d (1 - e^(-theta/tau))`` and its period
    ``2 theta + 2 tau ln(2 - e^(-theta/tau))``. Derived by following the output between
    two switches, the input reaching the plant one dead time after each."""
    k, tau, theta = plant.gain, plant.time_constant, plant.dead_time
    q = math.exp(-theta / tau)
    return abs(k) * amplitude * (1 - q), 2 * theta + 2 * tau * math.log(2 - q)


# ---- identification -----------------------------------------------------------------------


@dataclass(frozen=True)
class Identified:
    """A plant identified from data, by a named method, with what it rests on."""

    plant: Plant
    method: str
    initial: float
    final: float
    input_change: float
    note: str = ""
    fit_rms: Optional[float] = None


def _crossing(
    t: Sequence[float], y: Sequence[float], level: float, rising: bool
) -> Optional[float]:
    """The first time ``y`` reaches ``level`` going the way ``rising`` says, interpolated
    linearly between samples."""
    for i in range(1, len(y)):
        a, b = y[i - 1], y[i]
        if (rising and a < level <= b) or (not rising and a > level >= b):
            return t[i - 1] + (t[i] - t[i - 1]) * (level - a) / (b - a)
    return None


def _ends(t, y, step_time: float, tail: float) -> Tuple[float, float]:
    """The output just before ``step_time`` (the mean of the last ``tail`` fraction of
    the samples before it, ten at least, so a record that begins with a heat-up is read
    where it had settled) and at the end (the mean of the last ``tail`` fraction of the
    record)."""
    before = [v for s, v in zip(t, y, strict=True) if s <= step_time]
    if before:
        before = before[-max(10, int(len(before) * tail)) :]
    initial = sum(before) / len(before) if before else y[0]
    n = max(1, int(len(y) * tail))
    final = sum(y[-n:]) / n
    return initial, final


def two_point(
    t: Sequence[float],
    y: Sequence[float],
    input_change: float,
    step_time: float = 0.0,
    tail: float = 0.1,
) -> Identified:
    """Smith's two-point method: a FOPDT through the times the step response reaches
    28.3 % and 63.2 % of its change, which for a FOPDT are ``theta + tau/3`` and ``theta +
    tau``: ``tau = 1.5 (t63 - t28)``, ``theta = t63 - tau``; the gain is the change over
    the input's. The response must have settled by the end of the record (``tail``)."""
    initial, final = _ends(t, y, step_time, tail)
    change = final - initial
    if change == 0 or input_change == 0:
        raise ValueError("no change to identify from")
    rising = change > 0
    # The levels are taken at exactly 1 - e^(-1/3) and 1 - e^(-1), so the relation holds
    # exactly for a FOPDT.
    t28 = _crossing(t, y, initial + (1 - math.exp(-1 / 3)) * change, rising)
    t63 = _crossing(t, y, initial + (1 - math.exp(-1)) * change, rising)
    if t28 is None or t63 is None:
        raise ValueError("the response never reached 63.2 % of its change")
    tau = 1.5 * (t63 - t28)
    theta = max(0.0, t63 - step_time - tau)
    plant = FOPDT(change / input_change, tau, theta)
    return Identified(plant, "smith_two_point", initial, final, input_change)


def _trapezoid(t: Sequence[float], v: Sequence[float]) -> float:
    return sum((t[i] - t[i - 1]) * (v[i] + v[i - 1]) / 2 for i in range(1, len(t)))


def areas(
    t: Sequence[float],
    y: Sequence[float],
    input_change: float,
    step_time: float = 0.0,
    tail: float = 0.1,
) -> Identified:
    """The area method (Astrom and Hagglund): the area between the final value and the
    response, ``A0 = K (theta + tau)``, gives the average residence time; the area under
    the response up to it, ``A1 = K tau / e``, gives ``tau``. Exact for a FOPDT; the
    integrals are trapezoids over the samples, so noise averages out of them."""
    initial, final = _ends(t, y, step_time, tail)
    change = final - initial
    if change == 0 or input_change == 0:
        raise ValueError("no change to identify from")
    ts = [s - step_time for s in t if s >= step_time]
    ys = [(v - initial) / change for s, v in zip(t, y, strict=True) if s >= step_time]
    a0 = _trapezoid(ts, [1 - v for v in ys])
    upto = [(s, v) for s, v in zip(ts, ys, strict=True) if s <= a0]
    if len(upto) < 2:
        raise ValueError("too few samples before the residence time")
    # The last piece, from the last sample before a0 to a0, interpolated.
    i = len(upto)
    if i < len(ts):
        s0, v0 = upto[-1]
        s1, v1 = ts[i], ys[i]
        upto.append((a0, v0 + (v1 - v0) * (a0 - s0) / (s1 - s0)))
    a1 = _trapezoid([s for s, _ in upto], [v for _, v in upto])
    tau = math.e * a1
    theta = max(0.0, a0 - tau)
    plant = FOPDT(change / input_change, tau, theta)
    return Identified(plant, "areas", initial, final, input_change)


@dataclass(frozen=True)
class RelayPoint:
    """The point of a plant a relay oscillation sits on, by the relay's describing
    function: at ``frequency`` the plant's magnitude is ``pi a / (4 d)`` and its phase
    ``-180 + asin(hysteresis / a)`` degrees. Without hysteresis that is the ultimate
    point: ``ultimate_gain = 4 d / (pi a)``, ``ultimate_period`` the oscillation's."""

    frequency: float
    magnitude: float
    phase_deg: float
    ultimate_gain: Optional[float]
    ultimate_period: Optional[float]


def relay_point(
    amplitude: float, oscillation: float, period: float, hysteresis: float = 0.0
) -> RelayPoint:
    """The describing-function relation of a relay of ``amplitude`` d (half the input's
    swing) that holds the output in an oscillation of ``oscillation`` a (half its peak to
    peak) and ``period``. It keeps only the first harmonic of the relay's square wave, so
    it is exact only for a plant that passes nothing else; ``fopdt_relay_exact`` gives
    the true oscillation of a FOPDT to compare."""
    if not (amplitude > 0 and oscillation > 0 and period > 0):
        raise ValueError("an amplitude, an oscillation and a period are more than zero")
    if hysteresis >= oscillation:
        raise ValueError("a hysteresis as wide as the oscillation leaves no point")
    w = 2 * math.pi / period
    mag = math.pi * oscillation / (4 * amplitude)
    phase = -180.0 + math.degrees(math.asin(hysteresis / oscillation))
    if hysteresis == 0:
        return RelayPoint(w, mag, phase, 1 / mag, period)
    return RelayPoint(w, mag, phase, None, None)


@dataclass(frozen=True)
class Oscillation:
    """An oscillation read from a record: half its peak to peak, its period, how many
    whole cycles it was read over, and how much the cycles differ (the spread of their
    periods over the mean)."""

    amplitude: float
    period: float
    cycles: int
    centre: float
    period_spread: float


def oscillation(t: Sequence[float], y: Sequence[float], about: float, last: int = 3) -> Oscillation:
    """The last ``last`` whole cycles of ``y`` about the level ``about``: each cycle from
    one upward crossing to the next, interpolated, with its highest and lowest sample.
    A sampled peak is lower than the true one by up to the curve's travel in half a
    sample; that is what one sample a second costs."""
    ups = []
    for i in range(1, len(y)):
        if y[i - 1] < about <= y[i]:
            ups.append(t[i - 1] + (t[i] - t[i - 1]) * (about - y[i - 1]) / (y[i] - y[i - 1]))
    if len(ups) < 2:
        raise ValueError("fewer than one whole cycle about the level")
    ups = ups[-(last + 1) :]
    periods = [b - a for a, b in zip(ups, ups[1:], strict=False)]
    highs, lows = [], []
    for a, b in zip(ups, ups[1:], strict=False):
        inside = [v for s, v in zip(t, y, strict=True) if a <= s <= b]
        highs.append(max(inside))
        lows.append(min(inside))
    period = sum(periods) / len(periods)
    amp = (sum(highs) / len(highs) - sum(lows) / len(lows)) / 2
    centre = (sum(highs) / len(highs) + sum(lows) / len(lows)) / 2
    spread = (max(periods) - min(periods)) / period if len(periods) > 1 else 0.0
    return Oscillation(amp, period, len(periods), centre, spread)


def _solve3(m: List[List[float]], v: List[float]) -> Optional[List[float]]:
    """The 3 (or n) unknowns of ``m x = v`` by Gaussian elimination with pivoting; None
    when singular."""
    n = len(v)
    a = [row[:] + [v[i]] for i, row in enumerate(m)]
    for c in range(n):
        p = max(range(c, n), key=lambda r: abs(a[r][c]))
        if abs(a[p][c]) < 1e-300:
            return None
        a[c], a[p] = a[p], a[c]
        for r in range(n):
            if r != c:
                f = a[r][c] / a[c][c]
                for k in range(c, n + 1):
                    a[r][k] -= f * a[c][k]
    return [a[i][n] / a[i][i] for i in range(n)]


def _least_squares(rows: List[List[float]], ys: List[float]) -> Optional[List[float]]:
    n = len(rows[0])
    m = [[sum(r[i] * r[j] for r in rows) for j in range(n)] for i in range(n)]
    v = [sum(r[i] * y for r, y in zip(rows, ys, strict=True)) for i in range(n)]
    return _solve3(m, v)


def _arx(
    u: Sequence[float], y: Sequence[float], dt: float, top: int
) -> Optional[Tuple[float, float, float]]:
    """The equation-error start of ``fit_fopdt``: least squares on ``y[k+1] = a y[k] + b1
    u[k-d] + b2 u[k-d-1] + c`` for each whole dead time ``d``; its time constant and dead
    time, or None when no ``d`` gives a stable lag."""
    best = None
    n = len(y)
    for d in range(0, top + 1):
        rows = [[y[k], u[k - d], u[k - d - 1], 1.0] for k in range(d + 1, n - 1)]
        if len(rows) < 6:
            break
        ys = [y[k + 1] for k in range(d + 1, n - 1)]
        coef = _least_squares(rows, ys)
        if coef is None:
            continue
        a, b1, b2, _ = coef
        if not 0 < a < 1 or b1 + b2 == 0:
            continue
        res = [
            ys[i] - sum(c * x for c, x in zip(coef, rows[i], strict=True)) for i in range(len(rows))
        ]
        rms = math.sqrt(sum(e * e for e in res) / len(res))
        if best is None or rms < best[0] - 1e-15:
            gain = (b1 + b2) / (1 - a)
            frac = 0.0
            if 0 < 1 - b1 / gain < 1:
                frac = min(1.0, max(0.0, 1 - math.log(1 - b1 / gain) / math.log(a)))
            best = (rms, -dt / math.log(a), (d + frac) * dt)
    return None if best is None else best


def _lagged(u: Sequence[float], dt: float, tau: float, theta: float) -> List[float]:
    """A unit-gain FOPDT's output for the held input ``u``, settled at ``u[0]`` before
    it: the exact recursion ``x[k+1] = a x[k] + (1 - a^(1-f)) u[k-d] + (a^(1-f) - a)
    u[k-d-1]`` for a dead time ``(d + f) dt``."""
    a = math.exp(-dt / tau)
    d = int(theta // dt)
    f = theta / dt - d
    b1 = 1 - a ** (1 - f)
    b2 = a ** (1 - f) - a
    x = [u[0]]
    for k in range(len(u) - 1):
        x.append(a * x[k] + b1 * u[max(0, k - d)] + b2 * u[max(0, k - d - 1)])
    return x


def _output_error(u, y, dt, tau, theta) -> Tuple[float, float, float]:
    """For a time constant and a dead time: the gain and offset that fit ``y`` best as
    ``offset + gain * x`` (``x`` the unit-gain output), and the RMS left."""
    x = _lagged(u, dt, tau, theta)
    n = len(y)
    sx, sy = sum(x), sum(y)
    sxx = sum(v * v for v in x)
    sxy = sum(a * b for a, b in zip(x, y, strict=True))
    det = n * sxx - sx * sx
    if det == 0:
        return 0.0, sy / n, INF
    gain = (n * sxy - sx * sy) / det
    offset = (sy - gain * sx) / n
    rms = math.sqrt(sum((b - offset - gain * a) ** 2 for a, b in zip(x, y, strict=True)) / n)
    return gain, offset, rms


def _nelder_mead(
    f: Callable[[List[float]], float], start: List[float], step: List[float], iters: int = 300
) -> List[float]:
    """The least of ``f`` near ``start``, by the Nelder-Mead simplex."""
    pts = [start] + [
        [s + (step[i] if i == j else 0.0) for j, s in enumerate(start)] for i in range(len(start))
    ]
    vals = [f(p) for p in pts]
    for _ in range(iters):
        order = sorted(range(len(pts)), key=vals.__getitem__)
        pts, vals = [pts[i] for i in order], [vals[i] for i in order]
        centre = [sum(p[j] for p in pts[:-1]) / (len(pts) - 1) for j in range(len(start))]
        worst = pts[-1]
        refl = [c + (c - w) for c, w in zip(centre, worst, strict=True)]
        fr = f(refl)
        if fr < vals[0]:
            exp = [c + 2 * (c - w) for c, w in zip(centre, worst, strict=True)]
            fe = f(exp)
            pts[-1], vals[-1] = (exp, fe) if fe < fr else (refl, fr)
        elif fr < vals[-2]:
            pts[-1], vals[-1] = refl, fr
        else:
            con = [c + 0.5 * (w - c) for c, w in zip(centre, worst, strict=True)]
            fc = f(con)
            if fc < vals[-1]:
                pts[-1], vals[-1] = con, fc
            else:
                best = pts[0]
                pts = [best] + [
                    [b + 0.5 * (p - b) for b, p in zip(best, q, strict=True)] for q in pts[1:]
                ]
                vals = [vals[0]] + [f(p) for p in pts[1:]]
        if max(vals) - min(vals) < 1e-14 * (1 + abs(min(vals))):
            break
    return pts[min(range(len(pts)), key=vals.__getitem__)]


def fit_fopdt(
    u: Sequence[float],
    y: Sequence[float],
    dt: float,
    max_dead_steps: Optional[int] = None,
) -> Identified:
    """A FOPDT fitted to an input and an output sampled every ``dt``, the input held
    between samples and the plant settled at the first input before the record.

    The output error is what is fitted: the plant's simulated response to the recorded
    input, by its exact recursion (``_lagged``), against the recorded output; for each
    time constant and dead time the gain and an offset (an ambient) are a linear least
    squares, and the two are searched by the Nelder-Mead simplex from where an
    equation-error fit puts them (``_arx``). Exact on noise-free data from a FOPDT. A
    noisy output averages out of an output-error fit; an input read as a snapshot of
    one that moves between readings (a heater's power as a poll reports it) does not,
    and is the fit's weakest part."""
    n = len(y)
    if len(u) != n or n < 8:
        raise ValueError("an input and an output of the same length, eight samples at least")
    if max(u) == min(u):
        raise ValueError("no fit: the input does not move")
    top = max_dead_steps if max_dead_steps is not None else n // 4
    first = _arx(u, y, dt, top)
    span = dt * n
    tau0, theta0 = (first[1], first[2]) if first else (span / 5, 2 * dt)
    tau0 = min(max(tau0, dt / 4), 10 * span)
    limit = top * dt

    def cost(v: List[float]) -> float:
        tau, theta = math.exp(v[0]), v[1]
        if theta < 0 or theta > limit or tau > 100 * span:
            return INF
        return _output_error(u, y, dt, tau, theta)[2]

    best = _nelder_mead(cost, [math.log(tau0), theta0], [0.3, max(dt, 0.2 * theta0 + dt)])
    # One more start from a coarse dead-time scan guards the simplex against a poor start.
    for th in (0.0, limit / 4, limit / 2):
        other = _nelder_mead(cost, [math.log(tau0), th], [0.3, max(dt, 0.2 * th + dt)])
        if cost(other) < cost(best):
            best = other
    tau, theta = math.exp(best[0]), best[1]
    gain, offset, rms = _output_error(u, y, dt, tau, theta)
    return Identified(
        FOPDT(gain, tau, max(0.0, theta)),
        "fit_fopdt",
        offset,
        offset,
        0.0,
        note=f"output error; offset {offset:.4g}",
        fit_rms=rms,
    )


# ---- frequency response from data ---------------------------------------------------------


@dataclass(frozen=True)
class FrequencyPoint:
    """The plant at one excited frequency, estimated from data, and how far to trust it.

    ``coherence`` is between the output and what excited it (the setpoint when one is
    given, else the input), over ``segments`` whole periods: 1 for one period, by its
    construction, so it says nothing then. ``above_noise`` is the output's amplitude at
    this frequency over its mean at the neighbouring frequencies nothing excited.
    ``trust`` is ``good``, ``fair``, ``poor`` or ``unknown``, and ``why`` says which
    reason decided it."""

    frequency: float
    value: complex
    coherence: float
    segments: int
    above_noise: float
    trust: str
    why: str

    @property
    def magnitude(self) -> float:
        return abs(self.value)

    @property
    def phase_deg(self) -> float:
        return math.degrees(cmath.phase(self.value))


def resample(
    t: Sequence[float], v: Sequence[float], dt: float, start: Optional[float] = None
) -> Tuple[List[float], List[float]]:
    """``v`` read every ``dt`` from ``start`` (the first time) to the last, linearly
    between the samples it was taken at: polls are about a second apart, not exactly."""
    t0 = t[0] if start is None else start
    out_t, out_v = [], []
    j = 0
    k = 0
    while True:
        s = t0 + k * dt
        if s > t[-1] + 1e-9:
            break
        while j < len(t) - 2 and t[j + 1] < s:
            j += 1
        a, b = t[j], t[j + 1] if j + 1 < len(t) else t[j]
        if b == a:
            val = v[j]
        else:
            val = v[j] + (v[min(j + 1, len(v) - 1)] - v[j]) * (s - a) / (b - a)
        out_t.append(s)
        out_v.append(val)
        k += 1
    return out_t, out_v


def _bin(x: Sequence[float], k: int) -> complex:
    n = len(x)
    return sum(x[i] * cmath.exp(-2j * math.pi * k * i / n) for i in range(n))


def frequency_response(
    u: Sequence[float],
    y: Sequence[float],
    dt: float,
    period: float,
    harmonics: Sequence[int] = (1, 3, 5),
    reference: Optional[Sequence[float]] = None,
    skip: int = 0,
) -> List[FrequencyPoint]:
    """The plant from input ``u`` to output ``y``, both sampled every ``dt``, at the
    harmonics of an excitation of ``period`` seconds (a square wave excites the odd ones).

    The record after ``skip`` samples is cut into whole periods, each a segment. With a
    ``reference`` (the setpoint of a closed-loop experiment) the plant is the ratio of
    the output's and the input's cross-spectra with it, ``S_yr / S_ur``, which noise fed
    back through the controller does not bias; without one it is ``S_yu / S_uu``. A
    frequency at or above half the sampling rate cannot be read and is left out."""
    per = int(round(period / dt))
    if per < 4 or abs(per * dt - period) > 1e-6 * period:
        raise ValueError("the period is a whole number of samples, four at least")
    excite = reference if reference is not None else u
    u, y, excite = list(u[skip:]), list(y[skip:]), list(excite[skip:])
    segments = len(y) // per
    if segments < 1:
        raise ValueError("less than one whole period after the skip")
    nyquist = math.pi / dt
    points = []
    for k in harmonics:
        w = 2 * math.pi * k / period
        if w >= nyquist * (1 - 1e-12):
            continue
        syr = sur = 0j
        suu = syy = srr = 0.0
        side = 0.0
        for m in range(segments):
            seg = slice(m * per, (m + 1) * per)
            ym, um, rm = y[seg], u[seg], excite[seg]
            Y, U, R = _bin(ym, k), _bin(um, k), _bin(rm, k)
            syr += Y * R.conjugate()
            sur += U * R.conjugate()
            syy += abs(Y) ** 2
            suu += abs(U) ** 2
            srr += abs(R) ** 2
            near = [abs(_bin(ym, j)) for j in (k - 1, k + 1) if 0 < j < per / 2]
            side += sum(near) / len(near) if near else 0.0
        if not (syy and srr and suu):
            continue
        if reference is not None:
            value = syr / sur if sur != 0 else complex(math.nan, 0)
            # Both the output and the input are to follow the reference for the ratio to
            # hold: the lesser of their coherences with it.
            coh = min(abs(syr) ** 2 / (syy * srr), abs(sur) ** 2 / (suu * srr))
        else:
            value = syr / suu
            coh = abs(syr) ** 2 / (syy * suu)
        amp = math.sqrt(syy / segments)
        noise = side / segments
        above = amp / noise if noise > 0 else INF
        if segments < 2:
            trust, why = "unknown", "one period: its coherence is 1 by construction"
        elif coh < 0.5 or above < 3:
            trust, why = "poor", f"coherence {coh:.2f}, {above:.1f}x the noise beside it"
        elif w > nyquist / 2:
            trust, why = "fair", "above a quarter of the sampling rate"
        elif coh >= 0.9 and above >= 10:
            trust, why = "good", f"coherence {coh:.2f}, {above:.1f}x the noise beside it"
        else:
            trust, why = "fair", f"coherence {coh:.2f}, {above:.1f}x the noise beside it"
        points.append(FrequencyPoint(w, value, coh, segments, above, trust, why))
    return points


# ---- tuning rules -------------------------------------------------------------------------


@dataclass(frozen=True)
class Ultimate:
    """The ultimate point: the gain at which a proportional loop just oscillates, and the
    period it oscillates at."""

    gain: float
    period: float


@dataclass(frozen=True)
class Rule:
    """A named tuning relation: from what it takes (a FOPDT, a SOPDT or the ultimate
    point) to the ideal form, for the kinds of controller it gives."""

    name: str
    title: str
    source: str
    takes: str
    kinds: Tuple[str, ...]
    assumes: str
    relation: str
    design: Callable[..., Standard] = field(repr=False, compare=False)


def _zn_ultimate(u: Ultimate, kind: str, **_) -> Standard:
    if kind == "p":
        return Standard(0.5 * u.gain)
    if kind == "pi":
        return Standard(0.45 * u.gain, u.period / 1.2)
    return Standard(0.6 * u.gain, u.period / 2, u.period / 8)


def _zn_reaction(p: FOPDT, kind: str, **_) -> Standard:
    a = p.gain * p.dead_time / p.time_constant
    L = p.dead_time
    if a <= 0:
        raise ValueError("the reaction-curve rule needs a dead time")
    if kind == "p":
        return Standard(1 / a)
    if kind == "pi":
        return Standard(0.9 / a, 3 * L)
    return Standard(1.2 / a, 2 * L, L / 2)


def _tyreus_luyben(u: Ultimate, kind: str, **_) -> Standard:
    if kind == "pi":
        return Standard(u.gain / 3.2, 2.2 * u.period)
    return Standard(u.gain / 2.2, 2.2 * u.period, u.period / 6.3)


def _cohen_coon(p: FOPDT, kind: str, **_) -> Standard:
    k, tau, th = p.gain, p.time_constant, p.dead_time
    if th <= 0:
        raise ValueError("Cohen-Coon needs a dead time")
    r = th / tau
    if kind == "pi":
        return Standard((tau / (k * th)) * (0.9 + r / 12), th * (30 + 3 * r) / (9 + 20 * r))
    return Standard(
        (tau / (k * th)) * (4 / 3 + r / 4),
        th * (32 + 6 * r) / (13 + 8 * r),
        th * 4 / (11 + 2 * r),
    )


def _simc(p: Plant, kind: str, closed_loop_time: Optional[float] = None, **_) -> Standard:
    th = p.dead_time
    tc = th if closed_loop_time is None else closed_loop_time
    if tc <= 0:
        raise ValueError(
            "SIMC needs a closed-loop time more than zero (it is the dead time by default)"
        )
    t1 = p.lags[0] if len(p.lags) == 1 else max(p.lags)
    kc = t1 / (p.gain * (tc + th))
    ti = min(t1, 4 * (tc + th))
    if kind == "pi":
        if isinstance(p, SOPDT):
            raise ValueError("SIMC's PI is for a FOPDT; a SOPDT takes its PID")
        return Standard(kc, ti)
    if not isinstance(p, SOPDT):
        raise ValueError("SIMC's PID is for a SOPDT: its derivative cancels the second lag")
    return series_to_standard(kc, ti, min(p.lags))


def _imc(p: FOPDT, kind: str, closed_loop_time: Optional[float] = None, **_) -> Standard:
    k, tau, th = p.gain, p.time_constant, p.dead_time
    # The dead time by default, as SIMC's tau_c: this module's choice, not the source's.
    lam = closed_loop_time if closed_loop_time is not None else th
    if lam <= 0:
        raise ValueError("IMC needs a closed-loop time more than zero (the dead time by default)")
    return Standard((2 * tau + th) / (k * (2 * lam + th)), tau + th / 2, tau * th / (2 * tau + th))


def _amigo(p: FOPDT, kind: str, **_) -> Standard:
    k, T, L = p.gain, p.time_constant, p.dead_time
    if L <= 0:
        raise ValueError("AMIGO needs a dead time")
    if kind == "pi":
        kc = 0.15 / k + (0.35 - L * T / (L + T) ** 2) * T / (k * L)
        ti = 0.35 * L + 13 * L * T * T / (T * T + 12 * L * T + 7 * L * L)
        return Standard(kc, ti)
    kc = (0.2 + 0.45 * T / L) / k
    ti = (0.4 * L + 0.8 * T) / (L + 0.1 * T) * L
    td = 0.5 * L * T / (0.3 * L + T)
    return Standard(kc, ti, td)


RULES: Dict[str, Rule] = {
    r.name: r
    for r in (
        Rule(
            "zn_ultimate",
            "Ziegler-Nichols, ultimate sensitivity",
            "Ziegler and Nichols, Optimum settings for automatic controllers, Trans. ASME 64 (1942)",
            "ultimate",
            ("p", "pi", "pid"),
            "the ultimate point is the plant's; tuned for a quarter-amplitude decay, so it "
            "overshoots and rings, and its margins are small",
            "PID: kc = 0.6 Ku, ti = Tu/2, td = Tu/8; PI: 0.45 Ku, Tu/1.2; P: 0.5 Ku",
            _zn_ultimate,
        ),
        Rule(
            "zn_reaction",
            "Ziegler-Nichols, reaction curve",
            "Ziegler and Nichols (1942), as Astrom and Hagglund, Advanced PID Control (2006), state it",
            "fopdt",
            ("p", "pi", "pid"),
            "the step response is a FOPDT's, read as its steepest slope K/tau and its dead "
            "time L; aggressive like its sibling",
            "with a = K L / tau: PID kc = 1.2/a, ti = 2 L, td = L/2; PI 0.9/a, 3 L; P 1/a",
            _zn_reaction,
        ),
        Rule(
            "tyreus_luyben",
            "Tyreus-Luyben",
            "Tyreus and Luyben, Tuning PI controllers for integrator/dead time processes, "
            "Ind. Eng. Chem. Res. 31 (1992)",
            "ultimate",
            ("pi", "pid"),
            "the ultimate point is the plant's; a detuned Ziegler-Nichols, slower and with more margin",
            "PI: kc = Ku/3.2, ti = 2.2 Tu; PID: kc = Ku/2.2, ti = 2.2 Tu, td = Tu/6.3",
            _tyreus_luyben,
        ),
        Rule(
            "cohen_coon",
            "Cohen-Coon",
            "Cohen and Coon, Theoretical consideration of retarded control, Trans. ASME 75 (1953)",
            "fopdt",
            ("pi", "pid"),
            "a FOPDT with a dead time; aimed at a quarter-amplitude decay to a load, so it "
            "is aggressive for a setpoint",
            "with r = theta/tau: PID kc = (tau/(K theta))(4/3 + r/4), ti = theta (32 + 6 r)/(13 "
            "+ 8 r), td = 4 theta/(11 + 2 r); PI kc = (tau/(K theta))(0.9 + r/12), ti = theta (30 "
            "+ 3 r)/(9 + 20 r)",
            _cohen_coon,
        ),
        Rule(
            "simc",
            "SIMC (Skogestad)",
            "Skogestad, Simple analytic rules for model reduction and PID controller tuning, "
            "J. Process Control 13 (2003)",
            "fopdt or sopdt",
            ("pi", "pid"),
            "a FOPDT (PI) or a SOPDT (PID, its derivative cancelling the second lag); the "
            "closed-loop time tau_c is the one choice, the dead time by default for a tight "
            "but robust loop",
            "kc = tau1/(K (tau_c + theta)), ti = min(tau1, 4 (tau_c + theta)), and for a SOPDT "
            "td = tau2 in the series form, turned into the ideal form exactly",
            _simc,
        ),
        Rule(
            "imc",
            "IMC-PID",
            "Rivera, Morari and Skogestad, Internal model control 4: PID controller design, "
            "Ind. Eng. Chem. Process Des. Dev. 25 (1986)",
            "fopdt",
            ("pid",),
            "a FOPDT whose dead time is taken by its first-order Pade approximation; the "
            "closed-loop time lambda is the one choice",
            "kc = (2 tau + theta)/(K (2 lambda + theta)), ti = tau + theta/2, td = tau theta/(2 "
            "tau + theta)",
            _imc,
        ),
        Rule(
            "amigo",
            "AMIGO",
            "Astrom and Hagglund, Revisiting the Ziegler-Nichols step response method for PID "
            "control, J. Process Control 14 (2004); Advanced PID Control (2006)",
            "fopdt",
            ("pi", "pid"),
            "a FOPDT; chosen for a maximum sensitivity near 1.4 over a range of plants, the "
            "PID's in its simplified form, which is conservative",
            "PI: kc = 0.15/K + (0.35 - L T/(L + T)^2) T/(K L), ti = 0.35 L + 13 L T^2/(T^2 + 12 L "
            "T + 7 L^2); PID: kc = (0.2 + 0.45 T/L)/K, ti = L (0.4 L + 0.8 T)/(L + 0.1 T), td = "
            "0.5 L T/(0.3 L + T)",
            _amigo,
        ),
    )
}

LEFT_OUT: Dict[str, str] = {
    "chien_hrones_reswick": "its tables (setpoint and load, 0 % and 20 % overshoot) have "
    "constants not stated here with confidence",
    "kappa_tau": "Astrom and Hagglund's kappa-tau rules are fitted curves whose coefficients "
    "are not stated here with confidence",
    "lambda_variants": "the many lambda-tuning tables differ in how the dead time is "
    "approximated; IMC-PID and SIMC stand for the family",
    "pessen_some_overshoot_no_overshoot": "constants not stated here with confidence",
}


@dataclass(frozen=True)
class Design:
    """A PID designed by a rule: the ideal form, the parallel form for the firmware, and
    what it was designed from."""

    rule: str
    kind: str
    standard: Standard
    pid: PID
    closed_loop_time: Optional[float] = None


def design(
    rule: str,
    *,
    plant: Optional[Plant] = None,
    ultimate: Optional[Ultimate] = None,
    kind: str = "pid",
    dt: float = 0.1,
    filter: float = 0.0,
    closed_loop_time: Optional[float] = None,
) -> Design:
    """The PID ``rule`` gives, of ``kind`` (p, pi, pid), from a plant or an ultimate point
    as the rule takes; in the parallel form at sample time ``dt`` with the derivative
    filter ``filter``. A rule that takes an ultimate point is given one from a plant by
    ``ultimate_of`` when only a plant is at hand."""
    found = RULES.get(rule)
    if found is None:
        raise ValueError(f"no rule {rule!r}; the rules are {', '.join(RULES)}")
    if kind not in found.kinds:
        raise ValueError(f"{found.title} gives {', '.join(found.kinds)}, not {kind}")
    if found.takes == "ultimate":
        if ultimate is None:
            if plant is None:
                raise ValueError(f"{found.title} takes the ultimate point, or a plant to find it")
            ultimate = ultimate_of(plant)
        std = found.design(ultimate, kind)
    else:
        if plant is None:
            raise ValueError(f"{found.title} takes a plant")
        if found.takes == "fopdt" and not isinstance(plant, FOPDT):
            raise ValueError(f"{found.title} takes a FOPDT")
        std = found.design(plant, kind, closed_loop_time=closed_loop_time)
    return Design(rule, kind, std, std.parallel(dt, filter), closed_loop_time)


def ultimate_of(plant: Plant, hi: float = 1e3) -> Ultimate:
    """The ultimate point of a plant: where its phase is -180 degrees, the gain that
    makes a proportional loop's magnitude one there."""
    w = _root(lambda x: plant.phase(x) + math.pi, 1e-9, hi)
    if w is None:
        raise ValueError("the plant never reaches -180 degrees: no ultimate point")
    return Ultimate(1 / abs(plant.response(w)), 2 * math.pi / w)


def _root(f: Callable[[float], float], lo: float, hi: float, n: int = 400) -> Optional[float]:
    """The first root of ``f`` on a logarithmic grid from ``lo`` to ``hi``, by bisection."""
    grid = [lo * (hi / lo) ** (i / n) for i in range(n + 1)]
    for a, b in zip(grid, grid[1:], strict=False):
        fa, fb = f(a), f(b)
        if fa == 0:
            return a
        if fa * fb < 0:
            for _ in range(200):
                m = math.sqrt(a * b)
                fm = f(m)
                if fa * fm <= 0:
                    b, fb = m, fm
                else:
                    a, fa = m, fm
            return math.sqrt(a * b)
    return None


# ---- the loop -----------------------------------------------------------------------------


def hold(w: float, dt: float) -> complex:
    """A zero-order hold's response at ``w``: ``(1 - e^(-j w dt)) / (j w dt)``, half a
    sample's delay and a little loss."""
    if w == 0:
        return complex(1, 0)
    x = w * dt
    return (1 - cmath.exp(-1j * x)) / (1j * x)


@dataclass(frozen=True)
class Loop:
    """The open loop of a PID round a plant. ``sampled`` takes the controller as it runs
    (``PIDRunner``) with its hold before the plant: the emulation approximation, which
    leaves out the plant's response folded down from above half the sampling rate."""

    plant: Plant
    pid: PID
    sampled: bool = True

    def response(self, w: float) -> complex:
        c = self.pid.response(w, sampled=self.sampled)
        g = self.plant.response(w)
        return c * g * (hold(w, self.pid.dt) if self.sampled else 1)

    def phase(self, w: float) -> float:
        """Unwrapped, in radians: the plant's analytic phase, the controller's (which
        stays within a half turn below half the sampling rate) and the hold's."""
        c = cmath.phase(self.pid.response(w, sampled=self.sampled))
        held = -w * self.pid.dt / 2 if self.sampled else 0.0
        return self.plant.phase(w) + c + held

    def sensitivity(self, w: float) -> complex:
        return 1 / (1 + self.response(w))

    def complementary(self, w: float) -> complex:
        lw = self.response(w)
        return lw / (1 + lw)

    def setpoint(self, w: float) -> complex:
        """From the setpoint to the output, the derivative acting on the measurement
        alone (as ``PIDRunner``'s does): ``(kp + ki/s) G / (1 + L)``."""
        p = replace(self.pid, kd=0.0)
        c = p.response(w, sampled=self.sampled)
        g = self.plant.response(w) * (hold(w, self.pid.dt) if self.sampled else 1)
        return c * g / (1 + self.response(w))


@dataclass(frozen=True)
class Margins:
    """A loop's margins. Frequencies in rad/s, the phase margin in degrees, the gain
    margin as a ratio (``gain_margin_db`` in decibels); None where there is no crossover
    in the range searched. ``ms`` and ``mt`` are the peaks of the sensitivity and the
    complementary sensitivity, at ``ms_at`` and ``mt_at``."""

    gain_crossover: Optional[float]
    phase_margin: Optional[float]
    phase_crossover: Optional[float]
    gain_margin: Optional[float]
    ms: float
    ms_at: float
    mt: float
    mt_at: float

    @property
    def gain_margin_db(self) -> Optional[float]:
        return None if self.gain_margin is None else 20 * math.log10(self.gain_margin)


def _grid(lo: float, hi: float, n: int) -> List[float]:
    return [lo * (hi / lo) ** (i / (n - 1)) for i in range(n)]


def _bisect(f: Callable[[float], float], a: float, b: float) -> float:
    fa = f(a)
    for _ in range(100):
        m = math.sqrt(a * b)
        fm = f(m)
        if (fa <= 0) == (fm <= 0):
            a, fa = m, fm
        else:
            b = m
    return math.sqrt(a * b)


def _peak(f: Callable[[float], float], grid: List[float]) -> Tuple[float, float]:
    """The largest of ``f`` over ``grid``, refined by golden section between the
    neighbours of the best point."""
    vals = [f(w) for w in grid]
    i = max(range(len(vals)), key=vals.__getitem__)
    a = math.log(grid[max(0, i - 1)])
    b = math.log(grid[min(len(grid) - 1, i + 1)])
    g = (math.sqrt(5) - 1) / 2
    for _ in range(80):
        c, d = b - g * (b - a), a + g * (b - a)
        if f(math.exp(c)) >= f(math.exp(d)):
            b = d
        else:
            a = c
    w = math.exp((a + b) / 2)
    best = f(w)
    if vals[i] > best:
        return vals[i], grid[i]
    return best, w


def _unwrapped(response: Callable[[float], complex], grid: List[float]) -> Callable[[float], float]:
    """The phase of ``response`` unwrapped along ``grid`` from its first point, read at
    any frequency in the grid's range as the principal value nearest the grid's
    unwrapped value at the grid point next below it."""
    raw = [cmath.phase(response(w)) for w in grid]
    unwrapped = [raw[0]]
    for v in raw[1:]:
        unwrapped.append(v + 2 * math.pi * round((unwrapped[-1] - v) / (2 * math.pi)))

    def phase(w: float) -> float:
        j = max(0, min(len(grid) - 1, bisect.bisect_right(grid, w) - 1))
        v = cmath.phase(response(w))
        return v + 2 * math.pi * round((unwrapped[j] - v) / (2 * math.pi))

    return phase


def margins(
    response: Callable[[float], complex],
    phase: Optional[Callable[[float], float]] = None,
    lo: float = 1e-5,
    hi: float = 1e2,
    n: int = 3000,
) -> Margins:
    """The margins of an open-loop response ``L(jw)`` over ``lo`` to ``hi`` rad/s.

    ``phase`` is ``L``'s unwrapped phase in radians; without one the phase is unwrapped
    along the grid. Every gain crossover is found and the smallest phase margin kept;
    every crossing of -180 degrees (and of -540, ...) and the smallest gain margin. The
    peaks are on the grid, refined between its neighbours."""
    grid = _grid(lo, hi, n)
    if phase is None:
        phase = _unwrapped(response, grid)
    mags = [abs(response(w)) for w in grid]
    phs = [phase(w) for w in grid]
    pm = wc = None
    for i in range(1, n):
        if (mags[i - 1] - 1) * (mags[i] - 1) <= 0 and mags[i - 1] != mags[i]:
            w = _bisect(lambda x: abs(response(x)) - 1, grid[i - 1], grid[i])
            m = 180 + math.degrees(phase(w))
            m = (m + 180) % 360 - 180 if m > 180 or m < -180 else m
            if pm is None or m < pm:
                pm, wc = m, w
    gm = wp = None
    for i in range(1, n):
        a, b = phs[i - 1], phs[i]
        # crossings of -180 - 360 k
        for k in range(0, 8):
            level = -math.pi - 2 * math.pi * k
            if (a - level) * (b - level) <= 0 and a != b:
                w = _bisect(lambda x, lv=level: phase(x) - lv, grid[i - 1], grid[i])
                g = 1 / abs(response(w))
                if gm is None or g < gm:
                    gm, wp = g, w
    ms, ms_at = _peak(lambda w: abs(1 / (1 + response(w))), grid)
    mt, mt_at = _peak(lambda w: abs(response(w) / (1 + response(w))), grid)
    return Margins(wc, pm, wp, gm, ms, ms_at, mt, mt_at)


def _span(loop: Loop) -> Tuple[float, float]:
    """From well below the plant's slowest lag to half the sampling rate (the hold's
    emulation goes no further), or far above the fastest lag for a continuous loop."""
    lo = 1e-3 / max(loop.plant.lags)
    hi = math.pi / loop.pid.dt if loop.sampled else 1e3 / min(loop.plant.lags)
    return lo, hi * 0.999


def loop_margins(loop: Loop, n: int = 3000) -> Margins:
    """``margins`` of a PID round a plant, over ``_span``."""
    lo, hi = _span(loop)
    return margins(loop.response, loop.phase, lo, hi, n)


def bode(loop: Loop, n: int = 200) -> Dict[str, List[float]]:
    """The curves a page draws, over ``_span``: the frequency (rad/s); the plant's, the
    open loop's, the sensitivity's and the complementary sensitivity's magnitude, and the
    plant's and the open loop's phase in degrees."""
    lo, hi = _span(loop)
    grid = _grid(lo, hi, n)
    return {
        "w": grid,
        "plant_mag": [abs(loop.plant.response(w)) for w in grid],
        "plant_phase": [math.degrees(loop.plant.phase(w)) for w in grid],
        "loop_mag": [abs(loop.response(w)) for w in grid],
        "loop_phase": [math.degrees(loop.phase(w)) for w in grid],
        "s_mag": [abs(loop.sensitivity(w)) for w in grid],
        "t_mag": [abs(loop.complementary(w)) for w in grid],
    }


# ---- a recorded step ----------------------------------------------------------------------


@dataclass(frozen=True)
class StepMeasures:
    """What a recorded step response says. Times from the step, in the record's unit;
    ``overshoot`` a fraction of the change (0 for none); ``settling_time`` the last time
    the output is outside the band about its final value (None if it never enters it);
    ``steady_error`` the setpoint less the output at the end; ``iae`` the integral of
    the absolute error from the step to the end. A time read from samples is good to the
    sample period."""

    initial: float
    final: float
    change: float
    rise_time: Optional[float]
    overshoot: float
    peak_time: Optional[float]
    settling_time: Optional[float]
    band: float
    steady_error: Optional[float]
    iae: Optional[float]


def step_measures(
    t: Sequence[float],
    y: Sequence[float],
    step_time: float = 0.0,
    setpoint: Optional[Sequence[float]] = None,
    band: Optional[float] = None,
    band_fraction: float = 0.02,
    tail: float = 0.1,
) -> StepMeasures:
    """Rise time (10 to 90 % of the change), overshoot, peak time, settling time into a
    band (``band`` in the output's unit, else ``band_fraction`` of the change), steady
    error and IAE of a step at ``step_time``. Without a ``setpoint`` record the error
    measures are None."""
    initial, final = _ends(t, y, step_time, tail)
    change = final - initial
    if change == 0:
        raise ValueError("no change to measure")
    rising = change > 0
    after = [(s, v) for s, v in zip(t, y, strict=True) if s >= step_time]
    ts = [s for s, _ in after]
    ys = [v for _, v in after]
    t10 = _crossing(ts, ys, initial + 0.1 * change, rising)
    t90 = _crossing(ts, ys, initial + 0.9 * change, rising)
    rise = (t90 - t10) if t10 is not None and t90 is not None else None
    # A peak is looked for before the tail the final value is read over: a highest
    # sample inside the tail is the final value's own wobble, not an overshoot.
    body = max(1, len(ys) - max(1, int(len(y) * tail)))
    if rising:
        i = max(range(body), key=ys.__getitem__)
        over = max(0.0, (ys[i] - final) / change)
    else:
        i = min(range(body), key=ys.__getitem__)
        over = max(0.0, (final - ys[i]) / -change)
    peak_time = ts[i] - step_time if over > 0 else None
    width = band if band is not None else abs(change) * band_fraction
    outside = [s for s, v in zip(ts, ys, strict=True) if abs(v - final) > width]
    if not outside:
        settling = 0.0
    elif outside[-1] >= ts[-1]:
        settling = None
    else:
        settling = outside[-1] - step_time
    err = iae = None
    if setpoint is not None:
        rs = [r for s, r in zip(t, setpoint, strict=True) if s >= step_time]
        n = max(1, int(len(ys) * tail))
        err = sum(r - v for r, v in zip(rs[-n:], ys[-n:], strict=True)) / n
        iae = _trapezoid(ts, [abs(r - v) for r, v in zip(rs, ys, strict=True)])
    return StepMeasures(initial, final, change, rise, over, peak_time, settling, width, err, iae)
