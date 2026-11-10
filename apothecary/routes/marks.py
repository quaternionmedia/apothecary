"""A view's marks and notes, and a person's words on them.

- ``GET /sites/{s}/views/{id}/marks`` is the view's picture sorted: each mark a
  diagram's, writing or unsure, and each note with what it is about
  (``apothecary/vision/marks.py``, ``notes.py``), with the words a person has
  given here.
- ``PUT /sites/{s}/views/{id}/marks/{mark}`` ``{kind}`` is a person's word on one
  mark. It wins, and a view the outline finder searched is read again with it, so
  its shapes follow.
- ``PUT /sites/{s}/views/{id}/notes/{mark}`` ``{text}`` is what a note says, as a
  person typed it.

The words are kept with the views, in this server's memory, and go when it
stops; what may be kept longer waits on the draft record *Personal data stays on
the device*, as a view does (docs/pictures.md).
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Dict, List, Tuple

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..vision import marks, notes
from ..vision import views as viewing
from ..vision.cache import picture_hash
from .views import _answer, _picture_at, _picture_size, _view_or_404

router = APIRouter(tags=["views"])

_kept: Dict[Tuple[str, str], marks.Answers] = {}
_lock = threading.Lock()


def kept_for(site_name: str, view_id: str) -> marks.Answers:
    """The words a person has given on one view's marks, a copy."""
    with _lock:
        held = _kept.get((site_name, view_id))
        return held.model_copy(deep=True) if held is not None else marks.Answers()


def forget(site_name: str, view_id: str) -> None:
    with _lock:
        _kept.pop((site_name, view_id), None)


def _read(site_name: str, view_id: str) -> Tuple[List[marks.Mark], List[notes.Note]]:
    view = _view_or_404(site_name, view_id)
    where = _picture_at(view.picture)
    held = kept_for(site_name, view_id)
    try:
        found = marks.marks_in(where, held)
    except (OSError, ValueError) as exc:
        raise HTTPException(
            status_code=400, detail=f"{where.name} could not be read: {exc}"
        ) from None
    wide, high = _picture_size(where)
    return found, notes.notes_of(found, held, tallness=high / wide)


def _said(site_name: str, view_id: str) -> Dict[str, object]:
    found, listed = _read(site_name, view_id)
    view = _view_or_404(site_name, view_id)
    return {
        "view": view_id,
        "finder": view.finder,
        "marks": [mark.model_dump(mode="json") for mark in found],
        "notes": [note.model_dump(mode="json") for note in listed],
    }


@router.get("/sites/{site_name}/views/{view_id}/marks")
def view_marks(site_name: str, view_id: str):
    """A view's marks, sorted, and its notes."""
    return _said(site_name, view_id)


class MarkWord(BaseModel):
    kind: marks.Kind


@router.put("/sites/{site_name}/views/{view_id}/marks/{mark_id}")
def say_mark(site_name: str, view_id: str, mark_id: str, body: MarkWord):
    """A person's word on one mark; a view the outline finder searched is read
    again with it. Answers the marks, the notes and the view as it is now."""
    from ..vision import get as get_finder

    view = _view_or_404(site_name, view_id)
    where = _picture_at(view.picture)
    found, _ = _read(site_name, view_id)
    try:
        example = marks.say(found, mark_id, body.kind, picture_hash(where))
    except KeyError as missing:
        raise HTTPException(status_code=404, detail=str(missing).strip('"')) from None
    with _lock:
        _kept.setdefault((site_name, view_id), marks.Answers()).examples.append(example)
    if view.finder == "outline":
        seen = get_finder("outline").look_with(where, kept_for(site_name, view_id))
        shapes, left_out = viewing.keep_the_most_sure(seen.shapes)
        view = viewing.store().read_again(
            site_name, view_id, shapes=shapes, left_out=left_out, at=datetime.now(timezone.utc)
        )
    return {**_said(site_name, view_id), "seen": _answer(site_name, view)}


class NoteWords(BaseModel):
    text: str = Field(min_length=1, max_length=400)


@router.put("/sites/{site_name}/views/{view_id}/notes/{mark_id}")
def say_note(site_name: str, view_id: str, mark_id: str, body: NoteWords):
    """What one note says, as a person typed it."""
    found, _ = _read(site_name, view_id)
    try:
        words = notes.say(found, mark_id, body.text)
    except KeyError as missing:
        raise HTTPException(status_code=404, detail=str(missing).strip('"')) from None
    except ValueError as refused:
        raise HTTPException(status_code=400, detail=str(refused)) from None
    with _lock:
        held = _kept.setdefault((site_name, view_id), marks.Answers())
        held.words = [w for w in held.words if (w.min, w.max) != (words.min, words.max)] + [words]
    return _said(site_name, view_id)


__all__ = ["forget", "kept_for", "router"]
