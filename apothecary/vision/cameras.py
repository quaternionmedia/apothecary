"""Cameras: a camera is a part standing in a site, aimed where it looks.

A camera is a root structure of a site, as a printer is -- ``camera_1``,
``camera_2``... -- drawn as the library's bare webcam (``parts/cameras/webcam``)
standing in the air where it is put. What is known about one is its record:

- its site and its name;
- its pose: where the middle of its lens's front face is, in the site's frame,
  in millimetres; its turn about the vertical and its tilt from straight down,
  in degrees (``projection.py`` says which way each runs);
- its field of view across, in degrees -- ``START_FOV``, a typical webcam's,
  until the first width a person types for one of its pictures teaches it the
  real one -- and whether a person has taught it;
- the pose it was added at, which Reset stands it back at;
- its device: which of a browser's cameras it is, by the id and the label that
  browser gave it, or none. A device is one browser origin's, as a board's
  identity is one machine's: another browser shows its label and cannot open it.
  And one device is one camera: choosing it for one takes it off any other.

A label may be a person's own words ("FaceTime HD Camera (Built-in)"), so the
records are kept in the state folder (``state_folder.state_dir``), made the
person's alone, and written whole under one lock, as a board's pins are. Nothing
about the device goes into the site: the camera's node carries its place and
its shape, and nothing else.

The record is the camera, and its node is drawn from it. A site built from its
factory -- the first time it is asked for, after a restart, after a Reset -- has
its cameras stood in it from their records (``stand``); a camera moved with the
handles (``POST /sites/{s}/layout``) has its record follow (``follow``).

Where a camera's picture lands is the first upward-facing surface its centre ray
reaches: a host's top -- a root structure with a footprint that is neither a
made piece nor a camera -- or the floor. A ray that meets the side of something
first (a wall), or nothing (the sky), lands nowhere (``lands``).

A prototype: no ratified record governs it.
"""

from __future__ import annotations

import json
import math
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Set, Tuple

from pydantic import BaseModel, Field, ValidationError, field_validator

from ..hierarchy import Assembly
from ..models.bounds import BoundingBox3D
from ..models.vectors import Vector3D
from ..primitives import Cube, Cylinder
from ..site_names import current as current_site
from ..state_folder import state_dir, write_whole
from ..transforms import Rotate, Translate
from .projection import Box, Hit, first_surface, looking

# The library's part every camera is drawn as, and the category its node is filed under.
WEBCAM = "webcam"
CATEGORY = "camera"
# A typical webcam's field of view across, in degrees: a camera's until a person teaches it.
START_FOV = 60.0
# How far above the first top under the middle of its place a camera added there
# stands, in mm: a webcam on a desk stand looks down from about there, and sees a
# little under 700 mm across at the starting field of view.
START_HEIGHT = 600.0

# The webcam as parts/cameras/webcam/webcam.scad draws it: its body (across the
# picture, up the picture, lens to back) above its lens, the lens's front face
# at the origin. tests/test_camera_parts.py holds the two to each other.
BODY = (90.0, 30.0, 30.0)
LENS_D = 16.0
LENS_H = 4.0

# A browser's id for one of its cameras: letters, digits and the punctuation a
# browser's ids are written in (hex, or base64).
DEVICE_ID = r"^[A-Za-z0-9][A-Za-z0-9_.:+/=-]{0,199}$"
RECORDS = "camera_parts.json"


class CameraNotFound(LookupError):
    """No camera by that name in that site."""


class Pose(BaseModel):
    """Where a camera stands and which way it looks."""

    position: Vector3D  # the middle of the lens's front face, in the site's frame, mm
    turn: float = Field(0.0, allow_inf_nan=False)  # about the vertical, counterclockwise
    tilt: float = Field(0.0, ge=0.0, le=180.0)  # from straight down, toward the picture's top

    @field_validator("turn")
    @classmethod
    def _one_turn(cls, turn: float) -> float:
        """A turn as one of a whole turn's degrees, from 0 up to but not including 360."""
        return round(turn, 9) % 360.0


class Device(BaseModel):
    """Which of one browser's cameras a camera is: its id and the label it gave it."""

    id: str = Field(..., pattern=DEVICE_ID)
    label: str = Field("camera", min_length=1, max_length=120)


class Camera(BaseModel):
    """One camera's record."""

    site: str
    name: str
    pose: Pose
    added: Pose
    fov: float = Field(START_FOV, gt=0.0, lt=180.0)
    fov_taught: bool = False
    device: Optional[Device] = None
    added_at: str


# --- the records, in the state folder ---------------------------------------------------

# One read-modify-write at a time; a write lands whole, so a reader never sees half a file.
_LOCK = threading.Lock()


def _records_file() -> Path:
    return state_dir() / RECORDS


def _load() -> List[Camera]:
    """Every camera's record; a file that is missing or unreadable holds none, and a
    record that does not read is left out rather than taking the rest with it."""
    try:
        data = json.loads(_records_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    rows = data.get("cameras", []) if isinstance(data, dict) else []
    kept: List[Camera] = []
    for row in rows if isinstance(rows, list) else []:
        try:
            camera = Camera.model_validate(row)
        except ValidationError:
            continue
        # A camera kept under a name its site had before stands in that site still.
        kept.append(camera.model_copy(update={"site": current_site(camera.site)}))
    return kept


def _save(cameras: List[Camera]) -> None:
    write_whole(
        _records_file(),
        json.dumps({"cameras": [c.model_dump(mode="json") for c in cameras]}, indent=2),
    )


def records(site: Optional[str] = None) -> List[Camera]:
    """The cameras of one site (every site's with none named), in the order they were added."""
    return [c for c in _load() if site is None or c.site == site]


def record(site: str, name: str) -> Camera:
    found = next((c for c in records(site) if c.name == name), None)
    if found is None:
        raise CameraNotFound(f"no camera {name!r} in site {site!r}")
    return found


def names(site: str) -> Set[str]:
    """The names of a site's cameras."""
    return {c.name for c in records(site)}


def _change(site: str, name: str, change: Callable[[Camera], Camera]) -> Camera:
    """One camera's record changed and written back, under the lock."""
    with _LOCK:
        cameras = _load()
        index = next((i for i, c in enumerate(cameras) if c.site == site and c.name == name), None)
        if index is None:
            raise CameraNotFound(f"no camera {name!r} in site {site!r}")
        cameras[index] = Camera.model_validate(change(cameras[index]).model_dump())
        _save(cameras)
        return cameras[index]


# --- the node a record draws ------------------------------------------------------------


def body(pose: Pose) -> Rotate:
    """The webcam as its SCAD draws it, tilted about its long side and then turned
    about the vertical: OpenSCAD's ``rotate([tilt, 0, turn])``, which is what
    ``projection.axes`` means by a turn and a tilt."""
    width, up, deep = BODY
    return Rotate(
        a=Vector3D(x=pose.tilt, y=0.0, z=pose.turn),
        children=[
            Translate(
                v=Vector3D(x=-width / 2, y=-up / 2, z=LENS_H),
                children=[Cube(size=Vector3D(x=width, y=up, z=deep))],
            ),
            Cylinder(h=LENS_H, r=LENS_D / 2, fn=48),
        ],
    )


def _aimed(point: Vector3D, pose: Pose) -> Vector3D:
    """A point of the webcam as it stands looking down, as it stands aimed."""
    t, k = math.radians(pose.tilt), math.radians(pose.turn)
    x = point.x
    y = point.y * math.cos(t) - point.z * math.sin(t)
    z = point.y * math.sin(t) + point.z * math.cos(t)
    return Vector3D(x=x * math.cos(k) - y * math.sin(k), y=x * math.sin(k) + y * math.cos(k), z=z)


def footprint(pose: Pose) -> BoundingBox3D:
    """The upright box the webcam fills as it is aimed, about its lens."""
    width, up, deep = BODY
    corners = [
        _aimed(Vector3D(x=x, y=y, z=z), pose)
        for x in (-width / 2, width / 2)
        for y in (-up / 2, up / 2)
        for z in (0.0, LENS_H + deep)
    ]
    return BoundingBox3D(
        min_point=Vector3D(
            x=min(c.x for c in corners), y=min(c.y for c in corners), z=min(c.z for c in corners)
        ),
        max_point=Vector3D(
            x=max(c.x for c in corners), y=max(c.y for c in corners), z=max(c.z for c in corners)
        ),
    )


def node(camera: Camera) -> Assembly:
    """The camera as a root structure of its site: standing at its lens, the webcam
    part (``part_ref``) aimed as it is (``base``), its box as aimed for its footprint."""
    pose = camera.pose
    return Assembly(
        name=camera.name,
        role="structure",
        position=pose.position.model_copy(),
        footprint=footprint(pose),
        base=body(pose),
        part_ref=WEBCAM,
        category=CATEGORY,
        comment=f"a camera, turned {pose.turn:g} and tilted {pose.tilt:g} from straight down",
    )


def _put(site: Assembly, camera: Camera) -> None:
    """The camera's node in the site, drawn again where it was, or appended."""
    drawn = node(camera)
    for i, child in enumerate(site.children):
        if child.name == camera.name:
            site.children[i] = drawn
            return
    site.children.append(drawn)


def stand(site_name: str, site: Assembly, *, back: bool = False) -> List[str]:
    """Every camera of the site stood in it from its record, and their names; with
    ``back`` (a Reset), each first stood back at the pose it was added at. Its
    device and its field of view stay. A record whose name a structure of the
    site's own code has taken since is not stood."""
    if back:
        with _LOCK:
            cameras = _load()
            changed = False
            for i, camera in enumerate(cameras):
                if camera.site == site_name and camera.pose != camera.added:
                    cameras[i] = camera.model_copy(update={"pose": camera.added.model_copy()})
                    changed = True
            if changed:
                _save(cameras)
    stood = []
    taken = {c.name for c in site.children}
    for camera in records(site_name):
        if camera.name in taken:
            continue
        site.children.append(node(camera))
        stood.append(camera.name)
    return stood


def follow(site_name: str, site: Assembly) -> List[str]:
    """A camera moved with the handles: its record's position follows its node's.
    The names of the cameras whose records moved. Its footprint is about its lens,
    so it moves with it."""
    nodes = {c.name: c for c in site.children}
    with _LOCK:
        cameras = _load()
        moved = []
        for i, camera in enumerate(cameras):
            drawn = nodes.get(camera.name)
            if camera.site != site_name or drawn is None:
                continue
            if drawn.position == camera.pose.position:
                continue
            pose = camera.pose.model_copy(update={"position": drawn.position.model_copy()})
            cameras[i] = camera.model_copy(update={"pose": pose})
            moved.append(camera.name)
        if moved:
            _save(cameras)
    return moved


# --- where it looks ---------------------------------------------------------------------


def surfaces(site_name: str, site: Assembly) -> List[Box]:
    """The tops a camera's picture may land on: every host's bounds -- a root
    structure with a footprint that is neither a made piece nor a camera."""
    from .views import made_names

    passed = made_names(site_name) | names(site_name)
    boxes = []
    for child in site.children:
        bounds = child.world_bounds()
        if child.name in passed or bounds is None:
            continue
        low, high = bounds.min_point, bounds.max_point
        boxes.append(Box(child.name, (low.x, low.y, low.z), (high.x, high.y, high.z)))
    return boxes


def lands(
    site_name: str, site: Assembly, pose: Pose, boxes: Optional[List[Box]] = None
) -> Optional[Hit]:
    """Where a camera at ``pose`` would land a picture: a host's top (its name) or
    the floor (``""``), and the point its centre ray reaches; None for a wall or the sky.
    ``boxes`` are the site's ``surfaces``, when a caller asks again and again."""
    eye = (pose.position.x, pose.position.y, pose.position.z)
    if boxes is None:
        boxes = surfaces(site_name, site)
    hit = first_surface(eye, looking(pose.turn, pose.tilt), boxes)
    if hit is None or hit.side:
        return None
    return hit


def looks_at(site_name: str, site: Assembly, pose: Pose) -> Optional[str]:
    """The root structure a camera at ``pose`` looks at, its top or a side of it: what
    its centre ray reaches first; None for the floor, a wall or the sky."""
    eye = (pose.position.x, pose.position.y, pose.position.z)
    hit = first_surface(eye, looking(pose.turn, pose.tilt), surfaces(site_name, site))
    return hit.name if hit is not None and hit.name else None


# --- what a person does to one ------------------------------------------------------------


def _free_name(site_name: str, site: Assembly) -> str:
    """``camera_N``, the lowest N that names nothing in the site, no camera's record,
    and no camera a view or a made piece there still remembers."""
    from .views import store

    taken = {c.name for c in site.children} | names(site_name)
    taken |= {vw.camera for vw in store().views_at(site_name) if vw.camera}
    taken |= {m.camera for m in store().made_at(site_name).values() if m.camera}
    n = 1
    while f"{CATEGORY}_{n}" in taken:
        n += 1
    return f"{CATEGORY}_{n}"


def starting_pose(
    site_name: str, site: Assembly, host: str, boxes: Optional[List[Box]] = None
) -> Pose:
    """Where Add here stands a camera: above the middle of its place, looking
    straight down, ``START_HEIGHT`` above the first top under it -- the place's
    own, or the top of what stands on it there (a printer on a bench), so it
    never starts grazing something and its first picture is of what it is above.

    A host's middle is the middle of its top; the floor's is the middle of where
    a picture laid on the floor at the camera's starting width lies -- just past
    the site's roots in +x, so it looks at the floor and at nothing standing on it."""
    from .views import FLOOR, floor_anchor, made_names, top_centre

    if host == FLOOR:
        anchor = floor_anchor(site, made_names(site_name) | names(site_name))
        width = 2 * START_HEIGHT * math.tan(math.radians(START_FOV) / 2)
        middle = Vector3D(x=anchor.x + width / 2, y=anchor.y, z=anchor.z)
    else:
        middle = top_centre(next(c for c in site.children if c.name == host))
    if boxes is None:
        boxes = surfaces(site_name, site)
    above = max([middle.z, *(box.high[2] for box in boxes)]) + 1.0
    under = first_surface((middle.x, middle.y, above), (0.0, 0.0, -1.0), boxes)
    top = max(middle.z, under.point[2]) if under is not None else middle.z
    return Pose(position=Vector3D(x=middle.x, y=middle.y, z=top + START_HEIGHT))


# How far a camera added where another stands steps aside: its body's width and a
# hand's breadth along x, its depth and a hand's breadth along y to the next row, so
# the two stand clear of each other.
BESIDE = BODY[0] + 30.0
BESIDE_ROW = BODY[1] + 30.0


def _placed(pose: Pose) -> Tuple[Tuple[float, ...], Tuple[float, ...]]:
    """The webcam's box where it stands: its footprint, which is about its lens, moved
    to the lens's place."""
    box, at = footprint(pose), pose.position
    low = (box.min_point.x + at.x, box.min_point.y + at.y, box.min_point.z + at.z)
    high = (box.max_point.x + at.x, box.max_point.y + at.y, box.max_point.z + at.z)
    return low, high


def _clear(a, b) -> bool:
    return any(a[1][k] <= b[0][k] or b[1][k] <= a[0][k] for k in range(3))


def _steps(n: int) -> List[int]:
    """None, then one side and the other, a step further each time: 0, 1, -1, 2, -2..."""
    return [((k + 1) // 2) * (1 if k % 2 else -1) for k in range(n)]


def beside(pose: Pose, others: Sequence[Pose], stays: Callable[[Pose], bool]) -> Pose:
    """``pose``, or the nearest place clear of every camera in ``others`` that still
    ``stays`` over its place: a step along x to one side, then the other, then two,
    and once x runs out the same a row along y. So a second Add here at one place
    stands beside the first rather than in it, and the next few fill the place's top
    in rows; with no room left over it, the nearest clear place along x, outside it."""
    taken = [_placed(o) for o in others]
    steps = _steps(2 * len(others) + 1)

    def at(dx: float, dy: float) -> Pose:
        p = pose.position
        return pose.model_copy(
            update={"position": p.model_copy(update={"x": p.x + dx, "y": p.y + dy})}
        )

    def clear(moved: Pose) -> bool:
        return all(_clear(_placed(moved), box) for box in taken)

    for row in steps:
        for k in steps:
            moved = at(BESIDE * k, BESIDE_ROW * row)
            if clear(moved) and stays(moved):
                return moved
    for k in steps:
        if clear(moved := at(BESIDE * k, 0.0)):
            return moved
    return pose


def over(
    site_name: str, site: Assembly, host: str, pose: Pose, boxes: Optional[List[Box]] = None
) -> bool:
    """Whether a camera at ``pose`` lands its picture on ``host``'s top (``""``, the
    floor): one of the cameras of that place."""
    hit = lands(site_name, site, pose, boxes)
    return hit is not None and hit.name == host


def add_here(site_name: str, site: Assembly, host: str) -> Camera:
    """Add a camera above ``host``'s middle (``""``, the floor's), looking straight
    down -- beside a camera already standing there -- its record kept, its node
    appended to the site. ``host`` is one ``check_host`` has let through."""
    boxes = surfaces(site_name, site)
    start = starting_pose(site_name, site, host, boxes)
    with _LOCK:
        cameras = _load()
        pose = beside(
            start,
            [c.pose for c in cameras if c.site == site_name],
            lambda moved: over(site_name, site, host, moved, boxes),
        )
        camera = Camera(
            site=site_name,
            name=_free_name(site_name, site),
            pose=pose,
            added=pose.model_copy(),
            added_at=datetime.now(timezone.utc).isoformat(),
        )
        cameras.append(camera)
        _save(cameras)
    site.children.append(node(camera))
    return camera


def set_pose(
    site_name: str,
    site: Assembly,
    name: str,
    *,
    position: Optional[Vector3D] = None,
    turn: Optional[float] = None,
    tilt: Optional[float] = None,
) -> Camera:
    """Move, turn or tilt a camera: what is given changes, the rest stays. The
    pictures it took already stay where they landed."""

    def posed(camera: Camera) -> Camera:
        update: Dict[str, object] = {}
        if position is not None:
            update["position"] = position
        if turn is not None:
            update["turn"] = turn
        if tilt is not None:
            update["tilt"] = tilt
        pose = Pose.model_validate({**camera.pose.model_dump(), **update})
        return camera.model_copy(update={"pose": pose})

    camera = _change(site_name, name, posed)
    _put(site, camera)
    return camera


def set_device(site_name: str, name: str, device: Optional[Device]) -> Tuple[Camera, List[Camera]]:
    """Which of a browser's cameras this camera is, or (None) none; and the cameras
    the device was taken from. One device is one camera: choosing it for this one
    takes it off any other, in any site."""
    with _LOCK:
        cameras = _load()
        index = next(
            (i for i, c in enumerate(cameras) if c.site == site_name and c.name == name), None
        )
        if index is None:
            raise CameraNotFound(f"no camera {name!r} in site {site_name!r}")
        taken: List[Camera] = []
        if device is not None:
            for i, other in enumerate(cameras):
                if i != index and other.device is not None and other.device.id == device.id:
                    cameras[i] = other.model_copy(update={"device": None})
                    taken.append(cameras[i])
        cameras[index] = cameras[index].model_copy(update={"device": device})
        _save(cameras)
        return cameras[index], taken


def set_lens(site_name: str, name: str, fov: float) -> Camera:
    """A person's field of view for the camera, typed in its editor: the camera's
    lens from now on, taught as a person's."""
    return _change(site_name, name, lambda c: c.model_copy(update={"fov": fov, "fov_taught": True}))


def teach(site_name: str, name: str, fov: float) -> Optional[Camera]:
    """The camera's field of view, taught by the first width a person typed for one
    of its pictures; None when it has been taught already, or is gone."""
    try:
        camera = record(site_name, name)
    except CameraNotFound:
        return None
    if camera.fov_taught:
        return None
    return _change(site_name, name, lambda c: c.model_copy(update={"fov": fov, "fov_taught": True}))


def remove(site_name: str, site: Optional[Assembly], name: str) -> Camera:
    """A camera goes: its record, and its node from the site when the site is there.
    The pictures it took, and the pieces made from them, stay."""
    with _LOCK:
        cameras = _load()
        gone = next((c for c in cameras if c.site == site_name and c.name == name), None)
        if gone is None:
            raise CameraNotFound(f"no camera {name!r} in site {site_name!r}")
        _save([c for c in cameras if c is not gone])
    if site is not None:
        site.children[:] = [c for c in site.children if c.name != name]
    return gone


# --- as the page reads one ------------------------------------------------------------------


def _xyz(v: Vector3D) -> List[float]:
    return [v.x, v.y, v.z]


def _pose_answer(pose: Pose) -> Dict[str, object]:
    return {"position": _xyz(pose.position), "turn": pose.turn, "tilt": pose.tilt}


def answer(camera: Camera, site: Optional[Assembly]) -> Dict[str, object]:
    """A camera as the page reads it: its pose, the pose it was added at, its lens,
    its device, whether its node stands in the site, where its next picture would
    land (``lands``: a host or ``""`` and the point; null for a wall or the sky),
    and the webcam it is drawn as (``body``: its size and its lens, about the lens's
    front face, looking straight down)."""
    landing = lands(camera.site, site, camera.pose) if site is not None else None
    return {
        "name": camera.name,
        "site": camera.site,
        **_pose_answer(camera.pose),
        "added": _pose_answer(camera.added),
        "fov": camera.fov,
        "fov_taught": camera.fov_taught,
        "device": camera.device.model_dump() if camera.device is not None else None,
        "in_site": site is not None and any(c.name == camera.name for c in site.children),
        "lands": (
            {"host": landing.name, "point": list(landing.point)} if landing is not None else None
        ),
        "body": {"size": list(BODY), "lens_d": LENS_D, "lens_h": LENS_H},
    }


__all__ = [
    "BODY",
    "CATEGORY",
    "Camera",
    "CameraNotFound",
    "Device",
    "LENS_D",
    "LENS_H",
    "Pose",
    "RECORDS",
    "START_FOV",
    "START_HEIGHT",
    "WEBCAM",
    "add_here",
    "answer",
    "body",
    "follow",
    "footprint",
    "lands",
    "names",
    "node",
    "over",
    "record",
    "records",
    "remove",
    "set_device",
    "set_lens",
    "set_pose",
    "stand",
    "starting_pose",
    "surfaces",
    "teach",
]
