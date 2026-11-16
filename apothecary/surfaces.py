"""Surfaces: what the server already knows of each thing a page shows, read in one way.

A surface is something the server keeps and a page draws -- a machine's last poll, the
jobs, a projector's picture, a site's lighting levels, the pictures, a whiteboard's
marks, what carlos was last asked to hold. The module that owns it declares it here
(``register``), in a few lines beside the code that keeps it: its name, the frame its
coordinates are in, how to read it now (``snapshot``, asked with the words it takes:
a site, a machine's path, a view) and whether its owner says when it changes.

**Frames.** ``site_mm``: a site's millimetres, z up. ``bed_mm``: a machine's bed's
millimetres, its working volume as a file counts it (``apothecary/projector.py``).
``picture_fractions``: fractions of a picture, across and down from its top left.
``none``: no coordinates.

**Changes.** An owner that learns of a change -- a job begun or ended, a poll someone
made, levels put, a picture kept, a word on a mark, a hold sent -- says so
(``changed``), and every reader following the surface hears it (``subscribe``). Nothing
here asks anything of anything: a surface no owner says has changed is not relayed,
however long a reader follows it, and a poll is made by whoever polls -- a Machine, the
world, the projector's page -- never by a reader of this module. ``changed`` builds an
event's body only while someone follows the surface.

**Contributed.** A member of the family's hub may say what it found about a surface --
alfred watching a camera's frames, joe a performance -- as an observation: who says it,
when it held, the surface and the frame it is about, and a body (``contribute``). The
newest ``KEPT`` of each surface are kept in the state folder, written whole under one
lock, and are a surface of their own, ``contributed``.

A prototype: no ratified record governs it.
"""

from __future__ import annotations

import asyncio
import itertools
import json
import logging
import threading
from collections import deque
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Deque, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field, ValidationError, field_validator

from .state_folder import state_dir, write_whole

log = logging.getLogger(__name__)

FRAMES = {
    "site_mm": "a site's millimetres, z up",
    "bed_mm": "a machine's bed's millimetres: its working volume as a file counts it",
    "picture_fractions": "fractions of a picture, across and down from its top left",
    "none": "no coordinates",
}
EVENT = "apothecary.surface-change/1"
CONTRIBUTED = "contributed"
CONTRIBUTED_FORMAT = "apothecary.contributed/1"
# The newest observations kept of each surface, and how large one's body may be.
KEPT = 200
BODY_MOST = 16 * 1024
# How many changes a reader that does not keep up may fall behind before the oldest go.
WAITING_MOST = 256
NAME = r"^[a-z][a-z0-9_]{0,39}$"
MEMBER = r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$"


class UnknownSurface(KeyError):
    """No surface by that name."""


class Unasked(ValueError):
    """A surface read with words it does not take, or without one it needs."""


@dataclass(frozen=True)
class Surface:
    """One surface, as its owner declares it."""

    name: str
    frame: str
    about: str
    snapshot: Callable[[Dict[str, str]], Any]
    takes: Tuple[str, ...] = ()  # the words its snapshot is asked with
    needs: Tuple[str, ...] = ()  # those of them it cannot answer without
    tells: bool = False  # whether its owner says when it changes
    owner: str = ""  # the module that declared it


_SURFACES: Dict[str, Surface] = {}
_LOCK = threading.Lock()


def register(surface: Surface) -> Surface:
    """Declare a surface. A name is one owner's; declared again the same, it is kept."""
    if surface.frame not in FRAMES:
        raise ValueError(f"{surface.frame!r} is no frame; the frames are {', '.join(FRAMES)}")
    if not set(surface.needs) <= set(surface.takes):
        raise ValueError(f"{surface.name} needs words it does not take")
    with _LOCK:
        had = _SURFACES.get(surface.name)
        if had is not None and had.owner != surface.owner:
            raise ValueError(f"{surface.name!r} is already {had.owner}'s surface")
        _SURFACES[surface.name] = surface
    return surface


def get(name: str) -> Surface:
    with _LOCK:
        found = _SURFACES.get(name)
    if found is None:
        known = ", ".join(names())
        raise UnknownSurface(f"no surface is called {name!r}; the surfaces are {known}")
    return found


def names() -> List[str]:
    with _LOCK:
        return sorted(_SURFACES)


def listed() -> List[Surface]:
    with _LOCK:
        return [_SURFACES[name] for name in sorted(_SURFACES)]


def described(surface: Surface) -> Dict[str, Any]:
    """A surface as its list says it: everything but how it is read."""
    return {
        "name": surface.name,
        "frame": surface.frame,
        "about": surface.about,
        "takes": list(surface.takes),
        "needs": list(surface.needs),
        "tells": surface.tells,
        "owner": surface.owner,
    }


def read(name: str, words: Dict[str, str]) -> Any:
    """A surface now, asked with ``words``: ``Unasked`` for a word it does not take or
    one it needs and was not given."""
    surface = get(name)
    strange = sorted(set(words) - set(surface.takes))
    if strange:
        takes = ", ".join(surface.takes) or "nothing"
        raise Unasked(f"{name} is not asked by {', '.join(strange)}; it takes {takes}")
    missing = [w for w in surface.needs if not words.get(w)]
    if missing:
        raise Unasked(f"{name} is read for a {' and a '.join(missing)}: name one")
    return surface.snapshot(dict(words))


# --- changes, relayed -----------------------------------------------------------------------


class Subscription:
    """One reader following some surfaces (every one, for ``names`` None): the changes
    since it last looked, at most ``WAITING_MOST``, the oldest let go and counted as
    ``missed`` when it falls further behind. Made on the event loop that reads it; a
    change is handed to it from any thread."""

    def __init__(self, names: Optional[List[str]], loop: asyncio.AbstractEventLoop):
        self.names = set(names) if names is not None else None
        self.loop = loop
        self.waiting: Deque[Dict[str, Any]] = deque()
        self.missed = 0
        self.ready = asyncio.Event()

    def wants(self, name: str) -> bool:
        return self.names is None or name in self.names

    def _put(self, event: Dict[str, Any]) -> None:
        if len(self.waiting) >= WAITING_MOST:
            self.waiting.popleft()
            self.missed += 1
        self.waiting.append(event)
        self.ready.set()

    def offer(self, event: Dict[str, Any]) -> None:
        with suppress(RuntimeError):  # its loop has closed: the reader has gone
            self.loop.call_soon_threadsafe(self._put, event)

    async def next(self, timeout: float) -> Tuple[List[Dict[str, Any]], int]:
        """The changes waiting, and how many were let go, after waiting up to ``timeout``
        seconds for one; nothing when none came."""
        if not self.waiting:
            with suppress(asyncio.TimeoutError):
                await asyncio.wait_for(self.ready.wait(), timeout)
        self.ready.clear()
        events, self.waiting = list(self.waiting), deque()
        missed, self.missed = self.missed, 0
        return events, missed

    def close(self) -> None:
        with _LOCK:
            if self in _FOLLOWING:
                _FOLLOWING.remove(self)


_FOLLOWING: List[Subscription] = []
_SEQ = itertools.count(1)


def subscribe(names: Optional[List[str]] = None) -> Subscription:
    """Follow ``names`` (every surface, for None) from the running event loop."""
    for name in names or []:
        get(name)
    following = Subscription(names, asyncio.get_running_loop())
    with _LOCK:
        _FOLLOWING.append(following)
    return following


def listening(name: str) -> bool:
    """Whether any reader follows the surface ``name`` now."""
    with _LOCK:
        return any(s.wants(name) for s in _FOLLOWING)


def changed(name: str, key: Optional[str] = None, body: Any = None) -> Optional[Dict[str, Any]]:
    """Say that the surface ``name`` changed, at ``key`` (a port, a job's id, a site,
    a machine): every reader following it hears it, with ``body`` -- a value, or a
    function of none that makes one, called only while someone follows. The event
    sent, or None when nobody follows. Never raises into the owner that says it."""
    try:
        surface = get(name)
        with _LOCK:
            readers = [s for s in _FOLLOWING if s.wants(name)]
        if not readers:
            return None
        value = body() if callable(body) else body
        event = {
            "format": EVENT,
            "seq": next(_SEQ),
            "surface": name,
            "frame": surface.frame,
            "key": key,
            "at": datetime.now(timezone.utc).isoformat(),
            "body": value,
        }
        for reader in readers:
            reader.offer(event)
        return event
    except Exception:  # the change is the owner's; relaying it is not worth its failure
        log.exception("surfaces: a change of %s was not relayed", name)
        return None


# --- what the family's members contribute ------------------------------------------------------


class Observation(BaseModel):
    """What a member of the family's hub found about a surface: who says it, when it held,
    the surface and the frame it is about, which of it (``key``), and a body."""

    format: str = CONTRIBUTED_FORMAT
    by: str = Field(..., pattern=MEMBER)
    at: datetime
    surface: str = Field(..., pattern=NAME)
    frame: str
    key: Optional[str] = Field(None, max_length=200)
    body: Dict[str, Any]
    recorded_at: Optional[datetime] = None

    @field_validator("frame")
    @classmethod
    def _a_frame(cls, frame: str) -> str:
        if frame not in FRAMES:
            raise ValueError(f"{frame!r} is no frame; the frames are {', '.join(FRAMES)}")
        return frame

    @field_validator("body")
    @classmethod
    def _small(cls, body: Dict[str, Any]) -> Dict[str, Any]:
        if len(json.dumps(body, default=str)) > BODY_MOST:
            raise ValueError(f"a body is at most {BODY_MOST // 1024} KB of JSON")
        return body


_KEPT_LOCK = threading.Lock()


def _kept_file() -> Path:
    return state_dir() / "surfaces" / "contributed.json"


def _kept() -> Dict[str, List[Observation]]:
    """Every surface's observations kept, oldest first; a file missing or unreadable holds
    none, and one that does not read is left out."""
    try:
        data = json.loads(_kept_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    kept: Dict[str, List[Observation]] = {}
    rows = data.get("observations", []) if isinstance(data, dict) else []
    for row in rows if isinstance(rows, list) else []:
        try:
            said = Observation.model_validate(row)
        except ValidationError:
            continue
        kept.setdefault(said.surface, []).append(said)
    return kept


def contribute(said: Observation) -> Observation:
    """Keep what a member found about a surface, the newest ``KEPT`` of that surface;
    ``UnknownSurface`` for a surface no owner has declared. Relayed as a change of
    ``contributed``, keyed by the surface it is about."""
    get(said.surface)
    said = said.model_copy(update={"recorded_at": datetime.now(timezone.utc)})
    with _KEPT_LOCK:
        kept = _kept()
        held = kept.setdefault(said.surface, [])
        held.append(said)
        del held[:-KEPT]
        rows = [o.model_dump(mode="json") for name in sorted(kept) for o in kept[name]]
        write_whole(
            _kept_file(),
            json.dumps({"format": CONTRIBUTED_FORMAT, "observations": rows}, indent=2),
        )
    changed(CONTRIBUTED, key=said.surface, body=lambda: said.model_dump(mode="json"))
    return said


def contributed(words: Dict[str, str]) -> Dict[str, Any]:
    """The observations kept, newest first: of one surface, or by one member, when named."""
    found = [o for held in _kept().values() for o in held]
    if words.get("surface"):
        found = [o for o in found if o.surface == words["surface"]]
    if words.get("by"):
        found = [o for o in found if o.by == words["by"]]
    found.sort(key=lambda o: o.recorded_at or o.at, reverse=True)
    return {"observations": [o.model_dump(mode="json") for o in found]}


register(
    Surface(
        name=CONTRIBUTED,
        frame="none",
        about="what the family's members found about the other surfaces, each in its own frame",
        snapshot=contributed,
        takes=("surface", "by"),
        tells=True,
        owner=__name__,
    )
)


__all__ = [
    "CONTRIBUTED",
    "EVENT",
    "FRAMES",
    "KEPT",
    "Observation",
    "Subscription",
    "Surface",
    "UnknownSurface",
    "Unasked",
    "changed",
    "contribute",
    "contributed",
    "described",
    "get",
    "listed",
    "listening",
    "names",
    "read",
    "register",
    "subscribe",
]
