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
- ``POST /slicer/slice`` ``{part, port | site + printer | printer, slicer}``: slice
  a part or a made piece for a printer (a task). ``part`` is a node's path in
  the printer's site, as ``GET /jobs/choices`` lists them for the Print card --
  a part standing there or a piece made from a picture -- or a registered
  part's name. The printer is the one ``port``'s pin stands under, else
  ``site``'s node at ``printer`` (with none named, the site's one printer), else
  the printer part ``printer`` names (or the one that keeps a profile). What it names is checked before the task
  starts, so a part or printer that is not one is a 422 at once, and a slicer
  that is not installed a 503.
- ``GET /slicer/tasks/{id}?since=N``: the task, and ``slice``: null while it
  runs; then ``{"ok": true, "record": ...}`` -- the kept file (``file_id``, the
  Print card's), each value and where it came from, the slicer's estimate,
  its errors and warnings by line, where the moves reach -- or ``{"ok":
  false, "error": ..., "messages": [...], "settings": [...]}``.
- ``POST /slicer/tasks/{id}/cancel``.
- ``GET /slicer/slices``, ``GET /slicer/slices/{file_id}``: the slices whose
  files the Print card still keeps.

Slices run one at a time on a task runner of their own, so a slice never waits
for a flash, nor a flash for a slice. Slicing writes files only: no route here
opens a serial port or sends anything to a printer.
"""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.routing import APIRoute
from pydantic import BaseModel, Field

from ..firmware.models import Port
from ..firmware.tasks import Running, TaskBusy, TaskRunner
from . import compose, service
from .models import SliceRecord, SlicerStatus
from .modules import NotInstalled, SlicerError, chosen_id, get_module, modules, reset_modules
from .profiles import printers

SITE_NAME = r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$"
NODE_PATH = r"^[A-Za-z0-9_][A-Za-z0-9_.\-]{0,199}$"
MODULE_ID = r"^[a-z][a-z0-9_-]{0,31}$"


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
        body.part, port=body.port, site=body.site, printer=body.printer
    )
    module = get_module(chosen_id(body.slicer, printer.profile))
    status = module.status()
    if not status.ok:
        raise NotInstalled(f"{module.label}: " + "; ".join(status.problems))
    title = f"Slice {target.made.name} for {printer.at.name}"

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
