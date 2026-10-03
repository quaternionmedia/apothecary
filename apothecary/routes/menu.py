"""The two routes the ring speaks through: what are my options, and I chose one.

Who carries an action out is written down once, in `apothecary/menu.py`'s
`CARRIED_BY`; this module answers from it. An action nothing classifies is
refused with a 400 naming it, never answered with a 200 that did nothing.

**What the page knows about a board is carried beside the context, not inside
it.** `device` on a resolve says whether the node has a board pinned, whether
that board is a printer and whether its control latch is armed; the resolver
offers the device and control rings from that and nothing else. The verbs on
those rings are the viewer's: the pages already have a handler for each, and
the intent route never opens a port.

**Which arrangement an intent is about is carried beside the intent, not inside
it.** Reading a site name out of `context.targets` would work for the canvas
ring and mean the wrong thing for a node ring, where the target is a dotted
path to a piece.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..menu import (
    FLOOR_MARK,
    Carries,
    Context,
    Device,
    Intent,
    PictureContext,
    Ring,
    RingTooFull,
    carried_by,
    resolve,
)

router = APIRouter(prefix="/menu", tags=["menu"])


class ResolveRequest(BaseModel):
    """What the ring was opened on, which arrangement it was opened over, and
    what the page knows about the board under it, if any."""

    context: Context
    site: Optional[str] = None
    device: Optional[Device] = None
    picture: Optional[PictureContext] = None


class Chosen(BaseModel):
    """A chosen option, and the arrangement it applies to.

    The intent carries the address -- the cells pressed to reach the option --
    when the ring was the way in. It is echoed back, so a log of answers can be
    read as something a person could type again.
    """

    intent: Intent
    site: Optional[str] = None


class Carried(BaseModel):
    """What became of a chosen option.

    `did` is the point of this shape. A person who presses a wedge and sees
    nothing move has no way to tell "the viewer handles this" from "nothing
    handles this", and neither does a test. This says which.
    """

    action: str
    carried_by: str
    did: str
    site: Optional[Dict[str, object]] = None
    address: Optional[str] = None


def _site(name: Optional[str]):
    """The arrangement by name, or None.

    Imported inside the function rather than at the top because
    `apothecary/api.py` mounts this router, so importing it at module scope would
    close a circle. The same deferred-import shape the photo shelf already uses
    in that module.
    """
    if name is None:
        return None
    from ..api import _get_site_or_404

    return _get_site_or_404(name)


def _catalogue(name: Optional[str]) -> Dict[str, List[str]]:
    """The lists a ring is built from, read fresh on every call: the
    arrangements that exist now, and the groups in this one."""
    from ..api import _site_store

    groups: List[str] = []
    site = _site(name)
    if site is not None:
        groups = sorted({child.category for child in site.children if child.category})
    return {"site_names": sorted(_site_store.names()), "groups": groups}


def _pictures_known(site: Optional[str], told: Optional[PictureContext]) -> PictureContext:
    """What the page told about pictures, with what only the server knows put in:
    the site's made pieces, the vocabulary's words, and the finders that can read
    the drawn look's picture. A page cannot claim these, so it is never asked."""
    from ..vision import looks as looking
    from ..vocabulary import starter_words
    from .looks import finders_for

    known = (told or PictureContext()).model_copy(deep=True)
    known.made = sorted(looking.made_names(site)) if site else []
    known.words = starter_words().names()
    drawn = next((lk for lk in known.here.looks if lk.id == known.here.drawn), None)
    if drawn is None and known.here.looks:
        drawn = known.here.looks[0]
    known.finders = finders_for(drawn.picture) if drawn is not None and drawn.picture else []
    return known


@router.post("/resolve", response_model=Ring)
def resolve_ring(request: ResolveRequest) -> Ring:
    """Which options belong on the ring, given what it was opened on.

    Changes nothing, by construction: this calls the same pure function a test
    calls, with the lists filled in from what exists right now.
    """
    lists = _catalogue(request.site)
    try:
        return resolve(
            request.context,
            _site(request.site),
            site_names=lists["site_names"],
            groups=lists["groups"],
            device=request.device,
            picture=_pictures_known(request.site, request.picture),
        )
    except RingTooFull as too_many:
        # A ring that cannot be built is a design problem, and the answer says so
        # rather than handing back a shorter ring that hides what it dropped.
        raise HTTPException(status_code=409, detail=str(too_many)) from None


def _needs_site(chosen: Chosen) -> str:
    if not chosen.site:
        raise HTTPException(
            status_code=400,
            detail=(
                f"{chosen.intent.action!r} is about one arrangement, and the "
                "intent did not say which. Send it as `site`."
            ),
        )
    return chosen.site


def _carry_picture(chosen: Chosen, who: Carries) -> Carried:
    """Make, Make all, Drop and a made piece's Word: a root structure added,
    removed or rebuilt, by the functions the look routes call. Every refusal is
    a 4xx naming its reason, so no picture intent reaches the 500 below."""
    from ..api import _site_payload, _site_store
    from ..vision import looks as looking

    action = chosen.intent.action
    name = _needs_site(chosen)
    site = _site(name)
    verb, _, rest = action.partition(":")[2].partition(":")
    rest = rest.removesuffix(f":{FLOOR_MARK}")
    piece = chosen.intent.context.targets[0] if chosen.intent.context.targets else ""
    try:
        if verb == "make":
            look_id, _, index = rest.rpartition(":")
            if not look_id or not index.isdigit():
                raise HTTPException(
                    status_code=400,
                    detail=f"{action!r} names no look and shape: picture:make:<look>:<index>",
                )
            made, skipped = looking.make(name, site, look_id, int(index))
            did = f"made {', '.join(made) or 'nothing'}" + (
                f"; {skipped} already made" if skipped else ""
            )
        elif verb == "make-all":
            if not rest:
                raise HTTPException(
                    status_code=400, detail=f"{action!r} names no look: picture:make-all:<look>"
                )
            made, skipped = looking.make(name, site, rest, None)
            listed = f": {', '.join(made)}" if made else ""
            did = f"made {len(made)} piece(s){listed}; skipped {skipped} already made"
        elif verb == "drop":
            record = looking.drop(name, site, piece)
            did = f"dropped {piece}; shape {record.shape_index} of its look reads as found again"
        elif verb == "word":
            if not rest:
                raise HTTPException(status_code=400, detail=f"{action!r} names no word")
            record = looking.rebuild(name, site, piece, word=rest)
            did = f"{piece} is a {record.word} now, rebuilt where it stands"
        else:
            raise HTTPException(status_code=400, detail=f"{action!r} is no picture verb")
    except looking.LookNotFound as missing:
        raise HTTPException(status_code=404, detail=str(missing).strip('"')) from None
    except looking.NotMade as missing:
        raise HTTPException(status_code=404, detail=str(missing).strip('"')) from None
    except looking.CannotMake as refused:
        raise HTTPException(status_code=409, detail=str(refused)) from None
    except ValueError as refused:
        raise HTTPException(status_code=422, detail=str(refused)) from None
    return Carried(
        action=action,
        carried_by=who.value,
        did=did,
        site=_site_payload(site, _site_store.validator(name)(site)),
        address=chosen.intent.address,
    )


# `async def`, one at a time on the event loop, as api.py's rule for routes that
# change a site says: a reset and a make both change the site in place.
@router.post("/intent", response_model=Carried)
async def carry_out(chosen: Chosen) -> Carried:
    """Carry out a chosen option, or say that the viewer does, or refuse."""
    from ..api import _job_store, _site_payload, _site_store

    action = chosen.intent.action
    try:
        who = carried_by(action)
    except KeyError as unknown:
        raise HTTPException(status_code=400, detail=str(unknown).strip('"')) from None

    if who is Carries.VIEWER:
        return Carried(
            action=action,
            carried_by=who.value,
            did="nothing here; this one is about what is on screen",
            address=chosen.intent.address,
        )

    if action == "reset":
        name = _needs_site(chosen)
        _site(name)  # 404s on a name that is not there, before anything is reset
        rebuilt = _site_store.reset(name)
        _job_store.reset(name)
        return Carried(
            action=action,
            carried_by=who.value,
            did=f"rebuilt {name} from its factory and emptied its jobs",
            site=_site_payload(rebuilt, _site_store.validator(name)(rebuilt)),
            address=chosen.intent.address,
        )

    if action.startswith("picture:"):
        return _carry_picture(chosen, who)

    # Reachable only by classifying an action as the server's and not writing
    # the arm that carries it out.
    raise HTTPException(
        status_code=500,
        detail=f"{action!r} is written down as the server's and has no arm here.",
    )
