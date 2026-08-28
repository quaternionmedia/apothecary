"""The two routes the ring speaks through: what are my options, and I chose one.

Step one of the migration in `docs/plans/edits/apothecary-surface.md`, and it is
deliberately the step where **nothing visible changes**. The routes land,
resolving and carrying out only verbs that already exist. The toolbar is
untouched; the ring is not drawn yet. Landing the seam before the surface moves
means every later step replaces a control rather than adding one.

Two things this module refuses to do, both of which would make the promise
underneath the ring untrue:

- **It does not invent behaviour.** An option the rings offer with nothing behind
  it is answered with a refusal naming itself, not with a cheerful 200. `word:*`
  is exactly that today: the vocabulary is real, and swapping one piece's word
  for another is not built.
- **It does not decide who carries an action out.** That is written down once, in
  `apothecary/menu.py`'s `CARRIED_BY`, where a check can read it without starting
  a web server.

Everything that changes an arrangement is meant to arrive as an `Intent`. It does
not yet: the existing routes still change things directly, and rewiring them is
the next step. What is true today is that nothing arrives here and quietly does
nothing.

**Which arrangement an intent is about is carried beside the intent, not inside
it.** `Intent` is the shared contract's shape and names what was pointed at; the
arrangement is this project's own idea of where. Reading a site name out of
`context.targets` would work for the canvas ring and quietly mean the wrong thing
for a node ring, where the target is a dotted path to a piece.

PROTOTYPE -- not ratified. See `docs/plans/edits/apothecary-surface.md`.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..menu import Carries, Context, Intent, Ring, RingTooFull, carried_by, resolve

router = APIRouter(prefix="/menu", tags=["menu"])


class ResolveRequest(BaseModel):
    """What the ring was opened on, and which arrangement it was opened over."""

    context: Context
    site: Optional[str] = None


class Chosen(BaseModel):
    """A chosen option, and the arrangement it applies to."""

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
    """The lists a ring is built from: arrangements, groups, words.

    Read fresh on every call. Held once at import, a ring would offer whatever
    existed when the server started -- and the arrangements a person cares about
    are the ones they made since.
    """
    from ..api import _site_store
    from ..vocabulary.starter import starter_words

    groups: List[str] = []
    site = _site(name)
    if site is not None:
        groups = sorted({child.category for child in site.children if child.category})
    return {
        "site_names": sorted(_site_store.names()),
        "groups": groups,
        "words": starter_words().names(),
    }


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
            words=lists["words"],
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


@router.post("/intent", response_model=Carried)
def carry_out(chosen: Chosen) -> Carried:
    """Carry out a chosen option, or say who does, or refuse.

    Three answers and no fourth. The one that matters is the refusal: an option
    with nothing behind it has to come back as a refusal naming itself, because
    the alternative is a wedge that can be pressed for ever with no effect and no
    complaint.
    """
    from ..api import _find_node_by_path, _job_store, _site_payload, _site_store

    action = chosen.intent.action
    try:
        who = carried_by(action)
    except KeyError as unknown:
        raise HTTPException(status_code=400, detail=str(unknown).strip('"')) from None

    if who is Carries.UNBUILT:
        raise HTTPException(
            status_code=501,
            detail=(
                f"{action!r} is on the ring and nothing carries it out yet. This "
                "is a refusal rather than a silent no-op, so the wedge cannot "
                "look like it worked."
            ),
        )

    if who is Carries.VIEWER:
        return Carried(
            action=action,
            carried_by=who.value,
            did="nothing here; this one is about what is on screen",
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
        )

    if action == "render-stl":
        name = _needs_site(chosen)
        site = _site(name)
        path = chosen.intent.context.targets[0] if chosen.intent.context.targets else ""
        node = _find_node_by_path(site, path) if path else None
        if node is None:
            raise HTTPException(status_code=404, detail=f"Node {path!r} not found in site {name!r}")
        # Resolved here rather than taken on trust, so a wedge standing on a node
        # that has gone comes back as a refusal instead of a URL that 404s later.
        # The bytes themselves stay on the route that already serves them: this
        # answer says what to fetch, having checked that there is something there.
        return Carried(
            action=action,
            carried_by=who.value,
            did=f"found {path} in {name}; its shape is at /sites/{name}/nodes/{path}/stl",
        )

    # Reachable only by classifying an action as the server's and not writing the
    # arm that carries it out. Refused rather than returning a Carried that says
    # nothing happened, which is what the UNBUILT answer above is for.
    raise HTTPException(
        status_code=500,
        detail=(
            f"{action!r} is written down as the server's and has no arm here. "
            "Either give it one or classify it as not built yet."
        ),
    )
