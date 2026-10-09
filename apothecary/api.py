"""
Apothecary API - FastAPI endpoints for OpenSCAD generation toolkit.

This module provides REST API endpoints for:
- Scene rendering to OpenSCAD code
- Parts browsing and downloading
- 3D viewer for part preview

Note: STL files are generated on-demand and not stored in git.
On startup, missing STLs are automatically generated if OpenSCAD is available.
"""

import asyncio
import hashlib
import json
import mimetypes
import os
import re
import threading
import time
import weakref
from contextlib import asynccontextmanager, suppress
from importlib import import_module
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import quote

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ValidationError

from .core import OpenSCADObject
from .datum_core_site import create_datum_core_site, validate_datum_core
from .docs_site import router as docs_router
from .example_hierarchy import (
    PRINTER_STATUSES,
    Job,
    JobStore,
    create_example_site,
    job_fits_printer,
    validate_garage_layout,
)
from .example_parts_library import create_parts_library_site, validate_parts_library
from .firmware import devices as firmware_devices
from .firmware import gcode as firmware_gcode
from .firmware.api import _device_view as firmware_device_view
from .firmware.api import router as firmware_router
from .firmware.bindings import bindings_for_site, device_for_identity, same_device
from .firmware.models import DeviceAttachRequest
from .firmware.toolchains import ToolchainError
from .hierarchy import Assembly
from .models.bounds import BoundingBox3D
from .models.vectors import Vector3D
from .primitives import Cube, Cylinder, Sphere, absolute_imports
from .projects.parts.base import BasePart
from .projects.parts.params import (
    NoParameters,
    ParamsSpec,
    Validation,
    params_spec,
    validate_staged,
)
from .projects.parts.skeleton import ROOT
from .projects.parts.stl_renderer import build_stl
from .projects.parts.stl_renderer import get_renderer as get_stl_renderer
from .projects.registry import ProjectInfo, _sanitize_module_name, scan_projects
from .routes.looks import router as looks_router
from .routes.pictures import router as pictures_router
from .scene import Scene
from .site_store import SiteStore, UnknownSiteError
from .stays_local import LocalOnly
from .templates import TemplateRenderer
from .transforms import Translate
from .viewer import render_fractal_viewer_page


def _registered_part(item: ProjectInfo) -> BasePart:
    """A registry entry's part: its wrapper's DEFAULT, or a bare part for a SCAD with none."""
    if item.wrapper:
        return import_module(item.wrapper).DEFAULT
    return BasePart(name=item.name, source_file=item.path)


async def _generate_missing_stls():
    """Build the STL of every registered part that has none.

    STLs are build products a fresh checkout does not have. Each goes through
    build_stl on a worker thread, one part at a time; a part that cannot be
    built on this machine is skipped with its reason.
    """
    if os.environ.get("APOTHECARY_SKIP_STL_GENERATION", "").lower() in ("1", "true", "yes"):
        print("STL generation skipped (APOTHECARY_SKIP_STL_GENERATION=1)")
        return

    if not get_stl_renderer().is_available:
        print("OpenSCAD not found - STL generation skipped")
        print("Install OpenSCAD to enable automatic STL generation")
        return

    parts = [_registered_part(p) for p in scan_projects(ROOT) if p.kind == "part"]
    missing = [part for part in parts if not part.get_stl_output_path().exists()]
    if not missing:
        return

    print(f"Generating {len(missing)} missing STL file(s)...")
    for part in missing:
        print(f"  Generating {part.name}...", end=" ", flush=True)
        result = await asyncio.to_thread(build_stl, part, timeout=120)
        if result.skipped == "refused":
            print(f"skipped: {result.error_message}")
        elif result.success:
            print(f"OK ({result.render_time_seconds:.1f}s)")
        else:
            print(f"FAILED: {result.error_message}")


async def _generate_missing_stls_in_background():
    """Wrapper run as a background task -- see lifespan() for why."""
    try:
        await _generate_missing_stls()
    except Exception as exc:  # pragma: no cover - defensive; log, don't crash the server
        print(f"Background STL generation failed: {exc}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start building missing part STLs in the background; cancel it on shutdown.

    Not awaited: a render can take tens of seconds per part, and /health has to
    answer meanwhile for whatever polls it with a short timeout (`apothecary
    docs`, tests/e2e's --start-server fixture). The viewer draws a placeholder
    for a part with no STL yet and asks /parts/{name}/stl/generate for it.
    """
    # Startup
    stl_task = asyncio.create_task(_generate_missing_stls_in_background())
    app.state.stl_generation_task = stl_task  # keep a strong reference (asyncio GC gotcha)
    yield
    # Shutdown: don't leave a render subprocess dangling if we're still generating
    if not stl_task.done():
        stl_task.cancel()
        with suppress(asyncio.CancelledError):
            await stl_task


app = FastAPI(
    title="Apothecary API",
    version="0.1.0",
    description="Lean OpenSCAD generation toolkit exposed via FastAPI endpoints",
    lifespan=lifespan,
    # /docs is the project's documentation (docs_site.py). FastAPI's own Swagger
    # and ReDoc pages are off: each loads its script from a public CDN, which a
    # page here may not do (apothecary/stays_local.py). The API is described by
    # /openapi.json, which is served from here.
    docs_url=None,
    redoc_url=None,
)

# The viewer's 3D library, kept here rather than fetched from a public website
# while somebody is using it. See apothecary/static/vendor/three/README.md: with
# the network switched off, fetching it meant the viewer never loaded at all.
# A CDN copy is also exactly what an ad blocker or a corporate proxy drops --
# and when it goes, the page's script never executes, so the canvas, the
# contents list and the code panel come up empty together while the static
# markup still reads "Layout valid". Frontend dependencies are vendored per
# the house-stack record for the same reason.
STATIC_ROOT = Path(__file__).resolve().parent / "static"
# Personal data stays on this machine by the shape of the program: the app
# answers a client on loopback only and fences every page it sends
# (apothecary/stays_local.py). Outermost, so static files are under it too.
app.add_middleware(LocalOnly)
app.mount("/static", StaticFiles(directory=STATIC_ROOT), name="static")
app.include_router(docs_router)
# Mounted before the photo routes below, so /photos/pictures and /photos/gather
# are matched before /photos/{name} can take "pictures" for a name. The router
# reaches back into this module only inside its handlers.
app.include_router(pictures_router)
# Looks: a picture pinned at a place in a site, and the pieces made from its shapes.
app.include_router(looks_router)
THREE_DIR = STATIC_ROOT / "vendor" / "three"
THREE_IS_VENDORED = (THREE_DIR / "three.module.js").is_file()

renderer = TemplateRenderer()


# =============================================================================
# Parts Registry Helpers
# =============================================================================


def _part_template() -> str:
    template_path = ROOT / "templates" / "part.include.scad.j2"
    if template_path.exists():
        return template_path.read_text(encoding="utf-8")
    return "// {{ part.name }}\ninclude <{{ source_posix }}>"


def _load_part_wrapper(name: str):
    # Only a registered part: a name from a URL is never turned into an import
    # path (GET /parts/stl_renderer used to import that module and answer 500).
    # Spellings a link may carry: the registry's name in any case of - and _
    # (datum-core), or a nested part's package path (rc.snowplow). Each resolves
    # to a registered wrapper, never to a module constructed from the URL.
    wanted = _sanitize_module_name(name)
    full = next(
        (
            p.wrapper
            for p in scan_projects(ROOT)
            if p.kind == "part"
            and p.wrapper
            and (
                _sanitize_module_name(p.name) == wanted
                or p.wrapper == f"apothecary.projects.parts.{name}"
            )
        ),
        None,
    )
    if full is None:
        raise HTTPException(status_code=404, detail=f"Part '{name}' not found")
    module = import_module(full)
    if not hasattr(module, "DEFAULT"):
        raise HTTPException(status_code=500, detail=f"Wrapper '{full}' missing DEFAULT part")
    part = module.DEFAULT
    if not part.exists:
        raise HTTPException(status_code=404, detail=f"SCAD source for part '{name}' not found")
    return part


def _available_part_names() -> List[str]:
    return sorted({p.name for p in scan_projects(ROOT) if p.kind == "part" and p.wrapper})


def _repo_relative_path(path: Path) -> str:
    """Return a repository-relative POSIX path when possible.

    API responses should avoid exposing absolute local filesystem paths.
    """
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return path.name


def _normalize_params(part, params_query: str | None) -> tuple[Dict[str, object], str]:
    data: Dict[str, object] = {}
    if params_query:
        try:
            parsed = json.loads(params_query)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=400, detail=f"Invalid params JSON: {exc}") from exc
        if not isinstance(parsed, dict):
            raise HTTPException(status_code=400, detail="Params JSON must describe an object")
        data = parsed  # type: ignore[assignment]
    if part.params_model:
        try:
            params_obj = part.params_model(**data)
        except ValidationError as exc:
            raise HTTPException(status_code=400, detail=f"Invalid params: {exc}") from exc
        return params_obj.model_dump(), params_obj.model_dump_json()
    if data:
        raise HTTPException(
            status_code=400, detail=f"Part '{part.name}' does not accept parameters"
        )
    return {}, "{}"


def _render_part_include(part, params_json: str) -> str:
    template_str = _part_template()
    ctx = {
        "part": part,
        "params_json": params_json,
        "source_posix": _repo_relative_path(part.source_file),
    }
    return renderer.render_template(template_str, ctx)


def _part_metadata(part) -> Dict[str, object]:
    metadata = {
        "name": part.name,
        "description": part.description,
        "category": part.category,
        "tags": part.tags,
        "readme": (
            _repo_relative_path(part.readme_path)
            if part.readme_path and part.readme_path.exists()
            else None
        ),
        "source_file": _repo_relative_path(part.source_file),
        "has_params": bool(part.params_model),
    }

    stl_can_generate, stl_note = part.can_generate_stl()
    metadata["files"] = {
        "scad": {"exists": part.source_file.exists(), "url": f"/parts/{part.name}/scad"},
        "stl": {
            "exists": part.stl_file is not None,
            "url": f"/parts/{part.name}/stl" if part.stl_file else None,
            "generate_url": f"/parts/{part.name}/stl/generate",
            "can_generate": stl_can_generate,
            "note": stl_note or None,
        },
    }

    # Add geometry metadata if available
    metadata["geometry"] = part.to_geometry_dict()

    return metadata


def _part_payload(part, params_query: str | None) -> Dict[str, object]:
    metadata = _part_metadata(part)
    params_dict, params_json = _normalize_params(part, params_query)
    metadata.update(
        {
            "params": params_dict,
            "include": _render_part_include(part, params_json),
            "download_url": f"/parts/{part.name}/scad",
        }
    )
    return metadata


app.include_router(firmware_router)


@app.get("/")
async def root():
    """Root endpoint - redirects to the viewer."""
    return RedirectResponse("/viewer", status_code=307)


@app.get("/health")
async def health():
    """Health check endpoint"""
    return {"status": "healthy", "version": "0.1.0"}


@app.post("/render")
def render_scene(scene: Scene):
    """Render a scene to OpenSCAD code. Each object says what it is (``type``);
    one that does not, or says something unknown, is a 422 from validation."""
    return {
        "success": True,
        "scene_name": scene.name,
        "code": scene.render(),
        "object_count": len(scene.objects),
    }


@app.get("/parts")
def list_parts():
    names = _available_part_names()
    return [_part_metadata(_load_part_wrapper(name)) for name in names]


@app.get("/parts/{name}")
def get_part(name: str, params: str | None = Query(None, alias="params")):
    part = _load_part_wrapper(name)
    return _part_payload(part, params)


@app.get("/parts/{name}/scad", response_class=PlainTextResponse)
def get_part_scad(name: str):
    part = _load_part_wrapper(name)
    try:
        return PlainTextResponse(part.source_file.read_text(encoding="utf-8"))
    except OSError as exc:  # pragma: no cover - IO failure is rare
        raise HTTPException(status_code=500, detail=f"Failed to read SCAD: {exc}") from exc


@app.get("/parts/{name}/stl")
def get_part_stl(name: str):
    """
    Download the STL file for a part.

    Returns 404 if the STL hasn't been generated yet.
    Use POST /parts/{name}/stl/generate to create it.
    """
    part = _load_part_wrapper(name)

    stl_path = part.stl_file
    if stl_path is None or not stl_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"STL not found for '{name}'. Use POST /parts/{name}/stl/generate to create it.",
        )

    try:
        stl_data = stl_path.read_bytes()
        return Response(
            content=stl_data,
            media_type="application/sla",
            headers={
                "Content-Disposition": f'attachment; filename="{name}.stl"',
                "X-Part-Name": name,
            },
        )
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Failed to read STL: {exc}") from exc


class StlGenerateRequest(BaseModel):
    """Body for a parameterised STL generation."""

    params: Dict[str, Any] = Field(
        default_factory=dict,
        description="Parameter overrides, validated against the part's own model.",
    )


@app.post("/parts/{name}/stl/generate")
def generate_part_stl(
    name: str,
    force: bool = Query(False),
    body: Optional[StlGenerateRequest] = None,
):
    """Build a part's STL through build_stl, as `apothecary parts generate-stl` does.

    ``params`` are checked against what the part declares (422 on an unknown
    name or a bad value). An STL newer than its sources and rendered from the
    same parameters is kept unless ``force`` (``regenerated: false``). No
    OpenSCAD, or a part that cannot be built on this machine, is a 503.
    """
    part = _load_part_wrapper(name)
    try:
        overrides = part.validate_overrides(body.params if body else None)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    if not get_stl_renderer().is_available:
        raise HTTPException(
            status_code=503, detail="OpenSCAD not installed. Cannot generate STL files."
        )

    result = build_stl(part, overrides, force=force)
    if result.skipped == "refused":
        raise HTTPException(
            status_code=503, detail=f"Cannot generate STL for '{name}': {result.error_message}"
        )
    if not result.success:
        raise HTTPException(
            status_code=500, detail=f"STL generation failed: {result.error_message}"
        )

    regenerated = result.skipped != "fresh"
    return {
        "success": True,
        "message": (
            f"STL generated in {result.render_time_seconds:.1f}s"
            if regenerated
            else "STL is up to date (force=true rebuilds it)"
        ),
        "stl_url": f"/parts/{name}/stl",
        "regenerated": regenerated,
        "render_time_seconds": result.render_time_seconds,
        "params": jsonable_encoder(overrides),
        "bounds": jsonable_encoder(part.get_bounds(overrides or None)),
    }


@app.get("/parts/{name}/params", response_model=ParamsSpec)
def get_part_params(name: str):
    """What a part accepts, in a form a control surface can build itself from.

    ``params_spec`` (apothecary/projects/parts/params.py) reads it off the
    part's own Pydantic model, so the editor cannot drift from what the
    renderer will actually accept. ``contested`` carries the parameters whose
    value this project's sources disagree about, with the provenance of each
    candidate -- an ambiguity a reader can turn is worth more than one they
    have to argue about. A made piece answers the same shape from
    ``GET /sites/{s}/made/{piece}/params``.
    """
    part = _load_part_wrapper(name)
    try:
        return params_spec(part)
    except NoParameters:
        raise HTTPException(
            status_code=404, detail=f"Part '{name}' declares no parameters"
        ) from None


def _parse_build_volume(raw: Optional[str]):
    """`X,Y,Z` as a tuple, or None. Refuses anything else rather than guessing."""
    if not raw:
        return None
    try:
        parsed = tuple(float(v) for v in raw.split(","))
    except ValueError:
        raise HTTPException(status_code=422, detail="build_volume wants X,Y,Z") from None
    if len(parsed) != 3:
        raise HTTPException(status_code=422, detail="build_volume wants three numbers")
    return parsed


@app.get("/parts/{name}/checklist")
def get_part_checklist(name: str, build_volume: Optional[str] = Query(None)):
    """Whether this part is ready to print and check against a real one.

    The same assessment `apothecary parts checklist` prints, so the viewer and
    the command line cannot disagree about whether something is buildable.
    A question that could not be asked is reported as `unknown`, never as a
    pass.
    """
    from .projects.parts.readiness import assess

    part = _load_part_wrapper(name)

    report = assess(part, build_volume=_parse_build_volume(build_volume))
    return {
        "part": report.part,
        "ready": report.ready,
        "blocked": len(report.blocked),
        "unknown": len(report.unknown),
        "checks": [
            {"name": c.name, "state": c.state, "detail": c.detail, "fix": c.fix}
            for c in report.checks
        ],
    }


@app.post("/parts/{name}/validate", response_model=Validation)
def validate_part_params(name: str, body: Optional[StlGenerateRequest] = None):
    """Check a staged parameter set without rendering anything.

    The step between moving a slider and paying for a render (`apothecary
    parts generate-stl` measures one): ``validate_staged`` puts the values
    through the part's own model, and the envelope they would produce comes
    back. A set that cannot be rendered is rejected here, where it costs
    nothing.
    """
    part = _load_part_wrapper(name)
    return validate_staged(part, body.params if body else {})


# =============================================================================
# Site/Structure/Substructure/Feature hierarchy (prototype, unratified)
#
# Backed by a process-lifetime SiteStore (see site_store.py): edits persist
# across requests, unlike /render's stateless Scene handling. Known
# limitation: in-memory only, lost on restart, not shared across worker
# processes -- fine for a single-process dev server.
#
# Routes that change a site or a job stay `async def`: they run one at a time
# on the event loop, which is all that serializes the stores' plain dicts
# until they have a lock. Routes that only read, and do filesystem, parse or
# render work, are plain `def` and run on the threadpool.
# =============================================================================

_site_store = SiteStore(
    {
        "garage": (create_example_site, validate_garage_layout),
        "parts_library": (create_parts_library_site, validate_parts_library),
        "datum_core": (create_datum_core_site, validate_datum_core),
    }
)
_job_store = JobStore()

# The site /viewer opens on. Named rather than "whichever sorts first", so that
# registering a new site cannot silently move the front door.
DEFAULT_VIEWER_SITE = "garage"


# The only types a picture is served as. Anything else is handed back as bytes
# with no claim about what it is.
PICTURE_TYPES = {"image/png", "image/jpeg", "image/gif", "image/webp", "image/bmp", "image/tiff"}


def _photo_shelf():
    from .vision.shelf import shelf

    return shelf()


def _get_site_or_404(name: str) -> Assembly:
    try:
        return _site_store.get(name)
    except UnknownSiteError:
        raise HTTPException(status_code=404, detail=f"Site '{name}' not found") from None


def _find_node_by_path(site: Assembly, path: str) -> Optional[Assembly]:
    """Resolve a dotted, site-rooted path (e.g. ``printer_1.gantry_system``)
    to the Assembly node it names, walking ``children``/``additions``/
    ``subtractions`` together -- the same three-list-as-one-tree shape
    ``_assembly_tree`` exposes to the client, so a path the viewer displays
    is always resolvable back here. Returns None if any segment doesn't
    match, rather than raising, so callers can choose their own 404 wording.
    """
    node = site
    for segment in path.split("."):
        candidates = [*node.children, *node.additions, *node.subtractions]
        found = next((c for c in candidates if c.name == segment), None)
        if found is None:
            return None
        node = found
    return node


# Node renders kept in the cache. A key includes the node's position, so every
# layout drag of a structure adds one; the least recently served go first.
NODE_STL_KEEP = 500

# One lock per render key, gone once nobody holds it.
_NODE_STL_LOCKS: "weakref.WeakValueDictionary[str, threading.Lock]" = weakref.WeakValueDictionary()
_NODE_STL_LOCKS_GUARD = threading.Lock()


def _node_stl_cache_dir() -> Path:
    """``$APOTHECARY_CACHE_DIR/node_stl``, by default under the checkout's ignored ``.cache``."""
    return Path(os.environ.get("APOTHECARY_CACHE_DIR") or ROOT / ".cache") / "node_stl"


def _node_stl_cache_paths(scad_text: str) -> tuple[Path, Path]:
    """(scratch SCAD, STL) for a node's render, both in the cache, keyed by content.

    A node has no source file of its own, so the SCAD text is its identity.
    Each imported mesh's size and mtime go into the key too: the same
    ``import()`` over a regenerated file is a different render.
    """
    digest = hashlib.sha256(scad_text.encode("utf-8"))
    for match in re.finditer(r'import\("([^"]+)"', scad_text):
        imported = Path(match.group(1))
        imported = imported if imported.is_absolute() else ROOT / imported
        try:
            stat = imported.stat()
            digest.update(f"{match.group(1)}:{stat.st_size}:{stat.st_mtime_ns}".encode())
        except OSError:
            digest.update(f"{match.group(1)}:missing".encode())
    key = digest.hexdigest()[:20]
    cache = _node_stl_cache_dir()
    return cache / f"{key}.scad", cache / f"{key}.stl"


def _node_stl_lock(key: str) -> threading.Lock:
    with _NODE_STL_LOCKS_GUARD:
        lock = _NODE_STL_LOCKS.get(key)
        if lock is None:
            lock = _NODE_STL_LOCKS[key] = threading.Lock()
        return lock


def _served_node_stl(stl_path: Path) -> Optional[bytes]:
    """A cached render's bytes, its atime set to now; None when there is none."""
    try:
        mtime_ns = stl_path.stat().st_mtime_ns
        os.utime(stl_path, ns=(time.time_ns(), mtime_ns))
        return stl_path.read_bytes()
    except FileNotFoundError:
        return None


def _render_node_stl(scad_text: str, scad_path: Path, stl_path: Path) -> None:
    """Render ``scad_text`` to ``stl_path``; the scratch SCAD is removed either way."""
    renderer = get_stl_renderer()
    if not renderer.is_available:
        raise HTTPException(
            status_code=503, detail="OpenSCAD not installed. Cannot generate STL files."
        )
    scad_path.parent.mkdir(parents=True, exist_ok=True)
    scad_path.write_text(scad_text, encoding="utf-8")
    try:
        result = renderer.render_stl(scad_path, stl_path, timeout=60)
    finally:
        scad_path.unlink(missing_ok=True)
    if not result.success:
        raise HTTPException(
            status_code=500, detail=f"STL generation failed: {result.error_message}"
        )
    if result.dropped:
        # A node is the whole of what it holds; a mesh OpenSCAD could not
        # read back is missing from what it wrote, and that is not served.
        stl_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=500,
            detail="OpenSCAD dropped part of this node's geometry: "
            + "; ".join(result.dropped)[:400],
        )


def _trim_node_stl_cache(cache: Path, keep: int = NODE_STL_KEEP) -> None:
    """Remove all but the ``keep`` most recently served renders.

    A render still being written is a dot-file (OpenSCADRenderer.render_stl)
    and is left alone.
    """
    served = []
    for stl in cache.glob("*.stl"):
        if stl.name.startswith("."):
            continue
        try:
            served.append((stl.stat().st_atime_ns, stl))
        except FileNotFoundError:
            continue
    served.sort(reverse=True)
    for _, stl in served[keep:]:
        stl.unlink(missing_ok=True)


def _build_parts_referred_to(node: Assembly) -> None:
    """Build the STL of every registered part the subtree refers to and lacks."""
    wanted = set()

    def visit(n: Assembly) -> None:
        if n.part_ref and n.base is None:
            wanted.add(n.part_ref)
        for child in (*n.children, *n.additions, *n.subtractions):
            visit(child)

    visit(node)
    if not wanted or not get_stl_renderer().is_available:
        return
    by_name = {p.name: p for p in scan_projects(ROOT) if p.kind == "part"}
    for ref in sorted(wanted):
        if ref not in by_name:
            continue
        part = _registered_part(by_name[ref])
        if not part.get_stl_output_path().exists():
            build_stl(part, timeout=120)


def _bounds_dict(bounds: BoundingBox3D | None) -> Dict[str, List[float]] | None:
    if bounds is None:
        return None
    return {
        "min": [bounds.min_point.x, bounds.min_point.y, bounds.min_point.z],
        "max": [bounds.max_point.x, bounds.max_point.y, bounds.max_point.z],
    }


def _structure_summary(structure: Assembly) -> Dict[str, object]:
    return {
        "name": structure.name,
        "material": structure.material,
        "status": structure.status,
        "position": {
            "x": structure.position.x,
            "y": structure.position.y,
            "z": structure.position.z,
        },
        "footprint": _bounds_dict(structure.footprint),
        "world_bounds": _bounds_dict(structure.world_bounds()),
        "build_volume": (
            [structure.build_volume.x, structure.build_volume.y, structure.build_volume.z]
            if structure.build_volume
            else None
        ),
        "substructures": [
            {
                "name": sub.name,
                "features": [f.name for f in (*sub.additions, *sub.subtractions)],
            }
            for sub in structure.children
        ],
    }


def _primitive_descriptor(obj: OpenSCADObject, offset: Vector3D) -> Dict[str, object] | None:
    """Best-effort translation of a leaf's own geometry into a lightweight,
    client-renderable primitive descriptor -- Cube/Cylinder/Sphere, optionally
    wrapped in one Translate (accumulated into ``offset``, which starts as
    the node's own ``position`` so the returned bounds are already
    world-space, matching ``world_bounds``). This covers every leaf in this
    repo's own examples. Returns None for anything richer (nested booleans,
    Rotate, Scale, multiple children) -- the viewer falls back to a
    bounding-box wireframe for those, a deliberate scope boundary, not a
    bug: real CSG rendering of composite nodes is future work.
    """
    if isinstance(obj, Translate):
        if len(obj.children) != 1:
            return None
        return _primitive_descriptor(obj.children[0], offset + obj.v)

    if isinstance(obj, Cube):
        size = (
            obj.size
            if isinstance(obj.size, Vector3D)
            else Vector3D(x=obj.size, y=obj.size, z=obj.size)
        )
        local_min = (
            Vector3D(x=-size.x / 2, y=-size.y / 2, z=-size.z / 2) if obj.center else Vector3D()
        )
        bounds = BoundingBox3D(min_point=local_min + offset, max_point=local_min + size + offset)
        return {"type": "cube", "size": [size.x, size.y, size.z], "bounds": _bounds_dict(bounds)}

    if isinstance(obj, Cylinder):
        r1, r2 = obj.radii()
        max_r = max(r1, r2)
        z0 = -obj.h / 2 if obj.center else 0.0
        local_min = Vector3D(x=-max_r, y=-max_r, z=z0)
        local_max = Vector3D(x=max_r, y=max_r, z=z0 + obj.h)
        bounds = BoundingBox3D(min_point=local_min + offset, max_point=local_max + offset)
        return {"type": "cylinder", "h": obj.h, "r1": r1, "r2": r2, "bounds": _bounds_dict(bounds)}

    if isinstance(obj, Sphere):
        r = obj.r
        bounds = BoundingBox3D(
            min_point=Vector3D(x=-r, y=-r, z=-r) + offset,
            max_point=Vector3D(x=r, y=r, z=r) + offset,
        )
        return {"type": "sphere", "r": r, "bounds": _bounds_dict(bounds)}

    return None


def _assembly_tree(
    node: Assembly,
    parent_world_position: Vector3D | None = None,
    parent_category: str | None = None,
) -> Dict[str, object]:
    """Recursive serialization of an Assembly node and everything beneath it.

    Unlike ``_structure_summary`` (which flattens one extra level for the
    old, depth-capped viewers), this walks the *whole* tree -- the shape the
    fractal zoom viewer needs to navigate unbounded depth. ``children``,
    ``additions``, and ``subtractions`` are all real Assembly nodes (a
    garage printer's ``left_post``/``gantry_bar`` Features are additions, not
    children), so all three are combined into one navigable ``children``
    list here, each tagged with how it composes into its parent's geometry --
    navigation doesn't care about that distinction, but a viewer showing
    "what's inside" vs. "what's added/removed" might.

    ``Assembly.world_bounds()`` only offsets by *this* node's own
    ``position`` -- correct for a direct child of the root (the only depth
    the old, depth-capped viewers ever showed), wrong for anything deeper,
    since a node's ``position`` is relative to its immediate parent, not the
    root. A Structure two levels down from the site root would render as if
    its parent were sitting at the origin. ``parent_world_position``
    accumulates every ancestor's position on the way down so every node's
    reported ``position``/``world_bounds`` is genuinely in one consistent
    global frame, however deep -- the fractal viewer's camera framing and
    "show everything at once" mode both depend on this being true.

    ``category`` is resolved the same inheriting way: most nodes never set
    their own (see ``Assembly.category``'s docstring), so the reported
    ``category`` is this node's own if set, else whatever the nearest
    ancestor set -- a viewer can color-code a whole Structure's tree from
    one tag on its root instead of needing every Substructure/Feature
    tagged individually.
    """
    parent_world_position = parent_world_position or Vector3D()
    world_position = parent_world_position + node.position
    category = node.category if node.category is not None else parent_category
    world_bounds = (
        BoundingBox3D(
            min_point=node.footprint.min_point + world_position,
            max_point=node.footprint.max_point + world_position,
        )
        if node.footprint is not None
        else None
    )

    composed = (
        [(c, "child") for c in node.children]
        + [(c, "addition") for c in node.additions]
        + [(c, "subtraction") for c in node.subtractions]
    )
    return {
        "name": node.name,
        "role": node.role,
        "material": node.material,
        "status": node.status,
        "comment": node.comment,
        "part_ref": node.part_ref,
        "sketch_ref": node.sketch_ref,
        "category": category,
        "position": {"x": world_position.x, "y": world_position.y, "z": world_position.z},
        "footprint": _bounds_dict(node.footprint),
        "world_bounds": _bounds_dict(world_bounds),
        "build_volume": (
            [node.build_volume.x, node.build_volume.y, node.build_volume.z]
            if node.build_volume
            else None
        ),
        "build_origin": (
            [node.build_origin.x, node.build_origin.y, node.build_origin.z]
            if node.build_origin
            else None
        ),
        "primitive": (
            _primitive_descriptor(node.base, world_position) if node.base is not None else None
        ),
        "children": [
            {**_assembly_tree(child, world_position, category), "composition": composition}
            for child, composition in composed
        ],
    }


def _site_payload(site, report) -> Dict[str, object]:
    """The site as the viewer consumes it, including its generated OpenSCAD.

    ``scad`` used to be attached only by the layout route, so a site that had
    merely been loaded -- never dragged -- left the viewer's code panel showing
    its "Load a site..." placeholder indefinitely. It is string generation over
    a tree already in memory, not an OpenSCAD process, so every read carries it.

    A node that cannot compile is reported as a comment rather than a 500: the
    panel is one of several surfaces on the page, and the rest of them work.
    """
    try:
        scad = site.render()
    except ValueError as exc:
        scad = f"// This site has no generated OpenSCAD: {exc}"

    return {
        "name": site.name,
        "structures": [_structure_summary(s) for s in site.children],
        "tree": _assembly_tree(site),
        "violations": [v.model_dump() for v in report.violations],
        "is_valid": report.is_valid,
        "scad": scad,
    }


class PositionOverride(BaseModel):
    x: float
    y: float
    z: float


class LayoutRequest(BaseModel):
    positions: Dict[str, PositionOverride] = Field(default_factory=dict)


class StatusRequest(BaseModel):
    status: str


SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
# Words that are routes of their own under /photos/ (apothecary/routes/pictures.py):
# an arrangement so named could be built and then never fetched or forgotten,
# because its address is theirs -- and forgetting it would forget the kept
# pictures instead.
RESERVED_NAMES = frozenset({"pictures", "gather"})


def _check_name(name: str) -> str:
    """Refuse a name that is not simply a name.

    A name becomes part of a web address and a key in a register. One
    containing a slash can be stored and then never fetched or deleted again,
    because the address for it cannot be typed; one containing dots walks up
    directories in anything that later joins it to a path; one that is a
    route's own word is answered by the route, never by the arrangement.
    """
    if not SAFE_NAME.match(name or ""):
        raise HTTPException(
            status_code=400,
            detail=(
                f"{name!r} is not a usable name. Letters, numbers, dashes and "
                "underscores, starting with a letter or number, up to 64 characters."
            ),
        )
    if name in RESERVED_NAMES:
        raise HTTPException(
            status_code=400,
            detail=(
                f"{name!r} is the address of a route under /photos/; "
                "name the arrangement something else."
            ),
        )
    return name


class LookAtPicture(BaseModel):
    """Ask the server to look at a picture already on this machine."""

    picture: str
    name: Optional[str] = None
    width_mm: Optional[float] = Field(None, gt=0, allow_inf_nan=False)
    finder: str = "plain"


def _picture_root() -> Path:
    """The one folder pictures may be read from.

    A server that reads any path it is handed is a server that will read
    ``/etc/shadow`` the day somebody points it at a network it did not expect.
    Everything here is meant to run on one machine and listen only to it, and
    that is still not a reason to leave the door open.

    Set ``APOTHECARY_PICTURE_ROOT`` to say where pictures live. Without it, the
    folder the server was started in. Never the whole machine, and never the
    person's home folder or anything above it: a picture root is a folder of
    pictures, and those hold everything else of theirs.
    """
    named = os.environ.get("APOTHECARY_PICTURE_ROOT") or str(Path.cwd())
    root = Path(named).resolve()
    if not root.is_dir():
        raise HTTPException(
            status_code=500,
            detail=(
                f"pictures are supposed to be read from {root}, and there is no "
                "folder there. Set APOTHECARY_PICTURE_ROOT to one that exists."
            ),
        )
    if root == Path(root.anchor):
        raise HTTPException(
            status_code=500,
            detail=(
                f"pictures are supposed to be read from {root}, which is the whole "
                "machine. That turns the restriction off rather than setting it."
            ),
        )
    homes = _home_folders()
    state = _state_folder()
    if any(root == home or root in home.parents for home in homes) or (
        root == state or state in root.parents
    ):
        raise HTTPException(
            status_code=500,
            detail=(
                f"pictures are supposed to be read from {root}, which holds everything "
                "of yours, not a folder of pictures. Start the server in a folder of "
                "pictures, or set APOTHECARY_PICTURE_ROOT to one."
            ),
        )
    return root


def _home_folders() -> List[Path]:
    """The person's home: by HOME, and by the account, which a variable cannot move."""
    folders = [Path.home()]
    try:
        import pwd

        folders.append(Path(pwd.getpwuid(os.getuid()).pw_dir))
    except (ImportError, KeyError, AttributeError):
        pass
    return [f.expanduser().resolve() for f in folders]


def _state_folder() -> Path:
    """Where the serial numbers, camera labels and readings live: never pictures."""
    from .firmware.devices import state_dir

    return state_dir().expanduser().resolve()


def _picture_within_root(where: Path) -> Path:
    """Check a picture is inside the one folder, following any links first.

    Checked every time it is used, not only when it arrives. A file that passed
    on the way in can be swapped for a link pointing anywhere afterwards, and
    then the door that refused it is serving it.
    """
    root = _picture_root()
    try:
        settled = Path(where).resolve()
        settled.relative_to(root)
    except (ValueError, OSError):
        raise HTTPException(
            status_code=403, detail=f"pictures are read from {root} and nowhere else"
        ) from None
    # `is_file` rather than `exists`: a pipe exists, and opening one waits for
    # somebody to write to it, which is never. It also has to be guarded,
    # because asking about an impossible path is itself an error rather than a
    # no.
    try:
        real = settled.is_file()
    except OSError as exc:
        raise HTTPException(
            status_code=400, detail=f"{settled} cannot be looked at: {exc}"
        ) from None
    if not real:
        raise HTTPException(
            status_code=404,
            detail=f"there is no picture at {settled}, or it is not an ordinary file",
        )
    return settled


@app.post("/photos")
def look_at_picture(request: LookAtPicture):
    """Look at a picture on this machine and shelve what was built from it.

    The picture is read from disk each time and nothing is copied anywhere. The
    arrangement is held in memory for as long as the server runs.
    """
    from .vision import ScaleReference
    from .vision import build as build_arrangement
    from .vision import get as get_finder
    from .vision.shelf import shelf

    root = _picture_root()
    asked = Path(request.picture)
    where = _picture_within_root(asked if asked.is_absolute() else root / asked)

    name = _check_name(request.name or where.stem)
    stock = shelf()
    if name in _site_store.names() and name not in stock:
        raise HTTPException(
            status_code=409,
            detail=(
                f"{name!r} is already the name of an arrangement that did not come "
                "from a picture. Choose another name rather than covering it over."
            ),
        )

    try:
        finder = get_finder(request.finder)
    except KeyError:
        raise HTTPException(status_code=400, detail=f"no finder named {request.finder!r}") from None

    try:
        picture = finder.look(where)
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"{where} could not be read: {exc}") from None

    scale = ScaleReference(millimetres_across=request.width_mm) if request.width_mm else None
    made = build_arrangement(picture, name=name, scale=scale, picture_path=where)

    stock.put(made)
    _site_store.add(made.site.name, stock.factory(made.site.name), stock.checker(made.site.name))
    return get_photo_album(made.site.name)


@app.get("/photos")
def list_photo_sites():
    """Every arrangement built from a picture in this session."""
    return _photo_shelf().names()


@app.get("/photos/{name}")
def get_photo_album(name: str):
    """What is known about each piece of one arrangement built from a picture.

    Kept beside the arrangement rather than inside it, and joined to it by the
    same dotted path the rest of the API uses to name a node.
    """
    stock = _photo_shelf()
    if name not in stock:
        raise HTTPException(status_code=404, detail=f"no picture-built arrangement named {name!r}")
    album = stock.album(name)
    return {
        "name": name,
        "picture": album.picture_name,
        "pixel_width": album.pixel_width,
        "pixel_height": album.pixel_height,
        "finder": album.finder,
        "millimetres_across": album.millimetres_across,
        "sized": album.sized,
        "groups": album.groups(),
        "least_sure": album.unsure(),
        "share_a_machine_guessed": album.guessed_share(),
        "seen_in_several": album.seen_in_several(),
        "pieces": {
            path: {
                **about.model_dump(),
                "summary": about.summary(),
                "sightings": about.sightings,
            }
            for path, about in album.provenance.items()
        },
    }


@app.delete("/photos/{name}")
def forget_photo_site(name: str):
    """Forget an arrangement built from a picture.

    Anything that can be added while the server runs has to be removable while
    it runs, or whatever adds one has no way to tidy up after itself.
    """
    stock = _photo_shelf()
    if name not in stock:
        raise HTTPException(
            status_code=404,
            detail=(
                f"no arrangement built from a picture is named {name!r}. Only those "
                "can be forgotten here; the ones built into the program stay."
            ),
        )
    stock.forget(name)
    _site_store.remove(name)
    return {"forgotten": name}


@app.get("/photos/{name}/picture")
def get_photo_picture(name: str):
    """The picture this arrangement was built from, as it was on disk.

    Read from where the person pointed, each time it is asked for. Nothing is
    copied anywhere and nothing is cached.
    """
    stock = _photo_shelf()
    if name not in stock:
        raise HTTPException(status_code=404, detail=f"no picture-built arrangement named {name!r}")
    where = stock.album(name).picture_path
    if where is None or not Path(where).exists():
        raise HTTPException(
            status_code=404,
            detail="the picture is no longer where it was when this was built",
        )
    settled = _picture_within_root(where)

    # The type is chosen from a short list, not built out of the file name. A
    # name can contain anything at all, including the characters that end a
    # header, and a header built by pasting a file name into it is a header
    # somebody else gets to write.
    guessed, _ = mimetypes.guess_type(settled.name)
    kind = guessed if guessed in PICTURE_TYPES else "application/octet-stream"
    return Response(
        content=settled.read_bytes(),
        media_type=kind,
        headers={"X-Content-Type-Options": "nosniff"},
    )


@app.get("/sites")
async def list_sites():
    return _site_store.names()


@app.get("/sites/{name}")
def get_site(name: str):
    site = _get_site_or_404(name)
    validator = _site_store.validator(name)
    return _site_payload(site, validator(site))


@app.post("/sites/{name}/layout")
async def update_site_layout(name: str, body: LayoutRequest):
    """Apply position overrides (persisted), re-validate, and return regenerated OpenSCAD.

    ``body.positions`` need only include the structures the client has
    moved; everything else keeps its current persisted position.
    """
    site = _get_site_or_404(name)
    for structure in site.children:
        override = body.positions.get(structure.name)
        if override is not None:
            structure.position = Vector3D(x=override.x, y=override.y, z=override.z)

    validator = _site_store.validator(name)
    return _site_payload(site, validator(site))


@app.post("/sites/{name}/structures/{structure_name}/status")
async def update_structure_status(name: str, structure_name: str, body: StatusRequest):
    """Set a Structure's status (persisted). Validated against PRINTER_STATUSES.

    This is the garage scenario's closed set, not a hierarchy-wide rule --
    ``Structure.status`` itself is a free-form string; a future site with a
    different notion of status would validate against its own set here.
    """
    if body.status not in PRINTER_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status {body.status!r}; must be one of {PRINTER_STATUSES}",
        )
    site = _get_site_or_404(name)
    structure = next((s for s in site.children if s.name == structure_name), None)
    if structure is None:
        raise HTTPException(
            status_code=404, detail=f"Structure '{structure_name}' not found in site '{name}'"
        )
    structure.status = body.status

    validator = _site_store.validator(name)
    return _site_payload(site, validator(site))


@app.post("/sites/{name}/reset")
async def reset_site_layout(name: str):
    """Discard all edits and rebuild the site fresh from its factory.

    Also clears the site's job queue: a reset re-idles every printer, so a
    job still marked "assigned" to one would otherwise be stale.
    """
    _get_site_or_404(name)  # validates the name before resetting
    site = _site_store.reset(name)
    _job_store.reset(name)
    validator = _site_store.validator(name)
    payload = _site_payload(site, validator(site))
    payload["scad"] = site.render()
    return payload


@app.get("/sites/{name}/nodes/{path}/stl")
def get_node_stl(name: str, path: str):
    """Render one node's subtree to STL through OpenSCAD, cached by content.

    For composite nodes (a wall with a cutout, a whole Structure): leaves are
    drawn from ``_primitive_descriptor`` or their part's STL. The SCAD is the
    node's ``to_scad_object()``, what the site's own render produces for it,
    written into the cache with absolute import paths and rendered there. One
    render per key at a time; the cache keeps the NODE_STL_KEEP most
    recently served.
    """
    site = _get_site_or_404(name)
    node = _find_node_by_path(site, path)
    if node is None:
        raise HTTPException(status_code=404, detail=f"Node '{path}' not found in site '{name}'")

    # A part the subtree imports is a build product a fresh clone lacks.
    _build_parts_referred_to(node)

    try:
        with absolute_imports(ROOT):
            scad_text = node.to_scad_object(strict=True).render()
    except ValueError as exc:
        raise HTTPException(
            status_code=422, detail=f"Node '{path}' has no renderable geometry: {exc}"
        ) from None

    scad_path, stl_path = _node_stl_cache_paths(scad_text)
    with _node_stl_lock(stl_path.stem):
        stl_data = _served_node_stl(stl_path)
        if stl_data is None:
            _render_node_stl(scad_text, scad_path, stl_path)
            stl_data = _served_node_stl(stl_path)
            _trim_node_stl_cache(stl_path.parent)
    if stl_data is None:
        raise HTTPException(status_code=500, detail="OpenSCAD wrote no STL for this node")
    return Response(
        content=stl_data,
        media_type="application/sla",
        headers={"Content-Disposition": f'attachment; filename="{node.name}.stl"'},
    )


# -----------------------------------------------------------------------
# Devices of a site: which board sits at which node (see firmware/bindings.py).
# These live here, not on the firmware router, because they need the site
# store; the firmware package stays importable on its own.
# -----------------------------------------------------------------------


def status_bearer_for(site: Assembly, path: str) -> Optional[str]:
    """The path of ``path`` itself if it carries a status, else its nearest ancestor that does.

    A printer's port is pinned to its *board* (``printer_1.frame_system.mainboard``),
    which has no status of its own; the printer Structure above it is what
    the polls drive. ``None`` when nothing up the path carries a status (a
    footpedal, say).
    """
    parts = path.split(".")
    for depth in range(len(parts), 0, -1):
        candidate = ".".join(parts[:depth])
        node = _find_node_by_path(site, candidate)
        if node is not None and node.status is not None:
            return candidate
    return None


def _world_position_of(site: Assembly, path: str) -> Vector3D:
    """Sum of positions from the site root down to ``path``, each in its parent's frame."""
    total = Vector3D()
    node = site
    for name in path.split("."):
        node = next(
            (c for c in [*node.children, *node.additions, *node.subtractions] if c.name == name),
            None,
        )
        if node is None:
            break
        total = total + node.position
    return total


def _base_height(printer: Assembly) -> float:
    """How tall the printer's base is: the enclosure its bed sits on.

    The site's printers keep it in a ``frame_system`` substructure whose base
    is a Cube; a printer built some other way answers zero, and the board
    view draws the bed on the floor of the footprint.
    """
    for child in printer.children:
        if child.name != "frame_system":
            continue
        if child.footprint:
            return float(child.footprint.max_point.z)
        size = getattr(child.base, "size", None)
        if size is not None:
            return float(size.z)
    return 0.0


def _describe_for_view(
    site: Assembly, path: str, n: Assembly, *, is_printer: bool
) -> Dict[str, object]:
    """One node as the board view wants it: world position, footprint, build volume, base."""
    pos = _world_position_of(site, path)
    fp = n.footprint
    return {
        "path": path,
        "name": n.name,
        "position": {"x": pos.x, "y": pos.y, "z": pos.z},
        "footprint": (
            {
                "min": [fp.min_point.x, fp.min_point.y, fp.min_point.z],
                "max": [fp.max_point.x, fp.max_point.y, fp.max_point.z],
            }
            if fp
            else None
        ),
        "build_volume": (
            [n.build_volume.x, n.build_volume.y, n.build_volume.z]
            if getattr(n, "build_volume", None)
            else None
        ),
        # Where the build volume starts, in the node's frame, when the node
        # says; else the bed sits on the base of a desktop printer, centred.
        "build_origin": (
            [n.build_origin.x, n.build_origin.y, n.build_origin.z]
            if getattr(n, "build_origin", None)
            else None
        ),
        "base_height": (
            n.build_origin.z
            if getattr(n, "build_origin", None)
            else (_base_height(n) if is_printer else 0.0)
        ),
    }


@app.get("/firmware/printers/where", tags=["firmware"])
def printer_where(port: str):
    """Where a port is pinned, with the geometry a board view needs.

    Searches the loaded sites for a manual pin to ``port``. Answers the
    board (the pinned node) and the printer above it (the nearest
    status-bearing ancestor, or the board itself) with world positions, the
    footprint and build volume, and the base height the build volume sits
    on -- what ``apothecary/static/board_view.js`` draws. ``board`` is
    ``None`` when nothing is pinned.
    """
    state = firmware_devices.get_state()
    known = firmware_devices.known_device(port, state)
    # Every pin, not just the loaded sites': the monitor is often the first
    # page opened after the server starts, and a pin names its site.
    for binding in state.bindings():
        if not same_device(binding.identity, port, known):
            continue
        if binding.site not in _site_store.names():
            continue
        site = _site_store.get(binding.site)
        node = _find_node_by_path(site, binding.path)
        if node is None:
            continue
        bearer_path = status_bearer_for(site, binding.path) or binding.path
        bearer = _find_node_by_path(site, bearer_path) or node
        return {
            "port": port,
            "site": binding.site,
            "board": _describe_for_view(site, binding.path, node, is_printer=False),
            "printer": (
                _describe_for_view(site, bearer_path, bearer, is_printer=True)
                if bearer_path != binding.path
                else None
            ),
        }
    return {"port": port, "site": None, "board": None, "printer": None}


@app.get("/firmware/pins", tags=["firmware"])
def every_pin(fresh: bool = False):
    """Every pin on this machine, whatever site it names -- the management view.

    ``GET /sites/{name}/devices`` shows a site's pins where its nodes are; a
    pin whose site was forgotten (a photo arrangement) or whose node is gone
    appears nowhere else, and this is where it is seen and taken back. Each
    row says whether its site and node still exist and which detected board,
    if any, is the pinned identity today. Plain ``def``: the device scan
    shells out to arduino-cli (cached a couple of seconds).
    """
    state = firmware_devices.get_state()
    problem = None
    try:
        found = firmware_devices.detected_devices(fresh=fresh)
    except ToolchainError as exc:
        found, problem = [], str(exc)
    names = _site_store.names()
    rows = []
    for binding in sorted(state.bindings(), key=lambda b: (b.site, b.path)):
        site_known = binding.site in names
        node_found = False
        if site_known:
            try:
                node = _find_node_by_path(_site_store.get(binding.site), binding.path)
            except KeyError:  # forgotten, or its picture left the shelf, since names()
                node = None
            node_found = node is not None
        device = device_for_identity(binding.identity, found)
        rows.append(
            {
                **binding.model_dump(mode="json"),
                "site_known": site_known,
                "node_found": node_found,
                "device": device.model_dump(mode="json") if device is not None else None,
            }
        )
    return {"pins": rows, "problem": problem}


@app.delete("/firmware/pins/{site}/{path:path}", tags=["firmware"])
def unpin_anywhere(site: str, path: str):
    """Take a pin back by what it names, whether or not its site or node still exists."""
    if not firmware_devices.get_state().clear_binding(site, path):
        raise HTTPException(status_code=404, detail=f"nothing is pinned at {site} › {path}")
    return {"unpinned": {"site": site, "path": path}}


def _sync_printer_status(status) -> List[Dict[str, object]]:
    """A printer poll drives the status of the node its port is pinned to -- or the
    nearest ancestor that carries a status, when the pin is on a board inside it.

    Registered on ``firmware.devices.STATUS_LISTENERS`` at import. Nodes
    with no status anywhere up the path are left alone (a footpedal), and a
    hand-set ``maintenance`` is never overridden by a poll -- the printer
    may well be idle *because* someone is working on it.
    """
    out: List[Dict[str, object]] = []
    if status.state not in PRINTER_STATUSES:
        return out
    state = firmware_devices.get_state()
    known = firmware_devices.known_device(status.port, state)
    for site_name in _site_store.loaded():
        site = _site_store.get(site_name)
        for binding in state.bindings(site_name):
            if not same_device(binding.identity, status.port, known):
                continue
            target = status_bearer_for(site, binding.path)
            if target is None:
                continue
            node = _find_node_by_path(site, target)
            row: Dict[str, object] = {"site": site_name, "path": target}
            if target != binding.path:
                row["via"] = binding.path
            if node.status == "maintenance":
                out.append({**row, "status": node.status, "changed": False, "held": True})
                continue
            changed = node.status != status.state
            node.status = status.state
            out.append({**row, "status": node.status, "changed": changed})
    return out


firmware_devices.STATUS_LISTENERS.append(_sync_printer_status)


def _site_devices_payload(name: str, site: Assembly, fresh: bool = False) -> Dict[str, object]:
    problem = None
    try:
        found = firmware_devices.detected_devices(fresh=fresh)
    except ToolchainError as exc:
        found, problem = [], str(exc)
    # Refresh printers whose link is already held (0.1 s, no reset); a
    # never-opened port is left alone so this view never reboots a board.
    links = firmware_gcode.get_printer_links()
    for d in found:
        if d.printer is not None and links.get(d.port) is not None:
            firmware_devices.printer_status(d.port)
    rows = bindings_for_site(name, site, devices=found)
    return {
        "site": name,
        "bindings": [r.model_dump(mode="json") for r in rows],
        "devices": [firmware_device_view(d) for d in found],
        "streaming": firmware_devices.get_streams().open_ports,
        "problem": problem,
    }


def _binding_row(name: str, site: Assembly, path: str) -> Dict[str, object]:
    """The one row a pin change touches, from the cached port scan.

    No printer is polled: a pin is a state write. GET /sites/{name}/devices
    refreshes the held printer links.
    """
    try:
        found = firmware_devices.detected_devices()
    except ToolchainError:
        found = []
    rows = bindings_for_site(name, site, devices=found)
    row = next((r for r in rows if r.path == path), None)
    if row is None:
        return {"path": path, "name": path.rsplit(".", 1)[-1], "binding_source": None}
    return row.model_dump(mode="json")


@app.get("/sites/{name}/devices")
def site_devices(name: str, fresh: bool = False):
    """Every node of the site that names firmware, with the board bound to it.

    Plain ``def``: ``detected_devices`` shells out to arduino-cli, so this
    runs in the threadpool rather than blocking the event loop. ``fresh``
    bypasses the short port-scan cache (a rescan button, the auto-refresh).
    """
    site = _get_site_or_404(name)
    return _site_devices_payload(name, site, fresh=fresh)


@app.put("/sites/{name}/nodes/{path}/device")
def attach_device(name: str, path: str, body: DeviceAttachRequest):
    """Pin a device to a node; overrides the by-sketch rule.

    A port given for a device that is detected right now is stored as that
    device's own identity (its MAC or USB serial number) when it has one:
    the pin follows the board, not the socket it happens to be in today.
    """
    site = _get_site_or_404(name)
    if _find_node_by_path(site, path) is None:
        raise HTTPException(status_code=404, detail=f"Node '{path}' not found in site '{name}'")
    identity = firmware_devices.stable_identity(body.identity)
    firmware_devices.get_state().set_binding(name, path, identity)
    return _binding_row(name, site, path)


@app.delete("/sites/{name}/nodes/{path}/device")
def detach_device(name: str, path: str):
    """Drop a pin; the node goes back to the by-sketch rule (or to nothing)."""
    site = _get_site_or_404(name)
    if _find_node_by_path(site, path) is None:
        raise HTTPException(status_code=404, detail=f"Node '{path}' not found in site '{name}'")
    firmware_devices.get_state().clear_binding(name, path)
    return _binding_row(name, site, path)


# -----------------------------------------------------------------------
# Jobs: capacity-checked assignment to printer Structures (manufacturing
# planning, first slice). See example_hierarchy.py's Job/JobStore.
# -----------------------------------------------------------------------


class Dimensions(BaseModel):
    x: float
    y: float
    z: float


class CreateJobRequest(BaseModel):
    # A name is letters, digits and a little punctuation: what a page shows, never markup.
    # No slash: a job's name is a path segment of its own routes, and one with a
    # slash could be created and never assigned, completed or found again.
    name: str = Field(..., min_length=1, max_length=80, pattern=r"^[\w][\w .+\-]*$")
    required_volume: Dimensions


class AssignJobRequest(BaseModel):
    printer: str


def _job_summary(job: Job, site: Assembly) -> Dict[str, object]:
    compatible = [
        s.name
        for s in site.children
        if s.build_volume is not None and s.status == "idle" and job_fits_printer(job, s)
    ]
    return {
        "name": job.name,
        "required_volume": [job.required_volume.x, job.required_volume.y, job.required_volume.z],
        "status": job.status,
        "assigned_printer": job.assigned_printer,
        "compatible_printers": compatible,
    }


@app.get("/sites/{name}/jobs")
def list_jobs(name: str):
    site = _get_site_or_404(name)
    return [_job_summary(job, site) for job in _job_store.list_for_site(name)]


@app.post("/sites/{name}/jobs")
async def create_job(name: str, body: CreateJobRequest):
    site = _get_site_or_404(name)
    job = Job(
        name=body.name,
        required_volume=Vector3D(
            x=body.required_volume.x, y=body.required_volume.y, z=body.required_volume.z
        ),
    )
    try:
        _job_store.add(name, job)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _job_summary(job, site)


@app.post("/sites/{name}/jobs/{job_name}/assign")
async def assign_job(name: str, job_name: str, body: AssignJobRequest):
    """Assign a job to a printer, checked against its build volume and idle status.

    Assigning flips the printer's own status to "printing" -- the two
    concepts (job assignment, printer status) are meant to move together.
    """
    site = _get_site_or_404(name)
    try:
        job = _job_store.get(name, job_name)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Job '{job_name}' not found") from None

    if job.status != "queued":
        # Re-assigning an assigned job overwrote its printer and left the first
        # one "printing" forever; a done job is done.
        raise HTTPException(
            status_code=409, detail=f"Job '{job_name}' is {job.status}, not queued"
        )
    printer = next((s for s in site.children if s.name == body.printer), None)
    if printer is None or printer.build_volume is None:
        raise HTTPException(status_code=404, detail=f"Printer '{body.printer}' not found")
    if printer.status != "idle":
        raise HTTPException(
            status_code=409,
            detail=f"Printer '{body.printer}' is not idle (status={printer.status})",
        )
    if not job_fits_printer(job, printer):
        raise HTTPException(
            status_code=422,
            detail=(
                f"Job '{job_name}' (required volume "
                f"{[job.required_volume.x, job.required_volume.y, job.required_volume.z]}) "
                f"does not fit printer '{body.printer}''s build volume "
                f"{[printer.build_volume.x, printer.build_volume.y, printer.build_volume.z]}"
            ),
        )

    job.status = "assigned"
    job.assigned_printer = printer.name
    printer.status = "printing"
    return _job_summary(job, site)


@app.post("/sites/{name}/jobs/{job_name}/complete")
async def complete_job(name: str, job_name: str):
    """Mark a job done and free its printer back to idle.

    ``assigned_printer`` is left in place as a record of which printer did
    the job, even though the job is no longer occupying it.
    """
    site = _get_site_or_404(name)
    try:
        job = _job_store.get(name, job_name)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Job '{job_name}' not found") from None

    if job.status != "assigned":
        # Completing a job twice freed a printer that had since started another.
        raise HTTPException(
            status_code=409, detail=f"Job '{job_name}' is {job.status}, not assigned"
        )
    printer = next((s for s in site.children if s.name == job.assigned_printer), None)
    if printer is not None and printer.status == "printing":
        printer.status = "idle"
    job.status = "done"
    return _job_summary(job, site)


@app.get("/viewer")
async def viewer_home():
    """Redirect to the fractal zoom viewer for the first registered site.

    There is no longer a standalone parts browser or bare Site browser --
    both are absorbed into one viewer (see ``site_viewer`` below); this is
    just its default entry point.
    """
    names = _site_store.names()
    default_site = DEFAULT_VIEWER_SITE if DEFAULT_VIEWER_SITE in names else names[0]
    return RedirectResponse(f"/viewer/sites/{default_site}", status_code=307)


@app.get("/viewer/sites/{name}", response_class=HTMLResponse)
def site_viewer(name: str, request: Request, focus: str = Query(default="")):
    """Fractal zoom viewer: navigates any registered site's Assembly tree at
    any depth with standardized controls (prototype).

    Absorbs both previous viewers: the registered ``parts/`` library is
    reachable by selecting the ``parts_library`` site and zooming down to a
    leaf (``part_ref`` set) -- the old part-viewer experience, no longer a
    separate page. ``focus`` is an optional dotted path (e.g.
    ``workbench.frame_system``) used to deep-link directly to a node instead
    of always opening at the root.
    """
    if name not in _site_store.names():
        raise HTTPException(status_code=404, detail=f"Site '{name}' not found")
    base_url = str(request.base_url).rstrip("/")
    return HTMLResponse(
        render_fractal_viewer_page(
            _site_store.names(),
            base_url,
            default_site=name,
            focus_path=focus,
            three_is_vendored=THREE_IS_VENDORED,
        )
    )


@app.get("/viewer/parts/{name}")
def part_view(name: str):
    """A part is reached by navigating to it, not by a second viewer.

    This deep-link survives because links to it were handed out, but it now
    lands in the one viewer, focused on the part, where the parameter controls
    and the contested values live. Two pages onto one object is how a codebase
    ends up with two answers about it.
    """
    part = _load_part_wrapper(name)  # 404 here rather than after a redirect
    # Focus on the part's own name, not on whatever spelling was typed. The
    # library was consolidated to underscore case and links to `datum-core`
    # were handed out before that; the wrapper lookup already tolerates the
    # old spelling, and this makes the viewer land on the part rather than on
    # a focus string matching nothing.
    canonical = part.name or name
    return RedirectResponse(
        f"/viewer/sites/parts_library?focus={quote(canonical, safe='')}", status_code=307
    )


# The project's first APIRouter, mounted last. Its handlers reach back into the
# helpers above, so this module has to be finished before it is imported --
# importing it at the top would close a circle.
from .routes.menu import router as menu_router  # noqa: E402

app.include_router(menu_router)
