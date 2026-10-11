"""Jobs: one operation a machine performs on a part, and the record of it.

A job is a print on a printer today; a cut on a mill or a laser would be one the
same way. Each records its kind; the machine (its kind, its port, the board's
own identity when it is known, and the node it is pinned to, if any); the site
and the part it makes, when known (a piece made from a picture with that picture
and its camera); the input file it ran (its name, size and SHA-256); when it
started and finished; how it ended (``running``, ``done``,
``cancelled`` or ``failed``, with a reason); and how far it got.

**What a machine offers** is its kinds of operation. ``register`` adds one
(an ``Operation``) and ``operations(machine)`` lists what a kind of machine
offers: a printer offers ``print``. A mill would register ``mill`` the same
way, and its card would start ``mill`` jobs. The machine's own module does the
work -- ``firmware/devices.py``'s ``PrintJob`` streams a print -- and hands the
job here when it begins (``begin``) and when it ends (``end``).

**The store** is the state folder's ``jobs/``, one JSON file per job, readable
by this account alone, as the print records were. A job is written when it
begins and again when it ends; in between, a read takes it from the machine's
own thread (``begin``'s ``live``), so its progress costs no writes. A job
written as running that no thread of this process holds was running when the
server stopped: it reads as failed and says so, and its file is left as it is.

**The print records kept before jobs** (``prints/records/*.json``) are carried
over on the first read after they appear: each becomes a print job with the
record's id -- its port, its file's name and kept id, when it started and
finished, its outcome, its error as the reason, the lines sent of the total as
its progress, the firmware and the tail of what the firmware said. The file's
size comes from the kept file's description when that is still there; the
site, the part and the hash were never recorded and stay empty. The records are
left where they are, and nothing writes there any more.

**Listeners** (``LISTENERS``) hear each job as it begins and as it ends; the
site layer registers one that marks the machine's node busy while a job runs
on it, so a running job, not a hand-typed one, is what makes a printer busy.
**Where a machine stands** -- the site and node its port is pinned to, and the
parts a job there can name -- is asked of ``PLACES``, which the site layer
fills. This module imports nothing from the site layer or the firmware package
when it is imported.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Literal, Optional, Tuple

from pydantic import BaseModel, Field

OUTCOMES: Tuple[str, ...] = ("running", "done", "cancelled", "failed")
Outcome = Literal["running", "done", "cancelled", "failed"]

# What a job's id may be: it names the job's file.
JOB_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.\-]{0,119}$")

# What a job that was running when the server stopped says.
STOPPED = "the server stopped while it ran; how it ended was not recorded"


# --- the job ---------------------------------------------------------------------------


class JobMachine(BaseModel):
    """The machine a job ran on."""

    kind: str  # the kind of machine: "printer"
    port: str
    identity: Optional[str] = None  # the board's own (a MAC, a USB serial number), when known
    path: Optional[str] = None  # the node its port is pinned to, in the job's site


class JobInput(BaseModel):
    """The file a job ran."""

    name: str
    size: Optional[int] = None  # bytes
    sha256: Optional[str] = None
    file_id: Optional[str] = None  # the kept file it was, while it is kept


class JobPart(BaseModel):
    """The part or piece a job makes: a node of the job's site. A piece made from a
    picture also carries the picture and the camera that took it, as they were
    when the job began: kept in the job's record, not shown in its row."""

    path: str
    name: str  # the part it is built from, or the piece's own name
    picture: Optional[str] = None  # a made piece's picture, under the picture root
    camera: Optional[str] = None  # the camera that took that picture, when one did


class JobFacts(BaseModel):
    """A job without the machine's own words: what a list of jobs carries."""

    id: str
    kind: str
    machine: JobMachine
    site: Optional[str] = None
    part: Optional[JobPart] = None
    input: JobInput
    started_at: datetime
    finished_at: Optional[datetime] = None
    outcome: Outcome = "running"
    reason: Optional[str] = None
    progress: float = 0.0  # 0 to 1
    # What the kind adds: a print's lines sent and their total, its stage, the firmware.
    detail: Dict[str, Any] = Field(default_factory=dict)

    @property
    def running(self) -> bool:
        return self.outcome == "running"


class Job(JobFacts):
    """One operation a machine performs on a part."""

    log: List[str] = Field(default_factory=list)  # the tail of what the machine said


def new_id(started: datetime, port: str) -> str:
    """A job's id: when it started, to the millisecond, and the port it ran on."""
    slug = re.sub(r"[^A-Za-z0-9]+", "_", port).strip("_")
    return f"{started:%Y%m%dT%H%M%S}.{started.microsecond // 1000:03d}-{slug}"


# --- what a machine offers ------------------------------------------------------------------


@dataclass(frozen=True)
class Operation:
    """A kind of job, and the kind of machine that offers it."""

    kind: str  # the job's kind: "print"
    machine: str  # the kind of machine that offers it: "printer"
    label: str  # what a person calls it: "Print"
    inputs: Tuple[str, ...] = ()  # the file suffixes it runs
    busy: Optional[str] = None  # the status a running job gives its machine's node


_OPERATIONS: Dict[str, Operation] = {}


def register(operation: Operation) -> Operation:
    """Offer ``operation`` on its kind of machine. A kind is one machine's."""
    had = _OPERATIONS.get(operation.kind)
    if had is not None and had != operation:
        raise ValueError(f"{operation.kind!r} is already offered by a {had.machine}")
    _OPERATIONS[operation.kind] = operation
    return operation


def operation(kind: str) -> Optional[Operation]:
    return _OPERATIONS.get(kind)


def operations(machine: Optional[str] = None) -> List[Operation]:
    """What a kind of machine offers, or every operation, in the order registered."""
    return [op for op in _OPERATIONS.values() if machine is None or op.machine == machine]


def machine_kinds() -> List[str]:
    """Every kind of machine that offers something, in the order first registered."""
    return list(dict.fromkeys(op.machine for op in _OPERATIONS.values()))


PRINT = register(
    Operation(
        kind="print",
        machine="printer",
        label="Print",
        inputs=(".gcode", ".gco", ".g"),
        busy="printing",
    )
)


# --- where a machine stands ------------------------------------------------------------------


class Place(BaseModel):
    """Where a machine's port is pinned, and the parts a job there can name."""

    site: str
    path: str
    parts: List[JobPart] = Field(default_factory=list)


# Each answers where the machine on a port stands, or None. The site layer
# (api.py) registers one; the first answer wins.
PLACES: List[Callable[[str], Optional[Place]]] = []


def place_of(port: str) -> Optional[Place]:
    for answer in PLACES:
        place = answer(port)
        if place is not None:
            return place
    return None


def part_at(place: Optional[Place], path: Optional[str]) -> Optional[JobPart]:
    """The part ``path`` names where the machine stands; ``None`` for none named.

    Raises ``ValueError`` for a part named on a machine pinned nowhere, or for
    one that is not a part or piece of its site.
    """
    if not path:
        return None
    if place is None:
        raise ValueError("this machine is pinned in no site, so no part of one can be named")
    found = next((p for p in place.parts if p.path == path), None)
    if found is None:
        raise ValueError(f"{path!r} is not a part or piece of {place.site}")
    return found


# --- the store --------------------------------------------------------------------------


# The machines' threads, by job id: a running job's freshest state.
_LIVE: Dict[str, Callable[[], Job]] = {}
LISTENERS: List[Callable[[Job], None]] = []
_LOCK = threading.Lock()


def _state_dir() -> Path:
    from .firmware.devices import state_dir

    return state_dir()


def jobs_dir() -> Path:
    return _state_dir() / "jobs"


def _write(job: Job) -> None:
    from .firmware.devices import private_folder

    folder = private_folder(jobs_dir())
    # Whole or not at all: a reader never meets half a job.
    fd, tmp = tempfile.mkstemp(dir=folder, prefix=".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as out:
            out.write(job.model_dump_json(indent=2))
        os.replace(tmp, folder / f"{job.id}.json")
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def _tell(job: Job) -> None:
    for listener in LISTENERS:
        listener(job)


def begin(job: Job, live: Callable[[], Job]) -> Job:
    """A machine began ``job``: written as running; ``live`` answers it fresh until it ends."""
    if operation(job.kind) is None:
        kinds = ", ".join(op.kind for op in operations()) or "none"
        raise ValueError(f"no machine offers {job.kind!r}; the kinds are {kinds}")
    if not JOB_ID_RE.match(job.id):
        raise ValueError(f"{job.id!r} is not a job id")
    if not job.running:
        raise ValueError("a job begins running")
    with _LOCK:
        _write(job)
        _LIVE[job.id] = live
    _tell(job)
    return job


def end(job: Job) -> Job:
    """A machine ended ``job``: written as it ended, and no longer read from its thread."""
    if job.running:
        raise ValueError("a job ends done, cancelled or failed")
    with _LOCK:
        _write(job)
        _LIVE.pop(job.id, None)
    _tell(job)
    return job


def _as_read(job: Job) -> Job:
    live = _LIVE.get(job.id)
    if live is not None:
        fresh = live()
        if fresh is not None:
            return fresh
    if job.running:
        return job.model_copy(update={"outcome": "failed", "reason": STOPPED})
    return job


def _read(path: Path) -> Optional[Job]:
    try:
        return Job(**json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError, TypeError):
        return None


def get(job_id: str) -> Optional[Job]:
    """One job, with what its machine said, or ``None``."""
    if not JOB_ID_RE.match(job_id or ""):
        return None
    _carry_over_print_records()
    job = _read(jobs_dir() / f"{job_id}.json")
    return _as_read(job) if job is not None else None


def _same_machine(job: JobFacts, port: str, identity: Optional[str]) -> bool:
    """A machine is the board's own identity when both sides know it, else its port."""
    if identity and job.machine.identity:
        return job.machine.identity == identity
    return job.machine.port == port


def list_jobs(
    site: Optional[str] = None,
    machine: Optional[str] = None,
    identity: Optional[str] = None,
    kind: Optional[str] = None,
) -> List[Job]:
    """Jobs, running ones first, then the newest first: of a site, of the machine on a
    port (``identity`` is the board's own, when known), of a kind."""
    _carry_over_print_records()
    folder = jobs_dir()
    found: List[Job] = []
    if folder.is_dir():
        for path in folder.glob("*.json"):
            job = _read(path)
            if job is None:
                continue
            job = _as_read(job)
            if site is not None and job.site != site:
                continue
            if machine is not None and not _same_machine(job, machine, identity):
                continue
            if kind is not None and job.kind != kind:
                continue
            found.append(job)
    found.sort(key=lambda j: j.started_at, reverse=True)
    found.sort(key=lambda j: not j.running)  # stable: the running ones first, newest first
    return found


# --- the print records kept before jobs ----------------------------------------------------


def _carry_over_print_records() -> None:
    """Each print record not yet a job becomes one (see the module's docstring)."""
    records = _state_dir() / "prints" / "records"
    if not records.is_dir():
        return
    for path in records.glob("*.json"):
        if (jobs_dir() / path.name).is_file():
            continue
        job = _from_print_record(path)
        if job is not None:
            with _LOCK:
                if not (jobs_dir() / path.name).is_file():
                    _write(job)


def _from_print_record(path: Path) -> Optional[Job]:
    from .firmware.models import PrintRecord

    try:
        record = PrintRecord(**json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError, TypeError):
        return None
    if record.id != path.stem or not JOB_ID_RE.match(record.id):
        return None
    size = None
    kept = _state_dir() / "prints" / f"{record.file_id}.json"
    if JOB_ID_RE.match(record.file_id) and kept.is_file():
        try:
            size = int(json.loads(kept.read_text(encoding="utf-8"))["size"])
        except (OSError, ValueError, TypeError, KeyError):
            size = None
    outcome = record.outcome if record.outcome in ("done", "cancelled", "failed") else "failed"
    detail: Dict[str, Any] = {"sent": record.sent, "total": record.total}
    if record.firmware:
        detail["firmware"] = record.firmware
    return Job(
        id=record.id,
        kind=PRINT.kind,
        machine=JobMachine(kind=PRINT.machine, port=record.port),
        input=JobInput(name=record.name, size=size, file_id=record.file_id),
        started_at=record.at,
        finished_at=record.finished or record.at,
        outcome=outcome,
        reason=record.error,
        progress=(record.sent / record.total) if record.total else 0.0,
        detail=detail,
        log=record.lines,
    )
