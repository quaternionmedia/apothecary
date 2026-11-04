"""A printer's polls, as observations.

Every poll the server makes (``firmware/devices.printer_status``) passes
``STATUS_LISTENERS``; api.py registers ``record_poll`` there with the pins the
poll's port answers to. A poll is said of the subjects its pin names:

| Subject | Properties |
|---|---|
| the node the port is pinned to (``garage:printer_1.frame_system.mainboard``) | ``present``: the board answered |
| the node the poll drives, the nearest above the pin with a status (``garage:printer_1``) | ``state``, ``progress``, ``position``, ``filament`` |
| each heater of it (``…#heater:bed``, ``…#heater:hotend0``) | ``temperature``, ``target`` |
| each endstop of it (``…#endstop:x_min``) | ``endstop`` |
| a router's node, the same way | ``state``, ``machine_state``, ``position``, ``work_position``, ``pins`` |
| its spindle (``…#spindle:main``) | ``rpm``, ``target`` |

A port no pin names is a sighting, ``usb:<identity>``, in the ``_sightings``
space. Every observation is ``measured``, by the poll's commands, and rests on
the poll by its id and on the pin that attributes it.

Only what changed is written: a word when it changes, a number when it moves
past its tolerance, ``present`` at least once a minute while polled, so the
view can tell a quiet printer from one nobody is asking, and every value at
least every few hours, so the view need read back no further than a day. The poll an
observation rests on is written with it; a poll that wrote nothing is held for
a while in memory, so a frame kept with it can still name it (``keep``).
"""

from __future__ import annotations

import threading
from collections import OrderedDict
from datetime import datetime, timezone
from typing import Any, Dict, List, NamedTuple, Optional, Tuple

from ..firmware.models import GRBL, PrinterStatus
from ..stamped import stamp
from . import log
from .observation import By, Observation, Origin, Ref

BY = "printer poll: M105, M114, M27, M119, M31"
BY_GRBL = "router poll: ?, $G"
# How far a number moves before it is said again.
TOLERANCE = {"temperature": 1.0, "target": 0.0, "progress": 0.01, "rpm": 50.0, "feed": 50.0}
POSITION_TOLERANCE = {"x": 1.0, "y": 1.0, "z": 0.05, "e": 5.0}
# ``present`` is said again this often while a port is polled, changed or not,
# and everything else this often, so a day's files hold every value in force.
HEARTBEAT_S = 60.0
REFRESH_S = 6 * 3600.0
# Polls held in memory after they answer, for a frame kept with one.
HELD_POLLS = 64


class Pin(NamedTuple):
    """A pin a poll's port answers to: where it is, and the node the poll drives."""

    site: str
    path: str
    bearer: Optional[str]  # the nearest node at or above ``path`` with a status
    identity: str


def poll_id(status: PrinterStatus) -> str:
    """``20261031T101500.123-ttyFAKE1``: the poll's moment and its port."""
    leaf = status.port.rstrip("/").rsplit("/", 1)[-1] or status.port
    return f"{stamp(status.polled_at)}-{leaf}"


def _subjects(pin: Optional[Pin], identity: str) -> Tuple[str, str]:
    if pin is None:
        sighting = f"usb:{identity}"
        return sighting, sighting
    board = f"{pin.site}:{pin.path}"
    return board, (f"{pin.site}:{pin.bearer}" if pin.bearer else board)


def observations_of(
    status: PrinterStatus, pin: Optional[Pin], identity: str, now: Optional[datetime] = None
) -> List[Observation]:
    """Every observation one poll makes of the subjects its pin names."""
    now = now or datetime.now(timezone.utc)
    board, printer = _subjects(pin, identity)
    evidence = [Ref(kind="poll", id=poll_id(status))]
    if pin is not None:
        evidence.append(Ref(kind="pin", id=f"{pin.site}:{pin.path}"))
    origin = Origin(kind="measured", by=By(name=BY_GRBL if status.dialect == GRBL else BY))

    def said(subject: str, prop: str, value: Any, unit: Optional[str] = None) -> Observation:
        return Observation(
            subject=subject,
            property=prop,
            value=value,
            unit=unit,
            origin=origin,
            at=status.polled_at,
            recorded_at=now,
            evidence=evidence,
        )

    offline = status.state == "offline"
    out = [said(board, "present", not offline), said(printer, "state", status.state)]
    if offline:
        return out
    if status.sd_progress is not None:
        out.append(said(printer, "progress", round(status.sd_progress, 4), "fraction"))
    if status.position:
        out.append(said(printer, "position", dict(status.position), "mm"))
    if status.filament_present is not None:
        out.append(said(printer, "filament", status.filament_present))
    if status.machine_state is not None:
        out.append(said(printer, "machine_state", status.machine_state))
    if status.work_position:
        out.append(said(printer, "work_position", dict(status.work_position), "mm"))
    if status.spindle is not None:
        out.append(said(f"{printer}#spindle:main", "rpm", status.spindle.rpm, "rpm"))
        out.append(said(f"{printer}#spindle:main", "target", status.spindle.target, "rpm"))
    if status.feed is not None:
        out.append(said(printer, "feed", status.feed, "mm/min"))
    if status.dialect == GRBL:
        out.append(said(printer, "pins", sorted(status.pins)))
    heaters = [(f"hotend{i}", h) for i, h in enumerate(status.hotends)]
    if status.bed is not None:
        heaters.append(("bed", status.bed))
    for name, heater in heaters:
        out.append(said(f"{printer}#heater:{name}", "temperature", heater.actual, "°C"))
        out.append(said(f"{printer}#heater:{name}", "target", heater.target, "°C"))
    for name, value in sorted(status.endstops.items()):
        if name == "filament":
            continue  # the runout switch: ``filament`` above
        out.append(said(f"{printer}#endstop:{name}", "endstop", str(value).lower()))
    return out


def _moved(prop: str, before: Any, now: Any) -> bool:
    if prop in ("position", "work_position") and isinstance(before, dict) and isinstance(now, dict):
        return any(
            abs(float(now.get(axis, 0)) - float(before.get(axis, 0))) >= limit
            for axis, limit in POSITION_TOLERANCE.items()
        )
    limit = TOLERANCE.get(prop)
    if limit is not None and isinstance(before, (int, float)) and isinstance(now, (int, float)):
        return abs(now - before) > limit if limit else now != before
    return before != now


class Collector:
    """Polls into the log, writing only what changed."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # (space, subject, property) -> (the value last written, when it held)
        self._last: Dict[Tuple[str, str, str], Tuple[Any, datetime]] = {}
        # poll id -> (its record, the spaces it is said in, the spaces it is written in)
        self._held: "OrderedDict[str, Tuple[dict, List[str], set]]" = OrderedDict()

    def forget(self) -> None:
        with self._lock:
            self._last.clear()
            self._held.clear()

    def _due(self, space: str, each: Observation) -> bool:
        last = self._last.get((space, each.subject, each.property))
        if last is None:
            return True
        value, held = last
        again = HEARTBEAT_S if each.property == "present" else REFRESH_S
        quiet = (each.at - held).total_seconds() < again
        return not quiet or _moved(each.property, value, each.value)

    def take(self, status: PrinterStatus, pins: List[Pin], identity: str) -> str:
        """The poll's observations written in each space its pins name; its id."""
        pid = poll_id(status)
        record = {
            "id": pid,
            "port": status.port,
            "identity": identity,
            "polled_at": status.polled_at.isoformat(),
            "state": status.state,
            "raw": list(status.raw),
        }
        said = [(pin.site, pin) for pin in pins] or [(log.SIGHTINGS, None)]
        # The nodes the poll speaks of, as the frames kept with it are filed under.
        record["subjects"] = sorted({_subjects(pin, identity)[1] for _, pin in said})
        with self._lock:
            written: set = set()
            for space, pin in said:
                due = [o for o in observations_of(status, pin, identity) if self._due(space, o)]
                if not due:
                    continue
                log.append(space, log.POLLS, record, status.polled_at)
                log.write(space, due)
                # Taken as said once written: a write that failed is due again.
                for o in due:
                    self._last[(space, o.subject, o.property)] = (o.value, o.at)
                written.add(space)
            self._held[pid] = (record, [space for space, _ in said], written)
            while len(self._held) > HELD_POLLS:
                self._held.popitem(last=False)
        return pid

    def held(self, pid: str) -> Optional[dict]:
        """A poll this collector still holds: its record and the spaces it is said in."""
        with self._lock:
            found = self._held.get(pid)
            if found is None:
                return None
            record, spaces, _ = found
            return {
                "record": dict(record),
                "spaces": list(spaces),
                "subjects": list(record["subjects"]),
            }

    def keep(self, pid: str) -> List[str]:
        """The poll ``pid`` written to the log where it was not yet, so what rests
        on it can name it; the spaces it is in. Empty for a poll no longer held."""
        with self._lock:
            held = self._held.get(pid)
            if held is None:
                return []
            record, spaces, written = held
            for space in spaces:
                if space not in written:
                    log.append(
                        space, log.POLLS, record, datetime.fromisoformat(record["polled_at"])
                    )
                    written.add(space)
            return list(spaces)


COLLECTOR = Collector()


def record_poll(status: PrinterStatus, pins: List[Pin], identity: str) -> str:
    return COLLECTOR.take(status, pins, identity)
