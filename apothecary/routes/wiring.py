"""A site's bench as carlos reads a rig: ``apothecary/wiring/``'s doors.

Plain ``def``, since finding the ports shells out to the toolchains, which
runs in the threadpool rather than on the event loop; none touches a port the
scan does not already:

- ``GET /sites/{s}/wiring``: ``{site, patch, evidence, states, unplaced}`` --
  the ``carlos.patch`` document, how each of its modules is known, the state of
  each module and lead, and the nodes with a board or a sketch that have no
  device to be.
- ``GET /sites/{s}/wiring/patch``: the document alone, as carlos's Import
  reads a file.
- ``POST /sites/{s}/wiring/send``: the wiring sent to carlos now, at the address
  ``serve --carlos`` or the family's table gives it; ``{sent, answer}``, a 409 when no
  carlos is named and a 502 when carlos refused it or did not answer.

With a carlos named, a follower sends ``APOTHECARY_CARLOS_SITE``'s wiring (the
garage's when unset) at the start and whenever it changes: ``start_following`` and
``stop_following``, from the app's lifespan.
"""

from __future__ import annotations

import os
import threading
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException

from .. import sites, surfaces
from ..family import hub
from ..firmware import devices as firmware_devices
from ..firmware.bindings import bindings_for_site
from ..firmware.toolchains import ToolchainError
from ..wiring import carlos
from ..wiring.patch import Wiring, wiring_for_site

router = APIRouter()

_follower: Optional[carlos.Follower] = None


def _hold(body: Dict[str, Any]) -> Dict[str, Any]:
    """A hold, through the family's hub, so it is in the hub's audit; the last sent of
    each site kept, with what came of it (``CARLOS_HOLDS``)."""
    outcome = hub.deliver(carlos.CARLOS, body["cue"], body["action"])
    site = body["cue"].get("number")
    try:
        answer = carlos.answer_of(outcome, hub.carlos_at() or "")
    except carlos.CarlosError as exc:
        _held(site, body, None, str(exc))
        raise
    _held(site, body, answer, None)
    return answer


# What carlos was last asked to hold for each site, as a surface (apothecary/surfaces.py):
# kept as each hold is sent through the hub, and said changed then. Gone when the
# server stops; carlos's own state is carlos's (its GET /family/state).
CARLOS_HOLDS = "carlos_holds"
_HELD: Dict[str, Dict[str, Any]] = {}
_HELD_LOCK = threading.Lock()


def _held(site: Optional[str], body: Dict[str, Any], answer, error: Optional[str]) -> None:
    record = {
        "site": site,
        "sent_at": datetime.now(timezone.utc).isoformat(),
        "action": body["action"],
        "answer": answer,
        "error": error,
    }
    with _HELD_LOCK:
        _HELD[site or ""] = record
    surfaces.changed(CARLOS_HOLDS, key=site, body=record)


def _holds_kept(words: Dict[str, str]) -> Dict[str, Any]:
    with _HELD_LOCK:
        held = dict(_HELD)
    return {"holds": [r for s, r in sorted(held.items()) if words.get("site") in (None, s)]}


surfaces.register(
    surfaces.Surface(
        name=CARLOS_HOLDS,
        frame="none",
        about="what carlos was last asked to hold for each site, and what it answered",
        snapshot=_holds_kept,
        takes=("site",),
        tells=True,
        owner=__name__,
    )
)


def _wiring(name: str) -> Wiring:
    site = sites.store.get(name)
    try:
        found = firmware_devices.detected_devices()
    except ToolchainError:
        found = []
    return wiring_for_site(name, site, bindings_for_site(name, site, devices=found), found)


def hold_action(name: str) -> Dict[str, Any]:
    """What carlos is handed to hold the site's wiring as it is now."""
    return carlos.hold_body(_wiring(name))["action"]


@router.get("/sites/{name}/wiring")
def site_wiring(name: str) -> Dict[str, Any]:
    """The site's bench as a ``carlos.patch``, with the evidence, the states and the unplaced."""
    return _wiring(name).model_dump(mode="json")


@router.get("/sites/{name}/wiring/patch")
def site_wiring_patch(name: str) -> Dict[str, Any]:
    """The ``carlos.patch`` document alone."""
    return _wiring(name).patch


@router.post("/sites/{name}/wiring/send")
def send_site_wiring(name: str) -> Dict[str, Any]:
    """The site's wiring sent to carlos now, through the family's hub."""
    url = hub.carlos_at()
    if url is None:
        raise HTTPException(409, detail="no carlos to send to: serve --carlos names one")
    body = carlos.hold_body(_wiring(name))
    try:
        answer = _hold(body)
    except carlos.CarlosError as exc:
        raise HTTPException(502, detail=str(exc)) from None
    return {"sent": url, "answer": answer}


def start_following() -> None:
    """Follow the bench to carlos, when one is named."""
    global _follower
    url = hub.carlos_at()
    if url is None or _follower is not None:
        return
    site = os.environ.get(carlos.SITE_ENV) or carlos.DEFAULT_SITE
    _follower = carlos.Follower(url, lambda: _wiring(site), deliver=_hold)
    _follower.start()


def stop_following() -> None:
    global _follower
    if _follower is not None:
        _follower.stop()
        _follower = None
