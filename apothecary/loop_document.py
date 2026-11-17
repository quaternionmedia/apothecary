"""A machine's control loop as one document, ``control/loop/1``: its schema, a builder and a view.

One loop of one machine -- a printer's hotend or its bed -- with the experiments run on it
(their samples, or the job that holds them), the plant identified from one, the controller
as designed and as read back from the board, the frequency response an experiment
excited, and the figures that follow, grouped as the Airgap's metrics are.

Every figure says what it rests on (``basis``):

- ``measured``: read from the machine, or from an experiment's samples by arithmetic
  alone (a peak, a settling time, the gains the board answered with);
- ``identified``: a model's parameter fitted to an experiment's samples, or what the
  firmware computed from its own experiment (an autotune's gains);
- ``computed``: from a model alone -- a margin, a designed gain, the model's own step.

and where (``source``): an experiment's id for the first two, and for a computed figure the
parts of the document it is computed from, joined by ``+`` (``plant``,
``controller.designed``, ``controller.on_machine``). The validator holds each to a part the
document has: a figure cannot claim a measurement the document does not carry.

The figures are computed by ``apothecary.control_loops`` (``build``); a page or a Markdown
table renders the document and computes nothing, so what a page draws of a loop is a
claim about the document it was given. Values are stored at full precision; views round.

Groups are a contract (``GroupId``); keys inside a group are open.
"""

from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Literal, Optional, Sequence, Union

from pydantic import BaseModel, Field, field_validator, model_validator

from . import control_loops as cl

SCHEMA = "control/loop/1"
GENERATOR = "apothecary.control_loops"

Basis = Literal["measured", "identified", "computed"]
GroupId = Literal["plant", "controller", "loop", "response", "experiment"]
GROUP_TITLES: Dict[str, str] = {
    "plant": "Plant",
    "controller": "Controller",
    "loop": "Loop (from the model)",
    "response": "Response",
    "experiment": "Experiment",
}
PARTS = ("plant", "controller.designed", "controller.on_machine")
ID = r"^[A-Za-z0-9][A-Za-z0-9_.\-]{0,119}$"

FigureValue = Union[float, int, bool, str, None]


def _finite(v):
    if isinstance(v, float) and not math.isfinite(v):
        raise ValueError("values are finite; null stands for unavailable")
    return v


class Figure(BaseModel):
    """One figure: a stable key, a label, a value with its unit, what it rests on and where."""

    key: str = Field(..., pattern=r"^[a-z][a-z0-9_]*$")
    label: str
    value: FigureValue = None
    unit: str = ""
    note: str = ""
    basis: Basis
    source: str

    @field_validator("value")
    @classmethod
    def _finite_value(cls, v: FigureValue) -> FigureValue:
        return _finite(v)


class FigureGroup(BaseModel):
    id: GroupId
    title: str = ""
    figures: List[Figure] = Field(default_factory=list)

    @model_validator(mode="after")
    def _unique_keys(self) -> "FigureGroup":
        keys = [f.key for f in self.figures]
        dup = {k for k in keys if keys.count(k) > 1}
        if dup:
            raise ValueError(f"duplicate figure keys in group {self.id}: {sorted(dup)}")
        if not self.title:
            self.title = GROUP_TITLES[self.id]
        return self


class Machine(BaseModel):
    """Which machine: its kind, its port, the board's identity when known, its firmware,
    and whether it is a simulated one."""

    kind: Literal["printer"]
    port: str
    identity: Optional[str] = None
    firmware: Optional[str] = None
    simulated: bool = False


class LoopName(BaseModel):
    """Which loop: a hotend by its number, or the bed."""

    heater: Literal["hotend", "bed"]
    index: int = Field(0, ge=0, le=7)

    @property
    def label(self) -> str:
        return f"hotend {self.index}" if self.heater == "hotend" else "bed"


class Samples(BaseModel):
    """An experiment's readings: seconds from its start, the target set, the temperature
    read and the heater's power as the board reported it (null where it did not)."""

    t: List[float]
    target: List[float]
    actual: List[float]
    power: List[Optional[float]]

    @model_validator(mode="after")
    def _same_length(self) -> "Samples":
        n = len(self.t)
        if not (len(self.target) == len(self.actual) == len(self.power) == n):
            raise ValueError("t, target, actual and power are of one length")
        for v in (*self.t, *self.target, *self.actual, *(p for p in self.power if p is not None)):
            _finite(v)
        if any(b < a for a, b in zip(self.t, self.t[1:])):
            raise ValueError("t does not go back")
        return self


class Experiment(BaseModel):
    """One experiment on the loop: what kind, its limits, how it ended, and its samples or
    the job record that holds them. A ``read`` is the board asked for its settings: its
    lines are what it answered, and the gains read from them rest on it."""

    id: str = Field(..., pattern=ID)
    kind: Literal["step", "autotune", "perturbation", "recorded", "read"]
    started_at: str
    sample_period_s: float = Field(..., gt=0)
    ceiling_c: Optional[float] = None
    max_duration_s: Optional[float] = None
    parameters: Dict[str, Union[float, int, str]] = Field(default_factory=dict)
    outcome: Literal["done", "cancelled", "failed"] = "done"
    reason: Optional[str] = None
    job: Optional[str] = None
    samples: Optional[Samples] = None
    lines: List[str] = Field(default_factory=list)  # what the firmware said worth keeping

    @model_validator(mode="after")
    def _has_data(self) -> "Experiment":
        if self.kind == "read":
            if not self.lines:
                raise ValueError(f"the read {self.id} carries the lines the board answered")
        elif self.samples is None and self.job is None:
            raise ValueError(f"experiment {self.id} carries its samples or names its job")
        return self


class PlantModel(BaseModel):
    model: Literal["fopdt", "sopdt"]
    gain: float
    time_constant: float = Field(..., gt=0)
    second_time_constant: Optional[float] = Field(None, gt=0)
    dead_time: float = Field(0.0, ge=0)
    ambient: Optional[float] = None
    basis: Literal["identified", "computed"]
    source: str
    method: str

    @model_validator(mode="after")
    def _shape(self) -> "PlantModel":
        if (self.model == "sopdt") != (self.second_time_constant is not None):
            raise ValueError("a second time constant is a SOPDT's, and a SOPDT has one")
        return self

    def plant(self) -> cl.Plant:
        if self.model == "sopdt":
            return cl.SOPDT(self.gain, self.time_constant, self.second_time_constant, self.dead_time)
        return cl.FOPDT(self.gain, self.time_constant, self.dead_time)


class Gains(BaseModel):
    """A PID in the parallel form, as ``M301``/``M304`` take it: ``ki`` per second, ``kd``
    in seconds, at the sample time ``dt`` with the derivative filter ``filter`` (seconds)
    where they are known."""

    kp: float
    ki: float = 0.0
    kd: float = 0.0
    dt: Optional[float] = Field(None, gt=0)
    filter: Optional[float] = Field(None, ge=0)
    basis: Basis
    source: str
    rule: Optional[str] = None
    parameters: Dict[str, float] = Field(default_factory=dict)

    def pid(self, dt: float = 0.1) -> cl.PID:
        return cl.PID(self.kp, self.ki, self.kd, dt=self.dt or dt, filter=self.filter or 0.0)


class Controller(BaseModel):
    designed: Optional[Gains] = None
    on_machine: Optional[Gains] = None

    @model_validator(mode="after")
    def _bases(self) -> "Controller":
        if self.on_machine is not None and self.on_machine.basis != "measured":
            raise ValueError("the gains on the machine are what the board answered: measured")
        if self.designed is not None and self.designed.basis == "measured":
            raise ValueError("designed gains are computed by a rule or identified by an autotune")
        return self


class FrequencyPoint(BaseModel):
    frequency: float = Field(..., gt=0)  # rad/s
    magnitude: float
    phase_deg: float
    coherence: float = Field(..., ge=0, le=1.000001)
    segments: int = Field(..., ge=1)
    above_noise: Optional[float] = None
    trust: Literal["good", "fair", "poor", "unknown"]
    why: str
    basis: Literal["identified"] = "identified"
    source: str


class LoopDocument(BaseModel):
    """A loop of a machine, ``control/loop/1``."""

    schema_: Literal["control/loop/1"] = Field(SCHEMA, alias="schema")
    generated_at: str
    generator: str = GENERATOR
    machine: Machine
    loop: LoopName
    units: Dict[str, str] = Field(default_factory=dict)
    experiments: List[Experiment] = Field(default_factory=list)
    plant: Optional[PlantModel] = None
    controller: Controller = Field(default_factory=Controller)
    frequency: List[FrequencyPoint] = Field(default_factory=list)
    groups: List[FigureGroup] = Field(default_factory=list)

    model_config = {"populate_by_name": True}

    @model_validator(mode="after")
    def _sources(self) -> "LoopDocument":
        ids = [e.id for e in self.experiments]
        dup = {i for i in ids if ids.count(i) > 1}
        if dup:
            raise ValueError(f"duplicate experiments: {sorted(dup)}")
        gids = [g.id for g in self.groups]
        dup = {g for g in gids if gids.count(g) > 1}
        if dup:
            raise ValueError(f"duplicate groups: {sorted(dup)}")
        have = {
            "plant": self.plant is not None,
            "controller.designed": self.controller.designed is not None,
            "controller.on_machine": self.controller.on_machine is not None,
        }

        def check(what: str, basis: str, source: str) -> None:
            if basis in ("measured", "identified"):
                if source not in ids:
                    raise ValueError(
                        f"{what} is {basis} from {source!r}, which is no experiment of this document"
                    )
                return
            parts = source.split("+")
            for part in parts:
                if part not in PARTS:
                    raise ValueError(f"{what} is computed from {part!r}: not one of {', '.join(PARTS)}")
                if not have[part]:
                    raise ValueError(f"{what} is computed from {part}, which this document lacks")

        if self.plant is not None:
            check("the plant", self.plant.basis, self.plant.source)
        for name in ("designed", "on_machine"):
            gains = getattr(self.controller, name)
            if gains is not None:
                check(f"controller.{name}", gains.basis, gains.source)
        for point in self.frequency:
            check("a frequency point", point.basis, point.source)
        for group in self.groups:
            for f in group.figures:
                check(f"{group.id}.{f.key}", f.basis, f.source)
        return self

    def get(self, path: str) -> Figure:
        gid, _, key = path.partition(".")
        for g in self.groups:
            if g.id == gid:
                for f in g.figures:
                    if f.key == key:
                        return f
        raise KeyError(path)

    def flat(self) -> Dict[str, FigureValue]:
        return {f"{g.id}.{f.key}": f.value for g in self.groups for f in g.figures}


def load_document(path: Union[str, Path]) -> LoopDocument:
    with open(path, encoding="utf-8") as fh:
        return LoopDocument.model_validate(json.load(fh))


# ---- building one -------------------------------------------------------------------------


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _figure(key, label, value, unit, basis, source, note="") -> Figure:
    if isinstance(value, float) and not math.isfinite(value):
        value, note = None, note or "not finite"
    return Figure(key=key, label=label, value=value, unit=unit, basis=basis, source=source, note=note)


def plant_model(found: cl.Identified, source: str, ambient: Optional[float] = None) -> PlantModel:
    p = found.plant
    return PlantModel(
        model=p.model,
        gain=p.gain,
        time_constant=p.time_constant,
        second_time_constant=getattr(p, "second_time_constant", None),
        dead_time=p.dead_time,
        ambient=ambient,
        basis="identified",
        source=source,
        method=found.method,
    )


def gains_of(pid: cl.PID, basis: Basis, source: str, rule: Optional[str] = None, **parameters: float) -> Gains:
    return Gains(
        kp=pid.kp,
        ki=pid.ki,
        kd=pid.kd,
        dt=pid.dt,
        filter=pid.filter,
        basis=basis,
        source=source,
        rule=rule,
        parameters={k: v for k, v in parameters.items() if v is not None},
    )


def figures(doc: LoopDocument, step_of: Optional[str] = None, step_time: Optional[float] = None) -> List[FigureGroup]:
    """The document's figures, computed from what it carries: the plant's parameters, the
    controller's two forms, the loop's margins from the plant with each controller it has,
    and the step response of the experiment ``step_of`` (its setpoint stepped at
    ``step_time`` seconds) beside the model's own step."""
    groups: Dict[str, List[Figure]] = {g: [] for g in GROUP_TITLES}
    pm = doc.plant
    if pm is not None:
        for key, label, value, unit in (
            ("gain", "gain", pm.gain, f"{doc.units.get('temperature', '°C')} per power unit"),
            ("time_constant", "time constant", pm.time_constant, "s"),
            ("second_time_constant", "second time constant", pm.second_time_constant, "s"),
            ("dead_time", "dead time", pm.dead_time, "s"),
            ("ambient", "ambient", pm.ambient, doc.units.get("temperature", "°C")),
        ):
            if value is not None:
                groups["plant"].append(_figure(key, label, value, unit, pm.basis, pm.source, pm.method))
    for name in ("designed", "on_machine"):
        g = getattr(doc.controller, name)
        if g is None:
            continue
        where = "designed" if name == "designed" else "on the machine"
        for key, label, value, unit in (
            ("kp", "Kp", g.kp, "power per °C"),
            ("ki", "Ki", g.ki, "power per °C·s"),
            ("kd", "Kd", g.kd, "power·s per °C"),
        ):
            groups["controller"].append(
                _figure(f"{key}_{name}", f"{label} {where}", value, unit, g.basis, g.source, g.rule or "")
            )
        if g.kp:
            std = g.pid().standard()
            src = f"controller.{name}"
            groups["controller"].append(
                _figure(f"ti_{name}", f"Ti {where}", None if math.isinf(std.ti) else std.ti, "s", "computed", src)
            )
            groups["controller"].append(_figure(f"td_{name}", f"Td {where}", std.td, "s", "computed", src))
        if pm is not None and g.kp:
            src = f"plant+controller.{name}"
            m = cl.loop_margins(cl.Loop(pm.plant(), g.pid(), sampled=g.dt is not None))
            for key, label, value, unit in (
                ("gain_crossover", "gain crossover", m.gain_crossover, "rad/s"),
                ("phase_margin", "phase margin", m.phase_margin, "°"),
                ("phase_crossover", "phase crossover", m.phase_crossover, "rad/s"),
                ("gain_margin", "gain margin", m.gain_margin, "×"),
                ("ms", "peak of the sensitivity", m.ms, ""),
                ("mt", "peak of the complementary sensitivity", m.mt, ""),
            ):
                groups["loop"].append(_figure(f"{key}_{name}", f"{label}, {where}", value, unit, "computed", src))
    exp = next((e for e in doc.experiments if e.id == step_of), None)
    if exp is not None and exp.samples is not None and step_time is not None:
        s = exp.samples
        try:
            m = cl.step_measures(s.t, s.actual, step_time=step_time, setpoint=s.target, band=1.0)
        except ValueError:
            m = None
        if m is not None:
            for key, label, value, unit in (
                ("rise_time", "rise time, 10 to 90 %", m.rise_time, "s"),
                ("overshoot", "overshoot", m.overshoot * 100, "%"),
                ("peak_time", "peak time", m.peak_time, "s"),
                ("settling_time", "settling time into ±1 °C", m.settling_time, "s"),
                ("steady_error", "steady error", m.steady_error, "°C"),
                ("iae", "integrated absolute error", m.iae, "°C·s"),
            ):
                groups["response"].append(_figure(key, label, value, unit, "measured", exp.id))
        groups["experiment"].append(
            _figure("highest", "highest reading", max(s.actual), "°C", "measured", exp.id)
        )
        groups["experiment"].append(
            _figure("sample_period", "sample period", exp.sample_period_s, "s", "measured", exp.id)
        )
    return [FigureGroup(id=gid, figures=figs) for gid, figs in groups.items() if figs]


# ---- a view -------------------------------------------------------------------------------


def format_value(f: Figure) -> str:
    v = f.value
    if v is None:
        return "—"
    if isinstance(v, bool):
        return "yes" if v else "no"
    if isinstance(v, str):
        return v
    if isinstance(v, float):
        a = abs(v)
        if a != 0 and (a < 1e-3 or a >= 1e6):
            s = f"{v:.3e}"
        elif a >= 100:
            s = f"{v:.0f}"
        elif a >= 10:
            s = f"{v:.1f}"
        else:
            s = f"{v:.3f}".rstrip("0").rstrip(".")
    else:
        s = str(v)
    return f"{s} {f.unit}".strip()


def render_markdown(doc: LoopDocument) -> str:
    """The document as tables: the machine and loop, the experiments, one table per group
    with each figure's basis, and the frequency points. A view, not a computation."""
    out = [f"# Control loop: {doc.loop.label}", ""]
    sim = " (simulated)" if doc.machine.simulated else ""
    out.append(
        f"Schema `{doc.schema_}` · generated {doc.generated_at} by `{doc.generator}` · "
        f"{doc.machine.kind} on `{doc.machine.port}`{sim}"
    )
    if doc.machine.firmware:
        out.append(f"Firmware: {doc.machine.firmware}")
    out.append("")
    if doc.experiments:
        out += ["## Experiments", "", "| Id | Kind | Outcome | Sample period | Ceiling | Samples |", "|---|---|---|---|---|---|"]
        for e in doc.experiments:
            n = len(e.samples.t) if e.samples else f"job `{e.job}`"
            ceiling = f"{e.ceiling_c:g} °C" if e.ceiling_c is not None else "—"
            outcome = e.outcome + (f": {e.reason}" if e.reason else "")
            out.append(f"| `{e.id}` | {e.kind} | {outcome} | {e.sample_period_s:g} s | {ceiling} | {n} |")
        out.append("")
    for g in doc.groups:
        out += [f"## {g.title}", "", "| Figure | Value | Basis | From | Note |", "|---|---|---|---|---|"]
        for f in g.figures:
            out.append(f"| {f.label} (`{g.id}.{f.key}`) | {format_value(f)} | {f.basis} | `{f.source}` | {f.note} |")
        out.append("")
    if doc.frequency:
        out += ["## Frequency response", "", "| ω | Magnitude | Phase | Coherence | Trust |", "|---|---|---|---|---|"]
        for p in doc.frequency:
            out.append(
                f"| {p.frequency:.4g} rad/s | {p.magnitude:.4g} | {p.phase_deg:.1f}° | {p.coherence:.2f} | {p.trust}: {p.why} |"
            )
        out.append("")
    return "\n".join(out).rstrip() + "\n"


def samples_from_columns(rows: Sequence[Dict[str, str]]) -> Samples:
    """Samples from rows with the columns ``t``, ``target``, ``actual`` and ``power`` (a CSV
    as ``csv.DictReader`` reads it); an empty power is null."""
    def num(v: Optional[str]) -> Optional[float]:
        return None if v is None or v.strip() == "" else float(v)

    try:
        return Samples(
            t=[float(r["t"]) for r in rows],
            target=[float(r["target"]) for r in rows],
            actual=[float(r["actual"]) for r in rows],
            power=[num(r.get("power")) for r in rows],
        )
    except KeyError as exc:
        raise ValueError(f"a recorded loop has the columns t, target, actual, power: no {exc}") from exc
