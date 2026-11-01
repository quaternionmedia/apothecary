"""Image models through qmcp, and the plain reader beside them, over HTTP.

- ``GET /vision``: qmcp's state (``state``, one of ``finders.qmcp.STATES``, and
  ``says``, a sentence), its models, each origin and whether it is switched on,
  and the properties a shape can be asked about.
- ``PUT /vision/origins/{origin}`` ``{on}``: switch an origin on or off.
- ``GET /sites/{s}/views/{v}/shapes/{i}/observations``: what is kept about a
  shape, a row per property.
- ``POST /sites/{s}/views/{v}/shapes/{i}/ask`` ``{asked}``: ask about a shape:
  the plain reader's colour and qmcp's guesses; ``said`` says what happened.
- ``PUT /sites/{s}/views/{v}/shapes/{i}/observations/{property}`` ``{value}``: a
  person's word on a property, first over every guess about it.

Nothing is asked unless a person asks. Plain ``def``: the client blocks on qmcp
up to its deadline, on a worker thread, so the event loop goes on.
"""

from __future__ import annotations

from typing import List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from ..evidence.observation import model_key
from ..finders import kept, qmcp, switches

router = APIRouter()


class SwitchBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    on: bool


class AskBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    asked: List[str] = Field(default_factory=lambda: list(kept.ASKABLE), min_length=1)


class SayBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    value: str = Field(..., min_length=1, max_length=64)


@router.get("/vision")
def vision_status():
    from ..vision.colour import READER

    status = qmcp.status()
    switched = switches.read()
    origins = [
        {
            "origin": READER,
            "what": "the plain reader: a region's colour, read off its pixels",
            "on": switched.get(READER, True),
        }
    ]
    for model in status["models"]:
        origin = model_key(model.get("name"), model.get("version"))
        origins.append(
            {
                "origin": origin,
                "what": f"{model.get('name')} {model.get('version')}, on {(model.get('engine') or {}).get('name', '?')}",
                "answers": sorted((model.get("answers") or {}).keys()),
                "licence": model.get("licence"),
                "weights_sha256": model.get("weights_sha256"),
                "trusted": False,
                "on": switched.get(origin, True),
            }
        )
    return {**status, "origins": origins, "askable": list(kept.ASKABLE)}


@router.put("/vision/origins/{origin:path}")
def switch_origin(origin: str, body: SwitchBody):
    try:
        switches.switch(origin, body.on)
    except ValueError as refused:
        raise HTTPException(status_code=400, detail=str(refused)) from None
    return vision_status()


def _shape(site_name: str, view_id: str, index: int):
    from .views import _picture_at, _site, _view_or_404

    view = _view_or_404(site_name, view_id)
    shape = next((s for i, s in enumerate(view.shapes) if i == index), None)
    if shape is None:
        raise HTTPException(status_code=404, detail=f"view {view_id!r} has no shape {index}")
    return view, shape, _picture_at(view.picture), _site(site_name)


@router.get("/sites/{site_name}/views/{view_id}/shapes/{index}/observations")
def shape_observations(site_name: str, view_id: str, index: int):
    _shape(site_name, view_id, index)
    return kept.about((site_name, view_id, index))


@router.post("/sites/{site_name}/views/{view_id}/shapes/{index}/ask")
def ask_about_shape(site_name: str, view_id: str, index: int, body: AskBody):
    view, shape, picture, site = _shape(site_name, view_id, index)
    try:
        return kept.ask_about(
            (site_name, view_id, index),
            picture,
            view.taken_at,
            shape,
            site,
            body.asked,
            path=view.picture,
        )
    except ValueError as refused:
        raise HTTPException(status_code=400, detail=str(refused)) from None
    except OSError as unread:
        raise HTTPException(
            status_code=400, detail=f"{picture.name} could not be read: {unread}"
        ) from None


@router.put("/sites/{site_name}/views/{view_id}/shapes/{index}/observations/{prop}")
def say_about_shape(site_name: str, view_id: str, index: int, prop: str, body: SayBody):
    from ..vision.colour import digest

    _, shape, picture, _ = _shape(site_name, view_id, index)
    try:
        return kept.say((site_name, view_id, index), prop, body.value, digest(picture), shape)
    except ValueError as refused:
        raise HTTPException(status_code=400, detail=str(refused)) from None
