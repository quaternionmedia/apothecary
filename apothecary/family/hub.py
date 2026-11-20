"""The irl family's hub: hearth's coordinator, its table and what it says it is.

The family's own members are hosted here (``members``), and a camera is read from
the page, whatever the table says. The table names the rest: it is ``family.json`` in
the state folder, in the shape hearth's ``from_table`` reads: ``{"members": {name:
url}, "pull": [name], "timeout": seconds}``, each optional, and ``start``, the members
the hub starts itself (``beside``). ``serve --carlos`` adds carlos to it as a push
member. A member is on this machine or it is left out and said, as the process's guard
would refuse it anyway. The table is read afresh at each use, and a changed table starts
a new coordinator, whose audit starts empty.
"""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter
from hearth import coordinator

from .. import surfaces
from ..state_folder import state_dir
from ..version import __version__
from ..wiring.carlos import CARLOS, carlos_url, loopback_url
from . import beside
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


def table() -> Dict[str, Any]:
    """The table as written: what ``apothecary family`` lists."""
    return _table()


def _on_this_machine(members: Any) -> Any:
    """The members reached on this machine; any other is said and left out."""
    if not isinstance(members, dict):
        return members  # the coordinator's reading of the table says what is wrong with it
    kept = {}
    for name, url in members.items():
        try:
            kept[name] = loopback_url(url)
        except (AttributeError, TypeError, ValueError):
            beside.say_once(
                f"family: {TABLE}.members {name} = {url!r} is not on this machine, "
                "so it is left out"
            )
    return kept


def settings() -> Dict[str, Any]:
    """The table as the coordinator is given it: this machine's members, carlos and the
    members a page reads."""
    table = _table()
    members = _on_this_machine(table.get("members") or {})
    if isinstance(members, dict):
        members.update({spec.name: spec.url for spec in beside.specs(table.get("start"), TABLE)})
    named = carlos_url()
    if named and isinstance(members, dict):
        members[CARLOS] = named
    pull = table.get("pull") or []
    if isinstance(pull, list):
        pull = [*pull, *(name for name in PAGE_MEMBERS if name not in pull)]
    return {**table, "members": members, "pull": pull}


# The hub's own state, as a surface (apothecary/surfaces.py): its members and each recent
# delivery's outcome, as ``GET /family/`` answers and the Family view draws them. Told as a
# cue is fired, as each delivery ends and as a pull member reads its action.
FAMILY_SURFACE = "family"
# What of the coordinator says a thing has happened to its members or deliveries: ``fire``
# queues them, ``_push`` and ``_call`` end one, ``read`` delivers a pull member's. Two of
# the four are private to the hearth library, which is pinned, so a surface that rests on
# them says when one is not there (``not_told``) rather than going quiet.
_TOLD_BY = ("fire", "_push", "_call", "read")


def not_told(hub: Any) -> List[str]:
    """The methods of ``_TOLD_BY`` that ``hub`` (a coordinator, or its class) lacks: the
    changes it cannot be heard to make."""
    return [name for name in _TOLD_BY if not callable(getattr(hub, name, None))]


def _gap(missing: List[str]) -> str:
    return (
        f"family: hearth's Coordinator has no {', '.join(missing)}, which the hub wraps to tell "
        f"its surface (apothecary/family/hub.py, _TOLD_BY): the `family` surface still reads, "
        f"but its stream says nothing when {', '.join(missing)} would have run; a hearth "
        "update renamed them, so pin hearth to the version that has them or change _TOLD_BY"
    )


def _body(hub: Any) -> Dict[str, Any]:
    """What the surface says of ``hub``: its snapshot, and which methods tell its changes and
    which were missing (with why the stream is quiet for them)."""
    missing = getattr(hub, "_not_told", [])
    told = {"by": [name for name in _TOLD_BY if name not in missing], "missing": list(missing)}
    if missing:
        told["warning"] = _gap(missing)
    return {**hub.snapshot(), "told": told}


def _told(hub: coordinator.Coordinator) -> coordinator.Coordinator:
    """``hub`` that says its state changed after each of ``_TOLD_BY``; the body is made
    only while someone follows the surface. A method that is not there is not wrapped, and
    is said, in the log and in the surface's own snapshot. Tellings are made one at a time,
    so the stream never offers a snapshot older than one it offered before."""
    missing = not_told(hub)
    hub._not_told = missing
    if missing:
        log.error(_gap(missing))
    one_at_a_time = threading.Lock()

    def wrap(original):
        def wrapper(*args, **kwargs):
            try:
                return original(*args, **kwargs)
            finally:
                with one_at_a_time:
                    surfaces.changed(FAMILY_SURFACE, key=HUB, body=lambda: _body(hub))

        return wrapper

    for name in _TOLD_BY:
        if name not in missing:
            setattr(hub, name, wrap(getattr(hub, name)))
    return hub


surfaces.register(
    surfaces.Surface(
        name=FAMILY_SURFACE,
        frame="none",
        about="the family's hub: its members and each recent delivery's outcome",
        snapshot=lambda words: _body(running()),
        tells=True,
        owner=__name__,
    )
)


def running() -> coordinator.Coordinator:
    """The running coordinator, started anew when its table has changed."""
    global _running, _read
    wanted = settings()
    with _lock:
        if _running is None or wanted != _read:
            if _running is not None:
                _running.close()
            _running = _told(
                coordinator.from_table(wanted, local=hosted.receivers(), table=TABLE)
            )
            _read = wanted
        return _running


def start() -> None:
    """At the app's start: the members beside the hub, and a word in the log if the
    coordinator lacks a method the hub's surface is told by."""
    missing = not_told(coordinator.Coordinator)
    if missing:
        log.error(_gap(missing))
    beside.start(_table().get("start"), TABLE)


def close() -> None:
    """At the app's stop."""
    global _running, _read
    beside.stop()
    with _lock:
        if _running is not None:
            _running.close()
        _running, _read = None, None


def carlos_at() -> Optional[str]:
    """Where the family's carlos answers, however it is named."""
    return running().members.get(CARLOS)


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
