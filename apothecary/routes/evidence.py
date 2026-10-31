"""A working space as the evidence log has it (``apothecary/evidence/``).

- ``GET /sites/{s}/evidence?at=&since=``: the ``apothecary.evidence`` document
  for the site: every subject the log has said of, each property's value at
  ``at`` (now, unless given) with its sources, origins and evidence, and what
  moved since ``since`` (an hour before ``at``, unless given). A moment with no
  time zone is UTC.
- ``GET /sites/{s}/evidence/printers/{path}``: what the Working space watches
  for a printer: the port its board answers on (null when none does) and the
  cameras that look at it, each with the browser device it was told, so the
  page keeps a frame set from those of its own with each poll.
- ``GET /evidence/polls/{id}``: one poll an observation rests on, every line
  the printer sent, from the space that holds it.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query

from ..evidence import log

router = APIRouter(tags=["evidence"])


def _utc(moment: Optional[datetime]) -> Optional[datetime]:
    if moment is None or moment.tzinfo is not None:
        return moment
    return moment.replace(tzinfo=timezone.utc)


@router.get("/sites/{name}/evidence")
def site_evidence(
    name: str, at: Optional[datetime] = None, since: Optional[datetime] = None
) -> Dict[str, Any]:
    """The site as every kind of evidence has it, at a moment, and what changed in a span."""
    from ..api import _get_site_or_404

    _get_site_or_404(name)
    at, since = _utc(at), _utc(since)
    if at is not None and since is not None and since > at:
        raise HTTPException(status_code=422, detail="since is after at")
    return log.document(name, at=at, since=since)


@router.get("/sites/{name}/evidence/printers/{path}")
def printer_watched(name: str, path: str) -> Dict[str, Any]:
    """A printer's port and the cameras that look at it, for the page to keep frames with."""
    from ..api import PRINTER_STATUSES, _find_node_by_path, _get_site_or_404, status_bearer_for
    from ..firmware import devices as firmware_devices
    from ..firmware.bindings import device_for_identity
    from ..firmware.toolchains import ToolchainError
    from ..vision import cameras

    site = _get_site_or_404(name)
    node = _find_node_by_path(site, path)
    if node is None or node.status not in PRINTER_STATUSES:
        raise HTTPException(status_code=404, detail=f"{path} is no printer of {name}")
    try:
        found = firmware_devices.detected_devices()
    except ToolchainError:
        found = []
    port = None
    for binding in firmware_devices.get_state().bindings(name):
        if status_bearer_for(site, binding.path) == path:
            device = device_for_identity(binding.identity, found)
            port = device.port if device is not None else None
            if port:
                break
    root = path.split(".", 1)[0]
    looking = [
        {"name": cam.name, "device_id": cam.device.id if cam.device else None}
        for cam in cameras.records(name)
        if cameras.looks_at(name, site, cam.pose) == root
    ]
    return {
        "site": name,
        "path": path,
        "subject": f"{name}:{path}",
        "port": port,
        "cameras": looking,
    }


@router.get("/evidence/polls/{poll_id}")
def evidence_poll(
    poll_id: str, space: str = Query(..., min_length=1, max_length=64)
) -> Dict[str, Any]:
    """One poll by its id, with every line the printer sent."""
    try:
        found = log.find_poll(space, poll_id)
    except ValueError:
        raise HTTPException(status_code=404, detail=f"no space {space!r}") from None
    if found is None:
        raise HTTPException(status_code=404, detail=f"no poll {poll_id} in {space}")
    return found
