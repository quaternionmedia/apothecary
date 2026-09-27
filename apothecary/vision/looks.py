"""Looks: a picture pinned at one place in a site, and the pieces made from its shapes.

A *look* is a picture pinned at a *host* -- a root structure of the site that
has a footprint and is not itself a made piece -- or at the site's floor
(``host == ""``). It keeps what a finder saw there: the shapes, with no size
until a person gives the picture's width or one shape's long side. It is data
attached to a host, not a node in the tree: ``GET /sites/{name}`` does not
change, so SCAD, STL, validation and jobs never see one.

A shape becomes a *piece*: a root structure of the same site, standing where
the shape was seen, built by ``compose.piece_from_shape``. What is known about
a piece -- its picture, host, camera, shape index, a copy of the shape, its
extent as made, its word and why -- is kept here, keyed by (site, piece), and
never in the site store, so a plain-``def`` forget can mark it and the piece
can find its outline after the look is gone.

Where a look's picture is laid (its *mat*): centred on the host's current top,
so it follows the host when the host is moved, or, at the floor, from an
anchor fixed when the look is pinned, just past the site's roots in +x. A shape
at fractions ``(cx, cy)`` of the picture stands ``((cx - 0.5) * W,
(0.5 - cy) * H)`` from the mat's centre, where ``W`` is the picture's width in
millimetres and ``H`` is ``W`` times the picture's height over its width.

Held in memory behind one lock, as the shelf is, and lost on restart; the lock
is held for dictionary reads and writes only, never while a finder looks or a
file is read. Whether looks may be kept in the state folder across a restart
waits on what the draft record *Personal data stays on the device* counts as
this machine.

PROTOTYPE — not ratified.
"""

from __future__ import annotations

import threading
from datetime import datetime
from typing import Dict, List, Optional, Set, Tuple

from pydantic import BaseModel, Field

from ..hierarchy import Assembly
from ..models.vectors import Vector3D
from .compose import piece_from_shape
from .models import FoundShape

# The most shapes a look keeps, the most confident first: the outline budget per mat.
LOOK_SHAPES_MOST = 32

# The most made pieces a site holds: what the canvas ring's one grouped Made
# cell can list (two levels of eight, as `menu._grouped` allows).
MADE_MOST = 64

# How far past the site's roots, in +x, a floor mat's near edge is laid.
FLOOR_MARGIN_MM = 200.0

FLOOR = ""

# The reason recorded when a person, not the table, chose a shape's word.
STATED_REASON = "a person said so"


class NotAHost(ValueError):
    """A look or camera was asked to be pinned somewhere that cannot hold one."""


class HostNotFound(LookupError):
    """The host named is not in the site."""


class LookNotFound(LookupError):
    """No look by that id in that site."""


class NotMade(LookupError):
    """No made piece by that name in that site."""


class CannotMake(ValueError):
    """A make was refused: unsized, already made, no room, or its host gone."""


class Look(BaseModel):
    """One picture pinned at one host, and what a finder saw in it."""

    id: str
    site: str
    host: str
    picture: str  # relative to the picture root
    camera: Optional[str] = None
    taken_at: str
    finder: str
    scale: Optional[Dict[str, float]] = None  # {mm_across} | {known_index, mm}
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
    """How one made piece came to be: its provenance, kept beside the site."""

    site: str
    piece: str
    host: str
    look: str
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
    parameters: Dict[str, float]  # width, depth, height in mm
    parameters_stated: bool = False


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


def host_node(site: Assembly, host: str, made: Set[str]) -> Optional[Assembly]:
    """The root structure ``host`` names, or None for the floor; refused with its reason.

    Raises ``HostNotFound`` for a name not in the site, and ``NotAHost`` for
    one below the root, one with no footprint, or a made piece."""
    if host == FLOOR:
        return None
    root_name, _, rest = host.partition(".")
    root = next((c for c in site.children if c.name == root_name), None)
    if root is None:
        raise HostNotFound(f"Node '{host}' not found in site '{site.name}'")
    if rest:
        raise NotAHost(
            f"{host} is inside {root_name}: pictures and cameras are pinned at a root "
            f"structure, so pin at {root_name}"
        )
    if root_name in made:
        raise NotAHost(
            f"{root_name} is a made piece: pins there would go stale when it is dropped "
            "or the site is reset"
        )
    if root.world_bounds() is None:
        raise NotAHost(
            f"{root_name} has no footprint, so there is no top to lay a picture on; "
            "pin at a structure that has one, or at the floor"
        )
    return root


def floor_anchor(site: Assembly, made: Set[str]) -> Vector3D:
    """The floor mat's near (-x) edge: z 0, y at the centre of the site's roots, x past
    their +x edge by a margin; the origin when there are none. Made pieces excluded."""
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


def mat_centre(look: Look, site: Assembly) -> Optional[Vector3D]:
    """Where the look's mat is centred now; None when its host is gone.

    At the floor an unsized mat has no width, and its centre is the anchor."""
    if look.at_floor:
        anchor = look.anchor or Vector3D()
        half = (look.mm_across or 0.0) / 2
        return Vector3D(x=anchor.x + half, y=anchor.y, z=anchor.z)
    node = next((c for c in site.children if c.name == look.host), None)
    if node is None or node.world_bounds() is None:
        return None
    return top_centre(node)


def shape_offset(look: Look, shape: FoundShape) -> Tuple[float, float]:
    """A shape's centre from its mat's centre, in millimetres (the look is sized)."""
    assert look.mm_across is not None
    width = look.mm_across
    centre = shape.centre
    return ((centre.x - 0.5) * width, (0.5 - centre.y) * look.tallness * width)


def _in_frame(look: Look, shape: FoundShape) -> Tuple[float, float]:
    """A shape's centre where extents are kept: from the host's top-centre, or in the
    site's frame at the floor."""
    dx, dy = shape_offset(look, shape)
    if look.at_floor:
        anchor = look.anchor or Vector3D()
        return (anchor.x + look.mm_across / 2 + dx, anchor.y + dy)
    return (dx, dy)


def _extent(look: Look, shape: FoundShape) -> Extent:
    width = look.mm_across
    return Extent(
        centre=_in_frame(look, shape),
        size=(shape.width * width, shape.height * look.tallness * width),
    )


def status_of(look: Look, index: int, made: Dict[str, Made]) -> Tuple[str, Optional[str]]:
    """``("made", piece)`` when this look made it, ``("already_made", piece)`` when its
    centre lies inside the extent recorded for a piece made at the same host from any
    look, else ``("found", None)``. An unsized look is only ever found or made."""
    if index in look.made:
        return "made", look.made[index]
    if look.mm_across is None:
        return "found", None
    point = _in_frame(look, look.shapes[index])
    for record in made.values():
        if record.host != look.host:
            continue
        if record.look == look.id and record.shape_index == index:
            continue
        if record.extent.holds(point):
            return "already_made", record.piece
    return "found", None


def word_for_shape(look: Look, index: int) -> Tuple[str, str, bool]:
    """(word, reason, stated) for one shape: a person's word, or the table's."""
    from ..vocabulary import word_for

    if index in look.words:
        return look.words[index], STATED_REASON, True
    choice = word_for(look.shapes[index])
    return choice.word, choice.reason, False


def keep_the_most_sure(shapes: List[FoundShape]) -> Tuple[List[FoundShape], int]:
    """At most ``LOOK_SHAPES_MOST`` shapes, the most confident, in the finder's order;
    and how many were left out."""
    if len(shapes) <= LOOK_SHAPES_MOST:
        return list(shapes), 0
    ranked = sorted(range(len(shapes)), key=lambda i: (-shapes[i].confidence, i))
    kept = sorted(ranked[:LOOK_SHAPES_MOST])
    return [shapes[i] for i in kept], len(shapes) - LOOK_SHAPES_MOST


def new_look_id(at: datetime) -> str:
    return f"look_{at:%Y%m%dT%H%M%S%f}Z"


# --- the store -----------------------------------------------------------------------


class Looks:
    """Every look pinned and every piece made in this process, behind one lock."""

    def __init__(self) -> None:
        self._looks: Dict[str, Look] = {}
        self._made: Dict[Tuple[str, str], Made] = {}
        self._forgotten: Set[str] = set()
        self._lock = threading.Lock()

    # looks

    def pin(self, look: Look) -> Look:
        with self._lock:
            base, n = look.id, 2
            while look.id in self._looks:
                look = look.model_copy(update={"id": f"{base}-{n}"})
                n += 1
            self._looks[look.id] = look.model_copy(deep=True)
            self._forgotten.discard(look.picture)
        return look

    def get(self, site: str, look_id: str) -> Look:
        with self._lock:
            found = self._looks.get(look_id)
            if found is None or found.site != site:
                raise LookNotFound(f"no look {look_id!r} in site {site!r}")
            return found.model_copy(deep=True)

    def looks_at(self, site: Optional[str] = None) -> List[Look]:
        """A site's looks (every site's with none named), oldest first."""
        with self._lock:
            chosen = [
                lk.model_copy(deep=True)
                for lk in self._looks.values()
                if site is None or lk.site == site
            ]
        return sorted(chosen, key=lambda lk: (lk.taken_at, lk.id))

    def unpin(self, site: str, look_id: str) -> Look:
        with self._lock:
            found = self._looks.get(look_id)
            if found is None or found.site != site:
                raise LookNotFound(f"no look {look_id!r} in site {site!r}")
            return self._looks.pop(look_id)

    def set_scale(self, site: str, look_id: str, scale: Dict[str, float], mm_across: float) -> Look:
        with self._lock:
            found = self._looks.get(look_id)
            if found is None or found.site != site:
                raise LookNotFound(f"no look {look_id!r} in site {site!r}")
            found.scale = dict(scale)
            found.mm_across = mm_across
            return found.model_copy(deep=True)

    def set_word(self, site: str, look_id: str, index: int, word: str) -> Look:
        with self._lock:
            found = self._looks.get(look_id)
            if found is None or found.site != site:
                raise LookNotFound(f"no look {look_id!r} in site {site!r}")
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
        """Keep a made piece's provenance and mark its shape made in its look.

        False, and nothing kept, when the look already made that shape. A look
        unpinned meanwhile keeps nothing; the record is kept all the same, and
        marked forgotten when its picture was forgotten meanwhile."""
        with self._lock:
            look = self._looks.get(record.look)
            if look is not None and record.shape_index in look.made:
                return False
            if record.picture in self._forgotten and look is None:
                record = record.model_copy(update={"picture_forgotten": True})
            if look is not None:
                look.made[record.shape_index] = record.piece
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
            look = self._looks.get(record.look)
            if look is not None and look.made.get(record.shape_index) == piece:
                del look.made[record.shape_index]
            return record

    def forget_made(self, site: str) -> List[str]:
        """Every made piece of a site is gone (a reset): its records and its looks' marks."""
        with self._lock:
            gone = [piece for (s, piece) in self._made if s == site]
            for piece in gone:
                del self._made[(site, piece)]
            for look in self._looks.values():
                if look.site == site:
                    look.made.clear()
            return gone

    # pictures

    def forget_picture(self, picture: str) -> List[str]:
        """A kept picture was forgotten: its looks are unpinned, every site's, and the
        pieces made from it stay, marked forgotten. Returns the looks unpinned."""
        with self._lock:
            unpinned = [lid for lid, lk in self._looks.items() if lk.picture == picture]
            for lid in unpinned:
                del self._looks[lid]
            for record in self._made.values():
                if record.picture == picture:
                    record.picture_forgotten = True
            self._forgotten.add(picture)
            return unpinned

    def kept_again(self, picture: str) -> None:
        """A picture was kept at a path once forgotten: it is a new picture."""
        with self._lock:
            self._forgotten.discard(picture)


_store: Optional[Looks] = None
_made_store = threading.Lock()


def store() -> Looks:
    """The one look store this process uses."""
    global _store
    with _made_store:
        if _store is None:
            _store = Looks()
        return _store


def forget_made(site: str) -> List[str]:
    """What ``SiteStore.reset`` calls: a site rebuilt from its code has no made pieces."""
    return store().forget_made(site)


def made_names(site: str) -> Set[str]:
    return store().made_names(site)


# --- making, rebuilding, dropping: the site changes the look routes carry out ----------
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


def make(
    site_name: str, site: Assembly, look_id: str, shape: Optional[int] = None
) -> Tuple[List[str], int]:
    """Make one shape (``shape``) or every shape not yet made (``None``) into pieces.

    Returns the pieces made and how many shapes were skipped as already made.
    Refused (``CannotMake``) for an unsized look, a single shape already made,
    a host that is gone, or more made pieces than the site's Made cell holds."""
    looks = store()
    look = looks.get(site_name, look_id)
    if shape is not None and not 0 <= shape < len(look.shapes):
        raise LookNotFound(f"look {look_id!r} has no shape {shape}")
    if look.mm_across is None:
        raise CannotMake(
            "this look has no width yet: give the picture's width, or one shape's long "
            "side, and then make it"
        )
    centre = mat_centre(look, site)
    if centre is None:
        raise CannotMake(f"{look.host} is no longer in the site, so there is nowhere to stand it")
    made = looks.made_at(site_name)
    chosen = [shape] if shape is not None else list(range(len(look.shapes)))
    to_make, skipped = [], 0
    for index in chosen:
        status, piece = status_of(look, index, made)
        if status == "found":
            to_make.append(index)
            continue
        if shape is not None:
            raise CannotMake(
                f"shape {index} is already made: its centre lies in {piece} as it was made"
            )
        skipped += 1
    if len(made) + len(to_make) > MADE_MOST:
        raise CannotMake(
            f"{len(made)} piece(s) are made in this site and {len(to_make)} more would pass "
            f"{MADE_MOST}, the most the Made cell holds; drop some first"
        )
    names: List[str] = []
    for index in to_make:
        found = look.shapes[index]
        word, reason, stated = word_for_shape(look, index)
        name = _unique_name(site, word)
        piece, _about = piece_from_shape(
            found,
            name=name,
            word=word,
            reason=reason,
            per_unit=look.mm_across,
            tallness=look.tallness,
            finder=look.finder,
        )
        piece.position = piece.position + centre
        fp = piece.footprint
        record = Made(
            site=site_name,
            piece=name,
            host=look.host,
            look=look.id,
            picture=look.picture,
            camera=look.camera,
            shape_index=index,
            shape=found,
            extent=_extent(look, found),
            word=word,
            word_stated=stated,
            reason=reason,
            finder=look.finder,
            confidence=found.confidence,
            origin=found.origin,
            mm_across=look.mm_across,
            pixel_width=look.pixel_width,
            pixel_height=look.pixel_height,
            parameters={
                "width": fp.max_point.x - fp.min_point.x,
                "depth": fp.max_point.y - fp.min_point.y,
                "height": fp.max_point.z - fp.min_point.z,
            },
        )
        if looks.record_made(record):
            site.children.append(piece)
            names.append(name)
        else:
            skipped += 1
    return names, skipped


def rebuild(
    site_name: str,
    site: Assembly,
    piece: str,
    *,
    word: Optional[str] = None,
    parameters: Optional[Dict[str, float]] = None,
) -> Made:
    """Rebuild a made piece in place from its shape: another word, or a person's sides
    and thickness. Its name and position stay."""
    from ..vocabulary import WordShape, starter_words

    looks = store()
    record = looks.made_piece(site_name, piece)
    index = next((i for i, c in enumerate(site.children) if c.name == piece), None)
    if index is None:
        raise NotMade(f"{piece!r} is no longer in site {site_name!r}")
    if word is not None and word not in starter_words():
        raise ValueError(f"no word named {word!r}; have {starter_words().names()}")
    new_word = word or record.word
    stated = record.word_stated or word is not None
    reason = STATED_REASON if word is not None else record.reason
    size = WordShape(**parameters) if parameters else None
    if size is None and record.parameters_stated:
        size = WordShape(**record.parameters)
    rebuilt, _about = piece_from_shape(
        record.shape,
        name=piece,
        word=new_word,
        reason=reason,
        per_unit=record.mm_across,
        tallness=record.pixel_height / record.pixel_width,
        finder=record.finder,
        size=size,
    )
    rebuilt.position = site.children[index].position
    site.children[index] = rebuilt
    fp = rebuilt.footprint
    record = record.model_copy(
        update={
            "word": new_word,
            "word_stated": stated,
            "reason": reason,
            "parameters": {
                "width": fp.max_point.x - fp.min_point.x,
                "depth": fp.max_point.y - fp.min_point.y,
                "height": fp.max_point.z - fp.min_point.z,
            },
            "parameters_stated": record.parameters_stated or parameters is not None,
        }
    )
    looks.update_made(record)
    return record


def drop(site_name: str, site: Assembly, piece: str) -> Made:
    """The piece goes from the site; its shape reads as found again."""
    record = store().drop(site_name, piece)
    site.children[:] = [c for c in site.children if c.name != piece]
    return record


__all__ = [
    "FLOOR",
    "FLOOR_MARGIN_MM",
    "LOOK_SHAPES_MOST",
    "MADE_MOST",
    "CannotMake",
    "Extent",
    "HostNotFound",
    "Look",
    "LookNotFound",
    "Looks",
    "Made",
    "NotAHost",
    "NotMade",
    "drop",
    "floor_anchor",
    "forget_made",
    "host_node",
    "keep_the_most_sure",
    "make",
    "made_names",
    "mat_centre",
    "rebuild",
    "shape_offset",
    "status_of",
    "store",
    "top_centre",
    "word_for_shape",
]
