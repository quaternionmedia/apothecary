"""Apothecary's server: the FastAPI app the viewer and the CLI talk to.

This module renders scenes to OpenSCAD, serves the parts library and its STLs,
the sites and their nodes, and the one viewer page, and mounts the routers for
the docs, pictures, views, cameras, jobs, the slicer, part edits, firmware and
the ring's menus. ``/openapi.json`` lists every route.

STL files are generated on demand and not stored in git. On startup, missing
STLs are generated in the background when OpenSCAD is available.
"""

# An install point of the guard (apothecary/stays_local.py), before anything
# else here runs: `apothecary serve`, `uvicorn apothecary.api:app` and the docs
# generator's server all load this module, and from here on the process
# reaches nothing past this machine.
from .stays_local import install_guard as _install_guard

_install_guard()

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
from typing import Annotated, Any, Dict, List, Optional, Union
from urllib.parse import quote

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ValidationError

from . import jobs
from .core import OpenSCADObject
from .datum_core_site import create_datum_core_site, validate_datum_core
from .docs_site import router as docs_router
from .example_hierarchy import (
    PRINTER_STATUSES,
    create_example_site,
    validate_garage_layout,
)
from .example_parts_library import create_parts_library_site, validate_parts_library
from .firmware import devices as firmware_devices
from .firmware import gcode as firmware_gcode
from .firmware.api import _device_view as firmware_device_view
from .firmware.api import router as firmware_router
from .firmware.bindings import bindings_for_site, device_for_identity, same_device
from .firmware.models import DeviceAttachRequest, validate_port
from .firmware.toolchains import ToolchainError
from .hierarchy import Assembly
from .models.bounds import BoundingBox3D
from .models.vectors import Vector3D
from .primitives import Cube, Cylinder, Sphere, absolute_imports
from .projects.parts.base import BasePart
from .projects.parts.customizer import (
    Unlisted,
    customizer_spec,
    customizer_values,
    lists_parameters,
    part_check,
    without_initial,
)
from .projects.parts.drafts import editable
from .projects.parts.params import (
    FieldError,
    NoParameters,
    ParamsSpec,
    Validation,
    params_spec,
    validate_staged,
)
from .projects.parts.skeleton import ROOT
from .projects.parts.stl_renderer import RUNS, build_stl, geometry_scad, part_renderer, runs_for
from .projects.parts.stl_renderer import get_renderer as get_stl_renderer
from .projects.parts.variants import (
    KEY_PATTERN,
    PageRenders,
    PartState,
    VariantRecord,
    make_variant,
    measured_box,
    part_state,
    read_partial,
    read_variant,
    read_variant_draft,
    variant_paths,
    variant_record,
)
from .projects.parts.variants import wants as request_wants
from .projects.registry import ProjectInfo, _sanitize_module_name, scan_projects
from .routes.cameras import router as cameras_router
from .routes.jobs import router as jobs_router
from .routes.part_edits import router as part_edits_router
from .routes.pictures import router as pictures_router
from .routes.views import router as views_router
from .scene import Scene
from .site_store import SiteStore, UnknownSiteError
from .slicer import service as slicing
from .slicer.api import router as slicer_router
from .slicer.models import Made as SlicedMade
from .slicer.models import SlicedFor
from .slicer.modules import SlicerError
from .slicer.profiles import Declared
from .stays_local import LocalOnly
from .templates import TemplateRenderer
from .transforms import Translate
from .viewer import render_fractal_viewer_page
from .vocabulary.word import WORD_PRINT_SETTINGS_STUB


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
# Site panel's tree and its SCAD come up empty together while the static
# markup still reads "Layout valid". Frontend dependencies are vendored per
# the house-stack record for the same reason.
STATIC_ROOT = Path(__file__).resolve().parent / "static"
# Personal data stays on this machine by the shape of the program: the app
# answers a client on loopback only and fences every page it sends
# (apothecary/stays_local.py). Outermost, so static files are under it too.
# Responses compressed for a client that takes gzip: JSON, SCAD, STLs and the
# vendored scripts. Inside LocalOnly, which stays outermost; an event stream and
# an image are left as they are (Starlette excludes them).
app.add_middleware(GZipMiddleware, minimum_size=1024, compresslevel=6)
app.add_middleware(LocalOnly)
app.mount("/static", StaticFiles(directory=STATIC_ROOT), name="static")
app.include_router(docs_router)
# Mounted before the photo routes below, so /photos/pictures and /photos/gather
# are matched before /photos/{name} can take "pictures" for a name. The router
# reaches back into this module only inside its handlers.
app.include_router(pictures_router)
# Views: a picture pinned at a place in a site, and the pieces made from its shapes.
app.include_router(views_router)
# Cameras: a camera part added to a site, aimed, told its device, removed.
app.include_router(cameras_router)
# Jobs: what the machines ran, of every kind; each is started by its machine's own route.
app.include_router(jobs_router)
# The slicer: its status and install, and a part or a made piece sliced for a printer.
app.include_router(slicer_router)
# A part's SCAD edited: drafts checked and rendered, and saves as variants in git.
app.include_router(part_edits_router)
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


_BOARDS: Dict[str, bool] = {}


def is_board(part_ref: Optional[str]) -> bool:
    """Whether a part is a board -- one the boards library tags ``board``, bought and
    pinned to, never printed: a printer's mainboard, a devkit. Asked once per part."""
    if not part_ref:
        return False
    if part_ref not in _BOARDS:
        try:
            _BOARDS[part_ref] = "board" in (_load_part_wrapper(part_ref).tags or [])
        except HTTPException:
            _BOARDS[part_ref] = False
    return _BOARDS[part_ref]


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
    own = editable(part)
    from .projects.parts.texts import is_overlaid

    overlaid = own and is_overlaid(part)
    metadata["files"] = {
        "scad": {
            "exists": part.source_file.exists(),
            "url": f"/parts/{part.name}/scad",
            # A part built by Python geometry shows the SCAD that geometry
            # generates, read-only; any other's SCAD is its source, to edit.
            "editable": own,
            "generated": not own,
            # A part in a submodule is edited as its overlay; its upstream read only.
            "overlay": overlaid,
            "upstream_url": f"/parts/{part.name}/upstream" if overlaid else None,
        },
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
def get_part_scad(
    name: str,
    params: Optional[str] = Query(None, max_length=10_000),
    variant: Optional[str] = Query(
        None, description="A cached variant's key: the SCAD it was rendered from"
    ),
):
    """The part's SCAD. A part built by Python geometry (the snowplow) answers the
    SCAD its geometry generates, for ``params`` (JSON) or its defaults, and says
    so (``X-Part-Scad: generated``): it is shown, never edited, and a draft of
    it is refused. Any other answers its SCAD file (``X-Part-Scad: source``).

    ``variant`` answers the SCAD a cached variant was rendered from: for a part
    built by Python geometry, what it generates for the variant's parameters
    (the parameters an Apply drew); for any other, the draft it was rendered
    from (``X-Part-Scad: draft``), else its own text with the values it was
    applied with written in (``values``; none: ``source``). 404 once the cache has
    let it go.

    A part whose SCAD is in a submodule (gridfinity) answers the text it is
    edited as: its overlay setting nothing, an include of the upstream file
    (``X-Part-Scad: overlay``, ``X-Part-Upstream`` naming that file, which
    ``GET /parts/{name}/upstream`` serves read only)."""
    part = _load_part_wrapper(name)
    if variant is not None:
        return _variant_scad(name, part, variant)
    if editable(part) and not params:
        from .projects.parts.texts import is_overlaid, own_text, upstream_path

        if is_overlaid(part):
            return PlainTextResponse(
                own_text(part),
                headers={
                    "X-Part-Scad": "overlay",
                    "X-Part-Upstream": upstream_path(part),
                },
            )
    if not editable(part):
        overrides: Dict[str, Any] = {}
        if params:
            try:
                overrides = part.validate_overrides(json.loads(params))
            except (ValueError, TypeError, AttributeError) as exc:
                raise HTTPException(status_code=422, detail=f"Invalid params: {exc}") from None
        return PlainTextResponse(
            geometry_scad(part, overrides), headers={"X-Part-Scad": "generated"}
        )
    if params:
        raise HTTPException(
            status_code=422,
            detail=f"{name}'s SCAD is its source; parameters reach it as -D, not in its text",
        )
    try:
        return PlainTextResponse(
            part.source_file.read_text(encoding="utf-8"), headers={"X-Part-Scad": "source"}
        )
    except OSError as exc:  # pragma: no cover - IO failure is rare
        raise HTTPException(status_code=500, detail=f"Failed to read SCAD: {exc}") from exc


@app.get("/parts/{name}/upstream", response_class=PlainTextResponse)
def get_part_upstream(name: str):
    """A part in a submodule: its upstream SCAD, read only (``X-Part-Scad:
    upstream``), which its overlay includes and sets values after. 404 for a
    part in no submodule: its SCAD is ``GET /parts/{name}/scad``."""
    from .projects.parts.texts import is_overlaid

    part = _load_part_wrapper(name)
    if not editable(part) or not is_overlaid(part):
        raise HTTPException(
            status_code=404,
            detail=f"{name} is in no submodule: its SCAD is GET /parts/{name}/scad",
        )
    return PlainTextResponse(
        part.source_file.read_text(encoding="utf-8"),
        headers={"X-Part-Scad": "upstream", "Cache-Control": "no-cache"},
    )


def _variant_scad(name: str, part: BasePart, key: str) -> PlainTextResponse:
    record = read_variant(part, key) if KEY_PATTERN.match(key) else None
    if record is None:
        raise HTTPException(
            status_code=404,
            detail=f"No variant '{key}' of '{name}' is cached; "
            f"POST /parts/{name}/stl/generate makes it",
        )
    headers = {"X-Part-Variant": key}
    if not editable(part):
        try:
            overrides = part.validate_overrides(record.get("params") or {})
        except (ValueError, TypeError) as exc:
            raise HTTPException(status_code=422, detail=f"Invalid params: {exc}") from None
        return PlainTextResponse(
            geometry_scad(part, overrides), headers={**headers, "X-Part-Scad": "generated"}
        )
    text = read_variant_draft(part, key)
    if text is not None:
        return PlainTextResponse(text, headers={**headers, "X-Part-Scad": "draft"})
    from .projects.parts.texts import is_overlaid, own_text, with_params

    # The part's own text with the values it was applied with written in: what rendered.
    values = dict(record.get("params") or {})
    try:
        text = with_params(part, own_text(part), part.validate_overrides(values))
    except (ValueError, TypeError):
        text, values = own_text(part), {}
    kind = "overlay" if is_overlaid(part) else "source"
    return PlainTextResponse(text, headers={**headers, "X-Part-Scad": "values" if values else kind})


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


# What a page calls the state of its editor when it asks: a counter or a token,
# handed back as it came, so the page can tell an answer for older text.
EditorVersion = Optional[Union[int, Annotated[str, Field(max_length=64)]]]


class StlGenerateRequest(BaseModel):
    """Body for a parameterised STL generation."""

    params: Dict[str, Any] = Field(
        default_factory=dict,
        description="Parameter overrides, validated against the part's own model.",
    )
    editor_version: EditorVersion = Field(
        None,
        description="The page's own name for the state of its editor when it asked: "
        "handed back in the answer as it came",
    )


# The render each page has in flight per part, so a newer one can stop it.
_page_renders = PageRenders()

# What a variant's own URL is answered with: under its key its bytes never change.
IMMUTABLE = "public, max-age=31536000, immutable"


@app.post("/parts/{name}/stl/generate")
def generate_part_stl(
    name: str,
    force: bool = Query(False, description="Render even what the cache already has"),
    page: Optional[str] = Query(
        None,
        max_length=128,
        description="An id the page makes up once per load. A newer request from the "
        "same page for the same part stops this one's OpenSCAD run (409).",
    ),
    body: Optional[StlGenerateRequest] = None,
):
    """Render a part with ``params`` into the variant cache, and say what OpenSCAD said.

    ``params`` are checked against what the part declares (422 on an unknown
    name or a bad value). The cache is keyed by the SCAD and everything it
    reads, the parameters, the OpenSCAD and its backend
    (``apothecary/projects/parts/variants.py``): a request it already holds,
    or that the part's own STL already answers, renders nothing
    (``regenerated: false``) unless ``force``. ``stl_url`` is where the
    answer is: ``/parts/{name}/variants/{variant}/stl``, or the part's own
    STL. The defaults are also left as the part's own STL, unless its params
    sidecar says it holds another variant; any other variant is the cache's
    alone, so two pages applying different values never share a file.

    For a part whose SCAD is its source, the values are written into its own
    text (its SCAD, or a part in a submodule's overlay), and that text renders,
    as a draft does (``POST /parts/{name}/draft/render``): nothing is passed to
    OpenSCAD on the side. It is answered, and recorded, as the part with those
    values: ``params`` them, ``draft`` null; its key is that text's. A part
    built by Python geometry renders what its geometry generates for them.

    ``bounds`` is the envelope the part declares; ``measured`` is the box of
    what is served, in the same upright frame: OpenSCAD's own summary of the
    render where it writes one (``measured_from: "summary"``, a snapshot),
    else read off the STL (``"stl"``: 2021.01, or the part's own STL built
    elsewhere). ``saved`` says the answer is what the part's own STL holds.
    ``messages`` are its errors and warnings by file and line. A render
    OpenSCAD refused, or finished saying an error, is a 422 whose ``detail``
    carries them, and ``partial``: the geometry a snapshot wrote before the
    error (``stl_url`` under ``/parts/{name}/partials/``, the error's ``file``
    and ``line``, its ``measured`` box), or null; it is never a variant. One
    superseded by a newer request from the same ``page`` is a 409. No OpenSCAD, or a
    part that cannot be built on this machine, is a 503.
    """
    part = _load_part_wrapper(name)
    with runs_for(part.name, page):
        listing = _listing(part)
    overrides = checked_overrides(part, body.params if body else None, listing)
    if not get_stl_renderer().is_available:
        raise HTTPException(
            status_code=503, detail="OpenSCAD not installed. Cannot generate STL files."
        )
    if editable(part):
        # The text is the truth: the values are written into the part's own
        # text, which is what renders -- one path with a draft's render.
        from .projects.parts.texts import own_text, with_params
        from .routes.part_edits import render_text

        text = with_params(part, own_text(part), overrides)
        version = body.editor_version if body else None
        return render_text(self_api(), name, part, text, force, page, version, values=overrides)

    cancel = _page_renders.begin(part.name, page, request_wants(overrides, force))
    try:
        with runs_for(part.name, page):
            made = make_variant(part, overrides, force=force, cancel=cancel)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    finally:
        _page_renders.end(part.name, page, cancel)
    return made_answer(name, part, made, overrides, body.editor_version if body else None)


@app.get("/openscad/runs", tags=["parts"])
def openscad_runs(
    page: Optional[str] = Query(
        None, max_length=128, description="Only this page's runs (the id it sends with each)"
    ),
):
    """The queue of OpenSCAD runs: at most ``limit`` run at once (two; see
    apothecary/projects/parts/stl_renderer.py's ``RUNS``) and the rest wait,
    first come first served. ``running``: each run's ``kind`` (``render``, or
    the export a check or compile makes: ``param``, ``echo``, ``csg``), its
    ``part`` and ``page``, how long it has run; ``waiting``: the same, with its
    ``position`` (1: next) and how long it has waited. What a page polls while
    its render or check is in flight, to say it is queued. A cancelled request
    leaves the line without running."""
    return RUNS.snapshot(page)


def self_api():
    """This module, for a route elsewhere that answers as it does."""
    import sys

    return sys.modules[__name__]


def _listing(part: BasePart) -> Optional[List[Dict[str, Any]]]:
    """What OpenSCAD's customizer lists in a part's SCAD, for a part without a
    Python model; None for a part with one, or where the OpenSCAD lists nothing."""
    if part.params_model is not None or not editable(part):
        return None
    renderer = part_renderer(part)
    if not renderer.is_available or not lists_parameters(renderer.openscad_path):
        return None
    return part_check(part, renderer).parameters


def checked_overrides(
    part: BasePart,
    params: Optional[Dict[str, Any]],
    listing: Optional[List[Dict[str, Any]]],
    scad_text: Optional[str] = None,
) -> Dict[str, Any]:
    """A request's parameters as the part takes them, or a 422 saying why not.

    A part with a model has them checked by it. One without has them checked
    against what its SCAD's customizer lists (``listing``: of a draft, when
    ``scad_text`` is one), where OpenSCAD lists it -- a number as a number, a
    choice one of its options -- and a value the SCAD itself assigns is no
    override; else only their names, against its top-level variables."""
    if part.params_model is None and listing is not None and params:
        values, errors = customizer_values(listing, params)
        if errors:
            raise HTTPException(
                status_code=422, detail="; ".join(f"{e.field}: {e.message}" for e in errors)
            )
        params = without_initial(listing, values)
    try:
        return part.validate_overrides(params, scad_text=scad_text)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None


def partial_answer(name: str, partial) -> Optional[Dict[str, Any]]:
    """A failed render's partial geometry as an answer names it: where it is
    served, and the error it is flagged with. None where OpenSCAD wrote none."""
    if partial is None:
        return None
    return {
        "stl_url": f"/parts/{name}/partials/{partial.key}/stl",
        "message": partial.message,
        "file": partial.file,
        "line": partial.line,
        "measured": jsonable_encoder(measured_box(partial.measured)),
        "measured_from": partial.measured_from,
    }


def made_answer(
    name: str,
    part: BasePart,
    made,
    overrides: Dict[str, Any],
    editor_version: Optional[Union[int, str]] = None,
    shown_params: Optional[Dict[str, Any]] = None,
    text: Optional[str] = None,
) -> Dict[str, Any]:
    """What a render answers, as generate answers it, or the HTTPException for
    one that made nothing: 503 refused, 409 superseded, 422 with OpenSCAD's
    errors by line, 500 for a failure it said nothing about. Any error
    OpenSCAD said fails the render, even one it finished: a snapshot exits 0
    after a failed ``assert`` with the geometry built before it, which the
    422's ``partial`` names (``stl_url``, the error's ``file`` and ``line``),
    to be drawn greyed; it is never a variant. ``editor_version`` is handed
    back as the request gave it, in an answer and in a 409's or 422's
    ``detail``: what the page's editor held when it asked."""
    messages = jsonable_encoder(made.messages)
    if made.failure == "refused":
        raise HTTPException(
            status_code=503, detail=f"Cannot generate STL for '{name}': {made.error_message}"
        )
    if made.failure == "cancelled":
        raise HTTPException(
            status_code=409,
            detail={
                "message": made.error_message,
                "superseded": True,
                "editor_version": editor_version,
            },
        )
    if made.failure is not None:
        said = any(m.level == "error" for m in made.messages)
        detail: Dict[str, Any] = {
            "message": f"STL generation failed: {made.error_message}",
            "messages": messages,
            "partial": partial_answer(name, made.partial),
            "editor_version": editor_version,
        }
        raise HTTPException(status_code=422 if said else 500, detail=detail)

    return {
        "success": True,
        "message": (
            f"STL generated in {made.render_time_seconds:.1f}s"
            if made.rendered
            else (
                f"Compiled the same as variant {made.compiled_from}: nothing to render"
                if made.compiled_from
                else "STL is up to date (force=true rebuilds it)"
            )
        ),
        "stl_url": (f"/parts/{name}/variants/{made.key}/stl" if made.key else f"/parts/{name}/stl"),
        "variant": made.key,
        "regenerated": made.rendered,
        "render_time_seconds": made.render_time_seconds,
        "params": jsonable_encoder(made.params if shown_params is None else shown_params),
        "bounds": jsonable_encoder(part.get_bounds(overrides or None)),
        "measured": jsonable_encoder(measured_box(made.measured)),
        "measured_from": made.measured_from,
        "saved": made.saved,
        "messages": messages,
        "openscad": made.openscad,
        "backend": made.backend,
        # The sha256 of the draft it was rendered from; None: the part's own SCAD.
        "draft": made.draft,
        # What the page's editor held when it asked, as the page named it.
        "editor_version": editor_version,
        # The variant whose render this is too: it compiled the same.
        "compiled_from": made.compiled_from,
        # How long it waited for its turn among OpenSCAD's runs (GET /openscad/runs).
        "queued_seconds": round(made.queued_seconds, 3),
        # The text rendered, where values sent on the side were written into it.
        "text": text,
    }


@app.get("/parts/{name}/variants/{variant}", response_model=VariantRecord)
def get_part_variant(name: str, variant: str):
    """What made one cached variant: its parameters, OpenSCAD and backend, its
    measured bounds and what OpenSCAD said, and its ``stl_url``. A page that
    has only the key (a reloaded tab, a link) starts its editor from these.
    404 once the cache has let it go."""
    part = _load_part_wrapper(name)
    record = variant_record(part, variant, url_name=name) if KEY_PATTERN.match(variant) else None
    if record is None:
        raise HTTPException(
            status_code=404,
            detail=f"No variant '{variant}' of '{name}' is cached; "
            f"POST /parts/{name}/stl/generate makes it",
        )
    return record


@app.get("/parts/{name}/variants/{variant}/stl")
def get_part_variant_stl(name: str, variant: str):
    """One variant from the cache, by the ``variant`` key generate answered.

    Its bytes never change under its key, whichever page asks: what a page
    applied is what it draws, and the browser keeps it as immutable. 404 once
    the cache has let it go (it keeps the most recently served of each part);
    generating it again puts it back.
    """
    part = _load_part_wrapper(name)
    if not KEY_PATTERN.match(variant) or read_variant(part, variant) is None:
        raise HTTPException(
            status_code=404,
            detail=f"No variant '{variant}' of '{name}' is cached; "
            f"POST /parts/{name}/stl/generate makes it",
        )
    stl, _ = variant_paths(part, variant)
    try:
        data = stl.read_bytes()
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Variant '{variant}' was let go") from None
    return Response(
        content=data,
        media_type="application/sla",
        headers={
            "Content-Disposition": f'attachment; filename="{name}-{variant}.stl"',
            # A key is everything that made it: its bytes never change under it.
            "Cache-Control": IMMUTABLE,
            "X-Part-Name": name,
            "X-Part-Variant": variant,
        },
    )


@app.get("/parts/{name}/partials/{variant}/stl")
def get_part_partial_stl(name: str, variant: str):
    """What a failed render wrote before its error, to be drawn greyed: the
    ``partial.stl_url`` of a 422 from generate or a draft's render. Never a
    variant and never cached by the browser (a render of the same request
    that fails again writes it again); 404 once a newer failure has let it go."""
    part = _load_part_wrapper(name)
    path = read_partial(part, variant)
    try:
        data = path.read_bytes() if path is not None else None
    except OSError:
        data = None
    if data is None:
        raise HTTPException(
            status_code=404, detail=f"No partial geometry '{variant}' of '{name}' is kept"
        )
    return Response(
        content=data,
        media_type="application/sla",
        headers={
            "Content-Disposition": f'attachment; filename="{name}-{variant}-failed.stl"',
            "Cache-Control": "no-store",
            "X-Part-Name": name,
            "X-Part-Partial": variant,
        },
    )


@app.get("/parts/{name}/state", response_model=PartState)
def get_part_state(name: str):
    """What the part's own STL is, from its params sidecar.

    The parameters it was rendered with (empty: the defaults), when, and
    whether it is newer than everything it is built from: what a page drawing
    ``/parts/{name}/stl`` starts its editor from, rather than the model's
    defaults. ``apothecary parts generate-stl -p`` is what writes a variant
    there; the page's own Apply only ever leaves the defaults there.
    ``can_build`` says whether an OpenSCAD here can build the part at all, and
    ``build_note`` why not.
    """
    part = _load_part_wrapper(name)
    can, why = part.can_generate_stl()
    return part_state(part, url_name=name).model_copy(
        update={"can_build": can, "build_note": why or None}
    )


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

    A part without a Python model answers its SCAD's own parameters, as
    OpenSCAD's customizer lists them (``source: "customizer"``,
    apothecary/projects/parts/customizer.py): numbers with the ranges the SCAD
    gives, booleans, strings, choices and vectors. Where it has none to give,
    the 404's ``detail`` says why: ``lists`` false when the OpenSCAD in use
    (``openscad``, 2021.01) cannot list a SCAD's parameters at all, and
    ``messages`` when it could not read the SCAD.

    ``can_build`` says up front whether an OpenSCAD here can build the part
    (gridfinity cannot on 2021.01), and ``build_note`` why not: Apply is
    refused (a 503) where it is false.
    """
    part = _load_part_wrapper(name)
    try:
        return buildable(part, params_spec(part))
    except NoParameters:
        pass
    try:
        return buildable(part, customizer_spec(part))
    except Unlisted as why:
        raise HTTPException(
            status_code=404,
            detail={
                "message": str(why),
                "openscad": why.openscad,
                "lists": why.lists,
                "messages": jsonable_encoder(why.messages),
            },
        ) from None


def buildable(part: BasePart, spec: ParamsSpec) -> ParamsSpec:
    """``spec`` with whether an OpenSCAD here can build the part, and why not."""
    can, why = part.can_generate_stl()
    return spec.model_copy(update={"can_build": can, "build_note": why or None})


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


def drawn_variant(part: BasePart, key: str):
    """The cached variant ``key`` of ``part`` as the checklist asks about it, or
    a 404 once the cache has let it go (or never had it)."""
    from .projects.parts.readiness import Drawn

    record = read_variant(part, key) if KEY_PATTERN.match(key or "") else None
    if record is None:
        raise HTTPException(
            status_code=404,
            detail=f"No variant '{key}' of '{part.name}' is cached; "
            f"POST /parts/{part.name}/stl/generate makes it",
        )
    stl, _ = variant_paths(part, key)
    measured = record.get("measured")
    if not measured:
        from .projects.parts.variants import measure_stl

        measured = measure_stl(stl, part.display_rotation.to_list())
    return Drawn(
        key=key,
        stl=stl,
        params=dict(record.get("params") or {}),
        measured=measured,
        draft=record.get("draft"),
    )


def pinned_build_volume(site_name: str, printer: Optional[str] = None):
    """The build volume of the printer pinned in ``site_name``: ``printer``'s,
    the path of one of them, or the one there is. ``(size, where)``, or
    ``(None, (detail, fix))`` saying why there is none to take."""
    pinned = printers_in(site_name)
    if printer is not None:
        if printer not in pinned:
            named = ", ".join(pinned) or "none"
            return None, (
                f"{printer} is no printer pinned in {site_name} (pinned: {named})",
                f"pin {printer}'s board in {site_name}, or name a pinned printer",
            )
        chosen = printer
    elif len(pinned) == 1:
        chosen = pinned[0]
    elif not pinned:
        return None, (
            f"no printer is pinned in {site_name}",
            f"pin a printer's board in {site_name} (its Pin), or give a build volume",
        )
    else:
        return None, (
            f"{len(pinned)} printers are pinned in {site_name}: {', '.join(pinned)}",
            "name the one to print on (printer=<path>)",
        )
    node = _find_node_by_path(_site_store.get(site_name), chosen)
    volume = getattr(node, "build_volume", None) if node is not None else None
    if volume is None:
        return None, (
            f"{chosen} in {site_name} declares no build volume",
            "give its node a build_volume",
        )
    return (volume.x, volume.y, volume.z), f"{chosen} in {site_name}"


@app.get("/parts/{name}/checklist")
def get_part_checklist(
    name: str,
    build_volume: Optional[str] = Query(None, description="X,Y,Z in mm"),
    variant: Optional[str] = Query(
        None, description="A cached variant's key: the checklist of what a page draws"
    ),
    site: Optional[str] = Query(
        None, max_length=64, description="Take the build volume of the printer pinned here"
    ),
    printer: Optional[str] = Query(
        None, max_length=200, description="Which pinned printer, where the site has several"
    ),
):
    """Whether this part is ready to print and check against a real one.

    The same assessment `apothecary parts checklist` prints, so the viewer and
    the command line cannot disagree about whether something is buildable.
    A question that could not be asked is reported as `unknown`, never as a
    pass.

    ``variant`` asks about a variant from the cache (``/parts/{name}/variants/
    {key}``), as a page draws it: its render, its measured size against the
    bounds declared for its parameters, and whether that size fits (404 once
    the cache has let it go). Without ``build_volume``, ``site`` takes the
    build volume of the printer pinned there (``printer`` names one where
    several are): ``build_volume`` in the answer says the size and where it
    came from, and "Fits the printer" says why when there is none.
    """
    from .projects.parts.readiness import NO_VOLUME, assess

    part = _load_part_wrapper(name)
    drawn = drawn_variant(part, variant) if variant else None
    volume, source, none = _parse_build_volume(build_volume), "given", NO_VOLUME
    if volume is None and site:
        if site not in _site_store.names():
            raise HTTPException(status_code=404, detail=f"Site '{site}' not found")
        found, said = pinned_build_volume(site, printer)
        if found is None:
            none = said
        else:
            volume, source = found, said

    report = assess(part, build_volume=volume, drawn=drawn, volume_from=source, no_volume=none)
    return {
        "part": report.part,
        "variant": drawn.key if drawn else None,
        "ready": report.ready,
        "blocked": len(report.blocked),
        "unknown": len(report.unknown),
        "build_volume": ({"size": list(volume), "from": source} if volume is not None else None),
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
    nothing. A part without a model is checked against what its SCAD's
    customizer lists, where OpenSCAD lists it, else by its names alone.
    """
    part = _load_part_wrapper(name)
    params = body.params if body else {}
    if part.params_model is not None:
        return validate_staged(part, params)
    return validate_without_model(part, params, _listing(part))


def validate_without_model(
    part: BasePart,
    params: Dict[str, Any],
    listing: Optional[List[Dict[str, Any]]],
    scad_text: Optional[str] = None,
) -> Validation:
    """A staged set of a part without a model, checked against ``listing`` (what
    the customizer lists in its SCAD, or in the draft ``scad_text``) where
    there is one, else its names against the SCAD's top-level variables."""
    if listing is not None:
        values, errors = customizer_values(listing, params)
        if errors:
            return Validation(valid=False, errors=errors)
        return Validation(valid=True, params=values, bounds=part.get_bounds())
    try:
        values = part.validate_overrides(params, scad_text=scad_text)
    except ValueError as exc:
        return Validation(valid=False, errors=[FieldError(field="params", message=str(exc))])
    return Validation(valid=True, params=values, bounds=part.get_bounds())


# =============================================================================
# Site/Structure/Substructure/Feature hierarchy (prototype, unratified)
#
# Backed by a process-lifetime SiteStore: edits persist across requests,
# unlike /render's stateless Scene handling. site_store.py says what it keeps
# across a restart and what it does not share between worker processes.
#
# Routes that change a site stay `async def`: they run one at a time on the
# event loop, which is all that serializes the store's plain dicts until it
# has a lock. Routes that only read, and do filesystem, parse or
# render work, are plain `def` and run on the threadpool.
# =============================================================================

_site_store = SiteStore(
    {
        "garage": (create_example_site, validate_garage_layout),
        "parts_library": (create_parts_library_site, validate_parts_library),
        "datum_core": (create_datum_core_site, validate_datum_core),
    }
)
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
    Rotate, Scale, multiple children): the viewer draws those from the STL
    the server renders of the node's subtree
    (``GET /sites/{name}/nodes/{path}/stl``).
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
        drawn = {"type": "cylinder", "h": obj.h, "r1": r1, "r2": r2, "bounds": _bounds_dict(bounds)}
        # Its facets, when it names them: a wedge is a cylinder of three, and drawn
        # without them it was a round cone.
        if obj.fn:
            drawn["fn"] = obj.fn
        return drawn

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

    Unlike ``_structure_summary`` (the root's direct children and one level
    below them, in the payload's ``structures``), this walks the *whole*
    tree -- the shape the fractal zoom viewer needs to navigate unbounded
    depth. ``children``, ``additions``, and ``subtractions`` are all real
    Assembly nodes (a garage printer's ``left_post``/``gantry_bar`` Features
    are additions, not children), so all three are combined into one
    navigable ``children`` list here, each tagged with how it composes into
    its parent's geometry -- navigation doesn't care about that distinction,
    but a viewer showing "what's inside" vs. "what's added/removed" might.

    ``Assembly.world_bounds()`` only offsets by *this* node's own
    ``position`` -- correct for a direct child of the root, wrong for
    anything deeper, since a node's ``position`` is relative to its
    immediate parent, not the root. A Structure two levels down from the
    site root would render as if its parent were sitting at the origin. ``parent_world_position``
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
        # A board (a printer's mainboard, a devkit): where a printer's Pin puts its port.
        "board": is_board(node.part_ref),
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
    moved; everything else keeps its current persisted position. A camera
    moved here has its record follow, so it stands there after a restart.
    """
    from .vision.cameras import follow

    site = _get_site_or_404(name)
    for structure in site.children:
        override = body.positions.get(structure.name)
        if override is not None:
            structure.position = Vector3D(x=override.x, y=override.y, z=override.z)
    follow(name, site)

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
    """Discard all edits and rebuild the site fresh from its factory."""
    _get_site_or_404(name)  # validates the name before resetting
    site = _site_store.reset(name)
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
    stl_data, node = _node_stl(name, path)
    return Response(
        content=stl_data,
        media_type="application/sla",
        headers={"Content-Disposition": f'attachment; filename="{node.name}.stl"'},
    )


def _node_stl(name: str, path: str) -> tuple[bytes, Assembly]:
    """One node's STL and the node, as ``get_node_stl`` serves it -- the slicer
    slices a made piece from it too. Raises the HTTPException that route answers."""
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
    return stl_data, node


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
    on -- what the viewer's marks for a printer (``machine_marks.js``) are
    made from, and what a printer's Machine sizes its corner moves by.
    ``board`` is ``None`` when nothing is pinned.
    """
    pinned = _pinned_at(port)
    if pinned is None:
        return {"port": port, "site": None, "board": None, "printer": None}
    name, site, path = pinned
    node = _find_node_by_path(site, path)
    bearer_path = status_bearer_for(site, path) or path
    bearer = _find_node_by_path(site, bearer_path) or node
    return {
        "port": port,
        "site": name,
        "board": _describe_for_view(site, path, node, is_printer=False),
        "printer": (
            _describe_for_view(site, bearer_path, bearer, is_printer=True)
            if bearer_path != path
            else None
        ),
    }


def _pinned_at(port: str) -> Optional[tuple[str, Assembly, str]]:
    """Where the board on ``port`` is pinned: its site's name, the site, and the
    pinned node's path -- the first pin naming it whose site and node exist.

    Every pin, not just the loaded sites': a link to a board's Machine is often
    the first page opened after the server starts, and a pin names its site.
    """
    state = firmware_devices.get_state()
    known = firmware_devices.known_device(port, state)
    for binding in state.bindings():
        if not same_device(binding.identity, port, known):
            continue
        if binding.site not in _site_store.names():
            continue
        try:
            site = _site_store.get(binding.site)
        except KeyError:  # forgotten, or its picture left the shelf, since names()
            continue
        if _find_node_by_path(site, binding.path) is None:
            continue
        return binding.site, site, binding.path
    return None


def _parts_of(site_name: str, site: Assembly, leave_out: str) -> List[jobs.JobPart]:
    """What a job in ``site`` can name as the part it makes, by path: every node
    built from a part (named for its ``part_ref``) and every piece made from a
    picture (named for its word, with the picture and the camera it came from),
    but nothing at or under ``leave_out`` -- the machine itself. Holes cut from a
    piece are not things made."""
    from .vision import views as viewing

    made = viewing.store().made_at(site_name)
    found: Dict[str, jobs.JobPart] = {}

    def visit(node: Assembly, prefix: str) -> None:
        for child in [*node.children, *node.additions]:
            path = f"{prefix}.{child.name}" if prefix else child.name
            if path == leave_out or path.startswith(leave_out + "."):
                continue
            if child.part_ref:
                found[path] = jobs.JobPart(path=path, name=child.part_ref)
            elif not prefix and child.name in made:
                record = made[child.name]
                found[path] = jobs.JobPart(
                    path=path, name=record.word, picture=record.picture, camera=record.camera
                )
            visit(child, path)

    visit(site, "")
    return [found[path] for path in sorted(found)]


def _place_of(port: str) -> Optional[jobs.Place]:
    """Where the machine on ``port`` stands, for a job it starts (``jobs.PLACES``)."""
    pinned = _pinned_at(port)
    if pinned is None:
        return None
    name, site, path = pinned
    bearer = status_bearer_for(site, path) or path
    return jobs.Place(site=name, path=path, parts=_parts_of(name, site, leave_out=bearer))


jobs.PLACES.append(_place_of)


# -- what the slicer slices, and for which printer (apothecary/slicer/service.py) --


def _slice_target(site_name: str, path: str) -> Optional[slicing.Target]:
    """A node of a site, to slice: a part standing there (its part, at its
    defaults), or a piece made from a picture (its node's render, declaring no
    print settings). None for anything else."""
    from .vision import views as viewing

    try:
        site = _site_store.get(site_name)
    except KeyError:  # an UnknownSiteError, or forgotten since
        return None
    node = _find_node_by_path(site, path)
    if node is None:
        return None
    if node.part_ref:
        return slicing.part_target(node.part_ref, site=site_name, path=path)
    made = viewing.store().made_at(site_name)
    if "." in path or node.name not in made:
        return None

    def stl(log) -> bytes:
        try:
            data, _node = _node_stl(site_name, path)
        except HTTPException as exc:
            raise SlicerError(
                f"the piece {node.name} could not be rendered: {exc.detail}"
            ) from None
        log(f"STL: the piece {node.name}, rendered as its node is")
        return data

    return slicing.Target(
        made=SlicedMade(
            kind="piece", name=node.name, site=site_name, path=path, word=made[node.name].word
        ),
        # A word declaring print settings is a stub: the piece slices with the printer's.
        declared=Declared(
            by=f"piece {node.name}, made as {made[node.name].word}",
            note=WORD_PRINT_SETTINGS_STUB,
        ),
        stl=stl,
    )


def _printer_to_slice_for(
    port: Optional[str], site_name: Optional[str], path: Optional[str]
) -> Optional[SlicedFor]:
    """The printer a slice is for: the one ``port``'s pin stands under (the status
    bearer above the pinned board, as a print job's machine is), else ``site``'s
    node at ``path`` -- with no path, the site's one node built from a part that
    keeps a slicer profile; only a node built from a part."""
    if port:
        pinned = _pinned_at(port)
        if pinned is None:
            return None
        site_name, site, board = pinned
        path = status_bearer_for(site, board) or board
    else:
        if not site_name:
            return None
        try:
            site = _site_store.get(site_name)
        except KeyError:
            return None
        if not path:
            path = _the_printer_in(site_name, site)
            if path is None:
                return None
    node = _find_node_by_path(site, path)
    if node is None or not node.part_ref:
        return None
    return SlicedFor(part=node.part_ref, name=node.name, site=site_name, path=path, port=port)


def _the_printer_in(site_name: str, site: Assembly) -> Optional[str]:
    """The path of the one node of ``site`` built from a part that keeps a slicer
    profile; None for none, SlicerError naming them for several."""
    from .slicer.profiles import printers as keeping_profiles

    keeping = set(keeping_profiles())
    found: List[str] = []

    def visit(node: Assembly, prefix: str) -> None:
        for child in [*node.children, *node.additions]:
            path = f"{prefix}.{child.name}" if prefix else child.name
            if child.part_ref in keeping:
                found.append(path)
            visit(child, path)

    visit(site, "")
    if len(found) > 1:
        raise SlicerError(f"{site_name} has printers {', '.join(found)}: name one")
    return found[0] if found else None


slicing.TARGETS.append(_slice_target)
slicing.PRINTERS.append(_printer_to_slice_for)


def printers_in(site_name: str) -> List[str]:
    """The printers of ``site_name`` a print can go to: each node a board pinned in
    the site drives, when that node is a printer (it carries a printer's status),
    sorted. A made piece's Print offers them (``menu.py``)."""
    if site_name not in _site_store.names():
        return []
    try:
        site = _site_store.get(site_name)
    except KeyError:
        return []
    found = set()
    for binding in firmware_devices.get_state().bindings(site_name):
        bearer = status_bearer_for(site, binding.path)
        node = _find_node_by_path(site, bearer) if bearer else None
        if node is not None and node.status in PRINTER_STATUSES:
            found.add(bearer)
    return sorted(found)


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


def _sync_job_status(job: jobs.Job) -> None:
    """A job running on a machine marks the node its port is pinned to -- or the
    nearest above it that carries a status -- busy (its kind's ``busy``, "printing"
    for a print), and its end lets the node go back to idle.

    Registered on ``jobs.LISTENERS`` at import, beside the poll's sync: a running
    job, not a hand-typed one, is what makes a printer busy, from the moment it
    begins rather than at the next poll. A hand-set ``maintenance`` is the
    person's and is left alone, as a poll leaves it.
    """
    operation = jobs.operation(job.kind)
    if operation is None or operation.busy is None or not job.site or not job.machine.path:
        return
    if job.site not in _site_store.loaded():
        return
    site = _site_store.get(job.site)
    target = status_bearer_for(site, job.machine.path)
    node = _find_node_by_path(site, target) if target is not None else None
    if node is None or node.status == "maintenance":
        return
    if job.running:
        node.status = operation.busy
    elif node.status == operation.busy:
        node.status = "idle"


jobs.LISTENERS.append(_sync_job_status)


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
        # Whose link is held: a page may poll those without opening a port.
        "printers": links.open_ports,
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


def _default_site() -> str:
    """The site the viewer opens on when none is named: the garage, else the first."""
    names = _site_store.names()
    return DEFAULT_VIEWER_SITE if DEFAULT_VIEWER_SITE in names else names[0]


@app.get("/viewer")
async def viewer_home():
    """Redirect to the fractal zoom viewer for the first registered site.

    There is no longer a standalone parts browser or bare Site browser --
    both are absorbed into one viewer (see ``site_viewer`` below); this is
    just its default entry point.
    """
    return RedirectResponse(f"/viewer/sites/{_default_site()}", status_code=307)


# The firmware page and the printer monitor were pages of their own; they are
# the Bench and a board's Machine in front of the world now (the consolidation
# plan's Phase 5). Their links were handed out, so each still answers, with the
# viewer and the right panel open: the viewer reads ``panel`` and ``machine``
# from its address once the site's boards are known.


@app.get("/firmware", include_in_schema=False)
def firmware_page():
    """The firmware page is the Bench: the viewer, on the default site, with it open."""
    return RedirectResponse(f"/viewer/sites/{_default_site()}?panel=bench", status_code=307)


@app.get("/firmware/monitor", include_in_schema=False)
def monitor_page(port: str = ""):
    """The printer monitor is a board's Machine: the viewer on the site the port is
    pinned in, its Machine open there -- or, pinned nowhere, on the default site with
    its Machine open; either way the Machine is a tab of the rail's strip. A port of
    the wrong shape is dropped, as the page dropped it: the viewer opens with nothing
    in front of it."""
    try:
        validate_port(port) if port else None
    except ValueError:
        port = ""
    if not port:
        return RedirectResponse(f"/viewer/sites/{_default_site()}", status_code=307)
    pinned = _pinned_at(port)
    site = pinned[0] if pinned is not None else _default_site()
    return RedirectResponse(
        f"/viewer/sites/{quote(site, safe='')}?machine={quote(port, safe='')}", status_code=307
    )


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
            demo=_demo_folder(),
        )
    )


def _demo_folder() -> Optional[str]:
    """The demo's folder as the page's banner names it, when this is the demo."""
    from .demo import running, shown

    root = running()
    return shown(root) if root is not None else None


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
