"""A part's interfaces, and how two fit, over HTTP (docs/connections.md).

- ``GET /parts/{name}/interfaces?preset=``: the places where another part meets this
  one, as ``apothecary parts interfaces`` lists them: each with its type, its
  position and normal in the part's own frame, its sizes, where its numbers came
  from, and the interfaces of the same part it cannot be in use with; at one of the
  part's presets where ``preset`` names one, else at its defaults.
- ``GET /parts/{name}/interfaces/{interface}/fit?to=part[@preset].interface``: how
  that interface fits another part's, as ``apothecary parts fit`` says: the verdict,
  the seat, the shoulder's gap to the mouth, the interference and the reason in
  words.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.encoders import jsonable_encoder

from ..models.interfaces import fit
from ..projects.parts.base import address

router = APIRouter(tags=["parts"])


def _api():
    from .. import api

    return api


def _params(part, preset: Optional[str]) -> Dict[str, Any]:
    try:
        return dict(part.preset(preset)) if preset else {}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc.args[0])) from None


def _interface(part_name: str, interface: str, preset: Optional[str] = None):
    part = _api().load_part_wrapper(part_name)
    try:
        return part, part.interface(interface, _params(part, preset) or None)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc.args[0])) from None


@router.get("/parts/{name}/interfaces")
def get_part_interfaces(
    name: str,
    preset: Optional[str] = Query(None, max_length=100, description="one of the part's presets"),
) -> Dict[str, Any]:
    """The places where another part meets this one, at its defaults or a preset."""
    part = _api().load_part_wrapper(name)
    params = _params(part, preset)
    return {
        "part": part.name,
        "preset": preset,
        "interfaces": [jsonable_encoder(i) for i in part.interfaces(params or None)],
    }


@router.get("/parts/{name}/interfaces/{interface}/fit")
def get_interface_fit(
    name: str,
    interface: str,
    to: str = Query(
        ..., max_length=200, description="the other part's interface: part[@preset].interface"
    ),
    preset: Optional[str] = Query(None, max_length=100, description="this part's preset"),
) -> Dict[str, Any]:
    """How this interface fits another part's, by the rule for their pair of types."""
    other_part, other_preset, other = address(to)
    if not other_part or not other:
        raise HTTPException(status_code=422, detail=f"to={to!r} is not part.interface")
    part, here = _interface(name, interface, preset)
    them, there = _interface(other_part, other, other_preset)
    at = f"@{preset}" if preset else ""
    there_at = f"@{other_preset}" if other_preset else ""
    return {
        **jsonable_encoder(fit(here, there)),
        "a": f"{part.name}{at}.{here.name}",
        "b": f"{them.name}{there_at}.{there.name}",
    }
