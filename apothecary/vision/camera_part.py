"""A camera is a part like any other: its numbers are its parameters.

``CameraPart`` wraps one camera's record (``vision/cameras.py``) as a
``BasePart``, so the one parameter contract (``projects/parts/params.py``) and
the one editor in the browser serve it as they serve a part from the parts
folder and a piece made from a picture: Part › Edit on its ring opens it in
Selected (the owner's decision of 2026-10-04).

- ``params_model`` is a ``CameraParams`` built for the record: where its lens
  stands (``x``, ``y``, ``z``, in the site's frame, mm), its ``turn`` about the
  vertical and ``tilt`` from straight down (degrees), and its field of view
  across (``fov``, degrees), each defaulting to what the camera is now. A
  position is limited only as a slider is: its schema states a range around
  the site, and a value outside it is not refused.
- ``contested`` offers, for each number no longer what it started at, where it
  started: the pose the camera was added at (where Reset stands it) and the
  starting lens.
- ``geometry`` is the webcam aimed as the parameters say, and ``get_bounds``
  the box it fills about its lens -- the same box as its node's footprint.

A field of view typed here is the camera's lens from then on, a person's, and
its pictures no person sized follow it, as they follow a width that teaches it.

PROTOTYPE -- not ratified.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple, Type

from pydantic import BaseModel, Field, create_model

from ..core import OpenSCADObject
from ..hierarchy import Assembly
from ..models.bounds import BoundingBox3D
from ..models.vectors import Vector3D
from ..projects.parts.base import BasePart, ContestedValue
from .cameras import CATEGORY, START_FOV, WEBCAM, Camera, Pose, body, footprint, names
from .projection import FOV_LEAST, FOV_MOST

NUMBERS = ("x", "y", "z", "turn", "tilt", "fov")

# How far past the site's roots a position's slider reaches, in mm.
REACH = 1000.0

# The bounds a turn, a tilt and a field of view are held to; a position has none.
LIMITS: Dict[str, Tuple[float, float]] = {
    "turn": (0.0, 360.0),
    "tilt": (0.0, 180.0),
    "fov": (FOV_LEAST, FOV_MOST),
}


class CameraParams(BaseModel):
    """What a camera takes: where its lens stands, how it is aimed, how wide it sees."""

    x: float = Field(0.0, allow_inf_nan=False, description="the lens, across the site, mm")
    y: float = Field(0.0, allow_inf_nan=False, description="the lens, toward the back, mm")
    z: float = Field(0.0, allow_inf_nan=False, description="the lens, above the floor, mm")
    turn: float = Field(0.0, description="degrees about the vertical, counterclockwise")
    tilt: float = Field(0.0, description="degrees from straight down, toward the picture's top")
    fov: float = Field(START_FOV, description="degrees the camera sees across")


def _reach(camera: Camera, site: Optional[Assembly]) -> Dict[str, Tuple[float, float]]:
    """The range each position's slider spans: the site's roots and the camera,
    where it stands and where it was added, and ``REACH`` past them."""
    points = [camera.pose.position, camera.added.position]
    corners: List[Vector3D] = list(points)
    others = names(camera.site) if site is not None else set()
    for child in site.children if site is not None else []:
        bounds = child.world_bounds()
        if bounds is not None and child.name not in others:
            corners += [bounds.min_point, bounds.max_point]
    return {
        "x": (min(c.x for c in corners) - REACH, max(c.x for c in corners) + REACH),
        "y": (min(c.y for c in corners) - REACH, max(c.y for c in corners) + REACH),
        "z": (min(0.0, *(p.z for p in points)), max(c.z for c in corners) + REACH),
    }


def camera_params(camera: Camera, site: Optional[Assembly] = None) -> Type[CameraParams]:
    """``CameraParams`` whose defaults are what the camera is now, its position's
    sliders spanning the site, so a staged set naming one number keeps the rest."""
    base = CameraParams.model_fields
    pose = camera.pose
    now = {
        "x": pose.position.x,
        "y": pose.position.y,
        "z": pose.position.z,
        "turn": pose.turn,
        "tilt": pose.tilt,
        "fov": camera.fov,
    }
    reach = _reach(camera, site)
    fields: Dict[str, Any] = {}
    for name in NUMBERS:
        low, high = LIMITS.get(name, (None, None))
        extra = {"minimum": reach[name][0], "maximum": reach[name][1]} if name in reach else None
        fields[name] = (
            float,
            Field(
                now[name],
                ge=low,
                le=high,
                allow_inf_nan=False,
                description=base[name].description,
                json_schema_extra=extra,
            ),
        )
    return create_model("CameraParams", __base__=CameraParams, **fields)


def candidates(camera: Camera) -> Dict[str, List[ContestedValue]]:
    """Where each number started, when it is no longer there: the pose the camera
    was added at, where Reset stands it, and the starting lens."""
    added, pose = camera.added, camera.pose
    started = {
        "x": (added.position.x, pose.position.x),
        "y": (added.position.y, pose.position.y),
        "z": (added.position.z, pose.position.z),
        "turn": (added.turn, pose.turn),
        "tilt": (added.tilt, pose.tilt),
    }
    contested: Dict[str, List[ContestedValue]] = {}
    for name, (then, now) in started.items():
        if then != now:
            contested[name] = [
                ContestedValue(
                    value=then,
                    source=f"where {camera.name} was added, {camera.added_at[:10]}",
                    note="Reset stands it back here",
                )
            ]
    if camera.fov != START_FOV:
        contested["fov"] = [
            ContestedValue(
                value=START_FOV,
                source="a typical webcam's field of view",
                note="the starting lens, before a width typed for a picture taught this one",
            )
        ]
    return contested


class CameraPart(BasePart):
    """A camera, as the part it is."""

    camera: Camera

    @classmethod
    def of(cls, camera: Camera, site: Optional[Assembly] = None) -> "CameraPart":
        from ..projects.parts.skeleton import ROOT

        part = cls(
            name=camera.name,
            # It is drawn as the library's webcam, aimed.
            source_file=Path(ROOT) / "parts" / "cameras" / WEBCAM / f"{WEBCAM}.scad",
            description=(
                f"a camera in {camera.site}, drawn as the library's {WEBCAM}: where its lens "
                "stands, how it is turned and tilted, and how wide it sees"
            ),
            params_model=camera_params(camera, site),
            category=CATEGORY,
            tags=[CATEGORY, WEBCAM],
            contested=candidates(camera),
            camera=camera,
        )
        part.default_bounds = part.get_bounds()
        return part

    def _params(self, params: Optional[Mapping[str, Any]]) -> CameraParams:
        assert self.params_model is not None
        return self.params_model(**dict(params or {}))

    def _pose(self, params: Optional[Mapping[str, Any]]) -> Pose:
        p = self._params(params)
        return Pose(position=Vector3D(x=p.x, y=p.y, z=p.z), turn=p.turn, tilt=p.tilt)

    def geometry(self, params: Mapping[str, Any]) -> OpenSCADObject:
        """The webcam, aimed as the parameters say, about its lens."""
        return body(self._pose(params))

    def get_bounds(self, params: Optional[Dict] = None) -> BoundingBox3D:
        """The box the webcam fills, aimed as the parameters say, about its lens:
        the camera's node's footprint."""
        return footprint(self._pose(params))


__all__ = ["CameraParams", "CameraPart", "NUMBERS", "camera_params", "candidates"]
