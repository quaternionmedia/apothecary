"""The family's members hosted in its hub, on what apothecary already drives.

``machine`` is a printer or a router: ``home``, ``run`` {file, part}, ``pause``,
``resume``. ``board`` is a board a sketch runs on: ``flash`` {sketch, fqbn} and
``expect`` {hello}. An action names what it is for by the address the evidence log
uses, its ``node`` (``garage:printer_1.frame_system.mainboard``); ``{"home": true}``
will do where one machine is pinned, and ``port`` names a board no node has yet.

Each keeps apothecary's own bounds. A verb that moves a machine is refused with the
latch down, which a person arms in the Machine window, and so is anything for a port
a task is writing to; a refused cue changes nothing. The work runs after the answer,
one at a time in the order the cues came on a thread of the member's own, so the
answer is 202 and the member's state says how it ended.

Each is served under its name, ``/machine/family/*``, by hearth's own routes.
"""

from __future__ import annotations

import queue
import threading
import time
from collections import deque
from contextlib import suppress
from typing import Any, Callable, Deque, Dict, List, Optional, Tuple

import hearth
from fastapi import APIRouter, HTTPException
from hearth import web

from ..firmware import devices, gcode
from ..firmware.bindings import bindings_for_site, device_for_identity
from ..firmware.models import DeviceInfo, NodeBinding, TaskStatus
from ..firmware.sketches import find_sketch
from ..firmware.tasks import get_task_runner
from ..firmware.toolchains import ToolchainError
from ..version import __version__

FAMILY = "irl"

KEPT = 50  # how many ended pieces of work a member remembers
LISTEN_SECONDS = 3.0  # how long a board is listened to for its hello
TASK_LOOK_SECONDS = 0.1  # how often a flash's task is looked at

Work = Callable[[], Optional[Dict[str, Any]]]


class Hosted(hearth.Member):
    """A member whose work runs after its answer, one piece at a time."""

    family = FAMILY
    later = True

    def __init__(self) -> None:
        super().__init__(version=__version__)
        self._queue: "queue.SimpleQueue[Tuple[Dict[str, Any], Work]]" = queue.SimpleQueue()
        self._thread: Optional[threading.Thread] = None
        self._working: List[Dict[str, Any]] = []
        self._ended: Deque[Dict[str, Any]] = deque(maxlen=KEPT)

    def _then(self, verb: str, about: Dict[str, Any], work: Work) -> Callable[[], None]:
        """The change that queues ``work``: what ``understand`` hands back."""

        def change() -> None:
            piece = {"cue": self.cue, "verb": verb, **about}
            self._working.append(piece)
            self._queue.put((piece, work))
            if self._thread is None:
                self._thread = threading.Thread(
                    target=self._work, name=f"member-{self.name}", daemon=True
                )
                self._thread.start()

        return change

    def _work(self) -> None:
        while True:
            piece, work = self._queue.get()
            ended = dict(piece)
            try:
                ended.update(ok=True, **(work() or {}))
            except Exception as exc:  # the member's to say, in its state
                ended.update(ok=False, error=str(exc))
            with self._lock:
                self._working.remove(piece)
                self._ended.append(ended)
            self.changed()

    def state(self) -> Dict[str, Any]:
        return {
            "working": [dict(piece) for piece in self._working],
            "last": dict(self._ended[-1]) if self._ended else None,
        }

    def ended(self, cue: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """How the work of ``cue`` ended; None while it runs, or once it is forgotten."""
        with self._lock:
            return next((dict(e) for e in reversed(self._ended) if e["cue"] == cue), None)


def _one_verb(action: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
    """An action's verb and what it asks: true, or an object, says the same as none."""
    if len(action) != 1:
        raise hearth.Refused(f"one verb at a time, not {', '.join(sorted(action))}")
    verb, asked = next(iter(action.items()))
    if asked is True or asked is None:
        return verb, {}
    if not isinstance(asked, dict):
        raise hearth.Refused(f"{verb} takes an object, or true: not {hearth.shown(asked)}")
    return verb, asked


def _found() -> List[DeviceInfo]:
    try:
        return devices.detected_devices()
    except ToolchainError:
        return []


def _not_held(port: str) -> None:
    active = get_task_runner().active
    if active is not None and active.port == port:
        raise hearth.Refused(f"{port} is held: {active.title}")


class Machine(Hosted):
    """A printer or a router pinned to a node."""

    name = "machine"
    verbs = ("home", "run", "pause", "resume")

    @staticmethod
    def _pinned() -> Dict[str, str]:
        """Every machine pinned here: each one's node, and the port it is on now."""
        found = _found()
        pinned = {}
        for binding in devices.get_state().bindings():
            device = device_for_identity(binding.identity, found, binding.kind)
            if device is not None and device.printer is not None:
                pinned[f"{binding.site}:{binding.path}"] = device.port
        return pinned

    def _machine(self, asked: Dict[str, Any]) -> Tuple[str, str]:
        pinned = self._pinned()
        node = asked.get("node")
        if node is None and len(pinned) == 1:
            return next(iter(pinned.items()))
        if node is None:
            raise hearth.Refused(
                f"name the machine's node: {', '.join(sorted(pinned)) or 'none is pinned'}"
            )
        if node not in pinned:
            raise hearth.Refused(f"no machine is pinned at {hearth.shown(node)}")
        return node, pinned[node]

    def understand(self, action: Dict[str, Any]) -> Callable[[], None]:
        verb, asked = _one_verb(action)
        node, port = self._machine(asked)
        _not_held(port)
        if verb != "pause" and not gcode.get_printer_links().control.armed(port):
            raise hearth.Refused(f"{node}: {verb} moves the machine -- arm its control first")
        about = {"node": node}
        if verb == "home":
            return self._then(verb, about, lambda: self._home(port))
        if verb == "run":
            file_id = asked.get("file")
            if devices.print_file(str(file_id)) is None:
                raise hearth.Refused(f"no such kept file: {hearth.shown(file_id)}")
            part = asked.get("part")
            about["file"] = file_id
            return self._then(verb, about, lambda: self._run(port, file_id, part))
        job = devices.print_job(port)
        if job is None or job.finished is not None:
            raise hearth.Refused(f"{node}: no job is running")
        return self._then(verb, about, lambda: self._job(job, verb, port))

    @staticmethod
    def _home(port: str) -> Dict[str, Any]:
        line = devices.dialect_for(port).home
        said = devices.printer_control(port, line).lines
        # So what it did is in the log, for a step that waits on it. It has homed either way.
        with suppress(ToolchainError, OSError):
            devices.printer_status(port)
        return {"line": line, "said": said}

    @staticmethod
    def _run(port: str, file_id: str, part: Optional[str]) -> Dict[str, Any]:
        return {"job": devices.start_print(port, file_id, part=part).snapshot()["job_id"]}

    @staticmethod
    def _job(job: Any, verb: str, port: str) -> None:
        getattr(job, verb)()
        gcode.get_printer_links().control.renew(port)


class Board(Hosted):
    """A board a sketch runs on, at a node or on a port no node has yet."""

    name = "board"
    verbs = ("flash", "expect")

    @staticmethod
    def _row(node: Any, found: List[DeviceInfo]) -> NodeBinding:
        """What the site knows of ``node``, the board it names."""
        from ..api import _get_site_or_404

        site_name, _, path = str(node).partition(":")
        try:
            site = _get_site_or_404(site_name)
        except HTTPException:
            raise hearth.Refused(f"no site holds {hearth.shown(node)}") from None
        for row in bindings_for_site(site_name, site, devices=found):
            if row.path == path:
                return row
        raise hearth.Refused(f"no board or sketch is named at {hearth.shown(node)}")

    def _board(self, asked: Dict[str, Any]) -> Tuple[Optional[NodeBinding], DeviceInfo]:
        found = _found()
        row = self._row(asked["node"], found) if "node" in asked else None
        port = asked.get("port")
        if port is not None:
            device = next((d for d in found if d.port == port), None)
            if device is None:
                raise hearth.Refused(f"no board is on {hearth.shown(port)}")
            return row, device
        if row is None:
            raise hearth.Refused("name the board's node, or its port")
        if row.device is None:
            raise hearth.Refused(
                f"{asked['node']} has no board now: {row.note or 'nothing has been flashed there'}"
            )
        return row, row.device

    def understand(self, action: Dict[str, Any]) -> Callable[[], None]:
        verb, asked = _one_verb(action)
        row, device = self._board(asked)
        _not_held(device.port)
        named = asked.get("sketch") or (row.sketch if row else None)
        about = {"node": asked.get("node"), "port": device.port}
        if verb == "expect":
            hello = asked.get("hello") or named
            if not hello:
                raise hearth.Refused("expect names the hello it is to hear")
            about["hello"] = hello
            return self._then(verb, about, lambda: self._expect(device.port, hello))
        from ..firmware import service

        try:  # a name two sketches share is refused, in the words that say which
            sketch = find_sketch(str(named)) if named else None
            if sketch is None:
                raise hearth.Refused(f"no such sketch: {hearth.shown(named)}")
            fqbn = service.resolve_board(sketch, asked.get("fqbn") or device.fqbn)
        except ValueError as exc:
            raise hearth.Refused(str(exc)) from None
        about["sketch"] = sketch.id
        return self._then(verb, about, lambda: self._flash(sketch, fqbn, device.port))

    @staticmethod
    def _flash(sketch: Any, fqbn: Optional[str], port: str) -> Dict[str, Any]:
        from ..firmware import api as firmware_api

        task = get_task_runner().get(firmware_api.upload_sketch(sketch, fqbn, port)["id"])
        while task.status == TaskStatus.running:
            time.sleep(TASK_LOOK_SECONDS)
        if task.status != TaskStatus.succeeded:
            last = task.lines[-1] if task.lines else "it said nothing"
            raise RuntimeError(f"{task.title} {task.status.value}: {last}")
        return {"task": task.id}

    @staticmethod
    def _expect(port: str, hello: str) -> Dict[str, Any]:
        heard = devices.listen(port, LISTEN_SECONDS).running_sketch
        if heard != hello:
            raise RuntimeError(f"{port} said {heard or 'no hello'}, not {hello}'s")
        return {"heard": heard}


_hosted: Dict[str, Hosted] = {member.name: member for member in (Machine(), Board())}


def hosted(name: str) -> Optional[Hosted]:
    return _hosted.get(name)


def receivers() -> Dict[str, Callable[[Dict[str, Any]], Tuple[int, Dict[str, Any]]]]:
    """What the coordinator hands each hosted member its body through."""
    return {name: member.receive for name, member in _hosted.items()}


def routers() -> List[APIRouter]:
    """Each member's own routes, under its name."""
    served = []
    for name, member in _hosted.items():
        router = APIRouter(prefix=f"/{name}")
        router.include_router(web.router(member))
        served.append(router)
    return served
