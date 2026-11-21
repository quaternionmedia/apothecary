"""``/cabinet``: each part's drawers, a piece made of it each, and what is filed about them
(``apothecary/cabinet.py``). Part › Feedback reads and files here.

- ``GET /cabinet``: the parts with a drawer; ``?job=`` the drawer that job's piece is in.
- ``GET /cabinet/{part}``: its drawers, the newest first, each without the record that
  made it, with its line (``line``). A filing's answer is the drawer whole, with what
  the filing made said (``said``).
- ``GET /cabinet/{part}/drawers/{id}``: one drawer whole, with what its machine keeps of
  it now: a printer's tuning for the filament and process the piece used (``tuning``),
  a router's tool allowance (``allowance``); null where none is kept.
- ``POST /cabinet/{part}/drawers`` ``{"file_id"}``: a drawer for a kept slice or cut of
  the part no job here ran, or the newest one of it; 404 for a file no slice or cut keeps,
  422 for one of another part.
- ``POST /cabinet/{part}/drawers/{id}/measured`` ``{"readings": {feature: mm}}``: what
  calipers read of the piece, filed: a print's next turn of its printer's tuning, a cut's
  router allowance (each feature one size, null where not measured).
- ``POST /cabinet/{part}/drawers/{id}/seen`` ``{"seen": {fault: 0-3}, "where", "note"}``:
  a print's faults read by eye, filed as its printer's next look.
- ``POST /cabinet/{part}/drawers/{id}/note`` ``{"note"}``: a note, filed.
- ``POST /cabinet/{part}/drawers/{id}/tune/apply`` and ``/tune/undo``: the printer that
  made the piece takes its last turn's or look's changes into its next slices, or drops
  the last, for the filament and process the piece used; an undone filing says so.

What cannot be filed is a 422 saying why, and nothing is kept.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Union

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from .. import cabinet
from ..cam import measured as cut_measured
from ..slicer import tuning

router = APIRouter(prefix="/cabinet", tags=["cabinet"])

PART = r"^[A-Za-z0-9_][A-Za-z0-9_.\-]{0,199}$"
FILE_ID = r"^[A-Za-z0-9_.\-]{1,200}$"
JOB_ID = r"^[A-Za-z0-9][A-Za-z0-9_.\-]{0,119}$"


class OpenRequest(BaseModel):
    file_id: str = Field(..., pattern=FILE_ID)


class MeasuredRequest(BaseModel):
    # Each feature read, by its name: a print's one value in mm or its repeats, a cut's
    # one size or null where it was not measured.
    readings: Dict[str, Union[float, List[float], None]] = Field(..., max_length=64)
    resolution: float = Field(tuning.RESOLUTION, gt=0, le=1)  # the caliper's step, mm
    repeatability: Optional[float] = Field(None, ge=0, le=1)  # a person's, as stated, mm
    assume: Dict[str, float] = Field(default_factory=dict, max_length=8)


class SeenRequest(BaseModel):
    seen: Dict[str, int] = Field(..., max_length=32)  # by fault: 0 none, 1 slight, 2 clear, 3 bad
    where: Dict[str, str] = Field(default_factory=dict, max_length=32)
    note: str = Field("", max_length=cabinet.NOTE_MOST)


class NoteRequest(BaseModel):
    note: str = Field(..., max_length=cabinet.NOTE_MOST)


def _summary(drawer: cabinet.Drawer) -> dict:
    return drawer.model_dump(mode="json", by_alias=True, exclude={"slice", "cut"}) | {
        "line": drawer.said()
    }


def _kept(drawer: cabinet.Drawer) -> dict:
    """What the drawer's machine keeps of its piece now: a printer's tuning, a router's
    allowance."""
    at = drawer.machine
    doc = allowance = None
    if drawer.slice is not None and at.site and at.path and drawer.filament and drawer.process:
        found = tuning.load(at.site, at.path, _applies(drawer))
        doc = tuning.answer(found) if found is not None else None
    if drawer.cut is not None and at.site and at.path:
        kept = cut_measured.load(at.site, at.path)
        allowance = kept.model_dump(mode="json") if kept is not None else None
    return {"tuning": doc, "allowance": allowance}


def _whole(drawer: cabinet.Drawer) -> dict:
    return drawer.model_dump(mode="json", by_alias=True) | {"line": drawer.said()} | _kept(drawer)


def _applies(drawer: cabinet.Drawer) -> tuning.AppliesTo:
    return tuning.AppliesTo(filament=drawer.filament or "", process=drawer.process or "")


def _drawer(part: str, drawer_id: str) -> cabinet.Drawer:
    try:
        found = cabinet.get(part, drawer_id)
    except cabinet.Refused as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if found is None:
        raise HTTPException(status_code=404, detail=f"{part} has no drawer {drawer_id!r}")
    return found


@router.get("")
def cabinet_parts(job: Optional[str] = Query(None, pattern=JOB_ID)):
    """The parts with a drawer; with ``job``, the drawer that job's piece is in, or null."""
    found = cabinet.of_job(job) if job else None
    return {"parts": cabinet.parts()} | (
        {"drawer": {"part": found.part, "id": found.id} if found else None} if job else {}
    )


@router.get("/{part}")
def cabinet_of(part: str):
    """``part``'s drawers, the newest first."""
    try:
        found = cabinet.drawers(part)
    except cabinet.Refused as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"part": part, "drawers": [_summary(d) for d in found]}


@router.get("/{part}/drawers/{drawer_id}")
def cabinet_drawer(part: str, drawer_id: str):
    return _whole(_drawer(part, drawer_id))


@router.post("/{part}/drawers")
def cabinet_open(part: str, body: OpenRequest):
    """A drawer for the kept file ``file_id``, a slice or a cut of ``part``."""
    from ..cam import service as cam_service
    from ..slicer import service as slicer_service

    record = slicer_service.get_record(body.file_id)
    cut = cam_service.get_record(body.file_id) if record is None else None
    if record is None and cut is None:
        raise HTTPException(status_code=404, detail=f"no slice or cut keeps {body.file_id!r}")
    made = cabinet.part_of_slice(record) if record is not None else cut.part
    if made != part:
        what = made or "a piece made from a picture"
        raise HTTPException(status_code=422, detail=f"{body.file_id} made {what}, not {part}")
    try:
        drawer = cabinet.for_slice(record) if record is not None else cabinet.for_cut(cut)
    except cabinet.Refused as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _whole(drawer)


@router.post("/{part}/drawers/{drawer_id}/measured")
def cabinet_measured(part: str, drawer_id: str, body: MeasuredRequest):
    drawer = _drawer(part, drawer_id)
    try:
        if drawer.cut is not None:
            sizes = {}
            for name, v in body.readings.items():
                if isinstance(v, list):
                    if len(v) != 1:
                        raise cabinet.Refused(f"{name}: a cut piece's feature is one size")
                    v = v[0]
                sizes[name] = v
            drawer, kept = cabinet.measured_cut(drawer, sizes)
            return _whole(drawer) | {"said": cut_measured.said(kept.measurements[-1])}
        values = {}
        for name, v in body.readings.items():
            if v is None:
                continue
            read = [v] if isinstance(v, (int, float)) else list(v)
            if len(read) > 20 or any(not (0 < x <= 2000) for x in read):
                raise cabinet.Refused(f"{name}: up to 20 sizes, each over 0 mm")
            values[name] = read
        instrument = tuning.Instrument(resolution=body.resolution, repeatability=body.repeatability)
        drawer, _, turn = cabinet.measured(drawer, values, instrument, body.assume)
    except (cabinet.Refused, tuning.Refused, cut_measured.Refused) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _whole(drawer) | {"said": tuning.said(turn), "turn": turn.id}


@router.post("/{part}/drawers/{drawer_id}/seen")
def cabinet_seen(part: str, drawer_id: str, body: SeenRequest):
    drawer = _drawer(part, drawer_id)
    try:
        drawer, _, look = cabinet.looked(drawer, body.seen, body.where, body.note)
    except (cabinet.Refused, tuning.Refused) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _whole(drawer) | {"said": tuning.said_look(look), "look": look.id}


@router.post("/{part}/drawers/{drawer_id}/note")
def cabinet_note(part: str, drawer_id: str, body: NoteRequest):
    drawer = _drawer(part, drawer_id)
    try:
        drawer = cabinet.noted(drawer, body.note)
    except cabinet.Refused as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _whole(drawer) | {"said": f"noted on {drawer.id}"}


@router.post("/{part}/drawers/{drawer_id}/tune/{verb}")
def cabinet_tune(part: str, drawer_id: str, verb: str):
    """The printer that made the piece takes its last turn's changes (``apply``), or drops
    its last turn or look (``undo``), for the filament and process the piece used."""
    if verb not in ("apply", "undo"):
        raise HTTPException(status_code=404, detail=f"tune {verb!r}: apply or undo")
    drawer = _drawer(part, drawer_id)
    at = drawer.machine
    if drawer.slice is None or not at.site or not at.path:
        what = (
            "a cut: a router takes its allowance as it is measured"
            if drawer.cut
            else "no printer of a site"
        )
        raise HTTPException(status_code=422, detail=f"{drawer.id} was made by {what}")
    applies = _applies(drawer)
    try:
        if verb == "apply":
            _, changes = tuning.apply(at.site, at.path, applies)
            said = (
                f"Taken for {at.path}'s next slices: "
                + ", ".join(
                    f"{c.setting} {c.after:g}{(' ' + c.unit) if c.unit else ''}" for c in changes
                )
                if changes
                else f"nothing to take for {at.path}"
            )
            return _whole(drawer) | {
                "said": said,
                "applied": [c.model_dump(mode="json") for c in changes],
            }
        _, gone = tuning.undo(at.site, at.path, applies)
    except tuning.Refused as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    cabinet.undone(gone.slice.part, at.site, at.path, applies, gone.id)
    return _whole(_drawer(part, drawer_id)) | {"said": f"{gone.id} undone", "undone": gone.id}
