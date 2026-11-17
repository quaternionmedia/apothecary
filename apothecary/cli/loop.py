"""``apothecary loop``: a heater's control loop from the command line.

Identify a plant from a recorded file, design a PID by a named rule, say a loop's margins,
build and read ``control/loop/1`` documents, and run an experiment on a simulated printer.
Nothing here opens a port: ``simulate`` runs the simulated board in this process, on a
state folder of its own; a real machine's experiments are the server's
(``/firmware/printers/loops/*``), behind its latch.
"""

from __future__ import annotations

import csv
import json
import math
import os
import re
import tempfile
import time
from pathlib import Path
from typing import Optional

import click
from pydantic import ValidationError

from .. import control_loops as cl
from .. import loop_document as ld


@click.group()
def loop():
    """A heater's control loop: identify, design, margins, documents, a simulated run."""


def _read_csv(path: Path) -> ld.Samples:
    with open(path, newline="", encoding="utf-8") as fh:
        return ld.samples_from_columns(list(csv.DictReader(fh)))


def _plant(
    gain: float, time_constant: float, dead_time: float, second: Optional[float]
) -> cl.Plant:
    if second:
        return cl.SOPDT(gain, time_constant, second, dead_time)
    return cl.FOPDT(gain, time_constant, dead_time)


def _say_plant(p: cl.Plant) -> str:
    second = (
        f", second time constant {p.second_time_constant:.4g} s" if isinstance(p, cl.SOPDT) else ""
    )
    return f"gain {p.gain:.4g}, time constant {p.time_constant:.4g} s{second}, dead time {p.dead_time:.4g} s"


plant_options = [
    click.option("--gain", type=float, required=True, help="The plant's gain: output per input."),
    click.option(
        "--time-constant", type=float, required=True, help="Its (first) time constant, s."
    ),
    click.option(
        "--dead-time", type=float, default=0.0, show_default=True, help="Its dead time, s."
    ),
    click.option(
        "--second-time-constant", type=float, default=None, help="A second lag, s: a SOPDT."
    ),
]


def _with(options):
    def wrap(f):
        for o in reversed(options):
            f = o(f)
        return f

    return wrap


@loop.command("identify")
@click.argument("path", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option(
    "--method",
    type=click.Choice(["fit", "two-point", "areas"]),
    default="fit",
    show_default=True,
    help="fit: a FOPDT to the power and the temperature; two-point or areas: a step of the input.",
)
@click.option(
    "--sample-period", type=float, default=1.0, show_default=True, help="Read onto this grid, s."
)
@click.option(
    "--step-time", type=float, default=0.0, help="When the input stepped, s (two-point, areas)."
)
@click.option(
    "--input-change", type=float, default=None, help="How far the input stepped (two-point, areas)."
)
@click.option("--json", "as_json", is_flag=True, help="The plant as JSON.")
def identify_cmd(path, method, sample_period, step_time, input_change, as_json):
    """Identify a plant from a recorded file: CSV columns t, target, actual, power."""
    s = _read_csv(path)
    if method == "fit":
        if any(v is None for v in s.power):
            raise click.UsageError("a fit needs the power in every row")
        _, u = cl.resample(s.t, [float(v) for v in s.power], sample_period)
        _, y = cl.resample(s.t, s.actual, sample_period)
        found = cl.fit_fopdt(u, y, sample_period)
    else:
        if input_change is None:
            raise click.UsageError(f"{method} needs --input-change")
        f = cl.two_point if method == "two-point" else cl.areas
        found = f(s.t, s.actual, input_change, step_time=step_time)
    p = found.plant
    if as_json:
        click.echo(
            json.dumps(
                {
                    "model": p.model,
                    "gain": p.gain,
                    "time_constant": p.time_constant,
                    "dead_time": p.dead_time,
                    "method": found.method,
                    "fit_rms": found.fit_rms,
                    "offset": found.initial,
                },
                indent=2,
            )
        )
        return
    click.echo(
        f"{found.method}: {_say_plant(p)}"
        + (f"; RMS left {found.fit_rms:.3g}" if found.fit_rms is not None else "")
    )


@loop.command("rules")
def rules_cmd():
    """The tuning rules, each with its source and what it assumes, and those left out."""
    for r in cl.RULES.values():
        click.echo(f"{r.name}: {r.title} ({', '.join(r.kinds)}; takes {r.takes})")
        click.echo(f"  {r.relation}")
        click.echo(f"  assumes {r.assumes}")
        click.echo(f"  source: {r.source}")
    click.echo("left out:")
    for name, why in cl.LEFT_OUT.items():
        click.echo(f"  {name}: {why}")


@loop.command("design")
@_with(plant_options)
@click.option("--rule", type=click.Choice(sorted(cl.RULES)), default="simc", show_default=True)
@click.option("--kind", type=click.Choice(["p", "pi", "pid"]), default="pi", show_default=True)
@click.option("--closed-loop-time", type=float, default=None, help="SIMC's tau_c, IMC's lambda, s.")
@click.option(
    "--dt", type=float, default=1.0, show_default=True, help="The controller's sample time, s."
)
@click.option(
    "--filter",
    "filter_",
    type=float,
    default=0.0,
    show_default=True,
    help="The derivative filter, s.",
)
@click.option(
    "--bed", is_flag=True, help="Say the line as the bed's (M304), not hotend 0's (M301)."
)
def design_cmd(
    gain,
    time_constant,
    dead_time,
    second_time_constant,
    rule,
    kind,
    closed_loop_time,
    dt,
    filter_,
    bed,
):
    """Design a PID by a named rule; its parallel gains, its ideal form and its margins.
    The gain line is printed, never sent."""
    p = _plant(gain, time_constant, dead_time, second_time_constant)
    d = cl.design(
        rule, plant=p, kind=kind, dt=dt, filter=filter_, closed_loop_time=closed_loop_time
    )
    pid, std = d.pid, d.standard
    click.echo(f"{cl.RULES[rule].title}, {kind.upper()}, for {_say_plant(p)}")
    click.echo(f"  parallel: Kp {pid.kp:.4g}  Ki {pid.ki:.4g} /s  Kd {pid.kd:.4g} s")
    ti = "none" if math.isinf(std.ti) else f"{std.ti:.4g} s"
    click.echo(f"  ideal:    Kc {std.kc:.4g}  Ti {ti}  Td {std.td:.4g} s")
    click.echo(
        f"  line:     {'M304' if bed else 'M301'} P{pid.kp:.2f} I{pid.ki:.4f} D{pid.kd:.2f}  (not sent)"
    )
    _say_margins(cl.loop_margins(cl.Loop(p, pid)))


def _say_margins(m: cl.Margins) -> None:
    def f(v, unit=""):
        return "none" if v is None else f"{v:.4g}{unit}"

    click.echo(
        f"  gain crossover {f(m.gain_crossover, ' rad/s')}, phase margin {f(m.phase_margin, '°')}"
    )
    gm_db = m.gain_margin_db
    click.echo(
        f"  phase crossover {f(m.phase_crossover, ' rad/s')}, gain margin {f(m.gain_margin)}"
        + (f" ({gm_db:.3g} dB)" if gm_db is not None else "")
    )
    click.echo(f"  Ms {m.ms:.3g} at {m.ms_at:.3g} rad/s, Mt {m.mt:.3g} at {m.mt_at:.3g} rad/s")


@loop.command("margins")
@_with(plant_options)
@click.option("--kp", type=float, required=True)
@click.option("--ki", type=float, default=0.0)
@click.option("--kd", type=float, default=0.0)
@click.option(
    "--dt", type=float, default=1.0, show_default=True, help="The controller's sample time, s."
)
@click.option(
    "--filter",
    "filter_",
    type=float,
    default=0.0,
    show_default=True,
    help="The derivative filter, s.",
)
@click.option(
    "--continuous", is_flag=True, help="The controller as continuous: no hold, no sampling."
)
def margins_cmd(
    gain, time_constant, dead_time, second_time_constant, kp, ki, kd, dt, filter_, continuous
):
    """A PID round a plant: crossovers, margins, and the sensitivity peaks."""
    p = _plant(gain, time_constant, dead_time, second_time_constant)
    pid = cl.PID(kp, ki, kd, dt=dt, filter=filter_)
    click.echo(
        f"Kp {kp:g} Ki {ki:g} Kd {kd:g} round {_say_plant(p)}"
        + (" (continuous)" if continuous else f" (sampled every {dt:g} s)")
    )
    _say_margins(cl.loop_margins(cl.Loop(p, pid, sampled=not continuous)))


@loop.command("document")
@click.argument("path", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option(
    "--kind",
    "experiment",
    type=click.Choice(["step", "perturbation", "recorded"]),
    default="recorded",
    show_default=True,
)
@click.option("--sample-period", type=float, default=1.0, show_default=True)
@click.option(
    "--settle-s", type=float, default=None, help="A step's or a wave's time before it, s."
)
@click.option("--period-s", type=float, default=None, help="A perturbation's period, s.")
@click.option("--heater", type=click.Choice(["hotend", "bed"]), default="hotend", show_default=True)
@click.option("--rule", type=click.Choice(sorted(cl.RULES)), default="simc", show_default=True)
@click.option(
    "--controller", type=click.Choice(["p", "pi", "pid"]), default="pi", show_default=True
)
@click.option("--format", "fmt", type=click.Choice(["json", "md"]), default="md", show_default=True)
def document_cmd(
    path, experiment, sample_period, settle_s, period_s, heater, rule, controller, fmt
):
    """Build a control/loop/1 document from a recorded file (CSV: t, target, actual, power)."""
    params = {k: v for k, v in (("settle_s", settle_s), ("period_s", period_s)) if v is not None}
    exp = ld.Experiment(
        id=re.sub(r"[^A-Za-z0-9_.-]+", "_", path.stem).lstrip("_.-") or "recorded",
        kind=experiment,
        started_at=ld.now(),
        sample_period_s=sample_period,
        parameters=params,
        samples=_read_csv(path),
    )
    machine = ld.Machine(kind="printer", port="(a recorded file)")
    try:
        doc = ld.build(exp, machine, ld.LoopName(heater=heater), rule=rule, kind=controller)
    except ValueError as exc:
        raise click.UsageError(str(exc)) from exc
    if fmt == "json":
        click.echo(json.dumps(doc.model_dump(mode="json", by_alias=True), indent=2))
    else:
        click.echo(ld.render_markdown(doc), nl=False)


@loop.command("schema")
def schema_cmd():
    """Print the JSON Schema of control/loop/1."""
    click.echo(json.dumps(ld.LoopDocument.model_json_schema(by_alias=True), indent=2))


@loop.command("validate")
@click.argument("path", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--format", "fmt", type=click.Choice(["summary", "json", "md"]), default="summary")
def validate_cmd(path: Path, fmt: str):
    """Read a loop document back: a summary, the document normalized, or Markdown."""
    try:
        doc = ld.load_document(path)
    except ValidationError as exc:
        click.echo(f"Invalid loop document: {path}", err=True)
        for err in exc.errors():
            loc = ".".join(str(x) for x in err.get("loc", ()))
            click.echo(f"  {loc}: {err.get('msg')}", err=True)
        raise SystemExit(1) from exc
    except json.JSONDecodeError as exc:
        click.echo(f"Not JSON: {path} ({exc})", err=True)
        raise SystemExit(1) from exc
    if fmt == "json":
        click.echo(json.dumps(doc.model_dump(by_alias=True), indent=2))
    elif fmt == "md":
        click.echo(ld.render_markdown(doc), nl=False)
    else:
        n = sum(len(g.figures) for g in doc.groups)
        click.echo(
            f"OK {doc.schema_} · {doc.loop.label} · {len(doc.experiments)} experiments, {n} figures"
        )


@loop.command("simulate")
@click.argument("kind", type=click.Choice(["step", "autotune", "perturbation"]))
@click.option("--heater", type=click.Choice(["hotend", "bed"]), default="hotend", show_default=True)
@click.option("--ceiling", type=float, required=True, help="The ceiling, degC: said every time.")
@click.option(
    "--max-duration", type=float, required=True, help="The longest it may run, s: said every time."
)
@click.option("--base", type=int, help="A step's temperature before it.")
@click.option("--step", "step_c", type=int, help="How far a step goes.")
@click.option("--settle", type=float, help="The time before the step or the wave, s.")
@click.option("--after", type=float, help="A step's time after it, s.")
@click.option("--target", type=int, help="An autotune's target.")
@click.option("--cycles", type=int, help="An autotune's cycles.")
@click.option("--centre", type=int, help="A wave's middle.")
@click.option("--amplitude", type=int, help="A wave's half swing.")
@click.option("--period", type=float, help="A wave's period, s.")
@click.option("--periods", type=int, help="How many periods.")
@click.option(
    "--speed", type=float, default=200.0, show_default=True, help="Simulated seconds a real second."
)
@click.option("--rule", type=click.Choice(sorted(cl.RULES)), default="simc", show_default=True)
@click.option("--format", "fmt", type=click.Choice(["json", "md"]), default="md", show_default=True)
@click.option(
    "--keep",
    type=click.Path(file_okay=False, path_type=Path),
    default=None,
    help="The state folder to keep the run in; a temporary one, removed, without it.",
)
def simulate_cmd(
    kind,
    heater,
    ceiling,
    max_duration,
    base,
    step_c,
    settle,
    after,
    target,
    cycles,
    centre,
    amplitude,
    period,
    periods,
    speed,
    rule,
    fmt,
    keep,
):
    """Run an experiment on a simulated printer whose heaters are modelled, in this
    process, and print its document. No port is opened or listed."""
    with tempfile.TemporaryDirectory(prefix="apothecary-loop-") as scratch:
        folder = keep or Path(scratch)
        from ..firmware.scripted import write_fake_arduino_cli

        # The simulated machines' environment, as `serve --simulated` sets it: every port
        # the simulated engine's, the board list the scripted arduino-cli's, and the
        # state a folder of this run's own.
        (folder / "bench").mkdir(parents=True, exist_ok=True)
        os.environ.update(
            {
                "APOTHECARY_STATE_DIR": str(folder / "state"),
                "APOTHECARY_TOOLS_DIR": str(folder / "tools"),
                "APOTHECARY_SERIAL_ENGINE": "simulated",
                "APOTHECARY_SIMULATED_PRINTER": "idle",
                "APOTHECARY_SIMULATED_DEVKIT": "",
                "ARDUINO_CLI": str(write_fake_arduino_cli(folder / "bench" / "arduino-cli")),
                "ESPTOOL": "none",
            }
        )
        from ..firmware import devices, gcode, loops

        class Fast:
            t0 = time.monotonic()

            @staticmethod
            def now() -> float:
                return (time.monotonic() - Fast.t0) * speed

            @staticmethod
            def sleep(s: float) -> None:
                time.sleep(s / speed)

        port = "/dev/ttyFAKE1"
        links = gcode.PrinterLinks(
            factory=lambda p, b: gcode.SimulatedPrinter(
                p, b, heaters=gcode.simulated_heaters(p), clock=Fast.now
            )
        )
        try:
            plan = loops.plan(
                heater,
                0,
                kind,
                ceiling,
                max_duration,
                1.0,
                base_c=base,
                step_c=step_c,
                settle_s=settle,
                after_s=after,
                target_c=target,
                cycles=cycles,
                centre_c=centre,
                amplitude_c=amplitude,
                period_s=period,
                periods=periods,
            )
        except ValueError as exc:
            raise click.UsageError(str(exc)) from exc
        devices.printer_status(port, links=links)
        links.control.arm(port)
        job = loops.start(port, plan, links=links, clock=Fast.now, sleep=Fast.sleep)
        click.echo(f"{job.what}: simulated, {speed:g} times real time", err=True)
        job.thread.join()
        click.echo(
            f"{job.outcome}" + (f": {job.error}" if job.error else "") + f"; {job.heater_off}",
            err=True,
        )
        doc = loops.document(job.experiment.id, rule=rule, read_board=True, links=links)
        links.stop_all()
        if fmt == "json":
            click.echo(json.dumps(doc.model_dump(mode="json", by_alias=True), indent=2))
        else:
            click.echo(ld.render_markdown(doc), nl=False)
