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
import re
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Literal, Mapping, Optional, Sequence, Tuple

from pydantic import BaseModel, ConfigDict, Field

from . import jobs
from .cam import measured as cut_measured
from .cam.models import CutRecord
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


class Ran(BaseModel):
    """The job that made the piece: as it began, and as it ended."""

    id: str
    outcome: str = "running"
    reason: Optional[str] = None
    started_at: datetime
    finished_at: Optional[datetime] = None


class SeenFiled(BaseModel):
    fault: str
    severity: int = Field(..., ge=0, le=3)
    where: str = ""


class Filed(BaseModel):
    """One thing said of the piece: what was read, what was seen, or a note."""

    id: str = Field(..., pattern=FILED_ID)
    at: datetime
    kind: Kind
    said: str
    # What it made: a printer's turn or look ("turn-3", "look-2"), or the router's allowance.
    made: Optional[str] = None
    readings: Dict[str, List[float]] = Field(default_factory=dict)  # mm, by feature
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
    if not re.match(DRAWER_ID, drawer_id or ""):
        return None
    path = _folder(part) / f"{drawer_id}.json"
    with _LOCK:
        return _read(path) if path.is_file() else None


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


def measured(
    drawer: Drawer,
    readings: Mapping[str, Sequence[float]],
    instrument: Optional[tuning.Instrument] = None,
    assumed: Optional[Mapping[str, float]] = None,
) -> Tuple[Drawer, tuning.TuningDocument, tuning.Turn]:
    """A printed piece read with calipers: the printer's next turn of its tuning, filed."""
    if drawer.slice is None:
        raise Refused(f"{drawer.id} is a cut: a cut piece is measured by its sizes")
    with _LOCK:
        doc, turn = tuning.add_turn(drawer.slice, readings, instrument, assumed)
        drawer = _file(
            drawer,
            "measured",
            tuning.said(turn),
            made=turn.id,
            readings={k: list(v) for k, v in readings.items()},
        )
    return drawer, doc, turn


def measured_cut(
    drawer: Drawer, sizes: Mapping[str, Optional[float]]
) -> Tuple[Drawer, cut_measured.Correction]:
    """A cut piece measured: the router's tool allowance it makes, kept and filed."""
    if drawer.cut is None:
        raise Refused(f"{drawer.id} is a print: a printed piece is read by its plan's features")
    with _LOCK:
        kept = cut_measured.measure(drawer.cut, dict(sizes))
        drawer = _file(
            drawer,
            "measured",
            cut_measured.said(kept.measurements[-1]),
            made=cut_measured.SETTING,
            readings={k: [v] for k, v in sizes.items() if v is not None},
        )
    return drawer, kept


def looked(
    drawer: Drawer, seen: Mapping[str, int], where: Mapping[str, str], note: str = ""
) -> Tuple[Drawer, tuning.TuningDocument, tuning.Look]:
    """A printed piece read by eye: the printer's next look, filed."""
    if drawer.slice is None:
        raise Refused(f"{drawer.id} is a cut: faults are read on a printed piece")
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
