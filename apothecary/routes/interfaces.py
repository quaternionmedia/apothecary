"""A part's interfaces, and how two fit, over HTTP (docs/connections.md).

- ``GET /parts/{name}/interfaces``: the places where another part meets this one, as
  ``apothecary parts interfaces`` lists them: each with its type, its position and
  normal in the part's own frame, its sizes, where its numbers came from, and the
  interfaces of the same part it cannot be in use with.
- ``GET /parts/{name}/interfaces/{interface}/fit?to=part.interface``: how that
  interface fits another part's, as ``apothecary parts fit`` says: the verdict, the
  seat, the shoulder's gap to the mouth, the interference and the reason in words.
"""

from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Query
from fastapi.encoders import jsonable_encoder

from ..models.interfaces import fit

router = APIRouter(tags=["parts"])


def _api():
    from .. import api

    return api


def _interface(part_name: str, interface: str):
    part = _api().load_part_wrapper(part_name)
    try:
        return part, part.interface(interface)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc.args[0])) from None


@router.get("/parts/{name}/interfaces")
def get_part_interfaces(name: str) -> Dict[str, Any]:
    """The places where another part meets this one, at its defaults."""
    part = _api().load_part_wrapper(name)
    return {
        "part": part.name,
        "interfaces": [jsonable_encoder(i) for i in part.interfaces()],
    }


@router.get("/parts/{name}/interfaces/{interface}/fit")
def get_interface_fit(
    name: str,
    interface: str,
    to: str = Query(..., max_length=200, description="the other part's interface: part.interface"),
) -> Dict[str, Any]:
    """How this interface fits another part's, by the rule for their pair of types."""
    other_part, _, other = to.rpartition(".")
    if not other_part or not other:
        raise HTTPException(status_code=422, detail=f"to={to!r} is not part.interface")
    part, here = _interface(name, interface)
    them, there = _interface(other_part, other)
    return {
        **jsonable_encoder(fit(here, there)),
        "a": f"{part.name}.{here.name}",
        "b": f"{them.name}.{there.name}",
    }
