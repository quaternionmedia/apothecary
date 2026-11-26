"""The last half hour of each machine's polls, kept so a graph can be drawn from them.

``devices.notify_status`` is where every poll lands, whoever made it: a Machine's own
auto-poll, the Site's refresh, a loop's experiment or the deck. Each one hands this
module the numbers a graph draws -- a printer's hotend and bed, each as read and as
asked for, and a router's spindle speed and feed -- as one ``Reading``, kept per port
for ``KEPT_S`` and at most ``KEPT`` of them. Nothing here asks a machine for anything:
a port no one polls has no new readings, and a graph of it says how old its last is.

``devices.forget_port`` forgets a port's readings with its last poll, so the board
plugged in next on that port does not inherit another's history.
"""

from __future__ import annotations

import threading
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Deque, Dict, List, Optional, Tuple

KEPT_S = 1800.0  # half an hour of readings per port
SAME_S = 0.5  # a poll this soon after the last kept is not kept: two pages polling at once
KEPT = int(KEPT_S / SAME_S)  # and never more than this many

Heat = Optional[Tuple[float, float]]  # (as read, as asked for); asked for 0 is off


@dataclass(frozen=True)
class Reading:
    """One poll's numbers, at the time the poll was made (seconds since the epoch)."""

    at: float
    state: str
    hotend: Heat = None
    bed: Heat = None
    spindle_rpm: Optional[float] = None
    feed: Optional[float] = None

    def to_json(self) -> dict:
        return {
            "at": self.at,
            "state": self.state,
            "hotend": list(self.hotend) if self.hotend else None,
            "bed": list(self.bed) if self.bed else None,
            "spindle_rpm": self.spindle_rpm,
            "feed": self.feed,
        }


_KEPT: Dict[str, Deque[Reading]] = {}
_LOCK = threading.Lock()


def _epoch(at: Optional[datetime]) -> float:
    if at is None:
        return datetime.now(timezone.utc).timestamp()
    if at.tzinfo is None:
        at = at.replace(tzinfo=timezone.utc)
    return at.timestamp()


def _heat(heater) -> Heat:
    if heater is None:
        return None
    return (float(heater.actual), float(heater.target))


def reading_of(status) -> Optional[Reading]:
    """What of ``status`` a graph draws, or None for a poll that read nothing (offline)."""
    if getattr(status, "state", None) == "offline":
        return None
    hotends = getattr(status, "hotends", None) or []
    spindle = getattr(status, "spindle", None)
    return Reading(
        at=_epoch(getattr(status, "polled_at", None)),
        state=str(getattr(status, "state", "") or ""),
        hotend=_heat(hotends[0]) if hotends else None,
        bed=_heat(getattr(status, "bed", None)),
        spindle_rpm=(float(spindle.rpm) if spindle.on else 0.0) if spindle is not None else None,
        feed=getattr(status, "feed", None),
    )


def record(status) -> None:
    """``status``'s numbers kept for its port. A poll as old as the newest kept, or older,
    is a reading already kept (a held reading handed on again), and one within
    ``SAME_S`` after it says nothing a graph can show: neither is kept."""
    reading = reading_of(status)
    if reading is None:
        return
    with _LOCK:
        kept = _KEPT.setdefault(status.port, deque(maxlen=KEPT))
        if kept and reading.at - kept[-1].at < SAME_S:
            return
        kept.append(reading)
        while kept and reading.at - kept[0].at > KEPT_S:
            kept.popleft()


def history(
    port: Optional[str], window_s: float = KEPT_S, now: Optional[float] = None
) -> List[Reading]:
    """``port``'s readings of the last ``window_s`` seconds, oldest first."""
    if not port:
        return []
    with _LOCK:
        kept = list(_KEPT.get(port, ()))
    if not kept:
        return []
    since = (now if now is not None else datetime.now(timezone.utc).timestamp()) - window_s
    return [r for r in kept if r.at >= since]


def forget(port: str) -> None:
    with _LOCK:
        _KEPT.pop(port, None)


def reset() -> None:
    """Every port's readings forgotten: between tests."""
    with _LOCK:
        _KEPT.clear()
