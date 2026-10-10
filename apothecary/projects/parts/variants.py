"""Every render of a part the page asks for, kept by what made it.

A variant is a part rendered with a set of parameters. It is filed under a
key computed from everything that decides the mesh: the SCAD and every file
it includes, uses or imports (or, for a part built by Python geometry, the
SCAD that geometry writes), the parameters and the ``-D`` definitions they
become, the part's display rotation, the OpenSCAD that renders it (its
version line) and the backend it uses. The same request is the same key, so
it is rendered once; a different request is a different file, so two tabs
applying different values never write the same file. A changed include is a
different key, never a stale hit.

Layout, under ``$APOTHECARY_CACHE_DIR/part_stl`` (by default the checkout's
ignored ``.cache``)::

    <part>/<key>.stl    the mesh, display rotation applied
    <part>/<key>.json   what made it: params, OpenSCAD, backend, when, how
                        long, the bounding box OpenSCAD measured, and what
                        OpenSCAD warned about

The part's own STL (``get_stl_output_path``) is the default variant. A
request for the defaults leaves it current: rendered into the cache, then
placed there, unless the params sidecar says it holds something else (a
variant ``apothecary parts generate-stl -p`` made), which the page never
overwrites. A request the part's STL already answers (it is fresh for those
parameters) costs nothing either. Any other variant lives in the cache only.

One render per key at a time, and the cache keeps the ``PART_VARIANTS_KEEP``
most recently served of each part: the node-STL cache in ``api.py`` is the
precedent. ``PageRenders`` is how a newer request from the same page stops
the OpenSCAD run of an older one.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
import threading
import time
import uuid
import weakref
from dataclasses import dataclass, field
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple

from pydantic import BaseModel, Field

from apothecary.meshes import MeshError, read_mesh
from apothecary.meshes import bounds as mesh_bounds
from apothecary.models import BoundingBox3D, Vector3D

from .base import BasePart
from .openscad_messages import OpenSCADMessage, parse_openscad_messages, place_messages
from .skeleton import ROOT
from .stl_renderer import (
    SUPERSEDED,
    Cancellation,
    OpenSCADRenderer,
    RenderResult,
    _is_fresh,
    _recordable,
    geometry_scad,
    has_manifold,
    openscad_version,
    params_sidecar_path,
    part_renderer,
    read_params_sidecar,
    render_part,
    scad_definitions,
    scad_dependencies,
)

# Variants kept per part; the least recently served go first.
PART_VARIANTS_KEEP = 64

# Bumped when what goes into a key changes, so an old entry is never a hit.
KEY_SCHEME = "apothecary-part-variant-1"

KEY_PATTERN = re.compile(r"^[0-9a-f]{24}$")


def variant_cache_dir() -> Path:
    """``$APOTHECARY_CACHE_DIR/part_stl``, by default under the checkout's ignored ``.cache``."""
    return Path(os.environ.get("APOTHECARY_CACHE_DIR") or ROOT / ".cache") / "part_stl"


def _folder_name(part: BasePart) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "_", part.name) or "part"


def show_path(path: Path) -> Optional[str]:
    """A path as the API shows it: relative to the checkout, else None."""
    try:
        return Path(path).resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return None


# --- the key ------------------------------------------------------------------------

_DIGESTS: Dict[Tuple[str, int, int], str] = {}
_DIGESTS_GUARD = threading.Lock()


def _file_digest(path: Path) -> str:
    """A file's sha256, remembered while its size and mtime stay the same."""
    stat = path.stat()
    memo = (str(path), stat.st_size, stat.st_mtime_ns)
    with _DIGESTS_GUARD:
        known = _DIGESTS.get(memo)
    if known is None:
        known = hashlib.sha256(path.read_bytes()).hexdigest()
        with _DIGESTS_GUARD:
            _DIGESTS[memo] = known
    return known


# --- what it measures ---------------------------------------------------------------

# Where a variant's measured bounds came from: OpenSCAD's own summary of the
# render, or this module reading the STL (2021.01 writes no summary, and the
# part's own STL may have been built by the command line or at startup).
FROM_SUMMARY = "summary"
FROM_STL = "stl"


def _unturned(point: Tuple[float, float, float], rotation: List[float]):
    """``point`` turned back by OpenSCAD's ``rotate(rotation)``: that turns about
    x, then y, then z, so this undoes z, then y, then x."""
    x, y, z = point
    rx, ry, rz = (math.radians(-angle) for angle in rotation)
    x, y = x * math.cos(rz) - y * math.sin(rz), x * math.sin(rz) + y * math.cos(rz)
    x, z = x * math.cos(ry) + z * math.sin(ry), -x * math.sin(ry) + z * math.cos(ry)
    y, z = y * math.cos(rx) - z * math.sin(rx), y * math.sin(rx) + z * math.cos(rx)
    return (x, y, z)


@lru_cache(maxsize=256)
def _measured(path: str, size: int, mtime_ns: int, rotation: Tuple[float, ...]):
    triangles = read_mesh(Path(path))
    if any(rotation):
        triangles = [tuple(_unturned(c, list(rotation)) for c in t) for t in triangles]
    lo, hi = mesh_bounds(triangles)
    clean = [[round(v, 6) + 0.0 for v in side] for side in (lo, hi)]
    return {
        "min": clean[0],
        "max": clean[1],
        "size": [round(h - low, 6) + 0.0 for low, h in zip(*clean, strict=True)],
    }


def measure_stl(stl: Path, rotation: Optional[List[float]] = None) -> Optional[Dict[str, Any]]:
    """An STL's bounding box in the frame a part's bounds are declared in: the
    part's display rotation turned back, as OpenSCAD's summary of the upright
    render would say it. None when there is no STL or no mesh in it."""
    try:
        stat = Path(stl).stat()
        return _measured(
            str(stl), stat.st_size, stat.st_mtime_ns, tuple(float(a) for a in rotation or ())
        )
    except (OSError, MeshError):
        return None


def measured_box(measured: Optional[Mapping[str, List[float]]]) -> Optional[BoundingBox3D]:
    """A measurement in the shape the declared bounds come in."""
    if not measured:
        return None
    low, high = measured["min"], measured["max"]
    return BoundingBox3D(
        min_point=Vector3D(x=low[0], y=low[1], z=low[2]),
        max_point=Vector3D(x=high[0], y=high[1], z=high[2]),
    )


def _executable(renderer: OpenSCADRenderer) -> Optional[Path]:
    """The renderer's OpenSCAD; None for one without (a stand-in in a test)."""
    return getattr(renderer, "openscad_path", None)


def backend_of(renderer: OpenSCADRenderer) -> str:
    return "manifold" if has_manifold(_executable(renderer)) else "cgal"


def openscad_of(renderer: OpenSCADRenderer) -> Optional[str]:
    exe = _executable(renderer)
    return openscad_version(exe) if exe is not None and Path(exe).exists() else None


def variant_key(part: BasePart, params: Mapping[str, Any], renderer: OpenSCADRenderer) -> str:
    """The key a render of ``part`` with already-validated ``params`` is filed under."""
    digest = hashlib.sha256()

    def add(label: str, value: str) -> None:
        digest.update(f"{label}\0{value}\0".encode("utf-8"))

    add("scheme", KEY_SCHEME)
    add("part", part.name)
    text = geometry_scad(part, dict(params))
    if text is None:
        scad = part.source_file
        add("scad", _file_digest(scad))
        definitions = part.scad_overrides(params)
        reads = scad_dependencies(scad)
    else:
        add("scad", hashlib.sha256(text.encode("utf-8")).hexdigest())
        definitions = {}
        reads = scad_dependencies(part.source_file, text=text)
    for label, path in sorted(reads.items()):
        add("reads", f"{label}={_file_digest(path) if path is not None else 'missing'}")
    try:
        add("definitions", "\0".join(scad_definitions(definitions)))
    except TypeError as exc:  # a value -D cannot carry: the request's fault
        raise ValueError(str(exc)) from None
    add("params", json.dumps(dict(params), sort_keys=True, default=_recordable))
    add("rotation", json.dumps(part.display_rotation.to_list()))
    add("openscad", openscad_of(renderer) or "none")
    add("backend", backend_of(renderer))
    return digest.hexdigest()[:24]


# --- the cache ----------------------------------------------------------------------


class _KeyedLocks:
    """One lock per key, gone once nobody holds it."""

    def __init__(self) -> None:
        self._locks: "weakref.WeakValueDictionary[str, threading.Lock]" = (
            weakref.WeakValueDictionary()
        )
        self._guard = threading.Lock()

    def __call__(self, key: str) -> threading.Lock:
        with self._guard:
            lock = self._locks.get(key)
            if lock is None:
                lock = self._locks[key] = threading.Lock()
            return lock


_LOCKS = _KeyedLocks()


def variant_paths(part: BasePart, key: str, cache: Optional[Path] = None) -> Tuple[Path, Path]:
    """(STL, record) of a part's variant ``key``."""
    folder = (cache or variant_cache_dir()) / _folder_name(part)
    return folder / f"{key}.stl", folder / f"{key}.json"


def read_variant(part: BasePart, key: str, cache: Optional[Path] = None) -> Optional[dict]:
    """A variant's record, its STL marked served; None when there is none."""
    if not KEY_PATTERN.match(key):
        return None
    stl, record = variant_paths(part, key, cache)
    try:
        mtime_ns = stl.stat().st_mtime_ns
        os.utime(stl, ns=(time.time_ns(), mtime_ns))
        return json.loads(record.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _write_atomically(path: Path, data: bytes) -> None:
    partial = path.with_name(f".{path.name}.{uuid.uuid4().hex[:12]}.tmp")
    try:
        partial.write_bytes(data)
        os.replace(partial, path)
    finally:
        partial.unlink(missing_ok=True)


def trim_variants(folder: Path, keep: int = PART_VARIANTS_KEEP) -> None:
    """Remove all but the ``keep`` most recently served variants in ``folder``.
    A render still being written is a dot-file and is left alone."""
    served = []
    for stl in folder.glob("*.stl"):
        if stl.name.startswith("."):
            continue
        try:
            served.append((stl.stat().st_atime_ns, stl))
        except FileNotFoundError:
            continue
    served.sort(reverse=True)
    for _, stl in served[keep:]:
        stl.unlink(missing_ok=True)
        stl.with_suffix(".json").unlink(missing_ok=True)


# --- making one ---------------------------------------------------------------------


@dataclass
class Made:
    """What answers a request for a variant, and how it was come by."""

    stl_path: Optional[Path] = None
    # The cache key; None when the part's own STL answered.
    key: Optional[str] = None
    # Whether OpenSCAD ran for this request.
    rendered: bool = False
    # The OpenSCAD run when there was one, failed or not.
    result: Optional[RenderResult] = None
    # Why nothing was made: "refused" (cannot be built here), "cancelled"
    # (a newer request superseded it), or "failed" (OpenSCAD said why).
    failure: Optional[str] = None
    error_message: Optional[str] = None
    params: Dict[str, Any] = field(default_factory=dict)
    openscad: Optional[str] = None
    backend: Optional[str] = None
    render_time_seconds: float = 0.0
    measured: Optional[Dict[str, List[float]]] = None
    # FROM_SUMMARY or FROM_STL: where ``measured`` came from.
    measured_from: Optional[str] = None
    # Whether the answer is the part's own STL: fresh, and rendered with
    # these parameters (the defaults, or what the command line put there).
    saved: bool = False
    messages: List[OpenSCADMessage] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return self.failure is None

    def measure(self, measured: Optional[Dict[str, Any]], rotation: List[float]) -> None:
        """``measured`` as OpenSCAD's summary said it, else read off the STL."""
        if measured:
            self.measured, self.measured_from = measured, FROM_SUMMARY
            return
        self.measured = measure_stl(self.stl_path, rotation) if self.stl_path else None
        self.measured_from = FROM_STL if self.measured else None


def _messages_of(part: BasePart, result: RenderResult) -> List[OpenSCADMessage]:
    """What OpenSCAD said, its files named from the checkout. A part built by
    Python geometry renders a SCAD written to scratch under its source file's
    name, so a relative name there is not resolved against the part's folder."""
    if part.geometry({}) is None:
        base, own = part.source_file.parent, part.source_file
    else:
        base, own = None, None
    return place_messages(parse_openscad_messages(result.stderr), base, show_path, own=own)


def _place_as_canonical(part: BasePart, stl: Path) -> None:
    """Make the part's own STL a copy of the default variant ``stl``."""
    canonical = part.get_stl_output_path()
    canonical.parent.mkdir(parents=True, exist_ok=True)
    partial = canonical.with_name(f".{canonical.stem}.{uuid.uuid4().hex[:12]}.stl")
    try:
        shutil.copyfile(stl, partial)
        os.replace(partial, canonical)
    finally:
        partial.unlink(missing_ok=True)
    params_sidecar_path(canonical).unlink(missing_ok=True)


def make_variant(
    part: BasePart,
    params: Optional[Mapping[str, Any]] = None,
    force: bool = False,
    timeout: float = 120.0,
    renderer: Optional[OpenSCADRenderer] = None,
    cancel: Optional[Cancellation] = None,
    cache: Optional[Path] = None,
) -> Made:
    """The part rendered with ``params``, from the cache when it is there.

    ``params`` are checked against the part's model (ValueError on a bad
    one). A cached variant answers first, then the part's own STL when it is
    fresh for these parameters; otherwise OpenSCAD renders into the cache.
    ``force`` renders even so. The defaults are also left as the part's own
    STL, unless its params sidecar says it holds another variant.
    """
    params = part.validate_overrides(params)
    chosen, renderer = renderer, renderer or part_renderer(part)
    canonical = part.get_stl_output_path()
    rotation = part.display_rotation.to_list()
    holds_default = read_params_sidecar(canonical) is None
    key = variant_key(part, params, renderer)
    stl, record_path = variant_paths(part, key, cache)
    made = Made(params=params, openscad=openscad_of(renderer), backend=backend_of(renderer))

    with _LOCKS(f"{_folder_name(part)}/{key}"):
        if cancel is not None and cancel.cancelled:
            made.failure, made.error_message = "cancelled", SUPERSEDED
            return made
        record = None if force else read_variant(part, key, cache)
        if record is None and not force and _is_fresh(part, canonical, params):
            # The part's own STL answers it; it was not rendered by this cache.
            made.stl_path, made.saved = canonical, True
            made.measure(None, rotation)
            return made
        if record is None:
            # As build_stl asks: of the OpenSCAD the caller chose, else of
            # every one the part could use, so the reason names them all.
            can_build, reason = part.can_generate_stl(chosen.openscad_path if chosen else None)
            if not can_build:
                made.failure, made.error_message = "refused", reason
                return made
            stl.parent.mkdir(parents=True, exist_ok=True)
            result = render_part(part, stl, params, timeout, renderer, rotation, cancel)
            made.rendered, made.result = True, result
            made.render_time_seconds = result.render_time_seconds
            made.messages = _messages_of(part, result)
            if result.cancelled:
                made.failure, made.error_message = "cancelled", SUPERSEDED
                return made
            if not result.success:
                made.failure, made.error_message = "failed", result.error_message
                return made
            made.key, made.stl_path = key, stl
            made.measure(result.measured, rotation)
            record = {
                "part": part.name,
                "key": key,
                "params": params,
                "openscad": made.openscad,
                "backend": made.backend,
                "rendered": datetime.now().isoformat(timespec="seconds"),
                "render_time_seconds": result.render_time_seconds,
                "measured": made.measured,
                "measured_from": made.measured_from,
                "messages": [m.model_dump() for m in made.messages],
            }
            _write_atomically(
                record_path,
                (json.dumps(record, indent=2, sort_keys=True, default=_recordable) + "\n").encode(
                    "utf-8"
                ),
            )
        else:
            made.key, made.stl_path = key, stl
            made.render_time_seconds = float(record.get("render_time_seconds") or 0.0)
            made.messages = [OpenSCADMessage(**m) for m in record.get("messages", [])]
            if record.get("measured") and record.get("measured_from"):
                made.measured, made.measured_from = record["measured"], record["measured_from"]
            else:
                made.measure(None, rotation)
        if not params and holds_default:
            # The part's own STL is the default variant: kept current, and
            # left alone while it is (whichever OpenSCAD made it), unless forced.
            with _LOCKS(f"{_folder_name(part)}/canonical"):
                if force or not _is_fresh(part, canonical, {}):
                    _place_as_canonical(part, stl)
        made.saved = _is_fresh(part, canonical, params)
    trim_variants(stl.parent)
    return made


# --- whose render is whose ----------------------------------------------------------


class PageRenders:
    """The render each page has in flight for each part.

    A page names itself (an id it makes up once per load); a newer request
    from it for the same part cancels the older one's OpenSCAD run, unless it
    asks for the same thing, which it then shares. A request with no page
    supersedes nothing and is superseded by nothing.
    """

    def __init__(self) -> None:
        self._guard = threading.Lock()
        self._running: Dict[Tuple[str, str], Tuple[str, Cancellation]] = {}

    def begin(self, part: str, page: Optional[str], wants: str) -> Optional[Cancellation]:
        """The request's Cancellation; None for a request with no page."""
        if not page:
            return None
        with self._guard:
            held = self._running.get((part, page))
            if held is not None:
                older_wants, older = held
                if older_wants == wants and not older.cancelled:
                    return older
                older.cancel()
            cancellation = Cancellation()
            self._running[(part, page)] = (wants, cancellation)
            return cancellation

    def end(self, part: str, page: Optional[str], cancellation: Optional[Cancellation]) -> None:
        if not page or cancellation is None:
            return
        with self._guard:
            held = self._running.get((part, page))
            if held is not None and held[1] is cancellation:
                del self._running[(part, page)]

    def running(self) -> int:
        with self._guard:
            return len(self._running)


def wants(params: Mapping[str, Any], force: bool) -> str:
    """What a request asks for, for telling one request from another."""
    return json.dumps({"params": dict(params), "force": force}, sort_keys=True, default=_recordable)


# --- what is on disk ----------------------------------------------------------------


class PartState(BaseModel):
    """What the part's own STL is, as its params sidecar records it."""

    part: str
    exists: bool = Field(description="Whether the part's STL is on disk")
    stl_url: Optional[str] = None
    params: Dict[str, Any] = Field(
        default_factory=dict,
        description="The overrides it was rendered with, as the sidecar records them; "
        "empty for the defaults",
    )
    default: bool = Field(description="Rendered with the defaults (no sidecar)")
    generated: Optional[str] = Field(None, description="When the sidecar was written")
    fresh: bool = Field(description="Newer than everything it is built from")
    measured: Optional[BoundingBox3D] = Field(
        None, description="Its bounding box, read off the STL in the declared frame"
    )
    measured_from: Optional[str] = Field(None, description='"stl" when measured')


def part_state(part: BasePart, url_name: Optional[str] = None) -> PartState:
    """What the part's own STL is: whether it is there, the parameters its
    sidecar records (none: the defaults), when, whether it is newer than
    everything it is built from, and its bounding box. What a page that draws
    it starts from."""
    canonical = part.get_stl_output_path()
    record = read_params_sidecar(canonical) or {}
    params = dict(record.get("params") or {})
    exists = canonical.exists()
    measured = measure_stl(canonical, part.display_rotation.to_list()) if exists else None
    return PartState(
        part=part.name,
        exists=exists,
        stl_url=f"/parts/{url_name or part.name}/stl" if exists else None,
        params=params,
        default=not params,
        generated=record.get("generated"),
        fresh=exists and _is_fresh(part, canonical, params),
        measured=measured_box(measured),
        measured_from=FROM_STL if measured else None,
    )


class VariantRecord(BaseModel):
    """One cached variant: what made it, and where it is served."""

    part: str
    variant: str
    stl_url: str
    params: Dict[str, Any] = Field(default_factory=dict)
    openscad: Optional[str] = None
    backend: Optional[str] = None
    rendered: Optional[str] = Field(None, description="When OpenSCAD rendered it")
    render_time_seconds: float = 0.0
    measured: Optional[BoundingBox3D] = None
    measured_from: Optional[str] = Field(None, description='"summary" or "stl"')
    messages: List[OpenSCADMessage] = Field(default_factory=list)
    saved: bool = Field(description="It is what the part's own STL holds")


def variant_record(
    part: BasePart, key: str, url_name: Optional[str] = None
) -> Optional[VariantRecord]:
    """A cached variant's record, for a page that has its key and not its
    parameters (a tab reloaded, a link followed); None once it is let go."""
    record = read_variant(part, key)
    if record is None:
        return None
    measured, source = record.get("measured"), record.get("measured_from")
    if not (measured and source):
        stl, _ = variant_paths(part, key)
        measured = measure_stl(stl, part.display_rotation.to_list())
        source = FROM_STL if measured else None
    params = dict(record.get("params") or {})
    return VariantRecord(
        part=part.name,
        variant=key,
        stl_url=f"/parts/{url_name or part.name}/variants/{key}/stl",
        params=params,
        openscad=record.get("openscad"),
        backend=record.get("backend"),
        rendered=record.get("rendered"),
        render_time_seconds=float(record.get("render_time_seconds") or 0.0),
        measured=measured_box(measured),
        measured_from=source,
        messages=[OpenSCADMessage(**m) for m in record.get("messages", [])],
        saved=_is_fresh(part, part.get_stl_output_path(), params),
    )


__all__ = [
    "FROM_STL",
    "FROM_SUMMARY",
    "KEY_PATTERN",
    "Made",
    "PART_VARIANTS_KEEP",
    "PageRenders",
    "PartState",
    "VariantRecord",
    "make_variant",
    "measure_stl",
    "measured_box",
    "part_state",
    "read_variant",
    "variant_record",
    "trim_variants",
    "variant_cache_dir",
    "variant_key",
    "variant_paths",
    "wants",
]
