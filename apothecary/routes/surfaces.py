"""The surfaces (``apothecary/surfaces.py``) over HTTP: one way to read what the server
knows of each thing a page shows, one stream of what it learns changed, and one door for
what the family's members found.

- ``GET /surfaces``: every surface, its frame, the words it is read with and whether it
  says when it changes; and the frames.
- ``GET /surfaces/{name}?site=&path=&...``: the surface now, read with those words.
- ``GET /surfaces/events?names=&seconds=``: server-sent events, ``event: change``, one
  for each change an owner says (``surfaces.changed``) of the surfaces named (every one
  with none), each ``id`` its sequence number; ``event: missed`` when a reader fell so
  far behind that the oldest were let go; a comment every ``HEARTBEAT`` seconds. It
  relays what the server already learns and asks nothing of anything: a reader with
  nobody polling hears nothing of the machines. ``seconds`` ends it after that long.
- ``POST /surfaces/contributed``: an observation a member of the family's hub found
  about a surface (``surfaces.Observation``), kept; 403 for a name the hub's table does
  not hold, 404 for a surface no owner declared. Under the app's guard, as every route
  is (``apothecary/stays_local.py``): from this machine, and from a page of this origin.
"""

from __future__ import annotations

import json
import time
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from .. import surfaces

router = APIRouter(tags=["surfaces"])

FORMAT = "apothecary.surfaces/1"
# Seconds between the comments that keep a quiet stream open.
HEARTBEAT = 15.0
# How long a look for changes waits before it looks whether the reader has gone.
LOOK = 1.0


def _named(names: Optional[str]) -> Optional[list]:
    if not names:
        return None
    wanted = [n.strip() for n in names.split(",") if n.strip()]
    for name in wanted:
        try:
            surfaces.get(name)
        except surfaces.UnknownSurface as exc:
            raise HTTPException(status_code=404, detail=exc.args[0]) from None
    return wanted


@router.get("/surfaces")
def every_surface():
    return {
        "format": FORMAT,
        "frames": surfaces.FRAMES,
        "surfaces": [surfaces.described(s) for s in surfaces.listed()],
    }


def _frame(event: str, data, seq: Optional[int] = None) -> str:
    head = f"id: {seq}\n" if seq is not None else ""
    return f"{head}event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


@router.get("/surfaces/events")
async def surface_events(
    request: Request,
    names: Optional[str] = Query(None, max_length=400, description="surfaces by name, commas"),
    seconds: Optional[float] = Query(None, gt=0, le=86400, description="end after this long"),
):
    """Every change an owner says of the surfaces named, as it says it."""
    wanted = _named(names)
    following = surfaces.subscribe(wanted)
    ends = time.monotonic() + seconds if seconds is not None else None

    async def frames():
        try:
            yield _frame("surfaces", {"following": wanted or surfaces.names()})
            quiet = 0.0
            while not await request.is_disconnected():
                left = ends - time.monotonic() if ends is not None else LOOK
                if left <= 0:
                    break
                events, missed = await following.next(min(LOOK, left))
                if missed:
                    yield _frame("missed", {"missed": missed})
                for event in events:
                    yield _frame("change", event, event["seq"])
                if events or missed:
                    quiet = 0.0
                    continue
                quiet += LOOK
                if quiet >= HEARTBEAT:
                    quiet = 0.0
                    yield ": still here\n\n"
        finally:
            following.close()

    return StreamingResponse(
        frames(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/surfaces/contributed", status_code=201)
def contribute(body: surfaces.Observation):
    """What a member of the family's hub found about a surface, kept."""
    from ..family import hub

    if body.by not in hub.members():
        raise HTTPException(
            status_code=403,
            detail=f"{body.by!r} is no member of the family's hub: its table names the members",
        )
    try:
        return surfaces.contribute(body).model_dump(mode="json")
    except surfaces.UnknownSurface as exc:
        raise HTTPException(status_code=404, detail=exc.args[0]) from None


@router.get("/surfaces/{name}")
def one_surface(name: str, request: Request):
    """A surface now, read with the words of the query."""
    try:
        surface = surfaces.get(name)
        snapshot = surfaces.read(name, dict(request.query_params))
    except surfaces.UnknownSurface as exc:
        raise HTTPException(status_code=404, detail=exc.args[0]) from None
    except surfaces.Unasked as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    return {
        "surface": name,
        "frame": surface.frame,
        "words": dict(request.query_params),
        "snapshot": snapshot,
    }


__all__ = ["router"]
