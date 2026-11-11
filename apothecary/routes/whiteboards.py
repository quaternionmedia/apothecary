"""A whiteboard's history, a moment of it placed elsewhere, and what changed between
two of its photographs, taken or left by a person.

- ``GET /sites/{s}/whiteboards`` lists the site's whiteboards and how many
  photographs each holds.
- ``GET /sites/{s}/whiteboards/{w}/timeline`` is every event of a whiteboard,
  oldest first: each photograph pinned, each word given, each piece made
  (``apothecary/vision/history.py``). ``?at=`` names a moment, and the answer
  says the photograph the whiteboard stood as then.
- ``GET /sites/{s}/views/{later}/again?since={earlier}`` lists what the later
  photograph proposes of the earlier's shapes and notes, each row saying by how
  much and whether taking it changes anything: a moved or resized shape
  rebuilds the piece made from it, a new shape is made, a gone one drops its
  piece, and the same writing carries its words. ``POST`` with ``{since, take}``
  takes the rows named and nothing else.
- ``POST /sites/{s}/views/{id}/place`` ``{host, as_of?}`` places a moment of a
  whiteboard elsewhere: its picture pinned at another place, as wide, searched
  by the same finder, with the words given up to that moment.

Kept in the server's memory with the views; nothing here is stored.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..vision import again, history, marks, whiteboard
from ..vision import views as viewing
from ..vision.models import Picture
from .marks import _read, keep, kept_for
from .views import (
    _answer,
    _picture_at,
    _site,
    _site_answer,
    _view_or_404,
    find_in,
    pin_picture,
)

router = APIRouter(tags=["views"])


def _whiteboard_or_404(site_name: str, name: str):
    site = _site(site_name)
    node = next((c for c in site.children if c.name == name), None)
    if node is None or not whiteboard.is_whiteboard(node):
        raise HTTPException(status_code=404, detail=f"{name!r} is not a whiteboard of {site_name}")
    return site, node


def _photographs(site_name: str, name: str) -> List[viewing.View]:
    return history.photographs(viewing.store().views_at(site_name), name)


def _moment(at: Optional[str]) -> Optional[str]:
    if not at:
        return None
    try:
        datetime.fromisoformat(at)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"{at!r} is not a moment, ISO 8601") from None
    return at


@router.get("/sites/{site_name}/whiteboards")
def list_whiteboards(site_name: str):
    """The site's whiteboards, each with how many photographs it holds."""
    site = _site(site_name)
    return [
        {"name": node.name, "photographs": len(_photographs(site_name, node.name))}
        for node in site.children
        if whiteboard.is_whiteboard(node)
    ]


@router.get("/sites/{site_name}/whiteboards/{name}/timeline")
def whiteboard_timeline(site_name: str, name: str, at: Optional[str] = None):
    """Every event of a whiteboard, oldest first, and the photograph it stood as at
    ``at`` (ISO 8601), the newest when no moment is named."""
    _whiteboard_or_404(site_name, name)
    when = _moment(at)
    pictures = _photographs(site_name, name)
    kept = {view.id: kept_for(site_name, view.id) for view in pictures}
    events = history.timeline(pictures, kept, viewing.store().made_at(site_name))
    layer = history.layer_at(pictures, when)
    return {
        "whiteboard": name,
        "at": when,
        "since": events[0].at if events else None,
        "until": events[-1].at if events else None,
        "events": [event.model_dump(mode="json") for event in events],
        "photographs": [
            {"id": v.id, "taken_at": v.taken_at, "picture": v.picture, "shapes": len(v.shapes)}
            for v in pictures
        ],
        "layer": layer.id if layer is not None else None,
    }


def _rows(site_name: str, later: viewing.View, earlier: viewing.View) -> List[again.Proposal]:
    """What the later photograph proposes of the earlier's shapes and notes, each
    shape's row takeable only where taking it changes a piece."""
    made = viewing.store().made_at(site_name)
    stated = [
        index
        for index, piece in earlier.made.items()
        if piece in made and made[piece].parameters_stated
    ]
    before = Picture(
        name=earlier.id,
        pixel_width=earlier.pixel_width,
        pixel_height=earlier.pixel_height,
        shapes=earlier.shapes,
    )
    after = Picture(
        name=later.id,
        pixel_width=later.pixel_width,
        pixel_height=later.pixel_height,
        shapes=later.shapes,
    )
    rows = []
    for row in again.compare(before, after, stated=stated):
        piece = earlier.made.get(row.before) if row.before is not None else None
        changes = row.change is again.Change.NEW or piece is not None
        says = (
            row.says
            if changes or row.change is again.Change.DISAGREES
            else f"{row.says}; nothing is made from it"
        )
        rows.append(row.model_copy(update={"takeable": row.takeable and changes, "says": says}))
    _, old_notes = _read(site_name, earlier.id)
    _, new_notes = _read(site_name, later.id)
    return rows + again.compare_notes(old_notes, new_notes, numbered_from=len(rows) + 1)


def _pair(site_name: str, view_id: str, since: str):
    later, earlier = _view_or_404(site_name, view_id), _view_or_404(site_name, since)
    if not later.found or not earlier.found:
        raise HTTPException(
            status_code=409,
            detail="both photographs' shapes must be found first: Picture › Find shapes on each",
        )
    if later.host != earlier.host:
        raise HTTPException(
            status_code=409,
            detail=f"{since} lies at {earlier.host!r} and {view_id} at {later.host!r}: "
            "round again compares two photographs of one place",
        )
    return later, earlier


@router.get("/sites/{site_name}/views/{view_id}/again")
def what_changed(site_name: str, view_id: str, since: str):
    """What a later photograph proposes of an earlier one's shapes and notes."""
    later, earlier = _pair(site_name, view_id, since)
    return {
        "since": since,
        "view": view_id,
        "rows": [r.model_dump(mode="json") for r in _rows(site_name, later, earlier)],
    }


class Take(BaseModel):
    since: str = Field(min_length=1)
    take: List[int] = Field(min_length=1)


@router.post("/sites/{site_name}/views/{view_id}/again")
def take_changes(site_name: str, view_id: str, body: Take):
    """Take the rows named, and nothing else: a moved or resized shape's piece
    rebuilt from the later shape, a new shape made, a gone one's piece dropped,
    the same writing's words carried."""
    later, earlier = _pair(site_name, view_id, body.since)
    rows = {row.number: row for row in _rows(site_name, later, earlier)}
    for number in body.take:
        if number not in rows:
            raise HTTPException(status_code=404, detail=f"no row {number}; have {sorted(rows)}")
        if not rows[number].takeable:
            raise HTTPException(
                status_code=409, detail=f"row {number} cannot be taken: {rows[number].says}"
            )
    site = _site(site_name)
    made_now: List[str] = []
    dropped: List[str] = []
    for number in sorted(body.take):
        row = rows[number]
        if row.change in (again.Change.MOVED, again.Change.RESIZED, again.Change.GONE):
            piece = earlier.made[row.before]
            record = viewing.drop(site_name, site, piece)
            dropped.append(piece)
            if row.change is not again.Change.GONE:
                making = viewing.make(site_name, site, later.id, row.after)
                made_now.extend(making.made)
                if record.word_stated:
                    for name in making.made:
                        viewing.rebuild(site_name, site, name, word=record.word)
        elif row.change is again.Change.NEW:
            made_now.extend(viewing.make(site_name, site, later.id, row.after).made)
        elif row.change is again.Change.NOTE_SAME:
            found, _ = _read(site_name, later.id)
            mark = next(m for m in found if m.id == row.note_after)
            held = kept_for(site_name, later.id)
            held.words.append(
                marks.Words(
                    min=(mark.min_point.x, mark.min_point.y),
                    max=(mark.max_point.x, mark.max_point.y),
                    text=row.words or "",
                    by="you",
                    at=datetime.now(timezone.utc).isoformat(),
                )
            )
            keep(site_name, later.id, held)
    later, earlier = _pair(site_name, view_id, body.since)
    return {
        "taken": sorted(body.take),
        "made": made_now,
        "dropped": dropped,
        "rows": [r.model_dump(mode="json") for r in _rows(site_name, later, earlier)],
        "site": _site_answer(site_name, site),
    }


class Place(BaseModel):
    host: str
    as_of: Optional[str] = None


@router.post("/sites/{site_name}/views/{view_id}/place", status_code=201)
def place_moment(site_name: str, view_id: str, body: Place):
    """A moment of a whiteboard placed elsewhere: its picture pinned at ``host``, a
    structure's top or the floor (``""``), as wide as it was, searched by the same
    finder, with the words given up to ``as_of``. A view's own place, or another
    whiteboard, is refused."""
    source = _view_or_404(site_name, view_id)
    when = _moment(body.as_of)
    site = _site(site_name)
    node = next((c for c in site.children if c.name == body.host), None)
    if body.host == source.host:
        raise HTTPException(status_code=409, detail=f"{view_id} already lies at {body.host!r}")
    if node is not None and whiteboard.is_whiteboard(node):
        raise HTTPException(
            status_code=409,
            detail=f"{body.host} is a whiteboard: a photograph is pinned there, a moment placed elsewhere",
        )
    if source.mm_across is None:
        raise HTTPException(
            status_code=409, detail=f"{view_id} has no width yet, so it has no size to place"
        )
    placed = pin_picture(site_name, body.host, source.picture, mm_across=source.mm_across)
    words = marks.as_of(kept_for(site_name, view_id), when) or marks.Answers()
    keep(site_name, placed.id, words)
    if source.found and source.finder:
        if source.finder == "outline":
            from ..vision import get as get_finder

            seen = get_finder("outline").look_with(_picture_at(placed.picture), words)
            shapes, left_out = viewing.keep_the_most_sure(seen.shapes)
            find_in(site_name, placed.id, "outline")
            placed = viewing.store().read_again(
                site_name,
                placed.id,
                shapes=shapes,
                left_out=left_out,
                at=datetime.now(timezone.utc),
            )
        else:
            placed = find_in(site_name, placed.id, source.finder)
    return {**_answer(site_name, placed), "placed_from": view_id, "as_of": when}


__all__ = ["router"]
