"""The irl family's hub: hearth's coordinator, its table and what it says it is.

The family's own members are hosted here (``members``), and a camera is read from
the page, whatever the table says. The table names the rest: it is ``family.json`` in
the state folder, in the shape hearth's ``from_table`` reads: ``{"members": {name:
url}, "pull": [name], "timeout": seconds}``, each optional. ``serve --carlos`` adds
carlos to it as a push member. A member is on this machine or it is left out and said,
as the process's guard would refuse it anyway. The table is read afresh at each use,
and a changed table starts a new coordinator, whose audit starts empty.
"""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter
from hearth import coordinator

from ..firmware.devices import state_dir
from ..version import __version__
from ..wiring.carlos import CARLOS, carlos_url, loopback_url
from . import members as hosted
from .members import FAMILY

log = logging.getLogger(__name__)

HUB = "apothecary"
TABLE = "family.json"

# A camera's device is a browser's, so a page reads what the camera is to do.
PAGE_MEMBERS = ["camera"]

# How long past a member's own timeout a delivery waited for is given up on.
GRACE_SECONDS = 1.0

_lock = threading.Lock()
_running: Optional[coordinator.Coordinator] = None
_read: Optional[Dict[str, Any]] = None


def table_file() -> Path:
    return state_dir() / TABLE


def _table() -> Dict[str, Any]:
    """The table as written, or an empty one when it is missing or will not read."""
    path = table_file()
    try:
        table = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as exc:
        log.warning("family: %s does not read, so it is ignored: %s", path, exc)
        return {}
    if not isinstance(table, dict):
        log.warning("family: %s is not a table, so it is ignored", path)
        return {}
    return table


def _on_this_machine(members: Any) -> Any:
    """The members reached on this machine; any other is said and left out."""
    if not isinstance(members, dict):
        return members  # the coordinator's reading of the table says what is wrong with it
    kept = {}
    for name, url in members.items():
        try:
            kept[name] = loopback_url(url)
        except (AttributeError, TypeError, ValueError):
            log.warning(
                "family: %s.members %s = %r is not on this machine, so it is left out",
                TABLE,
                name,
                url,
            )
    return kept


def settings() -> Dict[str, Any]:
    """The table as the coordinator is given it: this machine's members, carlos and the
    members a page reads."""
    table = _table()
    members = _on_this_machine(table.get("members") or {})
    named = carlos_url()
    if named and isinstance(members, dict):
        members[CARLOS] = named
    pull = table.get("pull") or []
    if isinstance(pull, list):
        pull = [*pull, *(name for name in PAGE_MEMBERS if name not in pull)]
    return {**table, "members": members, "pull": pull}


def running() -> coordinator.Coordinator:
    """The running coordinator, started anew when its table has changed."""
    global _running, _read
    wanted = settings()
    with _lock:
        if _running is None or wanted != _read:
            if _running is not None:
                _running.close()
            _running = coordinator.from_table(wanted, local=hosted.receivers(), table=TABLE)
            _read = wanted
        return _running


def close() -> None:
    """At the app's stop."""
    global _running, _read
    with _lock:
        if _running is not None:
            _running.close()
        _running, _read = None, None


def identity() -> Dict[str, Any]:
    """What this hub says it is, at ``GET /family/identity``."""
    return coordinator.identity(HUB, FAMILY, __version__)


def router() -> APIRouter:
    """``/family/``, ``/family/identity`` and ``/family/members/<name>``."""
    return coordinator.router(running, identity, table=TABLE)


def members() -> List[str]:
    """Every member, however it is reached."""
    return sorted(running().snapshot()["members"])


def deliver(member: str, cue: Dict[str, Any], action: Dict[str, Any]) -> Dict[str, Any]:
    """Fire one member's action and wait for it: its outcome, as the audit keeps it.

    Nothing is raised for a member down or refusing, which is the outcome's to say.
    """
    hub = running()
    hub.fire(cue, {member: action})
    hub.wait(hub.timeout + GRACE_SECONDS)
    for outcome in reversed(hub.snapshot()["last"]):
        if outcome["member"] == member and outcome["cue"] == cue:
            return outcome
    return {"member": member, "cue": cue, "done": False, "status": None, "error": None}
