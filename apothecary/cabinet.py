"""A part's cabinet: a drawer for each piece made of it, and what is filed about that piece.

A **drawer** is one piece a machine made of a part: a print or a cut. It keeps what made
it, whole -- the slice's record or the cut's (``slicer/models.py``, ``cam/models.py``), so
the piece is measured from its drawer after its kept file is forgotten -- and names the
variant, its parameters, the draft of its SCAD and its STL's hash where the record has
them, the machine, the filament and process a print used, and the job that ran it and how
that ended. A piece made from a picture is not a part's and has no drawer.

What is said of the piece afterwards is **filed** in its drawer, a filing each: what
calipers read (a printer's next turn of its tuning, ``slicer/tuning.py``; a router's tool
allowance, ``cam/measured.py``), each fault seen by eye (a printer's next look), or a
note. A filing names the turn, look or allowance it made, and says when that was undone.
The printer's tuning and the router's allowance stay their machine's: the drawer is the
part's own account of what was made of it and what was said of each piece.

What calipers read is also **checked** against the design (``Checked``): each dimension's
designed size, the mean read, the deviation, and the tolerance it was checked with and
whose that is (``tolerance_of``). ``dimensions`` is a piece's dimensions with the newest
reading of each: Part › Feedback's rows and the marks the world's Measure layer draws on
the part are both read from it.

**A drawer is opened** when a job begins on a kept file whose slice or cut names a part
(``job_told``, on ``apothecary.jobs.LISTENERS``), and the job's end says how it ended;
or when something is filed of a kept file no job here ran -- printed from a card, cut
before -- by ``for_slice`` and ``for_cut``. Filed by its file, a piece goes into the
newest drawer of that file.

**Where it is kept**: the state folder's ``cabinet/<part>/``, one JSON file per drawer
named for the moment it was opened (``apothecary/stamped.py``), written whole under a
lock.
"""

from __future__ import annotations

import logging
import math
import re
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Literal, Mapping, Optional, Protocol, Sequence, Tuple, Union

from pydantic import BaseModel, ConfigDict, Field, computed_field

from . import jobs
from .cam import measured as cut_measured
from .cam.models import CutRecord
from .models.units import PrintSettings
from .slicer import tuning
from .slicer.models import SliceRecord
from .stamped import claim, stamp
from .state_folder import private_folder, state_dir, write_whole

log = logging.getLogger(__name__)

SCHEMA = "part/cabinet/1"
PART = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.\-]{0,199}$")
DRAWER_ID = r"^[0-9]{8}T[0-9]{6}\.[0-9]{3}(-[1-9][0-9]{0,5})?$"
FILED_ID = r"^filed-[1-9][0-9]{0,5}$"
# The most a note says, in characters.
NOTE_MOST = 2000

Made = Literal["print", "cut"]
Kind = Literal["measured", "look", "note"]


class Refused(ValueError):
    """What cannot be filed, and why: nothing is kept."""


class Machine(BaseModel):
    """The machine that made the piece, and where it stood."""

    kind: Literal["printer", "router"]
    name: str
    site: Optional[str] = None
    path: Optional[str] = None  # its node in the site
    port: Optional[str] = None
    part: Optional[str] = None  # a printer's part, which keeps its profile


class MadeFrom(BaseModel):
    """The kept file the piece was made from."""

    name: str
    file_id: str
    sha256: Optional[str] = None  # as the job that ran it recorded it


# How a print ended without finishing: what Part › Feedback offers to try again for.
STOPPED = ("cancelled", "failed")
# An OrcaSlicer file's mark of each layer it begins, and the height it names after.
_LAYER = ";LAYER_CHANGE"
_LAYER_Z = re.compile(r"^;Z:\s*([-+]?\d+(?:\.\d+)?)")


class Stopped(BaseModel):
    """Where a print that did not finish stopped: the layer of the last line sent, of the
    file's layers, and that layer's height. Layer 0 is the file's start, before its first."""

    layer: int = Field(..., ge=0)
    layers: int = Field(..., ge=1)
    z: Optional[float] = None
    sent: int = Field(..., ge=0)
    total: int = Field(..., ge=0)

    def said(self) -> str:
        if self.layer == 0:
            return f"in its start, before the first of {self.layers} layers"
        height = f", {self.z:g} mm" if self.z is not None else ""
        return f"on layer {self.layer} of {self.layers}{height}"


def stopped_at(text: str, sent: int, total: int) -> Optional[Stopped]:
    """Where a file stopped once ``sent`` of its lines were sent, counted as a print sends
    them (``gcode.strip_gcode``: each line with a command once its comment is taken off).
    None for a file that marks no layers."""
    from .firmware.gcode import strip_gcode

    layers = sum(1 for line in text.splitlines() if line.startswith(_LAYER))
    if not layers:
        return None
    layer, z, n = 0, None, 0
    for line in text.splitlines():
        if n >= sent:
            break
        if line.startswith(_LAYER):
            layer, z = layer + 1, None
            continue
        m = _LAYER_Z.match(line)
        if m:
            z = float(m.group(1))
        elif strip_gcode(line):
            n += 1
    return Stopped(layer=layer, layers=layers, z=z if layer else None, sent=sent, total=total)


def _stopped(job: jobs.Job) -> Optional[Stopped]:
    """Where ``job``'s print stopped, from its kept file, while that file is kept."""
    if job.kind != "print" or job.outcome not in STOPPED or not job.input.file_id:
        return None
    from .firmware import devices

    path = devices.prints_dir() / f"{job.input.file_id}.gcode"
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    sent = int(job.detail.get("sent") or 0)
    return stopped_at(text, sent, int(job.detail.get("total") or 0))


class Ran(BaseModel):
    """The job that made the piece: as it began, and as it ended."""

    id: str
    outcome: str = "running"
    reason: Optional[str] = None
    started_at: datetime
    finished_at: Optional[datetime] = None
    # A print that did not finish: where it stopped (STOPPED).
    stopped: Optional[Stopped] = None
    # What the print's start had the board say of its levelling (devices.levelled_by):
    # whether it was on, the probe's offset, the mesh's range, where the probe said the
    # grid lies. None for a start that said none of it.
    levelled: Optional[dict] = None


class SeenFiled(BaseModel):
    fault: str
    severity: int = Field(..., ge=0, le=3)
    where: str = ""


ToleranceFrom = Literal["part", "printer", "default"]


class Checked(BaseModel):
    """One dimension of the piece read against its design: what it was designed at, what
    calipers read (the mean of the repeats), how far apart, and the tolerance it was
    checked with, either way, and whose that was."""

    name: str
    designed: float  # mm
    measured: float  # mm
    deviation: float  # measured less designed, mm
    tolerance: float = Field(..., ge=0)
    tolerance_from: ToleranceFrom

    @computed_field
    @property
    def within(self) -> bool:
        return abs(self.deviation) <= self.tolerance + 1e-9

    def said(self) -> str:
        default = " (a default)" if self.tolerance_from == "default" else ""
        return (
            f"{self.name} {self.measured:.2f} mm against {self.designed:.2f} designed, "
            f"{self.deviation:+.2f}: {'within' if self.within else 'outside'} "
            f"± {self.tolerance:.2f}{default}"
        )


class Filed(BaseModel):
    """One thing said of the piece: what was read, what was seen, or a note."""

    id: str = Field(..., pattern=FILED_ID)
    at: datetime
    kind: Kind
    said: str
    # What it made: a printer's turn or look ("turn-3", "look-2"), or the router's allowance.
    made: Optional[str] = None
    readings: Dict[str, List[float]] = Field(default_factory=dict)  # mm, by feature
    # What was read, each dimension against its design (``dimensions``).
    checked: List[Checked] = Field(default_factory=list)
    seen: List[SeenFiled] = Field(default_factory=list)
    note: str = Field("", max_length=NOTE_MOST)
    undone: Optional[datetime] = None  # when what it made was undone


class Drawer(BaseModel):
    """A piece made of a part, and what has been filed about it."""

    model_config = ConfigDict(populate_by_name=True)

    schema_: Literal["part/cabinet/1"] = Field(SCHEMA, alias="schema")
    id: str = Field(..., pattern=DRAWER_ID)
    part: str
    at: datetime  # when it was opened: its job's start, else its first filing
    made: Made
    file: MadeFrom
    variant: Optional[str] = None
    params: Dict[str, object] = Field(default_factory=dict)
    draft: Optional[str] = None  # the sha256 of the SCAD draft it was rendered from
    stl_sha256: Optional[str] = None
    machine: Machine
    filament: Optional[str] = None  # a print's filament profile
    process: Optional[str] = None  # a print's process profile
    slice: Optional[SliceRecord] = None
    cut: Optional[CutRecord] = None
    job: Optional[Ran] = None
    filed: List[Filed] = Field(default_factory=list)

    def said(self) -> str:
        """The drawer in a line: what made the piece, on what, and how it ended."""
        how = f"{self.made} on {self.machine.name}"
        if self.filament:
            how += f" ({self.filament})"
        if self.variant:
            how += f", variant {self.variant[:8]}"
        ended = self.job.outcome if self.job else "no job here"
        kept = [f for f in self.filed if f.undone is None]
        return f"{how}: {ended}" + (f"; {len(kept)} filed" if kept else "")


_LOCK = threading.RLock()


def cabinet_dir() -> Path:
    return state_dir() / "cabinet"


def lock() -> threading.RLock:
    """The lock every drawer is written under: what rewrites drawers from outside, a
    machine renamed (``machine_names.py``), takes it as this module does."""
    return _LOCK


def _folder(part: str) -> Path:
    if not PART.match(part or ""):
        raise Refused(f"{part!r} is not a part's name")
    return cabinet_dir() / part


def _read(path: Path) -> Optional[Drawer]:
    try:
        return Drawer.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _write(drawer: Drawer) -> Drawer:
    checked = Drawer.model_validate(drawer.model_dump(by_alias=True))
    write_whole(
        _folder(checked.part) / f"{checked.id}.json",
        checked.model_dump_json(by_alias=True, indent=2),
    )
    return checked


def parts() -> List[str]:
    """Every part with a drawer, by name."""
    root = cabinet_dir()
    if not root.is_dir():
        return []
    return sorted(p.name for p in root.iterdir() if p.is_dir() and any(p.glob("*.json")))


def drawers(part: str) -> List[Drawer]:
    """``part``'s drawers, the newest first."""
    folder = _folder(part)
    with _LOCK:
        if not folder.is_dir():
            return []
        found = [d for d in (_read(p) for p in folder.glob("*.json")) if d is not None]
    return sorted(found, key=lambda d: (d.at, d.id), reverse=True)


def get(part: str, drawer_id: str) -> Optional[Drawer]:
    """The drawer, and a print's that stopped told where, when it was kept before the
    cabinet said so and its job and file are still kept."""
    if not re.match(DRAWER_ID, drawer_id or ""):
        return None
    path = _folder(part) / f"{drawer_id}.json"
    with _LOCK:
        drawer = _read(path) if path.is_file() else None
        ran = drawer.job if drawer is not None else None
        if ran is not None and ran.outcome in STOPPED and ran.stopped is None:
            job = jobs.get(ran.id)
            told = _stopped(job) if job is not None else None
            if told is not None:
                drawer.job = ran.model_copy(update={"stopped": told})
                drawer = _write(drawer)
        return drawer


# ---- opening a drawer ---------------------------------------------------------------------


def part_of_slice(record: SliceRecord) -> Optional[str]:
    """The part a slice made, or None: a piece made from a picture is no part's."""
    return record.made.name if record.made.kind == "part" else None


def _ran(job: jobs.Job) -> Ran:
    return Ran(
        id=job.id,
        outcome=job.outcome,
        reason=job.reason,
        started_at=job.started_at,
        finished_at=job.finished_at,
        stopped=_stopped(job),
        levelled=(job.detail or {}).get("start"),
    )


def _open(part: str, at: datetime, **fields) -> Drawer:
    folder = private_folder(_folder(part))
    kept = claim(folder, stamp(at), ".json")
    try:
        return _write(Drawer(id=kept.stem, part=part, at=at, **fields))
    except BaseException:
        kept.unlink(missing_ok=True)
        raise


def _of_file(part: str, file_id: str, job: Optional[jobs.Job]) -> Optional[Drawer]:
    """The drawer of ``file_id`` a filing or a job goes into: with a job, the one it
    opened, else one no job holds yet; without, the newest of that file."""
    mine = [d for d in drawers(part) if d.file.file_id == file_id]
    if job is None:
        return mine[0] if mine else None
    held = next((d for d in mine if d.job and d.job.id == job.id), None)
    return held or next((d for d in mine if d.job is None), None)


def _sha(job: Optional[jobs.Job]) -> Optional[str]:
    return job.input.sha256 if job is not None else None


def for_slice(record: SliceRecord, job: Optional[jobs.Job] = None) -> Drawer:
    """The drawer of the piece printed from ``record``'s slice: found by its file (and
    its job), else opened."""
    part = part_of_slice(record)
    if part is None:
        raise Refused(f"{record.name} was sliced from a piece made from a picture, no part's")
    with _LOCK:
        found = _of_file(part, record.file_id, job)
        if found is not None:
            if job is not None and found.job is None:
                found.job = _ran(job)
                found.file.sha256 = found.file.sha256 or _sha(job)
                return _write(found)
            return found
        applies = tuning.applies_of(record)
        at = record.printer
        return _open(
            part,
            job.started_at if job is not None else datetime.now(timezone.utc),
            made="print",
            file=MadeFrom(name=record.name, file_id=record.file_id, sha256=_sha(job)),
            variant=record.made.variant,
            params=dict(record.made.params),
            draft=record.made.draft,
            stl_sha256=record.stl_sha256,
            machine=Machine(
                kind="printer", name=at.name, site=at.site, path=at.path, port=at.port, part=at.part
            ),
            filament=applies.filament,
            process=applies.process,
            slice=record,
            job=_ran(job) if job is not None else None,
        )


def for_cut(record: CutRecord, job: Optional[jobs.Job] = None) -> Drawer:
    """The drawer of the piece cut by ``record``'s toolpath: found by its file (and its
    job), else opened."""
    with _LOCK:
        found = _of_file(record.part, record.file_id, job)
        if found is not None:
            if job is not None and found.job is None:
                found.job = _ran(job)
                found.file.sha256 = found.file.sha256 or _sha(job)
                return _write(found)
            return found
        at = record.router
        return _open(
            record.part,
            job.started_at if job is not None else datetime.now(timezone.utc),
            made="cut",
            file=MadeFrom(name=record.name, file_id=record.file_id, sha256=_sha(job)),
            variant=record.variant,
            params=dict(record.params),
            machine=Machine(kind="router", name=at.name, site=at.site, path=at.path, port=at.port),
            cut=record,
            job=_ran(job) if job is not None else None,
        )


def for_file(file_id: str, job: Optional[jobs.Job] = None) -> Optional[Drawer]:
    """The drawer of the piece made from the kept file ``file_id``, opened if need be:
    None for a file no slice or cut of a part made."""
    from .cam import service as cam_service
    from .slicer import service as slicer_service

    record = slicer_service.get_record(file_id)
    if record is not None:
        return for_slice(record, job) if part_of_slice(record) else None
    cut = cam_service.get_record(file_id)
    return for_cut(cut, job) if cut is not None else None


def of_job(job_id: str) -> Optional[Drawer]:
    """The drawer the piece job ``job_id`` made is in, or None."""
    with _LOCK:
        for part in parts():
            for drawer in drawers(part):
                if drawer.job is not None and drawer.job.id == job_id:
                    return drawer
    return None


def job_told(job: jobs.Job) -> None:
    """A print or a cut began or ended (``apothecary.jobs.LISTENERS``): its piece's drawer
    opened as it begins, and told how it ended. Never raises: the machine's thread tells it."""
    if job.kind not in ("print", "cut") or not job.input.file_id:
        return
    try:
        with _LOCK:
            if job.running:
                for_file(job.input.file_id, job)
                return
            drawer = of_job(job.id)
            if drawer is not None:
                drawer.job = _ran(job)
                _write(drawer)
    except Exception:  # the cabinet's failure is no reason for a machine's to be told one
        log.exception("the cabinet could not keep job %s", job.id)


# ---- by variant ---------------------------------------------------------------------------
#
# Part › Variants lists each piece under the saved variant it was made of. A piece rendered
# from a draft names the draft's sha256, which is a save's when the draft was that save's
# text: ``saved`` the variant as it is now, ``earlier`` one of its saves before. Otherwise a
# piece whose values are the ones a variant's text sets -- the part's numbers applied, or an
# overlay's -- was made ``values`` of it. A piece of no saved variant is ``own``, the part's
# own text; ``draft``, a text never saved; ``values``, numbers never saved; or ``deleted``,
# of variants now in the trash.

_RANK = {"saved": 0, "earlier": 1, "values": 2}


class Save(Protocol):
    """One save of a variant, as ``projects.parts.saved.save_texts`` reads it."""

    name: str
    commit: str
    digest: str
    params: Mapping[str, object]
    current: bool
    deleted: bool


class Piece(BaseModel):
    """A drawer as Part › Variants lists it."""

    id: str
    at: datetime
    made: Made
    machine: str
    filament: Optional[str] = None
    outcome: Optional[str] = None  # how its job ended; None: no job here made it
    line: str
    params: Dict[str, object] = Field(default_factory=dict)
    cached: Optional[str] = None  # its variant's key in the variant cache
    draft: bool = False  # rendered from a draft of the part's text
    filed: int = 0  # what is filed of it and not undone
    how: Literal["saved", "earlier", "values", "own", "draft", "deleted"]
    commit: Optional[str] = None  # the save it was made of
    deleted: List[str] = Field(default_factory=list)  # the deleted variants it was made of


class ByVariant(BaseModel):
    part: str
    # Each saved variant a piece was made of, its pieces the newest first.
    variants: Dict[str, List[Piece]] = Field(default_factory=dict)
    unsaved: List[Piece] = Field(default_factory=list)


def _same(a: object, b: object) -> bool:
    if isinstance(a, bool) or isinstance(b, bool):
        return a is b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return float(a) == float(b)
    if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
        return len(a) == len(b) and all(_same(x, y) for x, y in zip(a, b, strict=True))
    return a == b


def _same_values(made: Mapping[str, object], saved: Mapping[str, object]) -> bool:
    """Whether a piece was made with the values a save sets: some, and the same."""
    return (
        bool(made) and made.keys() == saved.keys() and all(_same(made[k], saved[k]) for k in made)
    )


def _piece(drawer: Drawer, how: str, commit: Optional[str] = None, deleted=()) -> Piece:
    return Piece(
        id=drawer.id,
        at=drawer.at,
        made=drawer.made,
        machine=drawer.machine.name,
        filament=drawer.filament,
        outcome=drawer.job.outcome if drawer.job else None,
        line=drawer.said(),
        params=dict(drawer.params),
        cached=drawer.variant,
        draft=drawer.draft is not None,
        filed=sum(1 for f in drawer.filed if f.undone is None),
        how=how,
        commit=commit,
        deleted=list(deleted),
    )


def by_variant(part: str, found: Sequence[Drawer], saves: Sequence[Save]) -> ByVariant:
    """``found`` (the newest first) by the saved variant each piece was made of, the best
    match of each variant's saves (``saved``, then ``earlier``, then ``values``); a piece of
    several variants -- a duplicate's, the same values -- is listed under each. A piece is
    sorted by itself, whatever else was made: an earlier save counts only for a piece
    whose draft is no variant's text as it is now, and values are those a variant sets now."""
    sorted_ = ByVariant(part=part)
    now = {save.digest for save in saves if save.current}
    for drawer in found:
        best: Dict[Tuple[str, bool], Tuple[str, str]] = {}
        for save in saves:
            if drawer.draft is not None and drawer.draft == save.digest:
                if not save.current and drawer.draft in now:
                    continue
                how = "saved" if save.current else "earlier"
            elif save.current and _same_values(drawer.params, save.params):
                how = "values"
            else:
                continue
            key = (save.name, save.deleted)
            if key not in best or _RANK[how] < _RANK[best[key][0]]:
                best[key] = (how, save.commit)
        live = [(name, hit) for (name, deleted), hit in best.items() if not deleted]
        for name, (how, commit) in live:
            sorted_.variants.setdefault(name, []).append(_piece(drawer, how, commit))
        if live:
            continue
        gone = sorted(name for name, deleted in best if deleted)
        how = (
            "deleted" if gone else "draft" if drawer.draft else "values" if drawer.params else "own"
        )
        sorted_.unsaved.append(_piece(drawer, how, deleted=gone))
    return sorted_


# ---- dimensions ---------------------------------------------------------------------------
#
# A piece's dimensions are what a person reads of it with calipers, each against what it was
# designed at: a print's are the features its slice's plan names, else the box it sliced
# (``slicer/tuning.py`` ``plan_of``), a cut's the sizes its toolpath names. Each carries
# where its line runs, so the page draws it on the part, and its newest reading kept in the
# piece's drawer. Part › Feedback and the world's Measure layer both read them here.
#
# **The tolerance** a reading is checked with, either way: the part's, where its print
# settings declare one (a slice records it, ``tolerance``, declared) -- what its design
# allows, so what a piece of it must hold; else the printer's, where its slicer profile's
# ``measured`` holds a ``tolerance`` in mm -- what that printer holds, as measured; else
# ``PrintSettings``' own, said as a default. A cut piece's is the default.

TOLERANCE = "tolerance"  # the declared setting a slice records, and the profile's key
DEFAULT_TOLERANCE: float = PrintSettings.model_fields["tolerance"].default


class Tolerance(BaseModel):
    """How far a dimension of a piece may stand from its design, either way, and whose
    figure that is, in words."""

    value: float = Field(..., ge=0)
    source: ToleranceFrom
    said: str


def _mm(value: object) -> Optional[float]:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return None
    try:
        found = float(value)
    except ValueError:
        return None
    return found if math.isfinite(found) and found >= 0 else None


def _printer_tolerance(printer_part: str) -> Optional[Tuple[float, str]]:
    """The tolerance a printer's slicer profile holds under ``measured``, and its file."""
    from .slicer import profiles
    from .slicer.modules import SlicerError

    if not printer_part:
        return None
    try:
        profile = profiles.load_profile(printer_part)
    except SlicerError:
        return None
    held = profile.measured.get(TOLERANCE)
    value = _mm(held.value) if held is not None and held.unit in (None, "mm") else None
    return (value, profile.file) if value is not None else None


def tolerance_of(part: str, record: Optional[SliceRecord]) -> Tolerance:
    """The tolerance a piece of ``part`` printed from ``record``'s slice is checked with;
    a cut piece's (``record`` None) is the default."""
    if record is None:
        return Tolerance(
            value=DEFAULT_TOLERANCE,
            source="default",
            said=f"a default, {DEFAULT_TOLERANCE:g} mm: nothing states one for a cut piece",
        )
    declared = next(
        (s for s in record.settings if s.name == TOLERANCE and s.origin == "declared"), None
    )
    value = _mm(declared.value) if declared is not None else None
    if declared is not None and value is not None:
        return Tolerance(value=value, source="part", said=f"{part}'s print settings")
    held = _printer_tolerance(record.printer.part)
    if held is not None:
        return Tolerance(
            value=held[0], source="printer", said=f"{record.printer.name}'s profile, {held[1]}"
        )
    return Tolerance(
        value=DEFAULT_TOLERANCE,
        source="default",
        said=(
            f"a default, {DEFAULT_TOLERANCE:g} mm: neither {part}'s print settings nor "
            f"{record.printer.name}'s profile states one"
        ),
    )


class Reading(BaseModel):
    """A dimension's newest reading kept in the piece's drawer: the filing it is in."""

    filed: str
    at: datetime
    made: Optional[str] = None  # the turn or allowance that filing made
    read: List[float] = Field(default_factory=list)  # each size read, mm
    checked: Checked


class Dimension(BaseModel):
    """One dimension of a piece, as designed, and its newest reading."""

    name: str
    words: str  # what to read, as a person reads it
    kind: str  # outside, inside, height, wall
    axis: Optional[Literal["x", "y", "z"]] = None
    jaw: Optional[str] = None
    designed: float
    # Where its line runs: in the part's own frame through ``at`` along ``axis``, from
    # ``faces[0]`` to ``faces[1]`` (``part``, a plan's); the same from the low corner of
    # the box sliced (``box``); or nowhere said (``none``, a cut's).
    frame: Literal["part", "box", "none"]
    at: Optional[Tuple[float, float, float]] = None
    faces: Optional[Tuple[float, float]] = None
    reading: Optional[Reading] = None


class Dimensions(BaseModel):
    """A piece's dimensions, the tolerance a reading of it is checked with, and the piece:
    its drawer, or the kept file a piece made elsewhere was made from."""

    part: str
    drawer: Optional[str] = None
    file_id: Optional[str] = None
    made: Optional[Made] = None
    machine: Optional[str] = None
    variant: Optional[str] = None
    # A print's: the box sliced, x, y and z, the way up it prints; a box's dimensions are
    # its sides, and a plan's lines stand in its frame.
    size: Optional[List[float]] = None
    tolerance: Optional[Tolerance] = None
    dimensions: List[Dimension] = Field(default_factory=list)
    why: str = ""  # why there are none


def _newest(drawer: Optional[Drawer], dims: List[Dimension], tolerance: Tolerance) -> None:
    """Each dimension's newest reading kept in ``drawer`` and not undone; a filing kept
    before readings were checked is checked here, with the tolerance as it is now."""
    if drawer is None:
        return
    by_name = {d.name: d for d in dims}
    for filed in reversed(drawer.filed):
        if filed.kind != "measured" or filed.undone is not None:
            continue
        checks = {c.name: c for c in filed.checked}
        for name, read in filed.readings.items():
            dim = by_name.get(name)
            if dim is None or dim.reading is not None or not read:
                continue
            check = checks.get(name) or _check(name, dim.designed, read, tolerance)
            dim.reading = Reading(
                filed=filed.id, at=filed.at, made=filed.made, read=list(read), checked=check
            )


def dimensions(
    part: str,
    drawer: Optional[Drawer] = None,
    record: Optional[Union[SliceRecord, CutRecord]] = None,
) -> Dimensions:
    """The dimensions of the piece in ``drawer``, or of one made from ``record``'s kept file
    that no drawer holds yet: as designed, each with its newest reading kept."""
    if drawer is not None:
        record = drawer.slice or drawer.cut
    out = Dimensions(
        part=part,
        drawer=drawer.id if drawer is not None else None,
        file_id=getattr(record, "file_id", None),
    )
    if isinstance(record, SliceRecord):
        out.made, out.machine, out.variant = "print", record.printer.name, record.made.variant
        out.size = list(record.size) if record.size else None
        out.tolerance = tolerance_of(part, record)
        try:
            plan = tuning.plan_of(record)
        except tuning.Refused as exc:
            out.why = str(exc)
            return out
        frame = "part" if record.plan is not None else "box"
        out.dimensions = [
            Dimension(
                name=f.name,
                words=f.words,
                kind=f.kind,
                axis=f.axis,
                jaw=f.jaw,
                designed=f.nominal,
                frame=frame,
                at=f.at,
                faces=f.faces,
            )
            for f in plan.features
        ]
    elif isinstance(record, CutRecord):
        out.made, out.machine, out.variant = "cut", record.router.name, record.variant
        out.tolerance = tolerance_of(part, None)
        out.dimensions = [
            Dimension(name=f.name, words=f.words, kind=f.side, designed=f.size, frame="none")
            for f in record.features
        ]
        if not out.dimensions:
            out.why = f"{record.name} names nothing to measure"
    else:
        out.why = (
            f"nothing made of {part} yet: its print or its cut opens a drawer in Part › Feedback"
        )
        return out
    _newest(drawer, out.dimensions, out.tolerance)
    return out


# ---- filing -------------------------------------------------------------------------------


def _next_filed(drawer: Drawer) -> str:
    taken = [int(f.id.split("-")[1]) for f in drawer.filed]
    return f"filed-{max(taken, default=0) + 1}"


def _file(drawer: Drawer, kind: Kind, said: str, **fields) -> Drawer:
    """The filing added to the drawer as it is kept now, not as it was read: a job's end
    told in between stays told."""
    with _LOCK:
        kept = get(drawer.part, drawer.id) or drawer
        kept.filed.append(
            Filed(
                id=_next_filed(kept), at=datetime.now(timezone.utc), kind=kind, said=said, **fields
            )
        )
        return _write(kept)


def _checked_print(drawer: Drawer, readings: Mapping[str, Sequence[float]]) -> List[Checked]:
    """Each feature read of a printed piece against its slice's plan (or its box): what
    the tuning would refuse as no reading of it is refused here too."""
    assert drawer.slice is not None
    plan = tuning.plan_of(drawer.slice)
    tolerance = tolerance_of(drawer.part, drawer.slice)
    out = []
    for name, read in readings.items():
        read = [float(v) for v in read]
        feature = tuning.feature_read(plan, name, read, drawer.part)
        if read:
            out.append(_check(name, feature.nominal, read, tolerance))
    if not out:
        raise Refused(f"read one of {', '.join(plan.names)}: what {drawer.part} names to measure")
    return out


def _check(name: str, designed: float, read: Sequence[float], tolerance: "Tolerance") -> Checked:
    mean = sum(read) / len(read)
    return Checked(
        name=name,
        designed=round(designed, 6),
        measured=round(mean, 6),
        deviation=round(mean - designed, 6),
        tolerance=tolerance.value,
        tolerance_from=tolerance.source,
    )


def measured(
    drawer: Drawer,
    readings: Mapping[str, Sequence[float]],
    instrument: Optional[tuning.Instrument] = None,
    assumed: Optional[Mapping[str, float]] = None,
) -> Tuple[Drawer, Optional[tuning.TuningDocument], Optional[tuning.Turn]]:
    """A printed piece read with calipers, each feature checked against its design and
    filed: the printer's next turn of its tuning. A piece the printer's last turn already
    reads is a check alone, filed with no turn: the turn moves the printer's settings
    once for a piece, and Undo turn takes it back to read it again."""
    if drawer.slice is None:
        raise Refused(f"{drawer.id} is a cut: a cut piece is measured by its sizes")
    with _LOCK:
        checked = _checked_print(drawer, readings)
        kept = {k: list(v) for k, v in readings.items()}
        already = tuning.reads_last(drawer.slice)
        if already is not None:
            said = (
                "; ".join(c.said() for c in checked)
                + f": kept as a check of the piece, and no turn: {already} already reads it "
                f"for {drawer.machine.path or drawer.machine.name}'s tuning"
            )
            return _file(drawer, "measured", said, readings=kept, checked=checked), None, None
        doc, turn = tuning.add_turn(drawer.slice, readings, instrument, assumed)
        drawer = _file(
            drawer, "measured", tuning.said(turn), made=turn.id, readings=kept, checked=checked
        )
    return drawer, doc, turn


def measured_cut(
    drawer: Drawer, sizes: Mapping[str, Optional[float]]
) -> Tuple[Drawer, cut_measured.Correction]:
    """A cut piece measured, each size checked against its design: the router's tool
    allowance it makes, kept and filed."""
    if drawer.cut is None:
        raise Refused(f"{drawer.id} is a print: a printed piece is read by its plan's features")
    with _LOCK:
        kept = cut_measured.measure(drawer.cut, dict(sizes))
        tolerance = tolerance_of(drawer.part, None)
        designed = {f.name: f.size for f in drawer.cut.features}
        drawer = _file(
            drawer,
            "measured",
            cut_measured.said(kept.measurements[-1]),
            made=cut_measured.SETTING,
            readings={k: [v] for k, v in sizes.items() if v is not None},
            checked=[
                _check(k, designed[k], [v], tolerance)
                for k, v in sizes.items()
                if v is not None and k in designed
            ],
        )
    return drawer, kept


def looked(
    drawer: Drawer, seen: Mapping[str, int], where: Mapping[str, str], note: str = ""
) -> Tuple[Drawer, tuning.TuningDocument, tuning.Look]:
    """A printed piece read by eye: the printer's next look, filed. On a print that
    stopped, a fault seen and placed nowhere is placed where the print stopped."""
    if drawer.slice is None:
        raise Refused(f"{drawer.id} is a cut: faults are read on a printed piece")
    stopped = drawer.job.stopped if drawer.job is not None else None
    if stopped is not None:
        where = {
            **{f: stopped.said() for f, s in seen.items() if s > 0},
            **{k: v for k, v in where.items() if v},
        }
    with _LOCK:
        doc, look = tuning.add_look(drawer.slice, dict(seen), dict(where), note)
        drawer = _file(
            drawer,
            "look",
            tuning.said_look(look),
            made=look.id,
            seen=[SeenFiled(fault=s.fault, severity=s.severity, where=s.where) for s in look.seen],
            note=note,
        )
    return drawer, doc, look


def noted(drawer: Drawer, note: str) -> Drawer:
    """A note on the piece, filed: it changes no machine's settings."""
    note = (note or "").strip()
    if not note:
        raise Refused("a note says something")
    if len(note) > NOTE_MOST:
        raise Refused(f"a note says at most {NOTE_MOST} characters")
    with _LOCK:
        return _file(drawer, "note", note, note=note)


def undone(part: str, site: str, printer: str, applies: tuning.AppliesTo, made: str) -> None:
    """A printer's turn or look ``made`` was undone: the newest filing that made it says
    so. An id comes back after an undo, so an older filing of the same id is another's."""
    with _LOCK:
        for drawer in drawers(part) if PART.match(part or "") else []:
            if (
                drawer.slice is None
                or drawer.machine.site != site
                or drawer.machine.path != printer
            ):
                continue
            if (drawer.filament, drawer.process) != (applies.filament, applies.process):
                continue
            hit = next(
                (f for f in reversed(drawer.filed) if f.made == made and f.undone is None), None
            )
            if hit is not None:
                hit.undone = datetime.now(timezone.utc)
                _write(drawer)
                return
