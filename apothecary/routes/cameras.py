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
- ``PUT /sites/{s}/cameras/{name}`` ``{params: {x?, y?, z?, turn?, tilt?, fov?}}``:
  the editor's Apply (Part › Edit). A field of view given is the camera's lens
  from then on, and its pictures no person sized follow it (``rebuilt``).
- ``DELETE /sites/{s}/cameras/{name}``: Remove. Its pictures and the pieces made
  from them stay. A camera whose site is gone (an arrangement built from a
  picture and forgotten) is removed all the same, its record with it.

Plain ``def``, since they change only a record, never the site:

- ``GET /sites/{s}/cameras/{name}``: one camera, as ``attached`` lists it.
- ``GET /sites/{s}/cameras/{name}/params`` and ``POST .../validate``
  ``{params}``: a camera is a part (``vision/camera_part.py``), and answers the
  parameter contract a part from the parts folder answers.
- ``PUT /sites/{s}/cameras/{name}/device`` ``{id, label}`` and ``DELETE`` it:
  which of a browser's cameras this camera is, or none. One device is one
  camera: choosing it here takes it off any other (``taken_from``). The label
  stays on this machine, in the state folder, and never enters the site.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..hierarchy import Assembly
from ..models.vectors import Vector3D
from ..projects.parts.params import ParamsSpec, Validation, params_spec, validate_staged
from ..vision import cameras
from ..vision.camera_part import CameraPart

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
    """Tell a camera which of a browser's cameras it is. One device is one camera:
    it is taken off any other camera it was, in any site (``taken_from`` names them)."""
    site = _site(site_name)
    _record_or_404(site_name, name)
    camera, taken = cameras.set_device(
        site_name, name, cameras.Device(id=body.id, label=body.label)
    )
    return {
        **cameras.answer(camera, site),
        "taken_from": [{"site": c.site, "name": c.name} for c in taken],
    }


@router.delete("/sites/{site_name}/cameras/{name}/device")
def clear_camera_device(site_name: str, name: str):
    """A camera that is none of a browser's cameras now."""
    site = _site(site_name)
    _record_or_404(site_name, name)
    camera, _taken = cameras.set_device(site_name, name, None)
    return cameras.answer(camera, site)


@router.get("/sites/{site_name}/cameras/{name}/params", response_model=ParamsSpec)
def camera_params(site_name: str, name: str):
    """What a camera's editor edits, in the form ``GET /parts/{name}/params`` answers:
    its lens's position, its turn and tilt and its field of view, defaulting to what
    the camera is now, and where each started as the candidates to turn back to."""
    site = _site(site_name)
    return params_spec(CameraPart.of(_record_or_404(site_name, name), site))


class StagedParams(BaseModel):
    params: Dict[str, Any] = Field(default_factory=dict)


@router.post("/sites/{site_name}/cameras/{name}/validate", response_model=Validation)
def validate_camera(site_name: str, name: str, body: Optional[StagedParams] = None):
    """Check a staged set against the camera's own model, as ``POST
    /parts/{name}/validate`` does: an unknown field, a tilt past straight up or a
    field of view of nothing is refused here, and a valid set says the box the
    camera would fill about its lens."""
    site = _site(site_name)
    part = CameraPart.of(_record_or_404(site_name, name), site)
    return validate_staged(part, body.params if body else {})


class EditBody(BaseModel):
    """The editor's Apply: any of the camera's numbers; the rest stay as they are."""

    model_config = ConfigDict(extra="forbid")

    params: Dict[str, Any] = Field(..., min_length=1)


@router.put("/sites/{site_name}/cameras/{name}")
async def edit_camera(site_name: str, name: str, body: EditBody):
    """Apply the editor's staged set: the camera moved, turned and tilted as it says,
    and a field of view given is the camera's lens from now on -- a person's -- which
    its pictures no person sized follow, the pieces made from them re-sized
    (``rebuilt``). Only what differs from the camera is a change. Refused (422) for
    an unknown field or a value out of range."""
    from ..vision import views as viewing

    site = _site(site_name)
    camera = _record_or_404(site_name, name)
    try:
        given = CameraPart.of(camera, site).validate_overrides(body.params)
    except ValueError as refused:
        raise HTTPException(status_code=422, detail=str(refused)) from None
    pose = camera.pose
    now = {"x": pose.position.x, "y": pose.position.y, "z": pose.position.z}
    moved = {axis: given[axis] for axis in now if axis in given and given[axis] != now[axis]}
    position = Vector3D(**{**now, **moved}) if moved else None
    turn = given["turn"] if "turn" in given and given["turn"] != pose.turn else None
    tilt = given["tilt"] if "tilt" in given and given["tilt"] != pose.tilt else None
    if position is not None or turn is not None or tilt is not None:
        cameras.set_pose(site_name, site, name, position=position, turn=turn, tilt=tilt)
    rebuilt: List[str] = []
    if "fov" in given and given["fov"] != camera.fov:
        cameras.set_lens(site_name, name, given["fov"])
        rebuilt = viewing.lens_followed(site_name, site, name, given["fov"])
    return {
        "camera": cameras.answer(cameras.record(site_name, name), site),
        "rebuilt": rebuilt,
        "site": _site_answer(site_name, site),
    }


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
