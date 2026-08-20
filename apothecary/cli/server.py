"""Server-related CLI commands: serve, dev."""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import click
import uvicorn

from ..projects.parts.skeleton import ROOT
from ..projects.registry import scan_projects
from .utils import _get_stl_bounding_box, _safe_echo


@click.command()
@click.option("--host", default="127.0.0.1", help="Host to bind to")
@click.option("--port", default=8000, type=int, help="Port to bind to")
@click.option("--reload/--no-reload", default=False, help="Enable auto-reload on code changes")
@click.option(
    "--viewer-path",
    type=click.Path(file_okay=False, dir_okay=True, resolve_path=True, exists=True),
    help="Serve the JSCAD web viewer from this directory (defaults to node_modules/@jscad/web if present)",
)
@click.option("--no-viewer", is_flag=True, help="Disable the JSCAD viewer even if assets exist")
def serve(host: str, port: int, reload: bool, viewer_path: str | None, no_viewer: bool):
    """Run the FastAPI server."""
    # CRITICAL: Set environment variables BEFORE importing the app,
    # because the app module initializes the viewer mount at import time

    # Check for viewer assets and warn if missing
    viewer_available = False
    if no_viewer:
        os.environ["APOTHECARY_VIEWER_PATH"] = ""
        _safe_echo("⚠️  JSCAD viewer disabled via --no-viewer")
    elif viewer_path:
        os.environ["APOTHECARY_VIEWER_PATH"] = viewer_path
        viewer_available = True
        _safe_echo(f"✓ Using JSCAD viewer from: {viewer_path}")
    else:
        # Check default location
        default_viewer = ROOT / "node_modules" / "@jscad" / "web"
        env_viewer = os.getenv("APOTHECARY_VIEWER_PATH")

        if env_viewer and env_viewer.strip():
            viewer_check = Path(env_viewer.strip())
            if viewer_check.exists():
                viewer_available = True
                _safe_echo(f"✓ Using JSCAD viewer from environment: {viewer_check}")
            else:
                _safe_echo(
                    "⚠️  Warning: APOTHECARY_VIEWER_PATH set but path doesn't exist", fg="yellow"
                )
        elif default_viewer.exists():
            viewer_available = True
            # Set the environment variable so the app mount will work
            os.environ["APOTHECARY_VIEWER_PATH"] = str(default_viewer)
            _safe_echo(f"✓ JSCAD viewer found at: {default_viewer}")
        else:
            # Even if assets not found, still try to set it to the expected path
            # in case they get installed later
            os.environ["APOTHECARY_VIEWER_PATH"] = str(default_viewer)
            _safe_echo("⚠️  Warning: JSCAD viewer assets not found", fg="yellow", bold=True)
            click.echo("   Nothing serves these assets today -- see below.")
            click.echo("")
            click.secho("   To enable the viewer:", fg="yellow")
            _safe_echo("   • Run: apothecary install")
            _safe_echo("   • Or manually: npm install @jscad/web")
            _safe_echo("   • Or pass: --viewer-path /path/to/viewer/dist")
            _safe_echo("   • Or use: --no-viewer to suppress this warning")
            click.echo("")

    # NOW import the app after environment variables are set
    from ..api import app as fastapi_app

    # Start the server
    click.echo(f"Starting server on http://{host}:{port}")
    # One entry point. Everything else here is an API the viewer reads.
    click.echo(f"  Viewer: http://{host}:{port}/viewer")
    # The JSCAD assets above are mounted by no route -- the fractal viewer is
    # the only viewer, and it needs the vendored three.js, not these. The flags
    # are kept because they are published; the messages no longer claim the
    # viewer breaks without them.
    if not viewer_available and not no_viewer:
        click.echo("(the JSCAD assets are unused by any route; the viewer is unaffected)")

    if reload:
        # When reload is enabled, uvicorn needs an import string
        uvicorn.run("apothecary.api:app", host=host, port=port, reload=reload)
    else:
        # Without reload, we can pass the app directly
        uvicorn.run(fastapi_app, host=host, port=port, reload=False)


@click.command()
@click.option("--host", default="127.0.0.1", help="Host to bind to")
@click.option("--port", default=8000, type=int, help="Port to bind to")
@click.option(
    "--install", is_flag=True, help="Run uv sync before starting (usually not needed with uv run)"
)
@click.option("--skip-stl", is_flag=True, help="Skip STL generation")
@click.option("--elephant", is_flag=True, help="Force regeneration of elephant walk file")
def dev(host: str, port: int, install: bool, skip_stl: bool, elephant: bool):
    """Development workflow: regenerate files and start server.

    This convenience command runs the full dev setup:
    1. Optionally syncs dependencies (--install flag)
    2. Generates any missing STL files from SCAD sources
    3. Regenerates the elephant walk file if missing or --elephant flag is set
    4. Starts the dev server with auto-reload

    Example:
        apothecary dev
        apothecary dev --install --port 3000
    """
    _safe_echo("🧪 Apothecary Dev Mode", bold=True)
    click.echo("")

    # Step 1: Sync dependencies (optional)
    if install:
        click.secho("Step 1: Syncing dependencies...", fg="cyan")

        uv_path = shutil.which("uv")
        if uv_path:
            result = subprocess.run(
                ["uv", "sync"],
                cwd=ROOT,
                capture_output=True,
                text=True,
            )
        else:
            result = subprocess.run(
                [sys.executable, "-m", "pip", "install", "-e", ".", "-q"],
                cwd=ROOT,
                capture_output=True,
                text=True,
            )

        if result.returncode == 0:
            _safe_echo("  ✓ Dependencies synced", fg="green")
        else:
            _safe_echo(f"  ✗ Sync failed: {result.stderr}", fg="red")
            raise SystemExit(1)
    else:
        click.echo("Step 1: Skipped (use --install to sync)")

    # Step 2: Generate STL files
    if not skip_stl:
        click.secho("Step 2: Generating STL files...", fg="cyan")
        from ..projects.parts.stl_renderer import get_renderer

        renderer = get_renderer()

        if renderer.is_available:
            items = [p for p in scan_projects(ROOT) if p.kind == "part"]
            generated = 0
            skipped = 0

            for item in items:
                if "elephant" in item.name.lower():
                    continue  # Skip elephant_walk, regenerated separately
                stl_path = item.path.with_suffix(".stl")
                if stl_path.exists():
                    skipped += 1
                    continue
                click.echo(f"  Generating {item.name}...", nl=False)
                result = renderer.render_stl(item.path, stl_path, timeout=120)
                if result.success:
                    _safe_echo(" ✓", fg="green")
                    generated += 1
                else:
                    _safe_echo(" ✗", fg="red")

            _safe_echo(f"  ✓ {generated} generated, {skipped} already exist", fg="green")
        else:
            _safe_echo("  ⚠ OpenSCAD not found, skipping STL generation", fg="yellow")
    else:
        click.echo("Step 2: Skipped (--skip-stl)")

    # Step 3: Regenerate elephant walk
    if elephant or not (ROOT / "parts" / "elephant_walk.stl").exists():
        click.secho("Step 3: Regenerating elephant walk...", fg="cyan")
        elephant_path = ROOT / "parts" / "elephant_walk.scad"

        # Use the parts elephant-walk command logic
        from ..projects.parts.stl_renderer import get_renderer

        renderer = get_renderer()

        items = [
            p for p in scan_projects(ROOT) if p.kind == "part" and "elephant" not in p.name.lower()
        ]

        if items and renderer.is_available:
            # Calculate bounding boxes
            part_data = []
            for item in items:
                stl_path = item.path.with_suffix(".stl")
                bbox = _get_stl_bounding_box(stl_path)
                if bbox:
                    min_x, max_x, min_y, max_y, min_z, max_z = bbox
                    part_data.append(
                        {
                            "item": item,
                            "width": max_x - min_x,
                            "depth": max_y - min_y,
                            "height": max_z - min_z,
                            "center_x": (min_x + max_x) / 2,
                            "center_y": (min_y + max_y) / 2,
                            "min_y": min_y,
                            "max_y": max_y,
                        }
                    )
                else:
                    part_data.append(
                        {
                            "item": item,
                            "width": 50,
                            "depth": 50,
                            "height": 50,
                            "center_x": 0,
                            "center_y": 0,
                            "min_y": -25,
                            "max_y": 25,
                        }
                    )

            # Calculate positions
            gap = 10
            x_positions = []
            current_x = 0
            for i, data in enumerate(part_data):
                half_width = data["width"] / 2
                if i == 0:
                    x_positions.append(half_width)
                    current_x = half_width + data["width"] / 2
                else:
                    x_positions.append(current_x + gap + half_width)
                    current_x = x_positions[-1] + half_width

            # Generate SCAD content
            lines = [
                "// Elephant Walk - Auto-generated by apothecary dev",
                f"// Parts: {len(items)}, Gap: {gap}mm",
                "",
            ]

            for _i, (data, x_pos) in enumerate(zip(part_data, x_positions, strict=False)):
                item = data["item"]
                rel_path = item.path.relative_to(ROOT / "parts").with_suffix(".stl")
                translate_x = x_pos - data["center_x"]
                translate_y = -data["center_y"]
                lines.append(f"// {item.name}")
                lines.append(f"translate([{translate_x:.2f}, {translate_y:.2f}, 0])")
                lines.append(f'    import("{rel_path.as_posix()}");')
                lines.append("")

            elephant_path.write_text("\n".join(lines), encoding="utf-8")

            # Generate STL
            stl_path = elephant_path.with_suffix(".stl")
            click.echo("  Rendering elephant_walk.stl...", nl=False)
            result = renderer.render_stl(elephant_path, stl_path, timeout=180)
            if result.success:
                _safe_echo(f" ✓ ({result.render_time_seconds:.1f}s)", fg="green")
            else:
                _safe_echo(f" ✗ {result.error_message}", fg="red")
        else:
            _safe_echo("  ⚠ Skipped (no parts or OpenSCAD not found)", fg="yellow")
    else:
        click.echo("Step 3: Skipped (--skip-elephant)")

    # Step 4: Start dev server
    click.echo("")
    click.secho(f"Step 4: Starting dev server on http://{host}:{port}", fg="cyan")
    _safe_echo("  → Viewer: http://" + host + ":" + str(port) + "/viewer", fg="green")
    click.echo("")

    uvicorn.run("apothecary.api:app", host=host, port=port, reload=True)
