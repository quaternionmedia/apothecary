"""The toolpath's routes: write one for a router, and read what was written.

``POST /cam/cut`` writes the named part's toolpath for the router whose
controller is on ``port`` (or the node named), keeps it as a cut file and answers
the record; ``GET /cam/cuts`` lists the records whose files are still kept, and
``GET /cam/cuts/{file_id}`` one of them. A part that does not say how it is cut
is refused with 400, as is a variant the page no longer holds.

``POST /cam/cuts/{file_id}/measured`` ``{"sizes": {name: mm}}`` takes the piece that
toolpath cut, measured by a person -- each feature its record names, any of them --
checks it against what was designed and keeps the router's tool allowance it makes
(``measured.py``), which its next toolpaths take; a measurement that is not of that
piece, or an allowance past what a tool's running out explains, is a 422 saying why,
and nothing is kept. ``GET /cam/corrections?site=&router=`` reads the allowance kept,
with the measurements that made it; ``null`` where none is.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from .. import sites
from ..hierarchy import find_node_by_path
from ..projects.parts.skeleton import ROOT
from ..projects.registry import part_names
from . import measured, service
from .models import CutFor, CutRecord

router = APIRouter(prefix="/cam", tags=["cam"])

NODE_PATH = r"^[A-Za-z0-9_][A-Za-z0-9_.\-]*$"
VARIANT_KEY = r"^[0-9a-f]{24}$"


class CutRequest(BaseModel):
    part: str = Field(..., pattern=NODE_PATH)
    port: Optional[str] = Field(None, max_length=120)
    site: Optional[str] = Field(None, pattern=NODE_PATH)
    router: Optional[str] = Field(None, pattern=NODE_PATH)  # the router's node in the site
    variant: Optional[str] = Field(None, pattern=VARIANT_KEY)


class MeasuredRequest(BaseModel):
    # Millimetres, as measured, by the feature's name; one left out was not measured.
    sizes: Dict[str, Optional[float]] = Field(..., max_length=24)


def _part_named(site: Optional[str], part: str) -> str:
    """The registered part ``part`` names: with a site, the part the node at that
    path stands for (its ``part_ref``), as the Cut card's makes names it, else a
    registered part of that name, which makes lists after the site's pieces;
    without one, the registry name itself."""
    if site is None:
        return part
    try:
        node = find_node_by_path(sites.store.get(site), part)
    except KeyError:
        node = None
    if node is None:
        if part in part_names(ROOT):
            return part
        raise HTTPException(
            status_code=404, detail=f"{part!r} is no piece of {site} and no part's name"
        )
    if not node.part_ref:
        raise HTTPException(
            status_code=400,
            detail=f"{part} in {site} stands for no part: nothing says how it is cut",
        )
    return node.part_ref


@router.post("/cut", response_model=CutRecord)
def write_cut(body: CutRequest):
    name = body.router or (body.port or "router")
    where = CutFor(
        name=name.split(".")[0], site=body.site, path=body.router, port=body.port or None
    )
    try:
        return service.cut_into(_part_named(body.site, body.part), where, variant=body.variant)
    except service.CamError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # a part that does not load names itself in the detail
        if type(exc).__name__ == "SlicerError":
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        raise


@router.get("/cuts", response_model=List[CutRecord])
def list_cuts():
    return service.records()


@router.get("/cuts/{file_id}", response_model=CutRecord)
def get_cut(file_id: str):
    record = service.get_record(file_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"no toolpath is recorded for {file_id!r}")
    return record


@router.post("/cuts/{file_id}/measured")
def cut_measured(file_id: str, body: MeasuredRequest):
    """The piece the toolpath ``file_id`` cut, measured: checked, and the allowance it
    makes kept for the router the toolpath was written for."""
    record = service.get_record(file_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"no toolpath is recorded for {file_id!r}")
    try:
        kept = measured.measure(record, body.sizes)
    except measured.Refused as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "correction": kept.model_dump(mode="json"),
        "said": measured.said(kept.measurements[-1]),
    }


@router.get("/corrections")
def cut_correction(
    site: str = Query(..., pattern=NODE_PATH),
    at: str = Query(..., alias="router", pattern=NODE_PATH),
):
    """The allowance kept for the router node ``router`` in ``site``, or null."""
    kept = measured.load(site, at)
    return {"correction": kept.model_dump(mode="json") if kept else None}
