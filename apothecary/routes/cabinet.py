"""``/cabinet``: each part's drawers, a piece made of it each, and what is filed about them
(``apothecary/cabinet.py``). Part › Feedback reads and files here.

- ``GET /cabinet``: the parts with a drawer; ``?job=`` the drawer that job's piece is in.
- ``GET /cabinet/{part}``: its drawers, the newest first, each without the record that
  made it, with its line (``line``). A filing's answer is the drawer whole, with what
  the filing made said (``said``).
- ``GET /cabinet/{part}/variants``: its drawers by the saved variant each piece was made
  of (``cabinet.by_variant``), and those of none (``unsaved``): Part › Variants lists them.
- ``GET /cabinet/{part}/drawers/{id}``: one drawer whole, with what its machine keeps of
  it now: a printer's tuning for the filament and process the piece used (``tuning``),
  a router's tool allowance (``allowance``); null where none is kept; and its
  ``dimensions`` (``cabinet.dimensions``).
- ``GET /cabinet/{part}/dimensions``: a piece's dimensions, each as designed with its newest
  reading kept, and the tolerance a reading is checked with: ``?drawer=`` that drawer's,
  ``?file=`` the newest drawer of that kept file (or the file's, as designed, where no
  drawer holds it), else the part's newest drawer, else its newest kept file.
- ``POST /cabinet/{part}/drawers`` ``{"file_id"}``: a drawer for a kept slice or cut of
  the part no job here ran, or the newest one of it; 404 for a file no slice or cut keeps,
  422 for one of another part.
- ``POST /cabinet/{part}/drawers/{id}/measured`` ``{"readings": {feature: mm}}``: what
  calipers read of the piece, each checked against its design and filed: a print's next
  turn of its printer's tuning (``turn`` null where its last turn already reads the
  piece: a check alone), a cut's router allowance (each feature one size, null where not
  measured).
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
from ..slicer.models import SliceRecord

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
    return (
        drawer.model_dump(mode="json", by_alias=True)
        | {"line": drawer.said()}
        | _kept(drawer)
        | {"dimensions": cabinet.dimensions(drawer.part, drawer).model_dump(mode="json")}
        | {"declared": _declared(drawer.part)}
    )


def _declared(part: str) -> dict:
    """The print settings ``part`` declares, only those it set (slicer Declared); none for
    a part that is not registered."""
    from ..projects.parts.skeleton import ROOT
    from ..projects.registry import PartLoadError, part_named
    from ..slicer.profiles import Declared

    try:
        found = part_named(part, ROOT)
    except (KeyError, PartLoadError):
        return {}
    return Declared.of(getattr(found, "print_settings", None), f"part {part}").values


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


# Every save of a part's variants, as last read, by what the variants were then: each
# one's newest save and its text. A variant's earlier saves do not change while those
# stand, so the walk over them is made once and not at each asking.
_SAVES: dict = {}


def _every_save(part: str, loaded, tips: list) -> list:
    from ..projects.parts import saved

    where = str(saved.where_saved(loaded).repo)
    key = (where, *((s.name, s.commit, s.digest, s.deleted) for s in tips))
    kept = _SAVES.get(part)
    if kept is None or kept[0] != key:
        kept = _SAVES[part] = (key, saved.save_texts(loaded, history=True))
    return kept[1]


@router.get("/{part}/variants")
def cabinet_by_variant(part: str):
    """``part``'s drawers by the saved variant each piece was made of: each variant's saves
    read as they are now, and every save of each where a piece's draft is none of those."""
    try:
        found = cabinet.drawers(part)
    except cabinet.Refused as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    saves: list = []
    if found:
        from .. import api
        from ..projects.parts import saved

        try:
            loaded = api.load_part_wrapper(part)
        except HTTPException as exc:
            if exc.status_code != 404:
                raise
            loaded = None  # no part of that name now: none of its pieces is a variant's
        try:
            if loaded is not None:
                saves = saved.save_texts(loaded)
                now = {s.digest for s in saves}
                if any(d.draft is not None and d.draft not in now for d in found):
                    saves = _every_save(part, loaded, saves)
        except saved.GitError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from None
    return cabinet.by_variant(part, found, saves).model_dump(mode="json")


@router.get("/{part}/drawers/{drawer_id}")
def cabinet_drawer(part: str, drawer_id: str):
    return _whole(_drawer(part, drawer_id))


def _kept_file(part: str, file_id: str):
    """The slice or cut record keeping ``file_id``, a piece of ``part``'s: 404 for a file
    none keeps, 422 for another part's. Opening a drawer and reading a piece's dimensions
    both find a kept file here."""
    from ..cam import service as cam_service
    from ..slicer import service as slicer_service

    record = slicer_service.get_record(file_id) or cam_service.get_record(file_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"no slice or cut keeps {file_id!r}")
    made = cabinet.part_of_slice(record) if isinstance(record, SliceRecord) else record.part
    if made != part:
        what = made or "a piece made from a picture"
        raise HTTPException(status_code=422, detail=f"{file_id} made {what}, not {part}")
    return record


def _newest_file(part: str):
    """The newest kept slice or cut of ``part``, or None."""
    from ..cam import service as cam_service
    from ..slicer import service as slicer_service

    kept = [r for r in slicer_service.records() if cabinet.part_of_slice(r) == part]
    kept += [r for r in cam_service.records() if r.part == part]
    return max(kept, key=lambda r: r.at, default=None)


@router.get("/{part}/dimensions")
def cabinet_dimensions(
    part: str,
    drawer: Optional[str] = Query(None, pattern=cabinet.DRAWER_ID),
    file: Optional[str] = Query(None, pattern=FILE_ID),
):
    """The dimensions of a piece of ``part`` -- the drawer named, else the newest drawer of
    the kept file named, else the part's newest drawer -- each as designed and with its
    newest reading kept; a kept file no drawer holds, as designed. Part › Feedback's rows
    and the world's Measure layer read them."""
    if drawer is not None:
        return cabinet.dimensions(part, _drawer(part, drawer)).model_dump(mode="json")
    try:
        found = cabinet.drawers(part)
    except cabinet.Refused as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if file is not None:
        record = _kept_file(part, file)
        held = next((d for d in found if d.file.file_id == file), None)
        return cabinet.dimensions(part, held, record).model_dump(mode="json")
    if found:
        return cabinet.dimensions(part, found[0]).model_dump(mode="json")
    return cabinet.dimensions(part, None, _newest_file(part)).model_dump(mode="json")


@router.post("/{part}/drawers")
def cabinet_open(part: str, body: OpenRequest):
    """A drawer for the kept file ``file_id``, a slice or a cut of ``part``."""
    record = _kept_file(part, body.file_id)
    try:
        if isinstance(record, SliceRecord):
            drawer = cabinet.for_slice(record)
        else:
            drawer = cabinet.for_cut(record)
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
    if turn is None:  # a check alone: the printer's last turn already reads the piece
        return _whole(drawer) | {"said": drawer.filed[-1].said, "turn": None}
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
