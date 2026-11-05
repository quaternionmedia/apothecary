"""A working space as the evidence log has it (``apothecary/evidence/``).

- ``GET /sites/{s}/evidence?at=&since=``: the ``apothecary.evidence`` document
  for the site: every subject the log has said of, each property's value at
  ``at`` (now, unless given) with its sources, origins and evidence, and what
  moved since ``since`` (an hour before ``at``, unless given). A moment with no
  time zone is UTC.
- ``GET /sites/{s}/evidence/printers``: the printers the Working space opens on,
  each a board pinned in the site drives, as the next door answers each.
- ``GET /sites/{s}/evidence/printers/{path}``: what the Working space watches
  for a printer: the port its board answers on (null when none does), the
  cameras that look at it, each with the browser device it was told, so the
  page keeps a frame set from those of its own with each poll, and how much
  its kept frames take of their budget.
- ``PUT /sites/{s}/evidence/printers/{path}/budget`` ``{gb}``: that budget set;
  past it, the oldest frames are forgotten as the next are kept.
- ``GET /evidence/polls/{id}``: one poll an observation rests on, every line
  the printer sent, from the space that holds it.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from ..evidence import frames, log

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


def _watched(name: str, site, path: str, found) -> Dict[str, Any]:
    """A printer's port, the cameras that look at it, and its kept frames' size."""
    from ..api import status_bearer_for
    from ..firmware import devices as firmware_devices
    from ..firmware.bindings import device_for_identity
    from ..vision import cameras

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
    subject = f"{name}:{path}"
    size = frames.sizes(name).get(subject, {"bytes": 0, "frames": 0})
    return {
        "site": name,
        "path": path,
        "subject": subject,
        "port": port,
        "cameras": looking,
        "frames": {
            "frames": size["frames"],
            "bytes": size["bytes"],
            "budget": frames.budget(name, subject),
        },
    }


def _found():
    from ..firmware import devices as firmware_devices
    from ..firmware.toolchains import ToolchainError

    try:
        return firmware_devices.detected_devices()
    except ToolchainError:
        return []


def _printer_or_404(name: str, path: str):
    """The site, when ``path`` is one of its machines (a printer or a router: a node
    that carries a machine's status); 404 otherwise."""
    from ..api import MACHINE_STATUSES, _find_node_by_path, _get_site_or_404

    site = _get_site_or_404(name)
    node = _find_node_by_path(site, path)
    if node is None or node.status not in MACHINE_STATUSES:
        raise HTTPException(status_code=404, detail=f"{path} is no machine of {name}")
    return site


@router.get("/sites/{name}/evidence/printers")
def printers_watched(name: str) -> Dict[str, Any]:
    """Each machine a board pinned in the site drives -- its printers and its routers,
    sorted -- as the Working space opens on one."""
    from ..api import _get_site_or_404, printers_in, routers_in

    site = _get_site_or_404(name)
    found = _found()
    machines = sorted({*printers_in(name), *routers_in(name)})
    return {"site": name, "printers": [_watched(name, site, p, found) for p in machines]}


@router.get("/sites/{name}/evidence/printers/{path}")
def printer_watched(name: str, path: str) -> Dict[str, Any]:
    """A printer's port and the cameras that look at it, for the page to keep frames with."""
    return _watched(name, _printer_or_404(name, path), path, _found())


class Budget(BaseModel):
    """A printer's frame budget, in gigabytes."""

    model_config = ConfigDict(extra="forbid")

    gb: float = Field(..., gt=0, le=10000, allow_inf_nan=False)


@router.put("/sites/{name}/evidence/printers/{path}/budget")
def printer_budget(name: str, path: str, body: Budget) -> Dict[str, Any]:
    """A printer's frame budget set; the oldest frames past it go as the next are kept."""
    site = _printer_or_404(name, path)
    frames.set_budget(name, f"{name}:{path}", int(body.gb * 1e9))
    return _watched(name, site, path, _found())


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
