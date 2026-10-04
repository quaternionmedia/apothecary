"""Cameras from the browser: a camera part added, aimed, told its device, removed.

The records, the node and where a camera looks are ``apothecary/vision/cameras.py``;
these routes are its doors. A camera's pictures are taken by
``POST /photos/pictures?site=&camera=`` (or ``POST /sites/{s}/views`` with
``{camera, picture}``) and listed with the site's in ``GET /sites/{s}/attached``.

``async def``, one at a time on the event loop, as api.py's rule for routes that
change a site says; each answers with the camera and the site as ``GET
/sites/{s}`` does:

- ``POST /sites/{s}/cameras`` ``{host}``: Add here -- a camera above the middle
  of a host's top, or of the floor (``""``), looking straight down.
- ``PUT /sites/{s}/cameras/{name}/pose`` ``{position?, turn?, tilt?}``: moved,
  turned or tilted; what is not given stays. Its pictures stay where they landed.
- ``DELETE /sites/{s}/cameras/{name}``: Remove. Its pictures and the pieces made
  from them stay. A camera whose site is gone (an arrangement built from a
  picture and forgotten) is removed all the same, its record with it.

Plain ``def``, since they change only a record, never the site:

- ``GET /sites/{s}/cameras/{name}``: one camera, as ``attached`` lists it.
- ``PUT /sites/{s}/cameras/{name}/device`` ``{id, label}`` and ``DELETE`` it:
  which of a browser's cameras this camera is, or none. The label stays on this
  machine, in the state folder, and never enters the site.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..hierarchy import Assembly
from ..models.vectors import Vector3D
from ..vision import cameras

router = APIRouter(tags=["cameras"])


def _site(site_name: str) -> Assembly:
    from ..api import _get_site_or_404

    return _get_site_or_404(site_name)


def _site_answer(site_name: str, site: Assembly) -> Dict[str, object]:
    from ..api import _site_payload, _site_store

    return _site_payload(site, _site_store.validator(site_name)(site))


def _record_or_404(site_name: str, name: str) -> cameras.Camera:
    try:
        return cameras.record(site_name, name)
    except cameras.CameraNotFound as missing:
        raise HTTPException(status_code=404, detail=str(missing).strip('"')) from None


class AddCamera(BaseModel):
    """Where Add here stands a camera: above a host, or the floor (``""``)."""

    model_config = ConfigDict(extra="forbid")

    host: str = Field("", max_length=400)


@router.post("/sites/{site_name}/cameras", status_code=201)
async def add_camera(site_name: str, body: AddCamera):
    """Add here: a camera ``START_HEIGHT`` above the middle of a host's top, or of
    the floor's mat place just past the site's roots, looking straight down. A
    place that cannot hold a picture is refused with its reason, as a view's is."""
    from .views import check_host

    site = check_host(site_name, body.host)
    camera = cameras.add_here(site_name, site, body.host)
    return {"camera": cameras.answer(camera, site), "site": _site_answer(site_name, site)}


@router.get("/sites/{site_name}/cameras/{name}")
def get_camera(site_name: str, name: str):
    """One camera part: its pose, the pose it was added at, its lens, its device,
    and where its next picture would land."""
    site = _site(site_name)
    return cameras.answer(_record_or_404(site_name, name), site)


class PoseBody(BaseModel):
    """A camera's new place and aim: its lens's position in the site's frame, in mm,
    its turn about the vertical and its tilt from straight down, in degrees. Any of
    the three; what is not given stays."""

    model_config = ConfigDict(extra="forbid")

    position: Optional[List[float]] = Field(None, min_length=3, max_length=3)
    turn: Optional[float] = Field(None, allow_inf_nan=False)
    tilt: Optional[float] = Field(None, ge=0.0, le=180.0, allow_inf_nan=False)

    @model_validator(mode="after")
    def _something(self) -> "PoseBody":
        if self.position is None and self.turn is None and self.tilt is None:
            raise ValueError("give a position, a turn or a tilt")
        if self.position is not None and not all(
            isinstance(v, (int, float)) and abs(v) < 1e9 for v in self.position
        ):
            raise ValueError("a position is three numbers of millimetres")
        return self


@router.put("/sites/{site_name}/cameras/{name}/pose")
async def pose_camera(site_name: str, name: str, body: PoseBody):
    """Move, turn or tilt a camera. The pictures it took already stay where they landed."""
    site = _site(site_name)
    _record_or_404(site_name, name)
    position = (
        Vector3D(x=body.position[0], y=body.position[1], z=body.position[2])
        if (body.position is not None)
        else None
    )
    camera = cameras.set_pose(
        site_name, site, name, position=position, turn=body.turn, tilt=body.tilt
    )
    return {"camera": cameras.answer(camera, site), "site": _site_answer(site_name, site)}


class DeviceBody(BaseModel):
    """Which of this browser's cameras a camera is: its id and its label, as the
    browser gave them."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., pattern=cameras.DEVICE_ID)
    label: str = Field("camera", min_length=1, max_length=120)


@router.put("/sites/{site_name}/cameras/{name}/device")
def set_camera_device(site_name: str, name: str, body: DeviceBody):
    """Tell a camera which of a browser's cameras it is. Another camera may be the
    same device, as a board may be pinned at two nodes."""
    site = _site(site_name)
    _record_or_404(site_name, name)
    camera = cameras.set_device(site_name, name, cameras.Device(id=body.id, label=body.label))
    return cameras.answer(camera, site)


@router.delete("/sites/{site_name}/cameras/{name}/device")
def clear_camera_device(site_name: str, name: str):
    """A camera that is none of a browser's cameras now."""
    site = _site(site_name)
    _record_or_404(site_name, name)
    return cameras.answer(cameras.set_device(site_name, name, None), site)


@router.delete("/sites/{site_name}/cameras/{name}")
async def remove_camera(site_name: str, name: str):
    """Remove a camera: it leaves the site, and its record goes. The pictures it took,
    and the pieces made from them, stay. A camera whose site is gone is removed
    from the records all the same (``site`` is null)."""
    from ..api import _site_store

    site = _site(site_name) if site_name in _site_store.names() else None
    try:
        cameras.remove(site_name, site, name)
    except cameras.CameraNotFound as missing:
        raise HTTPException(status_code=404, detail=str(missing).strip('"')) from None
    return {
        "removed": name,
        "site": _site_answer(site_name, site) if site is not None else None,
    }


__all__ = ["router"]
