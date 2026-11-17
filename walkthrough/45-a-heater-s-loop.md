# A heater's loop

**Hermetic.** No machine is asked anything here; `apothecary.control_loops`
computes and `apothecary.loop_document` keeps what it computed.

A printer's hotend is a loop: the board reads the temperature, its PID sets the
heater's power, the heater warms the block a little later and a little slowly.
This page identifies such a heater from a step read once a second, designs a
controller for it by a named rule, and says the loop's margins; it does the same
from a relay, the experiment a firmware's autotune runs, and shows what that
costs. The heater is made up: its numbers are no machine's.
[docs/control-loops.md](../docs/control-loops.md) is the reference.

## A step, read once a second

A first-order lag with a dead time: 2 °C a unit of power, a time constant of a
minute, eight seconds before anything moves.

    >>> import random
    >>> from apothecary import control_loops as cl
    >>> heater = cl.FOPDT(gain=2.0, time_constant=60.0, dead_time=8.0)

Its power is stepped by 20 at ten seconds, from 25 °C, and the temperature read
once a second with a little noise, as a board's `M105` answers:

    >>> rng = random.Random(45)
    >>> t = [float(s) for s in range(601)]
    >>> y = [25 + heater.step(s - 10, 20) + rng.gauss(0, 0.2) for s in t]

The area method reads the plant back from the areas between the response and
its final value; Smith's two points from the times it reaches 28.3 % and 63.2 %
of its change. Both find the heater, the areas a little closer:

    >>> p = cl.areas(t, y, input_change=20, step_time=10).plant
    >>> round(p.gain, 3), round(p.time_constant, 1), round(p.dead_time, 1)
    (1.996, 60.7, 7.9)
    >>> q = cl.two_point(t, y, input_change=20, step_time=10).plant
    >>> round(q.gain, 3), round(q.time_constant, 1), round(q.dead_time, 1)
    (1.996, 59.8, 8.4)

The data came from the model it was fitted to: this shows the arithmetic, not a
heater. A real one is not a first-order lag, and the page says what is left out.

## A controller by a named rule

SIMC's PI, with its closed-loop time the dead time, in the parallel form a
firmware's `M301` takes: `Ki` per second, as the board's PID would run it.

    >>> d = cl.design("simc", plant=p, kind="pi", dt=0.1)
    >>> round(d.pid.kp, 3), round(d.pid.ki, 4), round(d.standard.ti, 1)
    (1.932, 0.0318, 60.7)

Round the plant it was designed for, the loop is `e^(-theta s)/(2 theta s)`:
a gain margin of pi and a phase margin of 61.4 degrees, the figures the rule's
source gives, and a sensitivity peak of 1.59. Round the heater as it is, a
little different from the plant found, the margins move a little:

    >>> m = cl.loop_margins(cl.Loop(p, d.pid, sampled=False))
    >>> round(m.gain_margin, 2), round(m.phase_margin, 1), round(m.ms, 2)
    (3.14, 61.4, 1.59)
    >>> m = cl.loop_margins(cl.Loop(heater, d.pid, sampled=False))
    >>> round(m.gain_margin, 2), round(m.phase_margin, 1), round(m.ms, 2)
    (3.05, 60.7, 1.62)

A step of the setpoint by 5 °C at a minute, run with that controller ten times a
second and read once a second, rises in 14.5 s, overshoots by 5 %, and is within
a tenth of a degree after 47 s:

    >>> run = cl.closed_loop(heater, d.pid, lambda s: 200.0 if s < 60 else 205.0, 600,
    ...                      ambient=25.0, sample=1.0)
    >>> step = cl.step_measures(run.t, run.y, step_time=60, setpoint=run.r, band=0.1)
    >>> round(step.rise_time, 1), round(step.overshoot * 100, 1), step.settling_time
    (14.5, 5.0, 47.0)

## A relay, as an autotune runs it

A relay holds the heater full on below its setpoint and off above, and the
temperature oscillates. For this plant the oscillation has a closed form: an
amplitude of `K d (1 - e^(-theta/tau))` and a period of `2 theta + 2 tau ln(2 -
e^(-theta/tau))`, for a relay of 50 each way:

    >>> a, period = cl.fopdt_relay_exact(heater, 50.0)
    >>> round(a, 2), round(period, 2)
    (12.48, 30.12)

The relay's describing function turns that into the ultimate gain, `4 d / (pi
a)`. It keeps the first harmonic of the relay's square wave alone, and for a
lag with a dead time it reads the gain about a fifth low; the period is close:

    >>> point = cl.relay_point(50.0, a, period)
    >>> true = cl.ultimate_of(heater)
    >>> round(point.ultimate_gain, 2), round(true.gain, 2)
    (5.1, 6.21)
    >>> round(point.ultimate_period, 2), round(true.period, 2)
    (30.12, 30.44)

Ziegler and Nichols' rule on that point is what a firmware's autotune is
documented to compute. Its loop has less margin than SIMC's:

    >>> zn = cl.design("zn_ultimate", ultimate=cl.Ultimate(point.ultimate_gain, point.ultimate_period), dt=0.1)
    >>> round(zn.pid.kp, 2), round(zn.pid.ki, 3), round(zn.pid.kd, 2)
    (3.06, 0.203, 11.52)
    >>> m = cl.loop_margins(cl.Loop(heater, zn.pid, sampled=False))
    >>> round(m.gain_margin, 2), round(m.phase_margin, 1), round(m.ms, 2)
    (2.17, 37.6, 1.88)

## One document of the loop

The step run above, kept as an experiment of a loop's document, `control/loop/1`:
its plant fitted from the power and the temperature, a controller designed, and
each figure saying what it rests on.

    >>> from apothecary import loop_document as ld
    >>> exp = ld.Experiment(id="step-1", kind="step", started_at=ld.now(), sample_period_s=1.0,
    ...                     parameters={"settle_s": 60.0},
    ...                     samples=ld.Samples(t=run.t, target=run.r, actual=run.y, power=run.u))
    >>> doc = ld.build(exp, ld.Machine(kind="printer", port="(this page)"), ld.LoopName(heater="hotend"))
    >>> f = doc.get("plant.time_constant")
    >>> round(f.value, 1), f.basis, f.source
    (61.4, 'identified', 'step-1')

61.4 s and not 60: the record holds the power once a second, as a poll reads it,
and the controller moved it ten times a second between. A fit to such a record
is only as good as that snapshot of the input.

    >>> f = doc.get("loop.phase_margin_designed")
    >>> round(f.value, 1), f.basis, f.source
    (61.4, 'computed', 'plant+controller.designed')
    >>> doc.get("response.overshoot").basis
    'measured'

On a machine the same experiment runs as a job behind the seam's latch, with
its ceiling and its longest time stated, and ends with the heater off;
`apothecary loop simulate step` runs it on the simulated printer, and the
reference says what only a bench can show.
