"""A printer's heater loops through the seam: what its board holds, experiments, gains set.

Heaters are the one place this toolkit can start a fire, so everything here goes through
the seam's own rules and adds no shortcut of its own:

- **Reading** the gains is ``M503``, a report-only query (``devices.printer_query``),
  parsed by ``gcode.parse_gains``.
- **Setting** them is ``M301``/``M304`` with the values, a control line
  (``devices.printer_control``): the latch armed, the dialect's bounds, no job holding the
  port. It is read back by ``M503`` and compared.
- **Saving** them (``M500``, the board's memory written) is refused unless the caller
  asks for it by name (``write_board_memory``); it is never a control line and nothing
  here sends it otherwise.
- **An experiment** is a job (``tune``, apothecary/jobs.py) that holds the port as a
  print does: started only with the latch armed and nothing else on the port, with a
  ceiling and a longest time the caller states every time (``plan``). It reads the
  temperature once a sample period; a reading over the ceiling, the longest time passed,
  no reading for ``SILENCE_S``, the board restarting, a lost link, a cancel, the stop and
  the server stopping each end it, and every end sends the safe-off a cancelled print
  sends (``devices.safe_off``) and reads the target back; a target that is not off then
  gets the stop (``M112``), which halts the board with its heaters off.

The experiments: **a step** of the target (closed loop: in this dialect a heater is told
a target, ``M104``/``M140``, and no line sets its power), **an autotune** (the firmware's
own relay, ``M303``, watched line by line) and **a perturbation** (a square wave of the
target about an operating temperature, for the frequency response). A target changes half
a sample period after a reading, so a reading never falls on a change. Only hotend 0 and
the bed: ``M104`` here names no tool.

What the board says to ``M303``, and how its ``@:`` power is scaled, are assumed, not
established (``gcode.py``'s notes on heater loops); the reference page lists them.
"""

from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from .. import jobs, loop_document
from ..stamped import claim
from ..state_folder import private_folder, state_dir
from . import can, devices, gcode
from .toolchains import ToolchainError

TUNE = jobs.TUNE

MAX_DURATION_S = 2 * 3600.0  # the longest any experiment may be asked to run
SILENCE_S = 15.0  # an experiment that has read no temperature for this long ends
SAMPLES_KEPT = 20000
LINES_KEPT = 400
AUTOTUNE_HEADROOM_C = 5  # an autotune's ceiling stands this far above its target at least


# ---- the plan -----------------------------------------------------------------------------


@dataclass(frozen=True)
class Plan:
    """An experiment as it will run: which loop, its limits, and either the targets it
    sets and when (seconds from its start) or the autotune line it sends."""

    heater: str
    index: int
    kind: str
    ceiling_c: float
    max_duration_s: float
    sample_period_s: float
    changes: Tuple[Tuple[float, int], ...] = ()
    end_s: float = 0.0
    autotune: Optional[str] = None
    parameters: Dict[str, float] = field(default_factory=dict)

    @property
    def loop(self) -> loop_document.LoopName:
        return loop_document.LoopName(heater=self.heater, index=self.index)

    @property
    def what(self) -> str:
        article = {"step": "a step", "autotune": "an autotune", "perturbation": "a perturbation"}
        return f"{article[self.kind]} of {self.loop.label}"

    def target_line(self, target: int) -> str:
        """The control line that sets this loop's target, bounded by the dialect."""
        code = "M140" if self.heater == "bed" else "M104"
        return gcode.normalise_control(f"{code} S{int(target)}")


def _need(p: dict, *names: str) -> None:
    missing = [n for n in names if p.get(n) is None]
    if missing:
        raise ValueError(f"this experiment needs {', '.join(missing)}")


def plan(
    heater: str,
    index: int,
    kind: str,
    ceiling_c: float,
    max_duration_s: float,
    sample_period_s: float = 1.0,
    **p,
) -> Plan:
    """An experiment checked before anything is sent: ValueError naming what is wrong.

    Every target is at or under the ceiling, the ceiling at or under the dialect's cap for
    the heater, and the schedule within the longest time. A step takes ``base_c``,
    ``step_c``, ``settle_s`` and ``after_s``; a perturbation ``centre_c``,
    ``amplitude_c``, ``period_s`` (an even number of samples, eight at least), ``periods``
    and ``settle_s``; an autotune ``target_c`` and ``cycles``, its ceiling
    ``AUTOTUNE_HEADROOM_C`` above its target at least, since a relay swings about it."""
    if heater not in ("hotend", "bed"):
        raise ValueError(f"a loop is a hotend's or the bed's, not {heater!r}")
    if index != 0:
        raise ValueError("only hotend 0 and the bed: a target line here names no tool")
    cap = gcode.BED_MAX_C if heater == "bed" else gcode.HOTEND_MAX_C
    if not 0 < ceiling_c <= cap:
        raise ValueError(f"the ceiling is more than 0 and at most the {heater}'s cap, {cap} degC")
    if not 0 < max_duration_s <= MAX_DURATION_S:
        raise ValueError(f"the longest time is more than 0 and at most {MAX_DURATION_S:.0f} s")
    if not 0.5 <= sample_period_s <= 10:
        raise ValueError("the sample period is 0.5 s to 10 s")
    T = sample_period_s
    p = {k: v for k, v in p.items() if v is not None}
    base = dict(
        heater=heater,
        index=index,
        kind=kind,
        ceiling_c=float(ceiling_c),
        max_duration_s=float(max_duration_s),
        sample_period_s=float(T),
    )

    def under(target: int, what: str) -> int:
        if target <= 0:
            raise ValueError(f"{what} is above 0 degC")
        if target > ceiling_c:
            raise ValueError(f"{what}, {target} degC, is above the ceiling, {ceiling_c:g} degC")
        return int(target)

    if kind == "step":
        _need(p, "base_c", "step_c", "settle_s", "after_s")
        b = under(int(p["base_c"]), "the base")
        s = under(int(p["base_c"]) + int(p["step_c"]), "the step's target")
        if int(p["step_c"]) == 0:
            raise ValueError("a step of 0 degC is no step")
        if p["settle_s"] < 10 * T or p["after_s"] < 10 * T:
            raise ValueError("before and after the step: ten samples each at least")
        end = float(p["settle_s"]) + float(p["after_s"])
        changes = ((0.0, b), (float(p["settle_s"]), s))
    elif kind == "perturbation":
        _need(p, "centre_c", "amplitude_c", "period_s", "periods", "settle_s")
        c, a = int(p["centre_c"]), int(p["amplitude_c"])
        if a < 1:
            raise ValueError("the amplitude is a degree at least")
        under(c + a, "the wave's top")
        under(c - a, "the wave's bottom")
        under(c, "the centre")
        per = float(p["period_s"])
        n = round(per / T)
        if abs(n * T - per) > 1e-9 or n < 8 or n % 2:
            raise ValueError("the period is an even number of samples, eight at least")
        if int(p["periods"]) < 2:
            raise ValueError("two periods at least: one says nothing of its coherence")
        settle = float(p["settle_s"])
        changes = [(0.0, c)]
        for k in range(2 * int(p["periods"])):
            changes.append((settle + k * per / 2, c + a if k % 2 == 0 else c - a))
        end = settle + int(p["periods"]) * per
        changes.append((end, c))
        changes = tuple(changes)
    elif kind == "autotune":
        _need(p, "target_c", "cycles")
        t = under(int(p["target_c"]), "the target")
        if t + AUTOTUNE_HEADROOM_C > ceiling_c:
            raise ValueError(
                f"an autotune's ceiling stands {AUTOTUNE_HEADROOM_C} degC above its target at least"
            )
        e = -1 if heater == "bed" else index
        line = gcode.normalise_autotune(f"M303 E{e} S{t} C{int(p['cycles'])}")
        return Plan(**base, autotune=line, parameters={k: float(v) for k, v in p.items()})
    else:
        raise ValueError(f"no experiment {kind!r}: a step, an autotune or a perturbation")
    if end > max_duration_s:
        raise ValueError(
            f"the schedule takes {end:.0f} s, longer than the longest time, {max_duration_s:.0f} s"
        )
    for _, target in changes:
        Plan(**base).target_line(target)  # bounded by the dialect too
    return Plan(**base, changes=changes, end_s=end, parameters={k: float(v) for k, v in p.items()})


# ---- the job ------------------------------------------------------------------------------


class _Ended(Exception):
    """An experiment ends here, as ``outcome``, for ``reason``."""

    def __init__(self, outcome: str, reason: str):
        super().__init__(reason)
        self.outcome, self.reason = outcome, reason


class LoopJob:
    """An experiment on a heater loop, run on a thread as a job that holds the port.

    ``clock`` and ``sleep`` are the time it runs by: the monotonic clock and a real sleep,
    or a faster pair a test hands it. ``experiment`` is what it kept when it ended."""

    def __init__(
        self,
        port: str,
        plan: Plan,
        links: gcode.PrinterLinks,
        identity: Optional[str] = None,
        firmware: Optional[str] = None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.port, self.plan, self.links = port, plan, links
        self.clock, self.sleep = clock, sleep
        self.firmware = firmware
        self.started = datetime.now(timezone.utc)
        self.stage = "starting"
        self.finished: Optional[datetime] = None
        self.error: Optional[str] = None
        self.outcome: Optional[str] = None
        self.samples: Dict[str, list] = {"t": [], "target": [], "actual": [], "power": []}
        self.lines: List[str] = []
        self.result: Optional[Dict[str, float]] = None
        self.heater_off: Optional[str] = None
        self.experiment: Optional[loop_document.Experiment] = None
        self._cancelled = threading.Event()
        self._quiet = False
        self._t0: Optional[float] = None
        self.job = jobs.Job(
            id=jobs.new_id(self.started, port),
            kind=TUNE.kind,
            machine=jobs.JobMachine(kind="printer", port=port, identity=identity),
            input=jobs.JobInput(name=plan.what),
            started_at=self.started,
            detail=self._detail(),
        )
        self.record: Optional[jobs.Job] = None
        self.thread = threading.Thread(target=self._run, daemon=True, name=f"tune-{port}")

    # -- what it says -----------------------------------------------------------------
    @property
    def what(self) -> str:
        return self.plan.what

    def _elapsed(self) -> float:
        return self.clock() - self._t0 if self._t0 is not None else 0.0

    def _detail(self) -> dict:
        return {
            "experiment": self.plan.kind,
            "loop": self.plan.loop.label,
            "stage": self.stage,
            "samples": len(self.samples["t"]),
            "ceiling_c": self.plan.ceiling_c,
            "max_duration_s": self.plan.max_duration_s,
        }

    def progress(self) -> float:
        if self.plan.autotune:
            return 0.0
        return min(1.0, self._elapsed() / self.plan.end_s) if self.plan.end_s else 0.0

    def now(self) -> jobs.Job:
        if self.record is not None:
            return self.record
        return self.job.model_copy(update={"progress": self.progress(), "detail": self._detail()})

    def snapshot(self, samples: bool = False) -> dict:
        s = self.samples
        out = {
            "kind": TUNE.kind,
            "what": self.what,
            "port": self.port,
            "job_id": self.job.id,
            "experiment": self.plan.kind,
            "heater": self.plan.heater,
            "index": self.plan.index,
            "stage": self.stage,
            "samples": len(s["t"]),
            "reading": s["actual"][-1] if s["actual"] else None,
            "target": s["target"][-1] if s["target"] else None,
            "power": s["power"][-1] if s["power"] else None,
            "ceiling_c": self.plan.ceiling_c,
            "max_duration_s": self.plan.max_duration_s,
            "elapsed_s": round(self._elapsed(), 1),
            "progress": round(self.progress(), 4),
            "since": self.started.isoformat(),
            "finished": self.finished.isoformat() if self.finished else None,
            "outcome": self.outcome,
            "error": self.error,
            "heater_off": self.heater_off,
            "result": self.result,
            "experiment_id": self.experiment.id if self.experiment else None,
            "running": self.finished is None,
        }
        if samples:
            out["series"] = {k: list(v) for k, v in s.items()}
        return out

    def _announce(self) -> None:
        link = self.links.get(self.port)
        if link is not None and self.finished is None:
            link.job = self.snapshot()

    # -- ending -------------------------------------------------------------------------
    def cancel(self, quiet: bool = False) -> None:
        """End it at its next step. ``quiet``: the stop was sent and the board is halted,
        so nothing more is written. Otherwise a break of the wait (``M108``) goes at once,
        ahead of the line in flight: it ends an autotune (assumed of Marlin) and is
        harmless to a board that waits for nothing."""
        if self.finished is not None or self._cancelled.is_set():
            return
        self._quiet = quiet
        self._cancelled.set()
        self.stage = "cancelling"
        self._announce()
        link = self.links.get(self.port)
        if not quiet and link is not None:
            try:
                link.ahead("M108", origin=TUNE.kind)
            except ToolchainError:
                pass  # the heater-off says what the board still answers

    def _check(self) -> None:
        if self._cancelled.is_set():
            raise _Ended("cancelled", "stopped by the stop" if self._quiet else "cancelled")
        if self._elapsed() > self.plan.max_duration_s:
            raise _Ended("failed", f"the longest time, {self.plan.max_duration_s:.0f} s, passed")

    def _guard(self, actual: float) -> None:
        if actual > self.plan.ceiling_c:
            raise _Ended(
                "failed",
                f"{actual:.1f} degC read, over the ceiling of {self.plan.ceiling_c:g} degC",
            )

    # -- reading ------------------------------------------------------------------------
    def _heater_of(self, parsed: dict):
        if self.plan.heater == "bed":
            return parsed.get("bed")
        hotends = parsed.get("hotends") or []
        return hotends[self.plan.index] if len(hotends) > self.plan.index else None

    def _keep(self, heater) -> None:
        s = self.samples
        s["t"].append(round(self._elapsed(), 3))
        s["target"].append(heater.target)
        s["actual"].append(heater.actual)
        s["power"].append(float(heater.power) if heater.power is not None else None)
        if len(s["t"]) > SAMPLES_KEPT:
            raise _Ended("failed", f"more than {SAMPLES_KEPT} samples: the record is full")
        self._guard(heater.actual)

    def _read(self, link: gcode.GcodeLink) -> Optional[gcode.Heater]:
        lines = link.command("M105", timeout=10.0, origin=TUNE.kind, quiet=True)
        line = next((ln for ln in lines if gcode.is_temperature_line(ln)), "")
        parsed = gcode.parse_m105(line)
        heater = self._heater_of(parsed)
        if heater is not None:
            self._keep(heater)
            last = devices.last_statuses().get(self.port)
            if last is not None:
                status = last.model_copy(
                    update={
                        "polled_at": datetime.now(timezone.utc),
                        "hotends": parsed["hotends"] or last.hotends,
                        "bed": parsed["bed"] or last.bed,
                        "raw": lines,
                        "job": self.snapshot(),
                        "synced": [],
                    }
                )
                devices.notify_status(status)
        return heater

    def _sleep_until(self, when: float) -> None:
        while True:
            self._check()
            left = when - self.clock()
            if left <= 0:
                return
            self.sleep(min(left, 0.2))

    def _same_boot(self, link: gcode.GcodeLink, boots: int) -> None:
        link.sweep()
        if link.restarts != boots:
            raise ToolchainError(f"{self.port}: the board restarted under {self.what}")

    # -- the experiments ------------------------------------------------------------------
    def _schedule(self, link: gcode.GcodeLink) -> None:
        T = self.plan.sample_period_s
        changes = list(self.plan.changes)
        boots = link.restarts
        heard = self.clock()
        k = 0
        while True:
            self._check()
            if self._read(link) is not None:
                heard = self.clock()
            elif self.clock() - heard > SILENCE_S:
                raise _Ended(
                    "failed", f"no temperature of {self.plan.loop.label} for {SILENCE_S:.0f} s"
                )
            self._same_boot(link, boots)
            if self._elapsed() >= self.plan.end_s:
                return
            self._sleep_until(self._t0 + (k + 0.5) * T)
            while changes and changes[0][0] <= (k + 0.5) * T:
                _, target = changes.pop(0)
                if target > self.plan.ceiling_c:  # the plan refused it; never sent regardless
                    raise _Ended("failed", f"a target of {target} degC over the ceiling")
                link.command(self.plan.target_line(target), timeout=10.0, origin=TUNE.kind)
            k += 1
            self.stage = "running"
            self._announce()
            self._sleep_until(self._t0 + k * T)

    def _autotune(self, link: gcode.GcodeLink) -> None:
        def each(line: str) -> None:
            self.lines = (self.lines + [line])[-LINES_KEPT:]
            if gcode.is_temperature_line(line):
                heater = self._heater_of(gcode.parse_m105(line))
                if heater is not None:
                    self._keep(heater)
            self._check()

        self.stage = "running"
        self._announce()
        lines = link.watch(
            self.plan.autotune,
            each,
            silence=SILENCE_S,
            limit=self.plan.max_duration_s,
            origin=TUNE.kind,
        )
        said = gcode.parse_autotune(lines)
        if said["failed"]:
            raise _Ended("failed", f"the firmware's autotune failed: {said['failed']}")
        if not {"kp", "ki", "kd"} <= set(said["values"]):
            raise _Ended("failed", "the autotune ended without its gains")
        self.result = said["values"]

    # -- the run --------------------------------------------------------------------------
    def _off(self, link: gcode.GcodeLink) -> List[str]:
        """The heater off, whatever ended the experiment: an autotune's wait broken first,
        then the safe-off a cancelled print sends, each line tried, then the target read
        back. A target that is not off, or a board that does not answer, gets the stop;
        so does an autotune that answers nothing to the break of its wait, at once, since
        a board still in its autotune would hold an off line behind it."""
        said: List[str] = []
        if self.plan.autotune:
            try:
                broke = link.interrupt("M108", wait=10.0, origin=TUNE.kind)
            except ToolchainError as exc:
                broke = [f"(M108 not written: {exc})"]
            said += broke
            if not any(gcode.OK_RE.match(line) for line in broke):
                return said + self._stop(link, "the autotune did not answer the break of its wait")
        said += devices.safe_off(link, "printer", TUNE.kind)
        try:
            lines = link.command("M105", timeout=10.0, origin=TUNE.kind)
            heater = self._heater_of(
                gcode.parse_m105(next((ln for ln in lines if gcode.is_temperature_line(ln)), ""))
            )
            if heater is None or heater.target != 0:
                raise ToolchainError("the target did not read back as off")
            self.heater_off = "heater off: its target read back as 0"
        except ToolchainError as exc:
            said += self._stop(link, str(exc))
        return said

    def _stop(self, link: gcode.GcodeLink, why: str) -> List[str]:
        """The stop (``M112``), which halts the board with its heaters off, said with why."""
        try:
            said = link.emergency_stop()
            self.heater_off = f"the stop was sent ({why}): the board halts with its heaters off"
            return said
        except ToolchainError as stop_said:
            self.heater_off = (
                f"not confirmed: {why}; the stop was not written either ({stop_said}). "
                "The board's own thermal protection is what is left"
            )
            return []

    def _run(self) -> None:
        link = self.links.get(self.port)
        if link is None:
            self.error, self.outcome = "no link", "failed"
            self._finish(None)
            return
        link.job = self.snapshot()
        self._t0 = self.clock()
        outcome, reason = "done", None
        try:
            if self.plan.autotune:
                self._autotune(link)
            else:
                self._schedule(link)
        except _Ended as ended:
            outcome, reason = ended.outcome, ended.reason
        except (ToolchainError, ValueError, OSError) as exc:
            if self._cancelled.is_set():
                outcome, reason = "cancelled", "stopped by the stop" if self._quiet else "cancelled"
            else:
                outcome, reason = "failed", str(exc)
        self.outcome, self.error = outcome, reason if outcome == "failed" else None
        self.stage = outcome
        tail: List[str] = []
        if not self._quiet:
            tail = self._off(link)
        else:
            self.heater_off = "the stop was sent: the board halts with its heaters off"
        link.log.add("sys", f"{self.what} {outcome}" + (f": {reason}" if reason else ""), TUNE.kind)
        self._finish(link, reason, tail)

    def _finish(
        self, link: Optional[gcode.GcodeLink], reason: Optional[str] = None, tail: List[str] = ()
    ) -> None:
        try:
            self.experiment = keep(self)
        except (OSError, ValueError) as exc:
            if link is not None:
                link.log.add("sys", f"{self.what} not kept: {exc}", TUNE.kind)
        detail = self._detail()
        detail.update(
            {
                "heater_off": self.heater_off,
                "result": self.result,
                "experiment_id": self.experiment.id if self.experiment else None,
            }
        )
        self.record = self.job.model_copy(
            update={
                "finished_at": datetime.now(timezone.utc),
                "outcome": self.outcome or "failed",
                "reason": " -- ".join(r for r in (reason, self.heater_off) if r) or None,
                "progress": self.progress(),
                "detail": detail,
                "log": list(tail)[-200:],
            }
        )
        try:
            jobs.end(self.record)
        except (OSError, ValueError) as exc:
            if link is not None:
                link.log.add("sys", f"{self.what} not recorded: {exc}", TUNE.kind)
        if link is not None:
            link.job = None
        self.finished = self.record.finished_at


# ---- what is kept -------------------------------------------------------------------------


def loops_dir() -> Path:
    return state_dir() / "loops"


def keep(job: LoopJob) -> loop_document.Experiment:
    """The experiment as it ended, kept under the job's id: its samples, its limits, how it
    ended and what the firmware said."""
    s = job.samples
    exp = loop_document.Experiment(
        id=job.job.id,
        kind=job.plan.kind,
        started_at=job.started.isoformat(),
        sample_period_s=job.plan.sample_period_s,
        ceiling_c=job.plan.ceiling_c,
        max_duration_s=job.plan.max_duration_s,
        parameters={**job.plan.parameters, "heater": job.plan.heater, "index": job.plan.index},
        outcome=job.outcome or "failed",
        reason=job.error or (job.outcome if job.outcome == "cancelled" else None),
        job=job.job.id,
        samples=loop_document.Samples(
            t=s["t"], target=s["target"], actual=s["actual"], power=s["power"]
        ),
        lines=job.lines[-LINES_KEPT:],
    )
    path = claim(private_folder(loops_dir()), exp.id, ".json")
    exp = exp.model_copy(update={"id": path.name.removesuffix(".json")})
    body = exp.model_dump(mode="json")
    body["port"] = job.port
    body["result"] = job.result
    body["firmware"] = job.firmware
    body["identity"] = job.job.machine.identity
    path.write_text(json.dumps(body, indent=1), encoding="utf-8")
    return exp


def experiments(port: Optional[str] = None) -> List[dict]:
    """The kept experiments, newest first, without their samples: of the port's, or all."""
    folder = loops_dir()
    found = []
    if folder.is_dir():
        for path in folder.glob("*.json"):
            try:
                body = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if port is not None and body.get("port") != port:
                continue
            body.pop("samples", None)
            body.pop("lines", None)
            found.append(body)
    return sorted(found, key=lambda b: b.get("started_at", ""), reverse=True)


def experiment(experiment_id: str) -> Optional[dict]:
    if not jobs.JOB_ID_RE.match(experiment_id or ""):
        return None
    path = loops_dir() / f"{experiment_id}.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


# ---- the running jobs ---------------------------------------------------------------------

_TUNING: Dict[str, LoopJob] = {}


def tuning_job(port: str) -> Optional[LoopJob]:
    return _TUNING.get(port)


def running() -> List[LoopJob]:
    return [job for job in list(_TUNING.values()) if job.finished is None]


def start(
    port: str,
    plan_: Plan,
    state: Optional[devices.FirmwareState] = None,
    links: Optional[gcode.PrinterLinks] = None,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> LoopJob:
    """Begin an experiment on ``port``: refused, before anything is sent, as ``can`` says
    (a task on the port, the latch down, another job on it, no link, the card printing, a
    machine that is not a printer)."""
    state = state or devices.get_state()
    links = links or gcode.get_printer_links()
    with devices.STARTING:
        f = can.facts_of(port, state, links)
        refusal = can.tune_refusal(f)
        if refusal is not None:
            raise refusal.error()
        if links.get(port) is None:
            devices.printer_status(port, state=state, links=links)
        if links.get(port) is None:
            raise ToolchainError(f"{port}: no printer link (is it a G-code printer?)")
        f = can.facts_of(port, state, links)  # identified now, if it was not
        refusal = can.tune_refusal(f)
        if refusal is not None:
            raise refusal.error()
        cached = state.cached_device(port)
        job = LoopJob(
            port,
            plan_,
            links,
            identity=cached.identity if cached is not None else None,
            firmware=cached.printer.firmware_name if cached and cached.printer else None,
            clock=clock,
            sleep=sleep,
        )
        jobs.begin(job.job, live=job.now)
        _TUNING[port] = job
        links.get(port).job = job.snapshot()
        job.thread.start()
        return job


# ---- the gains ----------------------------------------------------------------------------


def _figure(v: float) -> str:
    return f"{v:.4f}".rstrip("0").rstrip(".") or "0"


def gains_line(heater: str, index: int, kp: float, ki: float, kd: float) -> str:
    """The line that sets a loop's gains, bounded by the dialect."""
    if heater not in ("hotend", "bed") or index != 0:
        raise ValueError("only hotend 0 and the bed")
    if min(kp, ki, kd) < 0:
        raise ValueError("gains are not negative")
    code = "M304" if heater == "bed" else "M301"
    return gcode.normalise_control(f"{code} P{_figure(kp)} I{_figure(ki)} D{_figure(kd)}")


def read_gains(
    port: str,
    state: Optional[devices.FirmwareState] = None,
    links: Optional[gcode.PrinterLinks] = None,
) -> dict:
    """The gains the board holds, as ``M503`` says them, by loop, and every line it said."""
    result = devices.printer_query(port, "M503", state, links)
    return {
        "port": port,
        "command": result.command,
        "lines": result.lines,
        "gains": gcode.parse_gains(result.lines),
        "read_at": result.queried_at.isoformat(),
    }


def set_gains(
    port: str,
    heater: str,
    index: int,
    kp: float,
    ki: float,
    kd: float,
    state: Optional[devices.FirmwareState] = None,
    links: Optional[gcode.PrinterLinks] = None,
) -> dict:
    """The gains set on the board (``M301``/``M304``, a control line: the latch, the bounds,
    no job on the port), read back (``M503``) and compared to the figures sent, to the
    hundredth the board is taken to print them to. Set, not saved."""
    line = gains_line(heater, index, kp, ki, kd)
    devices.printer_control(port, line, state, links)
    back = read_gains(port, state, links)
    name = loop_document.LoopName(heater=heater, index=index).label
    got = back["gains"].get(name)
    sent = {
        "kp": float(line.split(" P")[1].split()[0]),
        "ki": float(line.split(" I")[1].split()[0]),
        "kd": float(line.split(" D")[1].split()[0]),
    }
    matches = got is not None and all(
        abs(got[k] - sent[k]) <= 0.0051 + 1e-6 * abs(sent[k]) for k in sent
    )
    return {
        "port": port,
        "loop": name,
        "sent": line,
        "read_back": got,
        "matches": matches,
        "lines": back["lines"],
        "saved": False,
    }


def save_settings(
    port: str,
    write_board_memory: bool = False,
    state: Optional[devices.FirmwareState] = None,
    links: Optional[gcode.PrinterLinks] = None,
) -> dict:
    """``M500``: the board's settings written to its memory, the gains among them. Refused
    unless ``write_board_memory`` asks for it; then as a gain line is (the latch, no job)."""
    state = state or devices.get_state()
    links = links or gcode.get_printer_links()
    refusal = can.save_refusal(can.facts_of(port, state, links), write_board_memory)
    if refusal is not None:
        raise refusal.error()
    if links.get(port) is None:
        devices.printer_status(port, state=state, links=links)
    link = links.get(port)
    if link is None:
        raise ToolchainError(f"{port}: no printer link (is it a G-code printer?)")
    lines = link.command(gcode.SAVE_SETTINGS, timeout=15.0, origin="control")
    links.control.renew(port)
    return {"port": port, "command": gcode.SAVE_SETTINGS, "lines": lines, "saved": True}


# ---- a document of an experiment ------------------------------------------------------------


def document(
    experiment_id: str,
    rule: Optional[str] = "simc",
    kind: str = "pi",
    closed_loop_time: Optional[float] = None,
    read_board: bool = False,
    state: Optional[devices.FirmwareState] = None,
    links: Optional[gcode.PrinterLinks] = None,
) -> loop_document.LoopDocument:
    """The ``control/loop/1`` document of a kept experiment, its figures computed by
    ``loop_document.build``; with ``read_board`` the gains the board holds are read now
    and carried as the controller on the machine."""
    body = experiment(experiment_id)
    if body is None:
        raise ValueError(f"no kept experiment {experiment_id!r}")
    port = body.get("port", "")
    exp = loop_document.Experiment.model_validate(body)
    params = exp.parameters
    loop = loop_document.LoopName(
        heater=str(params.get("heater", "hotend")), index=int(params.get("index", 0))
    )
    machine = loop_document.Machine(
        kind="printer",
        port=port,
        identity=body.get("identity"),
        firmware=body.get("firmware"),
        simulated=gcode.serial_engine() == "simulated",
    )
    on_machine = read = None
    if read_board:
        said = read_gains(port, state, links)
        got = said["gains"].get(loop.label)
        read = loop_document.Experiment(
            id=f"{exp.id}-read",
            kind="read",
            started_at=said["read_at"],
            sample_period_s=exp.sample_period_s,
            lines=said["lines"] or ["(nothing said)"],
        )
        if got is not None:
            on_machine = loop_document.Gains(
                kp=got["kp"], ki=got["ki"], kd=got["kd"], basis="measured", source=read.id
            )
    return loop_document.build(
        exp,
        machine,
        loop,
        rule=rule,
        kind=kind,
        closed_loop_time=closed_loop_time,
        on_machine=on_machine,
        read=read,
        autotune=body.get("result"),
    )
