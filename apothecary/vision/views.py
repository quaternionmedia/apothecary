"""Views: a picture at one place in a site, and the pieces made from its shapes.

A *view* is a picture lying on a *place*: a *host* -- a root structure of the
site that has a footprint and is neither a made piece nor a camera -- or the
site's floor (``host == ""``). A picture added from a file is pinned at the
place it is added at; a picture a camera took lands where the camera's centre
ray first meets an upward-facing surface (``cameras.lands``), and one taken of
a wall or the sky lands nowhere (``host is None``): it is kept, and nothing is
made from it. Pinning finds nothing: Find shapes is a step of its own, and
until it runs a view has no finder and no shapes (``found`` is false), which is
not the same as a finder that found none. What a finder saw is kept on the view.
It is data attached to a place, not a node in the tree: ``GET /sites/{name}``
does not change, so SCAD, STL, validation and jobs never see one.

A shape becomes a *piece*: a root structure of the same site, standing where
the shape was seen, built by ``compose.piece_from_shape``. What is known about
a piece -- its picture, host, camera, shape index, a copy of the shape, its
extent as made, its word and why -- is kept here, keyed by (site, piece), and
never in the site store, so a plain-``def`` forget can mark it and the piece
can find its outline after the view is gone.

**One mapping.** Where any point of a view's picture lies is asked of its one
mapping (``mapping``, a homography from ``projection.py``): the mat's middle and
corners, each shape's outline, where a piece stands and how big it is, the
extents an already-made shape is read against, and re-sizing. It is measured in
the frame a made piece's extent is kept in -- from its host's current
top-centre, so a picture follows its host when the host is moved; at the floor,
in the site's own frame, from an anchor fixed when the view was made.

- A view no camera took (a dropped file, the floor's Add) is flat: ``W`` mm
  across (``mm_across``, a person's width) and ``W`` times its height over its
  width deep, its middle on its host's top-centre -- or at the floor with its
  near edge on the anchor, just past the site's roots in +x. A shape at
  fractions ``(cx, cy)`` of the picture stands ``((cx - 0.5) * W, (0.5 - cy) *
  H)`` from the mat's middle. Unsized, it has no mapping, and nothing is made.
- A view a camera took keeps where the camera stood, how it was aimed and its
  field of view at that moment (``Taken``), so moving the camera after does not
  move it; its picture lands through a pinhole, and ``mm_across`` is its width
  across its centre line. Until a person types a width for it, its field of
  view follows its camera's: the first width typed for any of a camera's
  pictures teaches the camera (``cameras.teach``), and its other pictures no
  person sized follow. A view a person sized keeps its own.

Held in memory behind one lock, as the shelf is, and lost on restart; the lock
is held for dictionary reads and writes only, never while a finder reads a
picture or a file is read. Whether views may be kept in the state folder across a restart
waits on what the draft record *Personal data stays on the device* counts as
this machine.

PROTOTYPE — not ratified.
"""

from __future__ import annotations

import math
import threading
from datetime import datetime
from typing import Dict, List, NamedTuple, Optional, Set, Tuple

from pydantic import BaseModel, Field

from ..hierarchy import Assembly
from ..models.vectors import Vector3D
from .compose import piece_from_shape, sides_as_found, thickness_guess
from .models import FoundShape
from .projection import (
    Laid,
    Matrix,
    across,
    as_lists,
    as_matrix,
    box_of,
    corners,
    down_the_middle,
    flat,
    lay,
    long_side_on,
    moved,
    onto,
    pinhole,
    solve_fov,
)

# The most shapes a view keeps, the most confident first: the outline budget per mat.
VIEW_SHAPES_MOST = 32

# The most made pieces a site holds: what the canvas ring's one grouped Made
# cell can list (two levels of eight, as `menu._grouped` allows).
MADE_MOST = 64

# How far past the site's roots, in +x, a floor mat's near edge is laid.
FLOOR_MARGIN_MM = 200.0

FLOOR = ""

# The reason recorded when a person, not the table, chose a shape's word.
STATED_REASON = "a person said so"


class NotAHost(ValueError):
    """A view or camera was asked to be pinned somewhere that cannot hold one."""


class HostNotFound(LookupError):
    """The host named is not in the site."""


class ViewNotFound(LookupError):
    """No view by that id in that site."""


class NotMade(LookupError):
    """No made piece by that name in that site."""


class CannotMake(ValueError):
    """A make was refused: unsized, already made, no room, landed nowhere, or its host gone."""


class CannotSize(ValueError):
    """A width that no field of view of a camera's picture comes to."""


class Taken(BaseModel):
    """Where a camera stood when it took a view's picture, as the view keeps it:
    moving the camera afterwards does not move the picture.

    ``eye`` is the middle of its lens's front face, measured from the view's
    place as its mapping is: from its host's top-centre, or from its anchor at
    the floor; in the site's frame when the picture landed nowhere. ``turn``
    and ``tilt`` are the camera's, and ``fov`` the field of view across it was
    taken with -- its camera's, or, once a person sized the view, the one that
    gives the width they typed."""

    eye: Vector3D
    turn: float
    tilt: float
    fov: float


class View(BaseModel):
    """One picture lying on one place, and what a finder saw in it, once one has.

    ``finder`` and ``found_at`` are None until Find shapes runs: a view pinned and
    not yet searched. A view searched and holding no shapes has both. ``host`` is
    None for a camera's picture that landed nowhere; ``camera`` names the camera
    part that took it, and ``taken`` is how that camera stood."""

    id: str
    site: str
    host: Optional[str]
    picture: str  # relative to the picture root
    camera: Optional[str] = None
    taken: Optional[Taken] = None
    taken_at: str
    finder: Optional[str] = None
    found_at: Optional[str] = None
    scale: Optional[Dict[str, float]] = None  # a person's: {mm_across} | {known_index, mm}
    mm_across: Optional[float] = None
    pixel_width: int
    pixel_height: int
    shapes: List[FoundShape] = Field(default_factory=list)
    left_out: int = 0
    words: Dict[int, str] = Field(default_factory=dict)  # a person's word per shape
    made: Dict[int, str] = Field(default_factory=dict)  # shape index -> piece
    anchor: Optional[Vector3D] = None  # the floor's, fixed when pinned

    @property
    def tallness(self) -> float:
        return self.pixel_height / self.pixel_width

    @property
    def at_floor(self) -> bool:
        return self.host == FLOOR

    @property
    def placed(self) -> bool:
        """Whether its picture lies anywhere: a camera's that landed on a wall or the sky does not."""
        return self.host is not None

    @property
    def found(self) -> bool:
        """Whether a finder has looked at its picture yet (Find shapes)."""
        return self.found_at is not None


class Extent(BaseModel):
    """Where a piece was made, in millimetres: from its host's top-centre, or in the
    site's frame at the floor. The record, not the live footprint, says what is made."""

    centre: Tuple[float, float]
    size: Tuple[float, float]

    def holds(self, point: Tuple[float, float]) -> bool:
        return all(
            abs(point[axis] - self.centre[axis]) <= self.size[axis] / 2 + 1e-9 for axis in (0, 1)
        )


class Made(BaseModel):
    """How one made piece came to be: its provenance, kept beside the site.

    ``homography`` is its view's mapping when it was made, or last laid on its
    shape by a re-size, in its extent's frame: what its sides as found, its
    turn, and its outline are read through after the view is gone."""

    site: str
    piece: str
    host: str
    view: str
    picture: str
    picture_forgotten: bool = False
    camera: Optional[str] = None
    shape_index: int
    shape: FoundShape
    extent: Extent
    word: str
    word_stated: bool = False
    reason: str
    finder: str
    confidence: float
    origin: str
    mm_across: float
    pixel_width: int
    pixel_height: int
    homography: List[List[float]]
    parameters: Dict[str, float]  # width, depth, height in mm
    parameters_stated: bool = False
    # Where the piece was stood when made, or last laid on its shape by a
    # re-scale, in the site's frame: a piece still standing there was not moved
    # by a person, so a re-scale may lay it on its shape again.
    placed_at: Vector3D = Field(default_factory=Vector3D)

    @property
    def tallness(self) -> float:
        return self.pixel_height / self.pixel_width


def laid_of(record: Made) -> Optional[Laid]:
    """Where a made piece's shape lies, read through the mapping its record keeps."""
    return lay(as_matrix(record.homography), record.shape, record.tallness)


def found_size(record: Made) -> Dict[str, float]:
    """The sides the finder found for a made piece, read through the mapping its
    provenance records, and the thickness guessed from them: what
    ``piece_from_shape`` builds when no person has stated a size. The candidates a
    made piece's editor offers."""
    laid = laid_of(record)
    if laid is not None:
        width, depth = laid.width, laid.depth
    else:  # its shape landed when it was made, so this is not reached
        width, depth = sides_as_found(record.shape, record.mm_across, record.tallness)
    # To a nanometre: a fraction of the picture times a width in millimetres
    # carries a floating-point tail no finder measured, and a candidate reads
    # as the number it is.
    return {
        "width": round(width, 6),
        "depth": round(depth, 6),
        "height": round(thickness_guess(width, depth), 6),
    }


def _same_size(a: Dict[str, float], b: Dict[str, float]) -> bool:
    return all(
        math.isclose(a[k], b[k], rel_tol=1e-9, abs_tol=1e-9) for k in ("width", "depth", "height")
    )


# --- where things are ----------------------------------------------------------------


def top_centre(node: Assembly) -> Vector3D:
    """A root structure's top-centre, in the site's frame (its bounds already are)."""
    b = node.world_bounds()
    assert b is not None
    return Vector3D(
        x=(b.min_point.x + b.max_point.x) / 2,
        y=(b.min_point.y + b.max_point.y) / 2,
        z=b.max_point.z,
    )


def host_node(
    site: Assembly, host: str, made: Set[str], cameras: Set[str] = frozenset()
) -> Optional[Assembly]:
    """The root structure ``host`` names, or None for the floor; refused with its reason.

    Raises ``HostNotFound`` for a name not in the site, and ``NotAHost`` for
    one below the root, one with no footprint, a made piece, or a camera."""
    if host == FLOOR:
        return None
    root_name, _, rest = host.partition(".")
    root = next((c for c in site.children if c.name == root_name), None)
    if root is None:
        raise HostNotFound(f"Node '{host}' not found in site '{site.name}'")
    if rest:
        raise NotAHost(
            f"{host} is inside {root_name}: a picture is pinned, and a camera added, at a "
            f"root structure, so use {root_name}"
        )
    if root_name in made:
        raise NotAHost(
            f"{root_name} is a made piece: pins there would go stale when it is dropped "
            "or the site is reset"
        )
    if root_name in cameras:
        raise NotAHost(
            f"{root_name} is a camera: its pictures land where it looks, not on it; "
            "add at a structure that has a top, or at the floor"
        )
    if root.world_bounds() is None:
        raise NotAHost(
            f"{root_name} has no footprint, so there is no top to lay a picture on; "
            "pin at a structure that has one, or at the floor"
        )
    return root


def floor_anchor(site: Assembly, made: Set[str]) -> Vector3D:
    """The floor mat's near (-x) edge: z 0, y at the centre of the site's roots, x past
    their +x edge by a margin; the origin when there are none. ``made`` -- the made
    pieces and the cameras, what a person added (``added_roots``) -- excluded."""
    bounds = [
        b for c in site.children if c.name not in made and (b := c.world_bounds()) is not None
    ]
    if not bounds:
        return Vector3D()
    return Vector3D(
        x=max(b.max_point.x for b in bounds) + FLOOR_MARGIN_MM,
        y=(min(b.min_point.y for b in bounds) + max(b.max_point.y for b in bounds)) / 2,
        z=0.0,
    )


def added_roots(site_name: str) -> Set[str]:
    """The root structures a person added to the site as it ran: its made pieces and
    its cameras. Neither is a host, and neither moves the floor's anchor."""
    from .cameras import names as camera_names

    return made_names(site_name) | camera_names(site_name)


# --- the one mapping ---------------------------------------------------------------------


def mapping(view: View) -> Optional[Matrix]:
    """The view's one mapping: from a point of its picture (fractions across and
    down) to where it lies, in mm, in the frame its made pieces' extents are kept
    in -- from its host's top-centre, or in the site's frame at the floor.

    A camera's picture lands through a pinhole as ``view.taken`` says the camera
    stood; any other is flat, ``mm_across`` wide, its middle on the host's
    top-centre or its near edge on the floor's anchor. None when there is nothing
    to map by: a flat view nobody sized, or a camera's that landed nowhere."""
    if not view.placed:
        return None
    if view.taken is not None:
        eye = view.taken.eye
        matrix = pinhole(
            (eye.x, eye.y, eye.z), view.taken.turn, view.taken.tilt, view.taken.fov, view.tallness
        )
    elif view.mm_across is not None:
        middle = (view.mm_across / 2, 0.0) if view.at_floor else (0.0, 0.0)
        matrix = flat(view.mm_across, view.tallness, middle)
    else:
        return None
    if view.at_floor:
        anchor = view.anchor or Vector3D()
        matrix = moved(matrix, anchor.x, anchor.y)
    return matrix


def width_of(view: View) -> Optional[float]:
    """How wide a view's picture is across its centre line, in mm: a flat view's
    width as a person gave it, a camera's as its pose and lens make it."""
    if view.taken is None:
        return view.mm_across
    matrix = mapping(view)
    return across(matrix) if matrix is not None else None


def frame_origin(view: View, site: Assembly) -> Optional[Vector3D]:
    """Where the view's mapping is measured from now, in the site's frame: its host's
    top-centre, or the site's origin (at the anchor's height) at the floor. None
    when its host is gone, or its picture landed nowhere."""
    if not view.placed:
        return None
    if view.at_floor:
        return Vector3D(z=(view.anchor or Vector3D()).z)
    node = next((c for c in site.children if c.name == view.host), None)
    if node is None or node.world_bounds() is None:
        return None
    return top_centre(node)


def in_site(view: View, site: Assembly) -> Optional[Matrix]:
    """The view's mapping in the site's frame, onto the plane at ``frame_origin``'s height."""
    origin, matrix = frame_origin(view, site), mapping(view)
    if origin is None or matrix is None:
        return None
    return moved(matrix, origin.x, origin.y)


def mat_centre(view: View, site: Assembly) -> Optional[Vector3D]:
    """Where the middle of the view's picture lies now; None when its host is gone, or
    it landed nowhere. At the floor an unsized mat has no width, and its centre is
    the anchor; at a host, its top-centre."""
    origin = frame_origin(view, site)
    if origin is None:
        return None
    matrix = mapping(view)
    if matrix is None:
        if view.at_floor:
            return (view.anchor or Vector3D()).model_copy()
        return origin
    x, y = onto(matrix, 0.5, 0.5)
    return Vector3D(x=origin.x + x, y=origin.y + y, z=origin.z)


def mat_corners(view: View, site: Assembly) -> Optional[List[Optional[List[float]]]]:
    """Where the picture's corners lie now, in the site's frame -- top left, top
    right, bottom right, bottom left -- each None where it lands nowhere (a camera's
    picture whose top runs past the horizon). None with no mapping."""
    origin, matrix = frame_origin(view, site), in_site(view, site)
    if origin is None or matrix is None:
        return None
    return [[p[0], p[1], origin.z] if p is not None else None for p in corners(matrix)]


def mat_depth(view: View) -> Optional[float]:
    """How deep the view's picture is down its middle, in mm."""
    if view.taken is None:
        return view.mm_across * view.tallness if view.mm_across is not None else None
    matrix = mapping(view)
    return down_the_middle(matrix) if matrix is not None else None


def shape_offset(view: View, shape: FoundShape) -> Tuple[float, float]:
    """A shape's centre from its mat's centre, in millimetres (the view is sized)."""
    matrix = mapping(view)
    assert matrix is not None
    middle = onto(matrix, 0.5, 0.5)
    at = onto(matrix, shape.centre.x, shape.centre.y)
    assert middle is not None and at is not None
    return (at[0] - middle[0], at[1] - middle[1])


def _in_frame(view: View, shape: FoundShape) -> Optional[Tuple[float, float]]:
    """A shape's centre where extents are kept: from the host's top-centre, or in the
    site's frame at the floor; None where it lands nowhere."""
    matrix = mapping(view)
    return onto(matrix, shape.centre.x, shape.centre.y) if matrix is not None else None


def _extent(matrix: Matrix, shape: FoundShape) -> Extent:
    """The extent a shape is made at: its centre, and the upright box its own box covers."""
    centre = onto(matrix, shape.centre.x, shape.centre.y)
    size = box_of(matrix, shape)
    assert centre is not None and size is not None
    return Extent(centre=centre, size=size)


def status_of(view: View, index: int, made: Dict[str, Made]) -> Tuple[str, Optional[str]]:
    """``("made", piece)`` when this view made it, ``("already_made", piece)`` when its
    centre lies inside the extent recorded for a piece made at the same host from any
    view, ``("beyond", None)`` when it lies past the horizon of a camera's picture,
    so there is nothing under it to stand a piece on, else ``("found", None)``. An
    unsized view, or one that landed nowhere, is only ever found or made."""
    if index in view.made:
        return "made", view.made[index]
    matrix = mapping(view)
    if matrix is None:
        return "found", None
    if (
        lay(matrix, view.shapes[index], view.tallness) is None
        or box_of(matrix, view.shapes[index]) is None
    ):
        return "beyond", None
    point = _in_frame(view, view.shapes[index])
    for record in made.values():
        if record.host != view.host:
            continue
        if record.view == view.id and record.shape_index == index:
            continue
        if record.extent.holds(point):
            return "already_made", record.piece
    return "found", None


def word_for_shape(view: View, index: int) -> Tuple[str, str, bool]:
    """(word, reason, stated) for one shape: a person's word, or the table's."""
    from ..vocabulary import word_for

    if index in view.words:
        return view.words[index], STATED_REASON, True
    choice = word_for(view.shapes[index])
    return choice.word, choice.reason, False


def keep_the_most_sure(shapes: List[FoundShape]) -> Tuple[List[FoundShape], int]:
    """At most ``VIEW_SHAPES_MOST`` shapes, the most confident, in the finder's order;
    and how many were left out."""
    if len(shapes) <= VIEW_SHAPES_MOST:
        return list(shapes), 0
    ranked = sorted(range(len(shapes)), key=lambda i: (-shapes[i].confidence, i))
    kept = sorted(ranked[:VIEW_SHAPES_MOST])
    return [shapes[i] for i in kept], len(shapes) - VIEW_SHAPES_MOST


def new_view_id(at: datetime) -> str:
    return f"view_{at:%Y%m%dT%H%M%S%f}Z"


# --- the store -----------------------------------------------------------------------


class Views:
    """Every view pinned and every piece made in this process, behind one lock."""

    def __init__(self) -> None:
        self._views: Dict[str, View] = {}
        self._made: Dict[Tuple[str, str], Made] = {}
        self._forgotten: Set[str] = set()
        self._lock = threading.Lock()

    # views

    def pin(self, view: View) -> View:
        with self._lock:
            base, n = view.id, 2
            while view.id in self._views:
                view = view.model_copy(update={"id": f"{base}-{n}"})
                n += 1
            self._views[view.id] = view.model_copy(deep=True)
            self._forgotten.discard(view.picture)
        return view

    def get(self, site: str, view_id: str) -> View:
        with self._lock:
            found = self._views.get(view_id)
            if found is None or found.site != site:
                raise ViewNotFound(f"no view {view_id!r} in site {site!r}")
            return found.model_copy(deep=True)

    def views_at(self, site: Optional[str] = None) -> List[View]:
        """A site's views (every site's with none named), oldest first."""
        with self._lock:
            chosen = [
                vw.model_copy(deep=True)
                for vw in self._views.values()
                if site is None or vw.site == site
            ]
        return sorted(chosen, key=lambda vw: (vw.taken_at, vw.id))

    def unpin(self, site: str, view_id: str) -> View:
        with self._lock:
            found = self._views.get(view_id)
            if found is None or found.site != site:
                raise ViewNotFound(f"no view {view_id!r} in site {site!r}")
            return self._views.pop(view_id)

    def set_scale(
        self,
        site: str,
        view_id: str,
        scale: Dict[str, float],
        mm_across: float,
        fov: Optional[float] = None,
    ) -> View:
        """A person's width for a view: kept as they gave it (``scale``), and the
        width across it comes to; for a camera's picture, the field of view that
        gives it too, which the view keeps from now on."""
        with self._lock:
            found = self._views.get(view_id)
            if found is None or found.site != site:
                raise ViewNotFound(f"no view {view_id!r} in site {site!r}")
            found.scale = dict(scale)
            found.mm_across = mm_across
            if fov is not None and found.taken is not None:
                found.taken = found.taken.model_copy(update={"fov": fov})
            return found.model_copy(deep=True)

    def follow_lens(self, site: str, camera: str, fov: float) -> List[View]:
        """A camera's lens was taught: each of its pictures in the site that no person
        sized takes the field of view it learned, and its width with it. The views
        that changed."""
        with self._lock:
            followed = []
            for view in self._views.values():
                if view.site != site or view.camera != camera or view.taken is None:
                    continue
                if view.scale is not None or view.taken.fov == fov:
                    continue
                view.taken = view.taken.model_copy(update={"fov": fov})
                view.mm_across = width_of(view)
                followed.append(view.model_copy(deep=True))
            return sorted(followed, key=lambda vw: (vw.taken_at, vw.id))

    def record_found(
        self,
        site: str,
        view_id: str,
        *,
        finder: str,
        shapes: List[FoundShape],
        left_out: int,
        pixel_width: int,
        pixel_height: int,
        at: datetime,
    ) -> View:
        """What a finder saw in a view's picture: kept on the view when it has not
        been searched yet; the view as it is when that finder searched it already;
        and, when another finder did, a new view of the same picture at the same
        host, sized as the first -- a camera's, taken as the first was and sized by
        the same person's width if one was given -- which becomes the newest and is
        answered."""
        with self._lock:
            view = self._views.get(view_id)
            if view is None or view.site != site:
                raise ViewNotFound(f"no view {view_id!r} in site {site!r}")
            found = {
                "finder": finder,
                "found_at": at.isoformat(),
                "shapes": list(shapes),
                "left_out": left_out,
                "pixel_width": pixel_width,
                "pixel_height": pixel_height,
            }
            if not view.found:
                for key, value in found.items():
                    setattr(view, key, value)
                return view.model_copy(deep=True)
            if view.finder == finder:
                return view.model_copy(deep=True)
            base, n = new_view_id(at), 2
            new_id = base
            while new_id in self._views:
                new_id, n = f"{base}-{n}", n + 1
            another = view.model_copy(
                deep=True,
                update={
                    **found,
                    "id": new_id,
                    "taken_at": at.isoformat(),
                    "scale": (
                        dict(view.scale)
                        if view.taken is not None and view.scale is not None
                        else {"mm_across": view.mm_across}
                        if view.taken is None and view.mm_across
                        else None
                    ),
                    "words": {},
                    "made": {},
                },
            )
            self._views[new_id] = another
            return another.model_copy(deep=True)

    def set_word(self, site: str, view_id: str, index: int, word: str) -> View:
        with self._lock:
            found = self._views.get(view_id)
            if found is None or found.site != site:
                raise ViewNotFound(f"no view {view_id!r} in site {site!r}")
            found.words[index] = word
            return found.model_copy(deep=True)

    # made pieces

    def made_at(self, site: str) -> Dict[str, Made]:
        with self._lock:
            return {
                piece: record.model_copy(deep=True)
                for (s, piece), record in self._made.items()
                if s == site
            }

    def made_names(self, site: str) -> Set[str]:
        with self._lock:
            return {piece for (s, piece) in self._made if s == site}

    def made_piece(self, site: str, piece: str) -> Made:
        with self._lock:
            found = self._made.get((site, piece))
            if found is None:
                raise NotMade(f"{piece!r} is not a piece made from a picture in site {site!r}")
            return found.model_copy(deep=True)

    def record_made(self, record: Made) -> bool:
        """Keep a made piece's provenance and mark its shape made in its view.

        False, and nothing kept, when the view already made that shape. A view
        unpinned meanwhile keeps nothing; the record is kept all the same, and
        marked forgotten when its picture was forgotten meanwhile."""
        with self._lock:
            view = self._views.get(record.view)
            if view is not None and record.shape_index in view.made:
                return False
            if record.picture in self._forgotten and view is None:
                record = record.model_copy(update={"picture_forgotten": True})
            if view is not None:
                view.made[record.shape_index] = record.piece
            self._made[(record.site, record.piece)] = record.model_copy(deep=True)
            return True

    def update_made(self, record: Made) -> None:
        with self._lock:
            if (record.site, record.piece) in self._made:
                self._made[(record.site, record.piece)] = record.model_copy(deep=True)

    def drop(self, site: str, piece: str) -> Made:
        """Forget a made piece's provenance; its shape reads as found again."""
        with self._lock:
            record = self._made.pop((site, piece), None)
            if record is None:
                raise NotMade(f"{piece!r} is not a piece made from a picture in site {site!r}")
            view = self._views.get(record.view)
            if view is not None and view.made.get(record.shape_index) == piece:
                del view.made[record.shape_index]
            return record

    def forget_made(self, site: str) -> List[str]:
        """Every made piece of a site is gone (a reset): its records and its views' marks."""
        with self._lock:
            gone = [piece for (s, piece) in self._made if s == site]
            for piece in gone:
                del self._made[(site, piece)]
            for view in self._views.values():
                if view.site == site:
                    view.made.clear()
            return gone

    # pictures

    def forget_picture(self, picture: str) -> List[str]:
        """A kept picture was forgotten: its views are unpinned, every site's, and the
        pieces made from it stay, marked forgotten. Returns the views unpinned."""
        with self._lock:
            unpinned = [lid for lid, vw in self._views.items() if vw.picture == picture]
            for lid in unpinned:
                del self._views[lid]
            for record in self._made.values():
                if record.picture == picture:
                    record.picture_forgotten = True
            self._forgotten.add(picture)
            return unpinned

    def kept_again(self, picture: str) -> None:
        """A picture was kept at a path once forgotten: it is a new picture."""
        with self._lock:
            self._forgotten.discard(picture)


_store: Optional[Views] = None
_made_store = threading.Lock()


def store() -> Views:
    """The one view store this process uses."""
    global _store
    with _made_store:
        if _store is None:
            _store = Views()
        return _store


def forget_made(site: str) -> List[str]:
    """What ``SiteStore.reset`` calls: a site rebuilt from its code has no made pieces."""
    return store().forget_made(site)


def made_names(site: str) -> Set[str]:
    return store().made_names(site)


# --- making, rebuilding, dropping: the site changes the view routes carry out ----------
#
# Each takes the live site and changes it in place. The routes that call them are
# `async def`, one at a time on the event loop, as api.py's rule for routes that
# change a site says; the store's lock covers what a plain-`def` route (a forget)
# may do meanwhile.


def _unique_name(site: Assembly, word: str) -> str:
    taken = {c.name for c in site.children}
    n = 1
    while f"{word}_{n}" in taken:
        n += 1
    return f"{word}_{n}"


class Making(NamedTuple):
    """What a Make did: the pieces made, the shapes skipped as already made, and
    the shapes left because they lie past the horizon of a camera's picture."""

    made: List[str]
    skipped: int
    beyond: int = 0


AIM_DOWN = (
    "this picture landed nowhere: its camera was looking at a wall or the sky, so "
    "there is no top or floor under it to stand a piece on. Aim the camera down at "
    "a structure's top or the floor, take another picture, and make from that"
)


def make(site_name: str, site: Assembly, view_id: str, shape: Optional[int] = None) -> Making:
    """Make one shape (``shape``) or every shape not yet made (``None``) into pieces.

    Each piece stands where its shape lies, as big as it lies there, both read
    through the view's one mapping. Returns the pieces made, how many shapes were
    skipped as already made, and how many lie past a camera picture's horizon.
    Refused (``CannotMake``), naming the step that comes first, for a view whose
    shapes have not been found (Find shapes) or that has none, for one that landed
    nowhere (aim the camera down), for an unsized view (its width in Selected,
    Size), a single shape already made or past the horizon, a host that is gone,
    or more made pieces than the site's Made cell holds."""
    views = store()
    view = views.get(site_name, view_id)
    if not view.found:
        raise CannotMake(
            "no shapes have been found in this view yet: Picture › Find shapes finds "
            "them, and then Make makes them pieces"
        )
    if not view.shapes:
        raise CannotMake(
            f"{view.finder} found no shapes in this view, so there is nothing to make: "
            "Find shapes with another finder, or pin another picture"
        )
    if shape is not None and not 0 <= shape < len(view.shapes):
        raise ViewNotFound(f"view {view_id!r} has no shape {shape}")
    if not view.placed:
        raise CannotMake(AIM_DOWN)
    matrix = mapping(view)
    if matrix is None:
        raise CannotMake(
            "this view has no width yet: type the picture's width, or one shape's long "
            "side, in Selected (Picture › Size), and then Make"
        )
    origin = frame_origin(view, site)
    if origin is None:
        raise CannotMake(f"{view.host} is no longer in the site, so there is nowhere to stand it")
    made = views.made_at(site_name)
    chosen = [shape] if shape is not None else list(range(len(view.shapes)))
    to_make, skipped, beyond = [], 0, 0
    for index in chosen:
        status, piece = status_of(view, index, made)
        if status == "found":
            to_make.append(index)
            continue
        if shape is not None and status == "beyond":
            raise CannotMake(
                f"shape {index} lies past this picture's horizon, so there is nothing under "
                "it to stand a piece on: aim the camera further down and take another picture"
            )
        if shape is not None:
            raise CannotMake(
                f"shape {index} is already made: its centre lies in {piece} as it was made"
            )
        if status == "beyond":
            beyond += 1
        else:
            skipped += 1
    if len(made) + len(to_make) > MADE_MOST:
        raise CannotMake(
            f"{len(made)} piece(s) are made in this site and {len(to_make)} more would pass "
            f"{MADE_MOST}, the most the Made cell holds; drop some first"
        )
    width = width_of(view)
    assert width is not None
    names: List[str] = []
    for index in to_make:
        found = view.shapes[index]
        laid = lay(matrix, found, view.tallness)
        assert laid is not None  # status_of said it lands
        word, reason, stated = word_for_shape(view, index)
        name = _unique_name(site, word)
        piece, _about = piece_from_shape(
            found,
            name=name,
            word=word,
            reason=reason,
            per_unit=width,
            tallness=view.tallness,
            finder=view.finder,
            laid=laid,
        )
        piece.position = piece.position + origin
        record = Made(
            site=site_name,
            piece=name,
            host=view.host,
            view=view.id,
            picture=view.picture,
            camera=view.camera,
            shape_index=index,
            shape=found,
            extent=_extent(matrix, found),
            word=word,
            word_stated=stated,
            reason=reason,
            finder=view.finder,
            confidence=found.confidence,
            origin=found.origin,
            mm_across=width,
            pixel_width=view.pixel_width,
            pixel_height=view.pixel_height,
            homography=as_lists(matrix),
            parameters=_sides(laid),
            placed_at=piece.position.model_copy(),
        )
        if views.record_made(record):
            site.children.append(piece)
            names.append(name)
        else:
            skipped += 1
    return Making(names, skipped, beyond)


def _sides(laid: Laid, size=None) -> Dict[str, float]:
    """The sides a piece is built with, before it is turned: a person's, else its
    shape's as it lies, and the thickness guessed from them. Its footprint is the
    box of it as turned, which is not its sides for a turned piece."""
    if size is not None:
        return {"width": size.width, "depth": size.depth, "height": size.height}
    return {
        "width": laid.width,
        "depth": laid.depth,
        "height": thickness_guess(laid.width, laid.depth),
    }


def _index_of(site_name: str, site: Assembly, piece: str) -> int:
    index = next((i for i, c in enumerate(site.children) if c.name == piece), None)
    if index is None:
        raise NotMade(f"{piece!r} is no longer in site {site_name!r}")
    return index


def _rebuilt_in_place(
    site: Assembly,
    index: int,
    record: Made,
    *,
    word: str,
    reason: str,
    size,
    laid: Laid,
    mm_across: float,
) -> Assembly:
    """The piece at ``index`` built again from its shape as it lies (``laid``),
    standing where it stood."""
    rebuilt, _about = piece_from_shape(
        record.shape,
        name=record.piece,
        word=word,
        reason=reason,
        per_unit=mm_across,
        tallness=record.tallness,
        finder=record.finder,
        size=size,
        laid=laid,
    )
    rebuilt.position = site.children[index].position
    site.children[index] = rebuilt
    return rebuilt


def rebuild(
    site_name: str,
    site: Assembly,
    piece: str,
    *,
    word: Optional[str] = None,
    parameters: Optional[Dict[str, float]] = None,
) -> Made:
    """Rebuild a made piece in place from its shape: another word, or a person's sides
    and thickness. Its name and position stay.

    Sides a person gives are ``parameters_stated`` -- unless they are the sides
    the finder found, in which case the piece reads as found again: the found
    candidate in its editor returns it to what it was, and a re-scale of its
    view rebuilds it with the rest."""
    from ..vocabulary import WordShape, starter_words

    views = store()
    record = views.made_piece(site_name, piece)
    index = _index_of(site_name, site, piece)
    if word is not None and word not in starter_words():
        raise ValueError(f"no word named {word!r}; have {starter_words().names()}")
    new_word = word or record.word
    stated = record.word_stated or word is not None
    reason = STATED_REASON if word is not None else record.reason
    size = WordShape(**parameters) if parameters else None
    if size is None and record.parameters_stated:
        size = WordShape(**record.parameters)
    laid = laid_of(record)
    assert laid is not None  # its record's mapping is the one it was made through
    _rebuilt_in_place(
        site,
        index,
        record,
        word=new_word,
        reason=reason,
        size=size,
        laid=laid,
        mm_across=record.mm_across,
    )
    built = _sides(laid, size)
    record = record.model_copy(
        update={
            "word": new_word,
            "word_stated": stated,
            "reason": reason,
            "parameters": built,
            "parameters_stated": (record.parameters_stated or parameters is not None)
            and not _same_size(built, found_size(record)),
        }
    )
    views.update_made(record)
    return record


def _same_place(a: Vector3D, b: Vector3D) -> bool:
    return all(math.isclose(getattr(a, k), getattr(b, k), abs_tol=1e-6) for k in ("x", "y", "z"))


def rescale_made(site_name: str, site: Assembly, view: View) -> List[str]:
    """After a view is re-sized: every piece made from it whose sides no person
    stated is rebuilt from its shape through the view's mapping as it is now, the
    scale in its provenance following, and laid on its shape again when it still
    stands where it was made -- a piece a person moved stays put. A piece whose
    shape now lies past a camera picture's horizon is left as it was. The names of
    the pieces rebuilt."""
    matrix, width = mapping(view), width_of(view)
    if matrix is None or width is None:
        return []
    views = store()
    origin = frame_origin(view, site)
    rebuilt: List[str] = []
    for name, record in sorted(views.made_at(site_name).items()):
        if record.view != view.id or record.parameters_stated:
            continue
        index = next((i for i, c in enumerate(site.children) if c.name == name), None)
        if index is None:
            continue
        laid = lay(matrix, record.shape, record.tallness)
        if laid is None or box_of(matrix, record.shape) is None:
            continue
        stood_still = _same_place(site.children[index].position, record.placed_at)
        piece = _rebuilt_in_place(
            site,
            index,
            record,
            word=record.word,
            reason=record.reason,
            size=None,
            laid=laid,
            mm_across=width,
        )
        update: Dict[str, object] = {
            "mm_across": width,
            "homography": as_lists(matrix),
            "parameters": _sides(laid),
        }
        if stood_still and origin is not None:
            piece.position = Vector3D(
                x=origin.x + laid.centre[0], y=origin.y + laid.centre[1], z=origin.z
            )
            update["placed_at"] = piece.position.model_copy()
            update["extent"] = _extent(matrix, record.shape)
        views.update_made(record.model_copy(update=update))
        rebuilt.append(name)
    return rebuilt


# --- a camera's pictures, and its lens taught ------------------------------------------------


def taken_by(
    site_name: str,
    site: Assembly,
    camera,
    *,
    picture: str,
    pixel_width: int,
    pixel_height: int,
    at: datetime,
) -> View:
    """A view of a picture ``camera`` (a ``cameras.Camera``) took as it stands now,
    nothing found in it: it lies where the camera's centre ray first meets a top or
    the floor, or (``host`` None) nowhere. It keeps the camera's pose and lens."""
    from .cameras import lands

    pose = camera.pose
    hit = lands(site_name, site, pose)
    eye, anchor, host = pose.position, None, None
    if hit is not None and hit.name == FLOOR:
        host = FLOOR
        anchor = Vector3D(x=hit.point[0], y=hit.point[1], z=0.0)
        eye = eye - anchor
    elif hit is not None:
        host = hit.name
        eye = eye - top_centre(next(c for c in site.children if c.name == hit.name))
    view = View(
        id=new_view_id(at),
        site=site_name,
        host=host,
        picture=picture,
        camera=camera.name,
        taken=Taken(eye=eye, turn=pose.turn, tilt=pose.tilt, fov=camera.fov),
        taken_at=at.isoformat(),
        pixel_width=pixel_width,
        pixel_height=pixel_height,
        anchor=anchor,
    )
    view.mm_across = width_of(view)
    return view


def fov_for(
    view: View, *, mm_across: Optional[float] = None, known_index: Optional[int] = None, mm=None
) -> float:
    """The field of view at which a camera's picture comes to a person's width: the
    picture's across its centre line (``mm_across``), or one shape's long side
    (``known_index``, ``mm``), as ``ScaleReference`` reads them off a flat one.
    Solved by bisection; refused (``CannotSize``) when no field of view gets there."""
    assert view.taken is not None

    def at(fov: float) -> Optional[Matrix]:
        return mapping(
            view.model_copy(update={"taken": view.taken.model_copy(update={"fov": fov})})
        )

    if mm_across is not None:
        target, said = mm_across, f"{mm_across:g} mm across"

        def measure(fov: float) -> Optional[float]:
            matrix = at(fov)
            return across(matrix) if matrix is not None else None

    else:
        shape = view.shapes[known_index]
        target, said = mm, f"shape {known_index}'s long side {mm:g} mm"

        def measure(fov: float) -> Optional[float]:
            matrix = at(fov)
            return long_side_on(matrix, shape, view.tallness) if matrix is not None else None

    fov = solve_fov(measure, target)
    if fov is None:
        raise CannotSize(
            f"no field of view makes this picture {said} from where its camera stood: "
            "check the number, or move the camera and take another picture"
        )
    return fov


def size_by_lens(
    site_name: str, site: Assembly, view: View, scale: Dict[str, float], fov: float
) -> Tuple[View, List[str], Optional[str]]:
    """A person sized a camera's picture: the view keeps the field of view that
    gives their width. The first width typed for any of a camera's pictures
    teaches the camera too, and each of its pictures here that no person sized
    follows the lens it learned, its made pieces re-sized as a re-size re-sizes
    them. The view as it is now, every piece rebuilt, and the camera taught (None
    when it was taught already, or is gone)."""
    from . import cameras

    views = store()
    width = width_of(view.model_copy(update={"taken": view.taken.model_copy(update={"fov": fov})}))
    sized = views.set_scale(site_name, view.id, scale, width, fov=fov)
    rebuilt = rescale_made(site_name, site, sized)
    taught = cameras.teach(site_name, view.camera, fov) if view.camera else None
    if taught is not None:
        rebuilt.extend(lens_followed(site_name, site, taught.name, fov))
    return sized, sorted(set(rebuilt)), taught.name if taught is not None else None


def lens_followed(site_name: str, site: Assembly, camera: str, fov: float) -> List[str]:
    """A camera's lens changed -- taught by a width, or typed in its editor: each of
    its pictures here that no person sized takes the new field of view, and the
    pieces made from them re-size as a re-size re-sizes them. The pieces rebuilt."""
    rebuilt: List[str] = []
    for follower in store().follow_lens(site_name, camera, fov):
        if follower.placed:  # one that landed nowhere has nothing made from it
            rebuilt.extend(rescale_made(site_name, site, follower))
    return sorted(set(rebuilt))


def drop(site_name: str, site: Assembly, piece: str) -> Made:
    """The piece goes from the site; its shape reads as found again."""
    record = store().drop(site_name, piece)
    site.children[:] = [c for c in site.children if c.name != piece]
    return record


__all__ = [
    "AIM_DOWN",
    "FLOOR",
    "FLOOR_MARGIN_MM",
    "VIEW_SHAPES_MOST",
    "MADE_MOST",
    "CannotMake",
    "CannotSize",
    "Extent",
    "HostNotFound",
    "Making",
    "Taken",
    "View",
    "ViewNotFound",
    "Views",
    "Made",
    "NotAHost",
    "NotMade",
    "added_roots",
    "drop",
    "floor_anchor",
    "forget_made",
    "found_size",
    "fov_for",
    "frame_origin",
    "host_node",
    "in_site",
    "keep_the_most_sure",
    "laid_of",
    "lens_followed",
    "make",
    "made_names",
    "mapping",
    "mat_centre",
    "mat_corners",
    "mat_depth",
    "rebuild",
    "rescale_made",
    "shape_offset",
    "size_by_lens",
    "status_of",
    "store",
    "taken_by",
    "top_centre",
    "width_of",
    "word_for_shape",
]
