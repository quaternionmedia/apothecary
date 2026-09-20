"""Which board belongs to which scene node.

A scene node names its firmware in one of two ways: ``part_ref`` (it *is* a
registered part, whose folder under ``parts/`` may hold a sketch) or
``sketch_ref`` (a bare devkit that only runs a sketch). From there the board
is found by the by-sketch rule -- the device Apothecary most recently flashed
that sketch onto -- unless the user pinned a specific device to the node
(``FirmwareState.set_binding``), which always wins.

This module is pure: it takes the site tree and the detected devices as
arguments so it never imports the API layer (which imports the firmware
router) and so tests can feed it fixtures.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Tuple

from ..hierarchy import Assembly
from ..projects.parts.skeleton import ROOT
from .devices import FirmwareState, detected_devices, expected_firmware, get_state, last_statuses
from .models import DeviceInfo, FlashRecord, NodeBinding, PrinterStatus, SketchInfo
from .service import BUILD_ROOT
from .sketches import discover_sketches


def walk_paths(site: Assembly) -> Iterator[Tuple[str, Assembly]]:
    """``(dotted path, node)`` for every node beneath the site root.

    Same traversal order as the API's ``_assembly_tree`` (children, then
    additions, then subtractions), so every path yielded here is one the
    viewer displays and ``_find_node_by_path`` resolves.
    """

    def visit(node: Assembly, prefix: str) -> Iterator[Tuple[str, Assembly]]:
        for child in [*node.children, *node.additions, *node.subtractions]:
            path = f"{prefix}.{child.name}" if prefix else child.name
            yield path, child
            yield from visit(child, path)

    yield from visit(site, "")


def sketch_for_node(
    node: Assembly, sketches: List[SketchInfo], parts_dir: Path = ROOT / "parts"
) -> Tuple[Optional[SketchInfo], Optional[str]]:
    """The sketch a node's ``sketch_ref``/``part_ref`` names, or why there is none.

    An exact sketch name wins. Otherwise the reference is matched against the
    sketch's folder path under ``parts/`` (a ``part_ref`` is the SCAD stem,
    e.g. ``snowplow`` for ``parts/rc/snowplow/``), which must be unique.
    """
    ref = node.sketch_ref or node.part_ref
    if not ref:
        return None, None
    exact = next((s for s in sketches if s.name == ref), None)
    if exact:
        return exact, None
    by_folder = []
    for s in sketches:
        try:
            folders = s.path.relative_to(parts_dir).parts
        except ValueError:
            folders = s.path.parts
        if ref in folders:
            by_folder.append(s)
    if len(by_folder) == 1:
        return by_folder[0], None
    if by_folder:
        return None, "ambiguous: " + ", ".join(sorted(s.name for s in by_folder))
    return None, f"no sketch for '{ref}'"


def same_device(identity: str, port: str, device: Optional[DeviceInfo] = None) -> bool:
    """Whether a pin's ``identity`` names the board on ``port``.

    It does when it is that port, a path that resolves to the same device
    node (``/dev/serial/by-id/...``, a udev name), or -- given what is known
    about the device there -- its MAC or its USB bridge's serial number.
    The last is what survives a replug that renumbers the port.
    """
    if identity == port:
        return True
    if identity.startswith("/") and os.path.realpath(identity) == os.path.realpath(port):
        return True
    if device is None:
        return False
    wanted = identity.lower()
    if device.mac and device.mac.lower() == wanted:
        return True
    return bool(device.serial_number and device.serial_number.lower() == wanted)


def device_for_identity(identity: str, found: List[DeviceInfo]) -> Optional[DeviceInfo]:
    for d in found:
        if same_device(identity, d.port, d):
            return d
    return None


def bindings_for_site(
    site_name: str,
    site: Assembly,
    *,
    devices: Optional[List[DeviceInfo]] = None,
    state: Optional[FirmwareState] = None,
    sketches: Optional[List[SketchInfo]] = None,
    build_root: Optional[Path] = None,
    statuses: Optional[Dict[str, PrinterStatus]] = None,
) -> List[NodeBinding]:
    """One row per node that names firmware or has a device pinned to it.

    ``devices=None`` asks arduino-cli; pass ``[]`` when the toolchain is
    missing so callers degrade instead of failing. ``statuses`` (per port)
    defaults to the newest polls; nothing here touches a port.
    """
    state = state or get_state()
    found = detected_devices(state=state) if devices is None else devices
    sketches = discover_sketches() if sketches is None else sketches
    build_root = build_root or BUILD_ROOT
    statuses = last_statuses() if statuses is None else statuses
    manual = {b.path: b for b in state.bindings(site_name)}

    # expected_firmware() hashes sketch sources; do it once per device, not per node.
    expected_by_port: Dict[str, object] = {}

    def expected_for(d: DeviceInfo):
        if d.port not in expected_by_port:
            expected_by_port[d.port] = expected_firmware(d, build_root, state)
        return expected_by_port[d.port]

    flashes: Optional[List[FlashRecord]] = None  # loaded lazily, only if a node needs it

    rows: List[NodeBinding] = []
    for path, node in walk_paths(site):
        pin = manual.get(path)
        sketch, note = sketch_for_node(node, sketches)
        if pin is None and not (node.sketch_ref or node.part_ref):
            continue
        row = NodeBinding(
            path=path,
            name=node.name,
            part_ref=node.part_ref,
            sketch_ref=node.sketch_ref,
            sketch=sketch.name if sketch else None,
            baud=sketch.baud if sketch else 115200,
            display=sketch.display if sketch else None,
            note=note,
        )
        if pin is not None:
            row.binding_source = "manual"
            row.identity = pin.identity
            row.device = device_for_identity(pin.identity, found)
            if row.device is None:
                row.note = f"{pin.identity} not connected"
        elif sketch is not None:
            running = []
            for d in found:
                exp = expected_for(d)
                if exp.record and exp.record.sketch == sketch.name:
                    running.append((exp.record.flashed_at, d, exp))
            running.sort(key=lambda t: t[0], reverse=True)
            if running:
                _, row.device, row.expected = running[0]
                row.binding_source = "sketch"
                row.identity = row.device.identity
                row.candidates = [d.port for _, d, _ in running[1:]]
            else:
                if flashes is None:
                    flashes = state.flashes()
                last = max(
                    (r for r in flashes if r.sketch == sketch.name),
                    key=lambda r: r.flashed_at,
                    default=None,
                )
                if last is not None:
                    row.binding_source = "sketch"
                    row.identity = last.identity
                    row.note = f"last flashed to {last.port} -- not connected"
                else:
                    row.note = "never flashed from apothecary"
        if row.device is not None and row.expected is None:
            row.expected = expected_for(row.device)
        if row.device is not None and row.device.printer is not None:
            row.printer_status = statuses.get(row.device.port)
        rows.append(row)
    return rows
