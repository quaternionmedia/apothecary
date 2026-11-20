"""``/slicer`` routes: the slicer's status and install, a slice, and the slices kept.

Every route that runs the slicer answers a task at once (202), as the firmware
routes do; the page polls ``GET /slicer/tasks/{id}?since=N`` for new log lines,
and the task carries the slice's answer once it ends:

- ``GET /slicer/status``: each slicer module -- what it slices, its program and
  version, the pinned release, its problems -- which one a slice uses, the
  printers that keep a slicer profile, and the pieces a slice can be composed
  from (the start of a print, the filament, a word's print settings), each
  saying what it does and whether it is a stub.
- ``POST /slicer/install`` ``{force, slicer}``: install the pinned OrcaSlicer, or
  the module named (a task).
- ``POST /slicer/slice`` ``{part, port | site + printer | printer, slicer, variant}``: slice
  a part or a made piece for a printer (a task). ``part`` is a node's path in
  the printer's site, as ``GET /jobs/choices`` lists them for the Print card --
  a part standing there or a piece made from a picture -- or a registered
  part's name. The printer is the one ``port``'s pin stands under, else
  ``site``'s node at ``printer`` (with none named, the site's one printer), else
  the printer part ``printer`` names (or the one that keeps a profile). What it names is checked before the task
  starts, so a part or printer that is not one is a 422 at once, and a slicer
  that is not installed a 503. ``variant``, a part's cached variant (the key
  ``/parts/{name}/stl/generate`` answered), is what is sliced instead of the
  part's own STL, and the record's ``made`` names it (``variant``, its
  ``params``, its ``draft``); a variant the cache does not have is a 422.
- ``GET /slicer/tasks/{id}?since=N``: the task, and ``slice``: null while it
  runs; then ``{"ok": true, "record": ...}`` -- the kept file (``file_id``, the
  Print card's), each value and where it came from, the slicer's estimate,
  its errors and warnings by line, where the moves reach -- or ``{"ok":
  false, "error": ..., "messages": [...], "settings": [...]}``.
- ``POST /slicer/tasks/{id}/cancel``.
- ``GET /slicer/slices``, ``GET /slicer/slices/{file_id}``: the slices whose
  files the Print card still keeps.
- ``POST /slicer/slices/{file_id}/measured`` ``{readings, resolution, repeatability,
  assume}``: the piece the printer made from that slice, read with calipers -- each
  feature its plan names (``readings``: a name and its values), the caliper's step and
  the person's repeatability in mm -- kept as the next turn of that printer's tuning
  for the slice's filament and process (``tuning.py``): solved, and each setting's
  change proposed, nothing applied. A reading that is not of that piece is a 422
  saying why, and nothing is kept.
- ``GET /slicer/tuning?site=&printer=``: the printer's tuning documents, one per
  filament and process, each with its terms' trends.
- ``POST /slicer/tuning/apply``, ``POST /slicer/tuning/undo`` ``{site, printer,
  filament, process}``: the last turn's changes taken into the printer's next
  slices; the last turn dropped, with what it applied.
- ``GET /slicer/tuning/schema``, ``POST /slicer/tuning/validate``: ``print/tuning/1``'s
  JSON Schema, and a document read back.

Slices run one at a time on a task runner of their own, so a slice never waits
for a flash, nor a flash for a slice. Slicing writes files only: no route here
opens a serial port or sends anything to a printer.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Union

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.routing import APIRoute
from pydantic import BaseModel, Field

from ..firmware.models import Port
from ..firmware.tasks import Running, TaskBusy, TaskRunner
from . import compose, service, tuning
from .models import SliceRecord, SlicerStatus
from .modules import NotInstalled, SlicerError, chosen_id, get_module, modules, reset_modules
from .profiles import printers

SITE_NAME = r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$"
NODE_PATH = r"^[A-Za-z0-9_][A-Za-z0-9_.\-]{0,199}$"
MODULE_ID = r"^[a-z][a-z0-9_-]{0,31}$"
VARIANT_KEY = r"^[0-9a-f]{24}$"


class SlicerRoute(APIRoute):
    """The seam's exceptions, one status each: not installed (503), a task already
    running (409), a request that cannot be done as asked (422)."""

    def get_route_handler(self):
        handler = super().get_route_handler()

        async def answer(request: Request):
            try:
                return await handler(request)
            except TaskBusy as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc
            except NotInstalled as exc:
                raise HTTPException(status_code=503, detail=str(exc)) from exc
            except (SlicerError, ValueError) as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc

        return answer


router = APIRouter(prefix="/slicer", tags=["slicer"], route_class=SlicerRoute)

_RUNNER: Optional[TaskRunner] = None


def get_runner() -> TaskRunner:
    """The slices' own task runner: one slice at a time, beside the firmware's."""
    global _RUNNER
    if _RUNNER is None:
        _RUNNER = TaskRunner()
    return _RUNNER


class InstallBody(BaseModel):
    force: bool = False
    slicer: str = Field("orcaslicer", pattern=MODULE_ID)  # which slicer module


class SliceRequest(BaseModel):
    part: str = Field(..., pattern=NODE_PATH)
    port: Optional[Port] = None
    site: Optional[str] = Field(None, pattern=SITE_NAME)
    printer: Optional[str] = Field(None, pattern=NODE_PATH)
    slicer: Optional[str] = Field(None, pattern=MODULE_ID)
    # A cached variant of the part (its key, as generate answered it): the
    # variant a page draws is what is sliced, and the record names it.
    variant: Optional[str] = Field(None, pattern=VARIANT_KEY)


class MeasuredRequest(BaseModel):
    # Each feature read, by the name the piece's plan gives it: one value in mm, or its
    # repeated readings.
    readings: Dict[str, Union[float, List[float]]] = Field(..., max_length=64)
    resolution: float = Field(tuning.RESOLUTION, gt=0, le=1)  # the caliper's step, mm
    repeatability: Optional[float] = Field(None, ge=0, le=1)  # a person's, as stated, mm
    # Terms held at a value a person states rather than solved: said as assumed.
    assume: Dict[str, float] = Field(default_factory=dict, max_length=8)


class TuningRequest(BaseModel):
    site: str = Field(..., pattern=SITE_NAME)
    printer: str = Field(..., pattern=NODE_PATH)
    filament: str = Field(..., min_length=1, max_length=200)
    process: str = Field(..., min_length=1, max_length=200)

    def applies(self) -> tuning.AppliesTo:
        return tuning.AppliesTo(filament=self.filament, process=self.process)


class Piece(BaseModel):
    kind: str  # start, filament or declared
    id: str
    does: str
    stub: bool  # exists, says what it will do, and is not chosen


class StatusAnswer(BaseModel):
    slicers: List[SlicerStatus]
    chosen: str
    printers: List[str]
    pieces: List[Piece]  # what a slice can be composed from (compose.py)


def _snapshot(task, since: int = 0) -> dict:
    data = task.snapshot(since=since)
    data["slice"] = service.answer_of(task.id)
    return data


@router.get("/status", response_model=StatusAnswer)
def slicer_status():
    """Each slicer module, the one a slice uses, and the printers that keep a profile."""
    picked = chosen_id()
    found = []
    for module in modules():
        status = module.status()
        status.chosen = module.id == picked
        found.append(status)
    return StatusAnswer(
        slicers=found,
        chosen=picked,
        printers=printers(),
        pieces=[Piece(**p.as_json()) for p in compose.pieces()],
    )


@router.post("/install", status_code=202)
def slicer_install(body: InstallBody):
    """Install a slicer module's pinned release into the tools dir (a task):
    OrcaSlicer's, unless another module is named."""
    module = get_module(body.slicer)

    def work(running: Running) -> None:
        module.install(running.log, force=body.force)
        reset_modules()

    return _snapshot(get_runner().run_staged("slicer-install", f"Install {module.label}", work))


@router.post("/slice", status_code=202)
def slicer_slice(body: SliceRequest):
    """Slice a part or a made piece for a printer (a task); see the module docstring."""
    target, printer = service.resolve(
        body.part, port=body.port, site=body.site, printer=body.printer, variant=body.variant
    )
    module = get_module(chosen_id(body.slicer, printer.profile))
    status = module.status()
    if not status.ok:
        raise NotInstalled(f"{module.label}: " + "; ".join(status.problems))
    named = f"{target.made.name} ({target.made.variant})" if target.made.variant else None
    title = f"Slice {named or target.made.name} for {printer.at.name}"

    def work(running: Running) -> None:
        try:
            record = service.slice_into(target, printer, running, slicer=module.id)
        except service.SliceFailed as exc:
            service.remember(
                running.task.id,
                {
                    "ok": False,
                    "error": str(exc),
                    "messages": [m.model_dump(mode="json") for m in exc.messages],
                    "settings": [s.model_dump(mode="json") for s in exc.settings],
                },
            )
            raise
        except SlicerError as exc:
            service.remember(
                running.task.id, {"ok": False, "error": str(exc), "messages": [], "settings": []}
            )
            raise
        service.remember(running.task.id, {"ok": True, "record": record.model_dump(mode="json")})

    return _snapshot(get_runner().run_staged("slice", title, work))


@router.get("/tasks")
def slicer_tasks():
    return [_snapshot(t, since=len(t.lines)) for t in get_runner().list()]


@router.get("/tasks/{task_id}")
def slicer_task(task_id: str, since: int = Query(0, ge=0)):
    task = get_runner().get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="no such task")
    return _snapshot(task, since=since)


@router.post("/tasks/{task_id}/cancel")
def slicer_task_cancel(task_id: str):
    if not get_runner().cancel(task_id):
        raise HTTPException(status_code=409, detail="the task is not running")
    return _snapshot(get_runner().get(task_id))


@router.get("/slices", response_model=List[SliceRecord])
def slicer_slices():
    """The slices whose G-code the Print card still keeps, newest first."""
    return service.records()


@router.get("/slices/{file_id}", response_model=SliceRecord)
def slicer_slice_record(file_id: str):
    """The slice that made the kept file ``file_id``."""
    record = service.get_record(file_id)
    if record is None:
        raise HTTPException(status_code=404, detail="no slice made that file, or it is not kept")
    return record


@router.post("/slices/{file_id}/measured")
def slicer_slice_measured(file_id: str, body: MeasuredRequest):
    """The piece the slice ``file_id`` made, read: kept as the next turn of its printer's
    tuning, solved, and each setting's change proposed; nothing is applied."""
    record = service.get_record(file_id)
    if record is None:
        raise HTTPException(status_code=404, detail="no slice made that file, or it is not kept")
    values = {
        name: [v] if isinstance(v, (int, float)) else list(v) for name, v in body.readings.items()
    }
    for name, read in values.items():
        if len(read) > 20 or any(not (0 < v <= 2000) for v in read):
            raise HTTPException(status_code=422, detail=f"{name}: up to 20 sizes, each over 0 mm")
    try:
        doc, turn = tuning.add_turn(
            record,
            values,
            tuning.Instrument(resolution=body.resolution, repeatability=body.repeatability),
            body.assume,
        )
    except tuning.Refused as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _tuned(doc) | {"turn": turn.id, "said": tuning.said(turn)}


def _tuned(doc: "tuning.TuningDocument") -> dict:
    return {
        "document": doc.model_dump(mode="json", by_alias=True),
        "trends": {
            key: {"term": t.term, "state": t.state, "stop": t.stop, "said": t.said}
            for key, t in tuning.trends(doc).items()
        },
    }


@router.get("/tuning")
def slicer_tuning(
    site: str = Query(..., pattern=SITE_NAME), printer: str = Query(..., pattern=NODE_PATH)
):
    """The tuning documents kept for ``printer`` in ``site``, one per filament and process."""
    return {"documents": [_tuned(d) for d in tuning.documents(site, printer)]}


@router.post("/tuning/apply")
def slicer_tuning_apply(body: TuningRequest):
    """The last turn's proposed changes, taken into the printer's next slices."""
    try:
        doc, changes = tuning.apply(body.site, body.printer, body.applies())
    except tuning.Refused as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _tuned(doc) | {"applied": [c.model_dump(mode="json") for c in changes]}


@router.post("/tuning/undo")
def slicer_tuning_undo(body: TuningRequest):
    """The last turn dropped, with what it applied."""
    try:
        doc, gone = tuning.undo(body.site, body.printer, body.applies())
    except tuning.Refused as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _tuned(doc) | {"undone": gone.id}


@router.get("/tuning/schema")
def slicer_tuning_schema():
    """``print/tuning/1``'s JSON Schema."""
    return tuning.TuningDocument.model_json_schema(by_alias=True)


@router.post("/tuning/validate")
def slicer_tuning_validate(body: dict):
    """A tuning document read back: 422 with the first figure that rests on nothing."""
    try:
        doc = tuning.TuningDocument.model_validate(body)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"ok": True, "turns": len(doc.turns), "settings": sorted(doc.settings)}
