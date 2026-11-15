"""A site's procedures (``apothecary/family/procedures.py``).

- ``GET /sites/{s}/procedures``: the names of the site's procedures.
- ``GET /sites/{s}/procedures/{p}``: one as it stands: each step, its status (waiting,
  standing by, fired, done, refused or failed), why, whether GO will fire it, and the
  outcome of its last fire per member.
- ``PUT /sites/{s}/procedures/{p}``: one written, whole.
- ``POST /sites/{s}/procedures/{p}/steps/{n}/go``: one step fired through the family's
  hub, and the procedure as it then stands; a 409 for a step not standing by.
- ``POST /sites/{s}/procedures/{p}/again``: the procedure started over.
- ``GET /family/beside``: what each member the hub started itself is doing now.

Plain ``def``: a GO waits for each member's answer, and reading a procedure reads the
evidence log.
"""

from __future__ import annotations

from typing import Annotated, Any, Dict

from fastapi import APIRouter, HTTPException, Path, Request
from fastapi.routing import APIRoute

from .. import sites
from ..family import beside, procedures
from ..site_store import UnknownSiteError
from .jobs import SITE_NAME


class _ProcedureRoute(APIRoute):
    """A procedure's file that will not read is a 422, in its own words, on every route."""

    def get_route_handler(self):
        handler = super().get_route_handler()

        async def answer(request: Request):
            try:
                return await handler(request)
            except procedures.Unreadable as exc:
                raise HTTPException(422, detail=str(exc)) from exc

        return answer


router = APIRouter(tags=["family"], route_class=_ProcedureRoute)

Name = Annotated[str, Path(pattern=SITE_NAME, description="the procedure's name")]
Site = Annotated[str, Path(pattern=SITE_NAME, description="the site it is under")]


def _no_procedure(site: str, name: str) -> HTTPException:
    return HTTPException(404, detail=f"{site} has no procedure {name}")


@router.get("/sites/{site}/procedures")
def list_procedures(site: Site) -> Dict[str, Any]:
    """The names of the site's procedures."""
    sites.store.get(site)
    return {"site": site, "procedures": procedures.names(site)}


@router.get("/sites/{site}/procedures/{name}")
def get_procedure(site: Site, name: Name) -> Dict[str, Any]:
    """One procedure as it stands."""
    sites.store.get(site)
    board = procedures.board(site, name)
    if board is None:
        raise _no_procedure(site, name)
    return board


@router.put("/sites/{site}/procedures/{name}")
def put_procedure(site: Site, name: Name, body: procedures.Procedure) -> Dict[str, Any]:
    """One procedure written, whole; the outcomes its steps have kept stay theirs."""
    sites.store.get(site)
    procedures.save(site, name, body)
    return procedures.board(site, name)


@router.post("/sites/{site}/procedures/{name}/steps/{number}/go")
def go(site: Site, name: Name, number: str) -> Dict[str, Any]:
    """One step fired through the family's hub."""
    sites.store.get(site)
    try:
        return procedures.go(site, name, number)
    except UnknownSiteError:  # a step holds the wiring of a site that is not there
        raise
    except KeyError:
        raise _no_procedure(site, f"{name} step {number}") from None
    except procedures.NotStandingBy as exc:
        raise HTTPException(409, detail=str(exc)) from None


@router.post("/sites/{site}/procedures/{name}/again")
def again(site: Site, name: Name) -> Dict[str, Any]:
    """The procedure started over."""
    sites.store.get(site)
    board = procedures.again(site, name)
    if board is None:
        raise _no_procedure(site, name)
    return board


@router.get("/family/beside")
def family_beside() -> Dict[str, Any]:
    """What each member the hub started itself is doing now."""
    return beside.status()
