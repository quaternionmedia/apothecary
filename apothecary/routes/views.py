"""Views from the browser: a picture lying on a place, its shapes, the pieces made.

The store, the anchors, the one mapping and the making are
``apothecary/vision/views.py``; these routes are its doors. ``host: ""`` is the
site's floor in every one; a view whose ``host`` is null is a camera's picture
that landed nowhere.

Plain ``def``, on the threadpool, for the routes that change no site -- a find
reads a file and may be slow, and the store's lock is never held across it:

- ``POST /sites/{s}/views`` ``{host?, picture, mm_across?}`` pins a picture
  under the picture root at a host (the floor when none is named) as a view,
  and finds nothing: its ``finder`` and ``found_at`` are null and it has no
  shapes. ``{camera, picture}`` makes it that camera part's picture instead,
  lying where the camera looks and keeping how it stood, as Take picture does
  (``POST /photos/pictures?site=&camera=``).
- ``POST /sites/{s}/views/{id}/find`` ``{finder?}`` is Find shapes: the finder
  (``plain`` unless named) reads the view's picture, through the finder cache,
  and its shapes are kept on the view; another finder's shapes on a view
  already searched are a new view of the same picture at the same host.
- ``DELETE /sites/{s}/views/{id}`` unpins a view; its picture and pieces stay.
- ``GET /sites/{s}/attached``: a site's camera parts (each with its pose, its
  field of view, its device and where its next picture would land), views and
  made pieces, in one.
- ``GET /placed``: every site's cameras, boards and views, each a row to take back.

A made piece is a part (``vision/piece.py``), and answers the parameter contract
a part from the parts folder answers (``projects/parts/params.py``):

- ``GET /sites/{s}/made/{piece}/params``: its fields, defaults and the
  candidates its provenance offers, as ``GET /parts/{name}/params`` does.
- ``POST /sites/{s}/made/{piece}/validate`` ``{params}``: a staged set checked
  and the envelope it would produce, as ``POST /parts/{name}/validate`` does.
- ``GET /sites/{s}/made/{piece}/scad``: the few lines of SCAD its geometry is.

``async def``, one at a time on the event loop, as api.py's rule for routes that
change a site says; each answers with the site as ``GET /sites/{s}`` does:

- ``PUT /sites/{s}/views/{id}/scale`` ``{mm_across} | {known_index, mm}`` sizes
  a view and rebuilds every piece made from it whose sides no person stated
  (``rebuilt`` names them). A camera's picture is sized by the field of view
  that gives the width, found by bisection and kept on the view; the first
  width typed for any of a camera's pictures teaches the camera that field of
  view (``taught``), and its pictures no person sized follow it, their pieces
  rebuilt too.
- ``PUT /sites/{s}/views/{id}/shapes/{i}`` ``{word}``: a person's word for a
  shape; on a made shape it rebuilds the piece in place.
- ``POST /sites/{s}/views/{id}/make`` ``{shape} | {all: true}``: pieces from
  shapes, skipping the shapes already made and those past a camera picture's
  horizon (``beyond``), each standing where its shape lies and as big as it
  is there, through the view's one mapping.
- ``PUT /sites/{s}/made/{piece}`` ``{params: {word?, width?, depth?, height?}}``
  (the editor's), or ``{word?, parameters?}`` (the ring's Word), and ``DELETE
  /sites/{s}/made/{piece}`` (Drop): keyed by the piece, so they work after its
  view is unpinned or its picture forgotten.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ..hierarchy import Assembly
from ..projects.parts.params import ParamsSpec, Validation, params_spec, validate_staged
from ..projects.parts.stl_renderer import geometry_scad
from ..vision import cameras
from ..vision import views as viewing
from ..vision.models import FoundShape, ScaleReference
from ..vision.piece import SIDES, MadePart
from ..vision.projection import as_lists
from ..vision.views import Made, View

router = APIRouter(tags=["views"])


# --- answers -------------------------------------------------------------------------


def _point(p) -> List[float]:
    return [p.x, p.y]


def shape_answer(shape: FoundShape) -> Dict[str, object]:
    return {
        "kind": shape.kind.value,
        "min": _point(shape.min_point),
        "max": _point(shape.max_point),
        "points": [_point(p) for p in shape.points],
        "confidence": shape.confidence,
        "origin": shape.origin,
        "label": shape.label,
        "turned_degrees": shape.turned_degrees,
        "long_side": shape.long_side,
        "short_side": shape.short_side,
    }


def _xyz(v) -> List[float]:
    return [v.x, v.y, v.z]


def view_answer(view: View, site: Optional[Assembly], made: Dict[str, Made]) -> Dict[str, object]:
    """A view as the page reads it: its mat where it lies now, and each shape's state.
    ``finder`` and ``found_at`` are null until Find shapes has run on it.

    The mat carries the view's one mapping in the site's frame (``homography``,
    rows of three: ``(u, v, 1)`` multiplied out is ``(x * w, y * w, w)``, at the
    mat's height), which every point of the picture -- a corner, an outline --
    is laid through, and its four ``corners`` already laid, each null where a
    camera's picture runs past the horizon. ``taken`` is how a camera stood when
    it took the picture; ``scale`` is null on one no person sized, whose field of
    view follows its camera's lens."""
    centre = viewing.mat_centre(view, site) if site is not None else None
    width = view.mm_across
    in_site = viewing.in_site(view, site) if site is not None else None
    shapes = []
    for index, shape in enumerate(view.shapes):
        word, reason, stated = viewing.word_for_shape(view, index)
        status, piece = viewing.status_of(view, index, made)
        shapes.append(
            {
                "index": index,
                **shape_answer(shape),
                "word": word,
                "reason": reason,
                "word_stated": stated,
                "status": status,
                "piece": piece,
            }
        )
    return {
        **view_row(view, site),
        "found_at": view.found_at,
        "scale": view.scale,
        "mm_across": width,
        "pixel_width": view.pixel_width,
        "pixel_height": view.pixel_height,
        "left_out": view.left_out,
        "made": {str(i): piece for i, piece in sorted(view.made.items())},
        "anchor": _xyz(view.anchor) if view.anchor is not None else None,
        "taken": (
            {
                "eye": _xyz(view.taken.eye),
                "turn": view.taken.turn,
                "tilt": view.taken.tilt,
                "fov": view.taken.fov,
            }
            if view.taken is not None
            else None
        ),
        "mat": (
            {
                "centre": _xyz(centre),
                "width": width,
                "depth": viewing.mat_depth(view),
                "corners": viewing.mat_corners(view, site),
                "homography": as_lists(in_site) if in_site is not None else None,
            }
            if centre is not None
            else None
        ),
        "shapes": shapes,
    }


def view_row(view: View, site: Optional[Assembly]) -> Dict[str, object]:
    """A view as one row of what is pinned: enough to name it and take it back.
    ``placed`` is false for a camera's picture that landed nowhere."""
    host_found = (
        site is not None
        and view.placed
        and (view.at_floor or any(c.name == view.host for c in site.children))
    )
    return {
        "id": view.id,
        "site": view.site,
        "host": view.host,
        "host_found": host_found,
        "placed": view.placed,
        "picture": view.picture,
        "camera": view.camera,
        "taken_at": view.taken_at,
        "finder": view.finder,
    }


def made_answer(record: Made, pinned: bool) -> Dict[str, object]:
    """A made piece as the page reads it: its provenance, and beside the sides it
    has (``parameters``) the sides the finder found (``found``), so the page can
    say whose the size is."""
    answer = record.model_dump(mode="json")
    answer["shape"] = shape_answer(record.shape)
    answer["view_pinned"] = pinned
    answer["found"] = viewing.found_size(record)
    return answer


def _site_answer(site_name: str, site: Assembly) -> Dict[str, object]:
    from ..api import _site_payload, _site_store

    return _site_payload(site, _site_store.validator(site_name)(site))


def _site(site_name: str) -> Assembly:
    from ..api import _get_site_or_404

    return _get_site_or_404(site_name)


def _view_or_404(site_name: str, view_id: str) -> View:
    try:
        return viewing.store().get(site_name, view_id)
    except viewing.ViewNotFound as missing:
        raise HTTPException(status_code=404, detail=str(missing).strip('"')) from None


def _answer(site_name: str, view: View) -> Dict[str, object]:
    return view_answer(view, _site(site_name), viewing.store().made_at(site_name))


# --- pinning ---------------------------------------------------------------------------


def check_host(site_name: str, host: str) -> Assembly:
    """The site, once ``host`` is known to be able to hold a view or a camera; or refused."""
    site = _site(site_name)
    try:
        viewing.host_node(site, host, viewing.made_names(site_name), cameras.names(site_name))
    except viewing.HostNotFound as missing:
        raise HTTPException(status_code=404, detail=str(missing).strip('"')) from None
    except viewing.NotAHost as refused:
        raise HTTPException(status_code=422, detail=str(refused)) from None
    return site


def _picture_at(picture: str) -> Path:
    """A picture under the root, by the path the listing gave; refused elsewhere."""
    from ..api import _picture_root, _picture_within_root

    asked = Path(picture)
    return _picture_within_root(asked if asked.is_absolute() else _picture_root() / asked)


def _picture_size(where: Path) -> Tuple[int, int]:
    """A picture's width and height in pixels, upright as a finder reads it: read
    from its header and its orientation tag, without decoding its pixels."""
    from PIL import Image, UnidentifiedImageError

    try:
        with Image.open(where) as opened:
            width, height = opened.size
            turned = opened.getexif().get(0x0112) in (5, 6, 7, 8)
    except (OSError, UnidentifiedImageError, ValueError) as exc:
        raise HTTPException(
            status_code=400, detail=f"{where.name} could not be read as a picture: {exc}"
        ) from None
    return (height, width) if turned else (width, height)


def pin_picture(
    site_name: str, host: str, picture: str, *, mm_across: Optional[float] = None
) -> View:
    """Pin a picture under the root at ``host`` as a view no camera took, finding
    nothing in it: flat, and unsized until a person gives its width.

    Find shapes (``find_in``) is the step that finds its shapes."""
    from ..api import _picture_root

    site = check_host(site_name, host)
    root = _picture_root()
    where = _picture_at(picture)
    width, height = _picture_size(where)
    at = datetime.now(timezone.utc)
    view = View(
        id=viewing.new_view_id(at),
        site=site_name,
        host=host,
        picture=where.relative_to(root).as_posix(),
        taken_at=at.isoformat(),
        scale={"mm_across": mm_across} if mm_across else None,
        mm_across=mm_across or None,
        pixel_width=width,
        pixel_height=height,
        anchor=(
            viewing.floor_anchor(site, viewing.added_roots(site_name))
            if host == viewing.FLOOR
            else None
        ),
    )
    return viewing.store().pin(view)


def camera_or_404(site_name: str, name: str) -> cameras.Camera:
    """A camera part of the site, or a 404 that says so."""
    _site(site_name)
    try:
        return cameras.record(site_name, name)
    except cameras.CameraNotFound as missing:
        raise HTTPException(status_code=404, detail=str(missing).strip('"')) from None


def take_picture(site_name: str, camera: str, picture: str) -> View:
    """A picture under the root, as the camera part ``camera`` took it standing as it
    stands now: a view lying where the camera's centre ray first meets a top or the
    floor -- or nowhere, at a wall or the sky -- keeping the camera's pose and lens,
    and finding nothing in it. What Take picture pins."""
    from ..api import _picture_root

    taker = camera_or_404(site_name, camera)
    site = _site(site_name)
    where = _picture_at(picture)
    width, height = _picture_size(where)
    view = viewing.taken_by(
        site_name,
        site,
        taker,
        picture=where.relative_to(_picture_root()).as_posix(),
        pixel_width=width,
        pixel_height=height,
        at=datetime.now(timezone.utc),
    )
    return viewing.store().pin(view)


def find_in(site_name: str, view_id: str, finder: str = "plain") -> View:
    """Find shapes: ``finder`` reads a view's picture, and what it saw is kept on the
    view -- or, on a view another finder searched already, on a new view of the
    same picture at the same host. The finder runs outside every lock, through the
    finder cache, so the same picture is read once per finder."""
    from ..vision import get as get_finder
    from ..vision.cache import cache

    view = _view_or_404(site_name, view_id)
    where = _picture_at(view.picture)
    try:
        seer = get_finder(finder)
    except KeyError:
        raise HTTPException(status_code=400, detail=f"no finder named {finder!r}") from None
    try:
        seen = cache().look(seer, where)
    except (OSError, ValueError) as exc:
        raise HTTPException(
            status_code=400, detail=f"{where.name} could not be read: {exc}"
        ) from None
    shapes, left_out = viewing.keep_the_most_sure(seen.shapes)
    try:
        found = viewing.store().record_found(
            site_name,
            view_id,
            finder=seen.finder,
            shapes=shapes,
            left_out=left_out,
            pixel_width=seen.pixel_width,
            pixel_height=seen.pixel_height,
            at=datetime.now(timezone.utc),
        )
    except viewing.ViewNotFound as missing:
        raise HTTPException(status_code=404, detail=str(missing).strip('"')) from None
    return found


def finders_for(picture: str) -> List[str]:
    """The finders that can read a picture under the root: every one, except a
    finder that reads a description beside the picture when there is none.
    What the ring's Find shapes offers, so it is offered only where it can do
    something."""
    from ..api import _picture_root, _picture_within_root
    from ..vision import get as get_finder
    from ..vision import names as finder_names

    root = _picture_root()
    try:
        where = _picture_within_root(root / picture)
    except HTTPException:
        return []
    readable = []
    for name in finder_names():
        seer = get_finder(name)
        described = getattr(seer, "description_path", None)
        if described is not None and not described(where).is_file():
            continue
        readable.append(name)
    return readable


CAMERA_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$"


class PinView(BaseModel):
    """A picture to pin, and where: at a host (the floor, ``""``, when none is
    named), or as the picture a camera part took. A finder is not asked for here:
    finding is Find shapes, its own request, so a pin that names one is refused
    rather than silently not found."""

    model_config = ConfigDict(extra="forbid")

    host: Optional[str] = Field(None, max_length=400)
    picture: str = Field(..., min_length=1, max_length=400)
    camera: Optional[str] = Field(None, pattern=CAMERA_PATTERN)
    mm_across: Optional[float] = Field(None, gt=0, allow_inf_nan=False)

    @model_validator(mode="after")
    def _a_host_or_a_camera(self) -> "PinView":
        if self.camera is not None and self.host is not None:
            raise ValueError(
                "a camera's picture lies where the camera looks: give the camera, or a "
                "host, not both"
            )
        if self.camera is not None and self.mm_across is not None:
            raise ValueError(
                "a camera's picture is sized by how the camera stands; to say its width, "
                "size it once it is pinned (PUT .../scale)"
            )
        return self


@router.post("/sites/{site_name}/views", status_code=201)
def pin_view(site_name: str, body: PinView):
    """Pin a picture as a view at a host, or the floor (``""``), or as the picture a
    camera part took; nothing is found yet."""
    if body.camera is not None:
        view = take_picture(site_name, body.camera, body.picture)
    else:
        view = pin_picture(
            site_name, body.host or viewing.FLOOR, body.picture, mm_across=body.mm_across
        )
    return _answer(site_name, view)


class FindBody(BaseModel):
    finder: str = Field("plain", min_length=1, max_length=64)


@router.post("/sites/{site_name}/views/{view_id}/find")
def find_shapes(site_name: str, view_id: str, body: Optional[FindBody] = None):
    """Find shapes in a view's picture: the view as it is now, its shapes found --
    or, when another finder had searched it, the new view that holds this
    finder's shapes, which is the newest at its host."""
    found = find_in(site_name, view_id, (body or FindBody()).finder)
    return _answer(site_name, found)


class ScaleBody(BaseModel):
    """The picture's width, or one shape's long side: millimetres either way."""

    mm_across: Optional[float] = Field(None, gt=0, allow_inf_nan=False)
    known_index: Optional[int] = Field(None, ge=0)
    mm: Optional[float] = Field(None, gt=0, allow_inf_nan=False)

    @model_validator(mode="after")
    def _one_way(self) -> "ScaleBody":
        by_width = self.mm_across is not None
        by_shape = self.known_index is not None or self.mm is not None
        if by_width == by_shape:
            raise ValueError("give the picture's width (mm_across), or a shape and its long side")
        if by_shape and (self.known_index is None or self.mm is None):
            raise ValueError("a shape's long side needs both known_index and mm")
        return self


@router.put("/sites/{site_name}/views/{view_id}/scale")
async def size_view(site_name: str, view_id: str, body: ScaleBody):
    """Size a view by the picture's width or one shape's long side.

    Every piece made from the view whose sides no person stated is rebuilt at
    the new width, in place, and laid on its shape again if it still stands
    where it was made (``rebuilt`` names them; ``site`` is the site as it is
    now). A piece whose sides a person stated keeps them, and the scale it was
    made at, in its provenance.

    A camera's picture is sized by its field of view: the one that brings it to
    the width given, found by bisection, kept on the view. The first width typed
    for any of a camera's pictures teaches the camera that field of view
    (``taught`` names it), and its pictures here no person sized follow, their
    pieces rebuilt as this view's are. ``async def``: a rebuild changes the site."""
    from ..vision.models import Picture

    view = _view_or_404(site_name, view_id)
    site = _site(site_name)
    if body.mm_across is None:
        if not view.found:
            raise HTTPException(
                status_code=422,
                detail="no shapes have been found in this view yet, so none can be "
                "measured: give the picture's width, or Picture › Find shapes first",
            )
        if body.known_index >= len(view.shapes):
            raise HTTPException(
                status_code=422,
                detail=f"this view has {len(view.shapes)} shape(s); there is no shape "
                f"{body.known_index}",
            )
    if view.taken is not None:
        return _size_by_lens(site_name, site, view, body)
    if body.mm_across is not None:
        scale, mm_across = {"mm_across": body.mm_across}, body.mm_across
    else:
        seen = Picture(
            name=view.picture,
            pixel_width=view.pixel_width,
            pixel_height=view.pixel_height,
            shapes=view.shapes,
        )
        mm_across = ScaleReference(
            known_index=body.known_index, known_width_mm=body.mm
        ).millimetres_per_unit(seen)
        if mm_across is None:
            raise HTTPException(
                status_code=422, detail=f"shape {body.known_index} has no size to measure by"
            )
        scale = {"known_index": body.known_index, "mm": body.mm}
    try:
        view = viewing.store().set_scale(site_name, view_id, scale, mm_across)
    except viewing.ViewNotFound as missing:
        raise HTTPException(status_code=404, detail=str(missing).strip('"')) from None
    rebuilt = viewing.rescale_made(site_name, site, view)
    return {
        **view_answer(view, site, viewing.store().made_at(site_name)),
        "rebuilt": rebuilt,
        "taught": None,
        "site": _site_answer(site_name, site) if rebuilt else None,
    }


def _size_by_lens(site_name: str, site: Assembly, view: View, body: ScaleBody):
    """A camera's picture sized: by the field of view that gives the width, the
    camera taught by its first, and its other pictures no person sized following."""
    if not view.placed:
        raise HTTPException(status_code=409, detail=viewing.AIM_DOWN)
    if viewing.frame_origin(view, site) is None:
        raise HTTPException(
            status_code=409, detail=f"{view.host} is no longer in the site, so nothing is sized"
        )
    if body.mm_across is not None:
        scale = {"mm_across": body.mm_across}
        asked = {"mm_across": body.mm_across}
    else:
        scale = {"known_index": body.known_index, "mm": body.mm}
        asked = {"known_index": body.known_index, "mm": body.mm}
    try:
        fov = viewing.fov_for(view, **asked)
        sized, rebuilt, taught = viewing.size_by_lens(site_name, site, view, scale, fov)
    except viewing.CannotSize as refused:
        raise HTTPException(status_code=422, detail=str(refused)) from None
    except viewing.ViewNotFound as missing:
        raise HTTPException(status_code=404, detail=str(missing).strip('"')) from None
    return {
        **view_answer(sized, site, viewing.store().made_at(site_name)),
        "rebuilt": rebuilt,
        "taught": taught,
        "site": _site_answer(site_name, site) if rebuilt else None,
    }


@router.delete("/sites/{site_name}/views/{view_id}")
def unpin_view(site_name: str, view_id: str):
    """Unpin a view. Its picture stays on disk and its made pieces stay in the site."""
    try:
        view = viewing.store().unpin(site_name, view_id)
    except viewing.ViewNotFound as missing:
        raise HTTPException(status_code=404, detail=str(missing).strip('"')) from None
    return {"unpinned": view.id, "picture": view.picture}


@router.get("/sites/{site_name}/attached")
def attached(site_name: str):
    """A site's camera parts (in the order they were added), views (oldest first) and
    made pieces, in one request."""
    site = _site(site_name)
    store = viewing.store()
    made = store.made_at(site_name)
    views = store.views_at(site_name)
    pinned = {vw.id for vw in views}
    return {
        "site": site_name,
        "cameras": [cameras.answer(camera, site) for camera in cameras.records(site_name)],
        "views": [view_answer(vw, site, made) for vw in views],
        "made": {
            piece: made_answer(rec, rec.view in pinned) for piece, rec in sorted(made.items())
        },
    }


@router.get("/placed")
def placed():
    """Everything a page placed or pinned, every site's: cameras, boards and views,
    each a row.

    A row whose host or site is gone says so (``host_found``/``node_found``/
    ``site_known``), so it can still be taken back from the list that shows it: a
    camera whose site is gone (an arrangement built from a picture, forgotten) is
    removed by ``DELETE /sites/{s}/cameras/{name}`` all the same."""
    from ..api import _find_node_by_path, _site_store
    from ..firmware import devices as firmware_devices

    names = set(_site_store.names())

    def site_or_none(name: str) -> Optional[Assembly]:
        try:
            return _site_store.get(name) if name in names else None
        except KeyError:
            return None

    boards = []
    for binding in sorted(firmware_devices.get_state().bindings(), key=lambda b: (b.site, b.path)):
        site = site_or_none(binding.site)
        boards.append(
            {
                **binding.model_dump(mode="json"),
                "site_known": site is not None,
                "node_found": site is not None
                and _find_node_by_path(site, binding.path) is not None,
            }
        )
    camera_rows = []
    for camera in cameras.records():
        site = site_or_none(camera.site)
        camera_rows.append(
            {
                "site": camera.site,
                "name": camera.name,
                "device": camera.device.model_dump() if camera.device is not None else None,
                "site_known": site is not None,
                "node_found": site is not None
                and any(c.name == camera.name for c in site.children),
            }
        )
    return {
        "cameras": camera_rows,
        "boards": boards,
        "views": [view_row(vw, site_or_none(vw.site)) for vw in viewing.store().views_at()],
    }


# --- what changes a site ------------------------------------------------------------------


class WordBody(BaseModel):
    word: str = Field(..., min_length=1, max_length=64)

    @field_validator("word")
    @classmethod
    def _a_word(cls, word: str) -> str:
        from ..vocabulary import starter_words

        words = starter_words()
        if word not in words:
            raise ValueError(f"no word named {word!r}; have {words.names()}")
        return word


@router.put("/sites/{site_name}/views/{view_id}/shapes/{index}")
async def word_for_shape(site_name: str, view_id: str, index: int, body: WordBody):
    """A person's word for one shape; a made shape's piece is rebuilt in place."""
    view = _view_or_404(site_name, view_id)
    if not 0 <= index < len(view.shapes):
        raise HTTPException(status_code=404, detail=f"view {view_id!r} has no shape {index}")
    site = _site(site_name)
    view = viewing.store().set_word(site_name, view_id, index, body.word)
    rebuilt = view.made.get(index)
    if rebuilt is not None:
        try:
            viewing.rebuild(site_name, site, rebuilt, word=body.word)
        except viewing.NotMade:
            rebuilt = None
    return {
        "view": _view_if_pinned(site_name, view_id),
        "rebuilt": rebuilt,
        "site": _site_answer(site_name, site),
    }


class MakeBody(BaseModel):
    shape: Optional[int] = Field(None, ge=0)
    all: bool = False

    @model_validator(mode="after")
    def _one_or_all(self) -> "MakeBody":
        if (self.shape is None) != self.all:
            raise ValueError("name one shape, or ask for all of them")
        return self


@router.post("/sites/{site_name}/views/{view_id}/make")
async def make_pieces(site_name: str, view_id: str, body: MakeBody):
    """Pieces from a view's shapes: one, or every one not already made. ``beyond``
    counts the shapes left because they lie past a camera picture's horizon."""
    site = _site(site_name)
    try:
        making = viewing.make(site_name, site, view_id, body.shape)
    except viewing.ViewNotFound as missing:
        raise HTTPException(status_code=404, detail=str(missing).strip('"')) from None
    except viewing.CannotMake as refused:
        raise HTTPException(status_code=409, detail=str(refused)) from None
    return {
        "made": making.made,
        "skipped": making.skipped,
        "beyond": making.beyond,
        "view": _view_if_pinned(site_name, view_id),
        "site": _site_answer(site_name, site),
    }


def _view_if_pinned(site_name: str, view_id: str) -> Optional[Dict[str, object]]:
    """The view as it is now, or None when it was unpinned meanwhile (its picture forgotten)."""
    try:
        return _answer(site_name, viewing.store().get(site_name, view_id))
    except viewing.ViewNotFound:
        return None


class Parameters(BaseModel):
    width: float = Field(..., gt=0, allow_inf_nan=False)
    depth: float = Field(..., gt=0, allow_inf_nan=False)
    height: float = Field(..., gt=0, allow_inf_nan=False)


class RebuildBody(BaseModel):
    """What to rebuild a made piece with: the editor's ``params`` (any of the
    piece's fields; the rest stay as they are), or the ring's ``word``, or all
    three sides as ``parameters``."""

    word: Optional[str] = Field(None, min_length=1, max_length=64)
    parameters: Optional[Parameters] = None
    params: Optional[Dict[str, Any]] = None

    @model_validator(mode="after")
    def _something(self) -> "RebuildBody":
        if self.word is None and self.parameters is None and self.params is None:
            raise ValueError(
                "give params (word, width, depth, height), a word, or parameters "
                "(width, depth, height in mm)"
            )
        if self.word is not None:
            WordBody(word=self.word)
        return self


def _made_or_404(site_name: str, piece: str) -> Made:
    try:
        return viewing.store().made_piece(site_name, piece)
    except viewing.NotMade as missing:
        raise HTTPException(status_code=404, detail=str(missing).strip('"')) from None


def _made_part(site_name: str, piece: str) -> MadePart:
    return MadePart.of(_made_or_404(site_name, piece))


@router.get("/sites/{site_name}/made/{piece}/params", response_model=ParamsSpec)
def made_params(site_name: str, piece: str):
    """What a made piece accepts, in the form ``GET /parts/{name}/params`` answers:
    its word and sides, defaulting to what it is now, and its provenance as the
    candidates a person can turn to."""
    return params_spec(_made_part(site_name, piece))


class StagedParams(BaseModel):
    params: Dict[str, Any] = Field(default_factory=dict)


@router.post("/sites/{site_name}/made/{piece}/validate", response_model=Validation)
def validate_made(site_name: str, piece: str, body: Optional[StagedParams] = None):
    """Check a staged set against the piece's own model, as ``POST
    /parts/{name}/validate`` does: an unknown field or a side of nothing is
    refused here, where it costs nothing, and a valid set says the box it
    would occupy."""
    return validate_staged(_made_part(site_name, piece), body.params if body else {})


@router.get("/sites/{site_name}/made/{piece}/scad", response_class=PlainTextResponse)
def made_scad(site_name: str, piece: str):
    """The SCAD a made piece's geometry renders to: a few lines, the word's body
    shifted onto its middle and turned as the shape was seen."""
    part = _made_part(site_name, piece)
    text = geometry_scad(part, {})
    assert text is not None  # a made piece is always built from its geometry
    return PlainTextResponse(text)


def _normalised(part: MadePart, body: RebuildBody) -> Dict[str, object]:
    """``params`` as ``word`` and ``parameters``: only what differs from the piece
    is a change, so applying a staged set that touched one side states one side's
    worth, and leaves the word the table's. Refused (422) for an unknown field or
    a side of nothing."""
    if body.params is None:
        return {
            "word": body.word,
            "parameters": body.parameters.model_dump() if body.parameters else None,
        }
    try:
        given = part.validate_overrides(body.params)
    except ValueError as refused:
        raise HTTPException(status_code=422, detail=str(refused)) from None
    record = part.record
    word = given.get("word")
    if word == record.word:
        word = None
    sides = {side: given[side] for side in SIDES if side in given}
    parameters = None
    if any(sides[side] != record.parameters[side] for side in sides):
        parameters = {**record.parameters, **sides}
    if body.word is not None:
        word = body.word
    if body.parameters is not None:
        parameters = body.parameters.model_dump()
    return {"word": word, "parameters": parameters}


@router.put("/sites/{site_name}/made/{piece}")
async def rebuild_made(site_name: str, piece: str, body: RebuildBody):
    """Rebuild a made piece in place: by the editor's staged set, by another word,
    or by a person's sides. Its name and position stay; the answer carries its
    provenance as it is now (``found`` beside ``parameters``), the box it
    occupies (``bounds``) and the site."""
    site = _site(site_name)
    change = _normalised(_made_part(site_name, piece), body)
    if change["word"] is None and change["parameters"] is None:
        record = _made_or_404(site_name, piece)  # nothing differs: nothing to rebuild
    else:
        try:
            record = viewing.rebuild(
                site_name, site, piece, word=change["word"], parameters=change["parameters"]
            )
        except viewing.NotMade as missing:
            raise HTTPException(status_code=404, detail=str(missing).strip('"')) from None
    pinned = {vw.id for vw in viewing.store().views_at(site_name)}
    return {
        "piece": piece,
        "provenance": made_answer(record, record.view in pinned),
        "bounds": MadePart.of(record).get_bounds().model_dump(),
        "site": _site_answer(site_name, site),
    }


@router.delete("/sites/{site_name}/made/{piece}")
async def drop_made(site_name: str, piece: str):
    """Drop: the piece leaves the site, and its shape reads as found again."""
    site = _site(site_name)
    _made_or_404(site_name, piece)
    record = viewing.drop(site_name, site, piece)
    return {
        "dropped": piece,
        "view": record.view,
        "shape": record.shape_index,
        "site": _site_answer(site_name, site),
    }


__all__ = ["check_host", "finders_for", "pin_picture", "router", "shape_answer", "view_answer"]
