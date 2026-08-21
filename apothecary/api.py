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
import os
from contextlib import asynccontextmanager, suppress
from importlib import import_module
from pathlib import Path
from random import choice
from typing import Any, Dict, List, Optional
from urllib.parse import quote

from fastapi import Body, FastAPI, HTTPException, Query, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ValidationError

from .booleans import Difference, Intersection, Union
from .core import OpenSCADObject
from .datum_core_site import create_datum_core_site, validate_datum_core
from .example_hierarchy import (
    PRINTER_STATUSES,
    Job,
    JobStore,
    create_example_site,
    job_fits_printer,
    validate_garage_layout,
)
from .example_parts_library import create_parts_library_site, validate_parts_library
from .hierarchy import Assembly
from .models.bounds import BoundingBox3D
from .models.vectors import Vector3D
from .primitives import Cube, Cylinder, Sphere
from .projects.parts.skeleton import ROOT
from .projects.parts.stl_renderer import get_renderer as get_stl_renderer
from .projects.parts.stl_renderer import write_params_sidecar
from .projects.registry import scan_projects
from .scene import Scene
from .site_store import SiteStore, UnknownSiteError
from .templates import TemplateRenderer
from .transforms import Rotate, Scale, Translate
from .viewer import render_fractal_viewer_page


async def _generate_missing_stls():
    """Generate STL files for all parts that don't have one.

    This runs at startup to ensure all parts have viewable STL files.
    STL files are not committed to git, so they need to be generated locally.
    """
    # Check if auto-generation is disabled
    if os.environ.get("APOTHECARY_SKIP_STL_GENERATION", "").lower() in ("1", "true", "yes"):
        print("STL generation skipped (APOTHECARY_SKIP_STL_GENERATION=1)")
        return

    renderer = get_stl_renderer()

    if not renderer.is_available:
        print("OpenSCAD not found - STL generation skipped")
        print("Install OpenSCAD to enable automatic STL generation")
        return

    parts = [p for p in scan_projects(ROOT) if p.kind == "part"]
    missing = []

    for part in parts:
        stl_path = part.path.with_suffix(".stl")
        if not stl_path.exists():
            missing.append(part)

    if not missing:
        return

    print(f"Generating {len(missing)} missing STL file(s)...")

    for part in missing:
        stl_path = part.path.with_suffix(".stl")
        print(f"  Generating {part.name}...", end=" ", flush=True)

        result = await renderer.render_stl_async(part.path, stl_path, timeout=120)

        if result.success:
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
    """Application lifespan handler - runs on startup and shutdown.

    STL generation for missing parts runs as a background task, not
    awaited here. Real OpenSCAD renders can take tens of seconds per part
    (CGAL boolean ops -- one part in this repo's own library takes ~39s),
    and _generate_missing_stls() renders every missing part sequentially;
    awaiting it here meant /health -- and every other route -- was
    unreachable until all of them finished, which starved every client
    that polls /health with a short timeout (apothecary test all,
    tests/e2e's --start-server fixture, and a plain first-run
    `apothecary serve` alike). Parts already handle "not generated yet"
    gracefully (placeholder geometry in the viewer, on-demand
    /parts/{name}/stl/generate), so backgrounding this is a strict
    improvement, not a behavior change callers need to adapt to.
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


def _vec(data):
    return Vector3D(x=data.get("x", 0), y=data.get("y", 0), z=data.get("z", 0))


def _rehydrate(obj_dict):
    """Best-effort reconstruction of OpenSCAD objects from a plain dict.

    Keeps logic intentionally minimal; adds a 'type' discriminator if present,
    otherwise infers by field set.
    """
    t = obj_dict.get("type")
    if t == "cube" or ("size" in obj_dict and isinstance(obj_dict.get("size"), dict)):
        size = obj_dict.get("size")
        size_val = _vec(size) if isinstance(size, dict) else size
        return Cube(
            size=size_val, center=obj_dict.get("center", False), comment=obj_dict.get("comment")
        )
    if t == "sphere" or "r" in obj_dict:
        return Sphere(
            r=obj_dict.get("r", 1.0), fn=obj_dict.get("fn"), comment=obj_dict.get("comment")
        )
    if t == "cylinder" or any(k in obj_dict for k in ("r", "r1", "r2")):
        return Cylinder(
            h=obj_dict.get("h", 1.0),
            r=obj_dict.get("r"),
            r1=obj_dict.get("r1"),
            r2=obj_dict.get("r2"),
            center=obj_dict.get("center", False),
            fn=obj_dict.get("fn"),
            comment=obj_dict.get("comment"),
        )
    if t in ("union", "difference", "intersection") or "children" in obj_dict:
        kids = [_rehydrate(k) if isinstance(k, dict) else k for k in obj_dict.get("children", [])]
        if t == "difference":
            return Difference(children=kids, comment=obj_dict.get("comment"))
        if t == "intersection":
            return Intersection(children=kids, comment=obj_dict.get("comment"))
        return Union(children=kids, comment=obj_dict.get("comment"))
    if t == "translate" and "v" in obj_dict:
        kids = [_rehydrate(k) if isinstance(k, dict) else k for k in obj_dict.get("children", [])]
        return Translate(v=_vec(obj_dict["v"]), children=kids, comment=obj_dict.get("comment"))
    if t == "rotate" and "a" in obj_dict:
        kids = [_rehydrate(k) if isinstance(k, dict) else k for k in obj_dict.get("children", [])]
        a = obj_dict["a"]
        a_val = _vec(a) if isinstance(a, dict) else a
        v = _vec(obj_dict["v"]) if isinstance(obj_dict.get("v"), dict) else None
        return Rotate(a=a_val, v=v, children=kids, comment=obj_dict.get("comment"))
    if t == "scale" and "v" in obj_dict:
        kids = [_rehydrate(k) if isinstance(k, dict) else k for k in obj_dict.get("children", [])]
        return Scale(v=_vec(obj_dict["v"]), children=kids, comment=obj_dict.get("comment"))
    # Fallback: produce a comment-only union wrapper for unknown structure
    return Union(children=[], comment="unrecognized object")


app = FastAPI(
    title="Apothecary API",
    version="0.1.0",
    description="Lean OpenSCAD generation toolkit exposed via FastAPI endpoints",
    lifespan=lifespan,
)

renderer = TemplateRenderer()


# =============================================================================
# Parts Registry Helpers
# =============================================================================


def _sanitize_part_name(name: str) -> str:
    """Convert part name to valid Python module name."""
    return name.lower().replace("-", "_").replace(" ", "_").replace(".", "_")


def _part_template() -> str:
    template_path = ROOT / "templates" / "part.include.scad.j2"
    if template_path.exists():
        return template_path.read_text(encoding="utf-8")
    return "// {{ part.name }}\ninclude <{{ source_posix }}>"


def _load_part_wrapper(name: str):
    module_name = _sanitize_part_name(name)
    full = f"apothecary.projects.parts.{module_name}"
    try:
        module = import_module(full)
    except ModuleNotFoundError as exc:  # pragma: no cover - error path
        raise HTTPException(status_code=404, detail=f"Part '{name}' not found") from exc
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

    # Check if this part has special STL generation requirements
    stl_can_generate = True
    stl_note = None
    if hasattr(part, "can_generate_stl"):
        stl_can_generate, stl_note = part.can_generate_stl()

    # Add file availability info
    metadata["files"] = {
        "scad": {"exists": part.source_file.exists(), "url": f"/parts/{part.name}/scad"},
        "jscad": {"exists": False, "url": f"/parts/{part.name}/jscad"},  # Generated on demand
        "stl": {
            "exists": part.stl_file is not None,
            "url": f"/parts/{part.name}/stl" if part.stl_file else None,
            "generate_url": f"/parts/{part.name}/stl/generate",
            "can_generate": stl_can_generate,
            "note": stl_note,
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


# The viewer's 3D library, served from this origin rather than a CDN. A CDN
# copy is unreachable offline and is exactly what an ad blocker or a corporate
# proxy drops -- and when it goes, the page's script never executes at all, so
# the canvas, the contents list and the code panel come up empty together while
# the static markup still reads "Layout valid". Frontend dependencies are
# vendored per the house-stack record for the same reason.
THREE_DIR = ROOT / "node_modules" / "three"
THREE_IS_VENDORED = (THREE_DIR / "build" / "three.module.js").is_file()
if THREE_IS_VENDORED:
    app.mount("/vendor/three", StaticFiles(directory=THREE_DIR), name="three")


@app.get("/")
async def root():
    """Root endpoint - redirects to the viewer."""
    return RedirectResponse("/viewer", status_code=307)


@app.get("/health")
async def health():
    """Health check endpoint"""
    return {"status": "healthy", "version": "0.1.0"}


@app.post("/render")
async def render_scene(scene: Scene):
    """Render a scene to OpenSCAD code.

    Attempts direct render; if underlying objects were deserialized without
    type info, rehydrate heuristically.
    """
    try:
        return {
            "success": True,
            "scene_name": scene.name,
            "code": scene.render(),
            "object_count": len(scene.objects),
        }
    except Exception:  # fallback path
        try:
            # FastAPI/Pydantic may coerce children into base-class instances or dicts.
            # Normalize everything to dicts and rehydrate best-effort.
            normalized = []
            for o in scene.objects:
                if isinstance(o, dict):
                    normalized.append(o)
                elif hasattr(o, "model_dump"):
                    try:
                        normalized.append(o.model_dump())
                    except Exception:  # pragma: no cover - defensive
                        normalized.append({})
                else:
                    normalized.append({})
            rebuilt = [_rehydrate(o) for o in normalized]
            scene.objects = rebuilt  # mutate for simplicity
            return {
                "success": True,
                "scene_name": scene.name,
                "code": scene.render(),
                "object_count": len(scene.objects),
                "rehydrated": True,
            }
        except Exception as e:  # pragma: no cover
            raise HTTPException(status_code=500, detail=f"render failed: {e}") from e


@app.post("/render/template")
async def render_scene_with_template(scene: Scene, template: str = Body("{{ scene_code }}")):
    """Render a scene using a Jinja2 template"""
    try:
        rendered_code = renderer.render_scene_template(scene, template)
        return {
            "success": True,
            "scene_name": scene.name,
            "code": rendered_code,
            "object_count": len(scene.objects),
        }
    except Exception:
        # Fallback: rehydrate best-effort like /render
        try:
            normalized = []
            for o in scene.objects:
                if isinstance(o, dict):
                    normalized.append(o)
                elif hasattr(o, "model_dump"):
                    normalized.append(o.model_dump())
                else:
                    normalized.append({})
            rebuilt = [_rehydrate(o) for o in normalized]
            scene.objects = rebuilt
            rendered_code = renderer.render_scene_template(scene, template)
            return {
                "success": True,
                "scene_name": scene.name,
                "code": rendered_code,
                "object_count": len(scene.objects),
                "rehydrated": True,
            }
        except Exception as e:  # pragma: no cover
            raise HTTPException(status_code=500, detail=str(e)) from e


@app.get("/parts")
async def list_parts():
    names = _available_part_names()
    return [_part_metadata(_load_part_wrapper(name)) for name in names]


@app.get("/parts/random")
async def random_part(params: str | None = Query(None, alias="params")):
    names = _available_part_names()
    if not names:
        raise HTTPException(status_code=404, detail="No parts available")
    picked = choice(names)
    payload = _part_payload(_load_part_wrapper(picked), params)
    payload["random_source"] = picked
    return payload


@app.get("/parts/random/scad", response_class=PlainTextResponse)
async def random_part_scad():
    names = _available_part_names()
    if not names:
        raise HTTPException(status_code=404, detail="No parts available")
    picked = choice(names)
    part = _load_part_wrapper(picked)
    try:
        return PlainTextResponse(
            part.source_file.read_text(encoding="utf-8"), headers={"x-part-name": part.name}
        )
    except OSError as exc:  # pragma: no cover - IO failure is rare
        raise HTTPException(status_code=500, detail=f"Failed to read SCAD: {exc}") from exc


@app.get("/parts/{name}")
async def get_part(name: str, params: str | None = Query(None, alias="params")):
    part = _load_part_wrapper(name)
    return _part_payload(part, params)


@app.get("/parts/{name}/scad", response_class=PlainTextResponse)
async def get_part_scad(name: str):
    part = _load_part_wrapper(name)
    try:
        return PlainTextResponse(part.source_file.read_text(encoding="utf-8"))
    except OSError as exc:  # pragma: no cover - IO failure is rare
        raise HTTPException(status_code=500, detail=f"Failed to read SCAD: {exc}") from exc


@app.get("/parts/{name}/jscad", response_class=PlainTextResponse)
async def get_part_jscad(name: str, params: str | None = Query(None, alias="params")):
    """Generate a JSCAD JavaScript module from a part's SCAD file.

    Since raw SCAD files can't be directly converted to JSCAD, this creates
    a simple JSCAD module with a placeholder shape and the SCAD code as documentation.
    """
    part = _load_part_wrapper(name)
    _, params_json = _normalize_params(part, params)

    try:
        scad_code = part.source_file.read_text(encoding="utf-8")
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Failed to read SCAD: {exc}") from exc

    # Create a JSCAD module with documentation
    jscad_code = f"""/**
 * {part.name}
 * @category {part.category or 'Parts'}
 * @description {part.description or 'No description'}
 * @tags {', '.join(part.tags) if part.tags else 'apothecary'}
 */

const jscad = require('@jscad/modeling')
const {{ cube, sphere }} = jscad.primitives
const {{ translate }} = jscad.transforms

// OpenSCAD source:
/*
{scad_code}
*/

const main = () => {{
    // Placeholder: display info about the part
    // The actual geometry would require OpenSCAD -> JSCAD conversion

    const info = cube({{ size: [50, 30, 2] }})
    const marker = translate([0, 0, 5], sphere({{ radius: 3 }}))

    return [info, marker]
}}

module.exports = {{ main }}
"""

    return PlainTextResponse(jscad_code, media_type="application/javascript")


@app.get("/parts/{name}/stl")
async def get_part_stl(name: str):
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
async def generate_part_stl(
    name: str,
    force: bool = Query(False),
    body: Optional[StlGenerateRequest] = None,
):
    """
    Generate an STL file from the part's SCAD source.

    Requires OpenSCAD to be installed on the server.

    Args:
        name: Part name
        force: If True, regenerate even if STL already exists
        params: Parameter overrides, validated against the part's own model
            before rendering. Supplying any implies a regeneration, since the
            STL on disk was rendered from something else.

    Returns:
        Generation status with download URL on success
    """
    part = _load_part_wrapper(name)
    renderer = get_stl_renderer()

    if not renderer.is_available:
        raise HTTPException(
            status_code=503, detail="OpenSCAD not installed. Cannot generate STL files."
        )

    # OpenSCAD accepts any -D name, defined or not, so an unrecognised
    # parameter would render the defaults and report success. Reject it here.
    params = body.params if body else {}
    overrides = {}
    if params:
        model_cls = getattr(part, "params_model", None)
        if model_cls is not None:
            unknown = sorted(set(params) - set(model_cls.model_fields))
            if unknown:
                raise HTTPException(
                    status_code=422,
                    detail=f"unknown parameter(s): {', '.join(unknown)}",
                )
            try:
                validated = model_cls(**params)
            except ValidationError as exc:
                raise HTTPException(status_code=422, detail=exc.errors()) from exc
            overrides = {key: getattr(validated, key) for key in params}
        else:
            overrides = dict(params)

    # Check if this part has special requirements
    if hasattr(part, "can_generate_stl"):
        can_gen, reason = part.can_generate_stl()
        if not can_gen:
            raise HTTPException(
                status_code=503, detail=f"Cannot generate STL for '{name}': {reason}"
            )

    # Check if we already have an up-to-date STL
    if not force and not overrides and part.stl_file and part.stl_file.exists():
        return {
            "success": True,
            "message": "STL already exists (use force=true to regenerate)",
            "stl_url": f"/parts/{name}/stl",
            "regenerated": False,
        }

    # Use part-specific OpenSCAD path if available (e.g., nightly build)
    part_renderer = renderer
    if hasattr(part, "get_openscad_path"):
        custom_path = part.get_openscad_path()
        if custom_path and custom_path != renderer.openscad_path:
            from apothecary.projects.parts.stl_renderer import OpenSCADRenderer

            part_renderer = OpenSCADRenderer(openscad_path=str(custom_path))

    # Generate STL - the part's own output path, and whatever overrides were
    # validated above; a part naming its own renderer must still honour them.
    stl_path = part.get_stl_output_path()
    result = await part_renderer.render_stl_async(
        part.source_file, stl_path, params=overrides or None
    )

    if not result.success:
        raise HTTPException(
            status_code=500, detail=f"STL generation failed: {result.error_message}"
        )

    write_params_sidecar(stl_path, overrides)

    return {
        "success": True,
        "message": f"STL generated successfully in {result.render_time_seconds:.1f}s",
        "stl_url": f"/parts/{name}/stl",
        "regenerated": True,
        "render_time_seconds": result.render_time_seconds,
        "params": jsonable_encoder(overrides),
        "bounds": jsonable_encoder(part.get_bounds(overrides or None)),
    }


@app.get("/parts/{name}/params")
async def get_part_params(name: str):
    """What a part accepts, in a form a control surface can build itself from.

    Types, defaults and bounds come from the part's own Pydantic model, so the
    dashboard cannot drift from what the renderer will actually accept.
    ``contested`` carries the parameters whose value this project's sources
    disagree about, with the provenance of each candidate -- an ambiguity a
    reader can turn is worth more than one they have to argue about.
    """
    part = _load_part_wrapper(name)
    model_cls = getattr(part, "params_model", None)
    if model_cls is None:
        raise HTTPException(status_code=404, detail=f"Part '{name}' declares no parameters")

    schema = model_cls.model_json_schema()
    defaults = model_cls()

    fields = []
    for field_name, spec in schema.get("properties", {}).items():
        default = getattr(defaults, field_name)
        candidates = [c.model_dump() for c in part.contested.get(field_name, [])]
        # A slider needs a range. Pydantic states one only where the field
        # constrains it, so the rest get a span around the default wide enough
        # to be worth dragging -- and wide enough to reach every candidate.
        interesting = [default, *(c["value"] for c in candidates)]
        low = spec.get("minimum")
        # gt=0 arrives as exclusiveMinimum, and a slider stopping exactly there
        # offers a value the model then refuses -- which is the one thing this
        # endpoint exists to prevent.
        exclusive_low = spec.get("exclusiveMinimum")
        high = spec.get("maximum")
        if not isinstance(default, (int, float)):
            low = high = None
        else:
            if low is None:
                low = float(exclusive_low) if exclusive_low is not None else None
            else:
                low = float(low)
            if low is None:
                low = max(0.0, min(interesting) * 0.25)
            high = max(interesting) * 2.5 if high is None else float(high)
            if exclusive_low is not None and low <= float(exclusive_low):
                # One slider step above the bound it may not touch.
                low = float(exclusive_low) + (high - float(exclusive_low)) / 200

        fields.append(
            {
                "name": field_name,
                "type": "enum" if spec.get("pattern") else ("number" if high else "text"),
                "default": default,
                "min": low,
                "max": high,
                "pattern": spec.get("pattern"),
                "description": spec.get("description"),
                "contested": candidates,
            }
        )

    return {
        "part": part.name,
        "description": part.description,
        "fields": fields,
        "bounds": jsonable_encoder(part.get_bounds()),
    }


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
async def get_part_checklist(name: str, build_volume: Optional[str] = Query(None)):
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


@app.get("/parts/{name}/files")
async def get_part_files(name: str, request: Request):
    """
    Get detailed file information for a part.

    Returns status and URLs for all file formats (SCAD, JSCAD, STL).
    """
    part = _load_part_wrapper(name)
    part_files = part.get_files()
    base_url = str(request.base_url).rstrip("/")

    return part_files.to_api_dict(base_url)


# =============================================================================
# Site/Structure/Substructure/Feature hierarchy (prototype, unratified)
#
# Backed by a process-lifetime SiteStore (see site_store.py): edits persist
# across requests, unlike /render's stateless Scene handling. Known
# limitation: in-memory only, lost on restart, not shared across worker
# processes -- fine for a single-process dev server.
# =============================================================================

_site_store = SiteStore(
    {
        "garage": (create_example_site, validate_garage_layout),
        "parts_library": (create_parts_library_site, validate_parts_library),
        "datum-core": (create_datum_core_site, validate_datum_core),
    }
)
_job_store = JobStore()

# The site /viewer opens on. Named rather than "whichever sorts first", so that
# registering a new site cannot silently move the front door.
DEFAULT_VIEWER_SITE = "garage"


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


_NODE_STL_CACHE_DIR = ROOT / ".cache" / "node_stl"


def _node_stl_cache_paths(scad_text: str) -> tuple[Path, Path]:
    """Content-hash-keyed cache location for a dynamically-addressed node's
    render. Unlike a registered part (which has a fixed source file to key
    off of), an arbitrary Assembly subtree has no path of its own on disk --
    the rendered SCAD text itself is the only stable identity available.

    A scene referring to registered parts imports them by repository-relative
    path, and OpenSCAD resolves a relative ``import()`` against the *source
    file's* own directory rather than the process working directory. So the
    source has to sit at the repository root to render at all, while the STL
    it produces belongs in the cache. It is scratch: written, rendered, removed.
    """
    digest = hashlib.sha256(scad_text.encode("utf-8")).hexdigest()[:20]
    return ROOT / f".node-stl-{digest}.scad", _NODE_STL_CACHE_DIR / f"{digest}.stl"


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
        size = obj.size if isinstance(obj.size, Vector3D) else Vector3D(x=obj.size, y=obj.size, z=obj.size)
        local_min = Vector3D(x=-size.x / 2, y=-size.y / 2, z=-size.z / 2) if obj.center else Vector3D()
        bounds = BoundingBox3D(min_point=local_min + offset, max_point=local_min + size + offset)
        return {"type": "cube", "size": [size.x, size.y, size.z], "bounds": _bounds_dict(bounds)}

    if isinstance(obj, Cylinder):
        r1 = obj.r if obj.r is not None else (obj.r1 if obj.r1 is not None else 1.0)
        r2 = obj.r if obj.r is not None else (obj.r2 if obj.r2 is not None else r1)
        max_r = max(r1, r2)
        z0 = -obj.h / 2 if obj.center else 0.0
        local_min = Vector3D(x=-max_r, y=-max_r, z=z0)
        local_max = Vector3D(x=max_r, y=max_r, z=z0 + obj.h)
        bounds = BoundingBox3D(min_point=local_min + offset, max_point=local_max + offset)
        return {"type": "cylinder", "h": obj.h, "r1": r1, "r2": r2, "bounds": _bounds_dict(bounds)}

    if isinstance(obj, Sphere):
        r = obj.r
        bounds = BoundingBox3D(
            min_point=Vector3D(x=-r, y=-r, z=-r) + offset, max_point=Vector3D(x=r, y=r, z=r) + offset
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
        "category": category,
        "position": {"x": world_position.x, "y": world_position.y, "z": world_position.z},
        "footprint": _bounds_dict(node.footprint),
        "world_bounds": _bounds_dict(world_bounds),
        "build_volume": (
            [node.build_volume.x, node.build_volume.y, node.build_volume.z]
            if node.build_volume
            else None
        ),
        "primitive": _primitive_descriptor(node.base, world_position) if node.base is not None else None,
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


@app.get("/sites")
async def list_sites():
    return _site_store.names()


@app.get("/sites/{name}")
async def get_site(name: str):
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
async def get_node_stl(name: str, path: str):
    """Render any addressable Assembly node's own subtree to STL, on demand.

    This is the real-geometry upgrade path for *composite* nodes in the
    fractal viewer (a wall with a window cutout, a whole Structure) --
    leaves already get exact primitives from ``_primitive_descriptor`` or,
    for parts-library leaves, ``/parts/{part_ref}/stl``; anything with
    nested booleans needs an actual CSG evaluation. Rather than a second,
    bespoke geometry engine, this reuses the same OpenSCAD CLI pipeline
    already serving ``/parts/{name}/stl`` -- the node's ``to_scad_object()``
    is exactly the OpenSCAD subtree the site's own render already produces
    for it, just rendered in isolation. Cached by content hash, since a
    dynamically-addressed node (unlike a registered part) has no fixed file
    path of its own to key a cache off of.
    """
    site = _get_site_or_404(name)
    node = _find_node_by_path(site, path)
    if node is None:
        raise HTTPException(status_code=404, detail=f"Node '{path}' not found in site '{name}'")

    try:
        scad_text = node.to_scad_object(strict=True).render()
    except ValueError as exc:
        raise HTTPException(
            status_code=422, detail=f"Node '{path}' has no renderable geometry: {exc}"
        ) from None

    scad_path, stl_path = _node_stl_cache_paths(scad_text)
    if not stl_path.exists():
        renderer = get_stl_renderer()
        if not renderer.is_available:
            raise HTTPException(
                status_code=503, detail="OpenSCAD not installed. Cannot generate STL files."
            )
        stl_path.parent.mkdir(parents=True, exist_ok=True)
        scad_path.write_text(scad_text, encoding="utf-8")
        try:
            result = await renderer.render_stl_async(scad_path, stl_path, timeout=60)
        finally:
            scad_path.unlink(missing_ok=True)
        if not result.success:
            raise HTTPException(
                status_code=500, detail=f"STL generation failed: {result.error_message}"
            )

    try:
        stl_data = stl_path.read_bytes()
        return Response(
            content=stl_data,
            media_type="application/sla",
            headers={"Content-Disposition": f'attachment; filename="{node.name}.stl"'},
        )
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Failed to read STL: {exc}") from exc


# -----------------------------------------------------------------------
# Jobs: capacity-checked assignment to printer Structures (manufacturing
# planning, first slice). See example_hierarchy.py's Job/JobStore.
# -----------------------------------------------------------------------


class Dimensions(BaseModel):
    x: float
    y: float
    z: float


class CreateJobRequest(BaseModel):
    name: str
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
async def list_jobs(name: str):
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

    if job.assigned_printer:
        printer = next((s for s in site.children if s.name == job.assigned_printer), None)
        if printer is not None:
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
async def site_viewer(name: str, request: Request, focus: str = Query(default="")):
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
async def part_view(name: str):
    """A part is reached by navigating to it, not by a second viewer.

    This deep-link survives because links to it were handed out, but it now
    lands in the one viewer, focused on the part, where the parameter controls
    and the contested values live. Two pages onto one object is how a codebase
    ends up with two answers about it.
    """
    _load_part_wrapper(name)  # 404 here rather than after a redirect
    return RedirectResponse(
        f"/viewer/sites/parts_library?focus={quote(name, safe='')}", status_code=307
    )


@app.get("/problems")
async def get_problems(
    owner: Optional[str] = Query(None, description="apothecary | datum | human | measurement"),
    kind: Optional[str] = Query(None),
    build_volume: Optional[str] = Query(None),
):
    """Every open question this repository can state, and who can close it.

    Derived from models that already exist -- contested values, the build
    checklist, layout validators, the black-box seam -- so it cannot drift from
    the repository the way a hand-maintained list does.
    """
    from .spaces import problems as open_problems

    volume = _parse_build_volume(build_volume)
    found = open_problems(build_volume=volume)
    if owner:
        found = [p for p in found if p.owner == owner]
    if kind:
        found = [p for p in found if p.kind == kind]
    return {"count": len(found), "problems": [p.to_dict() for p in found]}


@app.get("/solutions")
async def get_solutions(kind: Optional[str] = Query(None)):
    """What this repository offers against those problems."""
    from .spaces import capabilities

    found = capabilities()
    if kind:
        found = [c for c in found if c.kind == kind]
    return {"count": len(found), "capabilities": [c.to_dict() for c in found]}


@app.get("/spaces")
async def get_spaces(build_volume: Optional[str] = Query(None)):
    """Both spaces at a glance, and any problem kind nothing here addresses."""
    from .spaces import summary

    return summary(build_volume=_parse_build_volume(build_volume))


@app.get("/openscad/status")
async def openscad_status():
    """
    Check OpenSCAD availability and version.

    Returns information about the OpenSCAD installation used for STL generation.
    """
    renderer = get_stl_renderer()

    return {
        "available": renderer.is_available,
        "version": renderer.get_version(),
        "path": str(renderer.openscad_path) if renderer.openscad_path else None,
    }
