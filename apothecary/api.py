"""
Apothecary API - FastAPI endpoints for OpenSCAD generation toolkit.

This module provides REST API endpoints for:
- Scene rendering to OpenSCAD code
- Parts browsing and downloading
- 3D viewer for part preview

Note: STL files are generated on-demand and not stored in git.
On startup, missing STLs are automatically generated if OpenSCAD is available.
"""

import json
import os
from contextlib import asynccontextmanager
from importlib import import_module
from random import choice
from typing import Dict, List

from fastapi import Body, FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse, Response
from pydantic import BaseModel, Field, ValidationError

from .booleans import Difference, Intersection, Union
from .example_hierarchy import create_example_site, validate_garage_layout
from .hierarchy import Structure
from .models.bounds import BoundingBox3D
from .models.vectors import Vector3D
from .primitives import Cube, Cylinder, Sphere
from .projects.parts.skeleton import ROOT
from .projects.parts.stl_renderer import get_renderer as get_stl_renderer
from .projects.registry import scan_projects
from .scene import Scene
from .templates import TemplateRenderer
from .transforms import Rotate, Scale, Translate
from .viewer import render_site_viewer_page, render_viewer_page


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


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler - runs on startup and shutdown."""
    # Startup
    await _generate_missing_stls()
    yield
    # Shutdown (nothing to clean up)


def _vec(data):
    return Vector3D(x=data.get("x", 0), y=data.get("y", 0), z=data.get("z", 0))


def _rehydrate(obj_dict):
    """Best-effort reconstruction of OpenSCAD objects from a plain dict.
    Keeps logic intentionally minimal; adds a 'type' discriminator if present, otherwise infers by field set.
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
        "source_posix": part.source_file.as_posix(),
    }
    return renderer.render_template(template_str, ctx)


def _part_metadata(part) -> Dict[str, object]:
    metadata = {
        "name": part.name,
        "description": part.description,
        "category": part.category,
        "tags": part.tags,
        "readme": str(part.readme_path) if part.readme_path and part.readme_path.exists() else None,
        "source_file": part.source_file.as_posix(),
        "has_params": bool(part.params_model),
    }

    # Add file availability info
    metadata["files"] = {
        "scad": {"exists": part.source_file.exists(), "url": f"/parts/{part.name}/scad"},
        "jscad": {"exists": False, "url": f"/parts/{part.name}/jscad"},  # Generated on demand
        "stl": {
            "exists": part.stl_file is not None,
            "url": f"/parts/{part.name}/stl" if part.stl_file else None,
            "generate_url": f"/parts/{part.name}/stl/generate",
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
    Attempts direct render; if underlying objects were deserialized without type info, rehydrate heuristically.
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
            raise HTTPException(status_code=500, detail=f"render failed: {e}")


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
            raise HTTPException(status_code=500, detail=str(e))


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


@app.post("/parts/{name}/stl/generate")
async def generate_part_stl(name: str, force: bool = Query(False)):
    """
    Generate an STL file from the part's SCAD source.

    Requires OpenSCAD to be installed on the server.

    Args:
        name: Part name
        force: If True, regenerate even if STL already exists

    Returns:
        Generation status with download URL on success
    """
    part = _load_part_wrapper(name)
    renderer = get_stl_renderer()

    if not renderer.is_available:
        raise HTTPException(
            status_code=503, detail="OpenSCAD not installed. Cannot generate STL files."
        )

    # Check if we already have an up-to-date STL
    if not force and part.stl_file and part.stl_file.exists():
        return {
            "success": True,
            "message": "STL already exists (use force=true to regenerate)",
            "stl_url": f"/parts/{name}/stl",
            "regenerated": False,
        }

    # Generate STL
    stl_path = part.source_file.with_suffix(".stl")
    result = await renderer.render_stl_async(part.source_file, stl_path)

    if not result.success:
        raise HTTPException(
            status_code=500, detail=f"STL generation failed: {result.error_message}"
        )

    return {
        "success": True,
        "message": f"STL generated successfully in {result.render_time_seconds:.1f}s",
        "stl_url": f"/parts/{name}/stl",
        "regenerated": True,
        "render_time_seconds": result.render_time_seconds,
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
# Sites carry no persistence layer: each request rebuilds the registered
# site fresh from its factory and applies any position overrides the client
# sends, the same stateless pattern /render already uses for Scene. There is
# no server-side "current state" between requests -- the client is expected
# to hold the full set of position overrides and resend it each time.
# =============================================================================

_SITE_REGISTRY = {
    "garage": (create_example_site, validate_garage_layout),
}


def _load_site(name: str):
    entry = _SITE_REGISTRY.get(name)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"Site '{name}' not found")
    factory, validator = entry
    return factory(), validator


def _bounds_dict(bounds: BoundingBox3D | None) -> Dict[str, List[float]] | None:
    if bounds is None:
        return None
    return {
        "min": [bounds.min_point.x, bounds.min_point.y, bounds.min_point.z],
        "max": [bounds.max_point.x, bounds.max_point.y, bounds.max_point.z],
    }


def _structure_summary(structure: Structure) -> Dict[str, object]:
    return {
        "name": structure.name,
        "material": structure.material,
        "position": {
            "x": structure.position.x,
            "y": structure.position.y,
            "z": structure.position.z,
        },
        "footprint": _bounds_dict(structure.footprint),
        "world_bounds": _bounds_dict(structure.world_bounds()),
        "substructures": [
            {
                "name": sub.name,
                "features": [f.name for f in (*sub.additions, *sub.subtractions)],
            }
            for sub in structure.substructures
        ],
    }


def _site_payload(site, report) -> Dict[str, object]:
    return {
        "name": site.name,
        "structures": [_structure_summary(s) for s in site.structures],
        "violations": [v.model_dump() for v in report.violations],
        "is_valid": report.is_valid,
    }


class PositionOverride(BaseModel):
    x: float
    y: float
    z: float


class LayoutRequest(BaseModel):
    positions: Dict[str, PositionOverride] = Field(default_factory=dict)


@app.get("/sites")
async def list_sites():
    return sorted(_SITE_REGISTRY.keys())


@app.get("/sites/{name}")
async def get_site(name: str):
    site, validator = _load_site(name)
    return _site_payload(site, validator(site))


@app.post("/sites/{name}/layout")
async def update_site_layout(name: str, body: LayoutRequest):
    """Apply position overrides, re-validate, and return regenerated OpenSCAD.

    ``body.positions`` need only include the structures the client has
    moved from their defaults; everything else keeps the factory's position.
    """
    site, validator = _load_site(name)
    for structure in site.structures:
        override = body.positions.get(structure.name)
        if override is not None:
            structure.position = Vector3D(x=override.x, y=override.y, z=override.z)

    payload = _site_payload(site, validator(site))
    payload["scad"] = site.render()
    return payload


@app.get("/viewer/sites/{name}", response_class=HTMLResponse)
async def site_viewer(name: str, request: Request):
    """Site/Structure hierarchy viewer: box-per-structure 3D manipulation (prototype)."""
    if name not in _SITE_REGISTRY:
        raise HTTPException(status_code=404, detail=f"Site '{name}' not found")
    base_url = str(request.base_url).rstrip("/")
    return HTMLResponse(
        render_site_viewer_page(sorted(_SITE_REGISTRY.keys()), base_url, default_site=name)
    )


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


@app.get("/viewer", response_class=HTMLResponse)
async def viewer_home(request: Request, part: str = Query(default="elephant_walk")):
    """
    Integrated 3D parts viewer with Three.js.

    Displays a browser-based viewer with:
    - Part selection dropdown
    - 3D preview (placeholder geometry)
    - OpenSCAD source code display
    - Download buttons for SCAD and JSCAD formats

    Args:
        part: Default part to load (defaults to elephant_walk)
    """
    parts = _available_part_names()
    base_url = str(request.base_url).rstrip("/")
    # Pass the default part to the viewer
    default_part = part if part in parts else (parts[0] if parts else None)
    return HTMLResponse(render_viewer_page(parts, base_url, default_part=default_part))


@app.get("/viewer/random")
async def viewer_random(request: Request):
    """
    Redirect to the viewer with a random part selected.

    Returns a redirect to the main viewer page. The random part
    selection is handled client-side for simplicity.
    """
    names = _available_part_names()
    if not names:
        raise HTTPException(status_code=404, detail="No parts available")
    picked = choice(names)
    # Redirect to main viewer - client can auto-load if needed
    return RedirectResponse(f"/viewer?part={picked}", status_code=307)


@app.get("/viewer/parts/{name}")
async def viewer_part(name: str, request: Request):
    """
    Redirect to the viewer with a specific part selected.
    """
    part = _load_part_wrapper(name)  # Validates part exists
    return RedirectResponse(f"/viewer?part={part.name}", status_code=307)
