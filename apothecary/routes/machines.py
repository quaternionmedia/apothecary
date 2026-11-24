"""A site's machines, and each one's plan (``apothecary/machine_plans.py``).

- ``GET /sites/{name}/machines``: the nodes of the site drawn from a part that is a
  machine, each with its kind, whether or not a board is pinned to it.
- ``GET /sites/{name}/makers?part=``: every site's machines that make a piece of the
  site or a registered part, as Make lists them -- those whose board is connected
  first (``api.makers_of``).
- ``GET /sites/{name}/machines/{path}``: what a job on that machine could name -- its
  kind and what that kind offers, the parts and pieces of the site and then every
  registered part -- in the shape
  ``GET /jobs/choices`` answers for a board's port, with no port; where it stands, as
  ``/firmware/printers/where`` says of a pinned board's printer; and its plan.
- ``GET /sites/{name}/machines/{path}/missing``: why its board is not found -- each
  board pinned there that no port holds, how far it got (``firmware/missing.py``),
  and every serial port plugged in now.
- ``PUT /sites/{name}/machines/{path}/plan``: keep the part it will make and the kept
  file of its kind that makes it. ``DELETE`` lets the plan go.

Plain ``def``: each reads the site and the state folder; none touches a port.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from .. import jobs, machine_plans, sites
from ..firmware.bindings import walk_paths
from ..hierarchy import find_node_by_path

router = APIRouter(prefix="/sites", tags=["machines"])

NODE_PATH = r"^[A-Za-z0-9_][A-Za-z0-9_.\-]*$"


class PlanRequest(BaseModel):
    part: Optional[str] = Field(None, pattern=NODE_PATH)
    file_id: Optional[str] = Field(None, max_length=120)


def _machine(name: str, path: str):
    """The site, the machine node at ``path`` and its kind; 404 for a node that is not
    there, 400 for one that is no machine."""
    site = sites.store.get(name)
    node = find_node_by_path(site, path)
    if node is None:
        raise HTTPException(status_code=404, detail=f"no node {path!r} in {name}")
    kind = machine_plans.kind_of_part(node.part_ref) if node.part_ref else None
    if kind is None:
        raise HTTPException(
            status_code=400,
            detail=f"{path} in {name} is no machine: it is drawn from no part that is a printer or a router",
        )
    return site, node, kind


def machines_of(site, kind: Optional[str] = None) -> list[dict]:
    """The site's machines, of ``kind`` when it is named."""
    return [
        {"path": path, "kind": found, "part_ref": node.part_ref}
        for path, node in walk_paths(site)
        if node.part_ref
        and (found := machine_plans.kind_of_part(node.part_ref))
        and kind in (None, found)
    ]


@router.get("/{name}/machines")
def site_machines(name: str):
    return machines_of(sites.store.get(name))


@router.get("/{name}/makers")
def site_makers(
    name: str,
    part: str = Query(
        ..., pattern=NODE_PATH, description="a piece of the site by its path, or a part's name"
    ),
):
    """The machines of every site that make ``part``, as Make lists them from this
    site (``api.makers_of``): those whose board is connected first."""
    from ..api import makers_of

    try:
        return makers_of(name, part)
    except KeyError:
        raise HTTPException(
            status_code=404, detail=f"{part!r} is no piece of {name} and no part's name"
        ) from None


@router.get("/{name}/machines/{path}")
def site_machine(name: str, path: str):
    from ..api import describe_for_view, parts_of

    site, node, kind = _machine(name, path)
    return {
        "machine": {"kind": kind, "port": "", "identity": None, "path": path},
        "site": name,
        "operations": [
            {"kind": op.kind, "label": op.label, "inputs": list(op.inputs)}
            for op in jobs.operations(kind)
        ],
        "parts": [p.model_dump(mode="json") for p in parts_of(name, site, path)],
        "where": describe_for_view(site, path, node, is_printer=True),
        "plan": _plan_json(name, path),
    }


def _plan_json(name: str, path: str) -> Optional[dict]:
    plan = machine_plans.load(name, path)
    return plan.model_dump(mode="json") if plan is not None else None


@router.put("/{name}/machines/{path}/plan")
def keep_plan(name: str, path: str, body: PlanRequest):
    from ..api import parts_of

    site, _, kind = _machine(name, path)
    if body.part and body.part not in {p.path for p in parts_of(name, site, path)}:
        raise HTTPException(
            status_code=422,
            detail=f"{body.part!r} is no part or piece of {name}, and no part's name",
        )
    try:
        plan = machine_plans.save(name, path, kind, body.part, body.file_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return plan.model_dump(mode="json")


@router.delete("/{name}/machines/{path}/plan")
def let_plan_go(name: str, path: str):
    _machine(name, path)
    return {"cleared": machine_plans.clear(name, path)}


@router.get("/{name}/machines/{path}/missing")
def machine_missing(name: str, path: str):
    """Why the machine's board is not found: each board pinned at the machine or
    beneath it that the port scan names on no port, with the checks a board gets
    through on its way to being found (``firmware/missing.py``), and every serial
    port plugged in now with the node a pin names it for. No port is opened, and no
    scan started: a fresh one is the page's to ask for (``GET /sites/{name}/devices?fresh=1``)."""
    from ..firmware import devices, missing
    from ..firmware.bindings import bindings_for_site
    from ..firmware.toolchains import ToolchainError

    site, _, kind = _machine(name, path)
    # The newest scan however old, so asking every few seconds starts none; the
    # USB list and the serial engine's port list are read now (a board on its
    # port and not in the scan is scanned for afresh by the page, once, through
    # its model's rescan, so the page's own rows name it too).
    try:
        found = devices.detected_devices(any_age=True)
    except ToolchainError:
        found = []
    rows = bindings_for_site(name, site, devices=found)
    mine = [r for r in rows if r.path == path or r.path.startswith(path + ".")]
    state = devices.get_state()
    pins = {b.path: b for b in state.bindings(name)}
    usb = missing.usb_devices()
    listed = devices.ports_now()
    expected = []
    for row in mine:
        if row.device is not None or not row.identity:
            continue
        pin = pins.get(row.path)
        last_port, last, seen = state.last_found(row.identity)
        expected.append(
            {
                "pinned_at": row.path,
                "how": row.binding_source,
                **missing.explain(
                    row.identity,
                    (pin.kind if pin else None) or kind,
                    usb=usb,
                    listed=listed,
                    last_port=last_port,
                    last=last,
                    seen=seen,
                ),
            }
        )
    return {
        "site": name,
        "path": path,
        "kind": kind,
        "connected": [
            {"path": r.path, "port": r.device.port} for r in mine if r.device is not None
        ],
        "expected": expected,
        "plugged": missing.plugged(
            usb, listed, {r.device.port: r.path for r in rows if r.device is not None}
        ),
        "usb_read": usb is not None,
    }
