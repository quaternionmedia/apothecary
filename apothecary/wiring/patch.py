"""A site's bench as a ``carlos.patch`` document, with how each module is known.

``carlos.patch`` version 3 is carlos's interchange format: modules, the
connections between their sockets (the output end first), groups, how the rack
is drawn and its MIDI bindings, with any field it does not define refused. This
writes one from the site's tree, what ``bindings_for_site`` says of it, and the
boards answering on ports.

The declared rig is the site as drawn: a node that names firmware or has a
device pinned to it (a binding row) is expected plugged in, with a USB lead to
the computer. So the document has

- a module for every node whose part draws a device in the catalogue, its id
  the node's dotted path, plugged in or not -- a board lying on the bench is in
  the rig before it is plugged in, and expected only once it has a row;
- a module for every board answering on a port that no row has, its id
  ``usb:`` and its identity, typed by what its port says (``catalogue.BY_FQBN``);
- the computer, ``host``, once any lead runs to it;
- a USB lead to the computer from every expected board, seen or not, and from
  every board answering on a port.

The document says what is drawn. How apothecary knows each module -- the port,
the identity, the binding, what was flashed -- is ``Evidence`` beside it, since
carlos would refuse it inside; and each module's and each lead's state is a
``State``, a level and the lines that say it, which carlos draws without
reading. A node that names firmware or has a device pinned to it, and whose
part draws no device in the catalogue, is ``Unplaced``: on the bench, with no
type to be.

Pure: the tree, the rows and the boards found are arguments, so nothing here
touches a port.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from ..firmware.bindings import walk_paths
from ..firmware.models import DeviceInfo, NodeBinding
from ..hierarchy import Assembly
from . import catalogue

FORMAT = "carlos.patch"
VERSION = 3

# The computer's module id. A node path is a dotted name, and no site has a
# top-level node called this.
HOST_MODULE = "host"
# A board no node names is ``usb:<its identity>``.
UNNAMED_PREFIX = "usb:"

# How much a state asks of a person, least first: carlos colours by it.
LEVELS = ("none", "ok", "warn", "fault")


class Evidence(BaseModel):
    """How apothecary knows one module of the patch."""

    module: str  # the module's id: the node's dotted path, or usb:<identity>
    device: str  # its catalogue id
    part_ref: Optional[str] = None
    expected: bool = False  # the site as drawn expects it plugged in
    connected: bool = False  # a board answering on a port now
    port: Optional[str] = None
    identity: Optional[str] = None  # DeviceInfo.identity: the MAC, the bridge's serial, or the port
    binding_source: Optional[str] = None  # "manual" | "sketch" | None, as NodeBinding has it
    sketch: Optional[str] = None  # the sketch the node names
    flashed: Optional[str] = None  # the sketch apothecary last put on the board
    source_changed: bool = False  # edited since it was flashed
    build_changed: bool = False  # built since, and never uploaded
    note: Optional[str] = None


class State(BaseModel):
    """What one module or lead is, as a level and the lines that say it."""

    level: str = "none"  # one of LEVELS
    says: List[str] = Field(default_factory=list)

    def at_least(self, level: str) -> None:
        if LEVELS.index(level) > LEVELS.index(self.level):
            self.level = level


class LeadState(State):
    source: Dict[str, str]
    target: Dict[str, str]


class ModuleState(State):
    """A module's state, and a state of its own for any of its controls: one a
    picture could not read, say, by its parameter's name."""

    controls: Dict[str, State] = Field(default_factory=dict)


class States(BaseModel):
    modules: Dict[str, ModuleState] = Field(default_factory=dict)
    connections: List[LeadState] = Field(default_factory=list)


class Unplaced(BaseModel):
    """A node with a board, or a sketch, whose part draws no catalogued device."""

    path: str
    part_ref: Optional[str] = None
    sketch_ref: Optional[str] = None
    port: Optional[str] = None
    why: str


class Wiring(BaseModel):
    """The document, and what stands beside it."""

    site: str
    patch: Dict[str, Any]
    evidence: List[Evidence] = Field(default_factory=list)
    states: States = Field(default_factory=States)
    unplaced: List[Unplaced] = Field(default_factory=list)


def _module(module_id: str, device: str) -> Dict[str, Any]:
    return {"id": module_id, "type": device, "view": "front", "parameters": {}}


def _evidence(path: str, device: str, node: Assembly, row: Optional[NodeBinding]) -> Evidence:
    known = Evidence(module=path, device=device, part_ref=node.part_ref)
    if row is None:
        known.note = "names no firmware and has no device pinned to it"
        return known
    known.expected = True
    known.binding_source = row.binding_source
    known.identity = row.identity
    known.sketch = row.sketch
    known.note = row.note
    if row.device is not None:
        known.connected = True
        known.port = row.device.port
    expected = row.expected
    if expected is not None and expected.record is not None:
        known.flashed = expected.record.sketch
        known.source_changed = expected.source_changed
        known.build_changed = expected.build_changed
    return known


def _identity_kind(identity: str, device: Optional[DeviceInfo]) -> str:
    if device is not None and device.mac and device.mac.lower() == identity.lower():
        return "its MAC"
    if (
        device is not None
        and device.serial_number
        and device.serial_number.lower() == identity.lower()
    ):
        return "its USB serial number"
    return "its port"


def _state(known: Evidence, row: Optional[NodeBinding]) -> ModuleState:
    """A board's four states: present or absent, firmware, and how it is known (its
    lead's is the lead's own)."""
    state = ModuleState()
    device = row.device if row is not None else None
    # Present or absent.
    if not known.expected:
        state.says.append("on the bench: not expected plugged in")
    elif known.connected:
        state.at_least("ok")
        state.says.append(f"present: answering on {known.port}")
    else:
        state.at_least("fault")
        state.says.append("absent: expected, and not answering")
    # Firmware.
    printer = device.printer if device is not None else None
    if printer is not None:
        state.says.append(f"firmware: {printer.firmware_name}, as it answered M115")
    elif known.flashed:
        if row is not None and row.expected is not None and row.expected.sketch_missing:
            state.at_least("warn")
            state.says.append(f"firmware: {known.flashed}, whose sketch is no longer here")
        elif known.source_changed:
            state.at_least("warn")
            state.says.append(f"firmware: {known.flashed}, flashed from an older source")
        elif known.build_changed:
            state.at_least("warn")
            state.says.append(f"firmware: {known.flashed}, with a newer build not uploaded")
        elif known.sketch and known.sketch != known.flashed:
            state.at_least("warn")
            state.says.append(f"firmware: {known.flashed}, where the node names {known.sketch}")
        else:
            state.says.append(f"firmware: {known.flashed}, as flashed")
    elif known.sketch:
        if known.connected:
            state.at_least("warn")
        state.says.append(f"firmware: {known.sketch} never flashed from here")
    # A printer as its last poll found it, while the Machine polls it.
    if row is not None and row.printer_status is not None:
        _printing(state, row.printer_status)
    # How it is known.
    if known.binding_source == "manual":
        state.says.append(f"known by: pinned, by {_identity_kind(known.identity or '', device)}")
    elif known.binding_source == "sketch":
        state.says.append(
            f"known by: the board {known.flashed or known.sketch} was last flashed to"
        )
    else:
        state.says.append("known by: the site's drawing")
    return state


def _heat(name: str, heater) -> str:
    return f"{name} {heater.actual:.0f}/{heater.target:.0f} °C"


def _printing(state: ModuleState, status) -> None:
    """A printer's state, its job's progress and its heaters, as one poll found them:
    the lines printer monitoring adds, each poll being one look."""
    doing = status.state
    if status.sd_printing and status.sd_progress is not None:
        doing += f", {status.sd_progress:.0%} of its job"
        if status.print_time_s is not None:
            doing += f", {status.print_time_s // 60} min in"
    if status.state in ("offline", "maintenance"):
        state.at_least("warn")
    when = status.polled_at.strftime("%H:%M:%S")
    state.says.append(f"printer: {doing}, as polled at {when}")
    heaters = [_heat("hotend", h) for h in status.hotends]
    if status.bed is not None:
        heaters.append(_heat("bed", status.bed))
    if heaters:
        state.says.append("heaters: " + ", ".join(heaters))


def _unnamed(device: DeviceInfo) -> ModuleState:
    state = ModuleState(level="warn")
    state.says.append(f"unexpected: answering on {device.port}, and no node names it")
    if device.printer is not None:
        state.says.append(f"firmware: {device.printer.firmware_name}, as it answered M115")
    match = device.board_name or device.fqbn
    state.says.append(
        f"known by: its port, which arduino-cli matches to {match}"
        if match
        else "known by: its port alone"
    )
    return state


def wiring_for_site(
    site_name: str,
    site: Assembly,
    rows: List[NodeBinding],
    devices: Optional[List[DeviceInfo]] = None,
) -> Wiring:
    """The site's bench as a ``carlos.patch``, with the evidence, the states and the
    unplaced. ``devices`` are the boards answering on ports; one no row has is
    unexpected."""
    by_path = {row.path: row for row in rows}
    host_jack = catalogue.usb_jack(catalogue.HOST)
    modules: List[Dict[str, Any]] = []
    connections: List[Dict[str, Any]] = []
    wiring = Wiring(site=site_name, patch={})

    def lead(module_id: str, device: str, seen: Optional[str]) -> None:
        jack = catalogue.usb_jack(device)
        if jack is None:
            return
        source = {"module": module_id, "jack": jack}
        target = {"module": HOST_MODULE, "jack": host_jack}
        connections.append({"source": source, "target": target})
        state = LeadState(source=source, target=target)
        if seen:
            state.at_least("ok")
            state.says.append(f"seen: answering on {seen}")
        else:
            state.at_least("fault")
            state.says.append("declared: the board is not answering")
        wiring.states.connections.append(state)

    claimed = set()
    for path, node in walk_paths(site):
        row = by_path.get(path)
        if row is not None and row.device is not None:
            claimed.add(row.device.port)
        device = catalogue.device_of(node.part_ref)
        if device is None:
            if row is not None:
                wiring.unplaced.append(
                    Unplaced(
                        path=path,
                        part_ref=node.part_ref,
                        sketch_ref=node.sketch_ref,
                        port=row.device.port if row.device else None,
                        why=(
                            f"part {node.part_ref!r} draws no catalogued device"
                            if node.part_ref
                            else "no part says which device this is"
                        ),
                    )
                )
            continue
        modules.append(_module(path, device))
        known = _evidence(path, device, node, row)
        wiring.evidence.append(known)
        wiring.states.modules[path] = _state(known, row)
        if known.expected:
            lead(path, device, known.port)

    for found in devices or []:
        if found.port in claimed:
            continue
        module_id = UNNAMED_PREFIX + found.identity
        device = catalogue.device_by_port(found.fqbn)
        modules.append(_module(module_id, device))
        wiring.evidence.append(
            Evidence(
                module=module_id,
                device=device,
                connected=True,
                port=found.port,
                identity=found.identity,
                note="answering on a port no node names",
            )
        )
        wiring.states.modules[module_id] = _unnamed(found)
        lead(module_id, device, found.port)

    if connections:
        modules.append(_module(HOST_MODULE, catalogue.HOST))
        wiring.states.modules[HOST_MODULE] = ModuleState(
            level="ok", says=["the computer apothecary runs on"]
        )
    wiring.patch = {
        "format": FORMAT,
        "version": VERSION,
        "name": site_name,
        "modules": modules,
        "connections": connections,
        "groups": [],
        "display": {"mode": "minimal"},
        "midi": [],
    }
    return wiring
