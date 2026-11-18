# Control loops

A printer's hotend and its bed are loops: the board reads a temperature, its PID
sets the heater's power, and the heater warms what it heats a little later and a
little slowly. Apothecary describes such a loop, identifies its plant from what a
machine reports, designs a controller for it by a named rule, measures how the loop
responds, and runs the experiments that feed all of it on the machine, through the
seam's rules. Three modules hold it, and a window shows it:

| Module | |
|---|---|
| `apothecary/control_loops.py` | The maths, standard library only: plants, the PID in two forms, identification, rules, margins and a recorded step's measures |
| `apothecary/loop_document.py` | `control/loop/1`, one loop of one machine as a document: its schema, a builder that computes its figures, and a Markdown view |
| `apothecary/firmware/loops.py` | The machine: the gains a board holds, read, set and saved on request, and experiments run as jobs |
| `apothecary/static/widgets/loops.js` | [The Loops window](#the-loops-window): a loop of the printer whose Machine is open, drawn from the server's answers by `static/loop_plots.js` |

[Walkthrough page 45](../walkthrough/45-a-heater-s-loop.md) identifies a made-up
heater, designs for it and says its margins, in doctests.

## What a loop is taken to be

A plant is linear and time-invariant: first order plus dead time,
`K e^(-theta s) / (tau s + 1)` (`FOPDT`), or second order plus dead time, two lags in
series (`SOPDT`). Its input is the heater's power as the board counts it, its output
the temperature's rise over an ambient that stands still. Those are the model's
assumptions, and every figure computed from a model stands on them. A heater is not
that: it loses heat faster as it gets hotter (convection and radiation), a part
cooling fan and the filament flowing through a hotend take heat out in steps, a
thermistor lags the block it sits in and reads through an ADC with a resolution of
its own, and the power a board's `@:` reports is a snapshot of a PWM that moves many
times between two polls. A model identified at one temperature describes the loop
near that temperature.

The step response of either plant is computed by its exact formula. `PlantRunner`
steps a plant through time with its input held over each step, by the exact
discretization of its lags, so with a dead time that is a whole number of steps it
equals the formula to rounding, which its test holds.

## The PID

`PID` is the parallel form, `u = kp e + ki * integral(e) + kd * de/dt`, as Marlin's
`M301` (a hotend) and `M304` (the bed) take it: `kp` in power per degree, `ki` per
second, `kd` in seconds. That the board's figures are in those units is assumed;
see [What is established](#what-is-established-and-what-is-assumed). The form carries
its sample time `dt` and a first-order filter on the derivative of time constant
`filter`; a firmware's per-sample smoothing `a` is the backward-Euler image of a
filter of `a dt / (1 - a)` (`filter_of`). `Standard` is the ideal form,
`kc (e + integral(e)/ti + td de/dt)`; the two convert exactly both ways, and
`series_to_standard` turns a series PID into the ideal one it equals.

`PIDRunner` runs one a sample at a time: the derivative on the measurement through
its filter (so a step of the setpoint kicks nothing), the integral a rectangle sum
that does not grow while the output is clamped and the error would push it further.
Its response is the sampled controller's, `PID.response(w, sampled=True)`, which its
test holds sample by sample.

A designed controller is for the board's PID, which runs at the board's own sample
time; that time is not known here. Margins of a designed controller and of the board's
own gains are therefore of the continuous controller. `Loop(sampled=True)` adds a
controller's hold and its rectangles for a known sample time, by the emulation
approximation, which leaves out what the plant passes above half the sampling rate.

## Identification

| From | Method | What it gives | Exact for |
|---|---|---|---|
| A step of the input | `two_point`: Smith's two points, the times at 28.3 % and 63.2 % of the change are `theta + tau/3` and `theta + tau` | a FOPDT | a FOPDT |
| A step of the input | `areas`: the area method, `A0 = K (theta + tau)` above the response and `A1 = K tau / e` under it up to `A0` | a FOPDT | a FOPDT; the integrals average noise out |
| A relay | `relay_point`: the describing function of a relay of amplitude `d` holding an oscillation of amplitude `a` and period `T` | the plant's magnitude `pi a / (4 d)` at `2 pi / T`, at a phase of `-180 + asin(eps / a)` degrees for a hysteresis `eps`; with none, the ultimate gain `4 d / (pi a)` and period `T` | a plant that passes the first harmonic alone |
| An input and an output | `fit_fopdt`: the plant simulated from the recorded input against the recorded output, its time constant and dead time searched, its gain and an offset fitted | a FOPDT and an ambient | noise-free data from a FOPDT |
| An input and an output | `frequency_response`: the plant at the harmonics an excitation of known period puts in, from the cross-spectra with the setpoint over whole periods | a point of the plant per harmonic, each with its coherence and how far it stands above the noise beside it | a linear loop, no noise |

The describing function keeps only the first harmonic of the relay's square wave.
For a FOPDT the relay's true limit cycle has a closed form (`fopdt_relay_exact`), and
against it the relation reads the ultimate gain between 15 % and 20 % low over the
dead times the tests run, and the period within a few percent. A firmware's
autotune that computes its gains from the describing function carries that error
into them.

A heater is read about once a second. That sets what a frequency response can say:

- Half the sampling rate is the last frequency there is; a harmonic at or above it is
  left out, and above a quarter of it a point is at best `fair`.
- A slow heater passes little of a fast harmonic, so the output there sinks into the
  noise: `above_noise` compares the output at a harmonic with its mean at the
  neighbouring frequencies nothing excited, and the point is `poor` under three times
  it or with a coherence under a half, `good` over ten times it with a coherence of 0.9.
- One period gives a coherence of 1 by its construction; the point is `unknown`. Two
  periods are the least an experiment is allowed.
- A setpoint's square wave makes the controller's output jump at each edge, and a jump
  read on a reading's instant is read as half a sample early: the plant's phase comes
  out half a sample late. An experiment changes its target half a sample period after a
  reading, so a reading never falls on an edge.
- The power is a snapshot of a PWM the controller moves between polls. The coherence
  says nothing of that bias: noise-free, the estimate still drifts at the higher
  harmonics, and the fit's time constant comes out a little long
  (walkthrough page 45 shows it).

In a closed loop the noise on the reading reaches the heater's power through the
controller, so the plant from power to temperature, estimated against the power
alone, leans towards the inverse of the controller; against the setpoint, which the
noise does not reach, it does not.

## Rules

Each rule is a named relation with its source, what it takes and what it assumes
(`RULES`; `apothecary loop rules` prints them).

| Rule | Source | Takes | Gives |
|---|---|---|---|
| `zn_ultimate` | Ziegler and Nichols (1942) | the ultimate point | P, PI, PID |
| `zn_reaction` | Ziegler and Nichols (1942), as Astrom and Hagglund state it | a FOPDT | P, PI, PID |
| `tyreus_luyben` | Tyreus and Luyben (1992) | the ultimate point | PI, PID |
| `cohen_coon` | Cohen and Coon (1953) | a FOPDT | PI, PID |
| `simc` | Skogestad (2003), with the closed-loop time a parameter | a FOPDT (PI) or a SOPDT (PID) | PI, PID |
| `imc` | Rivera, Morari and Skogestad (1986), the dead time by first-order Pade, the closed-loop time a parameter | a FOPDT | PID |
| `amigo` | Astrom and Hagglund (2004, 2006) | a FOPDT | PI, PID |

A rule that takes the ultimate point is given a plant's when only a plant is at hand
(`ultimate_of`). IMC's closed-loop time defaults to the dead time, as SIMC's does: that
default is this module's, not the source's. The tests hold each rule to its formula,
SIMC's PI to the margins its source gives, IMC-PID to the IMC controller it is derived
from, and AMIGO's PID to the sensitivity peak it was chosen for.

Left out, because their constants are not stated here with confidence:
Chien-Hrones-Reswick's tables, Astrom and Hagglund's kappa-tau curves, Pessen's
some-overshoot and no-overshoot rules, and the many lambda-tuning tables, for which
IMC-PID and SIMC stand (`LEFT_OUT`).

## Measures

`margins` takes an open loop's response and finds every gain crossover (keeping the
least phase margin) and every crossing of -180, -540 ... degrees (keeping the least
gain margin), and the peaks of the sensitivity `|1/(1 + L)|` and the complementary
sensitivity `|L/(1 + L)|`, refined between grid points. Its tests are an integrator
with a dead time and a second-order loop, whose margins and peaks have closed forms.
`loop_margins` searches a PID round a plant from well below its slowest lag to half the
sampling rate; `bode` gives the curves a page draws over the same span.

`step_measures` reads a recorded step: rise time (10 to 90 % of the change), overshoot
and its time, settling time into a band about the final value, the steady error
against the setpoint, and the integrated absolute error. A time read from samples is
good to the sample period. The level before the step is read where the record had
settled, so a record that begins with a heat-up is read right.

## The document

A loop is one document, `control/loop/1`: the machine and the loop (a hotend by its
number, or the bed), its experiments, the plant identified, the controller as designed
and as read back from the board, the frequency points, and five fixed groups of
figures -- `plant`, `controller`, `loop`, `response`, `experiment` -- whose keys are
open, as `airgap/metrics/1`'s are. Every figure says what it rests on:

| Basis | Means | Its source |
|---|---|---|
| `measured` | read from the machine, or from an experiment's samples by arithmetic alone | an experiment of the document |
| `identified` | a model's parameter fitted to an experiment, or what the firmware computed from its own experiment | an experiment of the document |
| `computed` | from a model alone: a margin, a designed gain | the parts it is computed from, `plant`, `controller.designed`, `controller.on_machine`, joined by `+` |

The validator refuses a figure resting on a part the document does not carry.
`GET /firmware/loops/schema` publishes the schema; `POST /firmware/loops/validate` and
`apothecary loop validate` read a document back, as JSON or Markdown.

Where it departs from the Airgap's document, and why:

- **Python computes the figures; a page renders them.** The Airgap's figures can only
  be computed by its panel's JavaScript model, so there the panel is the collector and
  Python the view. A loop's experiments run on the server, its figures are wanted from
  the command line, and its maths has closed-form tests in Python, so here
  `apothecary.control_loops` is the one engine and every other surface a view: one
  component computes either way, and it is a different one.
- **A loop's document carries an experiment's samples.** A document is still one
  loop at one moment and is not committed; the samples are what its measured and
  identified figures rest on, and a reader re-deriving one reads them.

## Through the machine

`apothecary/firmware/loops.py`, behind the seam's rules ([Firmware](firmware.md#heater-loops)):

| Act | Line | What it needs |
|---|---|---|
| Read the gains | `M503`, report-only | no job other than a streamed one on the port |
| Set the gains | `M301 P.. I.. D..` (hotend 0), `M304 P.. I.. D..` (the bed), a control line bounded by `gcode.GAIN_MAX` | the latch armed, no job on the port; read back by `M503` and compared |
| Save them | `M500`, the board's memory written | `write_board_memory: true` in the request, in so many words; then as a set |
| Run an experiment | below | the latch armed, nothing else on the port, a ceiling and a longest time stated |

### The experiments

Each is a `tune` job (`apothecary/jobs.py`) that holds the port as a print does. It is
planned before anything is sent (`loops.plan`): every target at or under the ceiling,
the ceiling at or under the dialect's cap for the heater, the schedule within the
longest time, which is at most two hours. What each kind takes beside its ceiling and
its longest time is `loops.KINDS`, which `plan` reads its needs from and
`GET /firmware/loops/kinds` lists, each figure with a value to start from for a hotend
and for the bed; the ceiling and the longest time have none.

Only hotend 0 and the bed: a target line here names no tool. A second hotend needs a
`T` word on `M104` among the dialect's control lines (and on `M109`, which a print
sends), `M301` taking an `E` past `E0`, the safe-off a cancelled print sends -- which
names `M104 S0`, hotend 0's -- turning it off too, the same in what goes with the latch
down (`gcode.ALWAYS`, `can.js`'s off lines), and a simulated board with two hotends; a
board's status already lists every hotend it reports.

| Experiment | What it sends | What it is for |
|---|---|---|
| A step | `M104 S<base>` (`M140` for the bed), held, then `M104 S<base + step>` | a closed-loop step: the plant fitted from the power and the temperature, the step measured |
| An autotune | `M303 E<n> S<target> C<cycles>` (`E-1` the bed), sent by the job alone and watched line by line | the firmware's own relay and its gains |
| A perturbation | `M104 S<centre>`, then a square wave of the target about it | the frequency response at the odd harmonics, against the target |

In this dialect a heater is told a target and no line sets its power, so a step is a
step of the setpoint in closed loop, and the plant is fitted from the power the board
reports. While a step or a perturbation runs, the job reads `M105` once a sample
period and changes a target half a period after a reading. Its schedule is kept by the
clock, not by readings counted: readings slower than the period are fewer samples, and
each target is still set after the first reading past its time. While an autotune runs,
the board answers nothing else; the job reads the temperatures the board says as it goes.

An experiment ends -- done, a reading over its ceiling, its longest time passed, no
temperature read for fifteen seconds, its end come with a target of its schedule not
set, the board restarting, an objection, a lost link, a cancel, the stop, or the server
stopping -- and every end but the stop sends the safe-off a cancelled print sends
(`M104 S0`, `M140 S0`, `M107`, `M84`), each line tried,
after an autotune's wait is broken (`M108`), and reads the target back. A target that
does not read back as off, or a board that does not answer, is sent the stop (`M112`),
which halts the board with its heaters off until it is reset. An autotune whose board
answers nothing to the break of its wait gets the stop at once, with no off line first:
a board still in its autotune would hold an off line behind it. A board that has gone
cannot be told anything: the job says the heater is not known to be off, and the
board's own thermal protection is what is left. An experiment the server was running
when it died is found by the next poll of its port, ended as failed, and its heaters
turned off, as an orphaned print's are. The stop ends one at once and sends nothing
after itself.

`can_now` answers `tune.start`, `tune.cancel`, `tune.read`, `tune.set` and `tune.save`
from the predicates the routes raise from, so a page greys what the server would
refuse; `tune.save` is refused, kind `asked`, until a request asks for the board's
memory by name. The routes are `POST /firmware/printers/loops/read`, `start`, `cancel`,
`set`, `save`, `document`, `curves` (what a page draws of a loop, computed here: the
open loop over frequency with each controller, where it crosses and peaks with the
margins the document says, the frequency points measured with their trust, and the
measured temperature beside the model's step through the same targets, its PID run at a
stated stand-in rate) and `can-start` (whether an experiment of the figures sent would
start now: `tune.start`'s verdict, then the plan's, kind `plan`, with the plan when it
would; nothing is sent), `GET /firmware/printers/loops/job` (with `series`, its samples
so far) and `experiments`, and `GET /firmware/loops/rules` and `kinds`. A kept
experiment is in the state folder's `loops/`, under its job's id.

### What is established and what is assumed

| | |
|---|---|
| Established in this repository | `M503` is report-only and answers with the settings as G-code lines, `M301` and `M304` among them ([the bench checklist](bench-checklist.md) keeps them from it); `M500` saves the settings to the board's memory and no streamed file may carry it; `M105` answers `T:<actual> /<target> B:.. /.. @:<power> B@:<power>` (a recorded board's reply, `tests/firmware_helpers.py`); `M112` halts the board; the latch, the bounds and the safe-off are the seam's |
| Assumed, from Marlin's documentation as recalled, not its source or a board | that `M301`/`M304` take `P`, `I` and `D` with `I` per second and `D` in seconds and print them to the hundredth; that `M303` is `M303 E<n> S<target> C<cycles>` with `E-1` the bed; the words of its result (`Kp:`, `Ki:`, `Kd:`, `Ku:`, `Tu:`, `#define DEFAULT_Kp`, `PID Autotune finished`, `PID Autotune failed`); that it reports temperatures as it runs; that `M108` ends it; that it computes the classic Ziegler-Nichols gains from the describing function; that `@:` counts the power from 0 to 255 as the PID's output does; that the PID's derivative is smoothed and that it is full on or off outside a range of the target |

Nothing here sends `M303`, `M301`, `M304` or `M500` to a real board yet. Each
assumption is a line to keep at the bench, and the parsers read the forms named and
nothing more: a board that says something else is an experiment that ends without a
result, with the heater turned off.

## The Loops window

The **Loops** window (`apothecary/static/widgets/loops.js`) is a heater loop of the
printer whose Machine is open, in the page: ⊞ Windows › Loops, or the ring's Panels ›
Machine › Loops › Loops. It is a window of the Machine's group, closed until asked for;
with no printer's Machine open it says so, and every button is greyed with why. For the
loop chosen, hotend 0 or the bed:

| Part | What it shows | From |
|---|---|---|
| The board and the design | The gains the board holds, read back by Read (`M503`), and when it answered; beside them the controller designed for the identified plant, by the rule and kind chosen from the rules the server lists | `POST /firmware/printers/loops/read`; the document's `controller`; `GET /firmware/loops/rules` |
| The experiment | Its kind, its figures as the server lists them, its ceiling and its longest time; the plan the server makes of them; Start and Cancel; its stage, progress, reading, target and power as it runs, and how it ended | `GET /firmware/loops/kinds`; `POST /firmware/printers/loops/can-start`; the `tune` surface |
| The plots | The newest kept experiment of the loop: its measured temperature beside the model's step; the open loop's magnitude and phase over frequency, the crossovers marked with the margins; the sensitivity and the complementary sensitivity with their peaks; a perturbation's measured points of the plant, each drawn as its trust says -- good filled, fair faint, poor hollow and broken, unknown a hollow square | `POST /firmware/printers/loops/curves` |
| The figures | The plant's, the controller's, the loop's margins and peaks, the step's measures and the experiment's, each with its unit, its basis and what it rests on | `POST /firmware/printers/loops/document` |

The page computes nothing the server computes. `apothecary/static/loop_plots.js` maps
the answer's numbers onto plots and rounds a figure as the document's Markdown view
does, and nothing else; every series and mark carries the answer's own number.

**Start** is greyed until the server says the figures would start. The ceiling and the
longest time have no value to start from: the window sends neither until a person types
them, and `can-start` answers the machine's verdict first (`tune.start`: the latch, a job
on the port, the card printing), then the plan's -- which of the two is not stated, a
target over the ceiling, a schedule longer than the longest time. Read, Cancel and Set
on machine are greyed from the board's own answer (`tune.read`, `tune.cancel`,
`tune.set`). A greyed button's title says the server's reason before its own tip, and
the address of its cell.

**An experiment's progress** comes from the surfaces' stream (`GET
/surfaces/events?names=tune,control_loop`): `tune` tells its stage and each whole
percent, `control_loop` the kept experiment when it ends, whose document the window then
asks for by its own rule. Where the stream is not open, the window asks `GET
/firmware/printers/loops/job` once a second while one runs.

**Set on machine** sends the designed gains (`M301` or `M304`, the latch armed), reads
them back, says whether the board holds what was sent, and reads the board again for the
document. Nothing in the window, and no cell of its ring, saves gains to the board's
memory. A person who means to asks for it by name, the latch armed in the printer's
Machine, against the server:

```bash
curl -X POST http://127.0.0.1:6283/firmware/printers/loops/save \
  -H 'Content-Type: application/json' \
  -d '{"port": "/dev/ttyUSB0", "write_board_memory": true}'
```

**A board that identifies nothing.** A board whose heaters jump to their targets -- the
simulated printer without `APOTHECARY_SIMULATED_HEATERS=model`, as `apothecary serve
--simulated` runs it -- reports one power whatever its target. In closed loop a target
that moves moves the power that drives the heater, so a step or a perturbation whose
power stood still while its targets moved is refused a document
(`loop_document.unidentifiable`), naming the power it stood at, rather than fitted to
nothing; the window says the server's words in place of the curves. An autotune
identifies no plant either: its gains are the firmware's own, and the window says so.

**Its ring** is Panels › Machine › Loops: Loops 8 (the window), Read 6, Start 2,
Cancel 4, Set gains 9, Loop 3 (Hotend 0, Bed), Experiment 1 (Step, Autotune,
Perturbation) and Rule 7 (each rule a ring of the kinds of controller it gives). A cell
does what its control does; one the server would refuse says why on the status line.
[Walkthrough page 48](../walkthrough/48-a-heater-s-loop-in-the-page.md) shows it.

## The simulated board

With `APOTHECARY_SIMULATED_HEATERS=model` the simulated printer's heaters
(`gcode.SimulatedHeater`) are each a FOPDT from power to the rise over ambient, with a
PID round it in the manner assumed of Marlin -- the derivative smoothed, full on or off
outside a range of the target -- stepped in simulated time that
`APOTHECARY_SIMULATED_HEATER_SPEED` runs faster than real time. Its gains are designed
for its own plants by IMC-PID. It answers `M105` with the reading, the target and the
power, `M503` and `M301`/`M304` with its gains and takes new ones, runs a relay
autotune for `M303` in the forms the parser reads while the lines written meanwhile
wait, ends it at `M108`, and counts `M500`. Its numbers are the simulator's and no
machine's. A plant identified from it is its own model found again: that holds the
code and the pipeline, and says nothing of a heater.

## What is measured, and what is not

| Measured or computed here | Not here |
|---|---|
| A loop's plant as a FOPDT near one temperature, from a step, a relay or a perturbation | How the plant changes with temperature, with the fan, with filament flowing |
| The controller a rule gives for that plant, and its margins and peaks round it | Whether those margins hold round the real heater: they are the model's |
| The board's own gains, read back after a set | The board's PID's sample time, and its own handling of the integral and the derivative |
| A step's rise, overshoot, settling and error, as read once a second | What happens between two readings |
| The frequency response at the harmonics excited, with how far each point stands above the noise | Anything above half the sampling rate; the bias of a power read as a snapshot |

## At the bench

What only a bench can say, in the order to find it out:

1. **What the board says.** With a person at the printer, `M503` read (`apothecary
   firmware printer PORT --query M503`) and kept whole; then `M301` and `M304` with no
   arguments; then, on a heater at room temperature, the lines a short `M303` says,
   kept whole. That confirms or corrects every assumed form above before the parsers
   are trusted with a real board, and says whether `M108` ends an autotune.
2. **What `@:` counts.** A heater held full on from cold (a target well above its
   temperature, watched) reads its top: 255 or 127 says the scale the plant's gain is in.
3. **A step at a working temperature.** Hotend 0 held at a usual printing temperature,
   stepped by a few degrees with a ceiling a little above, the fan off and then on: the
   fitted plant, the board's own gains' margins round it, and how far the two runs differ.

The owner decides which loops are tuned, the ceilings, and whether apothecary may
write a board's memory at all.

## The command line

`apothecary loop identify` (a recorded CSV of `t`, `target`, `actual`, `power`),
`design`, `margins`, `rules`, `document`, `validate`, `schema`, and `simulate` (a step,
an autotune or a perturbation on the simulated printer, in its own process and state
folder). `uv run apothecary loop --help` lists them.
