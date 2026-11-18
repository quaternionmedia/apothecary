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

import json
import logging
import os
import threading
from contextlib import suppress
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException

from .. import sites, surfaces
from ..family import hub
from ..firmware import devices as firmware_devices
from ..firmware.bindings import bindings_for_site
from ..firmware.toolchains import ToolchainError
from ..state_folder import state_dir, write_whole
from ..wiring import carlos
from ..wiring.patch import Wiring, wiring_for_site

log = logging.getLogger(__name__)
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
# kept as each hold is sent through the hub, said changed then, and kept in the state
# folder (``carlos-holds.json``, written whole under one lock) so a restart reads them
# back. carlos's own state is carlos's (its GET /family/state).
CARLOS_HOLDS = "carlos_holds"
HOLDS_FILE = "carlos-holds.json"
HOLDS_FORMAT = "apothecary.carlos-holds/1"
_HELD: Optional[Dict[str, Dict[str, Any]]] = None
_HELD_FROM: Optional[Path] = None  # the file _HELD was read from
_HELD_LOCK = threading.Lock()


def _holds_file() -> Path:
    return state_dir() / HOLDS_FILE


def _held_now() -> Dict[str, Dict[str, Any]]:
    """The holds kept, read from the state folder the first time (and again when the
    folder is another); call with ``_HELD_LOCK`` held. A file that does not read is
    moved aside beside itself and the holds start empty: the next hold writes a new one."""
    global _HELD, _HELD_FROM
    path = _holds_file()
    if _HELD is not None and _HELD_FROM == path:
        return _HELD
    held: Dict[str, Dict[str, Any]] = {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        rows = data["holds"]
        if not isinstance(rows, dict) or not all(isinstance(r, dict) for r in rows.values()):
            raise ValueError("it holds no table of holds")
        held = rows
    except FileNotFoundError:
        pass
    except (OSError, ValueError, KeyError, TypeError) as exc:
        aside = path.with_name(f"{path.stem}.unreadable-{datetime.now(timezone.utc):%Y%m%dT%H%M%S}.json")
        with suppress(OSError):
            path.replace(aside)
        log.error("carlos holds: %s did not read (%s): kept aside as %s", path, exc, aside.name)
    _HELD, _HELD_FROM = held, path
    return held


def _held(site: Optional[str], body: Dict[str, Any], answer, error: Optional[str]) -> None:
    record = {
        "site": site,
        "sent_at": datetime.now(timezone.utc).isoformat(),
        "action": body["action"],
        "answer": answer,
        "error": error,
    }
    with _HELD_LOCK:
        held = _held_now()
        held[site or ""] = record
        try:
            write_whole(
                _holds_file(), json.dumps({"format": HOLDS_FORMAT, "holds": held}, indent=2)
            )
        except OSError as exc:  # the hold was sent: not keeping it is not worth its failure
            log.error("carlos holds: not kept in %s: %s", _holds_file(), exc)
    surfaces.changed(CARLOS_HOLDS, key=site, body=record)


def _holds_kept(words: Dict[str, str]) -> Dict[str, Any]:
    with _HELD_LOCK:
        held = dict(_held_now())
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
