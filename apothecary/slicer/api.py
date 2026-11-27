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
- ``POST /slicer/slices/{file_id}/seen`` ``{seen, where, note}``: the same piece read
  by eye -- each fault seen (``seen``: a fault's id and its severity, 0 none to 3
  bad; ``where``: where one shows) -- kept as the next look of that printer's tuning:
  the one setting's change it implies proposed, nothing applied
  (apothecary/print_faults.py).
- ``GET /slicer/faults``: the faults a look reads, each with what it looks like, the
  settings that govern it in the order they are tried, and what to look at when none
  does; and the severities.
- ``GET /slicer/tuning?site=&printer=``: the printer's tuning documents, one per
  filament and process, each with its terms' trends and each fault's over its looks.
- ``POST /slicer/tuning/apply``, ``POST /slicer/tuning/undo`` ``{site, printer,
  filament, process}``: the last turn's or look's changes taken into the printer's
  next slices; the last turn or look dropped, with what it applied.
- ``GET /slicer/filaments?site=&printer=``: the filament loaded on that printer, and
  every filament it can load (the slicer's profiles of its vendor that fit its
  machine); ``POST /slicer/filaments/loaded`` ``{site, printer, filament, note}``:
  another loaded, its next slices made with it (slicer/filaments.py).
- ``POST /slicer/first-layer/offset`` ``{site, printer, offset, note}``: the printer's
  first-layer offset kept, mm, negative lower: its next slices are made with it, as
  OrcaSlicer's ``z_offset`` (slicer/first_layer_offset.py). ``GET /slicer/first-layer``
  says the one kept, as ``offset``.
- ``GET /slicer/tuning/schema``, ``POST /slicer/tuning/validate``: ``print/tuning/1``'s
  JSON Schema, and a document read back.

Slices run one at a time on a task runner of their own, so a slice never waits
for a flash, nor a flash for a slice. Slicing writes files only: no route here
opens a serial port or sends anything to a printer.
"""

from __future__ import annotations

from typing import Dict, List, Literal, Optional, Union

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.routing import APIRoute
from pydantic import BaseModel, Field

from .. import cabinet
from .. import print_faults as pf
from ..firmware.models import Port
from ..firmware.tasks import Running, TaskBusy, TaskRunner
from . import compose, filaments, first_layer_offset, service, tuning
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
    # The start's levelling for this slice over the printer's profile (compose.levelled):
    # "home" none, or a levelling piece; none said is the profile's own.
    levelling: Optional[Literal["home", "stored-mesh", "probe-each-print"]] = None
    # How its first layer holds over what the part declares (profiles.ADHESIONS); none
    # said is the part's own.
    adhesion: Optional[Literal["brim", "raft", "none"]] = None


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


class SeenRequest(BaseModel):
    # Each fault seen on the piece, by its id: 0 none, 1 slight, 2 clear, 3 bad.
    seen: Dict[str, int] = Field(..., max_length=32)
    # Where a fault shows, in words: a height, a feature.
    where: Dict[str, str] = Field(default_factory=dict, max_length=32)
    note: str = Field("", max_length=2000)


class FilamentRequest(BaseModel):
    site: str = Field(..., pattern=SITE_NAME)
    printer: str = Field(..., pattern=NODE_PATH)
    filament: str = Field(..., min_length=1, max_length=200)
    note: str = Field("", max_length=200)  # the spool: its brand, its colour


class OffsetRequest(BaseModel):
    site: str = Field(..., pattern=SITE_NAME)
    printer: str = Field(..., pattern=NODE_PATH)
    offset: float  # mm, negative lower: first_layer_offset.keep bounds it
    note: str = Field("", max_length=first_layer_offset.NOTE_MOST)  # what the square showed


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
    asked, by = service.asked_levelling(target, body.levelling)
    if asked is not None:
        # A levelling whose precondition fails is refused now, not once the task runs.
        levelled = compose.levelled(printer.profile, asked, by)
        compose.chosen(compose.START, levelled.start.modules, levelled, printer.at.port)
    named = f"{target.made.name} ({target.made.variant})" if target.made.variant else None
    title = f"Slice {named or target.made.name} for {printer.at.name}"

    def work(running: Running) -> None:
        try:
            record = service.slice_into(
                target,
                printer,
                running,
                slicer=module.id,
                levelling=body.levelling,
                adhesion=body.adhesion,
            )
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


@router.get("/first-layer")
def slicer_first_layer(
    part: str = Query(..., pattern=NODE_PATH),
    port: Optional[Port] = None,
    site: Optional[str] = Query(None, pattern=SITE_NAME),
    printer: Optional[str] = Query(None, pattern=NODE_PATH),
    variant: Optional[str] = Query(None, pattern=VARIANT_KEY),
):
    """How a slice of ``part`` for the printer named as a slice names it levels and
    holds with neither asked: the part's own, else the printer's (service.first_layer);
    and the first-layer offset its slices take (``offset``, first_layer_offset.answer)."""
    target, at = service.resolve(part, port=port, site=site, printer=printer, variant=variant)
    return service.first_layer(target, at.profile) | {
        "offset": first_layer_offset.answer(at.profile, at.at.site, at.at.path)
    }


@router.post("/first-layer/offset")
def slicer_first_layer_offset(body: OffsetRequest):
    """The printer's first-layer offset kept: its next slices are made with it."""
    profile = _printer_profile(body.site, body.printer)
    try:
        first_layer_offset.keep(profile, body.site, body.printer, body.offset, body.note)
    except first_layer_offset.Refused as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return first_layer_offset.answer(profile, body.site, body.printer)


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
    instrument = tuning.Instrument(resolution=body.resolution, repeatability=body.repeatability)
    drawer = None
    try:
        # A part's piece is filed in its drawer (apothecary/cabinet.py), which makes the turn.
        if cabinet.part_of_slice(record):
            drawer, doc, turn = cabinet.measured(
                cabinet.for_slice(record), values, instrument, body.assume
            )
        else:
            doc, turn = tuning.add_turn(record, values, instrument, body.assume)
    except (tuning.Refused, cabinet.Refused) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if turn is None:  # a check alone, filed in the drawer: the last turn already reads it
        at = record.printer
        doc = tuning.load(at.site, at.path, tuning.applies_of(record), at.part)
        return _tuned(doc) | {"turn": None, "said": drawer.filed[-1].said, **_filed_in(drawer)}
    return _tuned(doc) | {"turn": turn.id, "said": tuning.said(turn), **_filed_in(drawer)}


@router.post("/slices/{file_id}/seen")
def slicer_slice_seen(file_id: str, body: SeenRequest):
    """The piece the slice ``file_id`` made, read by eye: kept as the next look of its
    printer's tuning, and the one setting's change it implies proposed; nothing is
    applied."""
    record = service.get_record(file_id)
    if record is None:
        raise HTTPException(status_code=404, detail="no slice made that file, or it is not kept")
    drawer = None
    try:
        if cabinet.part_of_slice(record):
            drawer, doc, look = cabinet.looked(
                cabinet.for_slice(record), body.seen, body.where, body.note
            )
        else:
            doc, look = tuning.add_look(record, body.seen, body.where, body.note)
    except (tuning.Refused, cabinet.Refused) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _tuned(doc) | {"look": look.id, "said": tuning.said_look(look), **_filed_in(drawer)}


@router.get("/faults")
def slicer_faults():
    """The faults a look reads, and the severities."""
    return {
        "severity": {str(k): v for k, v in pf.SEVERITY.items()},
        "faults": [
            {
                "id": f.id,
                "name": f.name,
                "looks_like": f.looks_like,
                "otherwise": f.otherwise,
                "levers": [
                    {
                        "setting": lv.key,
                        "kind": lv.kind,
                        "unit": lv.unit,
                        "step": lv.step,
                        "least": lv.least,
                        "most": lv.most,
                        "why": lv.why,
                    }
                    for lv in f.levers
                ],
            }
            for f in pf.FAULTS
        ],
    }


def _printer_profile(site: str, printer: str):
    """The slicer profile of ``printer`` standing in ``site``: 422 where it is none."""
    try:
        chosen = None
        for answer in service.PRINTERS:
            at = answer(None, site, printer)
            if at is not None:
                chosen = at
                break
        if chosen is None:
            raise SlicerError(f"{printer} in {site}: no printer that keeps a slicer profile")
        return service.load_profile(chosen.part)
    except SlicerError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/filaments")
def slicer_filaments(
    site: str = Query(..., pattern=SITE_NAME), printer: str = Query(..., pattern=NODE_PATH)
):
    """The filament loaded on ``printer`` and every filament it can load."""
    profile = _printer_profile(site, printer)
    try:
        found = filaments.choices(profile)
    except NotInstalled as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except SlicerError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    kept = filaments.loaded(site, printer)
    return {
        "chooses": filaments.chooses(profile),
        "profile": (profile.sections.get("orcaslicer") or {}).get("filament"),
        "loaded": kept.model_dump(mode="json") if kept else None,
        "choices": [c.model_dump() for c in found],
    }


@router.post("/filaments/loaded")
def slicer_filament_loaded(body: FilamentRequest):
    """Another filament loaded on the printer: its next slices are made with it."""
    profile = _printer_profile(body.site, body.printer)
    try:
        kept = filaments.load(profile, body.site, body.printer, body.filament, body.note)
    except filaments.Refused as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except NotInstalled as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return kept.model_dump(mode="json")


def _filed_in(drawer: Optional["cabinet.Drawer"]) -> dict:
    """Where a filing went: the part's drawer, or nothing for a piece no part's."""
    return {"drawer": {"part": drawer.part, "id": drawer.id}} if drawer is not None else {}


def _tuned(doc: "tuning.TuningDocument") -> dict:
    return tuning.answer(doc)


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
    """The last turn or look dropped, with what it applied."""
    try:
        doc, gone = tuning.undo(body.site, body.printer, body.applies())
    except tuning.Refused as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    # The filing in the part's cabinet that made it says it was undone.
    cabinet.undone(gone.slice.part, body.site, body.printer, body.applies(), gone.id)
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
    return {
        "ok": True,
        "turns": len(doc.turns),
        "looks": len(doc.looks),
        "settings": sorted(doc.settings),
    }
