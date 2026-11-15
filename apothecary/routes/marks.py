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

Each word is kept with when it was given. ``?as_of=`` on the marks reads them with
the words given up to that moment, as a whiteboard's timeline asks.

The words are kept with the views, in this server's memory, and go when it
stops; what may be kept longer waits on the draft record *Personal data stays on
the device*, as a view does (docs/pictures.md).
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..vision import marks, notes
from ..vision import views as viewing
from ..vision.cache import picture_hash
from .views import picture_at, picture_size, view_answer_in, view_or_404

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


def keep(site_name: str, view_id: str, answers: marks.Answers) -> None:
    """Words kept for a view as given: a whiteboard's moment placed elsewhere, or
    words carried to a later photograph."""
    with _lock:
        _kept[(site_name, view_id)] = answers.model_copy(deep=True)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_marks(
    site_name: str, view_id: str, as_of: Optional[str] = None
) -> Tuple[List[marks.Mark], List[notes.Note]]:
    """A view's marks and its notes, read from its picture with the words given up
    to ``as_of``."""
    view = view_or_404(site_name, view_id)
    where = picture_at(view.picture)
    held = marks.as_of(kept_for(site_name, view_id), as_of)
    try:
        found = marks.marks_in(where, held)
    except (OSError, ValueError) as exc:
        raise HTTPException(
            status_code=400, detail=f"{where.name} could not be read: {exc}"
        ) from None
    wide, high = picture_size(where)
    return found, notes.notes_of(found, held, tallness=high / wide)


def _said(site_name: str, view_id: str, as_of: Optional[str] = None) -> Dict[str, object]:
    found, listed = read_marks(site_name, view_id, as_of)
    view = view_or_404(site_name, view_id)
    return {
        "view": view_id,
        "as_of": as_of,
        "finder": view.finder,
        "marks": [mark.model_dump(mode="json") for mark in found],
        "notes": [note.model_dump(mode="json") for note in listed],
    }


@router.get("/sites/{site_name}/views/{view_id}/marks")
def view_marks(site_name: str, view_id: str, as_of: Optional[str] = None):
    """A view's marks, sorted, and its notes: with the words given up to ``as_of``,
    ISO 8601, where it is named."""
    if as_of:
        try:
            datetime.fromisoformat(as_of)
        except ValueError:
            raise HTTPException(
                status_code=422, detail=f"{as_of!r} is not a moment, ISO 8601"
            ) from None
    return _said(site_name, view_id, as_of)


class MarkWord(BaseModel):
    kind: marks.Kind


@router.put("/sites/{site_name}/views/{view_id}/marks/{mark_id}")
def say_mark(site_name: str, view_id: str, mark_id: str, body: MarkWord):
    """A person's word on one mark; a view the outline finder searched is read
    again with it. Answers the marks, the notes and the view as it is now."""
    from ..vision import get as get_finder

    view = view_or_404(site_name, view_id)
    where = picture_at(view.picture)
    found, _ = read_marks(site_name, view_id)
    try:
        example = marks.say(found, mark_id, body.kind, picture_hash(where))
        example = example.model_copy(update={"at": _now()})
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
    return {**_said(site_name, view_id), "seen": view_answer_in(site_name, view)}


class NoteWords(BaseModel):
    text: str = Field(min_length=1, max_length=400)


@router.put("/sites/{site_name}/views/{view_id}/notes/{mark_id}")
def say_note(site_name: str, view_id: str, mark_id: str, body: NoteWords):
    """What one note says, as a person typed it."""
    found, _ = read_marks(site_name, view_id)
    try:
        words = notes.say(found, mark_id, body.text).model_copy(update={"at": _now()})
    except KeyError as missing:
        raise HTTPException(status_code=404, detail=str(missing).strip('"')) from None
    except ValueError as refused:
        raise HTTPException(status_code=400, detail=str(refused)) from None
    with _lock:
        held = _kept.setdefault((site_name, view_id), marks.Answers())
        held.words = [w for w in held.words if (w.min, w.max) != (words.min, words.max)] + [words]
    return _said(site_name, view_id)


__all__ = ["forget", "keep", "kept_for", "read_marks", "router"]
