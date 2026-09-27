"""Looks from the browser: a picture pinned at a place, its shapes, the pieces made.

The store, the anchors and the making are ``apothecary/vision/looks.py``; these
routes are its doors. ``host: ""`` is the site's floor in every one.

Plain ``def``, on the threadpool, for the routes that change no site -- a find
reads a file and may be slow, and the store's lock is never held across it:

- ``POST /sites/{s}/looks`` ``{host, picture, camera?, finder?, mm_across?}``
  finds the shapes in a picture under the picture root and pins the look.
- ``PUT /sites/{s}/looks/{id}/scale`` ``{mm_across} | {known_index, mm}`` sizes
  a look, and stores the width it comes to on the look's camera, so the next
  look from that camera is sized alike.
- ``DELETE /sites/{s}/looks/{id}`` unpins a look; its picture and pieces stay.
- ``GET /sites/{s}/attached``: a site's cameras, looks and made pieces, in one.
- ``GET /placed``: every site's cameras, boards and looks, each a row to take back.

``async def``, one at a time on the event loop, as api.py's rule for routes that
change a site says; each answers with the site as ``GET /sites/{s}`` does:

- ``PUT /sites/{s}/looks/{id}/shapes/{i}`` ``{word}``: a person's word for a
  shape; on a made shape it rebuilds the piece in place.
- ``POST /sites/{s}/looks/{id}/make`` ``{shape} | {all: true}``: pieces from
  shapes, skipping the shapes already made.
- ``PUT /sites/{s}/made/{piece}`` ``{word?, parameters?}`` and ``DELETE
  /sites/{s}/made/{piece}`` (Drop): keyed by the piece, so they work after its
  look is unpinned or its picture forgotten.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator, model_validator

from ..hierarchy import Assembly
from ..vision import looks as looking
from ..vision.looks import Look, Made
from ..vision.models import FoundShape, ScaleReference

router = APIRouter(tags=["looks"])


# --- answers -------------------------------------------------------------------------


def _point(p) -> List[float]:
    return [p.x, p.y]


def shape_view(shape: FoundShape) -> Dict[str, object]:
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


def look_view(look: Look, site: Optional[Assembly], made: Dict[str, Made]) -> Dict[str, object]:
    """A look as the page reads it: its mat where it lies now, and each shape's state."""
    centre = looking.mat_centre(look, site) if site is not None else None
    width = look.mm_across
    shapes = []
    for index, shape in enumerate(look.shapes):
        word, reason, stated = looking.word_for_shape(look, index)
        status, piece = looking.status_of(look, index, made)
        shapes.append(
            {
                "index": index,
                **shape_view(shape),
                "word": word,
                "reason": reason,
                "word_stated": stated,
                "status": status,
                "piece": piece,
            }
        )
    return {
        **look_row(look, site),
        "scale": look.scale,
        "mm_across": width,
        "pixel_width": look.pixel_width,
        "pixel_height": look.pixel_height,
        "left_out": look.left_out,
        "made": {str(i): piece for i, piece in sorted(look.made.items())},
        "anchor": _xyz(look.anchor) if look.anchor is not None else None,
        "mat": (
            {
                "centre": _xyz(centre),
                "width": width,
                "depth": width * look.tallness if width is not None else None,
            }
            if centre is not None
            else None
        ),
        "shapes": shapes,
    }


def look_row(look: Look, site: Optional[Assembly]) -> Dict[str, object]:
    """A look as one row of what is pinned: enough to name it and take it back."""
    host_found = site is not None and (
        look.at_floor or any(c.name == look.host for c in site.children)
    )
    return {
        "id": look.id,
        "site": look.site,
        "host": look.host,
        "host_found": host_found,
        "picture": look.picture,
        "camera": look.camera,
        "taken_at": look.taken_at,
        "finder": look.finder,
    }


def made_view(record: Made, pinned: bool) -> Dict[str, object]:
    view = record.model_dump(mode="json")
    view["shape"] = shape_view(record.shape)
    view["look_pinned"] = pinned
    return view


def _site_answer(site_name: str, site: Assembly) -> Dict[str, object]:
    from ..api import _site_payload, _site_store

    return _site_payload(site, _site_store.validator(site_name)(site))


def _site(site_name: str) -> Assembly:
    from ..api import _get_site_or_404

    return _get_site_or_404(site_name)


def _look_or_404(site_name: str, look_id: str) -> Look:
    try:
        return looking.store().get(site_name, look_id)
    except looking.LookNotFound as missing:
        raise HTTPException(status_code=404, detail=str(missing).strip('"')) from None


def _view(site_name: str, look: Look) -> Dict[str, object]:
    return look_view(look, _site(site_name), looking.store().made_at(site_name))


# --- pinning ---------------------------------------------------------------------------


def check_host(site_name: str, host: str) -> Assembly:
    """The site, once ``host`` is known to be able to hold a look or a camera; or refused."""
    site = _site(site_name)
    try:
        looking.host_node(site, host, looking.made_names(site_name))
    except looking.HostNotFound as missing:
        raise HTTPException(status_code=404, detail=str(missing).strip('"')) from None
    except looking.NotAHost as refused:
        raise HTTPException(status_code=422, detail=str(refused)) from None
    return site


def pin_picture(
    site_name: str,
    host: str,
    picture: str,
    *,
    camera: Optional[str] = None,
    finder: str = "plain",
    mm_across: Optional[float] = None,
) -> Look:
    """Find the shapes in a picture under the root and pin the look at ``host``.

    The finder runs outside every lock, through the finder cache. A look with
    no width given takes its camera's last one."""
    from ..api import _picture_root, _picture_within_root
    from ..vision import get as get_finder
    from ..vision.cache import cache
    from .pictures import _load_cameras

    site = check_host(site_name, host)
    root = _picture_root()
    asked = Path(picture)
    where = _picture_within_root(asked if asked.is_absolute() else root / asked)
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
    if mm_across is None and camera:
        mm_across = _load_cameras().get(camera, {}).get("mm_across")
    shapes, left_out = looking.keep_the_most_sure(seen.shapes)
    at = datetime.now(timezone.utc)
    look = Look(
        id=looking.new_look_id(at),
        site=site_name,
        host=host,
        picture=where.relative_to(root).as_posix(),
        camera=camera,
        taken_at=at.isoformat(),
        finder=seen.finder,
        scale={"mm_across": mm_across} if mm_across else None,
        mm_across=mm_across or None,
        pixel_width=seen.pixel_width,
        pixel_height=seen.pixel_height,
        shapes=shapes,
        left_out=left_out,
        anchor=(
            looking.floor_anchor(site, looking.made_names(site_name))
            if host == looking.FLOOR
            else None
        ),
    )
    return looking.store().pin(look)


CAMERA_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$"


class PinLook(BaseModel):
    host: str = Field("", max_length=400)
    picture: str = Field(..., min_length=1, max_length=400)
    camera: Optional[str] = Field(None, pattern=CAMERA_PATTERN)
    finder: str = Field("plain", max_length=64)
    mm_across: Optional[float] = Field(None, gt=0, allow_inf_nan=False)


@router.post("/sites/{site_name}/looks", status_code=201)
def pin_look(site_name: str, body: PinLook):
    """Find the shapes in a picture and pin the look at a host, or the floor (``""``)."""
    look = pin_picture(
        site_name,
        body.host,
        body.picture,
        camera=body.camera,
        finder=body.finder,
        mm_across=body.mm_across,
    )
    return _view(site_name, look)


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


@router.put("/sites/{site_name}/looks/{look_id}/scale")
def size_look(site_name: str, look_id: str, body: ScaleBody):
    """Size a look; the width it comes to is stored on its camera as the next look's."""
    from ..vision.models import Picture
    from .pictures import set_camera_width

    look = _look_or_404(site_name, look_id)
    if body.mm_across is not None:
        scale, mm_across = {"mm_across": body.mm_across}, body.mm_across
    else:
        if body.known_index >= len(look.shapes):
            raise HTTPException(
                status_code=422,
                detail=f"this look has {len(look.shapes)} shape(s); there is no shape "
                f"{body.known_index}",
            )
        seen = Picture(
            name=look.picture,
            pixel_width=look.pixel_width,
            pixel_height=look.pixel_height,
            shapes=look.shapes,
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
        look = looking.store().set_scale(site_name, look_id, scale, mm_across)
    except looking.LookNotFound as missing:
        raise HTTPException(status_code=404, detail=str(missing).strip('"')) from None
    if look.camera:
        set_camera_width(look.camera, mm_across)
    return _view(site_name, look)


@router.delete("/sites/{site_name}/looks/{look_id}")
def unpin_look(site_name: str, look_id: str):
    """Unpin a look. Its picture stays on disk and its made pieces stay in the site."""
    try:
        look = looking.store().unpin(site_name, look_id)
    except looking.LookNotFound as missing:
        raise HTTPException(status_code=404, detail=str(missing).strip('"')) from None
    return {"unpinned": look.id, "picture": look.picture}


@router.get("/sites/{site_name}/attached")
def attached(site_name: str):
    """A site's cameras, looks (oldest first) and made pieces, in one request."""
    from .pictures import camera_rows

    site = _site(site_name)
    store = looking.store()
    made = store.made_at(site_name)
    looks = store.looks_at(site_name)
    pinned = {lk.id for lk in looks}
    return {
        "site": site_name,
        "cameras": camera_rows(site_name),
        "looks": [look_view(lk, site, made) for lk in looks],
        "made": {piece: made_view(rec, rec.look in pinned) for piece, rec in sorted(made.items())},
    }


@router.get("/placed")
def placed():
    """Everything a page pinned, every site's: cameras, boards and looks, each a row.

    A row whose host is gone says so (``host_found``/``node_found``), so it can
    still be taken back from the list that shows it."""
    from ..api import _find_node_by_path, _site_store
    from ..firmware import devices as firmware_devices
    from .pictures import camera_rows

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
    return {
        "cameras": camera_rows(None),
        "boards": boards,
        "looks": [look_row(lk, site_or_none(lk.site)) for lk in looking.store().looks_at()],
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


@router.put("/sites/{site_name}/looks/{look_id}/shapes/{index}")
async def word_for_shape(site_name: str, look_id: str, index: int, body: WordBody):
    """A person's word for one shape; a made shape's piece is rebuilt in place."""
    look = _look_or_404(site_name, look_id)
    if not 0 <= index < len(look.shapes):
        raise HTTPException(status_code=404, detail=f"look {look_id!r} has no shape {index}")
    site = _site(site_name)
    look = looking.store().set_word(site_name, look_id, index, body.word)
    rebuilt = look.made.get(index)
    if rebuilt is not None:
        try:
            looking.rebuild(site_name, site, rebuilt, word=body.word)
        except looking.NotMade:
            rebuilt = None
    return {
        "look": _view_if_pinned(site_name, look_id),
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


@router.post("/sites/{site_name}/looks/{look_id}/make")
async def make_pieces(site_name: str, look_id: str, body: MakeBody):
    """Pieces from a look's shapes: one, or every one not already made."""
    site = _site(site_name)
    try:
        made, skipped = looking.make(site_name, site, look_id, body.shape)
    except looking.LookNotFound as missing:
        raise HTTPException(status_code=404, detail=str(missing).strip('"')) from None
    except looking.CannotMake as refused:
        raise HTTPException(status_code=409, detail=str(refused)) from None
    return {
        "made": made,
        "skipped": skipped,
        "look": _view_if_pinned(site_name, look_id),
        "site": _site_answer(site_name, site),
    }


def _view_if_pinned(site_name: str, look_id: str) -> Optional[Dict[str, object]]:
    """The look as it is now, or None when it was unpinned meanwhile (its picture forgotten)."""
    try:
        return _view(site_name, looking.store().get(site_name, look_id))
    except looking.LookNotFound:
        return None


class Parameters(BaseModel):
    width: float = Field(..., gt=0, allow_inf_nan=False)
    depth: float = Field(..., gt=0, allow_inf_nan=False)
    height: float = Field(..., gt=0, allow_inf_nan=False)


class RebuildBody(BaseModel):
    word: Optional[str] = Field(None, min_length=1, max_length=64)
    parameters: Optional[Parameters] = None

    @model_validator(mode="after")
    def _something(self) -> "RebuildBody":
        if self.word is None and self.parameters is None:
            raise ValueError("give a word, or parameters (width, depth, height in mm)")
        if self.word is not None:
            WordBody(word=self.word)
        return self


def _made_or_404(site_name: str, piece: str) -> Made:
    try:
        return looking.store().made_piece(site_name, piece)
    except looking.NotMade as missing:
        raise HTTPException(status_code=404, detail=str(missing).strip('"')) from None


@router.put("/sites/{site_name}/made/{piece}")
async def rebuild_made(site_name: str, piece: str, body: RebuildBody):
    """Rebuild a made piece in place, by another word or a person's parameters."""
    site = _site(site_name)
    _made_or_404(site_name, piece)
    try:
        record = looking.rebuild(
            site_name,
            site,
            piece,
            word=body.word,
            parameters=body.parameters.model_dump() if body.parameters else None,
        )
    except looking.NotMade as missing:
        raise HTTPException(status_code=404, detail=str(missing).strip('"')) from None
    pinned = {lk.id for lk in looking.store().looks_at(site_name)}
    return {
        "piece": piece,
        "provenance": made_view(record, record.look in pinned),
        "site": _site_answer(site_name, site),
    }


@router.delete("/sites/{site_name}/made/{piece}")
async def drop_made(site_name: str, piece: str):
    """Drop: the piece leaves the site, and its shape reads as found again."""
    site = _site(site_name)
    _made_or_404(site_name, piece)
    record = looking.drop(site_name, site, piece)
    return {
        "dropped": piece,
        "look": record.look,
        "shape": record.shape_index,
        "site": _site_answer(site_name, site),
    }


__all__ = ["check_host", "look_view", "pin_picture", "router", "shape_view"]
