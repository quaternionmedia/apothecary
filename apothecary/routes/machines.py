"""A site's machines, and each one's plan (``apothecary/machine_plans.py``).

- ``GET /sites/{name}/machines``: the nodes of the site drawn from a part that is a
  machine, each with its kind, whether or not a board is pinned to it.
- ``GET /sites/{name}/machines/{path}``: what a job on that machine could name -- its
  kind and what that kind offers, the parts and pieces of the site -- in the shape
  ``GET /jobs/choices`` answers for a board's port, with no port; where it stands, as
  ``/firmware/printers/where`` says of a pinned board's printer; and its plan.
- ``PUT /sites/{name}/machines/{path}/plan``: keep the part it will make and the kept
  file of its kind that makes it. ``DELETE`` lets the plan go.

Plain ``def``: each reads the site and the state folder; none touches a port.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .. import jobs, machine_plans
from ..firmware.bindings import walk_paths

router = APIRouter(prefix="/sites", tags=["machines"])

NODE_PATH = r"^[A-Za-z0-9_][A-Za-z0-9_.\-]*$"


class PlanRequest(BaseModel):
    part: Optional[str] = Field(None, pattern=NODE_PATH)
    file_id: Optional[str] = Field(None, max_length=120)


def _site(name: str):
    from ..api import _get_site_or_404

    return _get_site_or_404(name)


def _machine(name: str, path: str):
    """The site, the machine node at ``path`` and its kind; 404 for a node that is not
    there, 400 for one that is no machine."""
    from ..api import _find_node_by_path

    site = _site(name)
    node = _find_node_by_path(site, path)
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
    return machines_of(_site(name))


@router.get("/{name}/machines/{path}")
def site_machine(name: str, path: str):
    from ..api import _describe_for_view, _parts_of

    site, node, kind = _machine(name, path)
    return {
        "machine": {"kind": kind, "port": "", "identity": None, "path": path},
        "site": name,
        "operations": [
            {"kind": op.kind, "label": op.label, "inputs": list(op.inputs)}
            for op in jobs.operations(kind)
        ],
        "parts": [p.model_dump(mode="json") for p in _parts_of(name, site, path)],
        "where": _describe_for_view(site, path, node, is_printer=True),
        "plan": _plan_json(name, path),
    }


def _plan_json(name: str, path: str) -> Optional[dict]:
    plan = machine_plans.load(name, path)
    return plan.model_dump(mode="json") if plan is not None else None


@router.put("/{name}/machines/{path}/plan")
def keep_plan(name: str, path: str, body: PlanRequest):
    from ..api import _parts_of

    site, _, kind = _machine(name, path)
    if body.part and body.part not in {p.path for p in _parts_of(name, site, path)}:
        raise HTTPException(status_code=422, detail=f"{body.part!r} is no part or piece of {name}")
    try:
        plan = machine_plans.save(name, path, kind, body.part, body.file_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return plan.model_dump(mode="json")


@router.delete("/{name}/machines/{path}/plan")
def let_plan_go(name: str, path: str):
    _machine(name, path)
    return {"cleared": machine_plans.clear(name, path)}
