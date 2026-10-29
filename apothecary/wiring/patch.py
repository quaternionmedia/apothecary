"""A site's bench as a ``carlos.patch`` document, with how each module is known.

``carlos.patch`` version 3 is carlos's interchange format: modules, the
connections between their sockets (the output end first), groups, how the rack
is drawn and its MIDI bindings, with any field it does not define refused. This
writes one from the site's tree and what ``bindings_for_site`` says of it:

- a module for every node whose part draws a device in the catalogue, its id
  the node's dotted path, connected or not -- a board lying on the bench is in
  the rig before it is plugged in;
- the computer, ``host``, once any board is connected to it;
- a USB lead from each connected board's USB socket to the computer's.

The document says what is drawn. How apothecary knows each module -- the port,
the identity, the binding, what was flashed -- is ``Evidence`` beside it, since
carlos would refuse it inside. A node that names firmware or has a device pinned
to it, and whose part draws no device in the catalogue, is ``Unplaced``: on the
bench, with no type to be.

Pure: the tree and the rows are arguments, so nothing here touches a port.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from ..firmware.bindings import walk_paths
from ..firmware.models import NodeBinding
from ..hierarchy import Assembly
from . import catalogue

FORMAT = "carlos.patch"
VERSION = 3

# The computer's module id. A node path is a dotted name, and no site has a
# top-level node called this.
HOST_MODULE = "host"


class Evidence(BaseModel):
    """How apothecary knows one module of the patch."""

    module: str  # the module's id: the node's dotted path
    device: str  # its catalogue id
    part_ref: Optional[str] = None
    connected: bool = False  # a board answering on a port now
    port: Optional[str] = None
    identity: Optional[str] = None  # DeviceInfo.identity: the MAC, the bridge's serial, or the port
    binding_source: Optional[str] = None  # "manual" | "sketch" | None, as NodeBinding has it
    sketch: Optional[str] = None  # the sketch the node names
    flashed: Optional[str] = None  # the sketch apothecary last put on the board
    source_changed: bool = False  # edited since it was flashed
    build_changed: bool = False  # built since, and never uploaded
    note: Optional[str] = None


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
    unplaced: List[Unplaced] = Field(default_factory=list)


def _module(module_id: str, device: str) -> Dict[str, Any]:
    return {"id": module_id, "type": device, "view": "front", "parameters": {}}


def _evidence(path: str, device: str, node: Assembly, row: Optional[NodeBinding]) -> Evidence:
    known = Evidence(module=path, device=device, part_ref=node.part_ref)
    if row is None:
        known.note = "names no firmware and has no device pinned to it"
        return known
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


def wiring_for_site(site_name: str, site: Assembly, rows: List[NodeBinding]) -> Wiring:
    """The site's bench as a ``carlos.patch``, with the evidence and the unplaced."""
    by_path = {row.path: row for row in rows}
    host_jack = catalogue.usb_jack(catalogue.HOST)
    modules: List[Dict[str, Any]] = []
    connections: List[Dict[str, Any]] = []
    wiring = Wiring(site=site_name, patch={})
    for path, node in walk_paths(site):
        row = by_path.get(path)
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
        jack = catalogue.usb_jack(device)
        if known.connected and jack is not None:
            connections.append(
                {
                    "source": {"module": path, "jack": jack},
                    "target": {"module": HOST_MODULE, "jack": host_jack},
                }
            )
    if connections:
        modules.append(_module(HOST_MODULE, catalogue.HOST))
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
