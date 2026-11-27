"""A printer's settings tuned from what its prints measure: one document per printer and
material, ``print/tuning/1``, a turn at a time.

A turn is a piece a printer made from a kept slice, read with calipers: each reading of
a feature the piece's plan names (``SliceRecord.plan``; a part with no plan is read by
its box), checked against its nominal, solved by ``apothecary.print_tuning`` into the
printer's errors, and turned into the change of each slicer setting a term moves
(``SETTINGS``). Apply takes the last turn's changes into the printer's next slices; the
next turn, measured from one of those, says whether they took the error out
(``trends``). Undo drops the last turn and what it applied.

**The settings** are OrcaSlicer's, as the pinned release's own option list names them
and its bundled profiles write them (docs/print-tuning.md says where each was read).
Each is moved by a named relation with its sign, damped, bounded per turn and held
inside its limits. ``z_offset`` is said and not applied: printer_1's profile holds it
at 0 because the board applies the probe's offset at G28, and the first-layer offset its
slices take is the one kept in its Print window from one-layer squares (the start piece
``first-layer-offset``, ``first_layer_offset.py``). A wall's thickness is kept
and said and moves nothing: the slice does not record the width the wall was printed
at, and the flow follows from that width only through the slicer's model of a line.

**The document** carries the printer (its site and node, its part), what it applies to
(the slicer, the filament profile and the process profile: a correction learnt with
one material or process is not another's), every turn -- the slice it measured and the
values that slice used, the instrument, every reading with its nominal and its
uncertainty, what was assumed, the terms solved with their errors and whether each
could be separated, the change proposed for each setting and the change applied --
and the settings the next slice takes. Every figure says its basis (``measured``,
``solved``, ``assumed``, ``computed``) and the turn it rests on, and the validator
refuses a figure resting on a turn the document lacks, and a held setting no applied
change of its turn sets. Python computes every figure; a page or a Markdown table
renders the document.

**Where it is kept**: the state folder's ``corrections/<site>/<printer>/`` (where the
printer's correction was kept), a file per filament and process, written whole under
a lock. A correction kept in the older shape -- ``corrections/<site>/<printer>.json``,
``xy_contour_compensation`` and its measurements -- is read once into its printer's
document for the printer's one filament and process, each measurement a turn whose
readings are its X, Y and Z, with the scales and the foot assumed none as its rule
took them, its change the one it applied; the older file is then removed, and nothing
reads that shape again.
"""

from __future__ import annotations

import json
import math
import re
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Literal, Mapping, Optional, Sequence, Tuple

from pydantic import BaseModel, Field, model_validator

from .. import print_faults as pf
from .. import print_tuning as pt
from ..models.measures import MeasuredFeature, MeasurePlan, box_plan
from ..state_folder import state_dir, write_whole
from .models import SliceRecord
from .profiles import PrinterProfile

SCHEMA = "print/tuning/1"
GENERATOR = "apothecary.print_tuning"
MODULE = "orcaslicer"
NAME = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.\-]{0,199}$")
TURN_ID = r"^turn-[1-9][0-9]{0,5}$"
LOOK_ID = r"^look-[1-9][0-9]{0,5}$"
# A reading further than this share of its nominal, or NEAR mm, whichever is more, is
# not of this piece's feature: measured across something else, or another piece.
WITHIN = 0.05
NEAR = 1.0
# A caliper's resolution taken for a turn that states none: a digital caliper's step.
RESOLUTION = 0.01
# The most a look says of where a fault shows, in characters.
WHERE_MOST = 200
# The older shape's rule assumed these none: what its turns are solved with.
EARLIER_ASSUMED = {"scale_x": 0.0, "scale_y": 0.0, "foot": 0.0}

Basis = Literal["measured", "solved", "assumed", "computed", "seen"]
Kind = Literal["process", "filament", "machine"]


class Refused(ValueError):
    """A reading, a turn or a change that is not kept, and why."""


# ---- the settings a term moves ---------------------------------------------------------------


class Tuned(BaseModel):
    """One OrcaSlicer setting a term moves: its key, which of its profiles holds it,
    its unit, the relation, its limits, and whether apothecary applies it."""

    term: str  # a print_tuning term, or "scale_xy": scale_x and scale_y as one
    key: str
    kind: Kind
    unit: Literal["mm", "%"]
    relation: str
    least: float
    most: float
    most_step: float
    applied: bool
    says: str  # OrcaSlicer's own words for it, from its option list
    why_not: str = ""

    @property
    def limits(self) -> pt.Limits:
        return pt.Limits(self.least, self.most, self.most_step)


# The limits are apothecary's, the owner's to set (docs/print-tuning.md): an offset
# within the 0.5 mm the earlier correction refused past (``MOST``), a scale within the
# 5 % a reading is refused past (``WITHIN``), the first layer's spread never grown (no
# bundled profile of the pinned release sets it below 0); a fifth of the farthest
# limit's reach from neutral a turn at most.
SETTINGS: Tuple[Tuned, ...] = (
    Tuned(
        term="contour",
        key="xy_contour_compensation",
        kind="process",
        unit="mm",
        relation="take_out",
        least=-0.5,
        most=0.5,
        most_step=0.1,
        applied=True,
        says="Contours of objects will expand or contract in the XY plane by the configured "
        "value. Positive values make contours bigger, negative values make contours smaller.",
    ),
    Tuned(
        term="hole",
        key="xy_hole_compensation",
        kind="process",
        unit="mm",
        relation="put_back",
        least=-0.5,
        most=0.5,
        most_step=0.1,
        applied=True,
        says="Holes in objects will expand or contract in the XY plane by the configured "
        "value. Positive values make holes bigger, negative values make holes smaller.",
    ),
    Tuned(
        term="foot",
        key="elefant_foot_compensation",
        kind="process",
        unit="mm",
        relation="put_back",
        least=0.0,
        most=0.5,
        most_step=0.1,
        applied=True,
        says="Shrinks the first layer on build plate to compensate for elephant foot effect.",
    ),
    Tuned(
        term="scale_xy",
        key="filament_shrink",
        kind="filament",
        unit="%",
        relation="percent",
        least=95.0,
        most=105.0,
        most_step=1.0,
        applied=True,
        says="Enter the shrinkage percentage that the filament will get after cooling (94% if "
        "you measure 94mm instead of 100mm). The part will be scaled in XY to compensate.",
    ),
    Tuned(
        term="scale_z",
        key="filament_shrinkage_compensation_z",
        kind="filament",
        unit="%",
        relation="percent",
        least=95.0,
        most=105.0,
        most_step=1.0,
        applied=True,
        says="Enter the shrinkage percentage that the filament will get after cooling (94% if "
        "you measure 94mm instead of 100mm). The part will be scaled in Z to compensate.",
    ),
    Tuned(
        term="first",
        key="z_offset",
        kind="machine",
        unit="mm",
        relation="take_out",
        least=-0.5,
        most=0.5,
        most_step=0.1,
        applied=False,
        says="This value will be added (or subtracted) from all the Z coordinates in the "
        "output G-code.",
        why_not="said, not applied: the printer's profile holds z_offset at 0 because the "
        "board applies the probe's offset when G28 homes Z, and the first-layer offset its "
        "slices take is the one kept in its Print window from one-layer squares (the start "
        "piece first-layer-offset)",
    ),
)
TUNED = {s.key: s for s in SETTINGS}
# The settings a turn records as its slice used them: each tuned one, and the layers.
LAYERS = ("layer_height", "initial_layer_print_height")


def tuned(key: str) -> Tuned:
    try:
        return TUNED[key]
    except KeyError:
        raise Refused(f"no tuned setting {key!r}") from None


# ---- the document ---------------------------------------------------------------------------


class Printer(BaseModel):
    site: str
    node: str  # the printer's node in the site
    part: str  # its part, which keeps its slicer profile


class AppliesTo(BaseModel):
    slicer: str = MODULE
    filament: str  # the filament profile the slices used
    process: str  # the process profile


class Instrument(BaseModel):
    resolution: float = Field(RESOLUTION, gt=0, le=1)  # mm, the caliper's step
    repeatability: Optional[float] = Field(None, ge=0, le=1)  # mm, a person's, as stated


class SliceRef(BaseModel):
    """The slice a turn's piece was printed from, and the values it used."""

    file_id: str
    part: str
    variant: Optional[str] = None
    params: Dict[str, object] = Field(default_factory=dict)
    used: Dict[str, Optional[float]] = Field(default_factory=dict)  # tuned keys and layers
    basis: Literal["measured"] = "measured"  # as the slice recorded them
    source: str


class ReadingDoc(BaseModel):
    feature: str
    kind: str
    axis: str
    level: str
    nominal: float
    values: List[float]
    mean: float
    error: float  # mean less nominal, mm
    uncertainty: float  # the mean's standard uncertainty, mm
    notes: List[str] = Field(default_factory=list)
    basis: Literal["measured"] = "measured"
    source: str


class TermDoc(BaseModel):
    term: str
    unit: str
    value: Optional[float]
    error: Optional[float]
    determined: bool
    resolved: bool
    with_terms: List[str] = Field(default_factory=list)  # what it cannot be told from
    note: str = ""
    basis: Literal["solved", "assumed"]
    source: str


class Fit(BaseModel):
    """The solve's own figures, for ``--explain``: the design matrix, rank and residuals."""

    columns: List[str]
    rows: List[str]
    matrix: List[List[float]]
    rank: int
    readings: int
    dof: int
    chi2: Optional[float] = None
    residuals: Dict[str, float] = Field(default_factory=dict)
    said: List[str] = Field(default_factory=list)
    basis: Literal["solved"] = "solved"
    source: str


class Proposal(BaseModel):
    setting: str
    kind: Kind
    unit: str
    term: str
    relation: str
    used: Optional[float]  # what the measured slice used
    whole: Optional[float]  # the value that would leave none of the term
    new: Optional[float]  # what the turn proposes; None: nothing
    expected: Optional[float]  # the term left at ``new``
    damping: float
    applies: bool  # whether apothecary applies this setting at all
    why: str
    basis: Literal["computed"] = "computed"
    source: str


class Change(BaseModel):
    setting: str
    kind: Kind
    unit: str
    before: Optional[float]  # what the next slices took before it
    after: float
    at: datetime
    basis: Literal["computed"] = "computed"
    source: str


class WallDoc(BaseModel):
    feature: str
    error: float
    uncertainty: float
    said: str
    basis: Literal["measured"] = "measured"
    source: str


class Turn(BaseModel):
    id: str = Field(..., pattern=TURN_ID)
    at: datetime
    slice: SliceRef
    instrument: Instrument = Field(default_factory=Instrument)
    readings: List[ReadingDoc]
    assumed: Dict[str, float] = Field(default_factory=dict)
    terms: List[TermDoc] = Field(default_factory=list)
    fit: Fit
    walls: List[WallDoc] = Field(default_factory=list)
    proposed: List[Proposal] = Field(default_factory=list)
    applied: List[Change] = Field(default_factory=list)
    converted: Optional[str] = None  # how a turn of the older shape was read

    def term(self, name: str) -> Optional[TermDoc]:
        return next((t for t in self.terms if t.term == name), None)

    def proposal(self, key: str) -> Optional[Proposal]:
        return next((p for p in self.proposed if p.setting == key), None)


class Seen(BaseModel):
    """One fault as a person read it on a piece (apothecary/print_faults.py)."""

    fault: str
    severity: int = Field(..., ge=0, le=3)
    where: str = Field("", max_length=WHERE_MOST)  # a height, a feature: where it shows
    basis: Literal["seen"] = "seen"
    source: str


class LookStep(BaseModel):
    """A setting a look changes for a fault: a step, or a lever put back."""

    setting: str
    kind: Kind
    unit: str
    fault: str
    used: Optional[float]  # what the looked-at slice used
    new: float
    back: bool  # put back where it was: the lever did not govern the fault here
    why: str
    applies: bool = True
    basis: Literal["computed"] = "computed"
    source: str


class Look(BaseModel):
    """A piece a printer made, read by eye: each fault's severity, and the one
    setting's change it proposes (print_faults.next_step)."""

    id: str = Field(..., pattern=LOOK_ID)
    at: datetime
    slice: SliceRef
    seen: List[Seen]
    note: str = Field("", max_length=2000)
    proposed: List[LookStep] = Field(default_factory=list)
    said: List[str] = Field(default_factory=list)
    applied: List[Change] = Field(default_factory=list)

    def proposal(self, key: str) -> Optional[LookStep]:
        return next((p for p in self.proposed if p.setting == key), None)

    def severity(self, fault_id: str) -> Optional[int]:
        return next((x.severity for x in self.seen if x.fault == fault_id), None)


class Held(BaseModel):
    """A setting the printer's next slices take, and the turn or look whose change set it."""

    kind: Kind
    unit: str
    value: float
    basis: Literal["computed"] = "computed"
    source: str


class TuningDocument(BaseModel):
    """A printer's settings tuned for one material and process, ``print/tuning/1``."""

    schema_: Literal["print/tuning/1"] = Field(SCHEMA, alias="schema")
    generated_at: str
    generator: str = GENERATOR
    printer: Printer
    applies_to: AppliesTo
    turns: List[Turn] = Field(default_factory=list)
    looks: List[Look] = Field(default_factory=list)
    settings: Dict[str, Held] = Field(default_factory=dict)

    model_config = {"populate_by_name": True}

    @model_validator(mode="after")
    def _rests_on_its_turns(self) -> "TuningDocument":
        ids = [t.id for t in self.turns] + [lk.id for lk in self.looks]
        dup = {i for i in ids if ids.count(i) > 1}
        if dup:
            raise ValueError(f"duplicate turns: {sorted(dup)}")

        def own(turn: Turn, what: str, source: str) -> None:
            if source != turn.id:
                raise ValueError(
                    f"{what} of {turn.id} rests on {source!r}: a turn's figures rest on it"
                )

        for turn in self.turns:
            own(turn, "its slice", turn.slice.source)
            own(turn, "its fit", turn.fit.source)
            touched = set()
            for r in turn.readings:
                own(turn, f"the reading {r.feature}", r.source)
                touched |= set(
                    pt.row(pt.Feature(r.feature, r.kind, r.axis, r.nominal, r.level))  # type: ignore[arg-type]
                )
            for w in turn.walls:
                own(turn, f"the wall {w.feature}", w.source)
            for t in turn.terms:
                own(turn, f"the term {t.term}", t.source)
                if t.basis == "solved" and t.determined and t.term != "scale_xy":
                    if t.term not in touched:
                        raise ValueError(
                            f"{turn.id} solves {t.term} from no reading of its own that it moves"
                        )
            for p in turn.proposed:
                own(turn, f"the proposal for {p.setting}", p.source)
                if p.new is not None:
                    found = turn.term(p.term)
                    if found is None or not found.determined:
                        raise ValueError(
                            f"{turn.id} proposes {p.setting} from {p.term}, which it does not determine"
                        )
            for c in turn.applied:
                own(turn, f"the change of {c.setting}", c.source)
                p = turn.proposal(c.setting)
                if p is None or p.new is None or abs(p.new - c.after) > 1e-9:
                    raise ValueError(
                        f"{turn.id} applies {c.setting} {c.after:g}, which it did not propose"
                    )
        for look in self.looks:
            own(look, "its slice", look.slice.source)
            for x in look.seen:
                own(look, f"what it saw of {x.fault}", x.source)
                if x.fault not in pf.BY_ID:
                    raise ValueError(f"{look.id} saw {x.fault!r}, which is no fault")
            for st in look.proposed:
                own(look, f"the step of {st.setting}", st.source)
                seen = look.severity(st.fault)
                if not st.back and not seen:
                    raise ValueError(
                        f"{look.id} steps {st.setting} for {st.fault}, which it did not see"
                    )
            for c in look.applied:
                own(look, f"the change of {c.setting}", c.source)
                st = look.proposal(c.setting)
                if st is None or abs(st.new - c.after) > 1e-9:
                    raise ValueError(
                        f"{look.id} applies {c.setting} {c.after:g}, which it did not propose"
                    )
        last: Dict[str, Tuple[str, float]] = {}
        for entry in entries(self.turns, self.looks):
            for c in entry.applied:
                last[c.setting] = (entry.id, c.after)
        for key, held in self.settings.items():
            if held.source not in ids:
                raise ValueError(
                    f"the held {key} rests on {held.source!r}, which is no turn of this document"
                )
            if (
                key not in last
                or last[key][0] != held.source
                or abs(last[key][1] - held.value) > 1e-9
            ):
                raise ValueError(
                    f"the held {key} {held.value:g} is not the last change {held.source} applied"
                )
        missing = set(last) - set(self.settings)
        if missing:
            raise ValueError(f"changes applied and not held: {sorted(missing)}")
        return self

    def turn(self, turn_id: str) -> Turn:
        for t in self.turns:
            if t.id == turn_id:
                return t
        raise KeyError(turn_id)

    def entry(self, entry_id: str) -> "Turn | Look":
        for e in entries(self.turns, self.looks):
            if e.id == entry_id:
                return e
        raise KeyError(entry_id)


def entries(turns: Sequence[Turn], looks: Sequence[Look] = ()) -> List["Turn | Look"]:
    """Turns and looks in the order they were kept: a document's history."""
    return sorted([*turns, *looks], key=lambda e: e.at)


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def held_of(turns: Sequence[Turn], looks: Sequence[Look] = ()) -> Dict[str, Held]:
    """The settings the next slices take: each the last change a turn or look applied."""
    out: Dict[str, Held] = {}
    for entry in entries(turns, looks):
        for c in entry.applied:
            out[c.setting] = Held(kind=c.kind, unit=c.unit, value=c.after, source=entry.id)
    return out


# ---- where it is kept ----------------------------------------------------------------------

_LOCK = threading.RLock()


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "unnamed"


def _folder(site: str, printer: str) -> Path:
    if not NAME.match(site or "") or not NAME.match(printer or ""):
        raise Refused(f"no tuning can be kept for {site!r}, {printer!r}")
    return state_dir() / "corrections" / site / printer


def kept_at(site: str, printer: str, applies: AppliesTo) -> Path:
    return _folder(site, printer) / f"{slug(applies.filament)}--{slug(applies.process)}.json"


def _read(path: Path) -> Optional[TuningDocument]:
    if not path.is_file():
        return None
    return TuningDocument.model_validate_json(path.read_text(encoding="utf-8"))


def _write(doc: TuningDocument) -> TuningDocument:
    doc.generated_at = now()
    doc.settings = held_of(doc.turns, doc.looks)
    checked = TuningDocument.model_validate(doc.model_dump(by_alias=True))
    write_whole(
        kept_at(doc.printer.site, doc.printer.node, doc.applies_to),
        checked.model_dump_json(by_alias=True, indent=2),
    )
    return checked


def load(
    site: Optional[str], printer: Optional[str], applies: AppliesTo, part: str = ""
) -> Optional[TuningDocument]:
    """The document kept for ``printer`` of ``site`` and what it applies to, or None; a
    correction of the older shape kept for that printer is read into it first."""
    if not site or not printer:
        return None
    try:
        path = kept_at(site, printer, applies)
    except Refused:
        return None
    with _LOCK:
        _carry_over(site, printer, applies, part)
        return _read(path)


def documents(site: str, printer: str) -> List[TuningDocument]:
    """Every document kept for ``printer`` of ``site``, one per material and process."""
    folder = _folder(site, printer)
    with _LOCK:
        if not folder.is_dir():
            return []
        return [d for d in (_read(p) for p in sorted(folder.glob("*.json"))) if d is not None]


def start(site: str, printer: str, part: str, applies: AppliesTo) -> TuningDocument:
    """The document for ``printer`` and what it applies to: the one kept, else a new one."""
    with _LOCK:
        found = load(site, printer, applies, part)
        if found is not None:
            return found
        doc = TuningDocument(
            generated_at=now(),
            printer=Printer(site=site, node=printer, part=part),
            applies_to=applies,
        )
        return _write(doc)


# ---- what a slice used ---------------------------------------------------------------------


def _number(value) -> Optional[float]:
    if isinstance(value, list):
        value = value[0] if value else None
    if value is None or isinstance(value, bool):
        return None
    text = str(value).split(",")[0].strip().rstrip("%")
    try:
        found = float(text)
    except ValueError:
        return None
    return found if math.isfinite(found) else None


def applies_of(record: SliceRecord) -> AppliesTo:
    """The filament and process profiles a slice was made with, as its record names them."""
    named = {s.name: s.value for s in record.settings}
    filament, process = named.get("filament profile"), named.get("process profile")
    if record.slicer != MODULE or not filament or not process:
        raise Refused(
            f"{record.name} was not sliced by OrcaSlicer with a filament and a process "
            "profile its record names: its settings cannot be tuned from it"
        )
    return AppliesTo(slicer=record.slicer, filament=str(filament), process=str(process))


def used_by(record: SliceRecord) -> Dict[str, Optional[float]]:
    """Each tuned setting, layer height and setting a fault's lever reads, as the slice
    recorded it; None where it did not."""
    named = {s.name: s.value for s in record.settings}
    return {key: _number(named.get(key)) for key in dict.fromkeys((*TUNED, *LAYERS, *pf.READ_KEYS))}


def plan_of(record: SliceRecord) -> MeasurePlan:
    if record.plan is not None:
        return record.plan
    if record.size is None:
        raise Refused(
            f"{record.name}'s slice does not say the size of what it sliced, and the part "
            f"names no plan: slice {record.made.name} again, print it, and measure that"
        )
    return box_plan(tuple(record.size))  # type: ignore[arg-type]


# ---- a turn ---------------------------------------------------------------------------------


def feature_read(plan: MeasurePlan, name: str, read: Sequence[float], part: str) -> MeasuredFeature:
    """The feature ``name`` of ``plan``, ``read`` as these sizes: refused where the plan
    names no such feature, a reading is no size, or one is further from its nominal
    than ``WITHIN`` of it or ``NEAR`` mm, whichever is more."""
    try:
        feature = plan.feature(name)
    except KeyError:
        raise Refused(
            f"{part} has no {name!r} to measure: it names {', '.join(plan.names)}"
        ) from None
    for v in read:
        if not (math.isfinite(v) and v > 0):
            raise Refused(f"{name} {v} mm is no size")
        bound = max(WITHIN * feature.nominal, NEAR)
        if abs(v - feature.nominal) > bound:
            raise Refused(
                f"{name} {v:g} mm against {feature.nominal:g} mm drawn is further off than "
                f"{bound:g} mm: not this piece's {name}, or measured across something "
                "else -- read it again, or choose the file it was printed from"
            )
    return feature


def _readings(
    plan: MeasurePlan,
    values: Mapping[str, Sequence[float]],
    instrument: Instrument,
    used: Mapping[str, Optional[float]],
    part: str,
) -> Tuple[List[pt.Reading], Dict[str, List[str]]]:
    if not values:
        raise Refused(f"read one of {', '.join(plan.names)}: what {part} names to measure")
    notes: Dict[str, List[str]] = {}
    out = []
    for name, read in values.items():
        read = [float(v) for v in read]
        feature = feature_read(plan, name, read, part)
        if not read:
            continue
        extra = 0.0
        notes[name] = []
        if feature.kind == "height":
            layer, first = used.get("layer_height"), used.get("initial_layer_print_height")
            shrink = used.get("filament_shrinkage_compensation_z") or 100.0
            if layer and first:
                extra = pt.layer_quantum(feature.nominal * 100.0 / shrink, first, layer)
                if extra:
                    notes[name].append(
                        f"its top falls between two of the slice's layers ({first:g} then "
                        f"{layer:g} mm): a layer's quantization is in its uncertainty"
                    )
            else:
                extra = 0.2 / math.sqrt(12)
                notes[name].append(
                    "the slice does not say its layer heights: 0.2 mm layers' quantization "
                    "is taken into its uncertainty"
                )
        reading = pt.Reading(
            feature.feature(),
            tuple(read),
            resolution=instrument.resolution,
            repeatability=instrument.repeatability,
            extra=extra,
        )
        if reading.understated:
            notes[name].append(
                "read once, with no repeatability stated: its uncertainty is the resolution's alone"
            )
        out.append(reading)
    return out, notes


def _scale_xy(found: pt.Solution) -> Tuple[pt.Solved, str]:
    """scale_x and scale_y as the one XY scale filament_shrink moves: their weighted mean
    where both are determined and agree within what they resolve."""
    sx, sy = found.terms.get("scale_x"), found.terms.get("scale_y")
    if sx is None or sy is None or not (sx.determined and sy.determined):
        missing = [
            n for n, s in (("scale_x", sx), ("scale_y", sy)) if s is None or not s.determined
        ]
        return (
            pt.Solved("scale_xy", None, None, False, with_=tuple(missing)),
            "the XY shrinkage moves X and Y alike, and "
            + " and ".join(missing)
            + " is not determined",
        )
    if sx.assumed or sy.assumed:
        return pt.Solved("scale_xy", None, None, True, assumed=True), "assumed, not measured"
    gap = abs(sx.value - sy.value)
    noise = pt.RESOLVE * math.hypot(sx.error, sy.error)
    if gap > noise:
        return (
            pt.Solved("scale_xy", None, None, False, with_=("scale_x", "scale_y")),
            f"X {sx.value:+.3%} and Y {sy.value:+.3%} differ by more than they resolve: the "
            "XY shrinkage is one value for both, and their difference is an axis's steps "
            "per millimetre (M92), which nothing here changes",
        )
    wx, wy = 1 / max(sx.error, 1e-12) ** 2, 1 / max(sy.error, 1e-12) ** 2
    value = (wx * sx.value + wy * sy.value) / (wx + wy)
    error = 1 / math.sqrt(wx + wy)
    return (
        pt.Solved("scale_xy", value, error, True, resolved=abs(value) > pt.RESOLVE * error),
        "the weighted mean of scale_x and scale_y, which agree",
    )


def _term_doc(s: pt.Solved, turn_id: str, note: str = "") -> TermDoc:
    unit = pt.term(s.name).unit if s.name in pt.TERM_NAMES else ""
    return TermDoc(
        term=s.name,
        unit=unit,
        value=s.value,
        error=s.error,
        determined=s.determined,
        resolved=s.resolved,
        with_terms=list(s.with_),
        note=note,
        basis="assumed" if s.assumed else "solved",
        source=turn_id,
    )


def _solve_turn(
    turn_id: str,
    at: datetime,
    ref: SliceRef,
    plan: MeasurePlan,
    values: Mapping[str, Sequence[float]],
    instrument: Instrument,
    assumed: Mapping[str, float],
    earlier: Sequence[Turn],
    whole_from: Optional[Dict[str, float]] = None,
) -> Turn:
    readings, notes = _readings(plan, values, instrument, ref.used, ref.part)
    for name in assumed:
        pt.term(name)
    found = pt.solve(readings, assumed)
    terms = [_term_doc(s, turn_id) for s in found.terms.values()]
    xy, xy_note = _scale_xy(found)
    if "scale_x" in found.terms or "scale_y" in found.terms:
        terms.append(_term_doc(xy, turn_id, xy_note))
    walls = [
        WallDoc(
            feature=name,
            error=err,
            uncertainty=u,
            said=f"{name} {err:+.3f} mm against its {plan.feature(name).nominal:g} mm: kept and "
            "said; the slice does not record the width this wall was printed at, so no "
            "flow follows from it",
            source=turn_id,
        )
        for name, (err, u) in pt.wall_errors(readings).items()
    ]
    turn = Turn(
        id=turn_id,
        at=at,
        slice=ref,
        instrument=instrument,
        readings=[
            ReadingDoc(
                feature=r.feature.name,
                kind=r.feature.kind,
                axis=r.feature.axis,
                level=r.feature.level,
                nominal=r.feature.nominal,
                values=list(r.values),
                mean=r.mean,
                error=r.error,
                uncertainty=r.uncertainty,
                notes=notes.get(r.feature.name, []),
                source=turn_id,
            )
            for r in readings
        ],
        assumed=dict(assumed),
        terms=terms,
        fit=Fit(
            columns=found.columns,
            rows=found.rows,
            matrix=found.matrix,
            rank=found.rank,
            readings=found.readings,
            dof=found.dof,
            chi2=found.chi2,
            residuals=found.residuals,
            said=found.said,
            source=turn_id,
        ),
        walls=walls,
    )
    solved = {t.term: t for t in terms}
    tallest = max((r.nominal for r in turn.readings if r.kind == "height"), default=None)
    for setting in SETTINGS:
        doc = solved.get(setting.term)
        if doc is None:
            continue
        s = pt.Solved(
            doc.term,
            doc.value,
            doc.error,
            doc.determined,
            with_=tuple(doc.with_terms),
            resolved=doc.resolved,
            assumed=doc.basis == "assumed",
        )
        used = ref.used.get(setting.key)
        trend = pt.trend(setting.term, points(earlier, setting) + [_point(turn_id, doc, None)])
        damping = trend.damping
        if whole_from is not None and setting.key in whole_from:
            # The older shape's rule: the whole of it, at once.
            proposal = Proposal(
                setting=setting.key,
                kind=setting.kind,
                unit=setting.unit,
                term=setting.term,
                relation=setting.relation,
                used=used,
                whole=whole_from[setting.key],
                new=whole_from[setting.key],
                expected=0.0,
                damping=1.0,
                applies=setting.applied,
                why="the earlier correction's rule: the whole of half the mean of X's and Y's "
                "errors, the scales and the foot taken as none",
                source=turn_id,
            )
            turn.proposed.append(proposal)
            continue
        if whole_from is not None:
            continue
        if used is None:
            step = pt.Step(setting.term, 0.0, None, None, damping, None, "")
            why = f"the slice does not say the {setting.key} it used: nothing to step from"
        elif trend.stop:
            step = pt.Step(setting.term, used, None, None, damping, None, "")
            why = trend.said
        else:
            step = pt.step(s, pt.RELATIONS[setting.relation], used, setting.limits, damping)
            why = step.why if setting.applied else setting.why_not
            if setting.term == "scale_z" and step.new is not None and tallest:
                moved = abs(step.new - used) / used * tallest
                layer = ref.used.get("layer_height") or 0.2
                if moved < layer / 2:
                    why = (
                        f"it moves the tallest top {moved:.3f} mm, under half a "
                        f"{layer:g} mm layer: the slice would put every top where it was"
                    )
                    step = pt.Step(setting.term, used, step.whole, None, damping, None, why)
        if xy_note and setting.term == "scale_xy" and not s.determined:
            why = xy_note
        turn.proposed.append(
            Proposal(
                setting=setting.key,
                kind=setting.kind,
                unit=setting.unit,
                term=setting.term,
                relation=setting.relation,
                used=used,
                whole=step.whole,
                new=step.new if setting.applied else None,
                expected=step.expected if setting.applied else None,
                damping=damping,
                applies=setting.applied,
                why=why,
                source=turn_id,
            )
        )
    return turn


def _point(turn_id: str, doc: TermDoc, change: Optional[Proposal]) -> pt.Point:
    return pt.Point(
        turn_id,
        doc.value if doc.determined and doc.basis == "solved" else None,
        doc.error,
        stepped=change is not None,
        expected=change.expected if change is not None else None,
        damping=change.damping if change is not None and change.damping < 1 else pt.DAMPING,
    )


def points(turns: Sequence[Turn], setting: Tuned) -> List[pt.Point]:
    """A term over the turns kept: its value at each, and whether its setting's change
    was applied after it."""
    out = []
    for turn in turns:
        doc = turn.term(setting.term)
        if doc is None:
            continue
        applied = any(c.setting == setting.key for c in turn.applied)
        out.append(_point(turn.id, doc, turn.proposal(setting.key) if applied else None))
    return out


def trends(doc: TuningDocument) -> Dict[str, pt.Trend]:
    """Each tuned setting's term over the document's turns."""
    return {s.key: pt.trend(s.term, points(doc.turns, s)) for s in SETTINGS}


def next_id(doc: TuningDocument, prefix: str = "turn") -> str:
    kept = doc.turns if prefix == "turn" else doc.looks
    n = max((int(t.id.split("-")[1]) for t in kept), default=0)
    return f"{prefix}-{n + 1}"


def reads_last(record: SliceRecord) -> Optional[str]:
    """The turn of its printer's tuning that already reads the piece ``record``'s slice
    made, when that is the last: a second reading of it is no new turn. None where the
    last turn is another piece's, or the printer keeps no tuning for it."""
    at = record.printer
    try:
        doc = load(at.site, at.path, applies_of(record), at.part)
    except Refused:
        return None
    if doc is None or not doc.turns or doc.turns[-1].slice.file_id != record.file_id:
        return None
    return doc.turns[-1].id


def add_turn(
    record: SliceRecord,
    values: Mapping[str, Sequence[float]],
    instrument: Optional[Instrument] = None,
    assumed: Optional[Mapping[str, float]] = None,
) -> Tuple[TuningDocument, Turn]:
    """A piece printed from ``record``'s slice, read: checked against the piece's plan,
    solved, its changes proposed, and kept as the next turn of its printer's document.
    ``Refused`` says why, and nothing is kept."""
    at = record.printer
    if not at.site or not at.path:
        raise Refused(
            f"{record.name} was sliced for {at.name}, a printer of no site: a printer's "
            "tuning is kept for a printer standing in one"
        )
    applies = applies_of(record)
    plan = plan_of(record)
    used = used_by(record)
    with _LOCK:
        # Written only with its turn: a refused reading keeps nothing, an empty document too.
        doc = load(at.site, at.path, applies, at.part) or TuningDocument(
            generated_at=now(),
            printer=Printer(site=at.site, node=at.path, part=at.part),
            applies_to=applies,
        )
        if any(t.slice.file_id == record.file_id for t in doc.turns[-1:]):
            raise Refused(
                f"the last turn already reads the piece {record.file_id} made: undo it to read it again"
            )
        turn_id = next_id(doc)
        ref = SliceRef(
            file_id=record.file_id,
            part=record.made.name,
            variant=record.made.variant,
            params=dict(record.made.params),
            used=used,
            source=turn_id,
        )
        turn = _solve_turn(
            turn_id,
            datetime.now(timezone.utc),
            ref,
            plan,
            values,
            instrument or Instrument(),
            dict(assumed or {}),
            doc.turns,
        )
        doc.turns.append(turn)
        doc = _write(doc)
        return doc, doc.turns[-1]


def apply(site: str, printer: str, applies: AppliesTo) -> Tuple[TuningDocument, List[Change]]:
    """The last turn's or look's proposed changes taken into the printer's next slices."""
    with _LOCK:
        doc = load(site, printer, applies)
        if doc is None or not (doc.turns or doc.looks):
            raise Refused(f"{printer} has no turn or look to apply for {applies.filament}")
        last = entries(doc.turns, doc.looks)[-1]
        if last.applied:
            raise Refused(f"{last.id} is applied already")
        held = held_of(doc.turns, doc.looks)
        if isinstance(last, Look):
            looked = [
                Change(
                    setting=st.setting,
                    kind=st.kind,
                    unit=st.unit,
                    before=held[st.setting].value if st.setting in held else st.used,
                    after=st.new,
                    at=datetime.now(timezone.utc),
                    source=last.id,
                )
                for st in last.proposed
                if st.applies
            ]
            if not looked:
                raise Refused(
                    f"{last.id} proposes no change: " + "; ".join(last.said or ["nothing seen"])
                )
            last.applied = looked
            doc = _write(doc)
            return doc, looked
        changes = [
            Change(
                setting=p.setting,
                kind=p.kind,
                unit=p.unit,
                before=held[p.setting].value if p.setting in held else p.used,
                after=p.new,
                at=datetime.now(timezone.utc),
                source=last.id,
            )
            for p in last.proposed
            if p.applies and p.new is not None
        ]
        if not changes:
            raise Refused(f"{last.id} proposes no change: " + "; ".join(_why_none(last)))
        last.applied = changes
        doc = _write(doc)
        return doc, changes


def _why_none(turn: Turn) -> List[str]:
    return [f"{p.setting}: {p.why}" for p in turn.proposed]


def undo(site: str, printer: str, applies: AppliesTo) -> Tuple[TuningDocument, "Turn | Look"]:
    """The last turn or look dropped, and what it applied with it: the next slices take
    what the ones before it applied."""
    with _LOCK:
        doc = load(site, printer, applies)
        if doc is None or not (doc.turns or doc.looks):
            raise Refused(f"{printer} has no turn or look to undo for {applies.filament}")
        gone = entries(doc.turns, doc.looks)[-1]
        if isinstance(gone, Look):
            doc.looks.remove(gone)
        else:
            doc.turns.remove(gone)
        return _write(doc), gone


def add_look(
    record: SliceRecord,
    seen: Mapping[str, int],
    where: Optional[Mapping[str, str]] = None,
    note: str = "",
) -> Tuple[TuningDocument, Look]:
    """A piece printed from ``record``'s slice, read by eye: each fault's severity
    checked, the one setting's change it implies decided (print_faults.next_step), and
    kept as the next look of its printer's document. ``Refused`` says why, and nothing
    is kept."""
    at = record.printer
    if not at.site or not at.path:
        raise Refused(
            f"{record.name} was sliced for {at.name}, a printer of no site: a printer's "
            "tuning is kept for a printer standing in one"
        )
    if not seen:
        raise Refused(
            "say what the piece shows: each fault seen, none to bad ("
            + ", ".join(f.id for f in pf.FAULTS)
            + ")"
        )
    for fault_id, severity in seen.items():
        if fault_id not in pf.BY_ID:
            raise Refused(f"no fault {fault_id!r}: there are {', '.join(f.id for f in pf.FAULTS)}")
        if not isinstance(severity, int) or isinstance(severity, bool) or not 0 <= severity <= 3:
            raise Refused(f"{fault_id}: a severity is 0 (none) to 3 (bad), not {severity!r}")
    where = dict(where or {})
    for fault_id, text in where.items():
        if fault_id not in seen:
            raise Refused(f"{fault_id}: where it shows is said for a fault seen")
        if len(str(text)) > WHERE_MOST:
            raise Refused(
                f"{fault_id}: where it shows is at most {WHERE_MOST} characters, "
                f"not {len(str(text))}"
            )
    applies = applies_of(record)
    used = used_by(record)
    with _LOCK:
        doc = load(at.site, at.path, applies, at.part) or TuningDocument(
            generated_at=now(),
            printer=Printer(site=at.site, node=at.path, part=at.part),
            applies_to=applies,
        )
        if any(lk.slice.file_id == record.file_id for lk in doc.looks[-1:]):
            raise Refused(
                f"the last look already reads the piece {record.file_id} made: undo it to look again"
            )
        look_id = next_id(doc, "look")
        past = [
            pf.Past(
                lk.id,
                {x.fault: x.severity for x in lk.seen},
                [
                    pf.Stepped(
                        lk.id,
                        st.fault,
                        c.setting,
                        c.before if c.before is not None else st.used or c.after,
                        c.after,
                        lk.severity(st.fault) or 0,
                        back=st.back,
                    )
                    for c in lk.applied
                    for st in [lk.proposal(c.setting)]
                    if st is not None
                ],
            )
            for lk in doc.looks
        ]
        decided = pf.next_step(dict(seen), used, past)
        look = Look(
            id=look_id,
            at=datetime.now(timezone.utc),
            slice=SliceRef(
                file_id=record.file_id,
                part=record.made.name,
                variant=record.made.variant,
                params=dict(record.made.params),
                used=used,
                source=look_id,
            ),
            seen=[
                Seen(fault=f, severity=v, where=str(where.get(f, "")), source=look_id)
                for f, v in seen.items()
            ],
            note=note,
            proposed=[
                LookStep(
                    setting=m.key,
                    kind=m.kind,  # type: ignore[arg-type]
                    unit=m.unit,
                    fault=m.fault,
                    used=m.used,
                    new=m.new,
                    back=m.back,
                    why=m.why,
                    source=look_id,
                )
                for m in decided.moves
            ],
            said=decided.said,
        )
        doc.looks.append(look)
        doc = _write(doc)
        return doc, doc.looks[-1]


def answer(doc: TuningDocument) -> dict:
    """The document as a route answers it: itself, each setting's trend and each fault's."""
    return {
        "document": doc.model_dump(mode="json", by_alias=True),
        "trends": {
            key: {"term": t.term, "state": t.state, "stop": t.stop, "said": t.said}
            for key, t in trends(doc).items()
        },
        "faults": fault_trends(doc),
    }


def fault_trends(doc: TuningDocument) -> Dict[str, str]:
    """Each fault seen over the document's looks: its severity at each, and the change
    applied after it. A fault no look saw is left out, though each said none of it."""
    out: Dict[str, str] = {}
    for f in pf.FAULTS:
        if not any(lk.severity(f.id) for lk in doc.looks):
            continue
        marks = []
        for lk in doc.looks:
            sev = lk.severity(f.id)
            if sev is None:
                continue
            mark = f"{pf.SEVERITY[sev].split(':')[0]} at {lk.id}"
            moved = [
                c
                for c in lk.applied
                if (st := lk.proposal(c.setting)) is not None and st.fault == f.id
            ]
            if moved:
                mark += " (then " + ", ".join(f"{c.setting} {c.after:g}" for c in moved) + ")"
            marks.append(mark)
        if marks:
            out[f.id] = "; ".join(marks)
    return out


def said_look(look: Look) -> str:
    """A look in one line: what it saw, and the change it proposes."""
    seen = [
        f"{pf.BY_ID[x.fault].name.lower()} {pf.SEVERITY[x.severity].split(':')[0]}"
        + (f" ({x.where})" if x.where else "")
        for x in look.seen
        if x.severity
    ]
    out = f"{look.slice.part} looked at: " + (", ".join(seen) if seen else "nothing wrong")
    moves = [
        f"{st.setting} {_plain_value(st.used, st.unit)} -> {_plain_value(st.new, st.unit)}"
        + (" (put back)" if st.back else "")
        for st in look.proposed
    ]
    out += "; proposed: " + ("; ".join(moves) if moves else "nothing")
    if look.said:
        out += "; " + "; ".join(look.said)
    return out


def _plain_value(v: Optional[float], unit: str) -> str:
    if v is None:
        return "-"
    return f"{round(v, 4):g}" + (
        f" {unit}" if unit and unit != "%" else ("%" if unit == "%" else "")
    )


# ---- the older shape, read once -------------------------------------------------------------


def _carry_over(site: str, printer: str, applies: AppliesTo, part: str) -> None:
    """A correction kept for ``printer`` in the older shape, read into its document's
    first turns and removed. Only a printer's: a router's keeps its own shape."""
    old = state_dir() / "corrections" / site / f"{printer}.json"
    if not old.is_file():
        return
    try:
        data = json.loads(old.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    if (
        not isinstance(data, dict)
        or "printer" not in data
        or data.get("setting") != "xy_contour_compensation"
    ):
        return
    path = kept_at(site, printer, applies)
    doc = _read(path) or TuningDocument(
        generated_at=now(),
        printer=Printer(site=site, node=printer, part=part or "unknown"),
        applies_to=applies,
    )
    for m in data.get("measurements") or []:
        turn_id = next_id(doc)
        sliced = [float(v) for v in m.get("sliced") or []]
        measured = list(m.get("measured") or [])
        if len(sliced) != 3 or len(measured) != 3:
            continue
        ref = SliceRef(
            file_id=str(m.get("file_id")),
            part=str(m.get("part")),
            used={"xy_contour_compensation": float(m.get("used") or 0.0)},
            source=turn_id,
        )
        values = {
            name: [float(v)]
            for name, v in zip(("x", "y", "z"), measured, strict=True)
            if v is not None
        }
        turn = _solve_turn(
            turn_id,
            datetime.fromisoformat(str(m.get("at")).replace("Z", "+00:00")),
            ref,
            box_plan((sliced[0], sliced[1], sliced[2])),
            values,
            Instrument(),
            {k: v for k, v in EARLIER_ASSUMED.items()},
            doc.turns,
            whole_from={"xy_contour_compensation": float(m.get("correction"))},
        )
        turn.converted = (
            "the earlier correction of this printer, read once: its X, Y and Z against the "
            "size sliced, the scales and the foot assumed none as its rule took them, its "
            "change the one it applied; it kept no caliper's resolution, and "
            f"{RESOLUTION:g} mm is taken"
        )
        turn.applied = [
            Change(
                setting="xy_contour_compensation",
                kind="process",
                unit="mm",
                before=float(m.get("used") or 0.0),
                after=float(m.get("correction")),
                at=turn.at,
                source=turn_id,
            )
        ]
        doc.turns.append(turn)
    _write(doc)
    old.unlink()


# ---- the next slices --------------------------------------------------------------------------


def applied(
    profile: PrinterProfile, site: Optional[str], printer: Optional[str], module: str
) -> PrinterProfile:
    """``profile`` with the settings the printer's tuning holds for the filament and
    process the profile names, each in its ``set`` with origin ``measured``: what every
    slice for that printer takes. The profile as it is where none is held, or the slice
    is by another slicer module."""
    if module != MODULE or not site or not printer:
        return profile
    section = profile.sections.get(MODULE) or {}
    if not section.get("filament") or not section.get("process"):
        return profile
    applies = AppliesTo(filament=str(section["filament"]), process=str(section["process"]))
    doc = load(site, printer, applies, profile.part)
    if doc is None or not doc.settings:
        return profile
    section = json.loads(json.dumps(section))
    for key, held in doc.settings.items():
        entry = doc.entry(held.source)
        # OrcaSlicer writes a percentage with its sign only for the shrinkages.
        written = key in TUNED and TUNED[key].unit == "%"
        value = f"{held.value:g}" + ("%" if written else "")
        how = "seen on" if isinstance(entry, Look) else "read from"
        section.setdefault("set", {}).setdefault(held.kind, {})[key] = {
            "value": [value] if held.kind == "filament" else value,
            "source": f"{site}'s {printer}, tuned: {entry.id} of its {applies.filament} "
            f"tuning, {how} {entry.slice.part} ({entry.at:%Y-%m-%d})",
            "origin": "measured",
        }
    return profile.model_copy(update={"sections": {**profile.sections, MODULE: section}})


# ---- in words --------------------------------------------------------------------------------


def _value(v: Optional[float], unit: str) -> str:
    if v is None:
        return "-"
    if unit == "%":
        return f"{round(v, 3):g}%"
    if unit == "":
        return f"{v:+.3%}"
    return f"{v:+.3f} mm"


def said(turn: Turn) -> str:
    """A turn in one line: each term found, and each change proposed."""
    found = [
        f"{t.term} {_value(t.value, t.unit)} ± {abs(t.error or 0) * (100 if t.unit == '' else 1):.2g}"
        + ("%" if t.unit == "" else "")
        for t in turn.terms
        if t.determined and t.basis == "solved" and t.term != "scale_xy"
    ]
    loose = sorted({t.term for t in turn.terms if not t.determined and t.term != "scale_xy"})
    out = f"{turn.slice.part} read at {len(turn.readings)} features"
    out += ": " + (", ".join(found) if found else "no term determined")
    if loose:
        out += f"; not separated: {', '.join(loose)}"
    moves = [
        f"{p.setting} {_value(p.used, p.unit if p.unit == '%' else 'mm').strip()} -> "
        f"{_value(p.new, p.unit if p.unit == '%' else 'mm').strip()}"
        for p in turn.proposed
        if p.new is not None
    ]
    out += "; proposed: " + ("; ".join(moves) if moves else "nothing")
    return out


def render_markdown(doc: TuningDocument, explain: bool = False) -> str:
    """The document as tables: the printer and what it applies to, the settings held,
    each turn's readings, terms and proposals, and the trend of each setting's term.
    With ``explain``, each turn's design matrix and residuals too. A view, not a
    computation."""
    out = [f"# Print tuning: {doc.printer.site}'s {doc.printer.node}", ""]
    out.append(
        f"Schema `{doc.schema_}` · generated {doc.generated_at} by `{doc.generator}` · "
        f"{doc.applies_to.filament}, {doc.applies_to.process} ({doc.applies_to.slicer})"
    )
    out.append("")
    out += ["## Held for the next slices", ""]
    if doc.settings:
        out += ["| Setting | Value | From |", "|---|---|---|"]
        for key, held in doc.settings.items():
            out.append(f"| `{key}` | {_value(held.value, held.unit)} | `{held.source}` |")
    else:
        out.append("Nothing: the next slices take the profile's own values.")
    out.append("")
    for turn in doc.turns:
        out += [f"## {turn.id}: {turn.slice.part} ({turn.at:%Y-%m-%d %H:%M})", ""]
        if turn.converted:
            out += [f"*{turn.converted}.*", ""]
        out += [
            f"Slice `{turn.slice.file_id}`; caliper step {turn.instrument.resolution:g} mm"
            + (
                f", repeatability {turn.instrument.repeatability:g} mm"
                if turn.instrument.repeatability is not None
                else ""
            )
            + (
                "; assumed " + ", ".join(f"{k} = {v:g}" for k, v in turn.assumed.items())
                if turn.assumed
                else ""
            ),
            "",
            "| Feature | Kind | Nominal | Read | Error | ± |",
            "|---|---|---|---|---|---|",
        ]
        for r in turn.readings:
            kind = f"{r.kind} {r.axis}" + (f" {r.level}" if r.axis != "z" else "")
            reads = ", ".join(f"{v:g}" for v in r.values)
            out.append(
                f"| {r.feature} | {kind} | {r.nominal:g} | {reads} | {r.error:+.3f} | {r.uncertainty:.3f} |"
            )
        out += ["", "| Term | Value | Error | Basis | Note |", "|---|---|---|---|---|"]
        for t in turn.terms:
            note = t.note or (
                "not separated from " + ", ".join(t.with_terms) if not t.determined else ""
            )
            if t.determined and t.basis == "solved" and not t.resolved:
                note = (note + "; " if note else "") + "within what the readings resolve"
            err = "-" if t.error is None else _value(t.error, t.unit).lstrip("+")
            out.append(f"| {t.term} | {_value(t.value, t.unit)} | {err} | {t.basis} | {note} |")
        for w in turn.walls:
            out.append(
                f"| wall `{w.feature}` | {w.error:+.3f} mm | {w.uncertainty:.3f} mm | measured | {w.said} |"
            )
        out += ["", "| Setting | Used | Proposed | Why |", "|---|---|---|---|"]
        for p in turn.proposed:
            unit = p.unit if p.unit == "%" else "mm"
            done = " (applied)" if any(c.setting == p.setting for c in turn.applied) else ""
            out.append(
                f"| `{p.setting}` | {_value(p.used, unit)} | {_value(p.new, unit)}{done} | {p.why} |"
            )
        if explain:
            out += ["", "Design matrix (a row per reading, a column per unknown):", ""]
            out.append("| Reading | " + " | ".join(turn.fit.columns) + " | Residual |")
            out.append("|---" * (len(turn.fit.columns) + 2) + "|")
            for name, row in zip(turn.fit.rows, turn.fit.matrix, strict=True):
                cells = " | ".join(f"{c:g}" for c in row)
                out.append(f"| {name} | {cells} | {turn.fit.residuals.get(name, 0):+.4f} |")
            chi = "none" if turn.fit.chi2 is None else f"{turn.fit.chi2:.3g}"
            out += [
                "",
                f"Rank {turn.fit.rank} of {len(turn.fit.columns)} unknowns, {turn.fit.readings} "
                f"readings, {turn.fit.dof} to spare; the residuals' mean square over their "
                f"uncertainties {chi}.",
            ]
            for line in turn.fit.said:
                out.append(f"- {line}")
        out.append("")
    for look in doc.looks:
        out += [f"## {look.id}: {look.slice.part} ({look.at:%Y-%m-%d %H:%M}), seen", ""]
        out += [f"Slice `{look.slice.file_id}`" + (f"; {look.note}" if look.note else ""), ""]
        out += ["| Fault | Seen | Where |", "|---|---|---|"]
        for x in look.seen:
            out.append(f"| {pf.BY_ID[x.fault].name} | {pf.SEVERITY[x.severity]} | {x.where} |")
        out += ["", "| Setting | Used | Proposed | Why |", "|---|---|---|---|"]
        for st in look.proposed:
            done = " (applied)" if any(c.setting == st.setting for c in look.applied) else ""
            out.append(
                f"| `{st.setting}` | {_plain_value(st.used, st.unit)} | "
                f"{_plain_value(st.new, st.unit)}{done} | {st.why} |"
            )
        for line in look.said:
            out.append(f"- {line}")
        out.append("")
    if doc.turns:
        out += ["## Convergence", "", "| Setting | Term | State | Said |", "|---|---|---|---|"]
        for key, t in trends(doc).items():
            out.append(f"| `{key}` | {t.term} | {t.state} | {t.said} |")
        out.append("")
    return "\n".join(out).rstrip() + "\n"
